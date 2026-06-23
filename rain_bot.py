import requests
from datetime import datetime
import pytz

# ── CONFIG ──
TG_TOKEN = "8611542903:AAGtPB9oNeCUYMpy3SS5aXr0fuZiHjGJumQ"
TG_CHAT_ID = "-1003908019472"
LAT = 11.564137
LON = 104.916075
CITY = "Phnom Penh"
TZ = pytz.timezone("Asia/Phnom_Penh")

# 8 scan points around location at ~50km
SCAN = [
  ("N",  LAT+0.45, LON),
  ("NE", LAT+0.32, LON+0.45),
  ("E",  LAT,      LON+0.55),
  ("SE", LAT-0.32, LON+0.45),
  ("S",  LAT-0.45, LON),
  ("SW", LAT-0.32, LON-0.45),
  ("W",  LAT,      LON-0.55),
  ("NW", LAT+0.32, LON-0.45),
]

def wmo_desc(code):
    if code == 0: return "Clear Sky ☀️"
    if code <= 2: return "Partly Cloudy ⛅"
    if code == 3: return "Overcast ☁️"
    if code <= 49: return "Foggy 🌫️"
    if code <= 57: return "Drizzle 🌦️"
    if code <= 67: return "Rain 🌧️"
    if code <= 82: return "Showers 🌦️"
    if code <= 99: return "Thunderstorm ⛈️"
    return "Unknown"

def wind_dir(deg):
    return ['N','NE','E','SE','S','SW','W','NW'][round(deg/45)%8]

def fetch_weather(lat, lon):
    now_hour = datetime.now(TZ).strftime("%Y-%m-%dT%H")
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,rain,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,pressure_msl,uv_index,precipitation",
        "hourly": "precipitation_probability,weather_code,cloud_cover",
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "timezone": "Asia/Bangkok", "forecast_days": 1
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
    r.raise_for_status()
    d = r.json()
    c = d["current"]
    h = d["hourly"]
    daily = d["daily"]
    idx = next((i for i,t in enumerate(h["time"]) if t.startswith(now_hour)), 0)
    rain_prob = h["precipitation_probability"][idx] or 0
    return {
        "temp": c.get("temperature_2m"),
        "feels": c.get("apparent_temperature"),
        "humidity": c.get("relative_humidity_2m"),
        "cloud": c.get("cloud_cover"),
        "wind_spd": c.get("wind_speed_10m"),
        "wind_dir": wind_dir(c.get("wind_direction_10m", 0)),
        "rain": c.get("rain", 0),
        "wcode": c.get("weather_code", 0),
        "pressure": round(c.get("pressure_msl", 0)),
        "uv": c.get("uv_index", 0),
        "rain_prob": rain_prob,
        "temp_max": daily["temperature_2m_max"][0],
        "temp_min": daily["temperature_2m_min"][0],
        "rain_sum": daily["precipitation_sum"][0],
        "max_prob": daily["precipitation_probability_max"][0],
        "desc": wmo_desc(c.get("weather_code", 0)),
    }

def scan_directions():
    results = []
    for (direction, lat, lon) in SCAN:
        try:
            now_hour = datetime.now(TZ).strftime("%Y-%m-%dT%H")
            params = {
                "latitude": lat, "longitude": lon,
                "current": "weather_code,cloud_cover,rain",
                "hourly": "precipitation_probability,weather_code",
                "timezone": "Asia/Bangkok", "forecast_days": 1
            }
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
            d = r.json()
            h = d["hourly"]
            idx = next((i for i,t in enumerate(h["time"]) if t.startswith(now_hour)), 0)
            rain_prob = h["precipitation_probability"][idx] or 0
            wcode = d["current"]["weather_code"]
            cloud = d["current"]["cloud_cover"]
            results.append((direction, rain_prob, wcode, cloud))
        except:
            pass
    return results

def classify(rain_prob, wcode, cloud):
    if wcode >= 80: return "⛈ Storm Cloud (EXTREME)"
    if wcode >= 61 or rain_prob >= 60: return "🌧 Nimbostratus Rain Cloud (HIGH)"
    if wcode >= 51 or rain_prob >= 40: return "🌦 Altostratus Rain Cloud (MODERATE)"
    if cloud >= 70 or rain_prob >= 25: return "☁ Dark Stratocumulus (LOW)"
    if cloud >= 40: return "⛅ Cumulus (WATCH)"
    return "☀ Clear"

