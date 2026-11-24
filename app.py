import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="wide")

# ==========================================
# 1. LOGIN / LOGOUT సిస్టమ్
# ==========================================
# ఇక్కడ మీకు కావాల్సిన Username : Password మార్చుకోవచ్చు
VALID_USERS = {
    "urk": "1234",
    "friend": "5678"
}

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>📈 URK Paper Trading</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>కొనసాగించడానికి దయచేసి లాగిన్ అవ్వండి</p>", unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        with st.form("login_form"):
            user_input = st.text_input("Username (యూజర్ పేరు)")
            pass_input = st.text_input("Password (పాస్‌వర్డ్)", type="password")
            submit_btn = st.form_submit_button("🔐 Login (లాగిన్)", use_container_width=True)
            
            if submit_btn:
                if user_input in VALID_USERS and VALID_USERS[user_input] == pass_input:
                    st.session_state.logged_in = True
                    st.session_state.username = user_input
                    st.rerun()
                else:
                    st.error("❌ తప్పు Username లేదా Password! మళ్ళీ ప్రయత్నించండి.")
    st.stop() # లాగిన్ అవ్వకపోతే కింద ఉన్న యాప్ కోడ్ రన్ అవ్వదు

# ==========================================
# 2. మెయిన్ ట్రేడింగ్ యాప్ (లాగిన్ అయ్యాక)
# ==========================================
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

# హెడర్ & Logout బటన్
h_col1, h_col2 = st.columns([4, 1])
with h_col1:
    st.title("📈 URK")
    st.caption(f"Welcome, **{st.session_state.username.upper()}** | Virtual Paper Trading App")
with h_col2:
    st.write("")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

timeframes = {
    "1m": ("1d", "1m"),
    "3m": ("1d", "3m"),
    "5m": ("2d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("1mo", "1h"),
    "1D": ("6mo", "1d")
}

@st.cache_data(ttl=60)
def get_index_price(symbol):
    try:
        idx = yf.Ticker(symbol)
        hist_2d = idx.history(period="2d")
        if len(hist_2d) >= 2:
            prev_close = hist_2d['Close'].iloc[-2]
            curr_price = hist_2d['Close'].iloc[-1]
            change = curr_price - prev_close
            pct = (change / prev_close) * 100
            return round(curr_price, 2), round(change, 2), round(pct, 2)
        elif len(hist_2d) == 1:
            return round(hist_2d['Close'].iloc[-1], 2), 0.0, 0.0
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=60)
def get_candle_data(symbol, period, interval):
    try:
        ticker_obj = yf.Ticker(symbol)
        if interval == "3m":
            df = ticker_obj.history(period="1d", interval="1m")
            if not df.empty:
                return df.resample('3min').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last'
                }).dropna()
            return pd.DataFrame()
        else:
            df = ticker_obj.history(period=period, interval=interval)
            return df[['Open', 'High', 'Low', 'Close']].dropna() if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def calculate_ut_bot(df, key_value=1.0, atr_period=10):
    df = df.copy()
    high, low, close = df['High'], df['Low'], df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/atr_period, adjust=False).mean()
    n_loss = key_value * atr
    
    close_vals = close.values
    n_loss_vals = n_loss.values
    x_atr_trailing_stop = np.zeros(len(df))
    x_atr_trailing_stop[0] = close_vals[0]
    
    for i in range(1, len(df)):
        prev_stop = x_atr_trailing_stop[i-1]
        c, pc, nl = close_vals[i], close_vals[i-1], n_loss_vals[i]
        if c > prev_stop and pc > prev_stop:
            x_atr_trailing_stop[i] = max(prev_stop, c - nl)
        elif c < prev_stop and pc < prev_stop:
            x_atr_trailing_stop[i] = min(prev_stop, c + nl)
        elif c > prev_stop:
            x_atr_trailing_stop[i] = c - nl
        else:
            x_atr_trailing_stop[i] = c + nl
            
    df['UT_Stop'] = x_atr_trailing_stop
    df['Buy_Signal'] = (close > df['UT_Stop']) & (close.shift(1) <= df['UT_Stop'].shift(1))
    df['Sell_Signal'] = (close < df['UT_Stop']) & (close.shift(1) >= df['UT_Stop'].shift(1))
    return df

