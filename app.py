import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="URK Pro Auto Bot", page_icon="🚀", layout="centered")
IST = ZoneInfo("Asia/Kolkata")

def play_beep_js(kind="buy"):
    freq = 1050 if kind == "buy" else 520
    dur = 0.35 if kind == "buy" else 0.55
    components.html(f"""<script>
    try {{
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime({freq}, ctx.currentTime);
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + {dur});
    }} catch(e) {{}}
    </script>""", height=0)

if "db" not in st.session_state:
    st.session_state.db = {
        "admin": {
            "pw": "123", "cash": 100000.0, "hist": [], "rpnl": 0.0,
            "bot_on": False, "bot_pos": None, "traded_candles": [],
            "bot_logs": [], "sound": None
        }
    }
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.title("🚀 URK Pro Bot Login")
    u = st.text_input("Username", value="admin")
    p = st.text_input("Password", type="password", value="123")
    if st.button("Login", type="primary"):
        if u in st.session_state.db and st.session_state.db[u]["pw"] == p:
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Wrong login! (admin / 123)")
    st.stop()

ud = st.session_state.db[st.session_state.user]
if ud.get("sound"):
    play_beep_js(ud["sound"])
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
def get_chart_and_ema(sym, tf):
    try:
        is_crude = (sym == "CRUDEOIL (₹)")
        is_crypto = sym.endswith("-USD (₹)")
        tk = "CL=F" if is_crude else (sym.replace(" (₹)", "") if is_crypto else sym)
        m = get_usdinr() if (is_crude or is_crypto) else 1.0
        if "BTC-USD" in sym:
            m = m / 1000.0
        elif "ETH-USD" in sym:
            m = m / 100.0

        df = yf.Ticker(tk).history(period="1d" if is_crypto else "5d", interval="1m")
        if df.empty:
            return pd.DataFrame()
        if is_crude or is_crypto:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * m
        if tf == "3m":
            df = df.resample("3min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        elif tf == "5m":
            df = df.resample("5min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        if len(df) >= 12:
            df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
            return df.tail(60).copy()
    except Exception:
        pass
    return pd.DataFrame()

def run_bot_step(ud, df_live, sym, tf, qty, init_sl_pts, trail_gap_pts, ignore_mkt_hrs, now_ist):
    if not ud["bot_on"] or df_live.empty:
        return
    is_crypto = sym.endswith("-USD (₹)")
    in_mkt = True if (is_crypto or ignore_mkt_hrs) else (dtime(9, 15) <= now_ist.time() <= dtime(15, 25))
    if not in_mkt:
        st.warning("⏳ NSE మార్కెట్ సమయం ముగిసింది.")
        return

    cc = df_live.iloc[-1]
    cid = f"{tf}_{str(df_live.index[-1])}"
    co, ccl, cema = float(cc["Open"]), float(cc["Close"]), float(cc["EMA9"])
    tf_m = int(tf.replace("m", ""))
    rem_s = (tf_m * 60) - ((now_ist.minute % tf_m) * 60 + now_ist.second)
    st.info(f"🔄 **SCANNING ({tf})** | LTP: **₹{ccl:,.2f}** | 9 EMA: **₹{cema:,.2f}** | **{'🟢 GREEN' if ccl >= co else '🔴 RED'}** | Closes in: **{rem_s}s**")

    if ud["bot_pos"] is None:
        crossed_up = (ccl > co) and (co <= cema) and (ccl > cema)
        if crossed_up and (cid not in ud["traded_candles"]):
            cost = round(ccl * qty, 2)
            if ud["cash"] >= cost:
                ep = round(ccl, 2)
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {"sym": sym, "tf": tf, "qty": qty, "entry": ep, "high": ep, "sl": round(ep - init_sl_pts, 2), "candle_id": cid, "buy_time": now_ist.strftime("%H:%M:%S")}
                ud["traded_candles"].append(cid)
                ud["sound"] = "buy"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🟢 BUY: {qty} {sym} @ ₹{ep:,.2f}")
                st.rerun()
        return

    bp = ud["bot_pos"]
    cp = round(ccl, 2)
    if cp > bp["high"]:
        bp["high"] = cp
        nsl = round(bp["high"] - trail_gap_pts, 2)
        if cp > (bp["entry"] + trail_gap_pts) and nsl <= bp["entry"]:
            nsl = round(bp["entry"] + 0.50, 2)
        if nsl > bp["sl"]:
            bp["sl"] = nsl

    reason = None
    if cp <= bp["sl"]:
        reason = "🔒 LOCKED TSL HIT" if bp["sl"] > bp["entry"] else "🛑 INITIAL SL HIT"
    elif (cid != bp["candle_id"]) and (ccl < co):
        reason = "🔴 RED CANDLE SELL"

    if reason:
        pnl = round((cp - bp["entry"]) * bp["qty"], 2)
        ud["cash"] = round(ud["cash"] + (cp * bp["qty"]), 2)
        ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
        ud["hist"].insert(0, {"TF": bp["tf"], "Buy": bp["buy_time"], "Sell": now_ist.strftime("%H:%M:%S"), "Asset": bp["sym"], "Qty": bp["qty"], "Entry": bp["entry"], "Exit": cp, "Reason": reason, "P&L": pnl})
        ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] {reason} -> SOLD @ ₹{cp:,.2f} | P&L: ₹{pnl:+,.2f}")
        ud["bot_pos"] = None
        ud["sound"] = "sell"
        st.rerun()

# ---------------- UI LAYOUT ----------------
c1, c2 = st.columns((3, 1))
c1.subheader(f"🚀 URK Pro Bot | Cash: ₹{ud['cash']:,.2f}")
if c2.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

assets = ["BTC-USD (₹)", "ETH-USD (₹)", "SOL-USD (₹)", "SBIN.NS", "RELIANCE.NS", "TCS.NS", "^NSEI", "^NSEBANK", "CRUDEOIL (₹)"]
col1, col2, col3, col4 = st.columns((2, 1, 1, 1))
sym = col1.selectbox("Asset:", assets, index=0)
tf = col2.selectbox("TF:", ["1m", "3m", "5m"], index=0)
qty = col3.number_input("Qty:", 1, 500, 1)
if col4.button("🔊 Beep", use_container_width=True):
    ud["sound"] = "buy"
    st.rerun()

sc1, sc2, sc3 = st.columns(3)
init_sl_pts = sc1.number_input("Initial SL (₹):", 0.5, 500.0, 5.0, 0.5)
trail_gap_pts = sc2.number_input("Auto TSL Gap (₹):", 0.5, 500.0, 3.0, 0.5)
ignore_mkt_hrs = sc3.checkbox("24/7 Test Mode", value=True)

df_live = get_chart_and_ema(sym, tf)
ltp = round(float(df_live["Close"].iloc[-1]), 2) if not df_live.empty else None

un_pnl = round((ltp - ud["bot_pos"]["entry"]) * ud["bot_pos"]["qty"], 2) if (isinstance(ud.get("bot_pos"), dict) and ltp) else 0.0
pm1, pm2, pm3 = st.columns(3)
pm1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
pm2.metric("Unrealized P&L", f"₹{un_pnl:+,.2f}")
pm3.metric("Net Total P&L", f"₹{round(ud['rpnl'] + un_pnl, 2):+,.2f}")
st.divider()

now_ist = datetime.now(IST)
b1, b2, b3 = st.columns((2, 2, 1))
if b1.button("▶️ START BOT", type="primary", use_container_width=True):
    ud["bot_on"] = True
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🚀 Bot Started ({sym} - {tf})")
    st.rerun()
if b2.button("⏹️ STOP BOT", use_container_width=True):
    ud["bot_on"] = False
    ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🛑 Bot Stopped.")
    st.rerun()
if b3.button("🔄 Reset", use_container_width=True):
    ud.update({"bot_on": False, "bot_pos": None, "hist": [], "bot_logs": [], "traded_candles": [], "cash": 100000.0, "rpnl": 0.0})
    st.rerun()

if not df_live.empty:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_live.index, open=df_live["Open"], high=df_live["High"], low=df_live["Low"], close=df_live["Close"], name="Price"))
    fig.add_trace(go.Scatter(x=df_live.index, y=df_live["EMA9"], mode="lines", line=dict(color="#FFD700", width=2), name="9 EMA"))
    if isinstance(ud.get("bot_pos"), dict):
        bp = ud["bot_pos"]
        fig.add_hline(y=bp["entry"], line_dash="dash", line_color="lime", annotation_text=f"🟢 BUY @ ₹{bp['entry']:,.2f}", annotation_position="top left")
        sl_c = "#00FFAA" if bp["sl"] > bp["entry"] else "#FF4B4B"
        sl_t = f"🔒 LOCKED TSL @ ₹{bp['sl']:,.2f}" if bp["sl"] > bp["entry"] else f"🛑 TSL @ ₹{bp['sl']:,.2f}"
        fig.add_hline(y=bp["sl"], line_dash="dot", line_color=sl_c, annotation_text=sl_t, annotation_position="bottom left")
    fig.update_layout(title=f"{sym} ({tf}) - 9 EMA & TSL Chart", height=360, margin=dict(l=10, r=10, t=35, b=10), xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

if isinstance(ud.get("bot_pos"), dict) and ltp is not None:
    bp = ud["bot_pos"]
    st.caption("🎛️ **Chart TSL Quick Adjust:**")
    tc1, tc2, tc3, tc4 = st.columns((1, 1, 1.5, 1))
    if tc1.button("⬆️ +₹1 TSL", use_container_width=True):
        bp["sl"] = round(bp["sl"] + 1.0, 2)
        st.rerun()
    if tc2.button("⬇️ -₹1 TSL", use_container_width=True):
        bp["sl"] = round(bp["sl"] - 1.0, 2)
        st.rerun()
    c_sl = tc3.number_input("SL", value=float(bp["sl"]), step=0.5, label_visibility="collapsed")
    if tc4.button("Set TSL", use_container_width=True):
        bp["sl"] = round(c_sl, 2)
        st.rerun()

st.subheader("📌 Current Position")
if isinstance(ud.get("bot_pos"), dict) and ltp is not None:
    bp = ud["bot_pos"]
    live_pnl = round((ltp - bp["entry"]) * bp["qty"], 2)
    locked_pnl = round((bp["sl"] - bp["entry"]) * bp["qty"], 2)
