import cv2
import numpy as np
import pymysql
from src.variables_globales import get_streamers, set_streamers, set_id, get_id, get_envio_correo, set_envio_correo
import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import io
from twilio.rest import Client

from src.logger_config import get_logger
# Función para enviar correos
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

logger = get_logger(__name__)


def save_video_from_buffer(frame_buffer, output_file, envio_correo, lista_emails, fps=20):
    """
    Guarda un video MP4 a partir de un buffer de frames en una carpeta llamada 'Videos'.
    Si el nombre del archivo ya existe, agrega un sufijo numérico para evitar sobrescribirlo.

    :param frame_buffer: Lista de frames (cada frame debe ser una matriz de NumPy).
    :param output_file: Nombre del archivo de salida (debe terminar en .mp4).
    :param envio_correo: Booleano para decidir si se envía un correo.
    :param lista_emails: Lista de correos electrónicos.
    :param fps: Cuadros por segundo del video.
    """
    if not frame_buffer:
        print("El buffer está vacío, no se puede crear el video.")
        return

    # Crear la carpeta 'Videos' si no existe
    videos_dir = os.path.join(os.getcwd(), "Videos")
    os.makedirs(videos_dir, exist_ok=True)

    # Construir la ruta inicial del archivo
    base_name, extension = os.path.splitext(output_file)
    output_path = os.path.join(videos_dir, output_file)

    # Verificar si el archivo ya existe y agregar un sufijo numérico si es necesario
    counter = 1
    while os.path.exists(output_path):
        output_file = f"{base_name}_{counter}{extension}"
        output_path = os.path.join(videos_dir, output_file)
        counter += 1

    # Obtener las dimensiones del primer frame
    height, width, channels = frame_buffer[0].shape

    # Definir el códec y crear el objeto VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Códec para MP4
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Escribir cada frame en el video
    for frame in frame_buffer:
        out.write(frame)

    # Liberar el objeto VideoWriter
    out.release()

    # Llamar a la función para guardar el video en la base de datos y enviar correos
    guardar_video_en_mariadb(output_path, output_path, envio_correo, lista_emails)
    print(f"Video guardado como {output_path}")
    
def borrar_primer_registro(host='10.20.30.33', user='ax_monitor', password='axure.2024', database='hseVideoAnalytics'):
    # Conectar a la base de datos
    conexion = pymysql.connect(host=host, user=user, password=password, database=database, cursorclass=pymysql.cursors.DictCursor)
    
    try:
        with conexion.cursor() as cursor:
            # Obtener el ID del primer registro (más antiguo) en Notificaciones
            sql_select = "SELECT id_notificacion, id_evento FROM Notificaciones ORDER BY id_notificacion ASC LIMIT 1"
            cursor.execute(sql_select)
            resultado = cursor.fetchone()
            
            if resultado:
                id_a_borrar = resultado['id_notificacion']
                id_a_borrar_evento = resultado['id_evento']
                print(f"ID del primer registro a eliminar: {id_a_borrar}")
                print(f"ID del evento asociado a eliminar: {id_a_borrar_evento}")
                
                # Borrar el registro en Notificaciones
                sql_delete_notificaciones = "DELETE FROM Notificaciones WHERE id_notificacion = %s"
                cursor.execute(sql_delete_notificaciones, (id_a_borrar,))
                
                # Borrar el registro en Eventos
                sql_delete_eventos = "DELETE FROM Eventos WHERE id_evento = %s"
                cursor.execute(sql_delete_eventos, (id_a_borrar_evento,))
                
                # Confirmar cambios
                conexion.commit()
                print(f"Registro con ID {id_a_borrar} en Notificaciones y evento con ID {id_a_borrar_evento} en Eventos eliminados exitosamente.")
            else:
                print("No hay registros en la tabla Notificaciones.")
    except Exception as e:
        print("Error al borrar el primer registro:", e)
    finally:
        conexion.close()

    
