import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# URK EMA PAPER TRADING - Binance BTCUSDT, 1-minute candles
# Strategy:
#   BUY  when 9 EMA crosses above 21 EMA on a CLOSED candle.
#   Entry = crossover candle close.
#   SL    = low of the candle immediately before crossover.
#   EXIT  when a later candle trades at/below the SL.
# Paper trading only. No broker orders are placed.
# ============================================================

st.set_page_config(page_title="URK EMA Paper Trading", page_icon="📈", layout="wide")
IST = ZoneInfo("Asia/Kolkata")
BINANCE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]
PAIR = "BTCUSDT"
INTERVAL = "1m"
STARTING_CASH = 100000.0


@st.cache_data(ttl=1, show_spinner=False)
def fetch_candles():
    last_error = None
    for url in BINANCE_URLS:
        try:
            response = requests.get(
                url,
                params={"symbol": PAIR, "interval": INTERVAL, "limit": 150},
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            rows = response.json()
            columns = [
                "OpenTime", "Open", "High", "Low", "Close", "Volume",
                "CloseTime", "QuoteVolume", "Trades", "TakerBuyBase",
                "TakerBuyQuote", "Ignore",
            ]
            df = pd.DataFrame(rows, columns=columns)
            df["OpenTime"] = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
            df["CloseTime"] = pd.to_datetime(df["CloseTime"], unit="ms", utc=True)
            df.set_index("OpenTime", inplace=True)
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df[["Open", "High", "Low", "Close", "Volume", "CloseTime"]].dropna()
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Binance connection failed: {last_error}")


@st.cache_data(ttl=300, show_spinner=False)
def get_usdinr():
    # Approximate conversion for display only; BTCUSDT itself is quoted in USDT.
    try:
        response = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        value = float(response.json()["rates"]["INR"])
        if value > 0:
            return value
    except Exception:
        pass
    return None


def inr(value, rate):
    if rate is None:
        return f"${value:,.2f} USDT"
    return f"₹{value * rate:,.2f}"


def init_state():
    defaults = {
        "logged_in": False,
        "password": "123",
        "cash": STARTING_CASH,
        "realized_pnl": 0.0,
        "position": None,
        "bot_on": False,
        "last_processed_candle": None,
        "logs": [],
        "trades": [],
        "last_signal": "Waiting for a confirmed 9 EMA / 21 EMA crossover.",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_log(message):
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.logs.insert(0, f"[{stamp}] {message}")
    st.session_state.logs = st.session_state.logs[:100]


def calculate_indicators(df):
    out = df.copy()
    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()
    return out


def process_strategy(df, rate):
    """Process each newly CLOSED candle once; monitor live candle for SL."""
    if len(df) < 25:
        return

    # Binance's last row is normally the currently-forming candle.
    # Use only completed candles for crossover signals.
    closed = df.iloc[:-1]
    if len(closed) < 22:
        return

    previous = closed.iloc[-2]
    signal_candle = closed.iloc[-1]
    candle_id = str(closed.index[-1])

    # First run after pressing START: don't take an old historical crossover.
    if st.session_state.last_processed_candle is None:
        st.session_state.last_processed_candle = candle_id
    elif st.session_state.last_processed_candle != candle_id:
        st.session_state.last_processed_candle = candle_id

        crossed_up = (
            previous["EMA9"] <= previous["EMA21"]
            and signal_candle["EMA9"] > signal_candle["EMA21"]
        )

        if st.session_state.position is None and crossed_up:
            entry_usdt = float(signal_candle["Close"])
            stop_usdt = float(previous["Low"])
            qty = 0.001  # Fixed BTC quantity for initial paper test.
            cost_inr = entry_usdt * qty * rate if rate else 0.0

            if rate is None:
                st.session_state.last_signal = (
                    "BUY setup found, but USD/INR conversion is unavailable. "
                    "Retry after conversion data returns."
                )
                add_log("BUY signal found; INR conversion unavailable, trade not opened.")
            elif stop_usdt >= entry_usdt:
                st.session_state.last_signal = "BUY setup skipped: previous candle low is not below entry."
                add_log("BUY setup skipped because previous candle low was not below entry.")
            elif st.session_state.cash >= cost_inr:
                st.session_state.cash = round(st.session_state.cash - cost_inr, 2)
                st.session_state.position = {
                    "qty": qty,
                    "entry_usdt": entry_usdt,
                    "entry_inr": entry_usdt * rate,
                    "stop_usdt": stop_usdt,
                    "stop_inr": stop_usdt * rate,
                    "entry_time": str(closed.index[-1]),
                    "entry_candle": candle_id,
                }
                st.session_state.last_signal = (
                    f"BUY @ {entry_usdt:,.2f} USDT | SL {stop_usdt:,.2f} USDT"
                )
                add_log(
                    f"🟢 PAPER BUY {qty} BTC @ {entry_usdt:,.2f} USDT "
                    f"({inr(entry_usdt, rate)}) | SL {stop_usdt:,.2f} USDT"
                )
            else:
                st.session_state.last_signal = "BUY signal found, but paper cash is insufficient."
                add_log("BUY signal skipped: insufficient paper cash.")

    # Stop-loss check: only candles after the entry candle can trigger the SL.
    pos = st.session_state.position
    if pos is not None:
        live_candle = df.iloc[-1]
        live_candle_id = str(df.index[-1])
        if live_candle_id != pos["entry_candle"] and float(live_candle["Low"]) <= pos["stop_usdt"]:
            exit_usdt = pos["stop_usdt"]
            exit_inr = exit_usdt * rate if rate else pos["stop_inr"]
            proceeds = exit_inr * pos["qty"]
            pnl = (exit_inr - pos["entry_inr"]) * pos["qty"]
            st.session_state.cash = round(st.session_state.cash + proceeds, 2)
            st.session_state.realized_pnl = round(st.session_state.realized_pnl + pnl, 2)
            st.session_state.trades.insert(0, {
                "Entry time (UTC)": pos["entry_time"],
                "Exit time (IST)": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "Qty BTC": pos["qty"],
                "Entry (₹/BTC)": round(pos["entry_inr"], 2),
                "Exit (₹/BTC)": round(exit_inr, 2),
                "Stop (USDT)": round(pos["stop_usdt"], 2),
                "P&L (₹)": round(pnl, 2),
                "Reason": "Stop Loss",
            })
            add_log(
                f"🔴 STOP LOSS EXIT @ {exit_usdt:,.2f} USDT "
                f"| Realized P&L {pnl:+,.2f} INR"
            )
            st.session_state.position = None
            st.session_state.last_signal = f"STOP LOSS hit. P&L: ₹{pnl:+,.2f}"


init_state()

# ---------------- Login ----------------
if not st.session_state.logged_in:
    st.title("📈 URK EMA Paper Trading")
    st.caption("Binance BTCUSDT · 1-minute · 9 EMA / 21 EMA")
    with st.form("login_form"):
        password = st.text_input("Password", type="password", value="123")
        submitted = st.form_submit_button("Login", type="primary")
    if submitted:
        if password == st.session_state.password:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Wrong password. Default password: 123")
    st.stop()

# ---------------- Header and controls ----------------
head1, head2 = st.columns([4, 1])
head1.title("📈 URK EMA Paper Trading")
head1.caption("BTCUSDT · Binance live data · 1-minute candles · Paper trading only")
if head2.button("Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.bot_on = False
    st.rerun()

rate = get_usdinr()
try:
    df = calculate_indicators(fetch_candles())
    data_error = None
except Exception as exc:
    df = pd.DataFrame()
    data_error = str(exc)

if data_error:
    st.error(f"Live data issue: {data_error}")
    st.info("Check internet access and refresh the app.")
    st.stop()

if rate is None:
    st.warning("USD/INR conversion is unavailable. Live BTCUSDT chart is shown in USDT; new INR paper entries are paused.")

# Process the strategy only while the bot is on.
if st.session_state.bot_on:
    process_strategy(df, rate)

# ---------------- Metrics ----------------
latest_price = float(df.iloc[-1]["Close"])
latest_price_inr = latest_price * rate if rate else None
position = st.session_state.position
unrealized = 0.0
if position and rate:
    unrealized = (latest_price * rate - position["entry_inr"]) * position["qty"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("BTCUSDT Live", f"{latest_price:,.2f}")
m2.metric("BTC Price (INR approx.)", f"₹{latest_price_inr:,.2f}" if latest_price_inr else "Unavailable")
m3.metric("Realized P&L", f"₹{st.session_state.realized_pnl:+,.2f}")
m4.metric("Unrealized P&L", f"₹{unrealized:+,.2f}")

st.divider()
c1, c2, c3 = st.columns([1, 1, 2])
if c1.button("▶ START EMA BOT", type="primary", use_container_width=True, disabled=st.session_state.bot_on):
    st.session_state.bot_on = True
    # Avoid entering on a crossover that happened before START was pressed.
    closed = df.iloc[:-1]
    st.session_state.last_processed_candle = str(closed.index[-1]) if len(closed) else None
    add_log("EMA paper bot started. Waiting for a NEW closed-candle bullish crossover.")
    st.rerun()
if c2.button("⏹ STOP BOT", use_container_width=True, disabled=not st.session_state.bot_on):
    st.session_state.bot_on = False
    add_log("Bot stopped. Any open paper position remains open; SL monitoring is paused.")
    st.rerun()
if c3.button("↻ RESET PAPER ACCOUNT", use_container_width=True):
    st.session_state.bot_on = False
    st.session_state.cash = STARTING_CASH
    st.session_state.realized_pnl = 0.0
    st.session_state.position = None
    st.session_state.last_processed_candle = None
    st.session_state.logs = []
    st.session_state.trades = []
    st.session_state.last_signal = "Waiting for a confirmed 9 EMA / 21 EMA crossover."
    st.rerun()

status = "🟢 BOT RUNNING" if st.session_state.bot_on else "⚪ BOT STOPPED"
st.subheader(status)
st.write(f"**Latest strategy status:** {st.session_state.last_signal}")
st.caption("Signal rule: closed candle EMA9 crosses above EMA21. Entry = crossover candle close. SL = previous candle low.")

# ---------------- Chart ----------------
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
    name="BTCUSDT",
))
fig.add_trace(go.Scatter(x=df.index, y=df["EMA9"], mode="lines", name="EMA 9", line=dict(width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["EMA21"], mode="lines", name="EMA 21", line=dict(width=2)))
if position:
    fig.add_hline(y=position["entry_usdt"], line_dash="dot", annotation_text="Entry")
    fig.add_hline(y=position["stop_usdt"], line_dash="dash", annotation_text="Stop Loss")
fig.update_layout(
    title="Binance BTCUSDT · 1 Minute · Live",
    height=560,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    margin=dict(l=10, r=10, t=50, b=10),
    legend=dict(orientation="h", y=1.02, x=0),
    uirevision="BTCUSDT-1m",
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Source: Binance public market-data API. Chart refreshes every 2 seconds; EMA signals use completed candles only.")

# ---------------- Position ----------------
st.subheader("📌 Current Position")
if position:
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Position", "LONG BTC")
    p2.metric("Quantity", f'{position["qty"]:.6f} BTC')
    p3.metric("Entry", f'{position["entry_usdt"]:,.2f} USDT')
    p4.metric("Stop Loss", f'{position["stop_usdt"]:,.2f} USDT')
    st.info("Position is open. Stop-loss monitoring runs only while the bot is running.")
else:
    st.info("No open paper position.")

# ---------------- Account and history ----------------
a1, a2 = st.columns(2)
a1.metric("Available Paper Cash", f'₹{st.session_state.cash:,.2f}')
a2.metric("Net P&L", f'₹{st.session_state.realized_pnl + unrealized:+,.2f}')

if st.session_state.trades:
    st.subheader("📋 Completed Paper Trades")
    st.dataframe(pd.DataFrame(st.session_state.trades), use_container_width=True, hide_index=True)

if st.session_state.logs:
    st.subheader("📜 Execution Logs")
    for item in st.session_state.logs[:20]:
        st.text(item)

# Refresh the dashboard without blocking the Streamlit script with time.sleep().
if st.session_state.bot_on:
    time.sleep(2)
    st.rerun()
