import traceback
import arcpy
import os, codecs
import uuid
import zipfile

# Global variables
field_we = None
field_ge = None
coord_format = None
out_folder = None

# Detect environment
PRODUCT_NAME = arcpy.GetInstallInfo()['ProductName']
IS_SERVER = PRODUCT_NAME == 'Server'
IS_PRO = PRODUCT_NAME == 'ArcGISPro'

# Function to handle Unicode transformation
def unicodify(row_val):
    return str(row_val) if row_val is not None else ''

# Get the name of the ObjectID field dynamically
def get_objectid_field_name(layer):
    return arcpy.Describe(layer).OIDFieldName

# Check and validate the fields in 'FIELDS_ADDR' for 'ADDRESS_LAYER'
def validate_fields(layer, fields):
    layer_fields = [field.name for field in arcpy.ListFields(layer)]
    missing_fields = [field for field in fields if field not in layer_fields]
    if missing_fields:
        arcpy.AddError(f"The following fields are missing in the address layer: {', '.join(missing_fields)}")
        return False
    return True

def generate_unique_filename(name_str, extension="zip"):
    if name_str:
        unique_name = f"{name_str}_{uuid.uuid4()}.{extension}"
    else:
        unique_name = f"{uuid.uuid4()}.{extension}"
    return os.path.join(arcpy.env.scratchFolder, unique_name)

def create_zip_from_files(files, zip_path):
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))  # Add files to the zip with their basename
    arcpy.AddMessage(f"Created ZIP archive: {zip_path}")

def project_to_utm(shape):
    # Determine the output spatial reference based on the X-coordinate of the geometry
    out_sr = 3044 if shape.firstPoint.X < 12 else 3045  # Assuming first point X-coordinate for this check
    # Project the shape to the target UTM spatial reference
    utm_point = shape.projectAs(arcpy.SpatialReference(out_sr), "DHDN_To_WGS_1984_5x + DHDN_To_ETRS_1989_8_NTv2")
    # Return the projected X and Y coordinates of the first point
    if utm_point and utm_point.firstPoint:
        return utm_point.firstPoint.X, utm_point.firstPoint.Y
    else:
        arcpy.AddWarning("The projection could not be completed successfully; the value is None.")
        return None, None

def project_to_utm32n(shape):
    utm32n_point = shape.projectAs(arcpy.SpatialReference(3044), "DHDN_To_WGS_1984_5x + DHDN_To_ETRS_1989_8_NTv2")
    if utm32n_point and utm32n_point.firstPoint:
        return utm32n_point.firstPoint.X, utm32n_point.firstPoint.Y
    else:
        arcpy.AddWarning("The projection could not be completed successfully; the value is None.")
        return None, None

def project_utm(shape, row):
    if coord_format.lower() == 'utm':
        x, y = project_to_utm(shape)  # Pass SHAPE@ geometry
        if field_ge and field_we:
            we_ge = [int(row[-3] or 0) + int(row[-2] or 0)] # we + ge
            csv_row = row[:-2] + tuple(we_ge) + (x, y)
        else:
            csv_row = row[:-1] + (x, y)
    elif coord_format.lower() == 'utm32n_wege':
        x, y = project_to_utm32n(shape)
        if field_ge and field_we:
            we_ge = [int(row[-3] or 0) + int(row[-2] or 0)]
            csv_row = row[:-2] + tuple(we_ge) + (x, y)
        else:
            csv_row = row[:-1] + (x, y)
    elif coord_format.lower() == 'utm32n_we_ge':
        x, y = project_to_utm32n(shape)
        csv_row = row[:-1] + (x, y)
    else:
        x, y = shape.firstPoint.X, shape.firstPoint.Y
        csv_row = row[:-1] + (x, y)
    return csv_row

