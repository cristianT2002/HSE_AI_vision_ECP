from ultralytics import YOLO

# Cargar el modelo con tus pesos personalizados
model = YOLO('models/best.pt')

# Imprimir las etiquetas definidas en el modelo
print("Etiquetas del modelo:", model.names)
