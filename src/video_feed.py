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
    Dibuja cajas para cada área definida en el YAML y realiza inferencias dentro de ellas.
    """
    target_width, target_height = 640, 380  # Resolución deseada

    while True:
        try:
            cap = None
            while True:
                # Recargar la configuración del YAML en cada iteración
                try:
                    config = load_yaml_config(config_path)
                    print(f"Configuración cargada desde {config_path}: {config}")  # Debug
                    rtsp_url = config["camera"]["rtsp_url"]
                except Exception as yaml_error:
                    print(f"Error al cargar el archivo YAML: {yaml_error}")
                    time.sleep(retry_interval)
                    continue

                # Validar que existan las claves necesarias
                try:
                    rtsp_url = config["camera"]["rtsp_url"]
                    
                    # Etiquetas a pintar definidas en 'label'
                    labels_to_draw = [label.strip() for label in config["camera"].get("label", "").split(",")]

                    # Obtener todas las áreas
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

                # Dibujar las cajas y realizar inferencias para cada área
                for area_name, area_config in areas.items():
                    try:
                        # Obtener las coordenadas de la caja
                        area_x = float(area_config["x"])
                        area_y = float(area_config["y"])
                        area_width = float(area_config["width"])
                        area_height = float(area_config["height"])
                        
                        # Dimensiones originales y escaladas
                        width2 = 294.1226453481414
                        height2 = 145.45830319313836
                        width1 = 640
                        height1 = 380

                        # Escalar coordenadas a la resolución objetivo
                        x1 = (area_x / width2) * width1
                        y1 = (area_y / height2) * height1
                        rect_width1 = (area_width / width2) * width1
                        rect_height1 = (area_height / height2) * height1

                        start_point = (int(x1), int(y1))
                        end_point = (int(x1 + rect_width1), int(y1 + rect_height1))

                        # Dibujar la caja azul para cada área
                        cv2.rectangle(frame, start_point, end_point, (255, 0, 0), 2)
                    except KeyError as e:
                        print(f"Error al procesar las coordenadas de {area_name}: {e}")
                        continue

                    # Procesar el frame con el modelo cargado globalmente
                    try:
                        results = model(frame)
                    except Exception as model_error:
                        print(f"Error al procesar el frame con el modelo: {model_error}")
                        time.sleep(retry_interval)
                        continue

                    # Filtrar y dibujar detecciones dentro de la caja actual
                    for detection in results[0].boxes:
                        try:
                            # Obtener coordenadas, probabilidad y etiqueta de la detección
                            x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                            probability = detection.conf[0] * 100
                            class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                            label = LABELS.get(class_index, "Unknown")

                            # Verificar si la detección está dentro de la caja actual
                            if start_point[0] <= x1_det <= end_point[0] and start_point[1] <= y1_det <= end_point[1]:
                                if label in labels_to_draw:
                                    # Dibujar la detección
                                    color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta
                                    cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)

                                    # Agregar el texto de la etiqueta
                                    text = f"{label}: {probability:.2f}%"
                                    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                                    text_offset_x, text_offset_y = x1_det, y1_det - 10
                                    box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 5, text_offset_y + 5))
                                    cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                    cv2.putText(frame, text, (text_offset_x, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                        except Exception as detection_error:
                            print(f"Error al procesar una detección: {detection_error}")

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



# def generate_frames(config_path, retry_interval=5):
#     """
#     Genera frames desde un RTSP utilizando YOLO para inferencias.
#     Filtra las detecciones dinámicamente basándose en las etiquetas definidas en 'camera.label'
#     y las probabilidades específicas de 'coordinates -> area1'. Además, dibuja una caja azul 
#     utilizando las coordenadas definidas en el archivo YAML, y realiza inferencias solo dentro de esa caja.
#     """
#     target_width, target_height = 640, 380  # Resolución deseada

#     while True:
#         try:
#             cap = None
#             while True:
#                 # Recargar la configuración del YAML en cada iteración
#                 try:
#                     config = load_yaml_config(config_path)
#                     print(f"Configuración cargada desde {config_path}: {config}")  # Debug
#                     rtsp_url = config["camera"]["rtsp_url"]
#                 except Exception as yaml_error:
#                     print(f"Error al cargar el archivo YAML: {yaml_error}")
#                     time.sleep(retry_interval)
#                     continue