def fcl_to_csv(fcl, csv_path, fields, custom_names):
    global coord_format   # Use global variables directly
    try:
        # Combine fields for the cursor, including geometry
        fields = fields + ["SHAPE@"]
        # Ensure the output directory exists
        output_dir = os.path.dirname(csv_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        spatial_reference = arcpy.Describe(fcl).spatialReference
        arcpy.AddMessage(f"Input coordinate system: {spatial_reference.name}")

        # Project data to WGS84 if UTM projection is needed and original is not WGS84
        if coord_format.lower().startswith('utm'):
            temp_fc = "in_memory\\temp_fc"
            arcpy.CopyFeatures_management(fcl, temp_fc)
            temp_layer = "in_memory\\temp_reprojected_layer"
            arcpy.Project_management(temp_fc, temp_layer, arcpy.SpatialReference(4326))
            arcpy.AddMessage("Layer reprojected to WGS 1984 for UTM determination.")
            fcl = temp_layer

        # Open the CSV file for writing
        with codecs.open(csv_path, "w", encoding="UTF-8") as f:
            header_fields = custom_names[:-1] + ["X", "Y"]
            f.write(";".join(header_fields) + os.linesep)  # CSV header
            # Process rows with `SearchCursor`
            with arcpy.da.SearchCursor(fcl, fields) as cursor:
                for row in cursor:
                    csv_row = project_utm(row[-1], row)
                    data = ";".join(map(str, csv_row)) + os.linesep
                    f.write(data)

        if not IS_SERVER:
            arcpy.AddMessage(f"Export completed to {csv_path}.")

        return csv_path  # Return path for download

    except Exception as e:
        arcpy.AddError(f"Error exporting to CSV: {e}")
        full_traceback = traceback.format_exc()
        arcpy.AddError(full_traceback)
    finally:
        # Clean up in-memory data if created
        if coord_format.startswith('utm'):
            if arcpy.Exists("in_memory\\temp_fc"):
                arcpy.Delete_management("in_memory\\temp_fc")
            if arcpy.Exists("in_memory\\temp_reprojected_layer"):
                arcpy.Delete_management("in_memory\\temp_reprojected_layer")

# Main function to execute the tool
def script_tool(poly_lyr, field_name, addr_lyr, fld_we, fld_ge, fld_addr, xy_format, out_dir, use_auth, url_portal, username, password, custom_names):

    global field_we, field_ge, coord_format
    field_we = fld_we
    field_ge = fld_ge
    coord_format = xy_format

    try:
        # Authentication check
        if use_auth or not arcpy.GetSigninToken() and url_portal and username and password:
                arcpy.SignInToPortal(url_portal, username, password)
                arcpy.AddMessage("Authenticated with provided credentials.")
        elif arcpy.GetSigninToken():
            arcpy.AddMessage("Authenticated with existing session.")
        else:
            raise ValueError("No authenticated session found and no credentials provided.")

        # Create feature layers if needed
        if not arcpy.Exists("temp_polygon_layer"):
            arcpy.MakeFeatureLayer_management(poly_lyr, "temp_polygon_layer")
        if not arcpy.Exists("temp_address_layer"):
            arcpy.MakeFeatureLayer_management(addr_lyr, "temp_address_layer")

        fields = fld_addr + [fld_we, fld_ge] if (field_ge and field_we) else fld_addr
        # Validate that fields exist in ADDRESS_LAYER
        if not validate_fields("temp_address_layer", fields):
            raise ValueError("Some required fields do not exist in the address layer.")

        oid_polygon_field = get_objectid_field_name("temp_polygon_layer")
        # Obtain unique OIDs to reduce processing time
        oids = [row[0] for row in arcpy.da.SearchCursor("temp_polygon_layer", [oid_polygon_field])]

        output_files = []
        for oid in oids:
            arcpy.SelectLayerByAttribute_management("temp_polygon_layer", "NEW_SELECTION", f"{oid_polygon_field} = {oid}")

            polygon_data = [(row[0], row[1]) for row in arcpy.da.SearchCursor("temp_polygon_layer", [field_name, oid_polygon_field])]

            for name, objectid in polygon_data:
                if not name:
                    raise ValueError("the values from polygon layer field name can not empty.")
                filename = f"{name}_{objectid}.csv"
                filepath = os.path.join(out_dir, filename) if not IS_SERVER else generate_unique_filename(filename, "csv")
                arcpy.SelectLayerByLocation_management("temp_address_layer", "WITHIN", "temp_polygon_layer")
                # Check if temp_address_layer has selected records
                count = int(arcpy.GetCount_management("temp_address_layer").getOutput(0))
                if count > 0:
                    arcpy.AddMessage(f"Creating {filepath}, total addresses={count}")
                    fcl_to_csv("temp_address_layer", filepath, fields, custom_names)
                    output_files.append(filepath)

        # Handle unique filename for server environment
        if IS_SERVER:
            # Create a zip archive of all CSV files
            zip_path = generate_unique_filename("zip")
            create_zip_from_files(output_files, zip_path)
            # Set the ZIP file as output for download
            arcpy.SetParameterAsText(12, zip_path)

        arcpy.AddMessage("Export completed successfully.")

    except Exception as e:
        arcpy.AddError(f"Error in script execution: {e}")
        full_traceback = traceback.format_exc()
        arcpy.AddError(full_traceback)
    finally:
        if arcpy.Exists("temp_polygon_layer"):
            arcpy.Delete_management("temp_polygon_layer")
        if arcpy.Exists("temp_address_layer"):
            arcpy.Delete_management("temp_address_layer")

def transform_field_address_names(field_address_names):
    pairs = field_address_names.split(';')

    field_address = []
    custom_names = []

    for pair in pairs:
        elements = pair.split(" ", 1)
        if len(elements) == 2:
            field = elements[0]
            name = elements[1].strip() 
            if name.startswith("'") and name.endswith("'"):
                name = name[1:-1] 

            field_address.append(field)
            custom_names.append(name)

    return field_address, custom_names


# Entry point for script execution
if __name__ == "__main__":
    # Retrieve parameters as global variables
    polygon_layer = arcpy.GetParameter(0)
    field_name = arcpy.GetParameterAsText(1)
    address_layer = arcpy.GetParameter(2)
    fields_we_ge = arcpy.GetParameterAsText(3).lower() == 'true'
    field_we = arcpy.GetParameterAsText(4)
    field_ge = arcpy.GetParameterAsText(5)
    field_address_names = str(arcpy.GetParameter(6)) # Assumes value-table parameter
    coord_format = arcpy.GetParameterAsText(7)
    out_folder = arcpy.GetParameterAsText(8)
    use_auth = arcpy.GetParameterAsText(9).lower() == 'true'
    url_portal = arcpy.GetParameterAsText(10)
    username = arcpy.GetParameterAsText(11)
    password = arcpy.GetParameterAsText(12)
    field_address, custom_names = transform_field_address_names(field_address_names)
    # Output for the CSV download

    # Execute the script tool
    script_tool(polygon_layer, field_name, address_layer, field_we, field_ge, field_address, coord_format, out_folder,
                use_auth, url_portal, username, password, custom_names)