def render_pro_candlestick(df, title, show_ut=True, key_val=1.0, atr_per=10, show_ema=False):
    df = calculate_ut_bot(df, key_value=key_val, atr_period=atr_per)
    total_candles = len(df)
    start_idx = max(0, total_candles - 65)
    x_labels = df.index.strftime('%H:%M' if len(df) > 100 else '%d %b %H:%M')
    df['X_Label'] = x_labels
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=x_labels, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color='#089981', decreasing_line_color='#F23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#F23645',
        line=dict(width=1.5), name='Price'
    ))
    
    if show_ut:
        fig.add_trace(go.Scatter(
            x=x_labels, y=df['UT_Stop'], mode='lines', name='UT Stop',
            line=dict(color='#7E57C2', width=1.5, dash='dot')
        ))
        buys = df[df['Buy_Signal']]
        if not buys.empty:
            fig.add_trace(go.Scatter(
                x=buys['X_Label'], y=buys['Low'] * 0.9992, mode='markers+text',
                marker=dict(symbol='triangle-up', size=12, color='#00C853'),
                text=['BUY'] * len(buys), textposition='bottom center',
                textfont=dict(color='#00C853', size=11, family='Arial Black'), name='UT BUY'
            ))
        sells = df[df['Sell_Signal']]
        if not sells.empty:
            fig.add_trace(go.Scatter(
                x=sells['X_Label'], y=sells['High'] * 1.0008, mode='markers+text',
                marker=dict(symbol='triangle-down', size=12, color='#FF1744'),
                text=['SELL'] * len(sells), textposition='top center',
                textfont=dict(color='#FF1744', size=11, family='Arial Black'), name='UT SELL'
            ))
            
    if show_ema:
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        fig.add_trace(go.Scatter(x=x_labels, y=df['EMA9'], mode='lines', name='9 EMA', line=dict(color='#2962FF', width=1.5)))
    
    visible_df = df.iloc[start_idx:]
    y_min, y_max = visible_df['Low'].min() * 0.998, visible_df['High'].max() * 1.002
    
    fig.update_xaxes(
        type='category', range=[start_idx - 0.5, total_candles + 2], tickangle=0, nticks=6,
        showgrid=True, gridcolor='#F0F3FA', showspikes=True, spikemode='across', spikesnap='cursor', spikecolor='#787B86', spikethickness=1, spikedash='dash'
    )
    fig.update_yaxes(
        side='right', range=[y_min, y_max], fixedrange=False, showgrid=True, gridcolor='#F0F3FA',
        showspikes=True, spikemode='across', spikesnap='cursor', spikecolor='#787B86', spikethickness=1, spikedash='dash'
    )
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=15, color="#131722")),
        template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        xaxis_rangeslider_visible=False, height=520, margin=dict(l=10, r=55, t=45, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        hovermode="x unified", dragmode="pan", newshape=dict(line=dict(color="#2962FF", width=2))
    )
    config = {'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False, 'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'drawrect', 'eraseshape']}
    st.plotly_chart(fig, use_container_width=True, config=config)

# ఇండెక్స్ ధరలు
col_n, col_b, col_s = st.columns(3)
n_p, n_c, n_pct = get_index_price("^NSEI")
b_p, b_c, b_pct = get_index_price("^NSEBANK")
s_p, s_c, s_pct = get_index_price("^BSESN")

with col_n:
    if n_p: st.metric("NIFTY 50", f"₹{n_p:,.0f}", f"{n_c:+.1f} ({n_pct:+.2f}%)")
with col_b:
    if b_p: st.metric("BANK NIFTY", f"₹{b_p:,.0f}", f"{b_c:+.1f} ({b_pct:+.2f}%)")
with col_s:
    if s_p: st.metric("BSE SENSEX", f"₹{s_p:,.0f}", f"{s_c:+.1f} ({s_pct:+.2f}%)")

# చార్ట్ సెక్షన్
with st.expander("📊 ప్రో క్యాండిల్‌స్టిక్ చార్ట్ + UT Bot Alerts (ఓపెన్ / క్లోజ్)", expanded=True):
    chart_options = {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
        "BSE SENSEX": "^BSESN",
        "SBIN (NSE)": "SBIN.NS",
        "RELIANCE (NSE)": "RELIANCE.NS",
        "TCS (NSE)": "TCS.NS",
        "HDFC BANK (NSE)": "HDFCBANK.NS"
    }
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        selected_chart = st.selectbox("చార్ట్ సింబల్:", list(chart_options.keys()))
    with c2:
        selected_tf = st.selectbox("టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1)
    with c3:
        ut_key = st.number_input("UT Key Value:", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
    with c4:
        ut_atr = st.number_input("UT ATR Period:", min_value=1, max_value=50, value=10, step=1)

    t1, t2 = st.columns(2)
    with t1:
        show_ut_toggle = st.checkbox("🤖 UT Bot Alerts (BUY / SELL)", value=True)
    with t2:
