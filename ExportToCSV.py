import arcpy
import os, codecs
import uuid
import zipfile

# Global variables
FIELD_GE = None
FIELD_WE = None
FIELDS_ADDR = []
POLYGON_LAYER = None
ADDRESS_LAYER = None
COORD_FORMAT = None
OUT_FOLDER = None

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

def generate_unique_filename(name, extension="zip"):
    if (name):
        unique_name = f"{name}_{uuid.uuid4()}.{extension}"
    else:
        unique_name = f"{uuid.uuid4()}.{extension}"
    return os.path.join(arcpy.env.scratchFolder, unique_name)

def create_zip_from_files(files, zip_path):
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))  # Add files to the zip with their basename
    arcpy.AddMessage(f"Created ZIP archive: {zip_path}")

def project_UTM(shape):
    # Determine the output spatial reference based on the X-coordinate of the geometry
    outSR = 3044 if shape.firstPoint.X < 12 else 3045  # Assuming first point X-coordinate for this check
    # Project the shape to the target UTM spatial reference
    utm_point = shape.projectAs(arcpy.SpatialReference(outSR), "DHDN_To_WGS_1984_5x + DHDN_To_ETRS_1989_8_NTv2")
    # Return the projected X and Y coordinates of the first point
    return utm_point.firstPoint.X, utm_point.firstPoint.Y

def project_UTM32N(shape):
    utm32n_point = shape.projectAs(arcpy.SpatialReference(3044), "DHDN_To_WGS_1984_5x + DHDN_To_ETRS_1989_8_NTv2")
    return utm32n_point.firstPoint.X, utm32n_point.firstPoint.Y

