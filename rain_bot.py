import requests, pytz
from datetime import datetime

TG_TOKEN = "8611542903:AAGtPB9oNeCUYMpy3SS5aXr0fuZiHjGJumQ"
TG_CHAT_ID = "-1003908019472"
LAT, LON, CITY = 11.564137, 104.916075, "Phnom Penh"
TZ = pytz.timezone("Asia/Phnom_Penh")

SCAN = [
  ("N",LAT+0.45,LON),("NE",LAT+0.32,LON+0.45),
  ("E",LAT,LON+0.55),("SE",LAT-0.32,LON+0.45),
  ("S",LAT-0.45,LON),("SW",LAT-0.32,LON-0.45),
  ("W",LAT,LON-0.55),("NW",LAT+0.32,LON-0.45),
]

def wmo(c):
  if c==0: return "Clear ☀️"
  if c<=2: return "Partly Cloudy ⛅"
  if c==3: return "Overcast ☁️"
  if c<=57: return "Drizzle 🌦️"
  if c<=67: return "Rain 🌧️"
  if c<=82: return "Showers 🌦️"
  if c<=99: return "Thunderstorm ⛈️"
  return "Unknown"

def wdir(d): return ['N','NE','E','SE','S','SW','W','NW'][round(d/45)%8]

def fetch(lat,lon):
  now_h = datetime.now(TZ).strftime("%Y-%m-%dT%H")
  p = {"latitude":lat,"longitude":lon,
    "current":"temperature_2m,relative_humidity_2m,apparent_temperature,rain,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,pressure_msl,uv_index,precipitation",
    "hourly":"precipitation_probability,weather_code",
    "daily":"precipitation_sum,precipitation_probability_max,temperature_2m_max,temperature_2m_min",
    "timezone":"Asia/Bangkok","forecast_days":1}
  d = requests.get("https://api.open-meteo.com/v1/forecast",params=p,timeout=15).json()
  h = d["hourly"]
  idx = next((i for i,t in enumerate(h["time"]) if t.startswith(now_h)),0)
  return d["current"], h["precipitation_probability"][idx] or 0, d["daily"]

def scan_dirs():
  now_h = datetime.now(TZ).strftime("%Y-%m-%dT%H")
  out = []
  for (dr,la,lo) in SCAN:
    try:
      p={"latitude":la,"longitude":lo,"current":"weather_code,cloud_cover",
        "hourly":"precipitation_probability","timezone":"Asia/Bangkok","forecast_days":1}
      d=requests.get("https://api.open-meteo.com/v1/forecast",params=p,timeout=10).json()
      h=d["hourly"]
      idx=next((i for i,t in enumerate(h["time"]) if t.startswith(now_h)),0)
      rp=h["precipitation_probability"][idx] or 0
      out.append((dr,rp,d["current"]["weather_code"],d["current"]["cloud_cover"]))
    except: pass
  return out

def classify(rp,wc,cloud):
  if wc>=80: return "⛈ Cumulonimbus STORM"
  if wc>=61 or rp>=60: return "🌧 Nimbostratus HEAVY RAIN"
  if wc>=51 or rp>=40: return "🌦 Altostratus RAIN CLOUD"
  if cloud>=70 or rp>=25: return "☁ Stratocumulus DARK CLOUD"
  if cloud>=40: return "⛅ Cumulus WATCH"
  return "☀ Clear"

def send(msg):
  for cid in [TG_CHAT_ID,"@cambodiarain8888"]:
    try:
      r=requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id":cid,"text":msg,"parse_mode":"HTML"},timeout=15)
      if r.json().get("ok"): print(f"✅ Sent {cid}"); return True
      print(f"⚠ {cid}:", r.json().get("description"))
    except Exception as e: print(f"❌ {e}")
  return False

def main():
  now = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
  print(f"🌧 Bot running — {now}")
  c,rp,dy = fetch(LAT,LON)
  dirs = scan_dirs()
  israin = rp>=50 or (61<=c["weather_code"]<=99)
  sc=0
  if rp>=60: sc+=30
  elif rp>=30: sc+=15
  if c["cloud_cover"]>=70: sc+=20
  elif c["cloud_cover"]>=40: sc+=10
  if c["relative_humidity_2m"]>=75: sc+=20
  elif c["relative_humidity_2m"]>=55: sc+=10
  if 61<=c["weather_code"]<=99: sc+=25
  elif c["weather_code"]>=51: sc+=12
  sc=min(sc,99)
  sig = "🌧 RAIN EXPECTED" if israin else "☀️ NO RAIN"
  bar = "🟦🟦🟦🟦🟦" if rp>=60 else ("🟦🟦🟦⬜⬜" if rp>=30 else "🟩🟩🟩🟩🟩")
  rain_dirs=[f"• <b>{d}</b> ~50km — {p}% — {classify(p,w,cl)}" for d,p,w,cl in sorted(dirs,key=lambda x:-x[1]) if p>=25 or 51<=w<=99]
  csec = ("\n🧭 <b>Cloud Systems:</b>\n"+("\n".join(rain_dirs))) if rain_dirs else "\n🧭 No rain clouds within 50km ☀️"
  msg=f"""🌧 <b>Cambodia Rain 8888 — AI Report</b>
📍 {CITY} | 11.5641°N 104.9161°E
🕐 {now}

<b>{sig}</b>  {bar}
Rain Prob: <b>{rp}%</b> | AI Score: <b>{sc}/99</b>

🌡 {c['temperature_2m']}°C (feels {c['apparent_temperature']}°C)
💧 Humidity: {c['relative_humidity_2m']}%
☁️ Cloud: {c['cloud_cover']}%
🌬 Wind: {c['wind_speed_10m']} km/h {wdir(c['wind_direction_10m'])}
🌧 Rain: {c['rain']} mm  |  🔆 UV: {c['uv_index']}{csec}

{'⚠️ Bring umbrella or find shelter!' if israin else '✅ Conditions favorable!'}
📡 @cambodiarain8888 | <b>MR TP AI Weather</b>"""
  send(msg)

if __name__=="__main__": main()
