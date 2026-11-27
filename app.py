import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time, io, wave, struct, math
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Auto Trading V4", page_icon="🚀", layout="centered")
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
            "port": {},
            "hist": [],
            "rpnl": 0.0,
            "wl": ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"],
            "bot_on": False,
            "bot_pos": None,
            "bot_logs": [],
            "trades_today": 0,
            "last_date": str(datetime.now(IST).date()),
            "sound": None,
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.title("🚀 URK V4 Login")
    u = st.text_input("Username", value="admin")
    p = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if u in st.session_state.db and st.session_state.db[u]["pw"] == p:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Wrong login! (Use: admin / 123)")
    st.stop()

ud = st.session_state.db[st.session_state.user]
today_str = str(datetime.now(IST).date())
if ud.get("last_date") != today_str:
    ud["trades_today"], ud["last_date"] = 0, today_str
for k, v in (("bot_on", False), ("bot_pos", None), ("bot_logs", []), ("trades_today", 0), ("sound", None)):
    ud.setdefault(k, v)

if ud["sound"]:
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

@st.cache_data(ttl=4)
def get_ltp(sym):
    try:
        is_c = (sym == "CRUDEOIL DEC FUT (₹)")
        tk = "CL=F" if is_c else sym
        m = get_usdinr() if is_c else 1.0
        df = yf.Ticker(tk).history(period="2d", interval="1m")
        if df.empty:
            df = yf.Ticker(tk).history(period="5d", interval="15m")
        if not df.empty:
            return round(float(df["Close"].iloc[-1]) * m, 2)
    except Exception:
        pass
    return None

