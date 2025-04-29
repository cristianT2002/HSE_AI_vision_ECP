HSE Video Analytics - Ejecución en Docker con soporte GPU

Este documento explica paso a paso cómo preparar una máquina Ubuntu para correr aplicaciones Docker con aceleración NVIDIA GPU, como el proyecto hse_video_analytics_ecp.

1. Instalar drivers NVIDIA en el host

Asegúrate de tener los drivers de NVIDIA instalados en tu sistema:

sudo apt update
sudo apt install -y nvidia-driver-525  # O una versión equivalente o más reciente
sudo reboot

Verifica la instalación:

nvidia-smi

Deberías ver la información de tu GPU (por ejemplo, "RTX 4060").

2. Instalar Docker

Instala Docker siguiendo estos comandos:

sudo apt update
sudo apt install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker

Verifica que Docker esté activo:

docker version

3. Instalar nvidia-container-toolkit

Esto permite a Docker acceder a la GPU.

# 1. Agregar repositorio NVIDIA
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

ARCH=amd64
echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/ubuntu22.04/${ARCH} /" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Instalar toolkit
sudo apt update
sudo apt install -y nvidia-container-toolkit

# 3. Configurar Docker para usar NVIDIA como runtime
sudo nano /etc/docker/daemon.json

Pegar dentro de daemon.json:

{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}

Luego reinicia Docker:

sudo systemctl restart docker

4. Verificar que Docker ve la GPU

Prueba este comando:

docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi

Deberías ver tu GPU desde dentro del contenedor.

5. Construir la imagen del proyecto

Posiciónate en el directorio del proyecto:

cd /home/axure/Documents/HSE_AI_vision_ECP

Construye la imagen:

docker build -t hse_video_analytics_ecp .

6. Correr el proyecto usando la GPU

Ejecuta el contenedor usando --gpus all y --network host para acceder a dispositivos de red reales:

docker run --gpus all -it --rm --network host --name hse_video_analytics_ecp_py hse_video_analytics_ecp

Notas:

--gpus all asigna todas las GPUs disponibles.

--network host permite acceso a las IP reales de red y dispositivos como cámaras.

7. Recomendaciones adicionales

Dentro de tu aplicación Flask, asegúrate de lanzar el servidor en:

app.run(host="0.0.0.0", port=5000)

Para verificar que PyTorch reconoce la GPU dentro del contenedor:

import torch
print(torch.cuda.is_available())  # Debería imprimir True
print(torch.cuda.get_device_name(0))  # Nombre de tu GPU

8. Resumen de Comandos Exitosos Clave

sudo apt install -y nvidia-driver-525
sudo apt install -y docker.io

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/ubuntu22.04/amd64 /" | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi

docker build -t hse_video_analytics_ecp .
docker run --gpus all -it --rm --network host --name hse_video_analytics_ecp_py hse_video_analytics_ecp

Listo 🚀

Con esto, tu proyecto corre en Docker usando tu GPU NVIDIA de forma exitosa.