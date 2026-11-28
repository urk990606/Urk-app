import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import requests
import pandas as pd
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK 1-Min Live Bot", page_icon="📈", layout="centered")
IST = ZoneInfo("Asia/Kolkata")

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

if not st.session_state.user:
    st.title("📈 URK 1-Min Live Bot")
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

def get_live_ltp(sym):
    div_map = {"BTC-USD (₹)": 1000.0, "ETH-USD (₹)": 100.0, "SOL-USD (₹)": 1.0}
    m = 87.5 / div_map.get(sym, 1.0)
    tk = sym.replace(" (₹)", "")
    errors = []

    # 1. మీ పాత కోడ్‌లో పనిచేసిన Yahoo Finance (fast_info & history)
    try:
        t = yf.Ticker(tk)
        p = t.fast_info.get("lastPrice")
        if p and float(p) > 0:
            return round(float(p) * m, 2), "Yahoo Live", ""
        df = t.history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df["Close"].iloc[-1]) * m, 2), "Yahoo 1m", ""
    except Exception as e:
        errors.append(f"YF: {e}")

    # 2. Coinbase Public API
    try:
        r = requests.get(f"https://coinbase.com{tk}/spot", timeout=4).json()
        p = float(r.get("data", {}).get("amount", 0))
        if p > 0:
            return round(p * m, 2), "Coinbase", ""
    except Exception as e:
        errors.append(f"CB: {e}")

    # 3. Gemini Public API
    try:
        g_sym = tk.replace("-", "").lower()
        r = requests.get(f"https://gemini.com{g_sym}", timeout=4).json()
        p = float(r.get("last", 0))
        if p > 0:
            return round(p * m, 2), "Gemini", ""
    except Exception as e:
        errors.append(f"GM: {e}")

    return None, None, " | ".join(errors)

c1, c2 = st.columns((3, 1))
c1.subheader("📈 Live 1-Min Auto Test")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]
is_holding = isinstance(ud.get("bot_pos"), dict)

col1, col2, col3 = st.columns(3)
sym = col1.selectbox("24/7 Live Asset:", cryptos, index=0, disabled=is_holding)
qty = col2.number_input("Quantity:", 1, 100, 1, disabled=is_holding)
interval_sec = col3.number_input("Cycle Time (Sec):", 10, 300, 60)

b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START 1-MIN LOOP", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["last_action_ts"] = 0.0
    ud["bot_logs"].insert(0, f"[{datetime.now(IST).strftime('%H:%M:%S')}] 🚀 Live Loop Started!")
    st.rerun()

if b2.button("⏹️ STOP LOOP", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_logs"].insert(0, f"[{datetime.now(IST).strftime('%H:%M:%S')}] 🛑 Loop Stopped.")
    st.rerun()

if b3.button("🔄 Reset", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_pos"] = None
    ud["hist"] = []
    ud["bot_logs"] = []
    ud["cash"] = 100000.0
    ud["rpnl"] = 0.0
    st.rerun()

# ---------------- TRADINGVIEW LIVE CHART ----------------
tv_sym = "COINBASE:BTCUSD"
if "ETH" in sym:
    tv_sym = "COINBASE:ETHUSD"
elif "SOL" in sym:
    tv_sym = "COINBASE:SOLUSD"

tv_html = f"""
<div class="tradingview-widget-container">
  <div id="tv_chart" style="height:380px;"></div>
  <script type="text/javascript" src="https://tradingview.com"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "autosize": true,
    "symbol": "{tv_sym}",
    "interval": "1",
    "timezone": "Asia/Kolkata",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "enable_publishing": false,
    "container_id": "tv_chart"
  }});
  </script>
</div>
"""
components.html(tv_html, height=390)

# ---------------- LIVE BOT ENGINE ----------------
@st.fragment(run_every=3)
def live_bot_engine():
    if ud.get("sound"):
        trigger_beep(ud["sound"])
        ud["sound"] = None

    now_ist = datetime.now(IST)
    ltp, src, err_info = get_live_ltp(sym)

    un_pnl = 0.0
    if isinstance(ud.get("bot_pos"), dict):
        bp = ud["bot_pos"]
        cur_p = ltp if ltp is not None else bp["entry"]
        un_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)

    m0, m1, m2, m3 = st.columns(4)
    m0.metric("Available Cash", f"₹{ud['cash']:,.2f}")
    m1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
    m2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
    m3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")

    if ltp is not None:
        st.success(f"🟢 Live Scaled Price ({sym} via {src}): **₹{ltp:,.2f}** | {now_ist.strftime('%H:%M:%S')} IST")
    else:
        st.error(f"Data Fetch Failed: {err_info}")

    if ud["bot_on"] and ltp is not None:
        now_ts = time.time()
        elapsed = now_ts - ud["last_action_ts"]
        remaining = max(0, int(interval_sec - elapsed))
        st.info(f"🔄 **BOT RUNNING** | Live **{sym}**: **₹{ltp:,.2f}** | Next Action in: **{remaining}s**")

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

        elif isinstance(ud.get("bot_pos"), dict) and elapsed >= interval_sec:
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

    st.subheader("📌 Current Position (ప్రస్తుత పొజిషన్)")
    if isinstance(ud.get("bot_pos"), dict):
        bp = ud["bot_pos"]
        cur_p = ltp if ltp is not None else bp["entry"]
        live_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)
        pos_df = pd.DataFrame([{
            "Status": "🟢 BOUGHT (HOLDING)",
            "Asset": bp["sym"],
            "Qty": bp["qty"],
            "Buy Price (₹)": bp["entry"],
            "Live Price (₹)": cur_p,
            "Live P&L (₹)": f"{live_pnl:+,.2f}",
            "Buy Time": bp["time"]
        }])
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("⚪ ప్రస్తుతం ఎలాంటి పొజిషన్ లేదు (Waiting for Next BUY)")

    if ud["hist"]:
        st.subheader("📋 Completed Orders (1-Min Buy/Sell History)")
        st.dataframe(pd.DataFrame(ud["hist"]), use_container_width=True, hide_index=True)

    if ud["bot_logs"]:
        st.subheader("📜 Live Execution Logs")
        for log in ud["bot_logs"][:15]:
            st.text(log)

live_bot_engine()
