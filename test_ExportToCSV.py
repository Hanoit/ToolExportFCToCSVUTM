import ssl
import unittest
from arcgis.gis import GIS
from spnego import client

from ExportToCSV import script_tool
import os
import requests

# Función para generar el token
def generate_token(username, password, portal_url, referer='*'):
    token_url = f"{portal_url}/sharing/rest/generateToken"
    payload = {
        'f': 'json',
        'username': username,
        'password': password,
        'client': 'referer',
        'referer': referer,
        'expiration': 60
    }

    response = requests.post(token_url, data=payload, verify=False)
    if response.status_code == 200:
        token = response.json().get('token')
        if token:
            return token
        else:
            raise Exception(f"Error generating token: {response.json().get('error')}")
    else:
        raise Exception(f"Error connecting to portal: {response.status_code}, {response.text}")


class TestExportToCSV(unittest.TestCase):

    def setUp(self):
        # Datos para la autenticación

        # disable ssl certificate validation
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            # Legacy Python that doesn't verify HTTPS certificates by default
            pass
        else:
            # Handle target environment that doesn't support HTTPS verification
            ssl._create_default_https_context = _create_unverified_https_context

        self.url = "https://portal.beexact.com/arcgis"
        self.username = "developer.it"
        self.password = "sinhyw-hergip-8degMu"

        # Conectar a ArcGIS Online usando el token
        self.gis = GIS(self.url, self.username,  self.password)

        # Cargar las capas desde ArcGIS Online
        self.test_polygon_layer = self.gis.content.get("6bc5263fdb8a4d5ead4ce5ec8b879dd7").layers[0]
        self.test_address_layer = self.gis.content.get("b20c1348cdae4878b3c73e02dd885687").layers[0]
        self.test_out_path = "/"
        self.test_coordinate_format = "UTM"

    def test_script_tool_execution(self):
        # Verifica la ejecución del script
        try:
            script_tool(self.test_polygon_layer, self.test_address_layer, self.test_out_path,
                        self.test_coordinate_format)
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"script_tool failed with error: {e}")

    def test_csv_creation(self):
        # Verifica la creación de CSV
        script_tool(self.test_polygon_layer, self.test_address_layer, self.test_out_path, self.test_coordinate_format)
        csv_files = os.listdir(self.test_out_path)
        self.assertGreater(len(csv_files), 0, "No CSV files created")

    def tearDown(self):
        # Opcional: limpiar archivos CSV generados
        pass


if __name__ == '__main__':
    unittest.main()