def guardar_video_en_mariadb(nombre_archivo, nombre_video, envio_correo, lista_emails, host='10.20.30.33', user='ax_monitor', password='axure.2024', database='hseVideoAnalytics'):
    # Conectar a la base de datos
    conexion = pymysql.connect(host=host, user=user, password=password, database=database, cursorclass=pymysql.cursors.DictCursor)
    ultimo_registro = get_id()
    
    # Contar el número de registros en la tabla Notificaciones
    with conexion.cursor() as cursor:
        sql_count = "SELECT COUNT(*) AS total_registros FROM Notificaciones"
        cursor.execute(sql_count)
        resultado_count = cursor.fetchone()
        total_registros = resultado_count['total_registros']
    
    print(f"Total de registros en la tabla Notificaciones: {total_registros}")
    
    # Verificar si el número de registros es mayor a 30
    if total_registros > 15:
        print("Se ha alcanzado el límite de registros en la tabla Notificaciones.")
        # Llamar a la función
        borrar_primer_registro()
    
    try:
        # Obtener el último registro con el ID de get_id()
        id_a_buscar = get_id()
        with conexion.cursor() as cursor:
            # Consultar los datos del registro con el ID
            sql_select = "SELECT * FROM Eventos WHERE id_evento = %s"
            cursor.execute(sql_select, (id_a_buscar,))
            resultado = cursor.fetchone()
            
            if resultado:
                
                print("Datos del registro:", resultado)
                # Actualizar los datos del registro
                fecha_notification = resultado['fecha']
                mensaje_notification = resultado['descripcion']
                estado_notification = 'pendiente'
                sitio_notificacion = resultado['sitio']
                company_notificacion = resultado['company']
                with open(nombre_archivo, 'rb') as archivo_video:
                    contenido_video = archivo_video.read()
                
                # nombre_archivo_video = os.path.basename(nombre_archivo)
                print("NOmbre del video: ",nombre_archivo)
                # Insertar el video en la base de datos
                with conexion.cursor() as cursor:
                    sql = "INSERT INTO Notificaciones (id_evento, fecha_envio, mensaje, estado, Nombre_Archivo, Video_Alerta) VALUES (%s,%s, %s,%s,%s, %s)"
                    cursor.execute(sql, (id_a_buscar, fecha_notification, mensaje_notification, estado_notification,nombre_archivo, contenido_video))
                
                # Confirmar cambios
                conexion.commit()
                print("Video guardado en la base de datos exitosamente.")
                logger.warning("Video guardado en la base de datos exitosamente.")
                if envio_correo == True:
                    if get_envio_correo() == True:
                        send_email_with_outlook("Add_Video", lista_emails, fecha_notification, mensaje_notification, nombre_archivo, sitio_notificacion, company_notificacion)
                
                # Aquí puedes usar los datos como necesites
            else:
                print(f"No se encontró un registro con ID {id_a_buscar}.")
    except Exception as e:
        print("Error al buscar el registro:", e)
    finally:
        conexion.close()

    
