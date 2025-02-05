# Importamos las librerias
from ultralytics import YOLO
import cv2
import torch
 
# Leer nuestro modelo
# model = YOLO("yolov8n-seg.pt")  # load an official model
model = YOLO("models/best_ultimo.pt")
video = "detectar_carga.mp4"
 
# Realizar VideoCaptura
cap = cv2.VideoCapture(video)
 
# Crear una ventana y ajustar su tamaño
cv2.namedWindow("DETECCION Y SEGMENTACION", cv2.WINDOW_NORMAL)
cv2.resizeWindow("DETECCION Y SEGMENTACION", 1080, 750)
 
# Bucle
while True:
    # Leer nuestros fotogramas
    ret, frame = cap.read()
   
    if not ret:
        break
 
    # Leemos resultados
    resultados = model.predict(frame, imgsz=640, conf=0.20)
 
    # Mostramos resultados
    anotaciones = resultados[0].plot()
 
    # Redimensionar los fotogramas a 1080x750 píxeles
    anotaciones_resized = cv2.resize(anotaciones, (1080, 750), interpolation=cv2.INTER_LINEAR)
 
    # Mostramos nuestros fotogramas
    cv2.imshow("DETECCION Y SEGMENTACION", anotaciones_resized)
 
 
    # Cerrar nuestro programa
    if cv2.waitKey(1) == 27:  # Presionar 'ESC' para salir
        break
 
cap.release()
cv2.destroyAllWindows()
 