#                 # Validar que existan las claves necesarias
#                 try:
#                     rtsp_url = config["camera"]["rtsp_url"]
                    
#                     # Etiquetas a pintar definidas en 'label'
#                     labels_to_draw = [label.strip() for label in config["camera"].get("label", "").split(",")]

#                     # Probabilidades específicas de 'coordinates -> area1'
#                     area_config = config["camera"]["coordinates"]["area1"]
#                     label_probabilities = {
#                         key: float(value) for key, value in area_config.items()
#                         if key not in ["camara", "punto"]  # Ignorar claves irrelevantes
#                     }
                    
#                     # Dimensiones de las imágenes
#                     width2 = 294.1226453481414
#                     height2 = 145.45830319313836
#                     width1 = 640
#                     height1 = 380

#                     # Obtener las coordenadas de la caja azul
#                     area_x = int(area_config["x"])
#                     area_y = int(area_config["y"])
#                     area_width = int(area_config["width"])
#                     area_height = int(area_config["height"])
                    
#                     x2 = area_x  # Ejemplo de coordenada x en imagen2
#                     y2 = area_y   # Ejemplo de coordenada y en imagen2
                    
#                     rect_width2 = area_width
#                     rect_height2 = area_height
                    
#                     # Escalar coordenadas a imagen1
#                     x1 = (x2 / width2) * width1
#                     y1 = (y2 / height2) * height1

#                     # Escalar dimensiones del rectángulo a imagen1
#                     rect_width1 = (rect_width2 / width2) * width1
#                     rect_height1 = (rect_height2 / height2) * height1
                    
#                     start_point = (int(x1), int(y1))
#                     end_point = (int(x1 + rect_width1), int(y1 + rect_height1))
                    
                    
#                 except KeyError as key_error:
#                     print(f"Clave faltante en el archivo YAML: {key_error}")
#                     time.sleep(retry_interval)
#                     continue
#                 except ValueError as value_error:
#                     print(f"Error en el formato de las probabilidades o coordenadas: {value_error}")
#                     time.sleep(retry_interval)
#                     continue

#                 # Manejo del flujo RTSP
#                 if cap is None or not cap.isOpened():
#                     cap = cv2.VideoCapture(rtsp_url)
#                     if not cap.isOpened():
#                         print(f"No se pudo abrir el video feed: {rtsp_url}. Reintentando en {retry_interval} segundos...")
#                         time.sleep(retry_interval)
#                         continue

#                 ret, frame = cap.read()
#                 if not ret:
#                     print(f"Error al leer el flujo de video: {rtsp_url}. Reiniciando conexión...")
#                     cap.release()
#                     cap = None
#                     break

#                 # Redimensionar el frame a la resolución deseada
#                 frame = cv2.resize(frame, (target_width, target_height))

#                 # Dibujar la caja azul en el frame
#                 cv2.rectangle(frame, start_point, end_point, (255, 0, 0), 2)

#                 # Procesar el frame con el modelo cargado globalmente
#                 try:
#                     results = model(frame)
#                 except Exception as model_error:
#                     print(f"Error al procesar el frame con el modelo: {model_error}")
#                     time.sleep(retry_interval)
#                     continue

#                 for detection in results[0].boxes:
#                     try:
#                         # Obtener coordenadas, probabilidad y etiqueta de la detección
#                         x1, y1, x2, y2 = map(int, detection.xyxy[0])
#                         probability = detection.conf[0] * 100
#                         class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
#                         label = LABELS.get(class_index, "Unknown")

#                         # Verificar si la detección está dentro de la caja azul
#                         if area_x <= x1 <= area_x + area_width and area_y <= y1 <= area_y + area_height:
#                             if label in labels_to_draw:
#                                 # Tomar la probabilidad desde 'coordinates -> area1'
#                                 min_probability = label_probabilities.get(label, 0)

#                                 # Filtrar detecciones basadas en la probabilidad específica
#                                 if probability >= min_probability:
#                                     color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta, blanco si no existe

