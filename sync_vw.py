import json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "vw_data.json"
raw = open("evcc_out.txt").read() if os.path.exists("evcc_out.txt") else ""

def get_val(pat):
    m = re.search(pat, raw, re.I)
    return float(m.group(1).replace(",", ".")) if m else None

soc = get_val(r"SoC:\s*([\d.,]+)\s*%")
rng = get_val(r"Range:\s*([\d.,]+)\s*km")
odo = get_val(r"Odometer:\s*([\d.,]+)\s*km")
pwr = get_val(r"Power:\s*([\d.,]+)\s*kW") or 0.0

if soc is None:
    print("EVCC inca nu a primit pachetul ZIP de la VW. Output complet:")
    print(raw)
    sys.exit(1)

db = json.load(open(DB)) if os.path.exists(DB) else {"sessions": []}
now = datetime.now(ZoneInfo("Europe/Bucharest"))

db["last_state"] = {
    "timestamp": now.strftime("%d.%m.%Y %H:%M"),
    "date": now.strftime("%d.%m.%Y"),
    "time": now.strftime("%H:%M"),
    "weekday": now.weekday(),
    "soc": int(round(soc)),
    "range_km": int(round(rng or 0)),
    "odometer": int(round(odo or 0)),
    "charging_state": "charging" if pwr > 0.5 else "ready",
    "charge_power_kw": round(pwr, 1),
    "charge_type": "dc" if pwr > 12 else "ac"
}

json.dump(db, open(DB, "w"), indent=2)
print(f"SUCCES REAL: SoC={int(soc)}% | Range={int(rng or 0)}km | Km={int(odo or 0)}")
