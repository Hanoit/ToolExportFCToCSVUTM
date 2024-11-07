import ssl
import unittest
import arcpy
import os
import requests
from ExportToCSV import script_tool, transform_field_address_names

class TestExportToCSV(unittest.TestCase):
    def setUp(self):
        self.url = "https://portal.beexact.com/arcgis"
        self.username = "developer.it"
        self.password = "sinhyw-hergip-8degMu"

        arcpy.SignInToPortal(self.url, self.username, self.password)
        print("Authenticated to portal")

        if not arcpy.GetSigninToken():
            self.fail("Portal authentication failed")

        self.test_polygon_layer = "https://portal.beexact.com/server/rest/services/geodata_editor_beeXact_Polygons_BeeXact_EDIT/FeatureServer/695"
        self.test_address_layer = "https://portal.beexact.com/server/rest/services/geodata_editor_beeXact_Addresses_MIH/FeatureServer/1240"

        arcpy.MakeFeatureLayer_management(self.test_polygon_layer, "temp_test_polygon_lyr")
        arcpy.MakeFeatureLayer_management(self.test_address_layer, "temp_test_address_lyr")

        print("Polygon layer created:", arcpy.Exists("temp_test_polygon_lyr"))
        print("Address layer created:", arcpy.Exists("temp_test_address_lyr"))

        self.test_out_path = "./Results"
        if not os.path.exists(self.test_out_path):
            os.makedirs(self.test_out_path)
        print("Output path exists:", os.path.exists(self.test_out_path))

        self.test_coordinate_format = "UTM"
        self.field_name_poly_layer = "objectid"
        self.field_we = "we"
        self.field_ge = "ge"
        self.fields_address_layer = [
            field.name for field in arcpy.ListFields("temp_test_address_lyr") if
            field.name not in [self.field_we, self.field_ge]
        ]
        self.field_address_names = arcpy.ValueTable(2)
        for field, name in zip(self.fields_address_layer, self.fields_address_layer):
            self.field_address_names.addRow(f"{field} {name}")

        self.field_address, self.custom_names = transform_field_address_names(str(self.field_address_names))

    def test_script_tool_execution(self):
        # Verifica la ejecución del script
        try:
            script_tool("temp_test_polygon_lyr", self.field_name_poly_layer, "temp_test_address_lyr",
                        self.field_we, self.field_ge, self.field_address, self.test_coordinate_format,
                        self.test_out_path, False, None, None, None, self.custom_names)
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"script_tool failed with error: {e}")

    def test_csv_creation(self):
        # Verifica la creación de CSV
        script_tool("temp_test_polygon_lyr", self.field_name_poly_layer, "temp_test_address_lyr",
                    self.field_we, self.field_ge, self.field_address, self.test_coordinate_format,
                    self.test_out_path, False, None, None, None, self.custom_names)
        csv_files = os.listdir(self.test_out_path)
        self.assertGreater(len(csv_files), 0, "No CSV files created")

    def tearDown(self):
        # Opcional: limpiar archivos CSV generados
        for file in os.listdir(self.test_out_path):
            os.remove(os.path.join(self.test_out_path, file))

if __name__ == '__main__':
    unittest.main()
