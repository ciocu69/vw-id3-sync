import json, os, re
from datetime import datetime
from zoneinfo import ZoneInfo

BATTERY_NET_KWH = 58.0
DB_FILE = "vw_data.json"
EVCC_OUT_FILE = "evcc_out.txt"

# 1. Incarcam baza de date existenta
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
else:
    db = {"last_state": {}, "active_charge": None, "sessions": []}

active_charge = db.get("active_charge")

# 2. Citim textul brut din EVCC
raw = ""
if os.path.exists(EVCC_OUT_FILE):
    with open(EVCC_OUT_FILE, "r", encoding="utf-8") as f:
        raw = f.read()

# Curatam secventele de escape ANSI (culori terminal)
clean_raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)

print("=== RAW EVCC OUTPUT CURATAT ===")
print(clean_raw)
print("================================")

def extract_val(pattern, text):
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        val_str = m.group(1).replace(",", ".").strip()
        try:
            return float(val_str)
        except:
            return None
    return None

# Extragere valori reale (fara fallback la valori vechi fixe!)
soc_val = extract_val(r"SoC:\s*([\d.,]+)\s*%", clean_raw)
range_val = extract_val(r"Range:\s*([\d.,]+)\s*km", clean_raw)
odo_val = extract_val(r"Odometer:\s*([\d.,]+)\s*km", clean_raw)
power_val = extract_val(r"(?:Charge power|Power):\s*([\d.,]+)\s*kW", clean_raw)

# Preluam starea anterioara salvata doar daca masina nu a raportat la aceasta interogare
prev_state = db.get("last_state", {})
soc_pct = int(round(soc_val)) if soc_val is not None else prev_state.get("soc", 0)
range_km = int(round(range_val)) if range_val is not None else prev_state.get("range_km", 0)
odometer = int(round(odo_val)) if odo_val is not None else prev_state.get("odometer", 0)
charge_power = round(power_val, 1) if power_val is not None else 0.0

# Status incarcare
status_m = re.search(r"Charge status:\s*([^\n\r]+)", clean_raw, re.IGNORECASE)
raw_status = status_m.group(1).strip() if status_m else "Unknown"

is_charging = (raw_status.upper().startswith("C") or "CHARGING" in raw_status.upper() or charge_power > 0.5)
charge_state = "charging" if is_charging else ("connected" if raw_status.upper().startswith("B") else "ready")

ro_now = datetime.now(ZoneInfo("Europe/Bucharest"))

state = {
    "timestamp": ro_now.strftime("%d.%m.%Y %H:%M"),
    "date": ro_now.strftime("%d.%m.%Y"),
    "time": ro_now.strftime("%H:%M"),
    "weekday": ro_now.weekday(),
    "soc": soc_pct,
    "range_km": range_km,
    "odometer": odometer,
    "charging_state": charge_state,
    "raw_status": raw_status,
    "charge_power_kw": charge_power,
    "charge_type": "dc" if charge_power > 12 else "ac"
}

# 3. Detectie automata a sesiunilor de incarcare
if is_charging:
    if not active_charge:
        active_charge = {
            "start_date": state["date"],
            "start_time": state["time"],
            "start_soc": state["soc"],
            "odometer": state["odometer"],
            "max_power_kw": state["charge_power_kw"] if state["charge_power_kw"] > 0 else 11.0,
            "weekday": state["weekday"]
        }
    else:
        if state["charge_power_kw"] > active_charge.get("max_power_kw", 0):
            active_charge["max_power_kw"] = state["charge_power_kw"]
        if state["odometer"] > 0:
            active_charge["odometer"] = state["odometer"]
else:
    if active_charge:
        soc_diff = state["soc"] - active_charge["start_soc"]
        if soc_diff > 2:
            kwh_added = round((soc_diff / 100.0) * BATTERY_NET_KWH, 1)
            max_p = active_charge.get("max_power_kw", 11.0)
            
            if max_p > 12:
                station_rule = "Cartier DC (50 kW - 2.49 lei)"
            elif active_charge["weekday"] < 5 and "08:00" <= active_charge["start_time"] <= "18:30":
                station_rule = "Birou - GRATIS (22 kW)"
            else:
                station_rule = "Cartier AC (22 kW - 1.99 lei)"

            new_session = {
                "id": f"{active_charge['start_date']}_{active_charge['start_time']}",
                "date": active_charge["start_date"],
                "interval": f"{active_charge['start_time']} - {state['time']}",
                "soc_interval": f"{active_charge['start_soc']}% -> {state['soc']}%",
                "kwh": kwh_added,
                "max_power_kw": max_p,
                "odometer": state["odometer"] or active_charge["odometer"],
                "suggested_station": station_rule
            }
            db["sessions"].insert(0, new_session)
        active_charge = None

db["last_state"] = state
db["active_charge"] = active_charge

with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"REZULTAT ACTUALIZAT: SoC={soc_pct}% | Range={range_km}km | Odometer={odometer}km")
