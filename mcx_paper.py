import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="NSE Stock Market Dashboard", layout="wide")

st.title("📈 NSE STOCK MARKET DASHBOARD")
st.caption(
    "Data source: Yahoo Finance (unofficial). Data may be delayed or unavailable. "
    "This is not an official NSE live feed."
)

# Refresh the dashboard every 60 seconds.
st_autorefresh(interval=60_000, key="nse_refresh")

stocks = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "SBIN": "SBIN.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "ITC": "ITC.NS",
    "TATA STEEL": "TATASTEEL.NS",
    "NIFTY 50": "^NSEI",
}

left, right = st.columns(2)
with left:
    stock_name = st.selectbox("Select NSE stock", list(stocks.keys()))
with right:
    interval = st.selectbox("Chart timeframe", ["1m", "5m", "15m"])

symbol = stocks[stock_name]
period = "5d" if interval == "1m" else "1mo"


@st.cache_data(ttl=50, show_spinner=False)
def get_data(ticker: str, candle_interval: str, lookback: str):
    return yf.download(
        ticker,
        period=lookback,
        interval=candle_interval,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
    )


if st.button("🔄 Refresh data now"):
    get_data.clear()

try:
    with st.spinner("Loading market data..."):
        df = get_data(symbol, interval, period)

    if df is None or df.empty:
        st.warning(
            "No data was returned. The market may be closed, the symbol may be "
            "temporarily unavailable, or Yahoo Finance may be limiting requests."
        )
        st.stop()

    # Handle MultiIndex columns returned by some yfinance versions.
    if isinstance(df.columns, __import__("pandas").MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        st.error(f"Data is missing required columns: {', '.join(missing)}")
        st.stop()

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        st.warning("No valid candle data is available.")
        st.stop()

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    last_price = float(latest["Close"])
    price_change = last_price - float(previous["Close"])
    volume = int(latest["Volume"]) if not __import__("pandas").isna(latest["Volume"]) else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Last price", f"₹{last_price:,.2f}", f"{price_change:+,.2f}")
    m2.metric("Latest candle volume", f"{volume:,}")
    m3.metric("Timeframe", interval)

    st.subheader(f"{stock_name} — candlestick chart")

    candle_fig = go.Figure(
        data=[
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=stock_name,
            )
        ]
    )
    candle_fig.update_layout(
        height=600,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=35, b=10),
        yaxis_title="Price (INR)",
        xaxis_title="Time",
    )
    st.plotly_chart(
        candle_fig,
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": True},
    )

    st.subheader("Volume")
    volume_fig = go.Figure(
        data=[go.Bar(x=df.index, y=df["Volume"], name="Volume")]
    )
    volume_fig.update_layout(
        height=220,
        template="plotly_dark",
        xaxis_title="Time",
        yaxis_title="Volume",
        margin=dict(l=10, r=10, t=25, b=10),
    )
    st.plotly_chart(volume_fig, use_container_width=True)

    st.caption(
        "Yahoo Finance is an unofficial data source. Refreshing this page does not "
        "guarantee real-time updates. OI and Change in OI are not included. "
        "Do not use this dashboard as the sole basis for trading decisions."
    )

except Exception as error:
    st.error(f"Could not load market data: {error}")
    st.info(
        "Check your internet connection and package installation. "
        "Yahoo Finance may also temporarily restrict requests."
    )
