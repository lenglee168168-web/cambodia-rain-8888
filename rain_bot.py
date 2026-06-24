import requests
import pytz
from datetime import datetime
import math

# ── CONFIG ──
TG_TOKEN = "8611542903:AAGtPB9oNeCUYMpy3SS5aXr0fuZiHjGJumQ"
# Your channel chat ID from the message you shared
TG_CHAT_ID = "1003908019472"  # will try multiple formats
LAT = 11.564137
LON = 104.916075
CITY = "Phnom Penh"
TZ = pytz.timezone("Asia/Phnom_Penh")

# 8 scan directions around location
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
    if code == 0: return "Clear Sky \u2600\ufe0f"
    if code <= 2: return "Partly Cloudy \u26c5"
    if code == 3: return "Overcast \u2601\ufe0f"
    if code <= 49: return "Foggy \ud83c\udf2b\ufe0f"
    if code <= 57: return "Drizzle \ud83c\udf26\ufe0f"
    if code <= 67: return "Rain \ud83c\udf27\ufe0f"
    if code <= 82: return "Showers \ud83c\udf26\ufe0f"
    if code <= 99: return "Thunderstorm \u26c8\ufe0f"
    return "Unknown"

def wind_dir(deg):
    dirs = ['N','NE','E','SE','S','SW','W','NW']
    return dirs[round(deg / 45) % 8]

def classify_cloud(rp, wc, cloud):
    if wc >= 80: return "Cumulonimbus (STORM)"
    if wc >= 61 or rp >= 60: return "Nimbostratus (HEAVY RAIN)"
    if wc >= 51 or rp >= 40: return "Altostratus (RAIN CLOUD)"
    if cloud >= 70 or rp >= 25: return "Stratocumulus (DARK CLOUD)"
    if cloud >= 40: return "Cumulus (WATCH)"
    return "Clear Sky"

def fetch_weather(lat, lon):
    now_h = datetime.now(TZ).strftime("%Y-%m-%dT%H")
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,rain,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,pressure_msl,uv_index,precipitation,dew_point_2m",
        "hourly": "precipitation_probability,weather_code,cloud_cover",
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "timezone": "Asia/Bangkok",
        "forecast_days": 1
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
    r.raise_for_status()
    d = r.json()
    c = d["current"]
    h = d["hourly"]
    dy = d["daily"]
    idx = next((i for i, t in enumerate(h["time"]) if t.startswith(now_h)), 0)
    rp = h["precipitation_probability"][idx] or 0
    return c, rp, dy

def scan_directions():
    now_h = datetime.now(TZ).strftime("%Y-%m-%dT%H")
    results = []
    for (direction, la, lo) in SCAN:
        try:
            params = {
                "latitude": la, "longitude": lo,
                "current": "weather_code,cloud_cover,rain",
                "hourly": "precipitation_probability",
                "timezone": "Asia/Bangkok",
                "forecast_days": 1
            }
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
            d = r.json()
            h = d["hourly"]
            idx = next((i for i, t in enumerate(h["time"]) if t.startswith(now_h)), 0)
            rp = h["precipitation_probability"][idx] or 0
            wc = d["current"]["weather_code"]
            cloud = d["current"]["cloud_cover"]
            # Approximate km distance (~50km per 0.45 deg lat)
            dist_km = 50
            results.append((direction, rp, wc, cloud, dist_km))
        except Exception as e:
            print(f"  Scan {direction} failed: {e}")
    return results

def try_get_chat_id():
    """Try to find the correct chat_id by checking bot updates"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("ok") and data.get("result"):
            for update in reversed(data["result"]):
                msg = update.get("channel_post") or update.get("message") or {}
                chat = msg.get("chat", {})
                if chat.get("id"):
                    print(f"  Found chat_id from updates: {chat['id']}")
                    return str(chat["id"])
    except Exception as e:
        print(f"  getUpdates error: {e}")
    return None

def send_telegram(message, chat_id):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        result = r.json()
        if result.get("ok"):
            return True, None
        return False, result.get("description", "Unknown error")
    except Exception as e:
        return False, str(e)

def build_message(c, rp, dy, scan_results):
    now = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    wc = c.get("weather_code", 0)
    desc = wmo_desc(wc)
    is_rain = rp >= 50 or (61 <= wc <= 99)

    # AI score
    score = 0
    cc = c.get("cloud_cover", 0)
    hum = c.get("relative_humidity_2m", 0)
    if rp >= 60: score += 30
    elif rp >= 30: score += 15
    if cc >= 70: score += 20
    elif cc >= 40: score += 10
    if hum >= 75: score += 20
    elif hum >= 55: score += 10
    if 61 <= wc <= 99: score += 25
    elif wc >= 51: score += 12
    score = min(score, 99)
    conf = min(99, score + round(rp * 0.3))

    bar = "🟦🟦🟦🟦🟦" if rp >= 60 else ("🟦🟦🟦⬜⬜" if rp >= 30 else "🟩🟩🟩🟩🟩")
    sig = "🌧 RAIN EXPECTED" if is_rain else "☀️ NO RAIN"

    # Compass scan summary - only show rain/cloud systems
    rain_systems = [(d,p,w,cl,km) for (d,p,w,cl,km) in scan_results if p >= 25 or (51 <= w <= 99) or cl >= 70]
    compass_lines = ""
    if rain_systems:
        compass_lines = "\n\n🧭 <b>Cloud Systems Detected (50km scan):</b>"
        for (d, p, w, cl, km) in sorted(rain_systems, key=lambda x: -x[1]):
            ctype = classify_cloud(p, w, cl)
            compass_lines += f"\n• <b>{d}</b> ~{km}km — {p}% rain — {ctype}"
    else:
        compass_lines = "\n\n🧭 No significant rain clouds within 50km ☀️"

    msg = f"""🌧 <b>Cambodia Rain 8888 — AI Weather Report</b>
