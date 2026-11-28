import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK 1-Min Binance Live Bot", page_icon="📈", layout="centered")
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
    st.title("📈 URK 1-Min Binance Live Bot")
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

# ---------------- BINANCE PUBLIC LIVE DATA API ----------------
@st.cache_data(ttl=300)
def get_usdtinr():
    try:
        # Binance USDT/INR లైవ్ రేటు (లేదా fallback 87.5)
        r = requests.get("https://binance.vision", timeout=3).json()
        if "price" in r:
            return float(r["price"])
    except Exception:
        pass
    return 87.5

def get_multiplier(sym):
    m = get_usdtinr()
    if "BTC" in sym:
        return m / 1000.0  # ₹1L బడ్జెట్ కోసం స్కేలింగ్
    elif "ETH" in sym:
        return m / 100.0
    return m

def get_binance_chart_and_ltp(sym):
    try:
        # "BTC-USD (₹)" -> "BTCUSDT" గా మారుస్తుంది
        tk = sym.split("-")[0] + "USDT"
        url = f"https://binance.vision{tk}&interval=1m&limit=60"
        data = requests.get(url, timeout=4).json()
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame(), None

        df = pd.DataFrame(data, columns=[
            "Open_time", "Open", "High", "Low", "Close", "Volume",
            "Close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        df["Open_time"] = pd.to_datetime(df["Open_time"], unit="ms").dt.tz_localize("UTC").dt.tz_convert(IST)
        df.set_index("Open_time", inplace=True)

        m = get_multiplier(sym)
        for col in ("Open", "High", "Low", "Close"):
            df[col] = df[col].astype(float) * m

        ltp = round(float(df["Close"].iloc[-1]), 2)
        return df, ltp
    except Exception:
        return pd.DataFrame(), None

# ---------------- TOP BAR & CONTROLS ----------------
c1, c2 = st.columns((3, 1))
c1.subheader("📈 Binance Live 1-Min Auto Test")
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
    ud["bot_logs"].insert(0, f"[{datetime.now(IST).strftime('%H:%M:%S')}] 🚀 Binance Live Loop Started!")
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
    df_ch, ltp = get_binance_chart_and_ltp(sym)

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
            title=f"{sym} - Binance Live 1-Min Chart (LTP: ₹{ltp:,.2f})",
            height=380,
            margin=dict(l=10, r=10, t=35, b=10),
            xaxis_rangeslider_visible=False,
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Binance లైవ్ డేటా లోడ్ అవుతోంది... దయచేసి వేచి ఉండండి.")

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
        }])
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("⚪ ప్రస్తుతం ఎలాంటి పొజిషన్ లేదు (Waiting for Next BUY)")

    # History & Logs
    if ud["hist"]:
        st.subheader("📋 Completed Orders (1-Min Buy/Sell History)")
        st.dataframe(pd.DataFrame(ud["hist"]), use_container_width=True, hide_index=True)

    if ud["bot_logs"]:
        st.subheader("📜 Live Execution Logs")
        for log in ud["bot_logs"][:15]:
            st.text(log)

live_trading_dashboard()
