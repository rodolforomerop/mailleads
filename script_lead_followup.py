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

def send_resend_email(api_key, to_email, user_name, imei):
    """Envía el correo de seguimiento usando la API de Resend y una plantilla de React."""
    if not api_key:
        print(" - RESEND_API_KEY no encontrada. No se puede enviar el correo.")
        return False

    url = "https://api.resend.com/emails"
    
    # Payload que usa la plantilla de React. `sendEmail` se encargará de renderizarlo.
    payload = {
        "from": "Registro IMEI Multibanda <registro@registroimeimultibanda.cl>",
        "to": [to_email],
        "subject": f"🤔 {user_name}, ¿olvidaste registrar tu IMEI?",
        "html": f"""
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ margin: 0; background-color: #f4f4f7; font-family: sans-serif; }}
                    .container {{ background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; margin: 32px auto; padding: 32px; max-width: 520px; }}
                    .logo {{ text-align: center; }}
                    .text {{ font-size: 16px; color: #333333; line-height: 1.6; }}
                    .button-section {{ text-align: center; margin: 24px 0; }}
                    .button {{ background-color: #009959; color: #ffffff; font-weight: 600; border-radius: 6px; padding: 12px 24px; text-decoration: none; }}
                    .footer-text {{ font-size: 12px; color: #888888; text-align: center; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">
                        <img src="https://registroimeimultibanda.cl/Logo%20Registro%20IMEI%20Multibanda%20Chile.webp" width="180" alt="Registro IMEI Multibanda Chile" />
                    </div>
                    <h1 style="font-size: 20px; font-weight: bold; margin-top: 32px;">¡Hola!</h1>
                    <p class="text">
                        Notamos que hace un tiempo verificaste el IMEI <strong>{imei}</strong> en nuestro sitio y descubriste que necesita ser registrado para operar en Chile.
                    </p>
                    <p class="text">
                        No dejes que tu equipo sea bloqueado y te quedes sin conexión. El proceso para inscribirlo es rápido, 100% online y está respaldado por nuestra garantía de entrega en menos de 90 minutos.
                    </p>
                    <div class="button-section">
                        <a href="https://registroimeimultibanda.cl/registro-dispositivo?imei={imei}&email={to_email}" class="button">
                            Completar mi Registro Ahora
                        </a>
                    </div>
                    <p class="text">
                        Si ya registraste tu equipo por otro medio o tienes alguna pregunta, no dudes en contactar a nuestro equipo de soporte.
                    </p>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 24px 0;" />
                    <p class="footer-text">
                        Si ya completaste el registro para este IMEI, por favor ignora este mensaje.
                    </p>
                    <p class="footer-text">
                        © {datetime.now().year} Registro IMEI Multibanda. Todos los derechos reservados.
                    </p>
                </div>
            </body>
            </html>
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

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    two_days_ago = now - timedelta(days=2)

    leads_ref = db.collection('leads')
    leads_query = leads_ref.where('followUpSent', '==', False) \
                           .where('createdAt', '<=', one_hour_ago) \
                           .order_by('createdAt', direction=firestore.Query.DESCENDING)
    
    all_pending_leads = list(leads_query.stream())

    if not all_pending_leads:
        print("No se encontraron leads pendientes con más de 1 hora de antigüedad. Finalizando.")
        return
        
    leads_to_process = [
        lead for lead in all_pending_leads 
        if lead.to_dict().get('createdAt') and lead.to_dict()['createdAt'].replace(tzinfo=timezone.utc) >= two_days_ago
    ]

    if not leads_to_process:
        print("No se encontraron leads en el rango de tiempo de 1 hora a 2 días. Finalizando.")
        return

    print(f"Se encontraron {len(leads_to_process)} leads para procesar.")

    for lead_doc in leads_to_process:
        lead_data = lead_doc.to_dict()
        lead_id = lead_doc.id
        lead_email = lead_data.get('email')
        lead_imei = lead_data.get('imei')
        
        lead_name = "Hola" 

        if not lead_email or not lead_imei:
            print(f" - Lead {lead_id} no tiene email o imei. Saltando.")
            continue

        print(f"\nProcesando lead: {lead_id} ({lead_email} - IMEI: {lead_imei})")

        # Verifica si ya existe un registro para ESE email Y ESE imei
        registros_ref = db.collection('registros') \
                          .where('customerEmail', '==', lead_email) \
                          .where('imei1', '==', lead_imei) \
                          .limit(1).stream()
        
        if any(registros_ref):
            print(f"  - Ya existe un registro para el email {lead_email} y el IMEI {lead_imei}. Marcando para no enviar.")
            db.collection('leads').document(lead_id).update({'followUpSent': True})
            continue
        
        print(f"  - El usuario {lead_email} no ha comprado para este IMEI. Enviando correo...")
        email_sent = send_resend_email(resend_api_key, lead_email, lead_name, lead_imei)

        if email_sent:
            db.collection('leads').document(lead_id).update({'followUpSent': True})
            print(f"  - Lead {lead_id} actualizado a 'followUpSent: True'.")

    print("\nProceso de seguimiento de leads completado.")

if __name__ == "__main__":
    main()
