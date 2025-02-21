import os
import yaml
import cv2
import time
import multiprocessing as mp
from multiprocessing import Manager
from collections import deque
from src.variables_globales import get_streamers, set_streamers, get_processes, set_processes

class CameraStreamer:
    def __init__(self, camara_name, camara_url, shared_buffers, camara_number):

        self.camara_name = camara_name
        self.camara_url = camara_url
        self.shared_buffers = shared_buffers
        self.camara_number = camara_number
        self.running = True

    def streaming(self):
        cap_camera = cv2.VideoCapture(self.camara_url)
        cap_camera.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        cap_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap_camera.set(cv2.CAP_PROP_FPS, 15)
        cap_camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'XVID'))

        print(f"📡 Iniciando streaming para {self.camara_name}")

        while self.running:
            ret, frame = cap_camera.read()
            if not ret:
                print(f"⚠️ Error en {self.camara_name}, reconectando...")
                cap_camera.release()
                cap_camera = cv2.VideoCapture(self.camara_url)
                continue

            frame = cv2.resize(frame, (640, 480))

            # Acceder al buffer compartido
            buffer = self.shared_buffers[self.camara_number]

            # Agregar frame al buffer compartido
            if len(buffer) >= 120:
                buffer.pop(0)  # Eliminar el frame más antiguo si ya está lleno
            buffer.append(frame)
            # print("Buffer: ", len(buffer))
            time.sleep(0.005)

        cap_camera.release()
        print(f"📡 Streaming detenido para {self.camara_name}")

    def stop(self):
        self.running = False

def load_yaml_config(file_path):
    """Carga el contenido de un archivo YAML."""
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def start_camera_stream(camara_name, camara_url, shared_buffers, camara_number):
    """
    Función auxiliar para iniciar el streaming de una cámara en un nuevo proceso.
    """
    streamer = CameraStreamer(camara_name, camara_url, shared_buffers, camara_number)
    streamer.streaming()

def start_streaming_from_configs():
    """Inicia el streaming de cámaras y usa `multiprocessing.Manager()` para compartir buffers."""
    base_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_folder = os.path.join(base_folder, 'configs')

    if not os.path.isdir(config_folder):
        raise FileNotFoundError(f"La carpeta 'configs' no existe en la ruta: {config_folder}")

    yaml_files = [f for f in os.listdir(config_folder) if 'camera' in f.lower() and f.endswith('.yaml')]
    print(f"📄 Archivos YAML encontrados: {yaml_files}")

    manager = Manager()
    shared_buffers = manager.dict()  # 🔹 Diccionario compartido entre procesos
    processes = {}

    for yaml_file in yaml_files:
        config_path = os.path.join(config_folder, yaml_file)
        config = load_yaml_config(config_path)

        try:
            camara_number = int(yaml_file.split('_')[1].split('.')[0])
        except (IndexError, ValueError):
            print(f"⚠️ No se pudo extraer el número de cámara de {yaml_file}")
            continue

        camara_name = config['camera'].get('name camera', f"Camara_{camara_number}")
        rtsp_url = config['camera'].get('rtsp_url')

        if rtsp_url:
            shared_buffers[camara_number] = manager.list()  # 🔹 Crear buffer compartido

            proceso = mp.Process(
                target=start_camera_stream,
                args=(camara_name, rtsp_url, shared_buffers, camara_number)
            )
            processes[camara_number] = proceso
            proceso.start()
        else:
            print(f"⚠️ No se encontró `rtsp_url` en {yaml_file}")

    set_streamers(shared_buffers)  # 🔹 Guardar en `variables_globales.py`
    set_processes(processes)

    print(f"✅ Buffers inicializados correctamente: {list(shared_buffers.keys())}")
    return shared_buffers, processes
