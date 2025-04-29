# Imagen base con soporte CUDA
FROM nvidia/cuda:12.0.0-runtime-ubuntu20.04

# Evita prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive

# Instala Python y utilidades necesarias
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    git \
    && apt-get clean

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia archivos necesarios (exceptuando ent_back_HSE)
COPY certs/ certs/
COPY configs/ configs/
COPY Imgs/ Imgs/
COPY logs/ logs/
COPY models/ models/
COPY outputs/ outputs/
COPY pruebas_realizadas/ pruebas_realizadas/
COPY src/ src/
COPY Videos/ Videos/
COPY VideosEnsayoModelo/ VideosEnsayoModelo/

# También copia el resto de archivos importantes (si los necesitas)
COPY requirements.txt .
COPY app.py .

# Instala dependencias específicas de PyTorch primero
RUN pip3 install --upgrade pip
RUN pip3 install torch==2.0.1+cu117 torchvision==0.15.2+cu117 torchaudio==2.0.2 -f https://download.pytorch.org/whl/cu117/torch_stable.html

# Luego instala el resto de tus dependencias
RUN pip3 install -r requirements.txt

# Ejecuta el programa
CMD ["python3", "app.py"]
