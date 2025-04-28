import os
import time
import socket
import json
import cv2
import numpy as np
import multiprocessing as mp
from multiprocessing import Manager
from datetime import datetime
from src.variables_globales import get_streamers, set_streamers, set_id, set_envio_correo, get_envio_correo
from src.Tipo_notificacion import save_video_from_buffer, guardar_imagen_en_mariadb
from src.db_utils import connect_to_db, close_connection
from src.load_config import load_yaml_config
from src.model_loader import model, LABELS
from src.logger_config import get_logger
import threading

logger = get_logger(__name__)

class ProcesarDetecciones:
    HELMET_LABELS = {"Green", "Yellow", "White", "Black", "Orange", "Brown", "No_Helmet"}
    
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
        self.areas_con_deteccion = {}  # 🔥 Controla si un área tiene detecciones activa
        
        self.tiempos_acumulados = {}  # Almacena la suma de tiempos
        self.contador_salidas = {}  # Almacena la cantidad de veces que salió
        self.tiempos_individuales = {}  # 🔥 Lista de tiempos individuales de cada salida
        # Definir color para detección activa        
        # Definir color para detección activa
        self.COLOR_DETECCION = (0, 0, 255, 50)  # Rojo 
        


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
            "Yellow": (0, 225, 225),  # Amarillo
            "Loading_Machine": (0, 100, 19),  # Verde Oscuro
            "Mud_Bucket": (255, 171, 171),  # Rosa Suave
            "Orange": (0, 128, 255),  # Naranja
            "gloves": (61, 223, 43),  # Rojo
            "Black": (0, 200, 200),
            "Brown": (100, 100, 100),
        }

     #---------------------AÑADI-------------------------------------------------------------------------------------------------------------------------------------------------------------------------   
    def get_head_region(self, person_box, fraction=0.40, offset=0):
        x1, y1, x2, y2 = person_box
        y1_adjusted = max(0, y1 - offset)
        adjusted_height = y2 - y1_adjusted
        head_height = int(adjusted_height * fraction)
        return (x1, y1_adjusted, x2, y1_adjusted + head_height)
    
    #---------------------AÑADI------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def compute_iou(self, boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        interArea = max(0, xB - xA) * max(0, yB - yA)
        areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        union = areaA + areaB - interArea
        return interArea / union if union > 0 else 0
    #---------------------AÑADI-------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    def is_inside(self, inner_box, outer_box):
        x1, y1, x2, y2 = inner_box
        X1, Y1, X2, Y2 = outer_box
        return (x1 >= X1) and (y1 >= Y1) and (x2 <= X2) and (y2 <= Y2)




   #-------------------------------------------Procesar cambiando fabian----------------------------------------------------------
    def procesar(self):
        host_ip = "172.30.37.67"
        feed_url = f"http://{host_ip}:5000/video_feed/{self.camera_id}"
        # (opcional) self.save_feed_url_to_database(self.camera_id, feed_url)

        while self.running:
            now = time.time()

            # ——— cargar configuración ———
            try:
                self.config = load_yaml_config(self.config_path)
                areas = self.config["camera"]["coordinates"]
                tiempos_limite = json.loads(self.config["camera"]["time_areas"])
                if isinstance(tiempos_limite, str):
                    tiempos_limite = json.loads(tiempos_limite)
                tiempos_limite = {k: float(v) for k,v in tiempos_limite.items()}

                sitio = self.config['camera']["point"]
                nombre_camera = self.config['camera']["name camera"]
                info_notifications = self.config['camera']["info_notifications"]
                if info_notifications:
                    info_notifications = json.loads(info_notifications)
                    
                # emails = self.config['camera']["info_emails"]
                emails = json.loads(json.dumps(["fabianmartinezr867@gmail.com"]))
            
            except Exception as e:
                print(f"Error al cargar configuración: {e}")
                return

            # ——— obtener frame ———
            frame_buffer = self.shared_buffers.get(self.camera_id, None)
            if not frame_buffer:
                time.sleep(0.05)
                continue
            try:
                frame = cv2.resize(frame_buffer[0], (640, 380))
            except Exception:
                time.sleep(0.05)
                continue

            # ——— inferencia ———
            results = model(frame, verbose=False)
            detections = results[0].boxes

            # 1) extraer todas las personas
            self.person_boxes = []
            for det in detections:
                lab = LABELS.get(int(det.cls[0]))
                if lab == "A_Person":
                    x1, y1, x2, y2 = map(int, det.xyxy[0])
                    self.person_boxes.append((x1, y1, x2, y2))

            # 2) procesar cada área según JSON
            for area_name, area_config in areas.items():
                pts = self.escalar_puntos(area_config)

                # **color específico por área**
                if area_name == "area3":
                    polygon_color = (0, 255, 0)
                elif area_name == "area2":
                    polygon_color = (255, 255, 0)
                else:
                    polygon_color = (255, 0, 0)

                cv2.polylines(frame, [pts], isClosed=True, color=polygon_color, thickness=2)

                # etiquetas válidas en BD
                allowed = [
                    k for k in area_config.keys()
                    if k not in ("points","camara","punto")
                ]

                for det in detections:
                    cls = int(det.cls[0])
                    lab = LABELS.get(cls)

                    #  persona pura
                    if lab == "A_Person" and "A_Person" in allowed:
                        self.procesar_deteccion_2(
                            det, area_name, area_config, tiempos_limite,
                            frame, sitio, nombre_camera,
                            info_notifications, emails, pts
                        )
                        continue

                    # b) casco: sólo si A_Person está permitida y hay al menos una persona
                    if "A_Person" in allowed and self.person_boxes \
                    and lab in self.HELMET_LABELS and lab in allowed:

                        x1, y1, x2, y2 = map(int, det.xyxy[0])
                        box = (x1, y1, x2, y2)
                        for pb in self.person_boxes:
                            head_box = self.get_head_region(pb, fraction=0.25, offset=5)
                            if self.compute_iou(box, head_box) >= 0.1:
                                self.procesar_deteccion_2(
                                    det, area_name, area_config, tiempos_limite,
                                    frame, sitio, nombre_camera,
                                    info_notifications, emails, pts,
                                    override_label=lab
                                )
                                break

                     # Todas las demás etiquetas configuradas me las muestra sin ningun problema, que esten en la base de datos claramente
                    if lab in allowed and lab not in self.HELMET_LABELS:
                        self.procesar_deteccion_2(
                            det, area_name, area_config, tiempos_limite,
                            frame, sitio, nombre_camera,
                            info_notifications, emails, pts
                        )
            # ——— reset detecciones inactivas ———
            umbral = 4
            for key, last_ts in list(self.tiempo_ultimo_detecciones.items()):
                if now - last_ts > umbral:
                    print(f"⏹️ Reiniciando {key} tras {now-last_ts:.1f}s inactivo")
                    self.tiempo_ultimo_detecciones.pop(key, None)
                    self.tiempo_deteccion_por_area.pop(key, None)

            # ——— guardar buffer y dormir ———
            self.actualizar_buffer(frame)
            time.sleep(0.01)
 
