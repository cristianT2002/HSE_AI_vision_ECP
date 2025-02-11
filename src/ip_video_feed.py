import time
import os
import json
from datetime import datetime
import cv2
from src.load_config import load_yaml_config
from src.model_loader import model, LABELS
from src.variables_globales import get_streamers
from src.db_utils import connect_to_db, close_connection
from src.variables_globales import get_streamers, set_streamers, set_id
from src.Tipo_notificacion import save_video_from_buffer, guardar_imagen_en_mariadb
import socket
import numpy as np
 
def procesar_detecciones(config_path, camera_id):
    tiempo_deteccion_por_area = {}
   
    # Colores para las etiquetas
    COLORS = {
        "A_Person": (255, 0, 0),      # Azul
        "Green": (0, 0, 255),         # Rojo
        "Harness": (0, 255, 206),     # Verde
        "No_Harness": (0, 0, 255),    # Rojo
        "No_Helmet": (0, 0, 255),     # Rojo
        "White": (120, 120, 120),     # Gris
        "Yellow": (0, 0, 255),        # Rojo
        "Loading_Machine": (0, 100, 19),  # Verde Bosque Oscuro
        "Mud_Bucket": (255, 171, 171),    # Rosa Suave
        "Orange": (0, 128, 255),      # Naranja
    }
   
    host_ip = socket.gethostbyname(socket.gethostname())
    feed_url = f"http://{host_ip}:5000/video_feed/{camera_id}"
    save_feed_url_to_database(camera_id, feed_url)
 
    while True:
        # Cargar la configuración
        try:
            config = load_yaml_config(config_path)
            # Usar "video_path" en lugar de "rtsp_url"
            rtsp_url = config["camera"]["rtsp_url"]
            areas = config["camera"]["coordinates"]
            tiempos_limite = json.loads(config["camera"]["time_areas"])
            # Asegurarse de que los límites sean float
            tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
            if isinstance(tiempos_limite, str):
                tiempos_limite = json.loads(tiempos_limite)
            tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
           
            sitio = config['camera']["point"]
            nombre_camera = config['camera']["name camera"]
            info_notifications = config['camera']["info_notifications"]
            if info_notifications:
                try:
                    info_notifications = json.loads(info_notifications)
                except json.JSONDecodeError as e:
                    print(f"Error decodificando JSON de notificaciones: {e}")
            emails = config['camera']["info_emails"]
            if emails:
                try:
                    emails = json.loads(emails)
                except json.JSONDecodeError as e:
                    print(f"Error decodificando JSON de correos: {e}")
        except Exception as e:
            print(f"Error al cargar configuración: {e}")
            return
 
        # Abrir el video estático
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print(f"Error al abrir el video: {rtsp_url}")
            return
 
        target_width, target_height = 640, 380  # Resolución deseada
 
        ret, frame_to_process = cap.read()
        if not ret:
            # Si se llega al final del video, reiniciar
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
 
        frame = cv2.resize(frame_to_process, (target_width, target_height))
        # Dimensiones originales (ajusta estos valores según corresponda)
        width2, height2 = 294.12, 145.45  
        width1, height1 = 640, 380
 
        for area_name, area_config in areas.items():
            try:
                # Escalar los puntos del polígono del área
                original_points = area_config["points"]
                scaled_points = [
                    {
                        "x": (point["x"] / width2) * width1,
                        "y": (point["y"] / height2) * height1
                    }
                    for point in original_points
                ]
 
                # Convertir los puntos al formato requerido por OpenCV
                pts = np.array(
                    [[int(point["x"]), int(point["y"])] for point in scaled_points],
                    dtype=np.int32
                ).reshape((-1, 1, 2))
 
                # Dibujar el polígono en el frame
                cv2.polylines(frame, [pts], isClosed=True, color=(255, 0, 0), thickness=2)
 
                # Procesar el frame con el modelo YOLO
                results = model(frame, verbose=False)
 
                for detection in results[0].boxes:
                    try:
                        # Extraer coordenadas, probabilidad y etiqueta
                        x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                        point = (x1_det, y1_det)
                        point2 = (int((x1_det + x2_det) / 2), y2_det)
 
                        probability = detection.conf[0] * 100
                        class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                        label = LABELS.get(class_index, "Unknown")
 
                        # Comprobar si la etiqueta es válida para el área
                        if label in area_config:
                            min_probability = float(area_config[label])
                            inside = cv2.pointPolygonTest(pts, point, False)
 
                            if inside >= 0 and probability >= min_probability:
                                print("Detectando en cámara:", camera_id)
                                print(f"Se detectó {label} con {probability:.2f}% en el área {area_name}")
                                color = COLORS.get(label, (255, 255, 255))
                                text = f"{label}: {probability:.2f}%"
                                (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                                text_offset_x, text_offset_y = x1_det, y1_det - 10
                                box_coords = ((text_offset_x, text_offset_y - text_height - 5),
                                              (text_offset_x + text_width + 25, text_offset_y + 5))
 
                                now = time.time()
                                if (area_name, label) not in tiempo_deteccion_por_area:
                                    tiempo_deteccion_por_area[(area_name, label)] = now
                                else:
                                    tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]
                                    print(f"Tiempo acumulado para {area_name}, {label}: {tiempo_acumulado:.2f} s")
                                    if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                        fecha_actual = datetime.now().strftime("%d/%m/%Y")
                                        hora_actual = datetime.now().strftime("%H:%M:%S")
                                        if label == "A_Person":
                                            NombreLabel = "Personas"
                                            descript = f"Se detectó una Persona en {area_name} en la cámara {nombre_camera}"
                                        elif label == "White":
                                            NombreLabel = "Persona con casco blanco"
                                            descript = f"Se detectó una Persona con casco blanco en {area_name} en la cámara {nombre_camera}"
                                        elif label == "No_Helmet":
                                            NombreLabel = "Persona Sin casco"
                                            descript = f"Se detectó una Persona sin casco en {area_name} en la cámara {nombre_camera}"
                                        elif label == "YellowGreen":
                                            NombreLabel = "Persona con casco Amarillo o Verde"
                                            descript = f"Se detectó una Persona con casco Amarillo o Verde en {area_name} en la cámara {nombre_camera}"
                                        else:
                                            descript = f"Se detectó {label} en {area_name} en la cámara {nombre_camera}"
 
                                        add_event_to_database(
                                            sitio=sitio,
                                            company="TechCorp",
                                            fecha=fecha_actual,
                                            hora=hora_actual,
                                            tipo_evento=f"Detección de {NombreLabel} en {area_name}",
                                            descripcion=descript
                                        )
                                        id_registro = get_last_event_id()
                                        set_id(id_registro)
                                        tiempo_deteccion_por_area[(area_name, label)] = time.time()
                                        cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)
                                        cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                        cv2.putText(frame, text, (text_offset_x, text_offset_y),
                                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                                        # NOTA: Si no cuentas con un buffer de frames, revisa o adapta save_video_from_buffer
                                        if info_notifications.get('Video') == True:
                                            # Aquí deberás ajustar la forma de guardar un clip de video
                                            save_video_from_buffer([], f"videos_{area_name}_{label}_{nombre_camera}.mp4",
                                                                   info_notifications.get('Email'), emails)
                                        elif info_notifications.get('Imagen') == True:
                                            nombre_img = f"Imgs/img_{area_name}_{label}_{nombre_camera}.jpg"
                                            directorio = os.path.dirname(nombre_img)
                                            if not os.path.exists(directorio):
                                                os.makedirs(directorio)
                                            cv2.imwrite(nombre_img, frame)
                                            guardar_imagen_en_mariadb(nombre_img, info_notifications.get('Email'), emails)
                                            print("Info notificaciones:", info_notifications)
 
                            if area_name == "area3":
                                inside_point2 = cv2.pointPolygonTest(pts, point2, False)
                                if inside_point2 >= 0 and probability >= min_probability:
                                    print("Detectando en cámara:", camera_id)
                                    print(f"Se detectó {label} con {probability:.2f}% en el área {area_name} DONDE ESTA EL")
                                    color = COLORS.get(label, (255, 255, 255))
                                    text = f"{label}: {probability:.2f}%"
                                    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                                    text_offset_x, text_offset_y = x1_det, y1_det - 10
                                    box_coords = ((text_offset_x, text_offset_y - text_height - 5),
                                                (text_offset_x + text_width + 25, text_offset_y + 5))
 
                                    now = time.time()
                                    if (area_name, label) not in tiempo_deteccion_por_area:
                                        tiempo_deteccion_por_area[(area_name, label)] = now
                                    else:
                                        tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]
                                        print(f"Tiempo acumulado para {area_name}, {label}: {tiempo_acumulado:.2f} s")
                                        if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                            fecha_actual = datetime.now().strftime("%d/%m/%Y")
                                            hora_actual = datetime.now().strftime("%H:%M:%S")
                                            if label == "A_Person":
                                                NombreLabel = "Personas"
                                                descript = f"Se detectó una Persona en {area_name} en la cámara {nombre_camera}"
                                            elif label == "White":
                                                NombreLabel = "Persona con casco blanco"
                                                descript = f"Se detectó una Persona con casco blanco en {area_name} en la cámara {nombre_camera}"
                                            elif label == "No_Helmet":
                                                NombreLabel = "Persona Sin casco"
                                                descript = f"Se detectó una Persona sin casco en {area_name} en la cámara {nombre_camera}"
                                            elif label == "YellowGreen":
                                                NombreLabel = "Persona con casco Amarillo o Verde"
                                                descript = f"Se detectó una Persona con casco Amarillo o Verde en {area_name} en la cámara {nombre_camera}"
                                            else:
                                                descript = f"Se detectó {label} en {area_name} en la cámara {nombre_camera}"
 
                                            add_event_to_database(
                                                sitio=sitio,
                                                company="TechCorp",
                                                fecha=fecha_actual,
                                                hora=hora_actual,
                                                tipo_evento=f"Detección de {NombreLabel} en {area_name}",
                                                descripcion=descript
                                            )
                                            id_registro = get_last_event_id()
                                            set_id(id_registro)
                                            tiempo_deteccion_por_area[(area_name, label)] = time.time()
                                            cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)
                                            cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                            cv2.putText(frame, text, (text_offset_x, text_offset_y),
                                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                                            # NOTA: Si no cuentas con un buffer de frames, revisa o adapta save_video_from_buffer
                                            if info_notifications.get('Video') == True:
                                                # Aquí deberás ajustar la forma de guardar un clip de video
                                                save_video_from_buffer([], f"videos_{area_name}_{label}_{nombre_camera}.mp4",
                                                                    info_notifications.get('Email'), emails)
                                            elif info_notifications.get('Imagen') == True:
                                                nombre_img = f"Imgs/img_{area_name}_{label}_{nombre_camera}.jpg"
                                                directorio = os.path.dirname(nombre_img)
                                                if not os.path.exists(directorio):
                                                    os.makedirs(directorio)
                                                cv2.imwrite(nombre_img, frame)
                                                guardar_imagen_en_mariadb(nombre_img, info_notifications.get('Email'), emails)
                                                print("Info notificaciones:", info_notifications)
 
                                       
                            else:
                                # Si la detección no cumple, reiniciamos el tiempo
                                tiempo_deteccion_por_area.pop((area_name, label), None)
                                print(f"{label} salió de {area_name}, reiniciando el tiempo.")
                                
                                
                                
                    except Exception as detection_error:
                        print(f"Error al procesar una detección en {area_name}: {detection_error}")
            except Exception as area_error:
                print(f"Error al procesar {area_name}: {area_error}")
 
 
 
 
 
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
 
 
def add_event_to_database(sitio, company, fecha, hora, tipo_evento, descripcion):
    """
    Inserta un nuevo registro en la tabla 'eventos' con los valores proporcionados.
    """
    connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
    cursor = connection.cursor()
 
    try:
        insert_query = """
            INSERT INTO Eventos (sitio, company, fecha, hora, tipo_evento, descripcion)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (sitio, company, fecha, hora, tipo_evento, descripcion))
        connection.commit()
    except Exception as e:
        print(f"Error al añadir el evento a la base de datos: {e}")
    finally:
        cursor.close()
        close_connection(connection)
       
 
def get_last_event_id():
    """
    Obtiene el ID del último registro en la tabla 'Eventos'.
    """
    connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
    cursor = connection.cursor()
 
    try:
        query = "SELECT id_evento FROM Eventos ORDER BY id_evento DESC LIMIT 1"
        cursor.execute(query)
        result = cursor.fetchone()
        if result:
            last_id = result[0]
            # print(f"El último ID en la tabla 'Eventos' es: {last_id}")
            return last_id
        else:
            print("No se encontraron registros en la tabla 'Eventos'.")
            return None
    except Exception as e:
        print(f"Error al obtener el último ID: {e}")
        return None
    finally:
        cursor.close()
        close_connection(connection)
 
if __name__ == "__main__":
    camera_id = 1  # Cambiar según la cámara deseada
    config_path = f"configs/camera_{camera_id}.yaml"
 
    if not os.path.exists(config_path):
        print(f"No se encontró el archivo YAML para la cámara {camera_id}.")
    else:
       
        procesar_detecciones(config_path, camera_id)