from flask import Flask, Response
from ultralytics import YOLO
import time
from datetime import time as dtime
import datetime
from datetime import datetime
import cv2
import os
import time
from src.load_config import load_yaml_config
import socket
from src.db_utils import connect_to_db, close_connection
import json
import threading
from src.variables_globales import get_streamers, set_streamers, set_id
from src.Tipo_notificacion import save_video_from_buffer
import numpy as np
from src.model_loader import model, LABELS

app = Flask(__name__)

# Colores para las etiquetas    El color significa que es una alerta si la llega a detectar
COLORS = {
    "A_Person": (255, 0, 0),  # Azul
    "Green": (0, 0, 255),   # Rojo
    "Harness": (0, 255, 206),   # Verde
    "No_Harness": (0, 0, 255),   # Rojo
    "No_Helmet": (0, 0, 255), # Rojo
    "White": (120, 120, 120),   # Gris
    "Yellow": (0, 255, 255), # Rojo
    "Loading_Machine": (0, 100, 19), # Verde Bosque Oscuro
    "Mud_Bucket": (255, 171, 171), # Rosa Suave
    "Orange": (0, 128, 255), # Naranja
    
}

detectiones_obtenidas = None
detecciones_obtenidas_actual = False
tiempo_deteccion_acumulado = 0

deteccion_confirmada = False
tiempos_limite = {}
NombreLabel = ""
descripcionPersona = ""
descripcionSinCasco = ""
id_registro = 0


tiempo_deteccion_por_area = {}


def generate_frames(config_path, camera_id, retry_interval=5):
    global detecciones_obtenidas
    global tiempo_deteccion_acumulado
   
   
    """
    Genera frames desde un RTSP utilizando YOLO para inferencias.
    Dibuja cajas y procesa detecciones para area1, area2 y area3,
    utilizando las probabilidades y etiquetas específicas de cada área.
    """
    target_width, target_height = 640, 380  # Resolución deseada


    while True:
            cap = None
            while True:
                # Recargar la configuración del YAML en cada iteración
                try:
                    config = load_yaml_config(config_path)
                    # print(f"Configuración cargada desde {config_path}: {config}")  # Debug
                    rtsp_url = config["camera"]["rtsp_url"]
                    
                except Exception as yaml_error:
                    print(f"Error al cargar el archivo YAML: {yaml_error}")
                    time.sleep(retry_interval)
                    continue

                # Validar que existan las claves necesarias
                try:
                    rtsp_url = config["camera"]["rtsp_url"]
                    areas = config["camera"]["coordinates"]
                    
                    # print("Areas: ", areas)
                    


                except KeyError as key_error:
                    print(f"Clave faltante en el archivo YAML: {key_error}")
                    time.sleep(retry_interval)
                    continue
    
                frame_to_process = None
                streamers = get_streamers()
                
                info_buffer = streamers[camera_id]
                # print("Buffer: ", len(frame_buffer))
                with info_buffer.buffer_lock:
                    if info_buffer.frame_buffer:
                        # Si hay suficientes frames en el buffer, tomar el más reciente
                        if len(info_buffer.frame_buffer) > 150:
                            frame_to_process = info_buffer.frame_buffer.popleft()  # Toma el frame más antiguo eficientemente
                        # else:
                        #     frame_to_process = info_buffer.frame_buffer[-1]  # Toma el último frame sin eliminarlo


                # print("Frame procesado: ",frame_to_process)
                if frame_to_process is not None:
                    
                    frame = cv2.resize(frame_to_process, (target_width, target_height))

                    # Dimensiones originales de las imágenes
                    width2 = 294.1226453481414
                    height2 = 145.45830319313836
                    width1 = 640
                    height1 = 380

                    
                    for area_name, area_config in areas.items():
                        try:
                            # Escalar los puntos del polígono
                            original_points = area_config["points"]
                            scaled_points = [
                                {
                                    "x": (point["x"] / width2) * width1,
                                    "y": (point["y"] / height2) * height1
                                }
                                for point in original_points
                            ]

                            # Convertir puntos escalados al formato requerido por OpenCV
                            pts = np.array(
                                [[int(point["x"]), int(point["y"])] for point in scaled_points],
                                dtype=np.int32
                            ).reshape((-1, 1, 2))

                            # Dibujar el polígono escalado en el frame
                            cv2.polylines(frame, [pts], isClosed=True, color=(255, 0, 0), thickness=2)

                            # Procesar el frame con el modelo
                            results = model(frame, verbose=False)

                            for detection in results[0].boxes:
                                try:
                                    # Obtener coordenadas, probabilidad y etiqueta de la detección
                                    x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                                    point = (x1_det, y1_det)
                                    probability = detection.conf[0] * 100
                                    class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                                    label = LABELS.get(class_index, "Unknown")
                                    print("label: ", label, "Probabilidad: ", probability)
                                    print("Area: ", area_config)
                                    # Verificar si la etiqueta está permitida en el área actual
                                    if label in area_config:
                                        min_probability = float(area_config[label])
                                        # Usar cv2.pointPolygonTest para verificar si el punto está dentro del polígono
                                        inside = cv2.pointPolygonTest(pts, point, False)

                                        # Verificar si la detección está dentro de la caja actual y cumple la probabilidad
                                        if inside >= 0 :

                                            if probability >= min_probability:
                                                # Dibujar la detección
                                                color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta

                                                # Agregar el texto de la etiqueta
                                                text = f"{label}: {probability:.0f}%"
                                                (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                                                text_offset_x, text_offset_y = x1_det, y1_det - 10
                                                box_coords = ((text_offset_x, text_offset_y - text_height - 5), 
                                                            (text_offset_x + text_width + 25, text_offset_y + 5))

                                                
                                                # Condicional para pintar del label  
                                                if label in config["camera"]["label"]:
                                                    cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)
                                                    cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                                    cv2.putText(frame, text, (text_offset_x, text_offset_y), 
                                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                                            

                                except Exception as detection_error:
                                    print(f"Error al procesar una detección en {area_name}: {detection_error}")

                        except Exception as area_error:
                            print(f"Error al procesar {area_name}: {area_error}")
                            continue

                    # Codificar el frame como JPEG
                    try:
                        _, buffer = cv2.imencode(".jpg", frame)
                        frame_bytes = buffer.tobytes()
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                    except Exception as encoding_error:
                        print(f"Error al codificar el frame: {encoding_error}")




def save_feed_url_to_database(camera_id, url):
    """
    Guarda la URL del video feed en la columna URL_CAMARA_SERVER de la base de datos.
    """
    connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
    cursor = connection.cursor()

    try:
        update_query = """
            UPDATE IP_Videofeed3
            SET URL_CAMARA_SERVER = %s
            WHERE ID = %s
        """
        cursor.execute(update_query, (url, camera_id))
        connection.commit()
        print(f"URL {url} guardada correctamente para la cámara {camera_id}")
    except Exception as e:
        print(f"Error al guardar la URL en la base de datos: {e}")
    finally:
        cursor.close()
        close_connection(connection)



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

        # Guardar la URL en la base de datos
        save_feed_url_to_database(camera_id, feed_url)

        return Response(generate_frames(config_path, camera_id), mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        print(f"Error en video_feed: {e}")
        return f"Error al procesar la solicitud de la cámara {camera_id}.", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)