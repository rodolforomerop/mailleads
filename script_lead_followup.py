
import os
import base64
import json
import requests
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """Inicializa la app de Firebase Admin si no está ya inicializada."""
    if not firebase_admin._apps:
        b64_creds = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if not b64_creds:
            raise ValueError("La variable de entorno FIREBASE_SERVICE_ACCOUNT no está configurada.")
        
        try:
            decoded_creds_str = base64.b64decode(b64_creds).decode('utf-8')
            firebase_creds_dict = json.loads(decoded_creds_str)
            cred = credentials.Certificate(firebase_creds_dict)
            firebase_admin.initialize_app(cred)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise ValueError(f"Error al decodificar o parsear FIREBASE_SERVICE_ACCOUNT: {e}")
            
    return firestore.client()

def send_resend_email(api_key, to_email, imei):
    """Envía el correo de seguimiento usando la API de Resend."""
    if not api_key:
        print(" - RESEND_API_KEY no encontrada. No se puede enviar el correo.")
        return False

    url = "https://api.resend.com/emails"
    
    # Este es el payload que simula la llamada a `sendEmail` desde el backend
    payload = {
        "from": "Registro IMEI Multibanda <registro@registroimeimultibanda.cl>",
        "to": [to_email],
        "subject": "🤔 ¿Olvidaste registrar tu IMEI? Aún estás a tiempo",
        # Aquí replicamos la estructura de la plantilla de React Email
        # Esto es una simplificación. En una app real, podrías tener un servicio de renderizado.
        "html": f"""
            <p>Hola,</p>
            <p>Notamos que hace un tiempo verificaste el IMEI <strong>{imei}</strong> en nuestro sitio y descubriste que necesita ser registrado para operar en Chile.</p>
            <p>¿Tuviste algún problema? No dejes que tu equipo sea bloqueado. El proceso es rápido y garantizado.</p>
            <p><strong><a href="https://registroimeimultibanda.cl/registro-dispositivo?imei={imei}&email={to_email}">Haz clic aquí para completar tu registro ahora</a></strong></p>
            <p>Si ya lo registraste, por favor ignora este mensaje.</p>
            <p>Saludos,<br>El equipo de Registro IMEI Multibanda</p>
        """
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print(f"  - Correo de seguimiento enviado exitosamente a {to_email}.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  - Error al enviar correo a {to_email}: {e}")
        # También imprime el cuerpo de la respuesta si hay más detalles
        if e.response is not None:
            print(f"  - Respuesta de la API: {e.response.text}")
        return False


def main():
    """Función principal del script."""
    print("Iniciando script de seguimiento de leads...")
    
    try:
        db = initialize_firebase()
        resend_api_key = os.getenv('RESEND_API_KEY')
    except Exception as e:
        print(f"No se pudo inicializar Firebase. Abortando. Error: {e}")
        return

    # 1. Definir el rango de tiempo para los leads
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

    # 2. Obtener leads que no han sido contactados y tienen entre 1 hora y 2 días de antigüedad
    leads_ref = db.collection('leads')
    leads_query = leads_ref.where('followUpSent', '==', False) \
                           .where('createdAt', '<=', one_hour_ago) \
                           .where('createdAt', '>=', two_days_ago)
    
    leads_to_process = list(leads_query.stream())

    if not leads_to_process:
        print("No se encontraron leads nuevos para enviar seguimiento. Finalizando.")
        return

    print(f"Se encontraron {len(leads_to_process)} leads para procesar.")

    for lead_doc in leads_to_process:
        lead_data = lead_doc.to_dict()
        lead_id = lead_doc.id
        lead_email = lead_data.get('email')
        lead_imei = lead_data.get('imei')

        if not lead_email or not lead_imei:
            print(f" - Lead {lead_id} no tiene email o imei. Saltando.")
            continue

        print(f"\nProcesando lead: {lead_id} ({lead_email})")

        # 3. Verificar si el email del lead ya tiene un registro
        registros_ref = db.collection('registros').where('customerEmail', '==', lead_email).limit(1).stream()
        
        if any(registros_ref):
            print(f"  - El usuario {lead_email} ya tiene un registro. Marcando como contactado para no volver a enviar.")
            # Marcar el lead como contactado para que no se vuelva a procesar
            db.collection('leads').document(lead_id).update({'followUpSent': True})
            continue
        
        # 4. Si no tiene registro, enviar el correo
        print(f"  - El usuario {lead_email} no ha comprado. Enviando correo de seguimiento...")
        email_sent = send_resend_email(resend_api_key, lead_email, lead_imei)

        # 5. Si el correo fue enviado con éxito, actualizar el lead
        if email_sent:
            db.collection('leads').document(lead_id).update({'followUpSent': True})
            print(f"  - Lead {lead_id} actualizado a 'followUpSent: True'.")

    print("\nProceso de seguimiento de leads completado.")

if __name__ == "__main__":
    main()
