import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="NSE Stock Market Dashboard", layout="wide")

st.title("📈 NSE STOCK MARKET DASHBOARD")
st.caption(
    "Data source: Yahoo Finance (unofficial). Data may be delayed or unavailable. "
    "This is not an official NSE live feed."
)

# Refresh the page periodically. Yahoo may still return delayed or incomplete data.
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
    interval = st.selectbox("Chart timeframe", ["1m", "5m", "15m"], index=1)

symbol = stocks[stock_name]
period = "5d" if interval == "1m" else "1mo"


@st.cache_data(ttl=45, show_spinner=False)
def get_data(ticker, candle_interval, lookback):
    return yf.download(
        ticker,
        period=lookback,
        interval=candle_interval,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
        threads=False,
    )


if st.button("🔄 Refresh data now"):
    get_data.clear()
    st.rerun()

try:
    with st.spinner("Loading market data..."):
        df = get_data(symbol, interval, period)

    if df is None or df.empty:
        st.warning(
            "No data returned. The market may be closed, Yahoo Finance may be "
            "temporarily limiting requests, or the selected symbol may be unavailable."
        )
        st.stop()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        st.error(f"Missing data columns: {', '.join(missing)}")
        st.stop()

    df = df[required].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    df = df[~df.index.duplicated(keep="last")]

    if df.empty:
        st.warning("No valid candle data is available.")
        st.stop()

    # Use a categorical x-axis: each candle gets equal horizontal spacing.
    # This removes large visual holes caused by irregular/missing Yahoo timestamps.
    # No candles are invented; the real timestamp is shown in the hover tooltip.
    df["ChartTime"] = df.index.strftime("%d %b %H:%M")
    x_values = df["ChartTime"].tolist()

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else latest
    last_price = float(latest["Close"])
    change = last_price - float(previous["Close"])
    volume = int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Last price", f"₹{last_price:,.2f}", f"{change:+,.2f}")
    m2.metric("Latest candle volume", f"{volume:,}")
    m3.metric("Timeframe", interval)

    st.subheader(f"{stock_name} — candlestick chart")

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=x_values,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=stock_name,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            whiskerwidth=0.45,
            hovertext=[
                f"Time: {ts.strftime('%d-%b-%Y %H:%M')}<br>"
                f"Open: ₹{row['Open']:.2f}<br>"
                f"High: ₹{row['High']:.2f}<br>"
                f"Low: ₹{row['Low']:.2f}<br>"
                f"Close: ₹{row['Close']:.2f}<br>"
                f"Volume: {int(row['Volume']) if pd.notna(row['Volume']) else 0:,}"
                for ts, (_, row) in zip(df.index, df.iterrows())
            ],
            hoverinfo="text",
        )
    )

    fig.update_layout(
        height=620,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        hovermode="closest",
        margin=dict(l=10, r=25, t=35, b=10),
        yaxis_title="Price (INR)",
        xaxis_title="Time (Yahoo Finance timestamps)",
        showlegend=False,
        dragmode="pan",
    )
    fig.update_xaxes(
        type="category",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        showline=True,
        tickangle=-35,
        nticks=10,
        rangeslider_visible=False,
    )
    fig.update_yaxes(
        side="right",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        showline=True,
        fixedrange=False,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToAdd": ["drawline", "drawrect", "eraseshape"],
        },
    )

    st.subheader("Volume")
    volume_colors = [
        "#26a69a" if close >= open_ else "#ef5350"
        for open_, close in zip(df["Open"], df["Close"])
    ]
    volume_fig = go.Figure(
        data=[
            go.Bar(
                x=x_values,
                y=df["Volume"].fillna(0),
                marker_color=volume_colors,
                name="Volume",
                hovertemplate="Time: %{x}<br>Volume: %{y:,.0f}<extra></extra>",
            )
        ]
    )
    volume_fig.update_layout(
        height=220,
        template="plotly_dark",
        xaxis_title="Time",
        yaxis_title="Volume",
        margin=dict(l=10, r=25, t=25, b=10),
        showlegend=False,
    )
    volume_fig.update_xaxes(type="category", tickangle=-35, nticks=10)
    volume_fig.update_yaxes(side="right")
    st.plotly_chart(volume_fig, use_container_width=True)

    st.caption(
        "Chart spacing is compressed so available candles appear evenly spaced. "
        "Only candles returned by Yahoo Finance are plotted; missing source candles "
        "are not fabricated. Yahoo Finance is unofficial and may be delayed. "
        "When NSE is closed, the latest candle will remain unchanged. "
        "OI and Change in OI are not provided by this dashboard."
    )

except Exception as error:
    st.error(f"Could not load market data: {error}")
    st.info(
        "Check the internet connection and package installation. "
        "Yahoo Finance may temporarily restrict requests."
    )
