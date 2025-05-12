import os
import time
import yaml
import threading
from src.db_utils import connect_to_db, close_connection
from src.yaml_utils import generate_camera_yaml
from src.json_utils import generate_json
from src.video_feed import app  # Importamos Flask app desde video_feed.py
from src.buffers_camaras import start_streaming_from_configs
from src.variables_globales import get_streamers, get_threads, set_streamers, set_threads, set_streamers_procesado
from src.notifications import ProcesarDetecciones
import multiprocessing as mp
from src.variables_globales import set_processes, get_processes, set_ip_local, get_ip_local, obtener_ip_local
from multiprocessing import Manager
import psycopg2
import socket

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



def monitor_database_and_start_detections(db_config, shared_buffers):
    """
    Monitorea la base de datos, actualiza YAML/JSON e inicia procesos de detección por cámara.
    """
    previous_data = []  # Almacenar datos previos de la base de datos
    detecciones_processes = {}  # Almacenar procesos por cámara
    # Crear un Manager para buffers compartidos
    manager = Manager()
    buffer_detecciones = manager.dict()
    while True:
        # try:
            # Establece una nueva conexión en cada iteración
            connection = connect_to_db(db_config)
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            ip_local = get_ip_local()
            # print("🌐 IP del equipo:", ip_local)  
            
            # Buscamos el proyecto en la base de datos segun la ip local
            cursor.execute(db_config["query_proyecto_por_ip"], (ip_local,))
            resultado = cursor.fetchall()
            
            if not resultado:
                print("❌ No se encontró un proyecto para la IP:", ip_local)
                return
            
            # Despues buscamos las camaras segun el proyecto de este PC
            proyectos_ids = [row["id_proyecto"] for row in resultado]
            if not proyectos_ids:
                print("❌ No se encontró ningún proyecto para la IP:", ip_local)
                return
            print("📡 Proyectos encontrados:", proyectos_ids)
            # 🔸 Obtener cámaras usando IN %s y pasando una tupla
            cursor.execute(db_config["query_yaml"], (tuple(proyectos_ids),))
            cameras = cursor.fetchall()
            cameras = [dict(fila) for fila in cameras]
            # print("📡 Datos obtenidos de la base de datos:", cameras)

            
            # Actualizar YAML si hay cambios en la base de datos
            if cameras != previous_data:
                # print("📡 Datos obtenidos de la base de datos:", cameras)
                generate_camera_yaml(cameras)  # Actualizar YAML
                # 🔸 Obtener datos para JSON también con múltiples proyectos
                cursor.execute(db_config["query_json"], (tuple(proyectos_ids),))
                data = cursor.fetchall()
                generate_json(data)
                previous_data = cameras

                # Iniciar o reiniciar procesos de detección por cámara
                for camera in cameras:
                    camera_id = camera["id_camara"]

                    # Crear buffer si no existe
                    if camera_id not in buffer_detecciones:
                        buffer_detecciones[camera_id] = manager.list()

                    config_path = f"configs/camera_{camera_id}.yaml"

                    # Si ya existe un proceso para esta cámara, no lo vuelvas a iniciar
                    if camera_id in detecciones_processes and detecciones_processes[camera_id].is_alive():
                        continue

                    print(f"🟢 Iniciando proceso de detección para cámara {camera_id}")

                    # Crear una instancia de la clase ProcesarDetecciones
                    procesador = ProcesarDetecciones(config_path, camera_id, shared_buffers, buffer_detecciones)

                    # Crear un nuevo proceso llamando al método procesar()
                    proceso = mp.Process(
                        target=procesador.procesar,  # 🔹 Llamamos al método de la clase
                        daemon=True
                    )

                    detecciones_processes[camera_id] = proceso
                    proceso.start()

                set_streamers_procesado(buffer_detecciones)

            set_processes(detecciones_processes)

            # Pausa antes de la próxima verificación
            time.sleep(5)



if __name__ == "__main__":
    # Vaciar la carpeta de videos
    if os.path.exists("Videos"):
        for elemento in os.listdir("Videos"):
            elemento_ruta = os.path.join("Videos", elemento)
            if os.path.isfile(elemento_ruta) or os.path.islink(elemento_ruta):
                os.unlink(elemento_ruta)

    # Cargar configuración desde database.yaml
    db_config = load_yaml_config("configs/database.yaml")["database"]

    host_ip = obtener_ip_local()
    set_ip_local(host_ip)
    
    # Iniciar el servidor Flask en un hilo separado
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()

    # Iniciar el streaming
    shared_buffers, threads = start_streaming_from_configs()

    
    monitor_database_and_start_detections(db_config, shared_buffers)