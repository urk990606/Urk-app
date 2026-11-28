import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK 1-Min Live Bot", page_icon="📈", layout="centered")
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

# ---------------- LIVE DATA API (BINANCE + COINBASE BACKUP) ----------------
def get_multiplier(sym):
    m = 87.5  # USD to INR rate
    if "BTC" in sym:
        return m / 1000.0
    elif "ETH" in sym:
        return m / 100.0
    return m

def get_live_chart_and_ltp(sym):
    coin = sym.split("-")[0]  # "BTC", "ETH", or "SOL"
    m = get_multiplier(sym)
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1. Try Binance Vision Public API
    try:
        url = f"https://binance.vision{coin}USDT&interval=1m&limit=60"
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    "Open_time", "Open", "High", "Low", "Close", "Volume",
                    "Close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
                ])
                df["Open_time"] = pd.to_datetime(df["Open_time"], unit="ms").dt.tz_localize("UTC").dt.tz_convert(IST)
                df.set_index("Open_time", inplace=True)
                for col in ("Open", "High", "Low", "Close"):
                    df[col] = df[col].astype(float) * m
                return df, round(float(df["Close"].iloc[-1]), 2), "Binance"
    except Exception:
        pass

    # 2. Fallback: Coinbase Exchange Public API (Works 100% on US Streamlit Servers)
    try:
        cb_url = f"https://coinbase.com{coin}-USD/candles?granularity=60"
        res = requests.get(cb_url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data[:60], columns=["time", "Low", "High", "Open", "Close", "Volume"])
                df["time"] = pd.to_datetime(df["time"], unit="s").dt.tz_localize("UTC").dt.tz_convert(IST)
                df.set_index("time", inplace=True)
                df.sort_index(inplace=True)
                for col in ("Open", "High", "Low", "Close"):
                    df[col] = df[col].astype(float) * m
                return df, round(float(df["Close"].iloc[-1]), 2), "Coinbase"
    except Exception:
        pass

    return pd.DataFrame(), None, None

# ---------------- TOP BAR & CONTROLS ----------------
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

st.divider()

# ---------------- LIVE UPDATING SECTION (EVERY 2 SECONDS) ----------------
@st.fragment(run_every=2)
def live_trading_dashboard():
    if ud.get("sound"):
        trigger_beep(ud["sound"])
        ud["sound"] = None

    now_ist = datetime.now(IST)
    df_ch, ltp, source = get_live_chart_and_ltp(sym)

    # P&L Calculation
    un_pnl = 0.0
    if isinstance(ud.get("bot_pos"), dict):
        bp = ud["bot_pos"]
        cur_p = ltp if ltp is not None else bp["entry"]
        un_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)

    # Metrics Row
    m0, m1, m2, m3 = st.columns(4)
    m0.metric("Available Cash", f"₹{ud['cash']:,.2f}")
    m1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
    m2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
    m3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")

    # Live Candlestick Chart
    if not df_ch.empty:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_ch.index,
            open=df_ch["Open"],
            high=df_ch["High"],
            low=df_ch["Low"],
            close=df_ch["Close"],
            name=sym
        ))
        if isinstance(ud.get("bot_pos"), dict) and ud["bot_pos"]["sym"] == sym:
            fig.add_hline(
                y=ud["bot_pos"]["entry"],
                line_dash="dash",
                line_color="lime",
                annotation_text=f"🟢 BOUGHT @ ₹{ud['bot_pos']['entry']:,.2f}",
                annotation_position="top left"
            )
        fig.update_layout(
            title=f"{sym} - {source} Live 1-Min Chart (LTP: ₹{ltp:,.2f})",
            height=380,
            margin=dict(l=10, r=10, t=35, b=10),
            xaxis_rangeslider_visible=False,
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("లైవ్ డేటా లోడ్ అవుతోంది... దయచేసి వేచి ఉండండి.")

    # Auto Execution Logic
    if ud["bot_on"] and ltp is not None:
        now_ts = time.time()
        elapsed = now_ts - ud["last_action_ts"]
        remaining = max(0, int(interval_sec - elapsed))
        st.info(f"🔄 **BOT RUNNING** | Live **{sym}**: **₹{ltp:,.2f}** | Next Action in: **{remaining}s**")

        # 1. BUY ACTION
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

        # 2. SELL ACTION
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

    # Current Position Table
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
