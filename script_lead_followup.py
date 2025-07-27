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
 """Envía el correo de seguimiento usando la API de Resend."""
 if not api_key:
     print(" - RESEND_API_KEY no encontrada. No se puede enviar el correo.")
     return False

 url = "https://api.resend.com/emails"
 
 # Este es el payload que simula la llamada a `sendEmail` desde el backend
 payload = {
     "from": "Registro IMEI Multibanda <registro@registroimeimultibanda.cl>",
     "to": [to_email],
     "subject": f"🤔 {user_name}, ¿olvidaste registrar tu IMEI?",
     "react": {
         "type": "lead-follow-up",
         "props": {
             "name": user_name,
             "imei": imei,
             "email": to_email
         }
     }
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
 now = datetime.now(timezone.utc)
 one_hour_ago = now - timedelta(hours=1)
 two_days_ago = now - timedelta(days=2)

 # 2. Obtener leads que no han sido contactados y tienen más de 1 hora de antigüedad
 leads_ref = db.collection('leads')
 leads_query = leads_ref.where('followUpSent', '==', False) \
                        .where('createdAt', '<=', one_hour_ago) \
                        .order_by('createdAt', direction=firestore.Query.DESCENDING)
 
 all_pending_leads = list(leads_query.stream())

 if not all_pending_leads:
     print("No se encontraron leads pendientes con más de 1 hora de antigüedad. Finalizando.")
     return
     
 # 3. Filtrar en el código para leads que no sean más antiguos de 2 días
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
     
     # Asumimos que no tenemos el nombre, así que lo omitimos del correo.
     lead_name = "Hola" 

     if not lead_email or not lead_imei:
         print(f" - Lead {lead_id} no tiene email o imei. Saltando.")
         continue

     print(f"\nProcesando lead: {lead_id} ({lead_email})")

     # 4. Verificar si el email del lead ya tiene un registro
     registros_ref = db.collection('registros').where('customerEmail', '==', lead_email).limit(1).stream()
     
     if any(registros_ref):
         print(f"  - El usuario {lead_email} ya tiene un registro. Marcando como contactado para no volver a enviar.")
         # Marcar el lead como contactado para que no se vuelva a procesar
         db.collection('leads').document(lead_id).update({'followUpSent': True})
         continue
     
     # 5. Si no tiene registro, enviar el correo
     print(f"  - El usuario {lead_email} no ha comprado. Enviando correo de seguimiento...")
     email_sent = send_resend_email(resend_api_key, lead_email, lead_name, lead_imei)

     # 6. Si el correo fue enviado con éxito, actualizar el lead
     if email_sent:
         db.collection('leads').document(lead_id).update({'followUpSent': True})
         print(f"  - Lead {lead_id} actualizado a 'followUpSent: True'.")

 print("\nProceso de seguimiento de leads completado.")

if __name__ == "__main__":
 main()
