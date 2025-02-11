from flask import Flask, Response
from ultralytics import YOLO
import time
import cv2
import os
import socket
import numpy as np
from src.load_config import load_yaml_config
from src.db_utils import connect_to_db, close_connection
from src.variables_globales import get_streamers
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

import time
import cv2
import numpy as np
from collections import deque
from src.load_config import load_yaml_config
from src.variables_globales import get_streamers
from src.model_loader import model, LABELS

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
        streamers = get_streamers()
        
        # print(streamers)
        frame_buffer = streamers.get(camera_id, None)  # Usa deque con tamaño máximo

        if not frame_buffer:
            # print(f"⚠️ Buffer vacío para la cámara {camera_id}, esperando frames...")
            time.sleep(0.05)
            continue

        # Obtener el último frame disponible de manera segura
        try:
            frame_to_process = frame_buffer.pop(0)
        except IndexError:
            print(f"⚠️ Error: Intento de acceder a un frame inexistente en {camera_id}")
            time.sleep(0.05)
            continue

        # Redimensionar el frame
        frame = cv2.resize(frame_to_process, (target_width, target_height))

        # Dimensiones originales del RTSP
        width2, height2 = 294.12, 145.45  # Valores base
        width1, height1 = 640, 380  # Valores de la ventana de visualización

        # Procesar detecciones en las áreas definidas en el YAML
        for area_name, area_config in areas.items():
            try:
                original_points = area_config["points"]
                scaled_points = [
                    {"x": (p["x"] / width2) * width1, "y": (p["y"] / height2) * height1}
                    for p in original_points
                ]
                pts = np.array([[int(p["x"]), int(p["y"])] for p in scaled_points], dtype=np.int32).reshape((-1, 1, 2))
                
                # Dibujar el polígono escalado en el frame
                        # Definir el color según el área
                if area_name == "area3":
                    polygon_color = (0, 255, 0)  # Verde para area2
                elif area_name == "area2":
                    polygon_color = (0, 0, 255)
                else:
                    polygon_color = (255, 0, 0)  # Rojo o azul para otras áreas (según lo desees)
                
                # Dibujar el polígono escalado en el frame con el color definido
                cv2.polylines(frame, [pts], isClosed=True, color=polygon_color, thickness=2)

                results = model(frame, verbose=False)

                for detection in results[0].boxes:
                    try:
                        x1, y1, x2, y2 = map(int, detection.xyxy[0])
                        
                        point = (x1, y1)
                        point2 = (int((x1 + x2) / 2), y2)
                        probability = detection.conf[0] * 100
                        class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                        label = LABELS.get(class_index, "Unknown")

                        if label in area_config:
                            min_probability = float(area_config[label])
                            inside = cv2.pointPolygonTest(pts, point, False)

                            if inside >= 0:
                                if probability >= min_probability:
                                    color = COLORS.get(label, (255, 255, 255))
                                    text = f"{label}: {probability:.0f}%"
                                    (text_width, text_height), _ = cv2.getTextSize(
                                        text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
                                    )
                                    text_offset_x, text_offset_y = x1, y1 - 10
                                    box_coords = (
                                        (text_offset_x, text_offset_y - text_height - 5),
                                        (text_offset_x + text_width + 25, text_offset_y + 5)
                                    )
 
                                    # Dibujar la detección en el frame
                                    if label in config["camera"]["label"]:
                                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
                                        cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                        cv2.putText(frame, text, (text_offset_x, text_offset_y),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                                                # **Verificar específicamente para "area2" si point2 está dentro del polígono**
                            if area_name == "area3":
                                inside_point2 = cv2.pointPolygonTest(pts, point2, False)
                                if inside_point2 >= 0:
                                    print("point2 se encuentra dentro del polígono de area3")
                                    # Por ejemplo, dibujar un círculo en point2
                                    cv2.circle(frame, point2, radius=5, color=(0, 0, 255), thickness=1)
                    except Exception as detection_error:
                        print(f"⚠️ Error al procesar detección en {area_name}: {detection_error}")

            except Exception as area_error:
                print(f"⚠️ Error al procesar {area_name}: {area_error}")
                continue

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
        feed_url = f"http://{host_ip}:5000/video_feed/{camera_id}"
        print(feed_url)

        return Response(generate_frames(config_path, camera_id), mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        print(f"Error en video_feed: {e}")
        return f"Error al procesar la solicitud de la cámara {camera_id}.", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