📍 {CITY} | 11.5641°N, 104.9161°E
🕐 {now}

<b>{sig}</b>
{bar} {rp}% rain probability

━━━━━━━━━━━━━━━━━━━
🌡 Temp: <b>{c.get('temperature_2m')}°C</b> (feels {c.get('apparent_temperature')}°C)
💧 Humidity: <b>{hum}%</b>
☁️ Cloud Cover: <b>{cc}%</b>
🌬 Wind: <b>{c.get('wind_speed_10m')} km/h {wind_dir(c.get('wind_direction_10m', 0))}</b>
🌧 Rain Now: <b>{c.get('rain', 0)} mm</b>
📊 Condition: <b>{desc}</b>
🔆 UV Index: <b>{c.get('uv_index', 0)}</b>
📉 Pressure: <b>{round(c.get('pressure_msl', 0))} hPa</b>

━━━━━━━━━━━━━━━━━━━
📅 Today:
🔺 Max: {dy['temperature_2m_max'][0]}°C  🔻 Min: {dy['temperature_2m_min'][0]}°C
🌧 Rain Total: {dy['precipitation_sum'][0]} mm
💡 Max Rain Prob: {dy['precipitation_probability_max'][0]}%{compass_lines}

━━━━━━━━━━━━━━━━━━━
🤖 AI Score: <b>{score}/99</b> | Confidence: <b>{conf}%</b>
{'⚠️ Bring umbrella or find shelter now!' if is_rain else '✅ Conditions favorable. Enjoy your day!'}

📡 @cambodiarain8888 | <b>MR TP AI Weather</b>"""
    return msg

def main():
    now_str = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    print(f"🌧 Cambodia Rain 8888 Bot")
    print(f"🕐 Time: {now_str}")
    print(f"📍 Location: {CITY} ({LAT}, {LON})")
    print()

    # Step 1: Fetch weather
    print("📡 Fetching weather data...")
    c, rp, dy = fetch_weather(LAT, LON)
    print(f"✅ Weather OK — Rain prob: {rp}%, Temp: {c.get('temperature_2m')}°C")

    # Step 2: Scan directions
    print("\n🧭 Scanning 8 directions...")
    scan_results = scan_directions()
    print(f"✅ Scan done — {len(scan_results)} directions checked")

    # Step 3: Build message
    msg = build_message(c, rp, dy, scan_results)
    print(f"\n📝 Message built ({len(msg)} chars)")

    # Step 4: Try to get correct chat_id from bot updates
    print("\n🔍 Checking bot for chat IDs...")
    found_id = try_get_chat_id()

    # Step 5: Try all possible chat_id formats
    chat_ids_to_try = []
    if found_id:
        chat_ids_to_try.append(found_id)

    # Common formats for the ID 1003908019472
    chat_ids_to_try += [
        "-1001003908019472",   # supergroup format (add -100 prefix)
        "-1003908019472",      # as given
        "@cambodiarain8888",   # username
        "1003908019472",       # raw number
    ]
    # Remove duplicates
    seen = set()
    unique_ids = []
    for cid in chat_ids_to_try:
        if cid not in seen:
            seen.add(cid)
            unique_ids.append(cid)

    print(f"\n📤 Trying {len(unique_ids)} chat ID formats...")
    sent = False
    for cid in unique_ids:
        print(f"  Trying: {cid}")
        ok, err = send_telegram(msg, cid)
        if ok:
            print(f"  ✅ SUCCESS with chat_id: {cid}")
            sent = True
            break
        else:
            print(f"  ❌ Failed: {err}")

    print()
    if sent:
        print("✅ Bot completed successfully!")
        print("📱 Check @cambodiarain8888 on Telegram")
    else:
        print("❌ All chat_id formats failed.")
        print()
        print("TROUBLESHOOT:")
        print("1. Make sure @cambodiarain8888_bot is ADMIN in @cambodiarain8888 channel")
        print("2. Open Telegram → @cambodiarain8888 channel → Add Admin → @cambodiarain8888_bot")
        print("3. Give it permission to 'Post Messages'")
        print("4. Then run this bot again")
        exit(1)

if __name__ == "__main__":
    main()
