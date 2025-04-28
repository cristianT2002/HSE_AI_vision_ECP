from twilio.rest import Client

# Tus credenciales de Twilio
ACCOUNT_SID = 'AC743208a5c6a4be7845784bd6a774f06e'
AUTH_TOKEN = 'eb6646dc29d975e7983d6ad810457964'
TWILIO_PHONE_NUMBER = '12543234954'

# Función para enviar un SMS
def enviar_sms(numero_destino, mensaje):
    cliente = Client(ACCOUNT_SID, AUTH_TOKEN)
    
    mensaje_enviado = cliente.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=numero_destino
    )
    
    print(f"Mensaje enviado con SID: {mensaje_enviado.sid}")

# Ejemplo de uso
if __name__ == "__main__":
    numero_destino = '+573012874982'  # Número de destino en formato internacional (ejemplo para Colombia)
    mensaje = '¡Hola Cristian! Este es un mensaje de prueba desde la API de Twilio.'
    enviar_sms(numero_destino, mensaje)
