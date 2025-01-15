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
from src.Tipo_notificacion import save_video_from_buffer

def procesar_detecciones(config_path, camera_id):
    tiempo_deteccion_por_area = {}
    while True:
        """
        Procesa las detecciones de objetos en cada área definida y las imprime en consola.
        """
        # Cargar configuración
        try:
            config = load_yaml_config(config_path)
            rtsp_url = config["camera"]["rtsp_url"]
            areas = config["camera"]["coordinates"]
            tiempos_limite = json.loads(config["camera"]["time_areas"])

            # Convertir valores de tiempos_limite a float
            tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
            # Convertir valores de tiempos_limite a float
            if isinstance(tiempos_limite, str):
                tiempos_limite = json.loads(tiempos_limite)  # Convertir JSON si es una cadena
            tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
            
            sitio = config['camera']["point"]
            nombre_camera = config['camera']["name camera"]
            info_notifications = config['camera']["info_notifications"]
            if info_notifications:
                try:
                    info_notifications = json.loads(info_notifications)
                    # print(info_notifications)
                except json.JSONDecodeError as e:
                    print(f"Error decodificando JSON: {e}")
        except Exception as e:
            print(f"Error al cargar configuración: {e}")
            return

        # Variables para el seguimiento de detecciones
        
        target_width, target_height = 640, 380  # Resolución deseada

        # Obtener buffer de frames
        streamers = get_streamers()
        info_buffer = streamers[camera_id]

        frame_to_process = None

        with info_buffer.buffer_lock:
            if info_buffer.frame_buffer:
                if len(info_buffer.frame_buffer) > 150:
                    frame_to_process = info_buffer.frame_buffer.pop(0)

        if frame_to_process is not None:
            frame = cv2.resize(frame_to_process, (target_width, target_height))
            width2, height2 = 294.12, 145.45  # Dimensiones originales
            width1, height1 = 640, 380  # Dimensiones redimensionadas

            for area_name, area_config in areas.items():
                try:
                    # Escalar coordenadas del área
                    area_x = float(area_config["x"])
                    area_y = float(area_config["y"])
                    area_width = float(area_config["width"])
                    area_height = float(area_config["height"])

                    x1 = (area_x / width2) * width1
                    y1 = (area_y / height2) * height1
                    rect_width1 = (area_width / width2) * width1
                    rect_height1 = (area_height / height2) * height1

                    detecciones_obtenidas = False
                    salidas_por_area = None
                    salidas_por_area2 = None
                    
                    start_point = (int(x1), int(y1))
                    end_point = (int(x1 + rect_width1), int(y1 + rect_height1))

                    # Procesar el frame con el modelo
                    results = model(frame, verbose=False)

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

                                        # Verificar si la detección está dentro de la caja actual y cumple la probabilidad
                                        if start_point[0] <= x1_det <= end_point[0] and start_point[1] <= y1_det <= end_point[1]:

                                            if probability >= min_probability:
                                                # print(f"Se detectó {label} con una probabilidad de {probability:.2f}% en el área {area_name}")
                                                # Dibujar la detección
                                                # color = COLORS.get(label, (255, 255, 255))  # Color por etiqueta

                                                # Agregar el texto de la etiqueta
                                                text = f"{label}: {probability:.2f}%"
                                                (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                                                text_offset_x, text_offset_y = x1_det, y1_det - 10
                                                box_coords = ((text_offset_x, text_offset_y - text_height - 5), 
                                                            (text_offset_x + text_width + 5, text_offset_y + 5))

                                                detecciones_obtenidas = True
                                                now = time.time()

                                                # Inicializar tiempo solo si no existe
                                                if (area_name, label) not in tiempo_deteccion_por_area:
                                                    tiempo_deteccion_por_area[(area_name, label)] = now
                                                else:
                                                    # Calcular tiempo acumulado
                                                    tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]
                                                    print(f"Tiempo acumulado para {area_name}, {label}: {tiempo_acumulado:.2f} segundos")

                                                    # Verificar si el tiempo acumulado cumple el límite
                                                    if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                                        fecha_actual = datetime.now().strftime("%d/%m/%Y")
                                                        hora_actual = datetime.now().strftime("%H:%M:%S")

                                                        print(f"{label} detectada en {area_name} por {tiempos_limite[area_name]} segundos.")
                                                        # save_video_from_buffer(info_buffer.frame_buffer, f"{area_name}_{label}.mp4", 20)
                                                        
                                                        descripcionPersona = f"Se detectó una Persona en el {area_name} con una probabilidad de {probability:.2f}% en la cámara {nombre_camera}"
                                                        descripcionSinCasco = f"Se detectó una Persona sin casco en el {area_name} con una probabilidad de {probability:.2f}% en la cámara {nombre_camera}"
                                                        descripcionCascoBlanco = f"Se detectó una persona con Casco Blanco en el {area_name} con una probabilidad de {probability:.2f}% en la cámara {nombre_camera}"
                                                        descripcionCascoAmarilloVerde = f"Se detectó una persona con Casco Amarillo o Verde en el {area_name} con una probabilidad de {probability:.2f}% en la cámara {nombre_camera}"


                                                        if label == "A_Person":
                                                            NombreLabel = "Personas"
                                                            descript = descripcionPersona
                                                        elif label == "White":
                                                            NombreLabel = "Persona con casco blanco"
                                                            descript = descripcionCascoBlanco
                                                        elif label == "No_Helmet":
                                                            NombreLabel = "Persona Sin casco"
                                                            descript = descripcionSinCasco
                                                        elif label == "YellowGreen":
                                                            NombreLabel = "Persona con casco Amarillo o Verde"
                                                            descript = descripcionCascoAmarilloVerde

                                
                                                        add_event_to_database(
                                                                    sitio = sitio,
                                                                    company="TechCorp",
                                                                    fecha = fecha_actual,
                                                                    hora= hora_actual,
                                                                    tipo_evento= f"Detección de {NombreLabel} en {area_name}",
                                                                    descripcion= descript
                                                                )
                                                        
                                                        id_registro = get_last_event_id()
                                                        set_id(id_registro)
                                                        # print("Tamaño del buffer: ", len(info_buffer.frame_buffer))
                                                        # Reiniciar el tiempo acumulado solo si se cumple el tiempo límite
                                                        tiempo_deteccion_por_area[(area_name, label)] = time.time()

                                                        # Verificar si el tiempo acumulado cumple el límite
                                                        if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                                            print(f"{label} detectada en {area_name} por {tiempos_limite[area_name]} segundos.")
                                                            # save_video_from_buffer(info_buffer.frame_buffer, f"{area_name}_{label}.mp4", 20)
                                                            print("Info Notificaciones: ",info_notifications)
                                                            print("Tamaño del buffer: ", len(info_buffer.frame_buffer))
                                                            # Reiniciar el tiempo acumulado solo si se cumple el tiempo límite
                                                            tiempo_deteccion_por_area[(area_name, label)] = time.time()

                                                # # Condicional para pintar del label  
                                                # if label in config["camera"]["label"]:
                                                #     cv2.rectangle(frame, (x1_det, y1_det), (x2_det, y2_det), color, 2)
                                                #     cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
                                                #     cv2.putText(frame, text, (text_offset_x, text_offset_y), 
                                                #                 cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                                            else:
                                                # Si la detección está fuera de los límites o no cumple con la probabilidad mínima
                                                tiempo_deteccion_por_area.pop((area_name, label), None)  # Reiniciar el tiempo al salir del área
                                                # print(f"{label} salió de {area_name}, reiniciando el tiempo.")


                        except Exception as detection_error:
                            print(f"Error al procesar una detección en {area_name}: {detection_error}")
                except Exception as area_error:
                    print(f"Error al procesar {area_name}: {area_error}")
                    
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
