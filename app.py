import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, wave, struct, math
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")
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
            "pw": "123", "cash": 100000.0, "hist": [], "rpnl": 0.0,
            "bot_on": False, "bot_pos": None, "last_action_ts": 0.0,
            "bot_logs": [], "sound": None,
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.title("📈 URK Paper Trading Login")
    u = st.text_input("Username", value="admin")
    p = st.text_input("Password", type="password", value="123")
    if st.button("Login", type="primary"):
        if u in st.session_state.db and st.session_state.db[u]["pw"] == p:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Wrong login! (Use admin / 123)")
    st.stop()

ud = st.session_state.db[st.session_state.user]
if ud.get("sound"):
    trigger_beep(ud["sound"])
    ud["sound"] = None

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

@st.cache_data(ttl=2)
def get_chart_data(sym, timeframe):
    try:
        symbol_map = {
            "BTC-USD (₹)": "BTCUSDT",
            "ETH-USD (₹)": "ETHUSDT",
            "SOL-USD (₹)": "SOLUSDT"
        }
        binance_symbol = symbol_map.get(sym)
        if not binance_symbol:
            return pd.DataFrame()
        url = "https://data-api.binance.vision/api/v3/klines"
        params = {"symbol": binance_symbol, "interval": timeframe, "limit": 60}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            "OpenTime", "Open", "High", "Low", "Close", "Volume",
            "CloseTime", "QuoteVolume", "Trades", "TakerBuyBase",
            "TakerBuyQuote", "Ignore"
        ])
        df["OpenTime"] = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
        df.set_index("OpenTime", inplace=True)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception as e:
        st.error(f"Binance Chart Error: {e}")
        return pd.DataFrame()

c1, c2 = st.columns((3, 1))
c1.subheader(f"📈 Paper Trading | Cash: ₹{ud['cash']:,.2f}")
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

now_ist = datetime.now(IST)
cryptos = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)"]
col1, col2, col3 = st.columns(3)
sym = col1.selectbox("Select Asset:", cryptos, index=0)
qty = col2.number_input("Quantity:", min_value=1, max_value=100, value=1)
interval_sec = col3.number_input("Cycle Time (Sec):", min_value=10, max_value=300, value=60)

b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START LOOP", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["last_action_ts"] = 0.0
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 Loop Started!")
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

st.subheader("📊 Binance Live Chart")
timeframe = st.selectbox(
    "Chart Timeframe:", ["1m", "3m", "5m"], index=0,
    format_func=lambda x: {"1m": "1 Minute", "3m": "3 Minutes", "5m": "5 Minutes"}[x]
)
df_ch = get_chart_data(sym, timeframe)
if not df_ch.empty:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_ch.index, open=df_ch["Open"], high=df_ch["High"],
        low=df_ch["Low"], close=df_ch["Close"],
        name=sym.replace(" (₹)", "") + " / USDT"
    ))
    fig.update_layout(
        title=f"Binance {sym.replace(' (₹)', '')} | {timeframe}",
        height=450, margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False, template="plotly_dark"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: Binance Spot | Prices in USDT | Public market data")
else:
    st.warning("Binance chart data load అవ్వలేదు. Internet/API check చేయండి.")

st.subheader("📌 Current Position")
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    cur_p = get_ltp(bp["sym"]) or bp["entry"]
    live_pnl = round((cur_p - bp["entry"]) * bp["qty"], 2)
    pos_df = pd.DataFrame([{
        "Status": "🟢 BOUGHT (HOLDING)", "Asset": bp["sym"],
        "Qty": bp["qty"], "Buy Price (₹)": bp["entry"],
        "Live Price (₹)": cur_p, "Live P&L (₹)": f"{live_pnl:+,.2f}",
        "Buy Time": bp["time"]
    }])
    st.dataframe(pos_df, use_container_width=True, hide_index=True)
else:
    st.info("⚪ ప్రస్తుతం ఎలాంటి పొజిషన్ లేదు")

if ud["bot_on"]:
    ltp = get_ltp(sym)
    now_ts = time.time()
    elapsed = now_ts - ud["last_action_ts"]
    remaining = max(0, int(interval_sec - elapsed))
    if ltp is not None:
        st.info(f"🔄 BOT RUNNING | {sym} | Live Price: ₹{ltp:,.2f} | Next Action: {remaining}s")
        if ud["bot_pos"] is None and elapsed >= interval_sec:
            cost = round(ltp * qty, 2)
            if ud["cash"] >= cost:
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {
                    "sym": sym, "qty": qty, "entry": ltp,
                    "time": now_ist.strftime("%H:%M:%S")
                }
                ud["last_action_ts"] = now_ts
                ud["sound"] = "buy"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🟢 AUTO BUY: {qty} {sym} @ ₹{ltp:,.2f}")
                st.rerun()
            else:
                st.error("Insufficient Cash!")
        elif isinstance(ud["bot_pos"], dict) and elapsed >= interval_sec:
            bp = ud["bot_pos"]
            pnl = round((ltp - bp["entry"]) * bp["qty"], 2)
            ud["cash"] = round(ud["cash"] + (ltp * bp["qty"]), 2)
            ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
            ud["hist"].insert(0, {
                "Buy Time": bp["time"], "Sell Time": now_ist.strftime("%H:%M:%S"),
                "Asset": bp["sym"], "Qty": bp["qty"], "Buy Price": bp["entry"],
                "Sell Price": ltp, "P&L (₹)": pnl
            })
            ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🔴 AUTO SELL: {bp['qty']} {bp['sym']} @ ₹{ltp:,.2f} | P&L: ₹{pnl:+,.2f}")
            ud["bot_pos"] = None
            ud["last_action_ts"] = now_ts
            ud["sound"] = "sell"
            st.rerun()
    time.sleep(2)
    st.rerun()

if ud["hist"]:
    st.subheader("📋 Completed Orders")
    st.dataframe(pd.DataFrame(ud["hist"]), use_container_width=True, hide_index=True)

if ud["bot_logs"]:
    st.subheader("📜 Execution Logs")
    for log in ud["bot_logs"][:15]:
        st.text(log)
