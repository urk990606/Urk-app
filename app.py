import io
import math
import struct
import time
import wave
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# URK EMA PAPER TRADING
# Binance BTCUSDT | 1m / 3m / 5m / 15m
# BUY: EMA9 crosses above EMA21 on a fully closed candle.
# Entry: crossover candle close. Initial SL: previous candle low.
# Target: configurable risk/reward (default 1:2).
# TSL: previous completed candle low; it can only move upward.
# Exit: Stop Loss / TSL / Target / Manual Exit. Paper trading only.

st.set_page_config(page_title="URK EMA Paper Trading", page_icon="📈", layout="wide")
IST = ZoneInfo("Asia/Kolkata")
PAIR = "BTCUSDT"
INTERVALS = ["1m", "3m", "5m", "15m"]
STARTING_CASH = 100000.0
BINANCE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]


@st.cache_data(ttl=1, show_spinner=False)
def fetch_candles(interval):
    last_error = None
    for url in BINANCE_URLS:
        try:
            response = requests.get(
                url,
                params={"symbol": PAIR, "interval": interval, "limit": 200},
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            rows = response.json()
            cols = [
                "OpenTime", "Open", "High", "Low", "Close", "Volume",
                "CloseTime", "QuoteVolume", "Trades", "TakerBuyBase",
                "TakerBuyQuote", "Ignore",
            ]
            df = pd.DataFrame(rows, columns=cols)
            df["OpenTime"] = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
            df["CloseTime"] = pd.to_datetime(df["CloseTime"], unit="ms", utc=True)
            df.set_index("OpenTime", inplace=True)
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df[["Open", "High", "Low", "Close", "Volume", "CloseTime"]].dropna()
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Binance data connection failed: {last_error}")


@st.cache_data(ttl=300, show_spinner=False)
def get_usdinr():
    try:
        r = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        rate = float(r.json()["rates"]["INR"])
        return rate if rate > 0 else None
    except Exception:
        return None


@st.cache_data
def make_wav(freq=950, duration=0.30):
    sample_rate = 22050
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(int(sample_rate * duration)):
            sample = int(23000 * math.sin(2 * math.pi * freq * i / sample_rate))
            frames.extend(struct.pack("<h", sample))
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def play_beep(kind):
    # Each event uses a distinct tone pattern.
    if kind == "buy":
        st.audio(make_wav(1050, 0.35), format="audio/wav", autoplay=True)
    elif kind == "manual":
        st.audio(make_wav(650, 0.22), format="audio/wav", autoplay=True)
    elif kind == "target":
        st.audio(make_wav(1250, 0.22), format="audio/wav", autoplay=True)
    elif kind == "stop":
        st.audio(make_wav(430, 0.55), format="audio/wav", autoplay=True)


def add_log(message):
    stamp = datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")
    st.session_state.logs.insert(0, f"[{stamp}] {message}")
    st.session_state.logs = st.session_state.logs[:100]


def init_state():
    defaults = {
        "logged_in": False,
        "cash": STARTING_CASH,
        "realized_pnl": 0.0,
        "position": None,
        "bot_on": False,
        "active_interval": None,
        "last_processed_closed": None,
        "logs": [],
        "trades": [],
        "last_signal": "Waiting for a new confirmed bullish EMA crossover.",
        "sound_event": None,
        "qty_btc": 0.001,
        "rr": 2.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def calculate_indicators(raw):
    df = raw.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    return df


def close_position(exit_usdt, rate, reason, sound):
    pos = st.session_state.position
    if pos is None:
        return
    exit_rate = rate if rate else pos["entry_rate"]
    exit_inr = exit_usdt * exit_rate
    proceeds = exit_inr * pos["qty"]
    pnl = (exit_inr - pos["entry_inr"]) * pos["qty"]

    st.session_state.cash = round(st.session_state.cash + proceeds, 2)
    st.session_state.realized_pnl = round(st.session_state.realized_pnl + pnl, 2)
    st.session_state.trades.insert(0, {
        "Entry time (IST)": pos["entry_time"],
        "Exit time (IST)": datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S"),
        "Timeframe": pos["timeframe"],
        "Qty BTC": pos["qty"],
        "Entry (USDT)": round(pos["entry_usdt"], 2),
        "Exit (USDT)": round(exit_usdt, 2),
        "Initial SL (USDT)": round(pos["initial_sl"], 2),
        "Final SL / TSL (USDT)": round(pos["stop"], 2),
        "Target (USDT)": round(pos["target"], 2),
        "P&L (₹)": round(pnl, 2),
        "Exit reason": reason,
    })
    add_log(f"🔴 {reason} EXIT @ {exit_usdt:,.2f} USDT | P&L ₹{pnl:+,.2f}")
    st.session_state.position = None
    st.session_state.sound_event = sound
    st.session_state.last_signal = f"{reason} exit completed | P&L ₹{pnl:+,.2f}"


def process_strategy(df, rate, interval):
    if len(df) < 30:
        return

    # Binance's final row is the still-forming candle. Signal checks use closed bars.
    closed = df.iloc[:-1]
    live = df.iloc[-1]
    if len(closed) < 22:
        return

    closed_bar = closed.iloc[-1]
    closed_id = str(closed.index[-1])
    pos = st.session_state.position

    # Update trailing SL once per newly closed candle.
    if pos is not None and pos["timeframe"] == interval:
        if closed_id != pos["last_trail_candle"]:
            candidate_sl = float(closed_bar["Low"])
            if candidate_sl > pos["stop"]:
                pos["stop"] = candidate_sl
                add_log(f"🟡 TSL moved up to {candidate_sl:,.2f} USDT")
            pos["last_trail_candle"] = closed_id

        # Monitor current live candle, but never exit on the entry candle.
        live_id = str(df.index[-1])
        if live_id != pos["entry_candle"]:
            stop_hit = float(live["Low"]) <= pos["stop"]
            target_hit = float(live["High"]) >= pos["target"]
            # Conservative assumption if both levels fall within one OHLC candle.
            if stop_hit:
                close_position(pos["stop"], rate, "STOP LOSS / TSL", "stop")
                return
            if target_hit:
                close_position(pos["target"], rate, "TARGET", "target")
                return

    # Handle each newly closed candle once.
    if st.session_state.last_processed_closed != closed_id:
        prior = closed.iloc[-2]
        st.session_state.last_processed_closed = closed_id

        crossed_up = (
            float(prior["EMA9"]) <= float(prior["EMA21"])
            and float(closed_bar["EMA9"]) > float(closed_bar["EMA21"])
        )

        if crossed_up and st.session_state.position is None:
            entry = float(closed_bar["Close"])
            initial_sl = float(prior["Low"])
            risk = entry - initial_sl
            qty = float(st.session_state.qty_btc)

            if risk <= 0:
                st.session_state.last_signal = "BUY skipped: previous candle low is not below entry."
                add_log("BUY skipped: invalid stop-loss distance.")
            elif rate is None:
                st.session_state.last_signal = "BUY signal found, but USD/INR conversion is unavailable."
                add_log("BUY setup paused: INR conversion unavailable.")
            else:
                entry_inr = entry * rate
                required_cash = entry_inr * qty
                if st.session_state.cash >= required_cash:
                    target = entry + risk * float(st.session_state.rr)
                    st.session_state.cash = round(st.session_state.cash - required_cash, 2)
                    st.session_state.position = {
                        "qty": qty,
                        "entry_usdt": entry,
                        "entry_inr": entry_inr,
                        "entry_rate": rate,
                        "initial_sl": initial_sl,
                        "stop": initial_sl,
                        "target": target,
                        "entry_time": datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S"),
                        "entry_candle": closed_id,
                        "last_trail_candle": closed_id,
                        "timeframe": interval,
                    }
                    st.session_state.last_signal = (
                        f"BUY @ {entry:,.2f} USDT | SL {initial_sl:,.2f} | "
                        f"Target {target:,.2f}"
                    )
                    add_log(
                        f"🟢 PAPER BUY {qty:g} BTC @ {entry:,.2f} USDT | "
                        f"SL {initial_sl:,.2f} | Target {target:,.2f} | {interval}"
                    )
                    st.session_state.sound_event = "buy"
                else:
                    st.session_state.last_signal = "BUY signal found, but paper cash is insufficient."
                    add_log("BUY skipped: insufficient paper cash.")


init_state()

# Login
if not st.session_state.logged_in:
    st.title("📈 URK EMA Paper Trading")
    st.caption("Binance BTCUSDT | EMA 9 / EMA 21 | Paper trading only")
    with st.form("login_form"):
        password = st.text_input("Password", type="password", value="123")
        submitted = st.form_submit_button("Login", type="primary")
    if submitted:
        if password == "123":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Wrong password. Default password: 123")
    st.stop()

# Header
head1, head2 = st.columns([4, 1])
head1.title("📈 URK EMA Paper Trading")
head1.caption("Binance public market data · BTCUSDT · Paper trades only")
if head2.button("Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.bot_on = False
    st.rerun()

# Settings
s1, s2, s3 = st.columns(3)
selected_interval = s1.selectbox("Timeframe", INTERVALS, index=0)
qty = s2.number_input(
    "Quantity (BTC)", min_value=0.0001, max_value=1.0,
    value=float(st.session_state.qty_btc), step=0.0001, format="%.4f"
)
rr = s3.selectbox(
    "Target Risk : Reward", [1.0, 1.5, 2.0, 3.0], index=2,
    format_func=lambda value: f"1 : {value:g}"
)
st.session_state.qty_btc = qty
st.session_state.rr = rr

if st.session_state.bot_on and selected_interval != st.session_state.active_interval:
    st.warning(
        f"Bot is running on {st.session_state.active_interval}. "
        "Stop the bot before selecting another timeframe."
    )
    interval = st.session_state.active_interval
else:
    interval = selected_interval

try:
    raw = fetch_candles(interval)
    df = calculate_indicators(raw)
    usdinr = get_usdinr()
except Exception as exc:
    st.error(f"Live data connection issue: {exc}")
    st.info("Check the Streamlit app internet connection and refresh.")
    st.stop()

if usdinr is None:
    st.warning("USD/INR conversion unavailable. Chart is shown in USDT; new INR paper entries are paused.")

if st.session_state.bot_on:
    process_strategy(df, usdinr, interval)

# Play event sound once after action state is recorded.
if st.session_state.sound_event:
    event = st.session_state.sound_event
    st.session_state.sound_event = None
    play_beep(event)

# Metrics
live_price = float(df.iloc[-1]["Close"])
live_inr = live_price * usdinr if usdinr else None
position = st.session_state.position
unrealized = 0.0
if position and usdinr:
    unrealized = (live_price * usdinr - position["entry_inr"]) * position["qty"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("BTCUSDT Live", f"{live_price:,.2f}")
m2.metric("BTC Price (approx INR)", f"₹{live_inr:,.2f}" if live_inr else "Unavailable")
m3.metric("Realized P&L", f"₹{st.session_state.realized_pnl:+,.2f}")
m4.metric("Unrealized P&L", f"₹{unrealized:+,.2f}")

st.divider()

# Bot controls
b1, b2, b3 = st.columns(3)
if b1.button(
    "▶ START EMA BOT", type="primary", use_container_width=True,
    disabled=st.session_state.bot_on
):
    if st.session_state.position is not None and st.session_state.position["timeframe"] != interval:
        st.error("Close the open position manually before starting another timeframe.")
    else:
        st.session_state.bot_on = True
        st.session_state.active_interval = interval
        completed = df.iloc[:-1]
        st.session_state.last_processed_closed = str(completed.index[-1]) if len(completed) else None
        add_log(f"EMA bot started on {interval}; waiting for a NEW closed-candle bullish crossover.")
        st.rerun()

if b2.button(
    "⏹ STOP BOT", use_container_width=True,
    disabled=not st.session_state.bot_on
):
    st.session_state.bot_on = False
    add_log("Bot stopped. Automatic SL/Target/TSL monitoring paused; open position remains.")
    st.rerun()

if b3.button("↻ RESET PAPER ACCOUNT", use_container_width=True):
    st.session_state.bot_on = False
    st.session_state.active_interval = None
    st.session_state.cash = STARTING_CASH
    st.session_state.realized_pnl = 0.0
    st.session_state.position = None
    st.session_state.last_processed_closed = None
    st.session_state.logs = []
    st.session_state.trades = []
    st.session_state.last_signal = "Waiting for a new confirmed bullish EMA crossover."
    st.session_state.sound_event = None
    st.rerun()

st.subheader("🧠 Strategy Status")
st.write("**Bot:** " + ("🟢 RUNNING" if st.session_state.bot_on else "⚪ STOPPED"))
st.write("**Latest signal:** " + st.session_state.last_signal)
st.caption(
    "BUY only when EMA9 was at/below EMA21 on the prior closed candle "
    "and closes above EMA21 on the crossover candle. Entry = crossover close; "
    "initial SL = previous candle low; target = selected R:R; TSL = previous "
    "completed candle low and can only move upward."
)

# Chart
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
    name="BTCUSDT"
))
fig.add_trace(go.Scatter(
    x=df.index, y=df["EMA9"], mode="lines", name="EMA 9", line=dict(width=2)
))
fig.add_trace(go.Scatter(
    x=df.index, y=df["EMA21"], mode="lines", name="EMA 21", line=dict(width=2)
))
if position:
    fig.add_hline(y=position["entry_usdt"], line_dash="dot", annotation_text="Entry")
    fig.add_hline(y=position["stop"], line_dash="dash", annotation_text="SL / TSL")
    fig.add_hline(y=position["target"], line_dash="dash", annotation_text="Target")
fig.update_layout(
    title=f"Binance {PAIR} | {interval} | LIVE",
    height=560,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    margin=dict(l=10, r=10, t=50, b=10),
    legend=dict(orientation="h", y=1.02, x=0),
    uirevision=f"{PAIR}-{interval}",
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Source: Binance public API. Dashboard refreshes every 2 seconds while the bot runs. Signals use closed candles.")

# Position and manual exit
st.subheader("📌 Current Position")
position = st.session_state.position
if position:
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Position", "LONG BTC")
    p2.metric("Quantity", f'{position["qty"]:.4f} BTC')
    p3.metric("Entry", f'{position["entry_usdt"]:,.2f} USDT')
    p4.metric("Current SL / TSL", f'{position["stop"]:,.2f} USDT')
    q1, q2, q3 = st.columns(3)
    q1.metric("Target", f'{position["target"]:,.2f} USDT')
    q2.metric("Live P&L (approx)", f"₹{unrealized:+,.2f}")
    q3.metric("Position timeframe", position["timeframe"])

    if st.button(
        "✋ MANUAL EXIT — CLOSE POSITION NOW",
        type="primary",
        use_container_width=True
    ):
        close_position(live_price, usdinr, "MANUAL", "manual")
        event = st.session_state.sound_event
        st.session_state.sound_event = None
        if event:
            play_beep(event)
        st.rerun()
    if not st.session_state.bot_on:
        st.warning("Bot is stopped. Automatic SL/Target/TSL checks are paused; Manual Exit is still available.")
else:
    st.info("No open paper position.")

a1, a2 = st.columns(2)
a1.metric("Available Paper Cash", f'₹{st.session_state.cash:,.2f}')
a2.metric("Net P&L", f"₹{st.session_state.realized_pnl + unrealized:+,.2f}")

if st.session_state.trades:
    st.subheader("📋 Completed Paper Trades")
    st.dataframe(pd.DataFrame(st.session_state.trades), use_container_width=True, hide_index=True)

if st.session_state.logs:
    st.subheader("📜 Execution Logs")
    for line in st.session_state.logs[:25]:
        st.text(line)

# Refresh while bot is running.
if st.session_state.bot_on:
    time.sleep(2)
    st.rerun()
