from flask import Flask, Response
from ultralytics import YOLO
import time
from datetime import time as dtime
import datetime
import cv2
import os
import time
from src.load_config import load_yaml_config
import socket
from src.db_utils import connect_to_db, close_connection


app = Flask(__name__)

# Ruta al modelo fijo
MODEL_PATH = os.path.join("models", "juanmodelo.pt")

# Verifica si el modelo existe
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"No se encontró el modelo en la ruta especificada: {MODEL_PATH}")

# Cargar el modelo una sola vez
model = YOLO(MODEL_PATH)

# Obtener nombres de las etiquetas desde el modelo
LABELS = model.model.names  # Diccionario de etiquetas, e.g., {0: 'A_Person', 1: 'Harness', ...}

# Colores para las etiquetas
COLORS = {
    "A_Person": (255, 0, 0),  # Azul
    "Harness": (0, 255, 0),   # Verde
    "No_Helmet": (0, 0, 255), # Rojo
    "White": (120, 120, 120),   # Gris
    "YellowGreen": (150, 50, 255) # Morado
}

detectiones_obtenidas = None
detecciones_obtenidas_actual = False
tiempo_deteccion_acumulado = 0
tiempo_no_deteccion_acumulado = 0
hora_primera_deteccion_segundos_almacenado = 0
hora_sin_detecciones_segundos = 0
deteccion_confirmada = False


tiempos_limite = {
    "area1": 4,  # Tiempo límite para área 1
    "area2": 3,  # Tiempo límite para área 2
    "area3": 10  # Tiempo límite para área 3
}

tiempo_deteccion_por_area = {}

def generate_frames(config_path, retry_interval=5):
    global detecciones_obtenidas, detecciones_obtenidas_actual, deteccion_confirmada
    global ahora1, ahora2
    global tiempo_deteccion_acumulado, tiempo_no_deteccion_acumulado
    global hora_primera_deteccion_segundos, hora_sin_detecciones_segundos
    global hora_primera_deteccion_segundos_almacenado
    """
    Genera frames desde un RTSP utilizando YOLO para inferencias.
    Dibuja cajas y procesa detecciones para area1, area2 y area3,
    utilizando las probabilidades y etiquetas específicas de cada área.
    """
    target_width, target_height = 640, 380  # Resolución deseada

    def obtener_segundos_actuales():
        ahora = datetime.datetime.now()
        return ahora.hour * 3600 + ahora.minute * 60 + ahora.second
    
    tiempo_actual_segundos = obtener_segundos_actuales()

 

    while True:
        try:
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
                except KeyError as key_error:
                    print(f"Clave faltante en el archivo YAML: {key_error}")
                    time.sleep(retry_interval)
                    continue

                # Manejo del flujo RTSP
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(rtsp_url)
                    if not cap.isOpened():
                        print(f"No se pudo abrir el video feed: {rtsp_url}. Reintentando en {retry_interval} segundos...")
                        time.sleep(retry_interval)
                        continue

                ret, frame = cap.read()
                if not ret:
                    print(f"Error al leer el flujo de video: {rtsp_url}. Reiniciando conexión...")
                    cap.release()
                    cap = None
                    break

                # Redimensionar el frame a la resolución deseada
                frame = cv2.resize(frame, (target_width, target_height))

                # Dimensiones originales de las imágenes
                width2 = 294.1226453481414
                height2 = 145.45830319313836
                width1 = 640
                height1 = 380

                detecciones_obtenidas = False

                # Procesar cada área: area1, area2, area3
                for area_name, area_config in areas.items():
                    try:
                        # Obtener las coordenadas y dimensiones del área actual
                        area_x = float(area_config["x"])
                        area_y = float(area_config["y"])
                        area_width = float(area_config["width"])
                        area_height = float(area_config["height"])

                        # Escalar las coordenadas a la resolución objetivo
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

                        time_in_area = 0

                        # print("areas", area_name)


                        for detection in results[0].boxes:
                            try:
                                # Obtener coordenadas, probabilidad y etiqueta de la detección
                                x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                                probability = detection.conf[0] * 100
                                class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                                label = LABELS.get(class_index, "Unknown")


                                # Verificar si la etiqueta está permitida en el área actual
                                if label in area_config:
                                    min_probability = float(area_config[label])
                                    if probability >= min_probability:
                                        if start_point[0] <= x1_det <= end_point[0] and start_point[1] <= y1_det <= end_point[1]:
                                            now = time.time()

                                            # Inicializar tiempo si no existe
                                            if (area_name, label) not in tiempo_deteccion_por_area:
                                                tiempo_deteccion_por_area[(area_name, label)] = now

                                            tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]

                                            # Usar tiempo límite específico para el área
                                            if tiempo_acumulado >= tiempos_limite.get(area_name, 5):  # Default 5s si no está definido
                                                print(f"{label} detectada en {area_name} por {tiempos_limite[area_name]} segundos.")
                                                # Reiniciar contador
                                                tiempo_deteccion_por_area[(area_name, label)] = time.time()
                                        else:
                                            # Resetear el tiempo si sale del área
                                            tiempo_deteccion_por_area.pop((area_name, label), None)

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
        except Exception as e:
            print(f"Error en generate_frames: {e}. Reintentando en {retry_interval} segundos...")
            time.sleep(retry_interval)
        finally:
            if cap:
                cap.release()





def save_feed_url_to_database(camera_id, url):
    """
    Guarda la URL del video feed en la columna URL_CAMARA_SERVER de la base de datos.
    """
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

        return Response(generate_frames(config_path), mimetype="multipart/x-mixed-replace; boundary=frame")
    except Exception as e:
        print(f"Error en video_feed: {e}")
        return f"Error al procesar la solicitud de la cámara {camera_id}.", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)





