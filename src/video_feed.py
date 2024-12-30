from flask import Flask, Response
from ultralytics import YOLO
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

def generate_frames(config_path, retry_interval=5):
    """
    Genera frames desde un RTSP utilizando YOLO para inferencias.
    Filtra las detecciones dinámicamente basándose en el YAML.
    """
    while True:
        try:
            cap = None
            while True:
                # Recargar la configuración del YAML en cada iteración
                config = load_yaml_config(config_path)
                print(config)
                rtsp_url = config["camera"]["rtsp_url"]
                min_probability = float(config["camera"].get("probability", 50))
                labels_to_detect = [label.strip() for label in config["camera"].get("label", "").split(",")]

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

                # Procesar el frame con el modelo cargado globalmente
                results = model(frame)

                for detection in results[0].boxes:
                    # Obtener coordenadas, probabilidad y etiqueta de la detección
                    x1, y1, x2, y2 = map(int, detection.xyxy[0])
                    probability = detection.conf[0] * 100
                    class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                    label = LABELS.get(class_index, "Unknown")

                    # Filtrar detecciones basadas en los labels del YAML y la probabilidad
                    if label in labels_to_detect and probability >= min_probability:
                        color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta, blanco si no existe

                        # Dibujar el rectángulo de la detección
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                        # Agregar un fondo para el texto
                        text = f"{label}: {probability:.2f}%"
                        (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                        text_offset_x, text_offset_y = x1, y1 - 10
                        box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 5, text_offset_y + 5))
                        cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)

                        # Agregar el texto encima del fondo
                        cv2.putText(frame, text, (text_offset_x, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

                # Codificar el frame como JPEG
                _, buffer = cv2.imencode(".jpg", frame)
                frame_bytes = buffer.tobytes()

                # Yield del frame para streaming
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
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
            UPDATE IP_Videofeed
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

