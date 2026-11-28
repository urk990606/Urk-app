import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK High-Low Breakout Bot", page_icon="📈", layout="centered")
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
            "last_traded_candle": None,
            "bot_logs": [],
            "sound": None,
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- LOGIN SCREEN ----------------
if not st.session_state.user:
    st.title("📈 URK High-Low Breakout Bot Login")
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
            df = df.tail(60).copy()  # చివరి 60 నిమిషాల క్యాండిల్స్
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * m
            return df
    except Exception:
        pass
    return pd.DataFrame()

# ---------------- HEADER & P&L ----------------
c1, c2 = st.columns((3, 1))
c1.subheader(f"📈 Breakout Bot | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

now_ist = datetime.now(IST)
cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]

col1, col2, col3 = st.columns(3)
sym = col1.selectbox("24/7 Live Asset:", cryptos, index=0)
qty = col2.number_input("Quantity:", 1, 100, 1)
trade_mode = col3.selectbox("Trade Mode:", ["Both (High & Low)", "Only Buy (High Break)", "Only Short (Low Break)"])

# డేటా తెచ్చుకోవడం
df_ch = get_chart_data(sym)
cur_p = round(float(df_ch["Close"].iloc[-1]), 2) if not df_ch.empty else None

# Unrealized P&L లెక్కింపు (BUY మరియు SHORT రెండింటికీ)
un_pnl = 0.0
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    live_price = cur_p if (cur_p and bp["sym"] == sym) else bp["entry"]
    if bp["side"] == "BUY":
        un_pnl = round((live_price - bp["entry"]) * bp["qty"], 2)
    else:  # SHORT
        un_pnl = round((bp["entry"] - live_price) * bp["qty"], 2)

pm1, pm2, pm3 = st.columns(3)
pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")
st.divider()

# ---------------- CONTROLS ----------------
b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START BREAKOUT BOT", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 High-Low Breakout Bot Started!")
    st.rerun()