#-------------------------------------------- ORIGINAL PROCESAR IP CAMBIOS DE MARZO  -----------------------------------------------------------------------------------------------------------------

    # def procesar(self):
    #     # host_ip = socket.gethostbyname(socket.gethostname())
    #     host_ip = "172.30.37.67"
    #     feed_url = f"http://{host_ip}:5000/video_feed/{self.camera_id}"

    #     # Guardar la URL del video feed en la base de datos
    #     # self.save_feed_url_to_database(self.camera_id, feed_url)

    #     while self.running:
    #         now = time.time()
    #         # print("Buffer antes de todo: ", self.buffer_detecciones)
            
    #         # Cargar configuración
    #         try:
    #             self.config = load_yaml_config(self.config_path)
    #             rtsp_url = self.config["camera"]["rtsp_url"]
    #             areas = self.config["camera"]["coordinates"]
    #             tiempos_limite = json.loads(self.config["camera"]["time_areas"])

    #             # Convertir valores de tiempos_limite a float
    #             tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
    #             # Convertir valores de tiempos_limite a float
    #             if isinstance(tiempos_limite, str):
    #                 tiempos_limite = json.loads(tiempos_limite)  # Convertir JSON si es una cadena
    #             tiempos_limite = {key: float(value) for key, value in tiempos_limite.items()}
                
    #             sitio = self.config['camera']["point"]
    #             nombre_camera = self.config['camera']["name camera"]
    #             info_notifications = self.config['camera']["info_notifications"]
    #             if info_notifications:
    #                 try:
    #                     info_notifications = json.loads(info_notifications)
    #                     # print(info_notifications)
    #                 except json.JSONDecodeError as e:
    #                     print(f"Error decodificando JSON de notificaciones: {e}")
                        
    #             #-----------------------enviar correo a todos en base de datos linea247-----------------------------
    #             # emails = self.config['camera']["info_emails"]
    #             emails = json.dumps(["fabianmartinezr867@gmail.com"])  # Esto genera un string JSON válido
    #             # print(f'formato de emails: {emails}')

    #             if emails:
    #                 try:
    #                     emails = json.loads(emails)
    #                     # print(emails)
    #                 except json.JSONDecodeError as e:
    #                     print(f"Error decodificando JSON de correos: {e}")
    #         except Exception as e:
    #             print(f"Error al cargar configuración: {e}")
    #             return

    #         # Variables para el seguimiento de detecciones
    #         target_width, target_height = 640, 380  # Resolución deseada

    #         # Obtener buffer de frames
    #         frame_buffer = self.shared_buffers.get(self.camera_id, None)

    #         if not frame_buffer:
    #             time.sleep(0.05)
    #             continue

    #         try:
    #             frame_to_process = frame_buffer[0]  # Último frame en el buffer
    #         except IndexError:
    #             print(f"⚠️ Error: Intento de acceder a un frame inexistente en notifications {self.camera_id}")
    #             time.sleep(0.05)
    #             continue
            
    #         frame = cv2.resize(frame_to_process, (target_width, target_height))

    #         for area_name, area_config in areas.items():
    #             # try:
    #                 # Procesar el área y realizar detección
    #                 pts = self.escalar_puntos(area_config)
    #                 # Dibujar el polígono escalado en el frame
    #                 if area_name == "area3":
    #                     polygon_color = (0, 255, 0)  # Verde para area2
    #                 elif area_name == "area2":
    #                     polygon_color = (255, 255, 0)
    #                 else:
    #                     polygon_color = (255, 0, 0)  # Rojo o azul para otras áreas (según lo desees)
                    
    #                 # Dibujar el polígono escalado en el frame con el color definido
    #                 cv2.polylines(frame, [pts], isClosed=True, color=polygon_color, thickness=2)

    #                 results = model(frame, verbose=False)

    #                 for detection in results[0].boxes:
    #                     self.procesar_deteccion_2(detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts)

    #             # except Exception as area_error:
    #             #     print(f"Error al procesar {area_name}: {area_error}")

    #         # Guardar frame en buffer de detecciones
    #         self.actualizar_buffer(frame)


