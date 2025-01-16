import os
from ultralytics import YOLO

# Ruta al modelo fijo
MODEL_PATH = os.path.join("models", "juanmodelo.pt")

# Verifica si el modelo existe
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"No se encontró el modelo en la ruta especificada: {MODEL_PATH}")

# Cargar el modelo una sola vez
model = YOLO(MODEL_PATH)

# Obtener nombres de las etiquetas desde el modelo
LABELS = model.model.names  # Diccionario de etiquetas, e.g., {0: 'A_Person', 1: 'Harness', ...}
