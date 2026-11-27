import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io, wave, struct, math
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Pro Auto Trading", page_icon="📈", layout="centered")
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
    st.session_state.db = {"admin": {"pw": "123", "cash": 100000.0, "port": {}, "hist": [], "rpnl": 0.0, "wl": ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"], "bot_on": False, "bot_pos": None, "bot_logs": [], "trades_today": 0, "last_date": str(datetime.now(IST).date()), "sound": None}}
if "user" not in st.session_state:
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

ud = st.session_state.db[st.session_state.user]
today_str = str(datetime.now(IST).date())
if ud.get("last_date") != today_str:
    ud["trades_today"], ud["last_date"] = 0, today_str
for k, v in (("bot_on", False), ("bot_pos", None), ("bot_logs", []), ("trades_today", 0), ("sound", None)):
    ud.setdefault(k, v)

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
        df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        vol = df["Volume"].replace(0, 1)
        df["VWAP"] = (tp * vol).groupby(df.index.date).cumsum() / vol.groupby(df.index.date).cumsum()
        tr = pd.concat((df["High"] - df["Low"], (df["High"] - df["Close"].shift()).abs(), (df["Low"] - df["Close"].shift()).abs()), axis=1).max(axis=1)
        atr = tr.ewm(alpha=0.1, adjust=False).mean()
        hl2 = (df["High"] + df["Low"]) / 2
        ub, lb = hl2 + 3 * atr, hl2 - 3 * atr
        n = len(df)
        st_l = [np.nan for _ in range(n)]
        d = [1 for _ in range(n)]
        for i in range(1, n):
            d[i] = 1 if df["Close"].iloc[i] > ub.iloc[i-1] else (-1 if df["Close"].iloc[i] < lb.iloc[i-1] else d[i-1])
            st_l[i] = lb.iloc[i] if d[i] == 1 else ub.iloc[i]
        df["ST"], df["ST_Dir"] = st_l, d
        df["ST_Up"] = np.where(df["ST_Dir"] == 1, df["ST"], np.nan)
        df["ST_Dn"] = np.where(df["ST_Dir"] == -1, df["ST"], np.nan)
        return df
    except Exception:
        return pd.DataFrame()

c1, c2 = st.columns((3, 1))
c1.subheader(f"📈 URK | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

stocks = ["SBIN.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS", "^NSEI", "^NSEBANK", "CRUDEOIL DEC FUT (₹)"]
t1, t2, t3, t4 = st.tabs(["🤖 Auto-Bot", "📊 Pro Chart & Trade", "⭐ Watchlist", "📜 History"])

with t1:
    bc1, bc2, bc3, bc4 = st.columns(4)
    bot_sym = bc1.selectbox("Asset:", stocks, index=0, key="bsym")
    bot_tf = bc2.selectbox("TF:", ["3m", "5m", "15m"], index=0, key="btf")
    bot_qty = bc3.number_input("Qty:", 1, 1000, 10, key="bqty")
    max_tr = bc4.number_input("Max Trades:", 1, 10, 5, key="bmax")

    ca, cb, cc, cd = st.columns(4)
    u_st = ca.checkbox("Supertrend", value=True, key="chk_st")
    u_vw = cb.checkbox("VWAP", value=True, key="chk_vw")
    u_em = cc.checkbox("9 EMA", value=False, key="chk_em")
    u_bk = cd.checkbox("Prev High", value=False, key="chk_bk")

    tc1, tc2, tc3 = st.columns((2, 1, 1))
    rr = tc1.slider("Target R:R:", 1.0, 5.0, 2.0, 0.5, key="sl_rr")
    u_tr = tc2.checkbox("Trailing SL", value=True, key="chk_tr")
    t_step = tc3.number_input("Trail Step:", 0.5, 50.0, 1.0, 0.5, key="num_ts")

    b1, b2, b3 = st.columns((2, 2, 1))
    if b1.button("▶️ START BOT", use_container_width=True, type="primary"):
        ud["bot_on"] = True
        ud["bot_logs"].append(f"[{datetime.now(IST).strftime('%H:%M:%S')}] Bot STARTED on {bot_sym}")
        st.rerun()
    if b2.button("⏹️ STOP BOT", use_container_width=True):
        ud["bot_on"] = False
        ud["bot_logs"].append(f"[{datetime.now(IST).strftime('%H:%M:%S')}] Bot STOPPED")
        st.rerun()
    if b3.button("🔊 Beep", use_container_width=True, type="primary"):
        trigger_beep("buy")

    @st.fragment(run_every=5)
    def live_bot_engine():
        if ud["sound"]:
            trigger_beep(ud["sound"])
            ud["sound"] = None

        now_ist = datetime.now(IST)
        curr_t = now_ist.time()
        is_crude = (bot_sym == "CRUDEOIL DEC FUT (₹)")
        in_win = (dtime(9, 0) <= curr_t <= dtime(23, 30)) if is_crude else (dtime(9, 15) <= curr_t <= dtime(15, 25))
        sq_t = dtime(23, 30) if is_crude else dtime(15, 25)

        # Live P&L Banner inside fragment
        inv_t = sum(v["qty"] * v["avg"] for v in ud["port"].values())
        cur_t = sum(v["qty"] * (get_ltp(k) or v["avg"]) for k, v in ud["port"].items())
        if ud["bot_pos"]:
            bp = ud["bot_pos"]
            inv_t += bp["qty"] * bp["entry"]
            cur_t += bp["qty"] * (get_ltp(bp["sym"]) or bp["entry"])
        un_pnl = round(cur_t - inv_t, 2)

        pm1, pm2, pm3 = st.columns(3)
        pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
        pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
        pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")

        st.caption(f"🕒 IST: **{now_ist.strftime('%H:%M:%S')}** | Cash: **₹{ud['cash']:,.2f}** | Trades: **{ud['trades_today']}**")
        if ud["bot_on"]:
            st.success("🟢 BOT RUNNING (Auto-Scanning every 5s...)")
        else:
            st.error("🔴 BOT STOPPED")

        bdf = get_data(bot_sym, bot_tf)
        if len(bdf) >= 3:
            ltp = round(float(bdf["Close"].iloc[-1]), 2)
            vwap = round(float(bdf["VWAP"].iloc[-1]), 2)
            ema9 = round(float(bdf["EMA9"].iloc[-1]), 2)
            stv = round(float(bdf["ST"].iloc[-1]), 2) if not np.isnan(bdf["ST"].iloc[-1]) else ltp
            stb = bdf["ST_Dir"].iloc[-1] == 1
            ph, pl = round(float(bdf["High"].iloc[-2]), 2), round(float(bdf["Low"].iloc[-2]), 2)

            c_vw = (ltp > vwap) if u_vw else True
            c_em = (ltp > ema9) if u_em else True
            c_st = (stb and ltp > stv) if u_st else True
            c_bk = (ltp > ph) if u_bk else True

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("LTP", f"₹{ltp}")
            m2.metric("VWAP", f"₹{vwap}", "✅" if ltp > vwap else "❌")
            m3.metric("9 EMA", f"₹{ema9}", "✅" if ltp > ema9 else "❌")
            m4.metric("Supertrend", f"₹{stv}", "✅" if (stb and ltp > stv) else "❌")

            if ud["bot_pos"] is not None:
                p = ud["bot_pos"]
                pltp = get_ltp(p["sym"]) or ltp
                if ud["bot_on"] and u_tr and pltp > p.get("hi", p["entry"]):
                    diff = pltp - p.get("hi", p["entry"])
                    if diff >= t_step:
                        ud["bot_pos"]["hi"] = pltp
                        ud["bot_pos"]["sl"] = round(p["sl"] + diff, 2)
                        p = ud["bot_pos"]

                rpnl = round((pltp - p["entry"]) * p["qty"], 2)
                st.info(f"{'🟢' if rpnl>=0 else '🔴'} **Active Trade:** {p['sym']} | Qty: {p['qty']} | Entry: ₹{p['entry']} | LTP: ₹{pltp} | SL: ₹{p['sl']} | TGT: ₹{p['tgt']} | **Live P&L: ₹{rpnl:+,.2f}**")

                if st.button("🚨 EXIT TRADE NOW (Manual Exit)", type="primary", use_container_width=True, key="btn_man_exit"):
                    ud["rpnl"] = round(ud["rpnl"] + rpnl, 2)
                    ud["cash"] = round(ud["cash"] + pltp * p["qty"], 2)
                    ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": p["sym"], "Type": "MANUAL-EXIT", "Qty": p["qty"], "Price": pltp, "P&L": rpnl})
