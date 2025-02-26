streamers = []
streamers_procesado = []
threads= []
processes = []  
id = 0
envio_correo = True

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