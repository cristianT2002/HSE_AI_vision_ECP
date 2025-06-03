
import os
import yaml
import json
from src.db_utils import connect_to_db, close_connection 

CONFIGS_FOLDER = "configs"

def load_yaml_config(path):
    """
    Carga un archivo YAML y devuelve su contenido como diccionario.
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error cargando el archivo YAML: {e}")
        raise

def fetch_camera_data():
    """
    Conecta a la base de datos y obtiene los datos de las cámaras.
    """
    connection = connect_to_db()  # Conexión a la base de datos
    cursor = connection.cursor()

    try:
        # Ajusta la consulta a tu esquema de base de datos
        query = "SELECT ID, LUGAR, PUNTO, NOMBRE_CAMARA, IP_CAMARA, USUARIO, CONTRASENA, COORDENADAS_AREA, ESTADO_LUGAR_MODELO, TIME_AREAS, INFO_NOTIFICATIONS, DESTINATARIOS FROM IP_Videofeed3"
        cursor.execute(query)
        rows = cursor.fetchall()

        # Convertir los resultados en una lista de diccionarios
        columns = [col[0] for col in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]

        return data
    except Exception as e:
        print(f"Error obteniendo datos de la base de datos: {e}")
        return []
    finally:
        cursor.close()
        close_connection(connection)

def generate_camera_yaml(data):
    """
    Genera un archivo YAML por cada cámara en la base de datos.
    """
    if not os.path.exists(CONFIGS_FOLDER):
        os.makedirs(CONFIGS_FOLDER)

    existing_files = set(os.listdir(CONFIGS_FOLDER))

    for camera in data:
        # print(camera)
        camera_id = camera["id_camara"]
        place_cam = camera["id_axure"]
        ponit_int = camera["id_proyecto"]
        name_cliente = camera["id_cliente"]
        name_cam = camera["nombre_camara"]
        ip_camera = camera["ip_camara"]
        username = camera["usuario"]
        password = camera["contrasena"]
        coordinates = camera["coordenadas_area"]  # Se espera que sea un string JSON
        times_areas = camera["time_areas"]
        info_notifications = camera["info_notifications"]
        info_emails = camera["destinatarios"]
        info_numeros = camera["numeros"]

        # Convertir coordinates a un diccionario Python----------------------------------------------------
        try:
            print(coordinates)
            coordinates_dict = json.loads(coordinates)
        except json.JSONDecodeError:
            print(f"Error: `COORDENADAS_AREA` no es un JSON válido para la cámara {camera_id}.")
            continue

        # rtsp_url = f"rtsp://{username}:{password}@{ip_camera}:554/Streaming/Channels/102"
        rtsp_url = "VideosEnsayoModelo/muchas-personas-perimetral2.mp4"
        model = "best.pt"

        camera_config = {
            "camera": {
                "rtsp_url": rtsp_url,
                "username": username,
                "password": password,
                "ip": ip_camera,
                "port": 554,
                "point": ponit_int,
                "client": name_cliente,
                "place": place_cam,
                "name camera": name_cam,
                "coordinates": coordinates_dict,
                "label": camera["estado_lugar_modelo"],
                "time_areas": times_areas,
                "info_notifications": info_notifications,
                "info_emails": info_emails,
                "info_numeros": info_numeros
            },
            "model": {
                "path": f"models/{model}"
            },
            "labels": ["A_Person", "Harness", "No_Helmet", "White", "YellowGreen"]
        }
        

        output_file = os.path.join(CONFIGS_FOLDER, f"camera_{camera_id}.yaml")
        with open(output_file, "w", encoding="utf-8") as file:
            yaml.dump(camera_config, file, default_flow_style=False, allow_unicode=True)

        print(f"Archivo YAML generado o actualizado: {output_file}")
        existing_files.discard(f"camera_{camera_id}.yaml")

    # Eliminar archivos YAML que no están en la base de datos
    for leftover_file in existing_files:
        file_path = os.path.join(CONFIGS_FOLDER, leftover_file)
        if leftover_file.startswith("camera_") and leftover_file.endswith(".yaml"):
            os.remove(file_path)
            print(f"Archivo YAML eliminado: {file_path}")

if __name__ == "__main__":
    # Obtener datos de la base de datos
    camera_data = fetch_camera_data()
    if camera_data:
        generate_camera_yaml(camera_data)
    else:
        print("No se encontraron datos para generar los archivos YAML.")
