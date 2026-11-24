import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="wide")

# 1. LOGIN / LOGOUT సిస్టమ్
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

# 2. సెషన్ స్టేట్
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

# హెడర్ & Logout బటన్
h1, h2 = st.columns([4, 1])
with h1:
    st.title("📈 URK")
    st.caption(f"Welcome, **{st.session_state.username.upper()}** | Virtual Paper Trading")
with h2:
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
    stop[0] = c_vals[0]
    
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

def render_chart(df, title, show_ut=True, key_val=1.0, atr_per=10, show_ema=False):
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
        fig.add_trace(go.Scatter(x=x_lbl, y=df['EMA9'], mode='lines', name='9 EMA', line=dict(color='#2962FF', width=1.5)))
        
    vis = df.iloc[start_idx:]
    fig.update_xaxes(type='category', range=[start_idx - 0.5, total + 2], nticks=6, showgrid=True, gridcolor='#F0F3FA', showspikes=True, spikemode='across', spikesnap='cursor')
    fig.update_yaxes(side='right', range=[vis['Low'].min()*0.998, vis['High'].max()*1.002], showgrid=True, gridcolor='#F0F3FA', showspikes=True, spikemode='across', spikesnap='cursor')
    fig.update_layout(title=dict(text=f"<b>{title}</b>", font=dict(size=15)), template="plotly_white", xaxis_rangeslider_visible=False, height=500, margin=dict(l=10, r=50, t=40, b=20), hovermode="x unified", dragmode="pan")
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displaylogo': False, 'modeBarButtonsToAdd': ['drawline', 'drawrect', 'eraseshape']})

# ఇండెక్స్ ధరలు
cn, cb, cs = st.columns(3)
n_p, n_c, n_pct = get_index_price("^NSEI")
b_p, b_c, b_pct = get_index_price("^NSEBANK")
s_p, s_c, s_pct = get_index_price("^BSESN")

with cn:
    if n_p: st.metric("NIFTY 50", f"₹{n_p:,.0f}", f"{n_c:+.1f} ({n_pct:+.2f}%)")
with cb:
    if b_p: st.metric("BANK NIFTY", f"₹{b_p:,.0f}", f"{b_c:+.1f} ({b_pct:+.2f}%)")
with cs:
    if s_p: st.metric("BSE SENSEX", f"₹{s_p:,.0f}", f"{s_c:+.1f} ({s_pct:+.2f}%)")

# చార్ట్ & UT Bot Alerts
with st.expander("📊 ప్రో క్యాండిల్‌స్టిక్ చార్ట్ + UT Bot Alerts (ఓపెన్ / క్లోజ్)", expanded=True):
    c_opts = {"NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK", "BSE SENSEX": "^BSESN", "SBIN": "SBIN.NS", "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS"}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sel_c = st.selectbox("సింబల్:", list(c_opts.keys()))
    with c2:
        sel_tf = st.selectbox("టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1)
    with c3:
        ut_k = st.number_input("UT Key:", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
    with c4:
        ut_a = st.number_input("UT ATR:", min_value=1, max_value=50, value=10, step=1)
        
    t1, t2 = st.columns(2)
    with t1:
        show_ut = st.checkbox("🤖 UT Bot Alerts (BUY/SELL)", value=True)
    with t2:
        show_ema = st.checkbox("📈 9 EMA లైన్", value=False)
        
    pv, iv = timeframes[sel_tf]
    cdf = get_candle_data(c_opts[sel_c], pv, iv)
    if not cdf.empty:
        render_chart(cdf, f"{sel_c} • {sel_tf}", show_ut=show_ut, key_val=ut_k, atr_per=ut_a, show_ema=show_ema)

st.info(f"💰 **వర్చువల్ బ్యాలెన్స్:** ₹ {st.session_state.cash:,.2f}")

# Option Chain & Stocks Tabs
tab_opt, tab_stk = st.tabs(["⛓️ Option Chain (CE / PE)", "📈 Stocks Trading (EQ)"])

with tab_opt:
    st.subheader("⛓️ Option Chain")
    opt_idx = {
        "NIFTY 50": {"spot": n_p or 25350, "step": 50, "lot": 75, "iv": 115},
        "BANK NIFTY": {"spot": b_p or 62585, "step": 100, "lot": 30, "iv": 280},
        "BSE SENSEX": {"spot": s_p or 82436, "step": 100, "lot": 20, "iv": 310}
    }
    s_opt = st.selectbox("ఇండెక్స్:", list(opt_idx.keys()))
    info = opt_idx[s_opt]
    atm = round(info["spot"] / info["step"]) * info["step"]
    strikes = [atm + (i * info["step"]) for i in range(-6, 7)]
    
    rows = []
    for st_p in strikes:
        diff = info["spot"] - st_p
        ce = round(max(0, diff) + max(5.0, info["iv"] * np.exp(-abs(diff) / (info["step"] * 4.5))), 2)
        pe = round(max(0, -diff) + max(5.0, info["iv"] * np.exp(-abs(diff) / (info["step"] * 4.5))), 2)
        rows.append({"CALL LTP": ce, "STRIKE": f"{st_p} (ATM)" if st_p == atm else f"{st_p}", "PUT LTP": pe})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab_stk:
    st.subheader("📊 స్టాక్ ఆర్డర్")
    s_list = {"SBIN": "SBIN.NS", "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "HDFCBANK": "HDFCBANK.NS"}
    s_name = st.selectbox("స్టాక్:", list(s_list.keys()))
    qty = st.number_input("క్వాంటిటీ:", min_value=1, value=10, step=1)
    
    @st.cache_data(ttl=30)
    def get_sp(sym):
        try:
            d = yf.Ticker(sym).history(period="1d", interval="1m")
            return round(d['Close'].iloc[-1], 2) if not d.empty else None
        except Exception:
            return None
            
    lp = get_sp(s_list[s_name])
    if lp:
        st.markdown(f"### ₹ {lp:,.2f}")

# END OF URK APP