# ---------------------------------------- PROCESAR PARA VIDEO EN DIRECTORIO ---------------------------------------

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
    #     print("rtsp  url:", rtsp_url)
    #     if not cap.isOpened():
    #         print("Error al abrir el video con rtsp_url")
    #         return

    #     target_width, target_height = 640, 380  # Resolución deseada

    #     while True:
    #         now = time.time()
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
    #             # ——— RESET de detecciones inactivas ———
    #         umbral = 8.0  # segundos sin ver la detección
    #         # recorremos las claves (area,label) que tenemos activas
    #         for key in list(self.tiempo_ultimo_detecciones.keys()):
    #             last_ts = self.tiempo_ultimo_detecciones[key]
    #             if now - last_ts > umbral:
    #                 print(f"⏹️ Reiniciando detect. {key} tras {now-last_ts:.1f}s sin actualizaciones")
    #                 # borramos el inicio y la última actualización
    #                 self.tiempo_ultimo_detecciones.pop(key, None)
    #                 self.tiempo_deteccion_por_area.pop(key, None)
                        
    #             # Guardar frame en buffer de detecciones
    #             # self.actualizar_buffer(frame)

    #         # Mostrar el frame procesado (opcional)
    #         cv2.imshow("Video", frame)
    #         if cv2.waitKey(1) & 0xFF == ord('q'):
    #             break

    #     cap.release()
    #     cv2.destroyAllWindows()


# ----------------------------------------- GUARDAR URL EN BASE DE DATOS -------------------------------------------------

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

