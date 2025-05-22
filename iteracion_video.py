from ultralytics import YOLO
import cv2

# —————— 1. Carga del modelo y vídeo ——————
model = YOLO("models/best.pt")
video_path = "VideosEnsayoModelo/muchas-personas-perimetral2.mp4"

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError(f"No se puede abrir el vídeo: {video_path}")

cv2.namedWindow("DETECCIÓN Y SEGMENTACIÓN", cv2.WINDOW_NORMAL)
cv2.resizeWindow("DETECCIÓN Y SEGMENTACIÓN", 1080, 750)

# —————— 2. Bucle de procesamiento ——————
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Ejecuta inferencia (detección + segmentación si aplica)
    results = model(frame, verbose=False)
    res = results[0]

    # ——— Opción A: Con el método plot() ———
    #     Dibuja cajas, máscaras y etiquetas automáticamente
    annotated = res.plot()

    # ——— Opción B: Dibujo manual de cajas + etiquetas ———
    # uncomment para usar esta sección en lugar de plot()
    # annotated = frame.copy()
    # for box in res.boxes:
    #     cls_id = int(box.cls.item())
    #     label = model.names[cls_id]                    # nombre de la clase
    #     x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
    #     # Caja
    #     cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
    #     # Texto (etiqueta)
    #     cv2.putText(
    #         annotated, label,
    #         (x1, y1 - 10),
    #         cv2.FONT_HERSHEY_SIMPLEX, 0.9,
    #         (0, 255, 0), 2,
    #         cv2.LINE_AA
    #     )

    # Mostrar el resultado redimensionado
    annotated = cv2.resize(annotated, (1080, 750), interpolation=cv2.INTER_LINEAR)
    cv2.imshow("DETECCIÓN Y SEGMENTACIÓN", annotated)

    # Salir con ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
