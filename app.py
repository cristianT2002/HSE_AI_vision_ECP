import os
import time
import yaml
import threading
from src.db_utils import connect_to_db, close_connection
from src.yaml_utils import generate_camera_yaml
from src.json_utils import generate_json
from src.video_feed import app  # Importamos Flask app desde video_feed.py

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

def monitor_database(db_config):
    """
    Monitorea la base de datos periódicamente y actualiza los archivos YAML y JSON.
    """
    previous_data = []  # Almacenar los datos previos de la base de datos

    while True:
        try:
            # Establece una nueva conexión en cada iteración
            connection = connect_to_db(db_config)

            print("Conectado a la base de datos. Consultando cambios...")
            cursor = connection.cursor(dictionary=True)
            cursor.execute(db_config["query_yaml"])
            cameras = cursor.fetchall()

            # print("Datos obtenidos de la base de datos:", cameras)

            # Comparar datos actuales con datos previos
            if cameras != previous_data:
                print("Se detectaron cambios en la base de datos. Actualizando archivos YAML y JSON...")

                # Actualizar archivos YAML
                generate_camera_yaml(cameras)

                # Generar el archivo JSON con todos los datos
                cursor.execute(db_config["query_json"])
                data = cursor.fetchall()
                generate_json(data)

                # Actualizar el array de datos previos
                previous_data = cameras
            else:
                print("No se detectaron cambios en la base de datos.")

        except Exception as e:
            print(f"Error monitoreando la base de datos: {e}")

        finally:
            # Asegúrate de cerrar la conexión después de cada iteración
            close_connection(connection)

        # Pausa antes de la próxima verificación
        time.sleep(5)

if __name__ == "__main__":
    # Cargar configuración desde database.yaml
    db_config = load_yaml_config("configs/database.yaml")["database"]

    # Iniciar el servidor Flask en un hilo separado
    print("Iniciando el servidor Flask para video feeds...")
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()

    # Iniciar el monitoreo de la base de datos en el hilo principal
    print("Iniciando monitoreo de la base de datos...")
    monitor_database(db_config)