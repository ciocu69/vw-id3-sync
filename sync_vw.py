import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "vw_data.json"
CAP = 58.0
raw = open("evcc_out.txt").read() if os.path.exists("evcc_out.txt") else ""

def get_val(pat):
    m = re.search(pat, raw, re.I)
    return float(m.group(1).replace(",", ".")) if m else None

soc = get_val(r"SoC:\s*([\d.,]+)\s*%")
rng = get_val(r"Range:\s*([\d.,]+)\s*km")
odo = get_val(r"Odometer:\s*([\d.,]+)\s*km")
lim = get_val(r"Limit Soc:\s*([\d.,]+)\s*%")
pwr = get_val(r"(?:Charge power|Power):\s*([\d.,]+)\s*kW") or 0.0

st_m = re.search(r"Charge status:\s*([A-Z])", raw, re.I)
c_code = st_m.group(1).upper() if st_m else "A"

if soc is None:
    print("EROARE: EVCC nu a returnat SoC valid.")
    sys.exit(1)

db = json.load(open(DB)) if os.path.exists(DB) else {}
prev = db.get("last_state", {})
trips = db.get("trips", [])
sessions = db.get("sessions", [])

now = datetime.now(ZoneInfo("Europe/Bucharest"))
now_str = now.strftime("%d.%m.%Y %H:%M")
date_str = now.strftime("%d.%m.%Y")
time_str = now.strftime("%H:%M")

final_soc = int(round(soc))
final_odo = int(round(odo)) if odo is not None else prev.get("odometer", 0)
final_rng = int(round(rng)) if rng is not None else int(round(final_soc * 3.2))
energy_kwh = round((final_soc / 100.0) * CAP, 2)

is_chg = (c_code == "C" or pwr > 0.5)
c_state = "charging" if is_chg else ("connected" if c_code == "B" else "ready")
c_type = "dc" if pwr > 12 else "ac"

# Comparatie cu starea anterioara pentru detectie automata Trip sau Charge
if prev and "soc" in prev and "odometer" in prev:
    p_soc = prev["soc"]
    p_odo = prev["odometer"]
    p_time = prev.get("time", time_str)
    p_date = prev.get("date", date_str)
    dist = final_odo - p_odo
    soc_diff = final_soc - p_soc

    # 1. Detectie DRUM (Trip): Odometrul a crescut si SoC a scazut sau a ramas egal
    if dist >= 1 and soc_diff <= 0:
        used_kwh = round(abs(soc_diff) * CAP / 100.0, 2)
        cons = round((used_kwh / dist) * 100.0, 1) if dist > 0 else 0.0
        # Daca ultimul trip e din aceeasi zi si acum mai putin de 45 min, il comasam
        trips.insert(0, {
            "id": f"trip_{int(now.timestamp())}",
            "date": date_str,
            "start_time": p_time,
            "end_time": time_str,
            "start_soc": p_soc,
            "end_soc": final_soc,
            "distance_km": dist,
            "energy_used_kwh": used_kwh,
            "consumption_kwh_100km": cons,
            "odometer_end": final_odo
        })
        trips = trips[:200]

    # 2. Detectie INCARCARE (Charge): SoC a crescut cu cel putin 2%
    elif soc_diff >= 2:
        added_kwh = round((soc_diff * CAP) / 100.0, 2)
        sessions.insert(0, {
            "id": f"chg_{int(now.timestamp())}",
            "date": date_str,
            "start_time": p_time,
            "end_time": time_str,
            "start_soc": p_soc,
            "end_soc": final_soc,
            "added_kwh": added_kwh,
            "charge_type": prev.get("charge_type", c_type).upper(),
            "max_power_kw": max(pwr, prev.get("charge_power_kw", 11.0)),
            "odometer": final_odo,
            "tag": "Birou (0 RON)" if c_type == "ac" else "Public DC",
            "cost_ron": 0.0
        })
        sessions = sessions[:100]

db["last_state"] = {
    "timestamp": now_str,
    "date": date_str,
    "time": time_str,
    "weekday": now.weekday(),
    "soc": final_soc,
    "battery_capacity_kwh": CAP,
    "current_energy_kwh": energy_kwh,
    "range_km": final_rng,
    "odometer": final_odo,
    "limit_soc": int(round(lim)) if lim is not None else 80,
    "charging_state": c_state,
    "charge_power_kw": round(pwr, 1),
    "charge_type": c_type
}
db["trips"] = trips
db["sessions"] = sessions

json.dump(db, open(DB, "w"), indent=2, ensure_ascii=False)
print(f"OK: SoC={final_soc}% | Odo={final_odo}km | Trips={len(trips)} | Charges={len(sessions)}")