################################## PROCESAR DETECCIONES DE FABIAN ###########################################################
    def procesar_deteccion_2(self, detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts, override_label=None):
        """Procesa una detección específica en el frame y maneja el tiempo de permanencia con margen de 2 segundos."""
        
        x1, y1, x2, y2 = map(int, detection.xyxy[0])
        point = (x1, y1)
        point2 = (int((x1 + x2) / 2), y2)
        probability = detection.conf[0] * 100
        class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
        label = LABELS.get(class_index, "Unknown")


        # label = override_label if override_label is not None else label
        # 2) Si viene override_label, úsalo; si no, la etiqueta que viene del modelo
        label = override_label if override_label is not None else LABELS.get(class_index, "Unknown")


        hora_actual_PS = 0
        tiempo_acumulado2 = 0
        # tiempo_acumulado = 0 # Asegura que siempre exista, incluso si nunca entramos en el else
        límite = 20
        # config_label = override_label if override_label is not None else label
        # if config_label not in area_config:
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
                
                #TIEMPOS LIMITE LINEA 543-----------------------------------------
                if tiempo_acumulado >= 8:
                # if tiempo_acumulado >= tiempos_limite.get(area_name, 5):

                    self.guardar_evento(area_name, label, nombre_camera, sitio, tiempo_acumulado)
                    
                    self.tiempo_deteccion_por_area[(area_name, label)] = time.time()
                    hilo = threading.Thread(target=self.guardar_evidencia, args=( frame, area_name, label, nombre_camera, info_notifications, emails), daemon=True)
                    hilo.start()
                    print(f"🚨 Evento registrado: {label} en {area_name} (Cámara {nombre_camera})")
                    logger.warning(f"Evento registrado: {label} en {area_name} (Cámara {nombre_camera} durante {tiempo_acumulado:.2f}s)")

                hora_actual_PS = datetime.now().strftime("%H:%M:%S")
                print(f"📊 {label} en {area_name} ({nombre_camera}) - {tiempo_acumulado:.2f}s / {tiempos_limite.get(area_name, 5)}s a las {hora_actual_PS}")
                # logger.info(f"{label} en {area_name} ({nombre_camera}) - {tiempo_acumulado:.2f}s / {tiempos_limite.get(area_name, 5)}s a las {hora_actual_PS}")
                print(get_envio_correo())       


            # Si no hay detección, esperar 4s antes de quitar la detección
            if (area_name, label) in self.tiempo_deteccion_por_area:
                tiempo_acumulado2 = time.time() - self.tiempo_deteccion_por_area[(area_name, label)]  # Nuevo cálculo                 
                tiempo_desde_ultima = time.time() - self.tiempo_ultimo_detecciones[(area_name, label)]
                # tiempo_restante = reset_threshold - tiempo_desde_ultima  # Umbral configurable  #-----------------------AÑADI----------------------------------
                tiempo_restante = 3 - tiempo_desde_ultima  # Tiempo restante antes de resetear   #-----------------------ESTO LO COMENTEEEEEEEE---------------------

                if tiempo_restante > 0:
                    pass  # Espera antes de borrar la detección
                else:
                    # 🔥 Guardar el tiempo en el diccionario
                    key = (area_name, label, nombre_camera)
                    
                    if key not in self.tiempos_acumulados:
                        self.tiempos_acumulados[key] = 0
                        self.contador_salidas[key] = 0
                        self.tiempos_individuales[key] = []  # Lista para tiempos individuales
                    
                    self.tiempos_acumulados[key] += tiempo_acumulado2
                    self.contador_salidas[key] += 1
                    self.tiempos_individuales[key].append(tiempo_acumulado2)  # ✅ Ahora sí se guarda el tiempo individual

                    # Calcular promedio
                    promedio = self.tiempos_acumulados[key] / self.contador_salidas[key]

                    print(f"❌ {label} salió de {area_name} en {nombre_camera}, y duró {tiempo_acumulado2:.2f}s")
                    logger.warning(f"{label} salio de {area_name} en {nombre_camera}, y duro {tiempo_acumulado2:.2f}s se pone bandera correo en {get_envio_correo()}")

                    promedio_dict = {}

                    for (area, etiqueta, camara), tiempo_total in self.tiempos_acumulados.items():
                        if camara == nombre_camera:
                            if self.contador_salidas[(area, etiqueta, camara)] > 0:
                                promedio = tiempo_total / self.contador_salidas[(area, etiqueta, camara)]
                                if area not in promedio_dict:
                                    promedio_dict[area] = {}
                                promedio_dict[area][etiqueta] = f"{promedio:.2f}"

                    print(f'Promedio diccionario: {promedio_dict}')

                    self.actualizar_promedio(sitio, nombre_camera, promedio_dict)

                    del self.tiempo_deteccion_por_area[(area_name, label)]
                    del self.tiempo_ultimo_detecciones[(area_name, label)]

                    set_envio_correo(True)
                    print("Bandera set envio correo:", get_envio_correo())


                    
