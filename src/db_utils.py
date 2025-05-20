import psycopg2
import psycopg2.extras

def connect_to_db(config, entorno):
    """
    Conecta a la base de datos PostgreSQL utilizando la configuración proporcionada.
    """
    
    # 1) Elijo el nombre de la DB según entorno
    if entorno == "production":
        dbname = config["database_prod"]
    else:
        dbname = config["database_dev"]
    
    try:
        connection = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=dbname
        )
        return connection
    except psycopg2.Error as err:
        print(f"❌ Error al conectar a la base de datos PostgreSQL: {err}")
        

def close_connection(connection):
    """
    Cierra la conexión a la base de datos.
    """
    if connection:
        connection.close()