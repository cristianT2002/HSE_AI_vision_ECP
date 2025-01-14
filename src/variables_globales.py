streamers = []
threads= []
id = 0

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