################################## ############################### ###########################################################

################################## PROCESAR DETECCIONES ORIGINAL ###########################################################

#     def procesar_deteccion_2(self, detection, area_name, area_config, tiempos_limite, frame, sitio, nombre_camera, info_notifications, emails, pts):
#             """Procesa una detección específica en el frame y maneja el tiempo de permanencia con margen de 2 segundos."""
            
#             x1, y1, x2, y2 = map(int, detection.xyxy[0])
#             point = (x1, y1)
#             point2 = (int((x1 + x2) / 2), y2)
#             probability = detection.conf[0] * 100
#             class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
#             label = LABELS.get(class_index, "Unknown")
#             hora_actual_PS = 0
#             tiempo_acumulado2 = 0
#             límite = 20


#             if label not in area_config:
#                 return  # No está en las etiquetas configuradas para el área

#             min_probability = float(area_config[label])
#             inside = cv2.pointPolygonTest(pts, point, False)
            
#             if probability < min_probability:
#                 return  # Probabilidad no suficiente
            
#             dentro_del_area = inside >= 0

#             if area_name == "area3":
#                 dentro_del_area = cv2.pointPolygonTest(pts, point2, False) >= 0

#             if dentro_del_area:
#                 # Dibujar detección en el frame
#                 color = self.COLORS.get(label, (255, 255, 255))
#                 text = f"{label}: {probability:.2f}%"
#                 (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
#                 text_offset_x, text_offset_y = x1, y1 - 10
#                 box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 25, text_offset_y + 5))
                
#                 self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
#                 now = time.time()

#                 if (area_name, label) not in self.tiempo_deteccion_por_area:
#                     self.tiempo_deteccion_por_area[(area_name, label)] = now
#                     self.tiempo_ultimo_detecciones[(area_name, label)] = now
#                     print(f"⏳ Inicio detección {label} en {area_name} ({nombre_camera})")
#                 else:
#                     tiempo_acumulado = now - self.tiempo_deteccion_por_area[(area_name, label)]
#                     # Actualizar el tiempo de detección cada vez que se mantenga dentro del área
#                     self.tiempo_ultimo_detecciones[(area_name, label)] = now
#                     tiempo_restante_alerta = tiempos_limite.get(area_name, 5) - tiempo_acumulado
#                     if tiempo_restante_alerta <= 1:
#                         color = (0, 0, 255) # Rojo
                        
#                         # Dibujar detección en el frame con color actualizado
#                         text = f"{label}: {probability:.2f}%"
#                         (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
#                         text_offset_x, text_offset_y = x1, y1 - 10
#                         box_coords = ((text_offset_x, text_offset_y - text_height - 5), (text_offset_x + text_width + 25, text_offset_y + 5))
#                         # Dibujar el polígono en el frame
#                         cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
#                         self.dibujo_etiquetas(frame, text, x1, y1, x2, y2, color, box_coords, text_offset_x, text_offset_y, text_width, text_height)
                    
#                     if tiempo_acumulado >= 10:
#                     # if tiempo_acumulado >= tiempos_limite.get(area_name, 5):

#                         self.guardar_evento(area_name, label, nombre_camera, sitio, tiempo_acumulado)
                        
#                         self.tiempo_deteccion_por_area[(area_name, label)] = time.time()
#                         hilo = threading.Thread(target=self.guardar_evidencia, args=( frame, area_name, label, nombre_camera, info_notifications, emails), daemon=True)
#                         hilo.start()
#                         print(f"🚨 Evento registrado: {label} en {area_name} (Cámara {nombre_camera})")
#                         logger.warning(f"Evento registrado: {label} en {area_name} (Cámara {nombre_camera} durante {tiempo_acumulado:.2f}s)")

