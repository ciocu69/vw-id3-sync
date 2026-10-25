from datetime import datetime
import json, os
from zoneinfo import ZoneInfo
from weconnect import weconnect

VW_USER = os.environ["VW_USER"]
VW_PASS = os.environ["VW_PASS"]
BATTERY_NET_KWH = 58.0
DB_FILE = "vw_data.json"

# 1. Citim baza de date direct din GitHub
if os.path.exists(DB_FILE):
  with open(DB_FILE, "r", encoding="utf-8") as f:
    db = json.load(f)
else:
  db = {"last_state": {}, "active_charge": None, "sessions": []}

active_charge = db.get("active_charge")

# 2. Ne conectam la serverele Volkswagen
wc = weconnect.WeConnect(
    username=VW_USER, password=VW_PASS, updateAfterLogin=False
)
wc.login()
wc.update()

target_vin = list(wc.vehicles.keys())[0]
vehicle = wc.vehicles[target_vin]

soc_pct = vehicle.domains["charging"]["batteryStatus"].currentSOC_pct.value
range_km = (
    vehicle.domains["charging"]["batteryStatus"].cruisingRangeElectric_km.value
)
odometer = (
    vehicle.domains["measurements"]["odometerStatus"].odometer.value
    if "measurements" in vehicle.domains
    else 0
)
charge_state = str(
    vehicle.domains["charging"]["chargingStatus"].chargingState.value
)
charge_power = vehicle.domains["charging"]["chargingStatus"].chargePower_kW.value
charge_type = str(
    vehicle.domains["charging"]["chargingStatus"].chargeType.value
)

ro_now = datetime.now(ZoneInfo("Europe/Bucharest"))

state = {
    "vin": target_vin,
    "timestamp": ro_now.strftime("%d.%m.%Y %H:%M"),
    "date": ro_now.strftime("%d.%m.%Y"),
    "time": ro_now.strftime("%H:%M"),
    "weekday": ro_now.weekday(),
    "soc": soc_pct,
    "range_km": range_km,
    "odometer": odometer,
    "charging_state": charge_state,
    "charge_power_kw": float(charge_power) if charge_power else 0.0,
    "charge_type": charge_type,
}

# 3. Detectie automata Start / Stop incarcare
is_charging = charge_state.lower() in [
    "charging",
    "conservation",
    "chargepurpose",
]

if is_charging:
  if not active_charge:
    active_charge = {
        "start_date": state["date"],
        "start_time": state["time"],
        "start_soc": state["soc"],
        "odometer": state["odometer"],
        "max_power_kw": state["charge_power_kw"],
        "weekday": state["weekday"],
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
      max_p = active_charge.get("max_power_kw", 0)

      if max_p > 12:
        station_rule = "Cartier DC (50 kW - 2.49 lei)"
      elif (
          active_charge["weekday"] < 5
          and "08:00" <= active_charge["start_time"] <= "18:30"
      ):
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
          "suggested_station": station_rule,
      }
      db["sessions"].insert(0, new_session)
    active_charge = None

db["last_state"] = state
db["active_charge"] = active_charge

with open(DB_FILE, "w", encoding="utf-8") as f:
  json.dump(db, f, indent=2, ensure_ascii=False)

print(
    f"Sync reusit: {soc_pct}% | {odometer} km | Putere:"
    f" {state['charge_power_kw']} kW"
)
