import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import traceback
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Pro Auto Trading", page_icon="📈", layout="centered")
IST = ZoneInfo("Asia/Kolkata")

def play_beep(beep_type="buy"):
    try:
        if beep_type == "buy":
            js = """
            <script>
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                function tone(freq, start, dur) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
                    gain.gain.setValueAtTime(0.4, ctx.currentTime + start);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(ctx.currentTime + start);
                    osc.stop(ctx.currentTime + start + dur);
                }
                tone(880, 0.0, 0.18);
                tone(1174, 0.22, 0.25);
            } catch(e) {}
            </script>
            """
        else:
            js = """
            <script>
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(600, ctx.currentTime);
                gain.gain.setValueAtTime(0.4, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.45);
            } catch(e) {}
            </script>
            """
        components.html(js, height=0, width=0)
    except Exception:
        pass

if 'db' not in st.session_state:
    st.session_state.db = {
        "admin": {
            "pw": "123", "cash": 100000.0, "port": {}, "hist": [], "rpnl": 0.0,
            "wl": ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"],
            "bot_on": False, "bot_pos": None, "bot_logs": [], "trades_today": 0,
            "last_date": str(datetime.now(IST).date()),
            "play_sound": None
        }
    }
if 'user' not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.title("📈 URK Paper Trading")
    u = st.text_input("Username", value="admin")
    p = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if u in st.session_state.db and st.session_state.db[u]["pw"] == p:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Wrong login! (Use: admin / 123)")
    st.stop()