#                                     # Dibujar el rectángulo de la detección
#                                     cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

#                                     # Agregar un fondo para el texto
#                                     text = f"{label}: {probability:.2f}%"
#                                     (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
#                                     text_offset_x, text_offset_y = x1, y1 - 10
#                                     box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 5, text_offset_y + 5))
#                                     cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)

#                                     # Agregar el texto encima del fondo
#                                     cv2.putText(frame, text, (text_offset_x, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
#                     except Exception as detection_error:
#                         print(f"Error al procesar una detección: {detection_error}")

#                 # Codificar el frame como JPEG
#                 try:
#                     _, buffer = cv2.imencode(".jpg", frame)
#                     frame_bytes = buffer.tobytes()
#                     yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
#                 except Exception as encoding_error:
#                     print(f"Error al codificar el frame: {encoding_error}")
#         except Exception as e:
#             print(f"Error en generate_frames: {e}. Reintentando en {retry_interval} segundos...")
#             time.sleep(retry_interval)
#         finally:
#             if cap:
#                 cap.release()


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








#------------------------------------penultima funcion---------------------------------------------------------

# def generate_frames(config_path, retry_interval=5):
#     """
#     Genera frames desde un RTSP utilizando YOLO para inferencias.
#     Filtra las detecciones dinámicamente basándose en las etiquetas definidas en 'camera.label'
#     y las probabilidades específicas de 'coordinates -> area1'.
#     """
#     while True:
#         try:
#             cap = None
#             while True:
#                 # Recargar la configuración del YAML en cada iteración
#                 try:
#                     config = load_yaml_config(config_path)
#                     print(f"Configuración cargada desde {config_path}: {config}")  # Debug
#                     rtsp_url = config["camera"]["rtsp_url"]
#                 except Exception as yaml_error:
#                     print(f"Error al cargar el archivo YAML: {yaml_error}")
#                     time.sleep(retry_interval)
#                     continue
                
#                 # Validar que existan las claves necesarias
#                 try:
#                     rtsp_url = config["camera"]["rtsp_url"]
                    
#                     # Etiquetas a pintar definidas en 'label'
#                     labels_to_draw = [label.strip() for label in config["camera"].get("label", "").split(",")]

#                     # Probabilidades específicas de 'coordinates -> area1'
#                     area_config = config["camera"]["coordinates"]["area1"]
#                     label_probabilities = {
#                         key: float(value) for key, value in area_config.items()
#                         if key != "camara" and key != "punto"  # Ignorar claves irrelevantes
#                     }
#                     print(f"Etiquetas a pintar: {labels_to_draw}")  # Debug
#                     print(f"Probabilidades cargadas: {label_probabilities}")  # Debug
#                 except KeyError as key_error:
#                     print(f"Clave faltante en el archivo YAML: {key_error}")
#                     time.sleep(retry_interval)
#                     continue
#                 except ValueError as value_error:
#                     print(f"Error en el formato de las probabilidades: {value_error}")
#                     time.sleep(retry_interval)
#                     continue

#                 # Manejo del flujo RTSP
#                 if cap is None or not cap.isOpened():
#                     cap = cv2.VideoCapture(rtsp_url)
#                     if not cap.isOpened():
#                         print(f"No se pudo abrir el video feed: {rtsp_url}. Reintentando en {retry_interval} segundos...")
#                         time.sleep(retry_interval)
#                         continue

#                 ret, frame = cap.read()
#                 if not ret:
#                     print(f"Error al leer el flujo de video: {rtsp_url}. Reiniciando conexión...")
#                     cap.release()
#                     cap = None
#                     break

#                 # Procesar el frame con el modelo cargado globalmente
#                 try:
#                     results = model(frame)
#                 except Exception as model_error:
#                     print(f"Error al procesar el frame con el modelo: {model_error}")
#                     time.sleep(retry_interval)
#                     continue

#                 for detection in results[0].boxes:
#                     try:
#                         # Obtener coordenadas, probabilidad y etiqueta de la detección
#                         x1, y1, x2, y2 = map(int, detection.xyxy[0])
#                         probability = detection.conf[0] * 100
#                         class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
#                         label = LABELS.get(class_index, "Unknown")

