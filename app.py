import os
import time
import yaml
import threading
from src.db_utils import connect_to_db, close_connection
from src.yaml_utils import generate_camera_yaml
from src.json_utils import generate_json
from src.video_feed import app  # Importamos Flask app desde video_feed.py
from src.buffers_camaras import start_streaming_from_configs
from src.variables_globales import get_streamers, get_threads, set_streamers, set_threads
from src.notifications import procesar_detecciones


def load_yaml_config(path):
    """
    Carga un archivo YAML y devuelve su contenido como diccionario.
    """
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

def start_flask_server():
    """
    Inicia el servidor Flask en un hilo separado.
    """
    app.run(host="0.0.0.0", port=5000)

# def monitor_database(db_config):
#     """
#     Monitorea la base de datos periódicamente y actualiza los archivos YAML y JSON.
#     """
#     previous_data = []  # Almacenar los datos previos de la base de datos

#     while True:
#         try:
#             # Establece una nueva conexión en cada iteración
#             connection = connect_to_db(db_config)

#             cursor = connection.cursor(dictionary=True)
#             cursor.execute(db_config["query_yaml"])
#             cameras = cursor.fetchall()

#             # print("Datos obtenidos de la base de datos:", cameras)

#             # Comparar datos actuales con datos previos
#             if cameras != previous_data:

#                 # Actualizar archivos YAML
#                 generate_camera_yaml(cameras)

#                 # Generar el archivo JSON con todos los datos
#                 cursor.execute(db_config["query_json"])
#                 data = cursor.fetchall()
#                 generate_json(data)

#                 # Actualizar el array de datos previos
#                 previous_data = cameras
#             else:
#                 print("")
#         except Exception as e:
#             print(f"Error monitoreando la base de datos: {e}")

#         finally:
#             # Asegúrate de cerrar la conexión después de cada iteración
#             close_connection(connection)

#         # Pausa antes de la próxima verificación
#         time.sleep(5)

# if __name__ == "__main__":
#     # Cargar configuración desde database.yaml
#     db_config = load_yaml_config("configs/database.yaml")["database"]

#     # Iniciar el servidor Flask en un hilo separado
#     flask_thread = threading.Thread(target=start_flask_server, daemon=True)
#     flask_thread.start()
    
#     # Llamar a la función para iniciar el streaming
#     streamers, threads = start_streaming_from_configs()
#     print("Streamers: ",streamers[2].camara_url)

#     # Iniciar el monitoreo de la base de datos en el hilo principal
#     monitor_database(db_config)

def monitor_database_and_start_detections(db_config):
    """
    Monitorea la base de datos, actualiza archivos YAML/JSON, e inicia hilos de detección por cámara.
    """
    previous_data = []  # Almacenar datos previos de la base de datos
    detecciones_threads = {}  # Almacenar hilos por cámara

    while True:
        try:
            # Establece una nueva conexión en cada iteración
            connection = connect_to_db(db_config)
            cursor = connection.cursor(dictionary=True)
            cursor.execute(db_config["query_yaml"])
            cameras = cursor.fetchall()

            # Actualizar YAML si hay cambios en la base de datos
            if cameras != previous_data:
                print("Datos obtenidos de la base de datos:", cameras)
                generate_camera_yaml(cameras)  # Actualizar YAML
                cursor.execute(db_config["query_json"])
                data = cursor.fetchall()
                generate_json(data)
                previous_data = cameras

                # Iniciar o reiniciar hilos de detección para cada cámara
                for camera in cameras:
                    camera_id = camera["ID"]
                    config_path = f"configs/camera_{camera_id}.yaml"

                    # Si ya existe un hilo para esta cámara, no lo vuelvas a iniciar
                    if camera_id in detecciones_threads and detecciones_threads[camera_id].is_alive():
                        continue
                    print("Info camara: ",config_path, camera_id)
                    # Iniciar un nuevo hilo para detecciones
                    thread = threading.Thread(
                        target=procesar_detecciones,
                        args=(config_path, camera_id),
                        daemon=True
                    )
                    detecciones_threads[camera_id] = thread
                    thread.start()
                    print(f"Hilo de detección iniciado para la cámara {camera_id}.")

        except Exception as e:
            print(f"Error monitoreando la base de datos: {e}")
        finally:
            close_connection(connection)

        # Pausa antes de la próxima verificación
        time.sleep(5)

if __name__ == "__main__":
    
    # Vaciar la carpeta de videos
    # Verifica si la carpeta existe
    if os.path.exists("Videos"):
        # Itera sobre los elementos de la carpeta
        for elemento in os.listdir("Videos"):
            elemento_ruta = os.path.join("Videos", elemento)
            # Elimina archivos
            if os.path.isfile(elemento_ruta) or os.path.islink(elemento_ruta):
                os.unlink(elemento_ruta)
    
    # Cargar configuración desde database.yaml
    db_config = load_yaml_config("configs/database.yaml")["database"]

    # Iniciar el servidor Flask en un hilo separado
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()

    # Iniciar el streaming
    streamers, threads = start_streaming_from_configs()
    print("Streamers: ", [s.camara_url for s in streamers.values()])

    # Monitorear la base de datos e iniciar hilos de detección
    monitor_database_and_start_detections(db_config)

