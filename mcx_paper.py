import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="MCX Paper Replay", layout="wide")

st.title("MCX Historical Replay & Paper Trading")
st.caption("Historical testing only | No real orders")

@st.cache_data(ttl=300)
def get_data():
    df = yf.download(
        "MCX.NS",
        period="60d",
        interval="5m",
        auto_adjust=False,
        progress=False
    )

    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    return df

try:
    df = get_data()
except Exception as e:
    st.error(f"Data download error: {e}")
    st.stop()

if df.empty:
    st.error("Historical data not available. Try again later.")
    st.stop()

df = df.copy()
df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()

df["Signal"] = 0
df.loc[
    (df["EMA9"] > df["EMA21"]) &
    (df["EMA9"].shift(1) <= df["EMA21"].shift(1)),
    "Signal"
] = 1

df.loc[
    (df["EMA9"] < df["EMA21"]) &
    (df["EMA9"].shift(1) >= df["EMA21"].shift(1)),
    "Signal"
] = -1

st.sidebar.header("Replay Settings")

replay_index = st.sidebar.slider(
    "Replay candle",
    min_value=20,
    max_value=len(df)-1,
    value=min(100, len(df)-1),
    step=1
)

sl_percent = st.sidebar.number_input(
    "Stop Loss %",
    min_value=0.1,
    max_value=10.0,
    value=1.0,
    step=0.1
)

target_percent = st.sidebar.number_input(
    "Target %",
    min_value=0.1,
    max_value=20.0,
    value=2.0,
    step=0.1
)

capital = st.sidebar.number_input(
    "Paper Capital (₹)",
    min_value=1000,
    value=100000,
    step=1000
)

qty = st.sidebar.number_input(
    "Quantity",
    min_value=1,
    value=1,
    step=1
)

visible = df.iloc[:replay_index+1].copy()

st.subheader("MCX India | 5 Minute Chart")

fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=visible.index,
    open=visible["Open"],
    high=visible["High"],
    low=visible["Low"],
    close=visible["Close"],
    name="MCX",
    increasing_line_color="green",
    decreasing_line_color="red"
))

fig.add_trace(go.Scatter(
    x=visible.index,
    y=visible["EMA9"],
    name="EMA 9",
    line=dict(width=1.5)
))

fig.add_trace(go.Scatter(
    x=visible.index,
    y=visible["EMA21"],
    name="EMA 21",
    line=dict(width=1.5)
))

fig.update_layout(
    height=650,
    xaxis_rangeslider_visible=False,
    hovermode="x",
    dragmode="pan",
    margin=dict(l=10, r=60, t=30, b=10)
)

fig.update_xaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor"
)

fig.update_yaxes(
    showspikes=True,
    spikemode="across",
    spikesnap="cursor"
)

st.plotly_chart(fig, use_container_width=True)

current = visible.iloc[-1]

c1, c2, c3 = st.columns(3)

c1.metric("Current Replay Price", f"₹{current['Close']:.2f}")
c2.metric("EMA 9", f"₹{current['EMA9']:.2f}")
c3.metric("EMA 21", f"₹{current['EMA21']:.2f}")

# Paper simulation
trades = []
position = None
cash = float(capital)

for i in range(1, len(visible)):
    bar = visible.iloc[i]
    prev = visible.iloc[i-1]

    # Exit checks
    if position is not None:
        sl = position["sl"]
        target = position["target"]

        exit_price = None
        exit_reason = None

        # If both SL and target touched, assume SL first.
        if bar["Low"] <= sl:
            exit_price = sl
            exit_reason = "Stop Loss"

        elif bar["High"] >= target:
            exit_price = target
            exit_reason = "Target"

        elif bar["Signal"] == -1:
            exit_price = bar["Close"]
            exit_reason = "EMA Exit"

        if exit_price is not None:
            pnl = (exit_price - position["entry"]) * qty
            cash += pnl

            trades.append({
                "Entry Time": position["time"],
                "Entry": position["entry"],
                "Exit Time": visible.index[i],
                "Exit": exit_price,
                "Qty": qty,
                "P&L": pnl,
                "Reason": exit_reason
            })

            position = None

    # Entry
    if position is None and bar["Signal"] == 1:
        entry = float(bar["Close"])

        position = {
            "entry": entry,
            "time": visible.index[i],
            "sl": entry * (1 - sl_percent/100),
            "target": entry * (1 + target_percent/100)
        }

# Results
st.subheader("Paper Trading Results")

if trades:
    trade_df = pd.DataFrame(trades)

    total_pnl = trade_df["P&L"].sum()
    wins = (trade_df["P&L"] > 0).sum()
    losses = (trade_df["P&L"] <= 0).sum()

    a, b, c, d = st.columns(4)

    a.metric("Total P&L", f"₹{total_pnl:.2f}")
    b.metric("Trades", len(trades))
    c.metric("Winning Trades", wins)
    d.metric("Losing Trades", losses)

    st.dataframe(trade_df, use_container_width=True)

else:
    st.info("No completed paper trades in this replay.")

if position is not None:
    st.warning(
        f"Open virtual position: Entry ₹{position['entry']:.2f} | "
        f"SL ₹{position['sl']:.2f} | Target ₹{position['target']:.2f}"
    )

st.caption(
    "Demo EMA strategy. Historical data may be delayed or incomplete. "
    "Yahoo Finance is not a guaranteed live market feed."
)