@st.cache_data(ttl=4)
def get_data(sym, tf):
    try:
        is_c = (sym == "CRUDEOIL DEC FUT (₹)")
        tk = "CL=F" if is_c else sym
        m = get_usdinr() if is_c else 1.0
        pm = {"3m": ("2d", "1m"), "5m": ("2d", "5m"), "15m": ("5d", "15m"), "1D": ("6mo", "1d")}
        per, inter = pm[tf]
        df = yf.Ticker(tk).history(period=per, interval=inter)
        if df.empty:
            return pd.DataFrame()
        if tf == "3m":
            df = df.resample("3min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        if is_c:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * m
        return df
    except Exception:
        return pd.DataFrame()

# --- STEP 1: 9 EMA + VWAP + PRICE STRATEGY ---
def add_ema_vwap(df):
    if df.empty or len(df) < 10:
        return df
    df = df.copy()
    # 1. Calculate 9 EMA
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()

    # 2. Calculate Intraday VWAP (resets daily)
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    if df["Volume"].sum() > 0:
        dates = df.index.date
        cum_pv = (tp * df["Volume"]).groupby(dates).cumsum()
        cum_vol = df["Volume"].groupby(dates).cumsum().replace(0, np.nan)
        df["VWAP"] = (cum_pv / cum_vol).ffill()
    else:
        # Indices (^NSEI / ^NSEBANK) have 0 volume on Yahoo Finance -> fallback to 20 SMA
        df["VWAP"] = df["Close"].rolling(20, min_periods=1).mean()

    # 3. Condition: Price > 9 EMA > VWAP
    df["Buy_Cond"] = (df["Close"] > df["EMA9"]) & (df["EMA9"] > df["VWAP"])
    df["Sell_Cond"] = (df["Close"] < df["EMA9"])
    return df

c1, c2 = st.columns((3, 1))
c1.subheader(f"🚀 URK V4 | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

inv_t = sum(v["qty"] * v["avg"] for v in ud["port"].values())
cur_t = sum(v["qty"] * (get_ltp(k) or v["avg"]) for k, v in ud["port"].items())
if isinstance(ud.get("bot_pos"), dict):
    bp = ud["bot_pos"]
    inv_t += bp["qty"] * bp["entry"]
    cur_t += bp["qty"] * (get_ltp(bp["sym"]) or bp["entry"])
un_pnl = round(cur_t - inv_t, 2)

pm1, pm2, pm3 = st.columns(3)
pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")
st.divider()

stocks = ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"]
t1, t2, t3, t4 = st.tabs(["🤖 Auto-Bot", "📊 Pro Chart", "⭐ Watchlist", "📜 History"])

with t1:
    now_ist = datetime.now(IST)
    curr_t = now_ist.time()
    bc1, bc2, bc3, bc4 = st.columns(4)
    bot_sym = bc1.selectbox("Asset:", stocks, index=0)
    bot_tf = bc2.selectbox("TF:", ["3m", "5m", "15m"], index=0)
    bot_qty = bc3.number_input("Qty:", 1, 1000, 10)
    max_tr = bc4.number_input("Max Trades:", 1, 10, 5)

    is_crude = (bot_sym == "CRUDEOIL DEC FUT (₹)")
    in_win = (dtime(9, 0) <= curr_t <= dtime(23, 30)) if is_crude else (dtime(9, 15) <= curr_t <= dtime(15, 25))
    sq_t = dtime(23, 30) if is_crude else dtime(15, 25)
    st.caption(f"🕒 IST: **{now_ist.strftime('%H:%M:%S')}** | Window: **{'09:00 - 23:30 (MCX)' if is_crude else '09:15 - 15:25 (NSE)'}** | Trades: **{ud['trades_today']}**")

    tc1, tc2, tc3 = st.columns((2, 1, 1))
    sl_pts = tc1.number_input("Stop Loss (₹):", 0.5, 500.0, 2.0, 0.5)
    tgt_pts = tc2.number_input("Target (₹):", 0.5, 1000.0, 4.0, 0.5)
    u_tr = tc3.checkbox("Trailing SL", value=True)

    b1, b2, b3 = st.columns((2, 2, 1))
    if b1.button("▶️ START BOT", use_container_width=True, type="primary"):
        ud["bot_on"] = True
        ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] Bot STARTED on {bot_sym} (9EMA > VWAP)")
        st.rerun()
    if b2.button("⏹️ STOP BOT", use_container_width=True):
        ud["bot_on"] = False
        ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] Bot STOPPED")
        st.rerun()
    if b3.button("🔊 Beep", use_container_width=True):
        trigger_beep("buy")

    if ud["bot_on"]:
        st.success("🟢 BOT RUNNING (Strategy: Price > 9 EMA > VWAP)")
    else:
        st.error("🔴 BOT STOPPED")

    ltp = get_ltp(bot_sym)
    df_bot = add_ema_vwap(get_data(bot_sym, bot_tf))

    if ltp is not None:
        if not df_bot.empty and "EMA9" in df_bot.columns:
            e9_val = round(float(df_bot["EMA9"].iloc[-1]), 2)
            vw_val = round(float(df_bot["VWAP"].iloc[-1]), 2)
            cond_ok = bool(df_bot["Buy_Cond"].iloc[-1])
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Live LTP", f"₹{ltp}")
            m2.metric("9 EMA", f"₹{e9_val}")
            m3.metric("VWAP", f"₹{vw_val}")
            m4.metric("Signal", "🟢 BUY READY" if cond_ok else "⏳ WAIT")
        else:
            st.metric("Live LTP", f"₹{ltp}")

        # ACTIVE TRADE & EXIT LOGIC
        if isinstance(ud.get("bot_pos"), dict):
            p = ud["bot_pos"]
            pltp = get_ltp(p["sym"]) or ltp
            if ud["bot_on"] and u_tr and pltp > p.get("hi", p["entry"]):
                diff = round(pltp - p.get("hi", p["entry"]), 2)
                if diff >= 0.5:
                    ud["bot_pos"]["hi"] = pltp
                    ud["bot_pos"]["sl"] = round(p["sl"] + diff, 2)
                    p = ud["bot_pos"]

            rpnl = round((pltp - p["entry"]) * p["qty"], 2)
            st.info(f"{'🟢' if rpnl>=0 else '🔴'} **Active Trade:** {p['sym']} | Qty: {p['qty']} | Entry: ₹{p['entry']} | LTP: ₹{pltp} | SL: ₹{p['sl']} | TGT: ₹{p['tgt']} | **Live P&L: ₹{rpnl:+,.2f}**")

            if st.button("🚨 EXIT TRADE NOW (Manual Exit)", type="primary", use_container_width=True):
                ud["rpnl"] = round(ud["rpnl"] + rpnl, 2)
                ud["cash"] = round(ud["cash"] + pltp * p["qty"], 2)
                ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": p["sym"], "Type": "MANUAL-EXIT", "Qty": p["qty"], "Price": pltp, "P&L": rpnl})
                ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] 🚨 MANUAL EXIT {p['sym']} @ ₹{pltp} | P&L: ₹{rpnl:+,.2f}")
                ud["bot_pos"], ud["sound"] = None, "exit"
                st.rerun()

            if ud["bot_on"]:
                reason = "SL HIT" if pltp <= p["sl"] else ("TARGET HIT" if pltp >= p["tgt"] else ("SQUARE-OFF" if curr_t >= sq_t else None))
                if reason:
                    ud["rpnl"] = round(ud["rpnl"] + rpnl, 2)
                    ud["cash"] = round(ud["cash"] + pltp * p["qty"], 2)
                    ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": p["sym"], "Type": reason, "Qty": p["qty"], "Price": pltp, "P&L": rpnl})
