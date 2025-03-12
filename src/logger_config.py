import logging
import os

# Crear la carpeta de logs si no existe
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Configurar el logger
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'eventos.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Filtro personalizado para errores relevantes
class CustomFilter(logging.Filter):
    def filter(self, record):
        return 'Error en mi lógica' in record.getMessage()  # Filtra solo ciertos errores

# Crear logger principal
logger = logging.getLogger(__name__)

# Configurar filtro para que solo guarde los errores relevantes
error_handler = logging.FileHandler(os.path.join(LOG_DIR, 'eventos.log'))
error_handler.setLevel(logging.ERROR)
error_handler.addFilter(CustomFilter())  # Se aplica el filtro
logger.addHandler(error_handler)

# Limitar la verbosidad de werkzeug
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Función para obtener el logger
def get_logger(name):
    return logging.getLogger(name)
