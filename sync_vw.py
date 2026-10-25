import asyncio, json, os
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import ClientSession
from volkswagencarnet.vw_connection import Connection

VW_USER = os.environ["VW_USER"].strip()
VW_PASS = os.environ["VW_PASS"].strip()
BATTERY_NET_KWH = 58.0
DB_FILE = "vw_data.json"


async def main():
  # 1. Citim baza de date din GitHub
  if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
      db = json.load(f)
  else:
    db = {"last_state": {}, "active_charge": None, "sessions": []}

  active_charge = db.get("active_charge")

  # 2. Conectare cu noul protocol myVolkswagen
  async with ClientSession() as session:
    conn = Connection(session, VW_USER, VW_PASS)
    await conn.doLogin()
    await conn.update()

    if not conn.vehicles:
      raise Exception("Nu s-a gasit nicio masina in contul Volkswagen!")

    vehicle = conn.vehicles[0]
    target_vin = vehicle.vin

    soc_pct = getattr(vehicle, "battery_level", 0) or 0
    range_km = getattr(vehicle, "electric_range", 0) or 0
    odometer = getattr(vehicle, "odometer", 0) or 0
    is_charging_bool = bool(getattr(vehicle, "charging", False))
    charge_power = float(getattr(vehicle, "charging_power", 0.0) or 0.0)
    charge_state = "charging" if is_charging_bool else "ready"

    ro_now = datetime.now(ZoneInfo("Europe/Bucharest"))

    state = {
        "vin": target_vin,
        "timestamp": ro_now.strftime("%d.%m.%Y %H:%M"),
        "date": ro_now.strftime("%d.%m.%Y"),
        "time": ro_now.strftime("%H:%M"),
        "weekday": ro_now.weekday(),
        "soc": int(soc_pct),
        "range_km": int(range_km),
        "odometer": int(odometer),
        "charging_state": charge_state,
        "charge_power_kw": charge_power,
        "charge_type": "dc" if charge_power > 12 else "ac",
    }

    # 3. Detectie automata Start / Stop incarcare
    if is_charging_bool:
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
              "id": (
                  f"{active_charge['start_date']}_{active_charge['start_time']}"
              ),
              "date": active_charge["start_date"],
              "interval": f"{active_charge['start_time']} - {state['time']}",
              "soc_interval": (
                  f"{active_charge['start_soc']}% -> {state['soc']}%"
              ),
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
        f"Sync reusit: VIN={target_vin} | SoC={soc_pct}% | Km={odometer} |"
        f" Putere={charge_power} kW"
    )


if __name__ == "__main__":
  asyncio.run(main())
  