def fcl_to_csv(fcl, csv_path, fields):
    global FIELD_GE, FIELD_WE, COORD_FORMAT   # Use global variables directly

    try:
        # Combine fields for the cursor, including geometry
        fields = fields + ["SHAPE@X", "SHAPE@Y", "SHAPE@"]
        # Ensure the output directory exists
        output_dir = os.path.dirname(csv_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        spatial_reference = arcpy.Describe(fcl).spatialReference
        arcpy.AddMessage(f"Input coordinate system: {spatial_reference.name}")

        # Project data to WGS84 if UTM projection is needed and original is not WGS84
        if COORD_FORMAT.startswith('utm'):
            temp_fc = "in_memory\\temp_fc"
            arcpy.CopyFeatures_management(fcl, temp_fc)
            temp_layer = "in_memory\\temp_reprojected_layer"
            arcpy.Project_management(temp_fc, temp_layer, arcpy.SpatialReference(4326))
            arcpy.AddMessage("Layer reprojected to WGS 1984 for UTM determination.")
            fcl = temp_layer

        # Open the CSV file for writing
        with codecs.open(csv_path, "w", encoding="UTF-8") as f:
            f.write(";".join(fields[:-1]) + os.linesep)  # CSV header
            index = 0
            # Process rows with `SearchCursor`
            with arcpy.da.SearchCursor(fcl, fields) as cursor:
                for row in cursor:
                    if COORD_FORMAT.lower() == 'utm':
                        x, y = project_UTM(row[-1])  # Pass SHAPE@ geometry
                        wege = [int(row[-5] or 0) + int(row[-4] or 0)]
                        csv_row = row[:-5] + [wege, x, y] # we + ge
                    elif COORD_FORMAT.lower() == 'utm32n_wege':
                        x, y = project_UTM32N(row[-1]) # Pass SHAPE@ geometry
                        wege = [int(row[-5] or 0) + int(row[-4] or 0)] # we + ge
                        csv_row = row[:-5] + [wege, x, y]
                    elif COORD_FORMAT.lower() == 'utm32n_we_ge':
                        x, y = project_UTM32N(row[10])
                        csv_row = row[:-3] + [x, y]
                    else:
                        csv_row = row[:-1]
                    data = ";".join(map(str, csv_row)) + os.linesep
                    arcpy.AddMessage(f"Export completed to {++index}{data}.")
                    f.write(data)

        if not IS_SERVER:
            arcpy.AddMessage(f"Export completed to {csv_path}.")

        return csv_path  # Return path for download

    except Exception as e:
        arcpy.AddError(f"Error exporting to CSV: {e}")
    finally:
        # Clean up in-memory data if created
        if coord_format.startswith('utm'):
            if arcpy.Exists("in_memory\\temp_fc"):
                arcpy.Delete_management("in_memory\\temp_fc")
            if arcpy.Exists("in_memory\\temp_reprojected_layer"):
                arcpy.Delete_management("in_memory\\temp_reprojected_layer")


# Main function to execute the tool
def script_tool(polygon_layer, field_name, address_layer, field_we, field_ge, field_addr, coord_format, out_folder,
                 use_auth, url_portal, username, password):

    global POLYGON_LAYER, ADDRESS_LAYER, FIELD_WE, FIELD_GE, FIELDS_ADDR, COORD_FORMAT
    POLYGON_LAYER = polygon_layer
    ADDRESS_LAYER = address_layer
    FIELD_WE = field_we
    FIELD_GE = field_ge
    FIELDS_ADDR = field_addr
    COORD_FORMAT = coord_format

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
            arcpy.MakeFeatureLayer_management(POLYGON_LAYER, "temp_polygon_layer")
        if not arcpy.Exists("temp_address_layer"):
            arcpy.MakeFeatureLayer_management(ADDRESS_LAYER, "temp_address_layer")

        fields =  FIELDS_ADDR + [FIELD_WE, FIELD_GE]
        # Validate that fields exist in ADDRESS_LAYER
        if not validate_fields("temp_address_layer", fields):
            raise ValueError("Some required fields do not exist in the address layer.")

        objectid_polygon_field = get_objectid_field_name("temp_polygon_layer")
        # Obtain unique OIDs to reduce processing time
        oids = [row[0] for row in arcpy.da.SearchCursor("temp_polygon_layer", [objectid_polygon_field])]

        output_files = []
        for oid in oids:
            arcpy.SelectLayerByAttribute_management("temp_polygon_layer", "NEW_SELECTION", f"{objectid_polygon_field} = {oid}")

            polygon_data = [(row[0], row[1]) for row in
                            arcpy.da.SearchCursor("temp_polygon_layer", [field_name, objectid_polygon_field])]

            for name, objectid in polygon_data:
                if not name:
                    raise ValueError("the values from polygon layer field name can not empty.")
                filename = f"{name}_{objectid}.csv"
                filepath = os.path.join(out_folder, filename) if not IS_SERVER else generate_unique_filename(filename, "csv")
                arcpy.SelectLayerByLocation_management("temp_address_layer", "WITHIN", "temp_polygon_layer")
                # Check if temp_address_layer has selected records
                count = int(arcpy.GetCount_management("temp_address_layer").getOutput(0))
                if count > 0:
                    arcpy.AddMessage(f"Creating {filepath}, total addresses={count}")
                    fcl_to_csv("temp_address_layer", filepath, fields)
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
    finally:
        if arcpy.Exists("temp_polygon_layer"):
            arcpy.Delete_management("temp_polygon_layer")
        if arcpy.Exists("temp_address_layer"):
            arcpy.Delete_management("temp_address_layer")


# Entry point for script execution
if __name__ == "__main__":
    # Retrieve parameters as global variables
    polygon_layer = arcpy.GetParameter(0)
    field_name = arcpy.GetParameterAsText(1)
    address_layer = arcpy.GetParameter(2)
    field_we = arcpy.GetParameterAsText(3)
    field_ge = arcpy.GetParameterAsText(4)
    field_address = [field.value for field in arcpy.GetParameter(5)] # Assumes multi-value list parameter
    coord_format = arcpy.GetParameterAsText(6)
    out_folder = arcpy.GetParameterAsText(7)
    use_auth = arcpy.GetParameterAsText(8).lower() == 'true'
    url_portal = arcpy.GetParameterAsText(9)
    username = arcpy.GetParameterAsText(10)
    password = arcpy.GetParameterAsText(11)
    # Output for the CSV download

    # Execute the script tool
    script_tool(polygon_layer, field_name, address_layer, field_we, field_ge, field_address, coord_format, out_folder,
                use_auth, url_portal, username, password)
