import os
import yaml
import threading
import cv2
from collections import deque
from src.variables_globales import get_streamers, get_threads, set_streamers, set_threads


class CameraStreamer:
    def __init__(self, camara_name, camara_url):
        self.camara_name = camara_name
        self.camara_url = camara_url
        self.frame_buffer = deque(maxlen=240)  # Buffer optimizado
        self.buffer_lock = threading.Lock()
        self.running = True

    def streaming(self):
        cap_camera = cv2.VideoCapture(self.camara_url, cv2.CAP_FFMPEG)
        cap_camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Evita delay en la captura
        cap_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap_camera.set(cv2.CAP_PROP_FPS, 30)
        cap_camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'XVID'))

        print(f"Iniciando streaming para {self.camara_name}")

        while self.running:
            ret, frame = cap_camera.read()
            if not ret:
                print(f"Error en {self.camara_name}, reconectando...")
                cap_camera.release()
                cap_camera = cv2.VideoCapture(self.camara_url)
                continue

            frame = cv2.resize(frame, (640, 480))  # Reducir resolución

            with self.buffer_lock:
                self.frame_buffer.append(frame)  # Buffer optimizado
        
        cap_camera.release()

    def stop(self):
        self.running = False


def load_yaml_config(file_path):
    """Carga el contenido de un archivo YAML."""
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


def start_streaming_from_configs():
    """Inicia el streaming de cámaras basándose en archivos YAML de una carpeta."""
    # Obtener la ruta al nivel superior (un nivel antes del script actual)
    base_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    print(base_folder)
    config_folder = os.path.join(base_folder, 'configs')

    # Verificar si la carpeta existe
    if not os.path.isdir(config_folder):
        raise FileNotFoundError(f"La carpeta 'configs' no existe en la ruta: {config_folder}")
    else:
        print(f"Carpeta de configuración encontrada: {config_folder}")
    
    # Listar todos los archivos en la carpeta configs
    yaml_files = [f for f in os.listdir(config_folder) if 'camera' in f.lower() and f.endswith('.yaml')]

    print(f"Archivos YAML encontrados: {yaml_files}")
    
    streamers = {}
    threads = {}

    for yaml_file in yaml_files:
        config_path = os.path.join(config_folder, yaml_file)
        config = load_yaml_config(config_path)
        
        # Extraer el número de la cámara del nombre del archivo (e.g., "1" de "camera_1.yaml")
        camara_number = int(yaml_file.split('_')[1].split('.')[0])  # Separa y obtiene el número
        
        camara_name = config['camera'].get('name camera', f"Camara_{camara_number}")
        rtsp_url = config['camera'].get('rtsp_url')
        
        if rtsp_url:
            streamer = CameraStreamer(camara_name, rtsp_url)
            streamers[camara_number] = streamer  # Guardar en el diccionario usando el número como clave
            set_streamers(streamers)
            
            hilo = threading.Thread(target=streamer.streaming, name=f"hilo_{camara_name}")
            threads[camara_number] = hilo  # Guardar el hilo en el diccionario
            hilo.start()
        else:
            print(f"No se encontró 'rtsp_url' en {yaml_file}")

    return streamers, threads


# Punto de entrada si se ejecuta como script
if __name__ == "__main__":
    streamers, threads = start_streaming_from_configs()

    try:
        for hilo in threads.values():
            hilo.join()
    except KeyboardInterrupt:
        print("Deteniendo streaming...")
        for streamer in streamers.values():
            streamer.stop()
