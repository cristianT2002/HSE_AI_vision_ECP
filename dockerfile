# Usar una imagen base que tenga tanto Python 3.9 como Node.js 16
FROM nikolaik/python-nodejs:python3.9-nodejs16

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo requirements.txt al contenedor
COPY requirements.txt .

# Instalar las dependencias del proyecto
RUN pip install -r requirements.txt



# Regresar al directorio principal de la aplicación Flask
WORKDIR /app

# Copiar los archivos de la aplicación al contenedor
COPY NUEVO.py .
COPY best_mejorado7.pt .



# Instalar la biblioteca libgl1-mesa-glx
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# Exponer el puerto en el que se ejecutará la aplicación Flask
EXPOSE 8444

# Establecer el comando por defecto para ejecutar la aplicación Flask
CMD ["sh", "-c", "python NUEVO.py"]
