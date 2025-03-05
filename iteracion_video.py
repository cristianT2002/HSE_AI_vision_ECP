# Importamos las librerías
from ultralytics import YOLO
import cv2
import torch
 
# Leer nuestro modelo
# model = YOLO("yolov8n-seg.pt")  # load an official model
model = YOLO("models/best_mejorado.pt")
video = "VideosEnsayoModelo/guantes_amarillos.mp4"
 
# Obtener el nombre de la clase a filtrar (en este caso, "Yellow")
target_label = "Yellow"
target_index = None
for idx, name in model.names.items():
    if name.lower() == target_label.lower():
        target_index = idx
        break
 
if target_index is None:
    raise ValueError(f"No se encontró la etiqueta '{target_label}' en model.names.")
 
# Realizar VideoCaptura
cap = cv2.VideoCapture(video)
 
# Crear una ventana y ajustar su tamaño
cv2.namedWindow("DETECCION Y SEGMENTACION", cv2.WINDOW_NORMAL)
cv2.resizeWindow("DETECCION Y SEGMENTACION", 1080, 750)
 
# Bucle principal
while True:
    # Leer fotogramas
    ret, frame = cap.read()
    if not ret:
        break
 
    # Realizamos la predicción
    resultados = model(frame, verbose=False)
    result = resultados[0]
 
    # Copia del fotograma para dibujar
    annotated_frame = frame.copy()
 
    # Iterar sobre cada detección (caja)
    for box in result.boxes:
        # Verificar si la detección es de la clase "Yellow"
        if int(box.cls.item()) == target_index:
            # Extraer coordenadas (xyxy) y convertir a enteros
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
           
            # Dibujar la caja y la etiqueta
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                annotated_frame,
                target_label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 0),
                2
            )
 
    # Redimensionar el fotograma a 1080x750 píxeles para mostrar
    annotated_frame = cv2.resize(annotated_frame, (1080, 750), interpolation=cv2.INTER_LINEAR)
    cv2.imshow("DETECCION Y SEGMENTACION", annotated_frame)
 
    # Salir presionando la tecla 'ESC'
    if cv2.waitKey(1) == 27:
        break
 
cap.release()
cv2.destroyAllWindows()
 