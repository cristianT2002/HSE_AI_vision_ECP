import os
import time
import socket
import json
import cv2
import numpy as np
import multiprocessing as mp
from multiprocessing import Manager
from datetime import datetime
from src.variables_globales import get_streamers, set_streamers, set_id
from src.Tipo_notificacion import save_video_from_buffer, guardar_imagen_en_mariadb
from src.db_utils import connect_to_db, close_connection
from src.load_config import load_yaml_config
from src.model_loader import model, LABELS
import threading

class ProcesarDetecciones:
    def __init__(self, config_path, camera_id, shared_buffers, buffer_detecciones):
        self.config_path = config_path
        self.camera_id = camera_id
        
        self.shared_buffers = shared_buffers
        self.buffer_detecciones = buffer_detecciones
        self.tiempo_deteccion_por_area = {}
        self.tiempo_ultimo_detecciones = {}
        self.tiempo_ultimo_dibujo = {}  # Diccionario para controlar el cambio de color de áreas

        self.tiempo_acumulado = 0
        self.area_pintada = set()  # 🔥 Bandera para evitar repintar el área
        self.tiempo_ultimo_dibujo = {}  # 🔥 Control del tiempo del último dibujo
        self.areas_con_deteccion = {}  # 🔥 Controla si un área tiene detecciones activas

        # Definir color para detección activa
        self.COLOR_DETECCION = (0, 0, 255, 50)  # Rojo transparente


        # if self.camera_id not in self.buffer_detecciones:
        #     self.buffer_detecciones[self.camera_id] = manager.list()  # Asegurar lista compartida
        
        self.running = True
        
        self.COLORS = {
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

    def procesar(self):
        # host_ip = socket.gethostbyname(socket.gethostname())
        host_ip = "172.30.37.63"
        feed_url = f"http://{host_ip}:5000/video_feed/{self.camera_id}"

        # Guardar la URL del video feed en la base de datos
        self.save_feed_url_to_database(self.camera_id, feed_url)

        while self.running:
            # print("Buffer antes de todo: ", self.buffer_detecciones)
            
            # Cargar configuración
            try:
                self.config = load_yaml_config(self.config_path)
                rtsp_url = self.config["camera"]["rtsp_url"]
                areas = self.config["camera"]["coordinates"]
                tiempos_limite = json.loads(self.config["camera"]["time_areas"])

                # Convertir valores de tiempos_limite a float
                tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
                # Convertir valores de tiempos_limite a float
                if isinstance(tiempos_limite, str):
                    tiempos_limite = json.loads(tiempos_limite)  # Convertir JSON si es una cadena
                tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
                
                sitio = self.config['camera']["point"]
                nombre_camera = self.config['camera']["name camera"]
                info_notifications = self.config['camera']["info_notifications"]
                if info_notifications:
                    try:
                        info_notifications = json.loads(info_notifications)
                        # print(info_notifications)
                    except json.JSONDecodeError as e:
                        print(f"Error decodificando JSON de notificaciones: {e}")
                        
                emails = self.config['camera']["info_emails"]
                if emails:
                    try:
                        emails = json.loads(emails)
                        # print(emails)
                    except json.JSONDecodeError as e:
                        print(f"Error decodificando JSON de correos: {e}")
            except Exception as e:
                print(f"Error al cargar configuración: {e}")
                return

            # Variables para el seguimiento de detecciones
            target_width, target_height = 640, 380  # Resolución deseada

            # Obtener buffer de frames
            frame_buffer = self.shared_buffers.get(self.camera_id, None)

            if not frame_buffer:
                time.sleep(0.05)
                continue

            try:
                frame_to_process = frame_buffer[0]  # Último frame en el buffer
            except IndexError:
                print(f"⚠️ Error: Intento de acceder a un frame inexistente en notifications {self.camera_id}")
                time.sleep(0.05)
                continue
            
            frame = cv2.resize(frame_to_process, (target_width, target_height))

            for area_name, area_config in areas.items():
                # try:
                    # Procesar el área y realizar detección
                    pts = self.escalar_puntos(area_config)
                    # Dibujar el polígono escalado en el frame
                    if area_name == "area3":
                        polygon_color = (0, 255, 0)  # Verde para area2
                    elif area_name == "area2":
                        polygon_color = (255, 255, 0)
                    else:
                        polygon_color = (255, 0, 0)  # Rojo o azul para otras áreas (según lo desees)
                    
                    # Dibujar el polígono escalado en el frame con el color definido
                    cv2.polylines(frame, [pts], isClosed=True, color=polygon_color, thickness=2)

                    results = model(frame, verbose=False)

                    for detection in results[0].boxes:
                        self.procesar_deteccion_2(detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts)
                    
                # except Exception as area_error:
                #     print(f"Error al procesar {area_name}: {area_error}")

            # Guardar frame en buffer de detecciones
            self.actualizar_buffer(frame)

    # def procesar(self):
    #     # Cargar la configuración y obtener parámetros necesarios
    #     try:
    #         self.config = load_yaml_config(self.config_path)
    #         rtsp_url = self.config["camera"]["rtsp_url"]
    #         areas = self.config["camera"]["coordinates"]
    #         tiempos_limite = self.config["camera"]["time_areas"]
    #         # Asegurar que tiempos_limite sea un diccionario con valores float
    #         if isinstance(tiempos_limite, str):
    #             tiempos_limite = json.loads(tiempos_limite)
    #         tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}

    #         sitio = self.config["camera"]["point"]
    #         nombre_camera = self.config["camera"]["name camera"]

    #         info_notifications = self.config["camera"]["info_notifications"]
    #         if info_notifications:
    #             try:
    #                 info_notifications = json.loads(info_notifications)
    #             except json.JSONDecodeError as e:
    #                 print(f"Error decodificando JSON de notificaciones: {e}")

    #         emails = self.config["camera"]["info_emails"]
    #         if emails:
    #             try:
    #                 emails = json.loads(emails)
    #             except json.JSONDecodeError as e:
    #                 print(f"Error decodificando JSON de correos: {e}")
    #     except Exception as e:
    #         print(f"Error al cargar configuración: {e}")
    #         return

    #     # Abrir el video estático utilizando la URL rtsp
    #     cap = cv2.VideoCapture(rtsp_url)
    #     if not cap.isOpened():
    #         print("Error al abrir el video con rtsp_url")
    #         return

    #     target_width, target_height = 640, 380  # Resolución deseada

    #     while True:
    #         ret, frame = cap.read()
    #         if not ret:
    #             print("Fin del video o error al leer frame")
    #             break

    #         # Redimensionar el frame
    #         frame = cv2.resize(frame, (target_width, target_height))

    #         # Procesar cada área definida en la configuración
    #         for area_name, area_config in areas.items():
    #             pts = self.escalar_puntos(area_config)
    #             # Seleccionar el color del polígono según el nombre del área
    #             if area_name == "area3":
    #                 polygon_color = (0, 255, 0)
    #             elif area_name == "area2":
    #                 polygon_color = (255, 255, 0)
    #             else:
    #                 polygon_color = (255, 0, 0)
                
    #             # Dibujar el polígono en el frame
    #             cv2.polylines(frame, [pts], isClosed=True, color=polygon_color, thickness=2)

    #             # Realizar detección en el frame (se asume que 'model' está definido)
    #             results = model(frame, verbose=False)
    #             for detection in results[0].boxes:
    #                 self.procesar_deteccion_2(
    #                     detection, area_name, area_config, tiempos_limite,
    #                     frame, sitio, nombre_camera, info_notifications, emails, pts
    #                 )
                    
    #             # Guardar frame en buffer de detecciones
    #             # self.actualizar_buffer(frame)

    #         # Mostrar el frame procesado (opcional)
    #         cv2.imshow("Video", frame)
    #         if cv2.waitKey(1) & 0xFF == ord('q'):
    #             break

    #     cap.release()
    #     cv2.destroyAllWindows()


    def save_feed_url_to_database(self, camera_id, url):
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


    # def dibujar_area(self, frame, pts, color):
    #     """Pinta el área solo una vez cuando inicia la detección y la borra cuando desaparece."""
    #     overlay = frame.copy()  # Crear una copia de la imagen
    #     cv2.fillPoly(overlay, [pts], color[:3])  # Relleno del área con el color
    #     alpha = color[3] / 255.0  # Transparencia

    #     # Mezclar la imagen con la transparencia
    #     cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # def dibujo_etiquetas(self, frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height):
    #     """Dibuja etiquetas sobre el frame."""
    #     cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
    #     cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
    #     cv2.putText(frame, text, (text_offset_x, text_offset_y),
    #                 cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    def dibujar_area(self, frame, pts, color):
        """Dibuja el área solo una vez, evitando acumulación de capas."""
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], color[:3])  # Relleno del área con el color
        alpha = color[3] / 255.0  # Transparencia
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    def dibujo_etiquetas(self, frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height):
        """Dibuja etiquetas sobre el frame."""
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        cv2.rectangle(frame, box_coords[0], box_coords[1], color, -1)
        cv2.putText(frame, text, (text_offset_x, text_offset_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        
    def escalar_puntos(self, area_config):
        """Escala los puntos del polígono según la resolución."""
        width2, height2 = 294.12, 145.45
        width1, height1 = 640, 380

        scaled_points = [
            {
                "x": (point["x"] / width2) * width1,
                "y": (point["y"] / height2) * height1
            }
            for point in area_config["points"]
        ]

        return np.array(
            [[int(point["x"]), int(point["y"])] for point in scaled_points],
            dtype=np.int32
        ).reshape((-1, 1, 2))

#Version inicial
    def procesar_deteccion(self, detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts):
        """Procesa una detección específica en el frame."""
        # try:
        x1, y1, x2, y2 = map(int, detection.xyxy[0])
        point = (x1, y1)
        point2 = (int((x1 + x2) / 2), y2)
        probability = detection.conf[0] * 100
        class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
        label = LABELS.get(class_index, "Unknown")

        if label in area_config:
            min_probability = float(area_config[label])
            inside = cv2.pointPolygonTest(self.escalar_puntos(area_config), point, False)
            
            if probability >= min_probability:
                
                if area_name == "area3":
                    inside_point2 = cv2.pointPolygonTest(pts, point2, False)
                    if inside_point2 >= 0 and probability >= min_probability:
                        # if self.camera_id == 2:
                        print(f"EN AREA 3 Se detectó {label} con {probability:.2f}% en el área {area_name}, tiempo acumulado: {self.tiempo_acumulado:.2f} segundos, tiempo limite: {tiempos_limite.get(area_name, 5)}")
                        color = self.COLORS.get(label, (255, 255, 255))
                        text = f"{label}: {probability:.2f}%"
                        (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                        text_offset_x, text_offset_y = x1, y1 - 10
                        box_coords = ((text_offset_x, text_offset_y - text_height - 5),
                                    (text_offset_x + text_width + 25, text_offset_y + 5))
                        self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
                        now_area3 = time.time()
                        now_mostrar = datetime.now()
                        # print("Fecha y hora actual:", now_mostrar.strftime("%Y-%m-%d %H:%M:%S"))

                        if (area_name, label) not in self.tiempo_deteccion_por_area:
                            self.tiempo_deteccion_por_area[(area_name, label)] = now_area3
                            print("Empezo a contar el tiempo")
                        else:
                            self.tiempo_acumulado = now_area3 - self.tiempo_deteccion_por_area[(area_name, label)]
                            print(f"Tiempo acumulado: {self.tiempo_acumulado:.2f} segundos")
                            if self.tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                self.guardar_evento(area_name, label, nombre_camera, sitio)
                                self.tiempo_deteccion_por_area[(area_name, label)] = time.time()
                                self.guardar_evidencia(frame, area_name, label, nombre_camera, info_notifications, emails)
                                # self.tiempo_deteccion_por_area.pop((area_name, label), None)
                                print("Tiempo limite:", tiempos_limite.get(area_name, 5))
                                print(f"Evento guardado en la base de datos para {area_name} con {label}")
                                # print(self.tiempo_deteccion_por_area[(area_name, label)])
                                
                elif inside >= 0 and probability >= min_probability:
                    
                    print(f"Se detectó {label} con {probability:.2f}% en el área {area_name}, tiempo acumulado: {self.tiempo_acumulado:.2f} segundos, tiempo limite: {tiempos_limite.get(area_name, 5)}, en cámera {nombre_camera}")
                    print("Tiempo limite:", tiempos_limite.get(area_name, 5))
                    color = self.COLORS.get(label, (255, 255, 255))
                    text = f"{label}: {probability:.0f}%"
                    (text_width, text_height), _ = cv2.getTextSize(
                        text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
                    )
                    text_offset_x, text_offset_y = x1, y1 - 10
                    box_coords = (
                        (text_offset_x, text_offset_y - text_height - 5),
                        (text_offset_x + text_width + 25, text_offset_y + 5)
                    )
                    self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
                    now_resto = time.time()
                    now_mostrar = datetime.now()
                    # print("Fecha y hora actual:", now_mostrar.strftime("%Y-%m-%d %H:%M:%S"))

                    if (area_name, label) not in self.tiempo_deteccion_por_area:
                        self.tiempo_deteccion_por_area[(area_name, label)] = now_resto
                    else:
                        self.tiempo_acumulado = now_resto - self.tiempo_deteccion_por_area[(area_name, label)]
                        
                        if self.tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                            self.guardar_evento(area_name, label, nombre_camera, sitio)
                            self.tiempo_deteccion_por_area[(area_name, label)] = time.time()
                            self.guardar_evidencia(frame, area_name, label, nombre_camera, info_notifications, emails)
                
                else:
                    # Si la detección no cumple, reiniciamos el tiempo
                    self.tiempo_deteccion_por_area.pop((area_name, label), None)
                    now_resto = time.time()
                    self.tiempo_deteccion_por_area[(area_name, label)] = now_resto
                    self.tiempo_acumulado = now_resto - self.tiempo_deteccion_por_area[(area_name, label)]
                    print(f"{label} salió de {area_name}, reiniciando el tiempo. {self.tiempo_acumulado:.2f} segundos, Tiempo limite: {tiempos_limite.get(area_name, 5)}")

# Versión sin areas                
    def procesar_deteccion_2(self, detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts):
        """Procesa una detección específica en el frame y maneja el tiempo de permanencia con margen de 2 segundos."""
        
        x1, y1, x2, y2 = map(int, detection.xyxy[0])
        point = (x1, y1)
        point2 = (int((x1 + x2) / 2), y2)
        probability = detection.conf[0] * 100
        class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
        label = LABELS.get(class_index, "Unknown")
        hora_actual_PS = 0
        
        if label not in area_config:
            return  # No está en las etiquetas configuradas para el área

        min_probability = float(area_config[label])
        inside = cv2.pointPolygonTest(pts, point, False)
        
        if probability < min_probability:
            return  # Probabilidad no suficiente
        
        dentro_del_area = inside >= 0
        if area_name == "area3":
            dentro_del_area = cv2.pointPolygonTest(pts, point2, False) >= 0
        if dentro_del_area:
            # Dibujar detección en el frame
            color = self.COLORS.get(label, (255, 255, 255))
            text = f"{label}: {probability:.2f}%"
            (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            text_offset_x, text_offset_y = x1, y1 - 10
            box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 25, text_offset_y + 5))
            
            self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
            now = time.time()

            if (area_name, label) not in self.tiempo_deteccion_por_area:
                self.tiempo_deteccion_por_area[(area_name, label)] = now
                self.tiempo_ultimo_detecciones[(area_name, label)] = now
                print(f"⏳ Inicio detección {label} en {area_name} ({nombre_camera})")
            else:
                tiempo_acumulado = now - self.tiempo_deteccion_por_area[(area_name, label)]
                # Actualizar el tiempo de detección cada vez que se mantenga dentro del área
                self.tiempo_ultimo_detecciones[(area_name, label)] = now
                tiempo_restante_alerta = tiempos_limite.get(area_name, 5) - tiempo_acumulado
                if tiempo_restante_alerta <= 1:
                    color = (0, 0, 255) # Rojo
                    
                    # Dibujar detección en el frame con color actualizado
                    text = f"{label}: {probability:.2f}%"
                    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                    text_offset_x, text_offset_y = x1, y1 - 10
                    box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 25, text_offset_y + 5))
                    # Dibujar el polígono en el frame
                    cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
                    self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
                
                if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                    self.guardar_evento(area_name, label, nombre_camera, sitio)
                    self.tiempo_deteccion_por_area[(area_name, label)] = time.time()
                    hilo = threading.Thread(target=self.guardar_evidencia, args=( frame, area_name, label, nombre_camera, info_notifications, emails), daemon=True)
                    hilo.start()
                    print(f"🚨 Evento registrado: {label} en {area_name} (Cámara {nombre_camera})")
                
                hora_actual_PS = datetime.now().strftime("%H:%M:%S")
                print(f"📊 {label} en {area_name} ({nombre_camera}) - {tiempo_acumulado:.2f}s / {tiempos_limite.get(area_name, 5)}s a las {hora_actual_PS}")

        else:
            # Si no hay detección, esperar 4s antes de quitar la detección
            if (area_name, label) in self.tiempo_deteccion_por_area:
                tiempo_desde_ultima = time.time() - self.tiempo_ultimo_detecciones[(area_name, label)]
                tiempo_restante = 6 - tiempo_desde_ultima  # Tiempo restante antes de resetear
                
                if tiempo_restante > 0:
                    # print(f"⏳ {label} en {area_name} desaparecerá en {tiempo_restante:.2f} segundos...")
                    pass
                else:
                    print(f"❌ {label} salió de {area_name}, quitando color y reiniciando tiempo.")
                    del self.tiempo_deteccion_por_area[(area_name, label)]  # 🔥 Solo se borra después de 4s
                    del self.tiempo_ultimo_detecciones[(area_name, label)]


    
    

