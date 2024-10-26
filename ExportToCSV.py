import arcpy
import os, codecs

# Function to handle Unicode transformation
def unicodify(row_val):
    """
    Ensures all values are converted to Unicode format.
    :param row_val: The row value to be converted
    :return: Unicode string representation of the row value
    """
    if row_val is None:
        return u''
    return str(row_val)


# Function to export feature class to CSV
def fcl_to_csv(fcl, csv_path, utm):
    """
    Exports the features from a layer to a CSV file.
    :param fcl: Feature class or layer
    :param csv_path: Output CSV file path
    :param utm: Boolean to determine if UTM projection is needed
    """
    try:
        # Get spatial reference of input data
        spatialReference = arcpy.Describe(fcl).spatialReference
        arcpy.AddMessage("Input coordinate system: " + spatialReference.name)
        outSR = 102100  # Default to Web Mercator

        with codecs.open(csv_path, "w", encoding="UTF-8") as f:
            # Define the fields to extract
            fields = [u"tzipcode", u"Stadt", u"Stra\xdfe", u"Nr", u"Zusatz", u"WE", u"GE", u"Anzahl", u"SHAPE@X", u"SHAPE@Y"]

            with arcpy.da.SearchCursor(fcl, fields) as cursor:
                for row in cursor:
                    x, y = row[8], row[9]

                    if utm:
                        # Reproject point coordinates if UTM is required
                        point = arcpy.Point(x, y)
                        pointGeometry = arcpy.PointGeometry(point, spatialReference, False, False)
                        xp = pointGeometry.projectAs(arcpy.SpatialReference(4326))

                        outSR = 3044 if xp.firstPoint.X < 12 else 3045
                        utmPoint = pointGeometry.projectAs(arcpy.SpatialReference(outSR), "DHDN_To_WGS_1984_5x + DHDN_To_ETRS_1989_8_NTv2")
                        x, y = utmPoint.firstPoint.X, utmPoint.firstPoint.Y

                    # Create the CSV row
                    we, ge = int(row[5] or 0), int(row[6] or 0)
                    we_ge = we + ge
                    csv_row = [row[0], row[1], row[2], row[3], row[4], we_ge, row[7], x, y]
                    csv_row = [unicodify(item) for item in csv_row]

                    # Write to CSV file
                    f.write(u";".join(csv_row) + os.linesep)

        arcpy.AddMessage("Output coordinate system: " + arcpy.SpatialReference(outSR).name)
    except Exception as e:
        arcpy.AddError(f"Error exporting to CSV: {e}")


# Main function to execute the tool
def script_tool(polygon_layer, address_layer, out_path, coordinate_format):
    """
    Main script tool function to handle input parameters and export to CSV.
    :param polygon_layer: Input polygon feature layer
    :param address_layer: Input address feature layer
    :param out_path: Output directory for CSV files
    :param coordinate_format: Coordinate format (e.g., UTM or other)
    """
    try:
        # Convert coordinate format to boolean for UTM projection
        convert_utm = coordinate_format.lower() == "utm"

        # Collect selected object IDs from the polygon layer
        oids = []
        with arcpy.da.SearchCursor(polygon_layer, ["*"]) as cursor:
            for row in cursor:
                oids.append(row[0])

        # Process each selected polygon
        for oid in oids:
            arcpy.SelectLayerByAttribute_management(polygon_layer, "NEW_SELECTION", f"objectid = {oid}")
            with arcpy.da.SearchCursor(polygon_layer, ["name", "id"]) as polygon_cursor:
                for row in polygon_cursor:
                    filename = f"{row[0]}_{row[1]}.csv"
                    filepath = os.path.join(out_path, filename)
                    arcpy.AddMessage(f"Creating {filepath}...")

                    # Select address points within the current polygon
                    arcpy.SelectLayerByLocation_management(address_layer, "WITHIN", polygon_layer)
                    
                    # Export the address layer to CSV
                    fcl_to_csv(address_layer, filepath, convert_utm)
        
        arcpy.AddMessage("Export completed successfully.")
    except Exception as e:
        arcpy.AddError(f"Error in script execution: {e}")


# Entry point for script execution
if __name__ == "__main__":
    # Get tool parameters from ArcGIS Pro interface
    polygon_layer = arcpy.GetParameterAsText(0)
    address_layer = arcpy.GetParameterAsText(1)
    out_path = arcpy.GetParameterAsText(2)
    coordinate_format = arcpy.GetParameterAsText(3)

    # Execute the script tool
    script_tool(polygon_layer, address_layer, out_path, coordinate_format)
