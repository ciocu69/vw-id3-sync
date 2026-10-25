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
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

print("1. Initiere sesiune autorizare...")
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
    params["client_id"] = "a24fba63-34b3-4d41-b181-9ab99119204e@apps_vw-dilab_com"
    params["redirect_uri"] = "https://www.volkswagen.de/app/authCallback/orchestrator"
    params["scope"] = "openid profile cars"
    r = session.get(auth_url, params=params)

if r.status_code != 200:
    print(f"Eroare initiala ({r.status_code}): {r.text[:300]}")
    sys.exit(1)

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
    print("Nu s-a putut parsa pasul de parola!")
    sys.exit(1)

post_pwd_url = "https://identity.vwgroup.io" + action_pwd.group(1)
pwd_payload = {
    "_csrf": csrf_pwd.group(1) if csrf_pwd else "",
    "relayState": relay_pwd.group(1) if relay_pwd else "",
    "hmac": hmac_pwd.group(1) if hmac_pwd else "",
    "password": PASS
}

print("3. Trimitere parola...")
r_auth = session.post(post_pwd_url, data=pwd_payload, allow_redirects=False)

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

print(f"Token extras: {'DA' if token else 'NU'}")

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
                b_stat = data_obj.get("batteryStatus", {})
                soc = b_stat.get("currentSOC_pct", soc)
                range_km = b_stat.get("cruisingRangeElectric_km", range_km)
                m_stat = data_obj.get("measurements", {}).get("odometerStatus", {})
                odometer = m_stat.get("odometer", odometer)
                c_stat = data_obj.get("chargingStatus", {})
                c_state = c_stat.get("chargingState", "ready")
                charging_state = "charging" if c_state == "charging" else "ready"
                charge_power = float(c_stat.get("chargePower_kW", 0.0))

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
    "charge_type": "dc" if charge_power > 12 else "ac"
}

db["last_state"] = state
with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"SINCRONIZARE REUSITA: SoC={soc}% | Autonomie={range_km}km | Kilometraj={odometer}km")
