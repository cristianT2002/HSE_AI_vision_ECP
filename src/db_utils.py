import mysql.connector

def connect_to_db(config):
    """
    Conecta a la base de datos MySQL utilizando la configuración proporcionada.
    """
    try:
        connection = mysql.connector.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database_name"]
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error al conectar a la base de datos: {err}")
        raise

def close_connection(connection):
    """
    Cierra la conexión a la base de datos.
    """
    if connection.is_connected():
        connection.close()
