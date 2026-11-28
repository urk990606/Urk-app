import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="Crude Oil Proxy Backtest", layout="wide")

st.title("Crude Oil Intraday Backtesting")
st.error(
    "MCX PROXY ONLY — This app uses NYMEX WTI Crude Oil Futures (Yahoo ticker CL=F). "
    "It is NOT MCX Crude Oil data. Prices, trading hours, contract size, expiry and "
    "tick value differ. Use only for strategy research, not live MCX decisions."
)

@st.cache_data(ttl=60)
def load_data(interval, period):
    df = yf.download(
        "CL=F",
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False
    )
    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance may return MultiIndex columns for a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()

    df = df[required].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata")
    df.index.name = "Datetime"
    return df

with st.sidebar:
    st.header("Data Settings")
    interval = st.selectbox("Timeframe", ["1m", "5m", "15m"], index=1)
    if interval == "1m":
        period = st.selectbox("History range", ["5d", "7d"], index=0)
        st.caption("1-minute history is very limited; Yahoo may return fewer days.")
    else:
        period = st.selectbox("History range", ["5d", "1mo", "3mo", "5d"], index=1)
        st.caption("Yahoo intraday history is limited; availability can vary.")
    if st.button("Refresh data"):
        st.cache_data.clear()

    st.divider()
    st.header("Backtest Settings")
    fast_ema = st.number_input("Fast EMA", min_value=2, max_value=50, value=9)
    slow_ema = st.number_input("Slow EMA", min_value=3, max_value=100, value=21)
    stop_pct = st.number_input("Stop loss (%)", min_value=0.1, max_value=10.0, value=0.5, step=0.1)
    target_pct = st.number_input("Target (%)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)
    replay_index = None

data = load_data(interval, period)

if data.empty:
    st.warning(
        "Yahoo Finance did not return intraday candles for this request. "
        "Try another timeframe/history range or refresh later. This is a free-data "
        "availability limitation, not MCX data."
    )
    st.stop()

if fast_ema >= slow_ema:
    st.warning("Fast EMA should be smaller than Slow EMA.")

data["EMA_Fast"] = data["Close"].ewm(span=int(fast_ema), adjust=False).mean()
data["EMA_Slow"] = data["Close"].ewm(span=int(slow_ema), adjust=False).mean()
data["Signal"] = 0
data.loc[data["EMA_Fast"] > data["EMA_Slow"], "Signal"] = 1
data.loc[data["EMA_Fast"] < data["EMA_Slow"], "Signal"] = -1
data["Cross"] = data["Signal"].diff()

st.caption(
    f"Instrument: CL=F (NYMEX WTI proxy) | Timeframe: {interval} | "
    f"Rows loaded: {len(data)} | Latest bar: {data.index[-1]}"
)

max_rows = len(data)
default_rows = min(max_rows, 300)
visible_rows = st.slider(
    "Candles to display",
    min_value=min(50, max_rows),
    max_value=max_rows,
    value=max(min(50, max_rows), default_rows),
    step=1
)
chart_data = data.tail(visible_rows).copy()

fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=chart_data.index,
    open=chart_data["Open"],
    high=chart_data["High"],
    low=chart_data["Low"],
    close=chart_data["Close"],
    name="WTI proxy candles"
))
fig.add_trace(go.Scatter(
    x=chart_data.index, y=chart_data["EMA_Fast"],
    mode="lines", name=f"EMA {fast_ema}"
))
fig.add_trace(go.Scatter(
    x=chart_data.index, y=chart_data["EMA_Slow"],
    mode="lines", name=f"EMA {slow_ema}"
))
fig.update_layout(
    height=650,
    hovermode="x unified",
    xaxis_title="Time (Asia/Kolkata display)",
    yaxis_title="WTI price (USD per barrel)",
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    legend=dict(orientation="h"),
    hoverlabel=dict(namelength=-1)
)
# Broker-style crosshair: vertical and horizontal cursor guide lines
fig.update_xaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    showline=True,
    spikethickness=1
)
fig.update_yaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor",
    showline=True,
    spikethickness=1
)
st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "scrollZoom": True,
        "displayModeBar": True,
        "displaylogo": False,
        "modeBarButtonsToAdd": ["drawline", "drawrect", "eraseshape"]
    }
)

st.subheader("Historical Candle Replay")
if len(data) > 1:
    replay_index = st.slider(
        "Move through historical candles",
        min_value=1,
        max_value=len(data),
        value=len(data),
        step=1
    )
    replay = data.iloc[:replay_index]
    last = replay.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Replay close", f"{last['Close']:.2f} USD")
    c2.metric("Fast EMA", f"{last['EMA_Fast']:.2f}")
    c3.metric("Slow EMA", f"{last['EMA_Slow']:.2f}")
    st.caption(f"Replay candle: {replay.index[-1]}")
else:
    st.info("Not enough candles for replay.")

st.subheader("Simple EMA Backtest (research only)")
st.caption(
    "Illustrative long-only crossover test. It assumes entry at the next candle open "
    "and exits on stop/target or opposite EMA signal. It excludes brokerage, slippage, "
    "taxes, currency conversion and MCX contract specifications."
)

trades = []
position = None
for i in range(1, len(data) - 1):
    row = data.iloc[i]
    next_open = float(data.iloc[i + 1]["Open"])

    if position is None:
        if row["Cross"] == 2:
            entry = next_open
            position = {
                "entry_time": data.index[i + 1],
                "entry": entry,
                "stop": entry * (1 - stop_pct / 100),
                "target": entry * (1 + target_pct / 100)
            }
    else:
        exit_price = None
        reason = None
        if float(row["Low"]) <= position["stop"]:
            exit_price, reason = position["stop"], "Stop Loss"
        elif float(row["High"]) >= position["target"]:
            exit_price, reason = position["target"], "Target"
        elif row["Cross"] == -2:
            exit_price, reason = next_open, "Opposite EMA"

        if exit_price is not None:
            pnl_pct = (exit_price - position["entry"]) / position["entry"] * 100
            trades.append({
                "Entry time": position["entry_time"],
                "Entry": position["entry"],
                "Exit time": data.index[i],
                "Exit": exit_price,
                "Reason": reason,
                "P&L %": pnl_pct
            })
            position = None

if trades:
    trade_df = pd.DataFrame(trades)
    wins = int((trade_df["P&L %"] > 0).sum())
    total = len(trade_df)
    a, b, c = st.columns(3)
    a.metric("Closed trades", total)
    b.metric("Win rate", f"{wins / total * 100:.1f}%")
    c.metric("Sum of trade returns", f"{trade_df['P&L %'].sum():.2f}%")
    st.dataframe(trade_df, use_container_width=True)
    csv = trade_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download trade log CSV", csv, "crude_oil_proxy_trades.csv", "text/csv")
else:
    st.info("No completed trades in the selected data range. Try another timeframe or EMA settings.")

st.subheader("Latest candles")
st.dataframe(data.tail(20).sort_index(ascending=False), use_container_width=True)

st.warning(
    "Reminder: This is WTI proxy data, not MCX. Do not treat this chart or backtest "
    "as actual MCX Crude Oil Futures or Options prices."
)
