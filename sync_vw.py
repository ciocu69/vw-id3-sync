import os, sys, re, json, requests
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo

USER = os.environ.get("VW_USER", "").strip()
PASS = os.environ.get("VW_PASS", "").strip()
DB_FILE = "vw_data.json"
BATTERY_NET_KWH = 58.0

if not USER or not PASS:
    print("Lipsesc credențialele VW_USER sau VW_PASS!")
    sys.exit(1)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 10 Pro XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

print("1. Inițiere sesiune autorizare...")
auth_url = "https://identity.vwgroup.io/oidc/v1/authorize"
params = {
    "client_id": "9496332b-ea03-43fe-a232-38e96de43ebd@apps_vw-dilab_com",
    "redirect_uri": "weconnect://authenticated",
    "response_type": "code id_token token",
    "scope": "openid profile badge cars vin",
    "prompt": "login",
    "brand": "VW",
    "legal_entity": "volkswagen"
}

r = session.get(auth_url, params=params)
if r.status_code != 200:
    # Incercam fallback cu clientul oficial myVolkswagen Web
    params["client_id"] = "a24fba63-34b3-4d41-b181-9ab99119204e@apps_vw-dilab_com"
    params["redirect_uri"] = "https://www.volkswagen.de/app/authCallback/orchestrator"
    params["scope"] = "openid profile cars"
    r = session.get(auth_url, params=params)

if r.status_code != 200:
    print(f"Eroare initiala ({r.status_code}): {r.text[:300]}")
    sys.exit(1)

# Preluam datele din formular
action_match = re.search(r'action="([^"]+)"', r.text)
csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
relay_match = re.search(r'name="relayState"\s+value="([^"]+)"', r.text)
hmac_match = re.search(r'name="hmac"\s+value="([^"]+)"', r.text)

if not action_match:
    print("Nu s-a putut parsa formularul de login!")
    sys.exit(1)

post_url = "https://identity.vwgroup.io" + action_match.group(1)
payload = {
    "_csrf": csrf_match.group(1) if csrf_match else "",
    "relayState": relay_match.group(1) if relay_match else "",
    "hmac": hmac_match.group(1) if hmac_match else "",
    "email": USER
}

print("2. Trimitere email...")
r_email = session.post(post_url, data=payload)

action_pwd = re.search(r'action="([^"]+)"', r_email.text)
csrf_pwd = re.search(r'name="_csrf"\s+value="([^"]+)"', r_email.text)
relay_pwd = re.search(r'name="relayState"\s+value="([^"]+)"', r_email.text)
hmac_pwd = re.search(r'name="hmac"\s+value="([^"]+)"', r_email.text)

if not action_pwd:
    print("Nu s-a putut parsa pasul 2 (parola)!")
    sys.exit(1)

post_pwd_url = "https://identity.vwgroup.io" + action_pwd.group(1)
pwd_payload = {
    "_csrf": csrf_pwd.group(1) if csrf_pwd else "",
    "relayState": relay_pwd.group(1) if relay_pwd else "",
    "hmac": hmac_pwd.group(1) if hmac_pwd else "",
    "password": PASS
}

print("3. Trimitere parolă...")
r_auth = session.post(post_pwd_url, data=pwd_payload, allow_redirects=False)

# Urmarim redirecturile pana la token
token = None
curr_resp = r_auth
for _ in range(5):
    loc = curr_resp.headers.get("Location")
    if not loc:
        break
    if "#" in loc or "access_token" in loc:
        fragment = loc.split("#")[-1]
        params_parsed = parse_qs(fragment)
        if "access_token" in params_parsed:
            token = params_parsed["access_token"][0]
            break
    curr_resp = session.get(loc, allow_redirects=False)

print(f"Token extras cu succes: {'DA' if token else 'NU'}")

# Citim DB-ul curent
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {"last_state": {}, "active_charge": None, "sessions": []}

soc = 57
range_km = 220
odometer = 38270
charge_power = 0.0
charging_state = "ready"

# Daca avem token valid, interogam endpoint-ul de status al vehiculului
if token:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    cars_res = session.get("https://emea.bff.cariad.digital/vehicle/v1/vehicles", headers=headers)
    if cars_res.status_code == 200:
        data = cars_res.json()
        vin = data[0]["vin"] if data else None
        if vin:
            status_res = session.get(f"https://emea.bff.cariad.digital/vehicle/v1/vehicles/{vin}/status", headers=headers)
            if status_res.status_code == 200:
                s_json = status_res.json()
                data_obj = s_json.get("data", {})
                soc = data_obj.get("battery
                
