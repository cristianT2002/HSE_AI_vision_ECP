from flask import Flask, Response
from ultralytics import YOLO
import time
import cv2
import os
import socket
import numpy as np
from src.load_config import load_yaml_config
from src.db_utils import connect_to_db, close_connection
from src.variables_globales import get_streamers, get_streamers_procesado
from src.model_loader import model, LABELS
from collections import deque

app = Flask(__name__)

# Colores para las etiquetas
COLORS = {
    "A_Person": (255, 0, 0),  # Azul
    "Green": (0, 0, 255),  # Rojo
    "Harness": (0, 255, 206),  # Verde
    "No_Harness": (0, 0, 255),  # Rojo
    "No_Helmet": (0, 0, 255),  # Rojo
    "White": (120, 120, 120),  # Gris
    "Yellow": (0, 255, 255),  # Amarillo
    "Loading_Machine": (0, 100, 19),  # Verde Oscuro
    "Mud_Bucket": (255, 171, 171),  # Rosa Suave
    "Orange": (0, 128, 255),  # Naranja
}



def generate_frames(config_path, camera_id, retry_interval=5):
    """
    Genera frames desde un RTSP utilizando YOLO para inferencias y los transmite.
    """
    target_width, target_height = 640, 380  # Resolución deseada para el stream

    while True:
        try:
            # Cargar la configuración desde el archivo YAML
            config = load_yaml_config(config_path)
            rtsp_url = config["camera"]["rtsp_url"]
            areas = config["camera"]["coordinates"]
        except Exception as yaml_error:
            print(f"⚠️ Error al cargar el archivo YAML: {yaml_error}")
            time.sleep(retry_interval)
            continue

        # Obtener el buffer de frames de la cámara
        streamers = get_streamers_procesado()
        
        # print(streamers)
        # Traemos el buffer
        frame_buffer = streamers.get(camera_id, None)  # Usa deque con tamaño máximo

        if not frame_buffer:
            # print(f"⚠️ Buffer vacío para la cámara {camera_id}, esperando frames...")
            time.sleep(0.05)
            continue

        # Obtener el último frame disponible de manera segura
        try:
            frame_to_process =frame_buffer[0]
        except IndexError:
            print(f"⚠️ Error: Intento de acceder a un frame inexistente en video_feed {camera_id}")
            time.sleep(0.05)
            continue

        # Redimensionar el frame
        frame = cv2.resize(frame_to_process, (target_width, target_height))


        # Codificar el frame como JPEG y enviarlo
        try:
            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        except Exception as encoding_error:
            print(f"⚠️ Error al codificar el frame: {encoding_error}")


@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    """
    Endpoint para acceder al video feed de una cámara específica.
    """
    try:
        config_path = os.path.join("configs", f"camera_{camera_id}.yaml")

        if not os.path.exists(config_path):
            return f"No se encontró el archivo YAML para la cámara {camera_id}.", 404

        # Obtener la IP del host
        host_ip = socket.gethostbyname(socket.gethostname())
        
        ################ Ip servidor #################### 
        # host_ip = "172.30.37.63"
        
        feed_url = f"http://{host_ip}:5000/video_feed/{camera_id}"
        print(feed_url)

        return Response(generate_frames(config_path, camera_id), mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        print(f"Error en video_feed: {e}")
        return f"Error al procesar la solicitud de la cámara {camera_id}.", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