#                     hora_actual_PS = datetime.now().strftime("%H:%M:%S")
#                     print(f"📊 {label} en {area_name} ({nombre_camera}) - {tiempo_acumulado:.2f}s / {tiempos_limite.get(area_name, 5)}s a las {hora_actual_PS}")
#                     # logger.info(f"{label} en {area_name} ({nombre_camera}) - {tiempo_acumulado:.2f}s / {tiempos_limite.get(area_name, 5)}s a las {hora_actual_PS}")
#                     print(get_envio_correo())       
#             else:
#                 # Si no hay detección, esperar 4s antes de quitar la detección
#                 if (area_name, label) in self.tiempo_deteccion_por_area:
#                     tiempo_acumulado2 = time.time() - self.tiempo_deteccion_por_area[(area_name, label)]  # Nuevo cálculo                 
#                     tiempo_desde_ultima = time.time() - self.tiempo_ultimo_detecciones[(area_name, label)]
#                     tiempo_restante = 3 - tiempo_desde_ultima  # Tiempo restante antes de resetear

#                     if tiempo_restante > 0:
#                         pass  # Espera antes de borrar la detección
#                     else:
#                         # 🔥 Guardar el tiempo en el diccionario
#                         key = (area_name, label, nombre_camera)
                        
#                         if key not in self.tiempos_acumulados:
#                             self.tiempos_acumulados[key] = 0
#                             self.contador_salidas[key] = 0
#                             self.tiempos_individuales[key] = []  # Lista para tiempos individuales
                        
#                         self.tiempos_acumulados[key] += tiempo_acumulado2
#                         self.contador_salidas[key] += 1
#                         self.tiempos_individuales[key].append(tiempo_acumulado2)  # ✅ Ahora sí se guarda el tiempo individual

#                         # Calcular promedio
#                         promedio = self.tiempos_acumulados[key] / self.contador_salidas[key]

#                         print(f"❌ {label} salió de {area_name} en {nombre_camera}, y duró {tiempo_acumulado2:.2f}s")
#                         logger.warning(f"{label} salio de {area_name} en {nombre_camera}, y duro {tiempo_acumulado2:.2f}s")

#                         promedio_dict = {}

#                         for (area, etiqueta, camara), tiempo_total in self.tiempos_acumulados.items():
#                             if camara == nombre_camera:
#                                 if self.contador_salidas[(area, etiqueta, camara)] > 0:
#                                     promedio = tiempo_total / self.contador_salidas[(area, etiqueta, camara)]
#                                     if area not in promedio_dict:
#                                         promedio_dict[area] = {}
#                                     promedio_dict[area][etiqueta] = f"{promedio:.2f}"

#                         print(f'Promedio diccionario: {promedio_dict}')

#                         self.actualizar_promedio(sitio, nombre_camera, promedio_dict)

#                         del self.tiempo_deteccion_por_area[(area_name, label)]
#                         del self.tiempo_ultimo_detecciones[(area_name, label)]

#                         set_envio_correo(True)

# # ----------------------------------- FUNCIONES SIN MODIFICAR -----------------------
#######
#######
#######
    
