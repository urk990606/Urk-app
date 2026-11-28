import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK 9-EMA Multi-TF Bot", page_icon="📈", layout="centered")
IST = ZoneInfo("Asia/Kolkata")

# ---------------- BROWSER WEB AUDIO BEEP ----------------
def play_beep_js(kind="buy"):
    freq = 1050 if kind == "buy" else 520
    dur = 0.35 if kind == "buy" else 0.55
    components.html(
        f"""
        <script>
        try {{
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime({freq}, ctx.currentTime);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + {dur});
        }} catch(e) {{ console.log(e); }}
        </script>
        """,
        height=0,
    )

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
            "traded_candles": [],
            "bot_logs": [],
            "sound": None,
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- LOGIN SCREEN ----------------
if not st.session_state.user:
    st.title("📈 URK 9-EMA Bot Login")
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
    play_beep_js(ud["sound"])
    ud["sound"] = None

# ---------------- 24/7 LIVE PRICE & MULTI-TF 9 EMA DATA ----------------
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
def get_chart_and_ema(sym, tf):
    try:
        tk = sym.replace(" (₹)", "")
        m = get_usdinr()
        if "BTC-USD" in sym:
            m = m / 1000.0
        elif "ETH-USD" in sym:
            m = m / 100.0

        # 1m డేటా తెచ్చి దాన్ని 1m, 3m, లేదా 5m లోకి కచ్చితంగా మార్చడం (Resample)
        df = yf.Ticker(tk).history(period="1d", interval="1m")
        if not df.empty:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * m

            if tf == "3m":
                df = df.resample("3min").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
            elif tf == "5m":
                df = df.resample("5min").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()

            if len(df) >= 12:
                df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
                return df.tail(60).copy()
    except Exception:
        pass
    return pd.DataFrame()

# ---------------- HEADER & P&L ----------------
c1, c2 = st.columns((3, 1))
c1.subheader(f"📈 9-EMA Bot | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]
timeframes = ["1m", "3m", "5m"]

col1, col2, col3, col4 = st.columns((2, 1, 1, 1))
sym = col1.selectbox("24/7 Asset:", cryptos, index=0)
tf = col2.selectbox("Timeframe:", timeframes, index=0)
qty = col3.number_input("Qty:", 1, 100, 1)
if col4.button("🔊 Beep", use_container_width=True):
    ud["sound"] = "buy"
    st.rerun()

df_live = get_chart_and_ema(sym, tf)
ltp = round(float(df_live["Close"].iloc[-1]), 2) if not df_live.empty else None

un_pnl = 0.0
if isinstance(ud.get("bot_pos"), dict) and ltp is not None:
    bp = ud["bot_pos"]
    un_pnl = round((ltp - bp["entry"]) * bp["qty"], 2)

pm1, pm2, pm3 = st.columns(3)
pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")
st.divider()

# ---------------- BOT START / STOP CONTROLS ----------------
now_ist = datetime.now(IST)
b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START 9-EMA BOT", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 9-EMA Bot Started ({sym} - {tf})")
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
    ud["traded_candles"] = []
    ud["cash"] = 100000.0
    ud["rpnl"] = 0.0
    st.rerun()

