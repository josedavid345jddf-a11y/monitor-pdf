import requests
from bs4 import BeautifulSoup
import urllib3
import re
import os
import pdfplumber
from urllib.parse import urljoin
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Desactivar advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL a monitorear
url = "https://servicios.supernotariado.gov.co/resoluciones.html"

# Archivos de control
archivo_notificadas = "notificadas.txt"
archivo_resultados = "resultados.txt"

# Configuración del correo
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_TO   = "jddftdm@gmail.com"

# Cargar resoluciones ya notificadas
if os.path.exists(archivo_notificadas):
    with open(archivo_notificadas, "r", encoding="utf-8") as f:
        resoluciones_notificadas = set(line.strip() for line in f)
else:
    resoluciones_notificadas = set()

def extraer_texto(pdf_path):
    texto = ""
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            contenido = pagina.extract_text()
            if contenido:
                texto += contenido
    return texto

def extraer_datos(texto_pdf, nombre_archivo):
    match_resolucion = re.search(r"RES[-\s]*\d{4}-\d{5,7}(?:-\d+)?", texto_pdf)
    if not match_resolucion:
        match_resolucion = re.search(r"Resolución\s+No\.?\s*\d+", texto_pdf, re.IGNORECASE)
    if not match_resolucion:
        match_resolucion = re.search(r"RESOLUCIÓN\s+NÚMERO.*", texto_pdf)
    numero = match_resolucion.group(0).strip() if match_resolucion else "No encontrado"

    match_fecha = re.search(r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}", texto_pdf, re.IGNORECASE)
    fecha = match_fecha.group(0) if match_fecha else "No encontrada"

    match_nom = re.search(r"(la señora|el señor)\s+([A-ZÁÉÍÓÚÑ\s]+?)(?=,)", texto_pdf)
    nombramiento = match_nom.group(2).strip() if match_nom else "No encontrado"

    match_ins = re.search(r"insubsistente.*?(la señora|el señor)\s+([A-ZÁÉÍÓÚÑ\s]+?)(?=,)", texto_pdf, re.IGNORECASE)
    insubsistencia = match_ins.group(2).strip() if match_ins else "No encontrado"

    match_comunicacion = re.search(
        r"ARTÍCULO\s+SEXTO.*?(Comunicación.*?|COMUNICAR.*?|Comunicar.*?)(?=ARTÍCULO|\Z)",
        texto_pdf,
        re.DOTALL | re.IGNORECASE
    )
    comunicacion = match_comunicacion.group(0).strip() if match_comunicacion else "No encontrado"

    return numero, fecha, nombramiento, insubsistencia, comunicacion

def enviar_correo(asunto, cuerpo, pdf_path):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain"))

    try:
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(pdf_path)}")
        msg.attach(part)
    except Exception as e:
        print("⚠️ Error al adjuntar PDF:", e)

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        server.quit()
        print("✅ Correo enviado:", asunto)
    except Exception as e:
        print("⚠️ Error al enviar correo:", e)

def guardar_resultados(cuerpo):
    with open(archivo_resultados, "a", encoding="utf-8") as f:
        f.write(cuerpo + "\n" + "-"*50 + "\n")

def main():
    global resoluciones_notificadas
    try:
        print("🔍 Revisando página...")
        response = requests.get(url, verify=False, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        enlaces_pdf = [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]

        nuevas = []
        for pdf_url in enlaces_pdf:
            pdf_url = urljoin(url, pdf_url)
            pdf_response = requests.get(pdf_url, verify=False, timeout=10)
            nombre_archivo = pdf_url.split("/")[-1]

            clave = nombre_archivo
            if clave not in resoluciones_notificadas:
                pdf_path = "temp.pdf"
                with open(pdf_path, "wb") as f:
                    f.write(pdf_response.content)

                texto_pdf = extraer_texto(pdf_path)
                numero, fecha, nombramiento, insubsistencia, comunicacion = extraer_datos(texto_pdf, nombre_archivo)

                cuerpo = f"📄 Nueva resolución detectada\nNúmero: {numero}\nFecha: {fecha}"
                cuerpo += f"\nNombramiento: {nombramiento}"
                cuerpo += f"\nInsubsistencia: {insubsistencia}"
                cuerpo += f"\nCOMUNICACIÓN: {comunicacion}"

                enviar_correo("Nueva resolución detectada", cuerpo, pdf_path)
                guardar_resultados(cuerpo)

                with open(archivo_notificadas, "a", encoding="utf-8") as f:
                    f.write(f"{clave}\n")

                nuevas.append(clave)

        if not nuevas:
            print("🔍 No hay resoluciones nuevas en esta revisión")

    except Exception as e:
        print(f"⚠️ Error al verificar la página: {e}")

if __name__ == "__main__":
    main()