if b2.button("⏹️ STOP BOT", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🛑 Bot Stopped.")
    st.rerun()

if b3.button("🔄 Reset", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_pos"] = None
    ud["last_traded_candle"] = None
    ud["hist"] = []
    ud["bot_logs"] = []
    ud["cash"] = 100000.0
    ud["rpnl"] = 0.0
    st.rerun()

# ---------------- PREV CANDLE & LIVE CANDLE ANALYSIS ----------------
prev_candle = None
curr_candle = None
curr_candle_ts = None

if len(df_ch) >= 2:
    prev_candle = df_ch.iloc[-2]  # పూర్తిగా క్లోజ్ అయిన మునుపటి క్యాండిల్ (రంగుతో సంబంధం లేదు)
    curr_candle = df_ch.iloc[-1]  # ప్రస్తుతం నడుస్తున్న క్యాండిల్
    curr_candle_ts = str(df_ch.index[-1])

# ---------------- LIVE CANDLESTICK CHART ----------------
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

    # మునుపటి క్యాండిల్ High & Low లెవెల్స్ చార్ట్ మీద చూపించడం (ఏ రంగు అయినా సరే)
    if prev_candle is not None and ud["bot_pos"] is None:
        if trade_mode in ["Both (High & Low)", "Only Buy (High Break)"]:
            fig.add_hline(
                y=prev_candle["High"],
                line_dash="dot",
                line_color="cyan",
                annotation_text=f"🎯 BUY Trigger (Prev High): ₹{prev_candle['High']:,.2f}",
                annotation_position="top left"
            )
        if trade_mode in ["Both (High & Low)", "Only Short (Low Break)"]:
            fig.add_hline(
                y=prev_candle["Low"],
                line_dash="dot",
                line_color="orange",
                annotation_text=f"🎯 SHORT Trigger (Prev Low): ₹{prev_candle['Low']:,.2f}",
                annotation_position="bottom left"
            )

    # ప్రస్తుతం పొజిషన్ ఉంటే Entry లైన్ చూపించడం
    if isinstance(ud.get("bot_pos"), dict) and ud["bot_pos"]["sym"] == sym:
        bp = ud["bot_pos"]
        line_col = "lime" if bp["side"] == "BUY" else "red"
        icon = "🟢" if bp["side"] == "BUY" else "🔴"
        fig.add_hline(
            y=bp["entry"],
            line_dash="dash",
            line_color=line_col,
            annotation_text=f"{icon} {bp['side']} @ ₹{bp['entry']:,.2f}",
            annotation_position="top left"
        )

    fig.update_layout(
        title=f"{sym} - Live 1-Min High/Low Breakout Chart",
        height=380,
        margin=dict(l=10, r=10, t=35, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("చార్ట్ డేటా లోడ్ అవుతోంది... దయచేసి వేచి ఉండండి.")

# ---------------- CURRENT POSITION ----------------
st.subheader("📌 Current Position (ప్రస్తుత పొజిషన్)")
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    live_price = cur_p if (cur_p and bp["sym"] == sym) else bp["entry"]
    live_pnl = round((live_price - bp["entry"]) * bp["qty"], 2) if bp["side"] == "BUY" else round((bp["entry"] - live_price) * bp["qty"], 2)
    status_lbl = "🟢 LONG (BOUGHT)" if bp["side"] == "BUY" else "🔴 SHORT (SOLD)"

    pos_df = pd.DataFrame([{
        "Position": status_lbl,
        "Asset": bp["sym"],
        "Qty": bp["qty"],
        "Entry Price (₹)": bp["entry"],
        "Live Price (₹)": live_price,
        "Live P&L (₹)": f"{live_pnl:+,.2f}",
        "Entry Time": bp["time"],
        "Exit Rule": "Current Candle Close"
    }])
    st.dataframe(pos_df, use_container_width=True, hide_index=True)
else:
    st.info("⚪ ప్రస్తుతం ఎలాంటి పొజిషన్ లేదు (Waiting for Prev High / Low Breakout...)")

# ---------------- AUTO BREAKOUT EXECUTION LOGIC ----------------
if ud["bot_on"] and prev_candle is not None and curr_candle is not None:
    ltp = round(float(curr_candle["Close"]), 2)
    prev_high = round(float(prev_candle["High"]), 2)
    prev_low = round(float(prev_candle["Low"]), 2)

    st.info(
        f"🔄 **BOT ACTIVE** | Live **{sym}**: **₹{ltp:,.2f}** | "
        f"🔼 Buy Above: **₹{prev_high:,.2f}** | 🔽 Short Below: **₹{prev_low:,.2f}**"
    )

    # 1. EXIT LOGIC (Current Candle Close అవ్వగానే, కొత్త క్యాండిల్ రాగానే Close చేయడం)
    if isinstance(ud.get("bot_pos"), dict):
        bp = ud["bot_pos"]
        if curr_candle_ts != bp["entry_candle_ts"]:
            exit_price = ltp
            if bp["side"] == "BUY":
                pnl = round((exit_price - bp["entry"]) * bp["qty"], 2)
                ud["cash"] = round(ud["cash"] + (exit_price * bp["qty"]), 2)
            else:  # SHORT COVER
                pnl = round((bp["entry"] - exit_price) * bp["qty"], 2)
                ud["cash"] = round(ud["cash"] + (bp["entry"] * bp["qty"]) + pnl, 2)

            ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
            ud["hist"].insert(0, {
                "Side": bp["side"],
                "Asset": bp["sym"],
                "Qty": bp["qty"],
                "Entry (₹)": bp["entry"],
                "Exit (₹)": exit_price,
                "P&L (₹)": f"{pnl:+,.2f}",
                "Entry Time": bp["time"],
                "Exit Time": now_ist.strftime("%H:%M:%S")
            })
