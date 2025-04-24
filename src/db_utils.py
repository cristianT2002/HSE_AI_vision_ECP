import psycopg2
import psycopg2.extras

def connect_to_db(config):
    """
    Conecta a la base de datos PostgreSQL utilizando la configuración proporcionada.
    """
    try:
        connection = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database_name"]
        )
        return connection
    except psycopg2.Error as err:
        print(f"❌ Error al conectar a la base de datos PostgreSQL: {err}")
        raise

def close_connection(connection):
    """
    Cierra la conexión a la base de datos.
    """
    if connection:
        connection.close()