import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone
import time
import html

# ============================================================
# EMA 9/21 PAPER TRADING APP - Binance public BTCUSDT data
# Paper trading only. No broker orders are placed.
# ===============================================================
st.set_page_config(page_title="EMA 9/21 Paper Trader", layout="wide")

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOL = "BTCUSDT"
TIMEFRAMES = {"1 minute": "1m", "3 minutes": "3m", "5 minutes": "5m", "15 minutes": "15m"}

st.title("₿ BTCUSDT – EMA 3 / EMA 8 Paper Trading")
st.caption("Live public Binance data • Paper trading only • Not financial advice")

# ---- Session state ----
defaults = {
    "logged_in": False,
    "bot_running": False,
    "position": None,
    "trade_log": [],
    "cash_usdt": 10000.0,
    "last_signal_candle": None,
    "last_trail_candle": None,
    "active_interval": "1m",
    "sound_event": None,
    "last_exit_message": "",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---- Simple optional app lock ----
with st.sidebar:
    st.header("Settings")
    password = st.text_input("App password", type="password", help="Default password: 123")
    if not st.session_state.logged_in:
        if st.button("Unlock app", use_container_width=True):
            if password == "123":
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Wrong password")
    else:
        st.success("App unlocked")
        if st.button("Lock app", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.bot_running = False
            st.rerun()

if not st.session_state.logged_in:
    st.info("Sidebar లో password `123` ఇచ్చి Unlock app నొక్కండి.")
    st.stop()

with st.sidebar:
    st.divider()
    interval_label = st.selectbox("Chart timeframe", list(TIMEFRAMES.keys()),
                                  index=list(TIMEFRAMES.values()).index(st.session_state.active_interval))
    selected_interval = TIMEFRAMES[interval_label]
    risk_reward = st.selectbox("Target risk : reward", ["1:1", "1:1.5", "1:2", "1:3"], index=2)
    rr_value = float(risk_reward.split(":")[1])
    qty_btc = st.number_input("Paper quantity (BTC)", min_value=0.0001, max_value=1.0,
                              value=0.001, step=0.0001, format="%.4f")
    refresh_seconds = st.slider("Refresh interval (seconds)", 2, 15, 3)
    st.caption("BUY: EMA3 crosses above EMA8 on a completed candle.")
    st.caption("Entry: crossover candle close • SL: previous candle low.")
    st.caption("TSL: previous completed candle low; it only moves upward.")

if st.session_state.bot_running and selected_interval != st.session_state.active_interval:
    st.warning("Bot running లో timeframe మార్చలేరు. ముందుగా Stop Bot నొక్కండి.")
    selected_interval = st.session_state.active_interval

# ---- Data ----
@st.cache_data(ttl=2, show_spinner=False)
def fetch_candles(interval: str, limit: int = 300):
    params = {"symbol": SYMBOL, "interval": interval, "limit": limit}
    response = requests.get(BINANCE_URL, params=params, timeout=12)
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list) or len(raw) < 30:
        raise ValueError("Binance returned insufficient candle data")
    columns = ["open_time", "open", "high", "low", "close", "volume",
               "close_time", "quote_volume", "trades", "taker_buy_base",
               "taker_buy_quote", "ignore"]
    df = pd.DataFrame(raw, columns=columns)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    df["ema9"] = df["close"].ewm(span=3, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=8, adjust=False).mean()
    return df

try:
    df = fetch_candles(selected_interval)
except Exception as exc:
    st.error(f"Market data load కాలేదు: {exc}")
    st.info("Internet connection లేదా Binance API అందుబాటులో ఉందో చూడండి.")
    st.stop()

if len(df) < 25:
    st.error("EMA calculation కోసం candle data సరిపోలేదు.")
    st.stop()

# Binance returns the currently forming candle as the last row.
# All strategy signals use completed candles only.
closed = df.iloc[:-1].copy()
live = df.iloc[-1]
if len(closed) < 23:
    st.error("Completed candles సరిపోలేదు.")
    st.stop()

# ---- Sound helper ----
def play_sound(kind: str):
    tones = {
        "buy": (880, 0.18),
        "exit": (520, 0.22),
        "target": (1040, 0.35),
        "stop": (260, 0.35),
    }
    freq, duration = tones.get(kind, (600, 0.2))
    # Browser autoplay policies may block automatic playback on some phones.
    audio_html = f"""
    <audio autoplay>
      <source src="data:audio/wav;base64,{make_tone_base64(freq, duration)}" type="audio/wav">
    </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

def make_tone_base64(freq, duration):
    # Small WAV tone generated without external audio dependencies.
    import math, struct, wave, io, base64
    sample_rate = 22050
    count = int(sample_rate * duration)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(count):
            envelope = min(1.0, i / 300, (count - i) / 500)
            sample = int(9000 * envelope * math.sin(2 * math.pi * freq * i / sample_rate))
            frames.extend(struct.pack("<h", sample))
        wav.writeframes(bytes(frames))
    return base64.b64encode(buffer.getvalue()).decode("ascii")

# ---- Position handling ----
def close_position(exit_price: float, reason: str):
    pos = st.session_state.position
    if not isinstance(pos, dict):
        return
    entry = float(pos.get("entry", exit_price))
    qty = float(pos.get("qty", qty_btc))
    pnl = (float(exit_price) - entry) * qty
    st.session_state.cash_usdt += float(exit_price) * qty
    st.session_state.trade_log.insert(0, {
        "Time (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "Side": "SELL",
        "Reason": reason,
        "Entry": entry,
        "Exit": float(exit_price),
        "Qty BTC": qty,
        "P&L USDT": pnl,
    })
    st.session_state.position = None
    st.session_state.last_exit_message = f"{reason} | P&L: {pnl:.4f} USDT"
    st.session_state.sound_event = "target" if reason == "TARGET" else "stop" if reason in ("SL", "TSL") else "exit"

def process_strategy():
    # Use the latest fully closed candle to detect a fresh EMA crossover.
    global closed, live
    pos = st.session_state.position
    latest_closed = closed.iloc[-1]
    previous_closed = closed.iloc[-2]
    candle_key = str(latest_closed["open_time"])

    if isinstance(pos, dict):
        # Update trailing stop once per newly completed candle.
        if st.session_state.last_trail_candle != candle_key:
            old_stop = float(pos.get("stop", pos.get("initial_sl", 0)))
            candidate = float(latest_closed["low"])
            new_stop = max(old_stop, candidate)
            pos["stop"] = new_stop
            st.session_state.position = pos
            st.session_state.last_trail_candle = candle_key

        # Check current live candle against stop/target.
        # If both levels trade within the same candle, assume stop first (conservative).
        stop_price = float(pos.get("stop", pos.get("initial_sl", 0)))
        target_price = float(pos.get("target", 0))
        live_low = float(live["low"])
        live_high = float(live["high"])
        if live_low <= stop_price:
            close_position(stop_price, "TSL" if stop_price > float(pos.get("initial_sl", stop_price)) else "SL")
        elif live_high >= target_price:
            close_position(target_price, "TARGET")
        return

    # No open position: only one evaluation per closed candle.
    if st.session_state.bot_running and st.session_state.last_signal_candle != candle_key:
        st.session_state.last_signal_candle = candle_key
        crossed_up = (
            float(previous_closed["ema9"]) <= float(previous_closed["ema21"])
            and float(latest_closed["ema9"]) > float(latest_closed["ema21"])
        )
        # Entry only when the completed crossover candle closes above both EMAs.
        if crossed_up and float(latest_closed["close"]) > float(latest_closed["ema9"]) and float(latest_closed["close"]) > float(latest_closed["ema21"]):
            entry = float(latest_closed["close"])
            initial_sl = float(previous_closed["low"])
            risk = entry - initial_sl
            if risk > 0:
                target = entry + (risk * rr_value)
                cost = entry * float(qty_btc)
                if cost <= st.session_state.cash_usdt:
                    st.session_state.cash_usdt -= cost
                    st.session_state.position = {
                        "side": "BUY",
                        "entry": entry,
                        "stop": initial_sl,
                        "initial_sl": initial_sl,
                        "target": target,
                        "qty": float(qty_btc),
                        "entry_time": str(latest_closed["open_time"]),
                    }
                    st.session_state.last_trail_candle = None
                    st.session_state.trade_log.insert(0, {
                        "Time (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "Side": "BUY",
                        "Reason": "EMA 3/8 CROSSOVER",
                        "Entry": entry,
                        "Exit": None,
                        "Qty BTC": float(qty_btc),
                        "P&L USDT": None,
                    })
                    st.session_state.sound_event = "buy"

# ---- Controls ----
left, middle, right = st.columns(3)
with left:
    if st.button("▶ Start Bot", type="primary", use_container_width=True, disabled=st.session_state.bot_running):
        st.session_state.active_interval = selected_interval
        st.session_state.bot_running = True
        st.session_state.last_signal_candle = str(closed.iloc[-1]["open_time"])
        st.success("Bot started. కొత్త crossover కోసం వేచి ఉంటుంది.")
        st.rerun()
with middle:
    if st.button("■ Stop Bot", use_container_width=True, disabled=not st.session_state.bot_running):
        st.session_state.bot_running = False
        st.rerun()
with right:
    if st.button("↻ Refresh", use_container_width=True):
        st.rerun()

# ---- Strategy processing ----
process_strategy()

# ---- Manual exit ----
position = st.session_state.position
if isinstance(position, dict):
    if st.button("MANUAL EXIT – Close Position", type="primary", use_container_width=True):
        close_position(float(live["close"]), "MANUAL EXIT")
        st.rerun()

# ---- Sound event ----
event = st.session_state.sound_event
if event:
    play_sound(event)
    st.session_state.sound_event = None

# ---- Status and metrics ----
current_price = float(live["close"])
position = st.session_state.position
m1, m2, m3, m4 = st.columns(4)
m1.metric("BTCUSDT Price", f"${current_price:,.2f}")
m2.metric("EMA 9", f"{float(live['ema9']):,.2f}")
m3.metric("EMA 21", f"{float(live['ema21']):,.2f}")
m4.metric("Bot Status", "RUNNING" if st.session_state.bot_running else "STOPPED")

if st.session_state.last_exit_message:
    st.info(st.session_state.last_exit_message)

if isinstance(position, dict):
    entry = float(position.get("entry", current_price))
    stop = position.get("stop")
    target = position.get("target")
    qty = float(position.get("qty", qty_btc))
    unrealized = (current_price - entry) * qty
    a, b, c, d = st.columns(4)
    a.metric("Position", "BUY")
    b.metric("Entry", f"${entry:,.2f}")
    c.metric("SL / TSL", f"${float(stop):,.2f}" if stop is not None else "—")
    d.metric("Target", f"${float(target):,.2f}" if target is not None else "—")
    st.metric("Unrealized P&L", f"{unrealized:+.4f} USDT")
else:
    st.info("Open position లేదు. Bot RUNNING అయితే EMA crossover కోసం వేచి ఉంటుంది.")

# ---- Chart ----
plot_df = df.tail(150).copy()
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=plot_df["open_time"], open=plot_df["open"], high=plot_df["high"],
    low=plot_df["low"], close=plot_df["close"], name="BTCUSDT"
))
fig.add_trace(go.Scatter(x=plot_df["open_time"], y=plot_df["ema9"],
                         mode="lines", name="EMA 3", line=dict(width=1.5)))
fig.add_trace(go.Scatter(x=plot_df["open_time"], y=plot_df["ema21"],
                         mode="lines", name="EMA 8", line=dict(width=1.5)))
position = st.session_state.position
if isinstance(position, dict):
    entry_level = position.get("entry")
    stop_level = position.get("stop")
    target_level = position.get("target")
    if entry_level is not None:
        fig.add_hline(y=float(entry_level), line_dash="dot", annotation_text="ENTRY")
    if stop_level is not None:
        fig.add_hline(y=float(stop_level), line_dash="dash", annotation_text="SL / TSL")
    if target_level is not None:
        fig.add_hline(y=float(target_level), line_dash="dash", annotation_text="TARGET")
fig.update_layout(
    height=650, xaxis_rangeslider_visible=False,
    title=f"{SYMBOL} • {selected_interval} • Binance",
    template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
)
st.plotly_chart(fig, use_container_width=True)

# ---- Account and trade log ----
st.subheader("Paper Account")
x, y = st.columns(2)
x.metric("Available Cash", f"{st.session_state.cash_usdt:,.2f} USDT")
y.metric("Completed Trades", sum(1 for t in st.session_state.trade_log if t.get("Exit") is not None))
if st.session_state.trade_log:
    st.subheader("Trade Log")
    st.dataframe(pd.DataFrame(st.session_state.trade_log), use_container_width=True, hide_index=True)
else:
    st.caption("ఇంకా trades లేవు.")

st.caption("గమనిక: ఈ app Binance public BTCUSDT spot candles మాత్రమే ఉపయోగిస్తుంది. ఇది paper trading; నిజమైన orders కాదు. Stop Bot చేస్తే SL/Target monitoring కూడా pause అవుతుంది.")
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ---- Auto refresh while bot is running ----
if st.session_state.bot_running:
    time.sleep(int(refresh_seconds))
    st.rerun()
