import os
import cv2
from ultralytics import YOLO

# Ruta al modelo fijo
MODEL_PATH = os.path.join("models", "best_mejorado.pt")

# Cargar el modelo una sola vez
model = YOLO(MODEL_PATH)

# Obtener nombres de las etiquetas desde el modelo
LABELS = model.model.names  # Diccionario de etiquetas, e.g., {0: 'A_Person', 1: 'Harness', ...}

# Umbral de confianza (probabilidad) deseado
confidence_threshold = 0.70
# Abrir el video (puedes cambiar "video.mp4" por la ruta de tu video o usar 0 para la webcam)
video_path = "VideosEnsayoModelo/guantes_amarillos.mp4"
cap = cv2.VideoCapture(video_path)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Realizar la detección en el frame
    results = model(frame)

    # Iterar sobre los resultados (normalmente hay un resultado por frame)
    for result in results:
        # Iterar sobre cada detección (bounding box)
        for box in result.boxes:
            # Obtener la confianza y verificar si cumple con el umbral
            conf = box.conf.item()
            if conf < confidence_threshold:
                continue  # Se omite la detección si la confianza es menor al umbral

            # Extraer las coordenadas del bounding box y convertir a enteros
            coords = box.xyxy.cpu().numpy().flatten()
            x1, y1, x2, y2 = map(int, coords)
            # Obtener el índice de la clase
            cls = int(box.cls.item())
            print("Clase: ",cls)
            # Obtener la etiqueta correspondiente
            label = LABELS.get(cls, str(cls)) if isinstance(LABELS, dict) else LABELS[cls]
            
            if label == "Yellow":
                print("Yellow sobre: ", conf)
            # Dibujar el rectángulo y la etiqueta en el frame
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Mostrar el frame con las detecciones
    cv2.imshow("Detecciones", frame)
    
    # Salir si se presiona la tecla 'ESC'
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()