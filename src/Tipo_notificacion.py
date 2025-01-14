import cv2
import numpy as np
import pymysql

def save_video_from_buffer(frame_buffer, output_file, fps=20):
    """
    Guarda un video MP4 a partir de un buffer de frames.

    :param frame_buffer: Lista de frames (cada frame debe ser una matriz de NumPy).
    :param output_file: Nombre del archivo de salida (debe terminar en .mp4).
    :param fps: Cuadros por segundo del video.
    """
    if not frame_buffer:
        print("El buffer está vacío, no se puede crear el video.")
        return

    # Obtener las dimensiones del primer frame
    height, width, channels = frame_buffer[0].shape

    # Definir el códec y crear el objeto VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Códec para MP4
    out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))

    # Escribir cada frame en el video
    for frame in frame_buffer:
        out.write(frame)

    # Liberar el objeto VideoWriter
    out.release()
    guardar_video_en_mariadb(output_file, output_file)
    print(f"Video guardado como {output_file}")
    
    
def guardar_video_en_mariadb(nombre_archivo, nombre_video, host='10.20.30.33', user='ax_monitor', password='axure.2024', database='hseVideoAnalytics'):
    # Conectar a la base de datos
    conexion = pymysql.connect(host=host, user=user, password=password, database=database)
    
    # try:
    with open(nombre_archivo, 'rb') as archivo_video:
        contenido_video = archivo_video.read()
    
    # Insertar el video en la base de datos
    with conexion.cursor() as cursor:
        sql = "INSERT INTO Notificaciones (Nombre_Archivo, Video_Alerta) VALUES (%s, %s)"
        cursor.execute(sql, (nombre_video, contenido_video))
    
    # Confirmar cambios
    conexion.commit()
    print("Video guardado en la base de datos exitosamente.")
    # except Exception as e:
    #     print("Error al guardar el video:", e)
    # finally:
    #     conexion.close()