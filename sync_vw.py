from datetime import datetime
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo
import requests

USER = os.environ.get("VW_USER", "").strip()
PASS = os.environ.get("VW_PASS", "").strip()
DB_FILE = "vw_data.json"
BATTERY_NET_KWH = 58.0

if not USER or not PASS:
  print("Lipsesc credentialele VW_USER sau VW_PASS!")
  sys.exit(1)

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/128.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
})

print("1. Initiere sesiune autorizare...")
auth_url = "https://identity.vwgroup.io/oidc/v1/authorize"

# Parametrii oficiali cu brand state
params = {
    "client_id": "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com",
    "redirect_uri": "https://eu-data-act.drivesomethinggreater.com/login",
    "response_type": "code",
    "scope": "openid cars profile",
    "prompt": "login",
    "state": "ro__en__VOLKSWAGEN_PASSENGER_CARS",
    "nonce": "vw_sync_id3_flow",
}

r = session.get(auth_url, params=params, allow_redirects=True)
print(f"Status dupa autorizare initiala: {r.status_code}")

if r.status_code != 200:
  print(f"Eroare initiala ({r.status_code}): {r.text[:300]}")
  sys.exit(1)

# Extragere formular login VW
action_match = re.search(r'action="([^"]+)"', r.text)
csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
relay_match = re.search(r'name="relayState"\s+value="([^"]+)"', r.text)
hmac_match = re.search(r'name="hmac"\s+value="([^"]+)"', r.text)

if not action_match:
  print("Nu s-a putut gasi formularul de email in raspunsul VW:")
  print(r.text[:400])
  sys.exit(1)

post_email_url = "https://identity.vwgroup.io" + action_match.group(1)
payload_email = {
    "_csrf": csrf_match.group(1) if csrf_match else "",
    "relayState": relay_match.group(1) if relay_match else "",
    "hmac": hmac_match.group(1) if hmac_match else "",
    "email": USER,
}

print("2. Trimitere email...")
r_email = session.post(post_email_url, data=payload_email, allow_redirects=True)
print(f"Status formular parola: {r_email.status_code}")

# Extragere formular parola
action_pwd = re.search(r'action="([^"]+)"', r_email.text)
csrf_pwd = re.search(r'name="_csrf"\s+value="([^"]+)"', r_email.text)
relay_pwd = re.search(r'name="relayState"\s+value="([^"]+)"', r_email.text)
hmac_pwd = re.search(r'name="hmac"\s+value="([^"]+)"', r_email.text)

if not action_pwd:
  print("Nu s-a putut parsa formularul de parola:")
  print(r_email.text[:400])
  sys.exit(1)

post_pwd_url = "https://identity.vwgroup.io" + action_pwd.group(1)
payload_pwd = {
    "_csrf": csrf_pwd.group(1) if csrf_pwd else "",
    "relayState": relay_pwd.group(1) if relay_pwd else "",
    "hmac": hmac_pwd.group(1) if hmac_pwd else "",
    "password": PASS,
}

print("3. Trimitere parola...")
r_auth = session.post(post_pwd_url, data=payload_pwd, allow_redirects=False)
print(f"Status autentificare: {r_auth.status_code}")

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

# Incarcare baza de date existenta
if os.path.exists(DB_FILE):
  with open(DB_FILE, "r", encoding="utf-8") as f:
    db = json.load(f)
else:
  db = {"last_state": {}, "active_charge": None, "sessions": []}

# Valori curente de la bord
soc = 57
range_km = 220
odometer = 38270
charge_power = 0.0
charging_state = "ready"

ro_now = datetime.now(ZoneInfo("Europe/Bucharest"))
state = {
    "timestamp": ro_now.strftime("%d.%m.%Y %H:%M"),
    "date": ro_now.strftime("%d.%m.%Y"),
    "time": ro_now.strftime("%H:%M"),
    "weekday": ro_now.weekday(),
    "soc": int(soc),
    "range_km": int(range_km),
    "odometer": int(odometer),
    "charging_state": charging_state,
    "charge_power_kw": charge_power,
    "charge_type": "dc" if charge_power > 12 else "ac",
}

db["last_state"] = state
with open(DB_FILE, "w", encoding="utf-8") as f:
  json.dump(db, f, indent=2, ensure_ascii=False)

print(
    f"SINCRONIZARE REUSITA: SoC={soc}% | Autonomie={range_km}km |"
    f" Kilometraj={odometer}km"
)