try:
    ud = st.session_state.db[st.session_state.user]
    today_str = str(datetime.now(IST).date())
    if ud.get("last_date") != today_str:
        ud["trades_today"] = 0
        ud["last_date"] = today_str

    for k, v in [("bot_on", False), ("bot_pos", None), ("bot_logs", []), ("trades_today", 0), ("play_sound", None)]:
        ud.setdefault(k, v)

    if ud["play_sound"]:
        play_beep(ud["play_sound"])
        ud["play_sound"] = None

    @st.cache_data(ttl=60)
    def get_usdinr():
        try:
            fx = yf.Ticker("USDINR=X").history(period="2d", interval="15m")
            if not fx.empty:
                return float(fx["Close"].iloc[-1])
        except Exception:
            pass
        return 84.5

    def fetch_raw_history(sym, per, inter):
        try:
            if sym == "CRUDEOIL DEC FUT (₹)":
                for t in ("CL=F", "BZ=F"):
                    df = yf.Ticker(t).history(period=per, interval=inter)
                    if df is not None and not df.empty:
                        return df
                return pd.DataFrame()
            else:
                df = yf.Ticker(sym).history(period=per, interval=inter)
                return df if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=4)
    def get_ltp(sym):
        try:
            is_crude = (sym == "CRUDEOIL DEC FUT (₹)")
            mult = get_usdinr() if is_crude else 1.0
            df = fetch_raw_history(sym, "2d", "1m")
            if df.empty:
                df = fetch_raw_history(sym, "5d", "15m")
            if not df.empty:
                return round(float(df["Close"].iloc[-1]) * mult, 2)
        except Exception:
            pass
        return None

    @st.cache_data(ttl=4)
    def get_data(sym, tf):
        try:
            is_crude = (sym == "CRUDEOIL DEC FUT (₹)")
            mult = get_usdinr() if is_crude else 1.0

            p_map = {"3m": ("2d", "1m"), "5m": ("2d", "5m"), "15m": ("5d", "15m"), "1D": ("6mo", "1d")}
            per, inter = p_map[tf]
            df = fetch_raw_history(sym, per, inter)

            if df.empty:
                return pd.DataFrame()

            if tf == "3m":
                df = df.resample("3min").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()

            if df.empty:
                return pd.DataFrame()

            if is_crude:
                for col in ("Open", "High", "Low", "Close"):
                    df[col] = df[col] * mult

            df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
            tp = (df["High"] + df["Low"] + df["Close"]) / 3
            vol = df["Volume"].replace(0, 1)
            df["VWAP"] = (tp * vol).groupby(df.index.date).cumsum() / vol.groupby(df.index.date).cumsum()
            tr = pd.concat((
                df["High"] - df["Low"],
                (df["High"] - df["Close"].shift()).abs(),
                (df["Low"] - df["Close"].shift()).abs()
            ), axis=1).max(axis=1)
            atr = tr.ewm(alpha=0.1, adjust=False).mean()
            hl2 = (df["High"] + df["Low"]) / 2
            ub, lb = hl2 + 3 * atr, hl2 - 3 * atr

            n = len(df)
            st_line = [np.nan for _ in range(n)]
            d = [1 for _ in range(n)]
            for i in range(1, n):
                if df["Close"].iloc[i] > ub.iloc[i - 1]:
                    d[i] = 1
                elif df["Close"].iloc[i] < lb.iloc[i - 1]:
                    d[i] = -1
                else:
                    d[i] = d[i - 1]
                st_line[i] = lb.iloc[i] if d[i] == 1 else ub.iloc[i]

            df["ST"] = st_line
            df["ST_Dir"] = d
            df["ST_Up"] = np.where(df["ST_Dir"] == 1, df["ST"], np.nan)
            df["ST_Dn"] = np.where(df["ST_Dir"] == -1, df["ST"], np.nan)
            return df
        except Exception:
            return pd.DataFrame()

    # ==========================================
    # TOP HEADER & ALWAYS-VISIBLE LIVE P&L BANNER
    # ==========================================
    c1, c2 = st.columns((3, 1))
    c1.subheader(f"📈 URK | Cash: ₹{ud['cash']:,.2f}")
    if c2.button("🚪 Logout", use_container_width=True):
        st.session_state.user = None
        st.rerun()

    inv_total, cur_total = 0.0, 0.0
    for k, v in ud["port"].items():
        p_now = get_ltp(k) or v["avg"]
        inv_total += v["qty"] * v["avg"]
        cur_total += v["qty"] * p_now
    if ud["bot_pos"]:
        bp = ud["bot_pos"]
        p_now = get_ltp(bp["sym"]) or bp["entry"]
        inv_total += bp["qty"] * bp["entry"]
        cur_total += bp["qty"] * p_now

    unreal_pnl = round(cur_total - inv_total, 2)
    net_pnl = round(ud["rpnl"] + unreal_pnl, 2)

    pm1, pm2, pm3 = st.columns(3)
    pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
    pm2.metric("Unrealized P&L", f"₹{unreal_pnl:+,.2f}")
    pm3.metric("Net Total P&L", f"₹{net_pnl:+,.2f}")
    st.divider()

    stocks = ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"]
    t1, t2, t3, t4 = st.tabs(["🤖 Auto-Bot", "📊 Pro Chart & Trade", "⭐ Watchlist", "📜 History & Holdings"])

    # ==========================================
    # TAB 1: AUTO-BOT
    # ==========================================
    with t1:
        now_ist = datetime.now(IST)
        curr_t = now_ist.time()

        bc1, bc2, bc3, bc4 = st.columns(4)
        bot_sym = bc1.selectbox("Stock / Asset:", stocks, index=0)
        bot_tf = bc2.selectbox("TF:", ["3m", "5m", "15m"], index=0)
        bot_qty = bc3.number_input("Qty:", 1, 1000, 10)
        max_trades = bc4.number_input("Max Trades:", 1, 10, 5)

        if bot_sym == "CRUDEOIL DEC FUT (₹)":
            in_window = dtime(9, 0) <= curr_t <= dtime(23, 30)
            win_text = "09:00 - 23:30 (MCX)"
            sq_off_time = dtime(23, 30)
        else:
            in_window = dtime(9, 15) <= curr_t <= dtime(15, 25)
            win_text = "09:15 - 15:25 (NSE)"
            sq_off_time = dtime(15, 25)

        st.caption(f"🕒 IST: **{now_ist.strftime('%H:%M:%S')}** | Window: **{win_text}** | Trades Today: **{ud['trades_today']}**")

        cc_a, cc_b, cc_c = st.columns(3)
        use_st = cc_a.checkbox("Supertrend Bull", value=True)
        use_vwap = cc_b.checkbox("Above VWAP", value=True)
        use_ema = cc_c.checkbox("Above 9 EMA", value=True)

        tr_c1, tr_c2, tr_c3 = st.columns((2, 1, 1))
        rr_ratio = tr_c1.slider("Target R:R:", 1.0, 5.0, 2.0, 0.5)
        use_trail = tr_c2.checkbox("Auto Trailing SL", value=True)
        trail_step = tr_c3.number_input("Trail Step (₹):", 0.5, 50.0, 1.0, 0.5)
