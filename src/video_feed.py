from flask import Flask, Response
from ultralytics import YOLO
import time
import datetime
import cv2
import os
import json
import threading
from src.load_config import load_yaml_config
import socket
from src.db_utils import connect_to_db, close_connection
from src.variables_globales import get_streamers
from src.Tipo_notificacion import save_video_from_buffer
from src.model_loader import model, LABELS
 
app = Flask(__name__)
 
# Colores para las etiquetas
COLORS = {
    "A_Person": (255, 0, 0),  # Azul
    "Harness": (0, 255, 0),   # Verde
    "No_Helmet": (0, 0, 255), # Rojo
    "White": (120, 120, 120),   # Gris
    "YellowGreen": (150, 50, 255) # Morado
}
 
detecciones_obtenidas = None
tiempo_deteccion_por_area = {}
 
def generate_frames(config_path, camera_id, retry_interval=5):
    global detecciones_obtenidas
    global tiempo_deteccion_por_area
 
    target_width, target_height = 640, 380  # Resolución deseada
 
    while True:
        try:
            config = load_yaml_config(config_path)
            rtsp_url = config["camera"]["rtsp_url"]
            areas = config["camera"]["coordinates"]
            tiempos_limite = {key: float(value) for key, value in json.loads(config["camera"]["time_areas"]).items()}
        except Exception as e:
            print(f"Error al cargar la configuración: {e}")
            time.sleep(retry_interval)
            continue
 
        # Capturar frame desde el buffer de streamers
        streamers = get_streamers()
        info_buffer = streamers[camera_id]
        frame_to_process = None
 
        with info_buffer.buffer_lock:
            if info_buffer.frame_buffer:
                frame_to_process = info_buffer.frame_buffer.pop(0)
 
        if frame_to_process is not None:
            frame = cv2.resize(frame_to_process, (target_width, target_height))
 
            width2 = 294.1226453481414
            height2 = 145.45830319313836
            width1 = 640
            height1 = 380
 
            detecciones_obtenidas = False
 
            # Procesar cada área
            for area_name, area_config in areas.items():
                try:
                    area_x = float(area_config["x"])
                    area_y = float(area_config["y"])
                    area_width = float(area_config["width"])
                    area_height = float(area_config["height"])
 
                    x1 = (area_x / width2) * width1
                    y1 = (area_y / height2) * height1
                    rect_width1 = (area_width / width2) * width1
                    rect_height1 = (area_height / height2) * height1
 
                    start_point = (int(x1), int(y1))
                    end_point = (int(x1 + rect_width1), int(y1 + rect_height1))
 
                    # Dibujar la caja azul
                    cv2.rectangle(frame, start_point, end_point, (255, 0, 0), 2)
 
                    # Procesar el frame con el modelo
                    results = model(frame, verbose=False)
 
                    for detection in results[0].boxes:
                        try:
                            x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                            probability = detection.conf[0] * 100
                            class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                            label = LABELS.get(class_index, "Unknown")
 
                            # Verificar si la detección está dentro del área actual
                            if (start_point[0] <= x1_det <= end_point[0] and
                                start_point[1] <= y1_det <= end_point[1]):
                                min_probability = float(area_config[label])
 
                                if probability >= min_probability:
                                    color = COLORS.get(label, (255, 255, 255))
                                    text = f"{label}: {probability:.2f}%"
                                    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                                    text_offset_x, text_offset_y = x1_det, y1_det - 10
                                    box_coords = ((text_offset_x, text_offset_y - text_height - 5),
                                                  (text_offset_x + text_width + 5, text_offset_y + 5))
 
                                    cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)
                                    cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                    cv2.putText(frame, text, (text_offset_x, text_offset_y),
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
 
                                    now = time.time()
                                    if (area_name, label) not in tiempo_deteccion_por_area:
                                        tiempo_deteccion_por_area[(area_name, label)] = now
                                    else:
                                        tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]
                                        if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                            print(f"{label} detectada en {area_name} durante {tiempos_limite[area_name]} segundos.")
                                            save_video_from_buffer(info_buffer.frame_buffer, f"{area_name}_{label}.mp4", 20)
                                            tiempo_deteccion_por_area[(area_name, label)] = time.time()
 
                        except Exception as detection_error:
                            print(f"Error al procesar una detección en {area_name}: {detection_error}")
 
                except Exception as area_error:
                    print(f"Error al procesar {area_name}: {area_error}")
 
            # Codificar el frame como JPEG y enviarlo
            try:
                _, buffer = cv2.imencode(".jpg", frame)
                frame_bytes = buffer.tobytes()
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            except Exception as encoding_error:
                print(f"Error al codificar el frame: {encoding_error}")
 
@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    try:
        config_path = os.path.join("configs", f"camera_{camera_id}.yaml")
        if not os.path.exists(config_path):
            return f"No se encontró el archivo YAML para la cámara {camera_id}.", 404
 
        host_ip = socket.gethostbyname(socket.gethostname())
        feed_url = f"http://{host_ip}:5000/video_feed/{camera_id}"
        save_feed_url_to_database(camera_id, feed_url)
 
        return Response(generate_frames(config_path, camera_id), mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        print(f"Error en video_feed: {e}")
        return f"Error al procesar la solicitud de la cámara {camera_id}.", 500
 
def save_feed_url_to_database(camera_id, url):
    connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
    cursor = connection.cursor()
 
    try:
        update_query = """
            UPDATE IP_Videofeed2
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
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
 