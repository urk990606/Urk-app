import streamlit as st
import yfinance as yf
import pandas as pd
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK 1-Min Auto Test Bot", page_icon="⏱️", layout="centered")
IST = ZoneInfo("Asia/Kolkata")

# ---------------- AUDIO BEEP GENERATOR ----------------
@st.cache_data
def make_wav(freq=950, dur=0.35):
    rate = 22050
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * dur)):
            frames.extend(struct.pack("<h", int(28000 * math.sin(2 * math.pi * freq * i / rate))))
        wf.writeframes(bytes(frames))
    return buf.getvalue()

def trigger_beep(kind="buy"):
    st.audio(make_wav(1000, 0.35) if kind == "buy" else make_wav(550, 0.5), format="audio/wav", autoplay=True)

# ---------------- SESSION STATE DB ----------------
if "db" not in st.session_state:
    st.session_state.db = {
        "admin": {
            "pw": "123",
            "cash": 100000.0,
            "hist": [],
            "rpnl": 0.0,
            "bot_on": False,
            "bot_pos": None,
            "last_action_ts": 0.0,
            "bot_logs": [],
            "sound": None,
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- LOGIN SCREEN ----------------
if not st.session_state.user:
    st.title("⏱️ URK 1-Min Test Bot Login")
    u = st.text_input("Username", value="admin")
    p = st.text_input("Password", type="password", value="123")
    if st.button("Login", type="primary"):
        if u in st.session_state.db and st.session_state.db[u]["pw"] == p:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Wrong login! (Use: admin / 123)")
    st.stop()

ud = st.session_state.db[st.session_state.user]
if ud.get("sound"):
    trigger_beep(ud["sound"])
    ud["sound"] = None

# ---------------- 24/7 LIVE PRICE FETCHING ----------------
@st.cache_data(ttl=60)
def get_usdinr():
    try:
        fx = yf.Ticker("USDINR=X").history(period="2d", interval="15m")
        if not fx.empty:
            return float(fx["Close"].iloc[-1])
    except Exception:
        pass
    return 84.5

@st.cache_data(ttl=2)
def get_ltp(sym):
    try:
        tk = sym.replace(" (₹)", "")
        m = get_usdinr()
        if "BTC-USD" in sym:
            m = m / 1000.0  # మినీ యూనిట్ (~₹7,500)
        elif "ETH-USD" in sym:
            m = m / 100.0   # మినీ యూనిట్ (~₹2,500)

        df = yf.Ticker(tk).history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df["Close"].iloc[-1]) * m, 2)
    except Exception:
        pass
    return None

# ---------------- HEADER & P&L ----------------
c1, c2 = st.columns((3, 1))
c1.subheader(f"⏱️ 1-Min Auto Test | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

un_pnl = 0.0
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    cur_p = get_ltp(bp["sym"]) or bp["entry"]
    un_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)

pm1, pm2, pm3 = st.columns(3)
pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")
st.divider()

# ---------------- MAIN 1-MIN BUY / SELL ENGINE ----------------
now_ist = datetime.now(IST)
cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]

col1, col2, col3 = st.columns(3)
sym = col1.selectbox("24/7 Live Asset:", cryptos, index=0)
qty = col2.number_input("Quantity:", 1, 100, 1)
interval_sec = col3.number_input("Cycle Time (Sec):", 10, 300, 60)

b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START 1-MIN LOOP", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["last_action_ts"] = 0.0  # నొక్కగానే వెంటనే మొదటి BUY జరిగేలా
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 1-Min Auto Loop Started!")
    st.rerun()

if b2.button("⏹️ STOP LOOP", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🛑 Loop Stopped.")
    st.rerun()

if b3.button("🔄 Reset", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_pos"] = None
    ud["hist"] = []
    ud["bot_logs"] = []
    ud["cash"] = 100000.0
    ud["rpnl"] = 0.0
    st.rerun()

# ---------------- AUTO EXECUTION LOGIC ----------------
if ud["bot_on"]:
    ltp = get_ltp(sym)
    now_ts = time.time()
    elapsed = now_ts - ud["last_action_ts"]
    remaining = max(0, int(interval_sec - elapsed))

    if ltp is not None:
        st.info(f"🔄 **RUNNING** | Live **{sym}**: **₹{ltp:,.2f}** | Next Action in: **{remaining}s**")

        # 1. పొజిషన్ లేకపోతే -> 1 నిమిషం అవ్వగానే BUY చేయాలి
        if ud["bot_pos"] is None and elapsed >= interval_sec:
            cost = round(ltp * qty, 2)
            if ud["cash"] >= cost:
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {
                    "sym": sym,
                    "qty": qty,
                    "entry": ltp,
                    "time": now_ist.strftime("%H:%M:%S")
                }
                ud["last_action_ts"] = now_ts
                ud["sound"] = "buy"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🟢 AUTO BUY: {qty} {sym} @ ₹{ltp:,.2f}")
                st.rerun()
            else:
                st.error("Insufficient Cash!")

        # 2. పొజిషన్ ఉంటే -> సరిగ్గా 1 నిమిషం తర్వాత SELL చేయాలి
        elif isinstance(ud["bot_pos"], dict) and elapsed >= interval_sec:
            bp = ud["bot_pos"]
            pnl = round((ltp - bp["entry"]) * bp["qty"], 2)
            ud["cash"] = round(ud["cash"] + (ltp * bp["qty"]), 2)
            ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
            ud["hist"].insert(0, {
                "Buy Time": bp["time"],
                "Sell Time": now_ist.strftime("%H:%M:%S"),
                "Asset": bp["sym"],
                "Qty": bp["qty"],
                "Buy Price": bp["entry"],
                "Sell Price": ltp,
                "P&L (₹)": pnl
            })
            ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🔴 AUTO SELL: {bp['qty']} {bp['sym']} @ ₹{ltp:,.2f} | P&L: ₹{pnl:+,.2f}")
            ud["bot_pos"] = None
            ud["last_action_ts"] = now_ts
            ud["sound"] = "sell"
            st.rerun()

    time.sleep(2)
    st.rerun()

# ---------------- ACTIVE POSITION & TABLES ----------------
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    cur_p = get_ltp(bp["sym"]) or bp["entry"]
    live_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)
    st.success(f"📌 **Holding Position:** {bp['qty']} {bp['sym']} | Bought @ ₹{bp['entry']:,.2f} | Live: ₹{cur_p:,.2f} | Live P&L: **₹{live_pnl:+,.2f}**")

if ud["hist"]:
    st.subheader("📋 Completed Orders (1-Min Buy/Sell History)")
    st.dataframe(pd.DataFrame(ud["hist"]), use_container_width=True)

if ud["bot_logs"]:
    st.subheader("📜 Live Execution Logs")
    for log in ud["bot_logs"][:15]:
        st.text(log)