# ------------- guardar_evento

    def guardar_evento(self, area_name, label, nombre_camera, sitio):
        """Guarda un evento en la base de datos."""
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
            NombreLabel = label  # Asignación de valor para evitar el error
            descript = f"Se detectó {label} en {area_name} en la cámara {nombre_camera}"
        
        self.add_event_to_database(
            sitio=sitio,
            company="TechCorp",
            fecha=fecha_actual,
            hora=hora_actual,
            tipo_evento=f"Detección de {NombreLabel} en {area_name} en la cámara {nombre_camera}",
            descripcion=descript
        )
        
        id_registro = self.get_last_event_id()
        set_id(id_registro)

    def add_event_to_database(self,sitio, company, fecha, hora, tipo_evento, descripcion):
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

    def guardar_evidencia(self, frame, area_name, label, nombre_camera, info_notifications, emails):
        """Guarda video o imagen como evidencia según configuración."""
        if info_notifications.get('Video'):
            buffer = self.buffer_detecciones[self.camera_id]
            save_video_from_buffer(buffer, f"videos_{area_name}_{label}_{nombre_camera}.mp4", info_notifications.get('Email'), emails)
        elif info_notifications.get('Imagen'):
            nombre_img = f"Imgs/img_{area_name}_{label}_{nombre_camera}.jpg"
            os.makedirs(os.path.dirname(nombre_img), exist_ok=True)
            cv2.imwrite(nombre_img, frame)
            guardar_imagen_en_mariadb(nombre_img, info_notifications.get('Email'), emails)

    def actualizar_buffer(self, frame):
        """Añade el frame al buffer de detecciones compartido."""
        hola = 0
        buffer = self.buffer_detecciones[self.camera_id]
        if len(buffer) >= 120:
            buffer.pop(0)
        buffer.append(frame)
        if self.camera_id == 1:
            # print(f"Buffer {self.camera_id} después de agregar: {len(buffer)}")
            hola = 1

    def stop(self):
        """Detiene el procesamiento de detecciones."""
        self.running = False

    def get_last_event_id(self):
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