#----------------------- Función para guardar tiempos promedio en base de datos, filtrando por PUNTO y NOMBRE DE CAMARA
    def actualizar_promedio(self, sitio, nombre_camera, promedio_dict):
        """Actualiza la base de datos con el promedio de permanencia."""
        connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
        cursor = connection.cursor()

        try:
            promedio_json = json.dumps(promedio_dict)
            update_query = """
                UPDATE IP_Videofeed4
                SET PROMEDIO = %s
                WHERE NOMBRE_CAMARA = %s AND PUNTO = %s
            """
            cursor.execute(update_query, (promedio_json, nombre_camera, sitio))
            connection.commit()
            print(f"✅ Base de datos actualizada para {nombre_camera} en {sitio} con el promedio: {promedio_json}")

        except Exception as e:
            print(f"⚠️ Error al actualizar la base de datos: {e}")

        finally:
            cursor.close()
            close_connection(connection)


    def guardar_evento(self, area_name, label, nombre_camera, sitio, tiempo_acumulado):
        """Guarda un evento en la base de datos, diferenciando casco con/sin persona."""
        fecha_actual = datetime.now().strftime("%d/%m/%Y")
        hora_actual  = datetime.now().strftime("%H:%M:%S")

        # 1) ¿Ese area_name tiene A_Person configurado?
        area_cfg = self.config["camera"]["coordinates"].get(area_name, {})
        has_person_cfg = "A_Person" in area_cfg

        # 2) Casco
        if label in self.HELMET_LABELS:
            if has_person_cfg:
                NombreLabel = f"Persona con casco {label.lower()}"
                descript    = (
                    f"Se detectó una persona con casco {label} "
                    f"en {area_name} en la cámara {nombre_camera} "
                    f"during {tiempo_acumulado:.2f}s"
                )
            else:
                NombreLabel = f"Casco {label.lower()}"
                descript    = (
                    f"Se detectó un casco {label} "
                    f"en {area_name} en la cámara {nombre_camera} "
                    f"during {tiempo_acumulado:.2f}s"
                )
            modelo = label

        # 3) Persona sola
        elif label == "A_Person":
            NombreLabel = "Persona"
            descript    = (
                f"Se detectó una persona en {area_name} "
                f"en la cámara {nombre_camera} "
                f"during {tiempo_acumulado:.2f}s"
            )
            modelo = "Personas"

        # 4) Resto de etiquetas
        else:
            NombreLabel = label
            descript    = (
                f"Se detectó {label} en {area_name} "
                f"en la cámara {nombre_camera} "
                f"during {tiempo_acumulado:.2f}s"
            )
            modelo = label

        # 5) Inserción en BD
        self.add_event_to_database(
            sitio=sitio,
            company="HOCOL",
            fecha=fecha_actual,
            hora=hora_actual,
            tipo_evento=f"Detección de {NombreLabel} en {area_name} en {nombre_camera}",
            descripcion=descript,
            mod=modelo
        )
        id_registro = self.get_last_event_id()
        set_id(id_registro)


# ------------- guardar_evento ORIGINAL-------------------------------------

    # def guardar_evento(self, area_name, label, nombre_camera, sitio, tiempo_acumulado):
    #     """Guarda un evento en la base de datos."""
    #     fecha_actual = datetime.now().strftime("%d/%m/%Y")
    #     hora_actual = datetime.now().strftime("%H:%M:%S")
    #     if label == "A_Person":
    #         NombreLabel = "Personas"
    #         descript = f"Se detectó una Persona en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = "Personas"
    #     elif label == "White":
    #         NombreLabel = "Persona con casco blanco"
    #         descript = f"Se detectó una Persona con casco blanco en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = "Blanco"
    #     elif label == "No_Helmet":
    #         NombreLabel = "Persona Sin casco"
    #         descript = f"Se detectó una Persona sin casco en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = "Sin Casco"        
    #     elif label == "Yellow":
    #         NombreLabel = "Persona con casco Amarillo"
    #         descript = f"Se detectó una Persona con casco Amarillo en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = "Amarillo"        
    #     elif label == "Green":
    #         NombreLabel = "Persona con casco Verde"
    #         descript = f"Se detectó una Persona con casco Verde en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = "Verde"
    #     else:
    #         NombreLabel = label  # Asignación de valor para evitar el error
    #         descript = f"Se detectó {label} en {area_name} en la cámara {nombre_camera} durante {tiempo_acumulado:.2f}s"
    #         modelo = label

    #     self.add_event_to_database(
    #         sitio=sitio,
    #         company="GEOPARK",
    #         fecha=fecha_actual,
    #         hora=hora_actual,
    #         tipo_evento=f"Detección de {NombreLabel} en {area_name} en la cámara {nombre_camera}",
    #         # tipo_evento=f"Detección de {NombreLabel} en {area_name} en la cámara {nombre_camera} en {sitio}",

    #         descripcion=descript,
    #         mod = modelo
    #     )
        
    #     id_registro = self.get_last_event_id()
    #     set_id(id_registro)

    def add_event_to_database(self,sitio, company, fecha, hora, tipo_evento, descripcion, mod):
        """
        Inserta un nuevo registro en la tabla 'eventos' con los valores proporcionados.
        """
        connection = connect_to_db(load_yaml_config("configs/database.yaml")["database"])
        cursor = connection.cursor()

        try:
            insert_query = """
                INSERT INTO Eventos (sitio, company, fecha, hora, tipo_evento, descripcion
                , modelo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (sitio, company, fecha, hora, tipo_evento, descripcion, mod))
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