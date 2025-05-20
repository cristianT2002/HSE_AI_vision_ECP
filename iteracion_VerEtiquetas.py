from ultralytics import YOLO

# Cargar el modelo con tus pesos personalizados
model = YOLO('models/best_person_cascos.pt')

# Imprimir las etiquetas definidas en el modelo
print("Etiquetas del modelo:", model.names)
