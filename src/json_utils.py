import os
import json

OUTPUT_JSON = "outputs/output.json"

def generate_json(data):
    """
    Guarda los datos proporcionados en un archivo JSON.
    """
    output_folder = os.path.dirname(OUTPUT_JSON)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    print(f"Archivo JSON generado: {OUTPUT_JSON}")
