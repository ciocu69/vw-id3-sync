import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "vw_data.json"
CAP = 58.0

TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

raw = open("evcc_out.txt").read() if os.path.exists("evcc_out.txt") else ""

def get_val(pat):
    m = re.search(pat, raw, re.I)
    return float(m.group(1).replace(",", ".")) if m else None

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Telegram info: Cheile nu sunt setate in Secrets.")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload)
        urllib.request.urlopen(req, timeout=5)
        print("Notificare Telegram trimisa cu succes!")
    except Exception as e:
        print(f"Telegram warning: {e}")

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
final_lim = int(round(lim)) if lim is not None else 80
energy_kwh = round((final_soc / 100.0) * CAP, 2)

# Fortam starea de incarcare daca EVCC zice ca e in priza/incarca SAU daca bateria a crescut fata de runda trecuta!
p_soc_prev = prev.get("soc", final_soc)
soc_diff_check = final_soc - p_soc_prev
is_chg = (c_code == "C" or pwr > 0.5 or soc_diff_check >= 1)

c_state = "charging" if is_chg else ("connected" if c_code == "B" else "ready")
c_type = "dc" if pwr > 12 else "ac"

notified = False

if prev and "soc" in prev and "odometer" in prev:
    p_soc = prev["soc"]
    p_odo = prev["odometer"]
    p_time = prev.get("time", time_str)
    dist = final_odo - p_odo
    soc_diff = final_soc - p_soc

    # 1. Detectie DRUM REAL (minim 2 km si SoC scazut/egal)
    if dist >= 2 and soc_diff <= 0:
        used_kwh = round(abs(soc_diff) * CAP / 100.0, 2)
        cons = round((used_kwh / dist) * 100.0, 1) if dist > 0 else 0.0
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

    # 2. Detectie & Comasare SESIUNE DE INCARCARE (datorita cresterii SoC, chiar daca VW zice Parked)
    elif soc_diff >= 1:
        if sessions and sessions[0].get("date") == date_str and abs(sessions[0].get("odometer", 0) - final_odo) <= 2:
            cur_s = sessions[0]
            cur_s["end_time"] = time_str
            cur_s["end_soc"] = final_soc
            total_diff = final_soc - cur_s["start_soc"]
            cur_s["added_kwh"] = round((total_diff * CAP) / 100.0, 2)
            cur_s["max_power_kw"] = max(cur_s.get("max_power_kw", 11.0), pwr)
            cur_s["in_progress"] = is_chg
        else:
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
                "cost_ron": 0.0,
                "in_progress": is_chg
            })
            sessions = sessions[:100]

        # Notificare automata pe Telegram la praguri de 10% (ex: 50%, 60%, 70%, 80%) sau la atingerea limitei
        if (final_soc // 10) > (p_soc // 10) or final_soc >= final_lim:
            start_s = sessions[0]["start_soc"]
            added_s = sessions[0]["added_kwh"]
            if final_soc >= final_lim or not is_chg:
                send_telegram(
                    f"✅ <b>Încărcare finalizată / Limită atinsă ({final_soc}%)</b>\n"
                    f"🔋 Sesiune: <b>{start_s}% → {final_soc}%</b> (+{added_s} kWh)\n"
                    f"🛣️ Autonomie: <b>~{final_rng} km</b> | Bord: {final_odo} km"
                )
            else:
                send_telegram(
                    f"⚡ <b>Recording of charging session in progress</b>\n"
                    f"ID.3 has recently reached a charge level of <b>{final_soc}%</b>.\n"
                    f"🔋 Pornit de la: {start_s}% (+{added_s} kWh) | Limită: {final_lim}%"
                )
            notified = True

# 3. NOTIFICARE DE TEST (Doar la rulare manuala din Actions)
if EVENT_NAME == "workflow_dispatch" and not notified:
    send_telegram(
        f"🟢 <b>Test Conexiune VW ID.3 Live</b>\n"
        f"🔋 Baterie: <b>{final_soc}%</b> ({energy_kwh} / {CAP} kWh)\n"
        f"🛣️ Autonomie: <b>~{final_rng} km</b>\n"
        f"🔢 Odometru: <b>{final_odo} km</b>\n"
        f"🔌 Status: <b>{c_state.upper()}</b> (Limită: {final_lim}%)\n"
        f"🕒 Sincronizat: {now_str}"
    )

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
    "limit_soc": final_lim,
    "charging_state": c_state,
    "charge_power_kw": round(pwr, 1),
    "charge_type": c_type
}
db["trips"] = trips
db["sessions"] = sessions

json.dump(db, open(DB, "w"), indent=2, ensure_ascii=False)
print(f"OK: SoC={final_soc}% | Odo={final_odo}km | Status={c_state}")
