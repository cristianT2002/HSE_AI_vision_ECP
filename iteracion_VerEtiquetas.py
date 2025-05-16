from ultralytics import YOLO

# Cargar el modelo con tus pesos personalizados
model = YOLO('models/best_only_person.pt')

# Imprimir las etiquetas definidas en el modelo
print("Etiquetas del modelo:", model.names)
