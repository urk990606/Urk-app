import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Pro Paper Bot + Chart", page_icon="📈", layout="centered")
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
    st.title("📈 URK Pro Paper Bot Login")
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

# ---------------- 24/7 LIVE PRICE & CHART DATA ----------------
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
            m = m / 1000.0
        elif "ETH-USD" in sym:
            m = m / 100.0

        df = yf.Ticker(tk).history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df["Close"].iloc[-1]) * m, 2)
    except Exception:
        pass
    return None

@st.cache_data(ttl=5)
def get_chart_data(sym):
    try:
        tk = sym.replace(" (₹)", "")
        m = get_usdinr()
        if "BTC-USD" in sym:
            m = m / 1000.0
        elif "ETH-USD" in sym:
            m = m / 100.0

        df = yf.Ticker(tk).history(period="1d", interval="1m")
        if not df.empty:
            df = df.tail(80).copy()
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * m
            df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
            return df.tail(60)
    except Exception:
        pass
    return pd.DataFrame()

# ---------------- HEADER & P&L ----------------
c1, c2 = st.columns((3, 1))
c1.subheader(f"📈 Pro Auto Bot | Cash: ₹{ud['cash']:,.2f}")
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

# ---------------- CONTROLS & STRATEGY SETTINGS ----------------
now_ist = datetime.now(IST)
cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]

has_pos = isinstance(ud.get("bot_pos"), dict)
default_idx = cryptos.index(ud["bot_pos"]["sym"]) if has_pos and ud["bot_pos"]["sym"] in cryptos else 0

col1, col2, col3 = st.columns(3)
sym = col1.selectbox("24/7 Live Asset:", cryptos, index=default_idx, disabled=has_pos)
qty = col2.number_input("Quantity:", 1, 100, 1, disabled=has_pos)
interval_sec = col3.number_input("Max Hold / Wait (Sec):", 10, 600, 60)

s1, s2, s3 = st.columns(3)
strategy_mode = s1.selectbox("Entry Strategy:", ["Timer Only (Test)", "EMA 9 > 21 Trend"], index=1)
sl_pct = s2.number_input("Stop-Loss (%):", 0.1, 10.0, 0.5, step=0.1)
tp_pct = s3.number_input("Target Profit (%):", 0.1, 20.0, 1.0, step=0.1)

b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START AUTO BOT", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["last_action_ts"] = 0.0
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 Bot Started ({strategy_mode} | SL:{sl_pct}% | TP:{tp_pct}%)")
    st.rerun()

if b2.button("⏹️ STOP BOT", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🛑 Bot Stopped.")
    st.rerun()

if b3.button("🔄 Reset", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_pos"] = None
    ud["hist"] = []
    ud["bot_logs"] = []
    ud["cash"] = 100000.0
    ud["rpnl"] = 0.0
    st.rerun()

# ---------------- LIVE CANDLESTICK CHART + EMA + MARKERS ----------------
df_ch = get_chart_data(sym)
ema_bullish = False

if not df_ch.empty:
    latest_ema9 = df_ch["EMA9"].iloc[-1]
    latest_ema21 = df_ch["EMA21"].iloc[-1]
    ema_bullish = latest_ema9 > latest_ema21

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_ch.index,
        open=df_ch["Open"],
        high=df_ch["High"],
        low=df_ch["Low"],
        close=df_ch["Close"],
        name="Price"
    ))
    fig.add_trace(go.Scatter(x=df_ch.index, y=df_ch["EMA9"], mode="lines", name="EMA 9 (Fast)", line=dict(color="cyan", width=1.5)))
    fig.add_trace(go.Scatter(x=df_ch.index, y=df_ch["EMA21"], mode="lines", name="EMA 21 (Slow)", line=dict(color="orange", width=1.5)))

    if has_pos and ud["bot_pos"]["sym"] == sym:
        bp = ud["bot_pos"]
        fig.add_hline(y=bp["entry"], line_dash="dash", line_color="white", annotation_text=f"BUY @ ₹{bp['entry']:,.2f}")
        fig.add_hline(y=bp["tp_price"], line_dash="dot", line_color="lime", annotation_text=f"🎯 TP @ ₹{bp['tp_price']:,.2f}")
        fig.add_hline(y=bp["sl_price"], line_dash="dot", line_color="red", annotation_text=f"🛑 SL @ ₹{bp['sl_price']:,.2f}")

    asset_trades = [t for t in ud["hist"] if t["Asset"] == sym and "buy_ts" in t]
    if asset_trades:
        fig.add_trace(go.Scatter(
            x=[t["buy_ts"] for t in asset_trades],
            y=[t["Buy Price (₹)"] for t in asset_trades],
            mode="markers",
            marker=dict(symbol="triangle-up", size=12, color="lime"),
            name="Past Buy"
        ))
        fig.add_trace(go.Scatter(
            x=[t["sell_ts"] for t in asset_trades],
            y=[t["Sell Price (₹)"] for t in asset_trades],
            mode="markers",
            marker=dict(symbol="triangle-down", size=12, color="red"),
            name="Past Sell"
        ))

    fig.update_layout(
        title=f"{sym} | Trend: {'🟢 BULLISH (EMA9 > EMA21)' if ema_bullish else '🔴 BEARISH (EMA9 < EMA21)'}",
        height=400,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("చార్ట్ డేటా లోడ్ అవుతోంది... దయచేసి వేచి ఉండండి.")

# ---------------- CURRENT POSITION ----------------
st.subheader("📌 Current Position (ప్రస్తుత పొజిషన్)")
if has_pos:
    bp = ud["bot_pos"]
    cur_p = get_ltp(bp["sym"]) or bp["entry"]
    live_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)
    pos_df = pd.DataFrame([{
        "Status": "🟢 HOLDING",
        "Asset": bp["sym"],
        "Qty": bp["qty"],
        "Buy (₹)": bp["entry"],
        "Live (₹)": cur_p,
        "SL (₹)": bp["sl_price"],
        "Target (₹)": bp["tp_price"],
        "Live P&L (₹)": f"{live_pnl:+,.2f}",
        "Time": bp["time"]
    }])
    st.dataframe(pos_df, use_container_width=True, hide_index=True)
else:
    st.info("⚪ ప్రస్తుతం ఎలాంటి పొజిషన్ లేదు (Waiting for Signal)")

# ---------------- AUTO EXECUTION LOGIC ----------------
if ud["bot_on"]:
    ltp = get_ltp(sym)
    now_ts = time.time()
    elapsed = now_ts - ud["last_action_ts"]
    remaining = max(0, int(interval_sec - elapsed))

    if ltp is not None:
        st.info(f"🔄 **BOT ACTIVE** | **{sym}**: **₹{ltp:,.2f}** | Timer: **{remaining}s** | EMA Signal: **{'BUY OK' if ema_bullish else 'WAIT'}**")

        # 1. BUY ACTION
        can_buy = (strategy_mode == "Timer Only (Test)") or (strategy_mode == "EMA 9 > 21 Trend" and ema_bullish)
        if not has_pos and elapsed >= interval_sec and can_buy:
            cost = round(ltp * qty, 2)
            if ud["cash"] >= cost:
                sl_price = round(ltp * (1 - sl_pct / 100.0), 2)
                tp_price = round(ltp * (1 + tp_pct / 100.0), 2)
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {
                    "sym": sym,
                    "qty": qty,
                    "entry": ltp,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "time": now_ist.strftime("%H:%M:%S"),
                    "buy_ts": df_ch.index[-1] if not df_ch.empty else now_ist
                }
                ud["last_action_ts"] = now_ts
                ud["sound"] = "buy"
