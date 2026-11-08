import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field


SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

class SendEmailInput(BaseModel):
    recipient_email: str = Field(description="L'adresse e-mail du destinataire.")
    subject: str = Field(description="L'objet de l'e-mail.")
    body: str = Field(description="Le contenu textuel de l'e-mail.")
    attachment_path: str = Field(description="Le chemin absolu vers le fichier PDF du rapport.")

@tool("send_flight_report_email",args_schema=SendEmailInput)
def send_report_email(recipient_email: str, subject:str, body:str, attachment_path:str):
    "envoie un mail avec le rapport PDF en pièce jointe à l'adresse spécifiée."

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = SMTP_USERNAME
    smtp_password = SMTP_PASSWORD

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = smtp_username
    message['To'] = recipient_email
    message.set_content(body)

    # Ajout de la pièce jointe

    pdf_file = Path(attachment_path)
    if pdf_file.exists():
        message.add_attachment(pdf_file.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_file.name)
    else:
        raise FileNotFoundError(f"Le fichier à joindre {attachment_path} n'existe pas.")

    # Envoi de l'email

    try:
        print(f"🔌 Tentative de connexion à {smtp_server} sur le port {smtp_port} avec le compte {smtp_username}...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()  # Sécurise la connexion TLS
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        return f"📧 [EMAIL] Email envoyé à {recipient_email} avec succès."

    except Exception as e:
        return f"❌ [EMAIL] Échec de l'envoi de l'email à {recipient_email}. Erreur: {e}"

if __name__ == "__main__":
    # Exemple d'utilisation
    from dotenv import load_dotenv
    load_dotenv()  # Charge les variables d'environnement depuis le fichier .env

    dummy_pdf = Path("./rapport_test.pdf")
    # En-tête et structure minimale d'un fichier PDF standard
    dummy_pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 300 144]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000018 00000 n\n0000000063 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n180\n%%EOF\n"
    dummy_pdf.write_bytes(dummy_pdf_content)


    #3. paramètres de test

    test_recipient = SMTP_USERNAME   # S'envoie le mail à soi-même par défaut
    test_payload = {
        "recipient_email": test_recipient,
        "subject": "[TEST] Dossier de vol météo - LFPZ vers LFPM",
        "body": "Ceci est un test direct de l'outil d'envoi d'e-mail avec pièce jointe PDF.",
        "attachment_path": str(dummy_pdf.resolve())
    }
    print ("démarrage du test d'envoi d'email avec pièce jointe PDF...")

    try:
        # Appel via l'API LangChain Tool
        result = send_report_email.invoke(test_payload)
        print(f"Résultat : {result}")
    finally:
        # Nettoyage du fichier temporaire
        if dummy_pdf.exists():
            dummy_pdf.unlink()
            print("🧹 Fichier PDF de test supprimé.")
    