def guardar_imagen_en_mariadb(nombre_archivo, envio_correo, lista_emails, host='10.20.30.33', user='ax_monitor', password='axure.2024', database='hseVideoAnalytics'):
    # Conectar a la base de datos
    conexion = pymysql.connect(host=host, user=user, password=password, database=database, cursorclass=pymysql.cursors.DictCursor)
    
    # Contar el número de registros en la tabla Notificaciones
    with conexion.cursor() as cursor:
        sql_count = "SELECT COUNT(*) AS total_registros FROM Notificaciones"
        cursor.execute(sql_count)
        resultado_count = cursor.fetchone()
        total_registros = resultado_count['total_registros']
    
    print(f"Total de registros en la tabla Notificaciones: {total_registros}")
    
    # Verificar si el número de registros es mayor a 30
    if total_registros > 15:
        print("Se ha alcanzado el límite de registros en la tabla Notificaciones.")
        # Llamar a la función
        borrar_primer_registro()
    
    
    try:
        # Obtener el último registro con el ID de get_id()
        id_a_buscar = get_id()  # Asegúrate de que esta función esté definida
        with conexion.cursor() as cursor:
            # Consultar los datos del registro con el ID
            sql_select = "SELECT * FROM Eventos WHERE id_evento = %s"
            cursor.execute(sql_select, (id_a_buscar,))
            resultado = cursor.fetchone()
            
            if resultado:
                print("Datos del registro:", resultado)
                
                # Extraer datos del registro
                fecha_notification = resultado['fecha']
                mensaje_notification = resultado['descripcion']
                estado_notification = 'pendiente'
                sitio_notificacion = resultado['sitio']
                company_notificacion = resultado['company']
                
                # Leer el contenido de la imagen como binario
                with open(nombre_archivo, 'rb') as archivo_imagen:
                    contenido_imagen = archivo_imagen.read()
                
                print("Nombre de la imagen:", nombre_archivo)
                
                # nombre_archivo = os.path.basename(nombre_archivo)
                # Insertar la imagen en la base de datos
                with conexion.cursor() as cursor:
                    sql = "INSERT INTO Notificaciones (id_evento, fecha_envio, mensaje, estado, Nombre_Archivo, Imagen_Alerta) VALUES (%s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (id_a_buscar, fecha_notification, mensaje_notification, estado_notification, nombre_archivo, contenido_imagen))
                
                # Confirmar cambios
                conexion.commit()
                print("Imagen guardada en la base de datos exitosamente.")
                logger.warning(f"Imagen guardada en la base de datos exitosamente. ID: {id_a_buscar}")
               
                # Enviar correo si está habilitado
                if envio_correo:
                    if get_envio_correo() == True:
                        send_email_with_outlook("Add_Image", lista_emails, fecha_notification, mensaje_notification, nombre_archivo, sitio_notificacion, company_notificacion)
            else:
                print(f"No se encontró un registro con ID {id_a_buscar}.")
    
    except Exception as e:
        print("Error al guardar la imagen en la base de datos:", e)
    
    finally:
        conexion.close()
    
def recuperar_video_de_mariadb(id_video, string_adicional='', host='10.20.30.33', user='ax_monitor', password='axure.2024', database='hseVideoAnalytics'):
    # Conectar a la base de datos
    conexion = pymysql.connect(host=host, user=user, password=password, database=database)
    
    try:
        with conexion.cursor() as cursor:
            # Consulta para obtener el video y el nombre del archivo
            sql = "SELECT Video_Alerta, Nombre_Archivo FROM Notificaciones WHERE id_notificacion = %s"
            cursor.execute(sql, (id_video,))
            resultado = cursor.fetchone()
            
            if resultado:
                video_data = resultado[0]  # Contenido del video
                nombre_archivo = resultado[1]  # Nombre del archivo
                
                # Agregar el string adicional al nombre del archivo antes de la extensión
                nombre_base, extension = nombre_archivo.rsplit('.', 1)
                nuevo_nombre_archivo = f"{nombre_base}_{string_adicional}.{extension}"
                
                # Guardar el video con el nuevo nombre
                with open(nuevo_nombre_archivo, 'wb') as archivo_salida:
                    archivo_salida.write(video_data)
                print(f"Video recuperado y guardado como {nuevo_nombre_archivo}.")
            else:
                print("No se encontró un video con ese ID.")
    except Exception as e:
        print("Error al recuperar el video:", e)
    finally:
        conexion.close()



# Recuperar y guardar el video desde la base de datos
# recuperar_video_de_mariadb(7, 'recuperado')


