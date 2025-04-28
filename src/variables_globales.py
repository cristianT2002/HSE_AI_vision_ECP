import socket

streamers = []
streamers_procesado = []
threads= []
processes = []  
id = 0
envio_correo = True

ip_local = None

def get_streamers():
    return streamers

def get_threads():
    return threads

def set_streamers(streamers_edit):
    global streamers
    streamers = streamers_edit

def set_threads(threads_edit):
    global threads
    threads = threads_edit
    
def get_id():
    global id
    return id

def set_id(id_edit):
    global id
    id = id_edit
    print("el id es: ", id)
    
def set_processes(processes_edit):  # Nueva función para establecer procesos
    global processes
    processes = processes_edit
    
def get_processes():  # Nueva función para obtener procesos
    return processes

def get_streamers_procesado():
    return streamers_procesado

def set_streamers_procesado(streamers_procesado_edit):
    global streamers_procesado
    streamers_procesado = streamers_procesado_edit

def set_envio_correo(envio_correo_edit):
    global envio_correo
    envio_correo = envio_correo_edit    
    
def get_envio_correo():
    return envio_correo

# Función para saber la ip que tiene el equipo
def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return socket.gethostbyname(socket.gethostname())

def get_ip_local():
    global ip_local
    return ip_local

def set_ip_local(ip_local_edit):
    global ip_local
    ip_local = ip_local_edit