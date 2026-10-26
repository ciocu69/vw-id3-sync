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
lim = get_val(r"Limit Soc:\s*([\d.,]+)\s*%")
pwr = get_val(r"Power:\s*([\d.,]+)\s*kW") or 0.0

st_m = re.search(r"Charge status:\s*([A-Z])", raw, re.I)
c_code = st_m.group(1).upper() if st_m else "A"

if soc is None:
    print("EROARE: EVCC nu a returnat SoC valid.")
    sys.exit(1)

db = json.load(open(DB)) if os.path.exists(DB) else {"sessions": []}
prev = db.get("last_state", {})

# Daca VW nu trimite Range in pachetul Data Act, estimam realist (~350km la 100%)
final_soc = int(round(soc))
final_rng = int(round(rng)) if rng is not None else int(round(final_soc * 3.5))
final_odo = int(round(odo)) if odo is not None else prev.get("odometer", 0)

is_chg = (c_code == "C" or pwr > 0.5)
c_state = "charging" if is_chg else ("connected" if c_code == "B" else "ready")

now = datetime.now(ZoneInfo("Europe/Bucharest"))

db["last_state"] = {
    "timestamp": now.strftime("%d.%m.%Y %H:%M"),
    "date": now.strftime("%d.%m.%Y"),
    "time": now.strftime("%H:%M"),
    "weekday": now.weekday(),
    "soc": final_soc,
    "range_km": final_rng,
    "odometer": final_odo,
    "limit_soc": int(round(lim)) if lim is not None else 80,
    "charging_state": c_state,
    "charge_power_kw": round(pwr, 1),
    "charge_type": "dc" if pwr > 12 else "ac"
}

json.dump(db, open(DB, "w"), indent=2)
print(f"SINCRONIZAT: SoC={final_soc}% | Range={final_rng}km | Odo={final_odo}km | Status={c_code}")