def send_email_with_outlook(img_or_video, destinatario, fecha, mensaje, nombre_archivo, sitio_notificacion, company_notificacion):
    # Configuración del servidor SMTP de Office 365
    smtp_server = 'smtp.office365.com'
    smtp_port = 587
    username = 'apic.rto@axuretechnologies.com'
    password = '4xUR3_2017'

    # Dirección de correo del remitente
    from_address = 'apic.rto@axuretechnologies.com'

    if isinstance(destinatario, list):
        to_address_display = ', '.join(destinatario)  # Para mostrar en el encabezado
        to_address = destinatario  # Mantenerlo como lista para sendmail
    else:
        to_address_display = destinatario
        to_address = [destinatario]  # Convertirlo en lista para sendmail

    print("destinatarios: ", destinatario)
    # Asunto y cuerpo del correo
    subject = "Alerta Detectada en HSE-Video-Analytics"
    # Crear el objeto del mensaje
    msg = MIMEMultipart()
    msg['From'] = from_address
    msg['To'] = to_address_display
    msg['Subject'] = subject

    body_template = f"""
        <html>
        <body>
            <p><b>Evento Detectado:</b> {mensaje}</p>
            <p><strong>Sitio:</strong> {sitio_notificacion}</p>
            <p><strong>Empresa:</strong> {company_notificacion}</p>
            <p><strong>Fecha:</strong> {fecha}</p>
            <br>
            <p>Por favor, revise los detalles del evento y tome las acciones necesarias.</p>
            <p><b>Favor Descargar el archivo adjunto.</b></p>
        </body>
        </html>
    """
    # Agregar el cuerpo del mensaje al correo
    msg.attach(MIMEText(body_template, 'html'))

    try:
        if img_or_video == "Add_Video":
            # Adjuntar el video al correo
            with open(nombre_archivo, 'rb') as attachment:
                part = MIMEBase('video', 'mp4')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{nombre_archivo}"')
            msg.attach(part)
            print('Video adjuntado exitosamente.')
            logger.info("Video adjuntado exitosamente.")

        elif img_or_video == "Add_Image":
            # Adjuntar la imagen al correo
            with open(nombre_archivo, 'rb') as attachment:
                part = MIMEBase('image', 'jpeg')  # Cambia 'jpeg' según el formato (e.g., 'png', 'gif')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{nombre_archivo}"')
            msg.attach(part)
            print('Imagen adjuntada exitosamente.')
            logger.info("Imagen adjuntada exitosamente.")

        # Conectar al servidor SMTP y enviar el correo
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Habilitar el modo seguro (TLS)
        server.login(username, password)
        server.sendmail(from_address, to_address, msg.as_string())
        print('Correo enviado exitosamente.')
        logger.warning("Correo enviado exitosamente.")
        set_envio_correo(False)

    except Exception as e:
        print('Error al enviar el correo:', e)
        logger.error(f"Error al enviar el correo: {e}")

    finally:
        # Cerrar la conexión con el servidor
        server.quit()


def send_sms_with_twilio(mensaje, fecha, company_notificacion, sitio_notificacion, destinatario):
    # Credenciales de Twilio
    account_sid = 'US435484b16fe8d64c9d71a905dd53c7f2'
    auth_token = 'TU_AUTH_TOKEN'
    twilio_phone_number = 'TU_NUMERO_TWILIO'  # Ejemplo: "+1234567890"

    # Crear cliente de Twilio
    client = Client(account_sid, auth_token)

    # Mensaje de texto
    sms_body = (
        f"🚨 Alerta Detectada 🚨\n"
        f"Evento: {mensaje}\n"
        f"Fecha: {fecha}\n"
        f"Empresa: {company_notificacion}\n"
        f"Sitio: {sitio_notificacion}\n"
        f"Por favor, tome las medidas necesarias."
    )

    try:
        # Enviar mensaje
        message = client.messages.create(
            body=sms_body,
            from_=twilio_phone_number,
            to=destinatario  # Número del destinatario (ejemplo: "+573001234567")
        )
        print(f"Mensaje enviado exitosamente. SID: {message.sid}")
    except Exception as e:
        print(f"Error al enviar el mensaje: {e}")