#                         # Verificar si la etiqueta está en las configuraciones de 'label'
#                         if label in labels_to_draw:
#                             # Tomar la probabilidad desde 'coordinates -> area1'
#                             min_probability = label_probabilities.get(label, 0)

#                             # Filtrar detecciones basadas en la probabilidad específica
#                             if probability >= min_probability:
#                                 color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta, blanco si no existe

#                                 # Dibujar el rectángulo de la detección
#                                 cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

#                                 # Agregar un fondo para el texto
#                                 text = f"{label}: {probability:.2f}%"
#                                 (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
#                                 text_offset_x, text_offset_y = x1, y1 - 10
#                                 box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 5, text_offset_y + 5))
#                                 cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)

#                                 # Agregar el texto encima del fondo
#                                 cv2.putText(frame, text, (text_offset_x, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
#                     except Exception as detection_error:
#                         print(f"Error al procesar una detección: {detection_error}")

#                 # Codificar el frame como JPEG
#                 try:
#                     _, buffer = cv2.imencode(".jpg", frame)
#                     frame_bytes = buffer.tobytes()
#                     yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
#                 except Exception as encoding_error:
#                     print(f"Error al codificar el frame: {encoding_error}")
#         except Exception as e:
#             print(f"Error en generate_frames: {e}. Reintentando en {retry_interval} segundos...")
#             time.sleep(retry_interval)
#         finally:
#             if cap:
#                 cap.release()




#------------------------------original---------------------------------------------------

# def generate_frames(config_path, retry_interval=5):
#     """
#     Genera frames desde un RTSP utilizando YOLO para inferencias.
#     Filtra las detecciones dinámicamente basándose en el YAML.
#     """
#     while True:
#         try:
#             cap = None
#             while True:
#                 # Recargar la configuración del YAML en cada iteración
#                 config = load_yaml_config(config_path)
#                 print(config)
#                 rtsp_url = config["camera"]["rtsp_url"]
#                 min_probability = float(config["camera"].get("probability", 50))
#                 labels_to_detect = [label.strip() for label in config["camera"].get("label", "").split(",")]

#                 if cap is None or not cap.isOpened():
#                     cap = cv2.VideoCapture(rtsp_url)
#                     if not cap.isOpened():
#                         print(f"No se pudo abrir el video feed: {rtsp_url}. Reintentando en {retry_interval} segundos...")
#                         time.sleep(retry_interval)
#                         continue

#                 ret, frame = cap.read()
#                 if not ret:
#                     print(f"Error al leer el flujo de video: {rtsp_url}. Reiniciando conexión...")
#                     cap.release()
#                     cap = None
#                     break

#                 # Procesar el frame con el modelo cargado globalmente
#                 results = model(frame)

#                 for detection in results[0].boxes:
#                     # Obtener coordenadas, probabilidad y etiqueta de la detección
#                     x1, y1, x2, y2 = map(int, detection.xyxy[0])
#                     probability = detection.conf[0] * 100
#                     class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
#                     label = LABELS.get(class_index, "Unknown")

#                     # Filtrar detecciones basadas en los labels del YAML y la probabilidad
#                     if label in labels_to_detect and probability >= min_probability:
#                         color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta, blanco si no existe

#                         # Dibujar el rectángulo de la detección
#                         cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

#                         # Agregar un fondo para el texto
#                         text = f"{label}: {probability:.2f}%"
#                         (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
#                         text_offset_x, text_offset_y = x1, y1 - 10
#                         box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 5, text_offset_y + 5))
#                         cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)

#                         # Agregar el texto encima del fondo
#                         cv2.putText(frame, text, (text_offset_x, text_offset_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

#                 # Codificar el frame como JPEG
#                 _, buffer = cv2.imencode(".jpg", frame)
#                 frame_bytes = buffer.tobytes()

#                 # Yield del frame para streaming
#                 yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
#         except Exception as e:
#             print(f"Error en generate_frames: {e}. Reintentando en {retry_interval} segundos...")
#             time.sleep(retry_interval)
#         finally:
#             if cap:
#                 cap.release()