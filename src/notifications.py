import time
import os 
import json
from datetime import datetime
import cv2
from src.load_config import load_yaml_config
from src.model_loader import model, LABELS
from src.variables_globales import get_streamers

def procesar_detecciones(config_path, camera_id):
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
    except Exception as e:
        print(f"Error al cargar configuración: {e}")
        return

    # Variables para el seguimiento de detecciones
    tiempo_deteccion_por_area = {}
    target_width, target_height = 640, 380  # Resolución deseada

    # Obtener buffer de frames
    streamers = get_streamers()
    info_buffer = streamers[camera_id]

    while True:
        frame_to_process = None

        with info_buffer.buffer_lock:
            if info_buffer.frame_buffer:
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

                    start_point = (int(x1), int(y1))
                    end_point = (int(x1 + rect_width1), int(y1 + rect_height1))

                    # Procesar el frame con el modelo
                    results = model(frame, verbose=False)

                    for detection in results[0].boxes:
                        try:
                            # Obtener coordenadas, probabilidad y etiqueta
                            x1_det, y1_det, x2_det, y2_det = map(int, detection.xyxy[0])
                            probability = detection.conf[0] * 100
                            class_index = int(detection.cls[0]) if hasattr(detection, 'cls') else -1
                            label = LABELS.get(class_index, "Unknown")

                            # Verificar si la detección está dentro del área y cumple con la probabilidad
                            if start_point[0] <= x1_det <= end_point[0] and start_point[1] <= y1_det <= end_point[1]:
                                min_probability = float(area_config.get(label, 0))

                                if probability >= min_probability:
                                    now = time.time()

                                    # Verificar tiempo acumulado
                                    if (area_name, label) not in tiempo_deteccion_por_area:
                                        tiempo_deteccion_por_area[(area_name, label)] = now
                                    else:
                                        tiempo_acumulado = now - tiempo_deteccion_por_area[(area_name, label)]
                                        if tiempo_acumulado >= tiempos_limite.get(area_name, 5):
                                            print(f"Detección confirmada en {area_name}: {label} - {probability:.2f}% "
                                                  f"por {tiempo_acumulado:.2f} segundos")
                                            # Reiniciar el tiempo acumulado
                                            tiempo_deteccion_por_area[(area_name, label)] = time.time()

                                    # Imprimir la detección
                                    print(f"Detección en {area_name}: {label} - {probability:.2f}%")

                        except Exception as detection_error:
                            print(f"Error al procesar una detección en {area_name}: {detection_error}")
                except Exception as area_error:
                    print(f"Error al procesar {area_name}: {area_error}")

if __name__ == "__main__":
    camera_id = 1  # Cambiar según la cámara deseada
    config_path = f"configs/camera_{camera_id}.yaml"

    if not os.path.exists(config_path):
        print(f"No se encontró el archivo YAML para la cámara {camera_id}.")
    else:
        procesar_detecciones(config_path, camera_id)