# ---------------- CANDLESTICK CHART + 9 EMA LINE ----------------
if not df_live.empty:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_live.index,
        open=df_live["Open"],
        high=df_live["High"],
        low=df_live["Low"],
        close=df_live["Close"],
        name="Candles"
    ))
    fig.add_trace(go.Scatter(
        x=df_live.index,
        y=df_live["EMA9"],
        mode="lines",
        line=dict(color="#FFD700", width=2),
        name="9 EMA"
    ))
    if isinstance(ud.get("bot_pos"), dict):
        fig.add_hline(
            y=ud["bot_pos"]["entry"],
            line_dash="dash",
            line_color="lime",
            annotation_text=f"🟢 BOUGHT @ ₹{ud['bot_pos']['entry']:,.2f}",
            annotation_position="top left"
        )
    fig.update_layout(
        title=f"{sym} - {tf} Chart with 9 EMA Line",
        height=380,
        margin=dict(l=10, r=10, t=35, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark"
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------- CURRENT POSITION ('BOUGHT' STATUS) ----------------
st.subheader("📌 Current Position (ప్రస్తుత పొజిషన్)")
if isinstance(ud.get("bot_pos"), dict) and ltp is not None:
    bp = ud["bot_pos"]
    live_pnl = round((ltp - bp["entry"]) * bp["qty"], 2)
    pos_df = pd.DataFrame([{
        "Status": "🟢 BOUGHT (HOLDING)",
        "Asset": bp["sym"],
        "TF": bp["tf"],
        "Qty": bp["qty"],
        "Buy Price (₹)": bp["entry"],
        "Live Price (₹)": ltp,
        "Live P&L (₹)": f"{live_pnl:+,.2f}",
        "Candle Time": bp["candle_id"]
    }])
    st.dataframe(pos_df, use_container_width=True, hide_index=True)
else:
    st.info(f"⚪ పొజిషన్ లేదు — {tf} గ్రీన్ క్యాండిల్ 9 EMA ని కింద నుండి పైకి క్రాస్ చేసినప్పుడు BUY అవుతుంది.")

# ---------------- 9 EMA CROSSOVER EXECUTION ENGINE ----------------
if ud["bot_on"] and not df_live.empty:
    curr_candle = df_live.iloc[-1]
    curr_candle_id = f"{tf}_{str(df_live.index[-1])}"
    
    c_open = float(curr_candle["Open"])
    c_close = float(curr_candle["Close"])
    c_ema9 = float(curr_candle["EMA9"])
    is_green = c_close > c_open

    # క్యాండిల్ క్లోజ్ అవ్వడానికి మిగిలిన సెకన్లు లెక్కించడం
    tf_mins = int(tf.replace("m", ""))
    rem_sec = (tf_mins * 60) - ((now_ist.minute % tf_mins) * 60 + now_ist.second)

    st.info(
        f"🔄 **SCANNING ({tf})** | LTP: **₹{c_close:,.2f}** | 9 EMA: **₹{c_ema9:,.2f}** | "
        f"Candle: **{'🟢 GREEN' if is_green else '🔴 RED'}** | Candle closes in: **{rem_sec}s**"
    )

    # 1. BUY CONDITION
    if ud["bot_pos"] is None:
        crossed_up = is_green and (c_open <= c_ema9) and (c_close > c_ema9)
        if crossed_up and (curr_candle_id not in ud["traded_candles"]):
            cost = round(c_close * qty, 2)
            if ud["cash"] >= cost:
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {
                    "sym": sym,
                    "tf": tf,
                    "qty": qty,
                    "entry": round(c_close, 2),
                    "candle_id": curr_candle_id,
                    "buy_time": now_ist.strftime("%H:%M:%S")
                }
                ud["traded_candles"].append(curr_candle_id)
                ud["sound"] = "buy"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🟢 {tf} 9-EMA BUY: {qty} {sym} @ ₹{c_close:,.2f}")
                st.rerun()

    # 2. SELL CONDITION (ఆ టైమ్‌ఫ్రేమ్ క్యాండిల్ క్లోజ్ అవ్వగానే SELL)
    elif isinstance(ud["bot_pos"], dict):
        bp = ud["bot_pos"]
        if curr_candle_id != bp["candle_id"]:
            exit_price = round(c_close, 2)
            pnl = round((exit_price - bp["entry"]) * bp["qty"], 2)
            ud["cash"] = round(ud["cash"] + (exit_price * bp["qty"]), 2)
            ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
            ud["hist"].insert(0, {
                "TF": bp["tf"],
                "Buy Time": bp["buy_time"],
                "Sell Time": now_ist.strftime("%H:%M:%S"),
                "Asset": bp["sym"],
                "Qty": bp["qty"],
                "Buy Price": bp["entry"],
                "Sell Price": exit_price,
                "P&L (₹)": pnl
            })
            ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🔴 {bp['tf']} CANDLE CLOSED SELL: {bp['qty']} {bp['sym']} @ ₹{exit_price:,.2f} | P&L: ₹{pnl:+,.2f}")
