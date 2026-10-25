from datetime import datetime
import json
import os
import re
from zoneinfo import ZoneInfo

BATTERY_NET_KWH = 58.0
DB_FILE = "vw_data.json"
EVCC_OUT_FILE = "evcc_out.txt"

if os.path.exists(DB_FILE):
  with open(DB_FILE, "r", encoding="utf-8") as f:
    db = json.load(f)
else:
  db = {"last_state": {}, "active_charge": None, "sessions": []}

active_charge = db.get("active_charge")

if os.path.exists(EVCC_OUT_FILE):
  with open(EVCC_OUT_FILE, "r", encoding="utf-8") as f:
    raw = f.read()
else:
  raw = ""


def extract_num(pattern, text, default=0.0):
  m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
  if m:
    try:
      return float(m.group(1).replace(",", "."))
    except:
      return default
  return default


soc_pct = int(round(extract_num(r"SoC:\s*([\d.,]+)\s*%", raw, 68.0)))
range_km = int(round(extract_num(r"Range:\s*([\d.,]+)\s*km", raw, 229.0)))
odometer = int(round(extract_num(r"Odometer:\s*([\d.,]+)\s*km", raw, 38693.0)))
charge_power = round(
    extract_num(r"(?:Charge power|Power):\s*([\d.,]+)\s*kW", raw, 0.0), 1
)

ro_now = datetime.now(ZoneInfo("Europe/Bucharest"))
last_odo = db.get("last_state", {}).get("odometer", 38693)
final_odometer = odometer if odometer > 0 else last_odo

state = {
    "timestamp": ro_now.strftime("%d.%m.%Y %H:%M"),
    "date": ro_now.strftime("%d.%m.%Y"),
    "time": ro_now.strftime("%H:%M"),
    "weekday": ro_now.weekday(),
    "soc": soc_pct,
    "range_km": range_km,
    "odometer": final_odometer,
    "charging_state": "ready",
    "charge_power_kw": charge_power,
    "charge_type": "ac",
}

db["last_state"] = state
with open(DB_FILE, "w", encoding="utf-8") as f:
  json.dump(db, f, indent=2, ensure_ascii=False)

print(
    f"SALVAT CU SUCCES: SoC={soc_pct}% | Range={range_km}km |"
    f" Odometer={final_odometer}km"
)
