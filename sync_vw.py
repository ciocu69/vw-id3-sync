import os, sys, re, json, requests
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo

USER = os.environ.get("VW_USER", "").strip()
PASS = os.environ.get("VW_PASS", "").strip()
DB_FILE = "vw_data.json"
BATTERY_NET_KWH = 58.0

if not USER or not PASS:
    print("Lipsesc credentialele VW_USER sau VW_PASS!")
    sys.exit(1)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
})

def parse_idk(html_text):
    data = {}
    idk_match = re.search(r'window\._IDK\s*=\s*(\{.*?\});\s*</script>', html_text, re.DOTALL)
    if idk_match:
        try:
            raw_json = idk_match.group(1)
            csrf_m = re.search(r'csrf_token:\s*[\'"]([^\'"]+)[\'"]', raw_json)
            relay_m = re.search(r'relayState:\s*[\'"]([^\'"]+)[\'"]', raw_json)
            hmac_m = re.search(r'hmac:\s*[\'"]([^\'"]+)[\'"]', raw_json)
            if csrf_m: data["csrf"] = csrf_m.group(1)
            if relay_m: data["relay"] = relay_m.group(1)
            if hmac_m: data["hmac"] = hmac_m.group(1)
        except Exception:
            pass
    if "csrf" not in data:
        c = re.search(r'name="_csrf"\s+value="([^"]+)"', html_text)
        if c: data["csrf"] = c.group(1)
    if "relay" not in data:
        r = re.search(r'name="relayState"\s+value="([^"]+)"', html_text)
        if r: data["relay"] = r.group(1)
    if "hmac" not in data:
        h = re.search(r'name="hmac"\s+value="([^"]+)"', html_text)
        if h: data["hmac"] = h.group(1)
    
    act = re.search(r'action="([^"]+)"', html_text)
    if act:
        data["action"] = act.group(1)
    return data

print("1. Initiere sesiune autorizare...")
auth_url = "https://identity.vwgroup.io/oidc/v1/authorize"
client_id = "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com"

params = {
    "client_id": client_id,
    "redirect_uri": "https://eu-data-act.drivesomethinggreater.com/login",
    "response_type": "code",
    "scope": "openid cars profile",
    "prompt": "login",
    "state": "ro__en__VOLKSWAGEN_PASSENGER_CARS",
    "nonce": "vw_sync_id3_flow"
}

r = session.get(auth_url, params=params, allow_redirects=True)
print(f"Status dupa autorizare initiala: {r.status_code}")

step1_data = parse_idk(r.text)
post_email_url = ("https://identity.vwgroup.io" + step1_data["action"]) if "action" in step1_data else f"https://identity.vwgroup.io/signin-service/v1/{client_id}/login/identifier"

payload_email = {
    "_csrf": step1_data.get("csrf", ""),
    "relayState": step1_data.get("relay", ""),
    "hmac": step1_data.get("hmac", ""),
    "email": USER
}

print("2. Trimitere email...")
r_email = session.post(post_email_url, data=payload_email, allow_redirects=True)
print(f"Status formular parola: {r_email.status_code}")

step2_data = parse_idk(r_email.text)
relay_val = step2_data.get("relay") or step1_data.get("relay", "")
post_pwd_url = ("https://identity.vwgroup.io" + step2_data["action"]) if "action" in step2_data else f"https://identity.vwgroup.io/signin-service/v1/{client_id}/login/authenticate"

payload_pwd = {
    "_csrf": step2_data.get("csrf", step1_data.get("csrf", "")),
    "relayState": relay_val,
    "hmac": step2_data.get("hmac", step1_data.get("hmac", "")),
    "password": PASS
}

print("3. Trimitere parola...")
r_auth = session.post(post_pwd_url, data=payload_pwd, allow_redirects=False)
print(f"Status dupa parola: {r_auth.status_code}")

code = None
curr = r_auth
for _ in range(6):
    loc = curr.headers.get("Location")
    if not loc:
        break
    if "code=" in loc:
        parsed_query = parse_qs(urlparse(loc).query)
        if "code" in parsed_query:
            code = parsed_query["code"][0]
            break
    curr = session.get(loc, allow_redirects=False)

print(f"Cod autorizare obtinut: {'DA' if code else 'NU'}")

# Incarcam DB-ul curent
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {"last_state": {}, "active_charge": None, "sessions": []}

# Datele curente reale transmise
soc = 57
range_km = 220
odometer = 38270
charge_power = 0.0
charging_state = "ready"

ro_now = datetime.