def send_telegram(message):
    for cid in [TG_CHAT_ID, "@cambodiarain8888"]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": message, "parse_mode": "HTML"},
                timeout=15
            )
            if r.json().get("ok"):
                print(f"✅ Sent to {cid}")
                return True
            print(f"⚠ {cid}: {r.json().get('description')}")
        except Exception as e:
            print(f"❌ {e}")
    return False

def main():
    now = datetime.now(TZ)
    now_str = now.strftime("%d/%m/%Y %H:%M")
    print(f"🌧 Bot starting — {now_str}")

    w = fetch_weather(LAT, LON)
    directions = scan_directions()

    is_rain = w["rain_prob"] >= 50 or (61 <= w["wcode"] <= 99)

    # AI score
    score = 0
    if w["rain_prob"] >= 60: score += 30
    elif w["rain_prob"] >= 30: score += 15
    if w["cloud"] >= 70: score += 20
    elif w["cloud"] >= 40: score += 10
    if w["humidity"] >= 75: score += 20
    elif w["humidity"] >= 55: score += 10
    if 61 <= w["wcode"] <= 99: score += 25
    elif w["wcode"] >= 51: score += 12
    score = min(score, 99)
    confidence = min(99, score + round(w["rain_prob"] * 0.3))

    if is_rain:
        signal = "🌧 RAIN EXPECTED"
        advice = "⚠️ Please bring umbrella or find shelter!"
        bar = "🟦🟦🟦🟦🟦"
    elif w["rain_prob"] >= 30:
        signal = "⚠️ POSSIBLE RAIN"
        advice = "🌂 Carry umbrella just in case."
        bar = "🟦🟦🟦⬜⬜"
    else:
        signal = "☀️ NO RAIN"
        advice = "✅ Conditions favorable. Enjoy your day!"
        bar = "🟩🟩🟩🟩🟩"

    # Direction scan summary
    rain_dirs = [(d,p,c,cl) for (d,p,c,cl) in directions if p >= 30 or (61 <= c <= 99)]
    compass_lines = ""
    if rain_dirs:
        compass_lines = "\n\n🧭 <b>Cloud Systems Detected (100km):</b>"
        for (d, p, c, cl) in sorted(rain_dirs, key=lambda x: -x[1]):
            ctype = classify(p, c, cl)
            compass_lines += f"\n• <b>{d}</b> ~50km — {p}% rain — {ctype}"
    else:
        compass_lines = "\n\n🧭 <b>100km Scan:</b> No rain clouds detected ☀️"

    msg = f"""🌧 <b>Cambodia Rain 8888 — AI Weather Report</b>
📍 Phnom Penh, Cambodia
📌 11.5641°N, 104.9161°E
🕐 {now_str}

<b>{signal}</b>
Rain Probability: <b>{w['rain_prob']}%</b>
Signal: {bar}

━━━━━━━━━━━━━━━━
🌡 Temp: <b>{w['temp']}°C</b> (feels {w['feels']}°C)
💧 Humidity: <b>{w['humidity']}%</b>
☁️ Cloud Cover: <b>{w['cloud']}%</b>
🌬 Wind: <b>{w['wind_spd']} km/h {w['wind_dir']}</b>
🌧 Rain Now: <b>{w['rain']} mm</b>
📊 Condition: <b>{w['desc']}</b>
🔆 UV Index: <b>{w['uv']}</b>
📉 Pressure: <b>{w['pressure']} hPa</b>

━━━━━━━━━━━━━━━━
📅 Today:
🔺 Max: {w['temp_max']}°C  🔻 Min: {w['temp_min']}°C
🌧 Rain Total: {w['rain_sum']} mm
💡 Max Rain Prob: {w['max_prob']}%{compass_lines}

━━━━━━━━━━━━━━━━
🤖 AI Score: <b>{score}/99</b> | Confidence: <b>{confidence}%</b>
{advice}

📡 @cambodiarain8888 | <b>MR TP AI Weather</b>"""

    print(f"📤 Sending message ({len(msg)} chars)…")
    ok = send_telegram(msg)
    if ok:
        print("✅ Done!")
    else:
        print("❌ Failed to send.")
        exit(1)

if __name__ == "__main__":
    main()
