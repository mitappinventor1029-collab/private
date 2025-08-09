from flask import Flask, request, Response
import requests
import threading
import time
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# Token y config IZZI (como en tu código)
auth_token = None
token_expira = 0
DEVICE_ID = "6bda35df-25f0-4dfe-b6d0-66b540765bf3"
PROFILE_ID = "15117588"
BASE_URL = "https://www.izzigo.tv/streamlocators/multirights/getPlayableUrlAndLicense"

def obtener_token():
    global auth_token, token_expira
    logging.info("Usando token copiado de IZZI Go...")
    auth_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjg2MzIwMDQ0OSwidHkiOiJVU0VSIiwicGNpIjoiMTc0OTE1NzIiLCJod0lkIjoiNmJkYTM1ZGYtMjVmMC00ZGZlLWI2ZDAtNjZiNTQwNzY1YmYzIiwiZXhwIjoxNzU0NzE0NDQ2LCJwbiI6IklaWkkiLCJjaWQiOjQyMTAyNDk3fQ.7FvzaL4KEyKXe1zGV2_LifOIqetEU2RAlzAWmPkuU6o"
    token_expira = int(time.time()) + 3500

def monitor_token():
    while True:
        if not auth_token:
            obtener_token()
        elif time.time() >= token_expira - 60:
            logging.warning("El token está por expirar. Actualízalo manualmente en obtener_token().")
        time.sleep(30)

@app.route("/licencia", methods=["GET", "POST"])
def licencia_proxy():
    logging.debug(f"Solicitud {request.method} recibida en /licencia")

    # Obtener parámetros provisioningData y url (de GET o POST)
    if request.method == "GET":
        provisioning_data = request.args.get("provisioningData")
        media_url = request.args.get("url")
    else:
        # Para POST puede venir JSON o form-data o query
        data = request.get_json(silent=True)
        if data:
            provisioning_data = data.get("provisioningData")
            media_url = data.get("url")
        else:
            provisioning_data = request.form.get("provisioningData") or request.args.get("provisioningData")
            media_url = request.form.get("url") or request.args.get("url")

    if not provisioning_data or not media_url:
        logging.error("Faltan parámetros provisioningData y/o url")
        return {"error": "Faltan parámetros provisioningData y url"}, 400

    # 1) Hacer la primera llamada GET para obtener URL real licencia
    headers_izzigo = {
        "Accept": "*/*",
        "Authorization": auth_token,
        "IRIS-APP-VERSION": "11.2.63",
        "IRIS-DEVICE-CLASS": "PC",
        "IRIS-DEVICE-REGION": "METRO",
        "IRIS-DEVICE-STATUS": "ACTIVE",
        "IRIS-DEVICE-TYPE": "WINDOWS/EDGE",
        "IRIS-HW-DEVICE-ID": DEVICE_ID,
        "IRIS-MODULE-ID": "dyFcNJKc",
        "IRIS-PROFILE-ID": PROFILE_ID,
        "Referer": "https://www.izzigo.tv/webclient/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
    params = {
        "drm": "WV",
        "packaging": "DASH",
        "provisioningData": provisioning_data,
        "url": media_url
    }

    try:
        r = requests.get(BASE_URL, headers=headers_izzigo, params=params)
        r.raise_for_status()
        data = r.json()
        license_url = data["videos"][0]["licenses"][0]["url"]
        logging.info(f"URL real de licencia: {license_url}")
    except Exception as e:
        logging.exception("Error al obtener URL de licencia de IZZI")
        return {"error": "Error al obtener URL de licencia"}, 500

    # 2) Hacer la llamada POST a license_url pasando el body binario recibido en este proxy
    body_binario = request.get_data()  # Raw bytes que envía Kodi o cliente DRM

    headers_license = {
        "Accept": "*/*",
        "Origin": "https://www.izzigo.tv",
        "Referer": "https://www.izzigo.tv/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
        "Content-Type": "application/octet-stream",
        "Connection": "keep-alive"
    }

    try:
        license_resp = requests.post(
            license_url,
            headers=headers_license,
            data=body_binario,
            timeout=10
        )
        license_resp.raise_for_status()
    except Exception as e:
        logging.exception("Error al solicitar licencia binaria")
        return {"error": "Error al solicitar licencia binaria"}, 500

    # 3) Responder al cliente con el contenido binario recibido
    return Response(
        license_resp.content,
        status=license_resp.status_code,
        content_type=license_resp.headers.get("Content-Type", "application/octet-stream")
    )


if __name__ == "__main__":
    obtener_token()
    threading.Thread(target=monitor_token, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)


