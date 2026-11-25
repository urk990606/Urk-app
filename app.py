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
    
    c_l1, c_l2, c_l3 = st.columns(3)
    with c_l2:
        with st.form("login_form"):
            u_in = st.text_input("Username")
            p_in = st.text_input("Password", type="password")
            if st.form_submit_button("🔐 Login", use_container_width=True):
                if u_in in VALID_USERS and VALID_USERS[u_in] == p_in:
                    st.session_state.logged_in = True
                    st.session_state.username = u_in
                    st.rerun()
                else:
                    st.error("❌ తప్పు Username లేదా Password!")
    st.stop()

# ==========================================
# 2. సెషన్ స్టేట్ (Cash, Holdings, Watchlist 1-3, P&L)
# ==========================================
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'holdings' not in st.session_state:
    st.session_state.holdings = {}
if 'history' not in st.session_state:
    st.session_state.history = []
if 'realized_pnl' not in st.session_state:
    st.session_state.realized_pnl = 0.0
if 'wl_1' not in st.session_state:
    st.session_state.wl_1 = ["NIFTY 50", "BANK NIFTY", "BSE SENSEX", "SBIN.NS", "RELIANCE.NS"]
if 'wl_2' not in st.session_state:
    st.session_state.wl_2 = ["TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
if 'wl_3' not in st.session_state:
    st.session_state.wl_3 = ["TATAMOTORS.NS", "BAJFINANCE.NS", "LT.NS", "AXISBANK.NS"]

# మాస్టర్ స్టాక్స్ & ఇండెక్స్ లిస్ట్
MASTER_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "BSE SENSEX": "^BSESN",
    "SBIN.NS": "SBIN.NS",
    "RELIANCE.NS": "RELIANCE.NS",
    "TCS.NS": "TCS.NS",
    "HDFCBANK.NS": "HDFCBANK.NS",
    "ICICIBANK.NS": "ICICIBANK.NS",
    "INFY.NS": "INFY.NS",
    "TATAMOTORS.NS": "TATAMOTORS.NS",
    "BAJFINANCE.NS": "BAJFINANCE.NS",
    "LT.NS": "LT.NS",
    "AXISBANK.NS": "AXISBANK.NS",
    "ITC.NS": "ITC.NS",
    "BHARTIARTL.NS": "BHARTIARTL.NS"
}

timeframes = {
    "1m": ("1d", "1m"),
    "3m": ("1d", "3m"),
    "5m": ("2d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("1mo", "1h"),
    "1D": ("6mo", "1d")
}

# ==========================================
# 3. డేటా ఫంక్షన్లు
# ==========================================
@st.cache_data(ttl=45)
def get_quote(symbol):
    try:
        hist = yf.Ticker(symbol).history(period="2d")
        if len(hist) >= 2:
            prev_c, curr_c = hist['Close'].iloc[-2], hist['Close'].iloc[-1]
            chg = curr_c - prev_c
            return round(curr_c, 2), round(chg, 2), round((chg / prev_c) * 100, 2)
        elif len(hist) == 1:
            return round(hist['Close'].iloc[-1], 2), 0.0, 0.0
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=60)
def get_candle_data(symbol, period, interval):
    try:
        t_obj = yf.Ticker(symbol)
        if interval == "3m":
            df = t_obj.history(period="1d", interval="1m")
            if not df.empty:
                return df.resample('3min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
            return pd.DataFrame()
        df = t_obj.history(period=period, interval=interval)
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
    
    c_vals, nl_vals = close.values, n_loss.values
    stop = np.zeros(len(df))
    stop = c_vals
    
    for i in range(1, len(df)):
        ps, c, pc, nl = stop[i-1], c_vals[i], c_vals[i-1], nl_vals[i]
        if c > ps and pc > ps:
            stop[i] = max(ps, c - nl)
        elif c < ps and pc < ps:
            stop[i] = min(ps, c + nl)
        elif c > ps:
            stop[i] = c - nl
        else:
            stop[i] = c + nl
            
    df['UT_Stop'] = stop
    df['Buy_Sig'] = (close > df['UT_Stop']) & (close.shift(1) <= df['UT_Stop'].shift(1))
    df['Sell_Sig'] = (close < df['UT_Stop']) & (close.shift(1) >= df['UT_Stop'].shift(1))
    return df

def render_chart(df, title, show_ut=True, key_val=1.0, atr_per=10, show_ema=True):
    df = calculate_ut_bot(df, key_value=key_val, atr_period=atr_per)
    total = len(df)
    start_idx = max(0, total - 65)
    x_lbl = df.index.strftime('%H:%M' if total > 100 else '%d %b %H:%M')
    df['X'] = x_lbl
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=x_lbl, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color='#089981', decreasing_line_color='#F23645',
        increasing_fillcolor='#089981', decreasing_fillcolor='#F23645', name='Price'
    ))
    
    if show_ut:
        fig.add_trace(go.Scatter(x=x_lbl, y=df['UT_Stop'], mode='lines', name='UT Stop', line=dict(color='#7E57C2', width=1.5, dash='dot')))
        buys = df[df['Buy_Sig']]
        if not buys.empty:
            fig.add_trace(go.Scatter(x=buys['X'], y=buys['Low']*0.9992, mode='markers+text', marker=dict(symbol='triangle-up', size=12, color='#00C853'), text=['BUY']*len(buys), textposition='bottom center', name='BUY'))
        sells = df[df['Sell_Sig']]
        if not sells.empty:
            fig.add_trace(go.Scatter(x=sells['X'], y=sells['High']*1.0008, mode='markers+text', marker=dict(symbol='triangle-down', size=12, color='#FF1744'), text=['SELL']*len(sells), textposition='top center', name='SELL'))
            
    if show_ema:
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        fig.add_trace(go.Scatter(x=x_lbl, y=df['EMA9'], mode='lines', name='9 EMA', line=dict(color='#2962FF', width=1.5)))
        fig.add_trace(go.Scatter(x=x_lbl, y=df['EMA20'], mode='lines', name='20 EMA', line=dict(color='#FF6D00', width=1.5)))
        
    vis = df.iloc[start_idx:]
    fig.update_xaxes(type='category', range=[start_idx - 0.5, total + 2], nticks=6, showgrid=True, gridcolor='#F0F3FA', showspikes=True, spikemode='across', spikesnap='cursor')
    fig.update_yaxes(side='right', range=[vis['Low'].min()*0.998, vis['High'].max()*1.002], showgrid=True, gridcolor='#F0F3FA', showspikes=True, spikemode='across', spikesnap='cursor')
    fig.update_layout(title=dict(text=f"<b>{title}</b>", font=dict(size=15)), template="plotly_white", xaxis_rangeslider_visible=False, height=480, margin=dict(l=10, r=50, t=40, b=20), hovermode="x unified", dragmode="pan")
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False, 'modeBarButtonsToAdd': ['drawline', 'drawrect', 'eraseshape']})

# ఆర్డర్ ఎగ్జిక్యూషన్ ఫంక్షన్
def execute_trade(side, item_name, qty, price, is_option=False):
    total_val = round(qty * price, 2)
    if side == "BUY":
        if st.session_state.cash >= total_val:
            st.session_state.cash -= total_val
            if item_name in st.session_state.holdings:
                old_q = st.session_state.holdings[item_name]['qty']
                old_a = st.session_state.holdings[item_name]['avg']
                new_q = old_q + qty
                new_a = ((old_q * old_a) + total_val) / new_q
                st.session_state.holdings[item_name]['qty'] = new_q
                st.session_state.holdings[item_name]['avg'] = round(new_a, 2)
            else:
                st.session_state.holdings[item_name] = {'qty': qty, 'avg': price, 'is_opt': is_option, 'ltp': price}
            st.session_state.history.append({"సమయం": datetime.now().strftime("%H:%M:%S"), "రకం": "BUY", "పేరు": item_name, "క్వాంటిటీ": qty, "ధర": price, "P&L": 0.0})
            st.success(f"✅ {item_name} ({qty} Qty) @ ₹{price} కొనుగోలు పూర్తయింది!")
            st.rerun()
        else:
            st.error("❌ సరిపడా వర్చువల్ క్యాష్ లేదు!")
    elif side == "SELL":
        if item_name in st.session_state.holdings and st.session_state.holdings[item_name]['qty'] >= qty:
            avg_buy = st.session_state.holdings[item_name]['avg']
            trade_pnl = round((price - avg_buy) * qty, 2)
            st.session_state.realized_pnl += trade_pnl
            st.session_state.cash += total_val
            st.session_state.holdings[item_name]['qty'] -= qty
            if st.session_state.holdings[item_name]['qty'] == 0:
                del st.session_state.holdings[item_name]
            st.session_state.history.append({"సమయం": datetime.now().strftime("%H:%M:%S"), "రకం": "SELL", "పేరు": item_name, "క్వాంటిటీ": qty, "ధర": price, "P&L": trade_pnl})
            st.success(f"✅ {item_name} ({qty} Qty) @ ₹{price} అమ్మేశారు! P&L: ₹{trade_pnl:+.2f}")
            st.rerun()
        else:
            st.error("❌ మీ Holdings లో ఇన్ని షేర్లు/లాట్లు లేవు!")

# ==========================================
# 4. టాప్ హెడర్ & నావిగేషన్ మెనూ
# ==========================================
h1, h2, h3 = st.columns([3, 2, 1])
with h1:
    st.title("📈 URK")
with h2:
