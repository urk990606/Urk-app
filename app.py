import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import hashlib
import time
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

# Password Hashing Function (SHA-256)
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# SECURE USER DATABASE & AUTH STATE
# ==========================================
if 'users_db' not in st.session_state:
    st.session_state.users_db = {
        "admin": {
            "password": hash_password("Urk@2026"),
            "cash": 100000.00,
            "portfolio": {},
            "history": [],
            "realized_pnl": 0.0,
            "watchlist": [
                "SBIN - NSE (State Bank of India)",
                "RELIANCE - NSE (Reliance Industries)",
                "TCS - NSE (Tata Consultancy Services)",
                "HDFCBANK - NSE (HDFC Bank)"
            ]
        }
    }

if 'logged_in_user' not in st.session_state:
    st.session_state.logged_in_user = None
if 'login_attempts' not in st.session_state:
    st.session_state.login_attempts = 0
if 'lockout_until' not in st.session_state:
    st.session_state.lockout_until = 0

# ==========================================
# LOGIN / SIGNUP SCREEN WITH BRUTE-FORCE LOCK
# ==========================================
if st.session_state.logged_in_user is None:
    st.title("📈 URK Paper Trading")
    st.caption("Secure Virtual Paper Trading App (₹0 Risk)")
    st.divider()

    if time.time() < st.session_state.lockout_until:
        remaining = int(st.session_state.lockout_until - time.time())
        st.error(f"🚫 ఎక్కువ సార్లు తప్పు పాస్‌వర్డ్ ప్రయత్నించారు. {remaining} సెకన్ల తర్వాత మళ్ళీ ప్రయత్నించండి.")
        st.stop()

    auth_tab1, auth_tab2 = st.tabs(["🔐 Login (లాగిన్)", "📝 Sign Up (కొత్త అకౌంట్)"])

    with auth_tab1:
        st.subheader("మీ అకౌంట్‌లోకి లాగిన్ అవ్వండి")
        login_user = st.text_input("యూజర్‌నేమ్ (Username):", key="l_user").strip()
        login_pass = st.text_input("పాస్‌వర్డ్ (Password):", type="password", key="l_pass")

        if st.button("Login", use_container_width=True, type="primary"):
            if login_user in st.session_state.users_db and st.session_state.users_db[login_user]["password"] == hash_password(login_pass):
                st.session_state.logged_in_user = login_user
                st.session_state.login_attempts = 0
                st.success(f"స్వాగతం {login_user}!")
                st.rerun()
            else:
                st.session_state.login_attempts += 1
                if st.session_state.login_attempts >= 3:
                    st.session_state.lockout_until = time.time() + 30
                    st.session_state.login_attempts = 0
                    st.error("3 సార్లు తప్పు పాస్‌వర్డ్ ఎంటర్ చేశారు! 30 సెకన్ల పాటు లాగిన్ లాక్ చేయబడింది.")
                else:
                    st.error(f"తప్పు యూజర్‌నేమ్ లేదా పాస్‌వర్డ్! (మిగిలిన అవకాశాలు: {3 - st.session_state.login_attempts})")

    with auth_tab2:
        st.subheader("కొత్త ట్రేడింగ్ అకౌంట్ సృష్టించండి")
        new_user = st.text_input("కొత్త యూజర్‌నేమ్:", key="s_user").strip()
        new_pass = st.text_input("కొత్త పాస్‌వర్డ్ (కనీసం 6 అక్షరాలు):", type="password", key="s_pass")
        confirm_pass = st.text_input("పాస్‌వర్డ్ నిర్ధారించండి:", type="password", key="s_cpass")

        if st.button("Create Account (₹1,00,000 Virtual Cash)", use_container_width=True):
            if len(new_user) < 3:
                st.warning("యూజర్‌నేమ్ కనీసం 3 అక్షరాలు ఉండాలి.")
            elif len(new_pass) < 6:
                st.warning("భద్రత కోసం పాస్‌వర్డ్ కనీసం 6 అక్షరాలు ఉండాలి.")
            elif new_user in st.session_state.users_db:
                st.error("ఈ యూజర్‌నేమ్ ఇప్పటికే ఉంది. వేరే పేరు ప్రయత్నించండి.")
            elif new_pass != confirm_pass:
                st.error("పాస్‌వర్డ్‌లు సరిపోలడం లేదు!")
            else:
                st.session_state.users_db[new_user] = {
                    "password": hash_password(new_pass),
                    "cash": 100000.00,
                    "portfolio": {},
                    "history": [],
                    "realized_pnl": 0.0,
                    "watchlist": [
                        "SBIN - NSE (State Bank of India)",
                        "RELIANCE - NSE (Reliance Industries)"
                    ]
                }
                st.success("అకౌంట్ విజయవంతంగా క్రియేట్ అయింది! ఇప్పుడు Login ట్యాబ్ ద్వారా లాగిన్ అవ్వండి.")

    st.stop()

# ==========================================
# TECHNICAL INDICATORS CALCULATION
# ==========================================
def calculate_indicators(df, ut_key=1.0, ut_atr_period=10, st_period=10, st_mult=3.0):
    df = df.copy()
    
    # 1. 9 EMA
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    
    # 2. VWAP (Session/Daily Reset)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, np.nan).fillna(1)
    df['Date'] = df.index.date
    df['Cum_TP_Vol'] = (tp * vol).groupby(df['Date']).cumsum()
    df['Cum_Vol'] = vol.groupby(df['Date']).cumsum()
    df['VWAP'] = df['Cum_TP_Vol'] / df['Cum_Vol']
    
    # True Range (TR)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift(1)).abs()
    low_close = (df['Low'] - df['Close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # 3. Supertrend
    atr_st = tr.ewm(alpha=1/st_period, adjust=False).mean()
    hl2 = (df['High'] + df['Low']) / 2
    upperband = hl2 + (st_mult * atr_st)
    lowerband = hl2 - (st_mult * atr_st)
    
    final_ub = upperband.copy()
    final_lb = lowerband.copy()
    st_dir = [1] * len(df)
    supertrend = [np.nan] * len(df)
    
    for i in range(1, len(df)):
        if upperband.iloc[i] < final_ub.iloc[i-1] or df['Close'].iloc[i-1] > final_ub.iloc[i-1]:
            final_ub.iloc[i] = upperband.iloc[i]
        else:
            final_ub.iloc[i] = final_ub.iloc[i-1]
            
        if lowerband.iloc[i] > final_lb.iloc[i-1] or df['Close'].iloc[i-1] < final_lb.iloc[i-1]:
            final_lb.iloc[i] = lowerband.iloc[i]
        else:
            final_lb.iloc[i] = final_lb.iloc[i-1]
            
        if st_dir[i-1] == 1 and df['Close'].iloc[i] < final_lb.iloc[i]:
            st_dir[i] = -1
        elif st_dir[i-1] == -1 and df['Close'].iloc[i] > final_ub.iloc[i]:
            st_dir[i] = 1
        else:
            st_dir[i] = st_dir[i-1]
            
        supertrend[i] = final_lb.iloc[i] if st_dir[i] == 1 else final_ub.iloc[i]
        
    df['Supertrend'] = supertrend
    df['ST_Dir'] = st_dir
    df['ST_Up'] = np.where(df['ST_Dir'] == 1, df['Supertrend'], np.nan)
    df['ST_Down'] = np.where(df['ST_Dir'] == -1, df['Supertrend'], np.nan)
    
    # 4. UT Bot Alerts
    atr_ut = tr.ewm(alpha=1/ut_atr_period, adjust=False).mean()
    nLoss = ut_key * atr_ut
    src = df['Close']
    xATRTrailingStop = [0.0] * len(df)
    pos = [0] * len(df)
    
    for i in range(1, len(df)):
        prev_stop = xATRTrailingStop[i-1]
        if src.iloc[i] > prev_stop and src.iloc[i-1] > prev_stop:
            xATRTrailingStop[i] = max(prev_stop, src.iloc[i] - nLoss.iloc[i])
        elif src.iloc[i] < prev_stop and src.iloc[i-1] < prev_stop:
            xATRTrailingStop[i] = min(prev_stop, src.iloc[i] + nLoss.iloc[i])
        elif src.iloc[i] > prev_stop:
            xATRTrailingStop[i] = src.iloc[i] - nLoss.iloc[i]
        else:
            xATRTrailingStop[i] = src.iloc[i] + nLoss.iloc[i]
            
        if src.iloc[i-1] < prev_stop and src.iloc[i] > prev_stop:
            pos[i] = 1
        elif src.iloc[i-1] > prev_stop and src.iloc[i] < prev_stop:
            pos[i] = -1
        else:
            pos[i] = pos[i-1]
            
    df['UT_Stop'] = xATRTrailingStop
    df['UT_Buy'] = (src > df['UT_Stop']) & (src.shift(1) <= df['UT_Stop'].shift(1))
    df['UT_Sell'] = (src < df['UT_Stop']) & (src.shift(1) >= df['UT_Stop'].shift(1))
    
    return df

# ==========================================
# MAIN APP (AFTER LOGIN)
# ==========================================
current_user = st.session_state.logged_in_user
user_data = st.session_state.users_db[current_user]

head_col1, head_col2 = st.columns()
with head_col1:
    st.title("📈 URK")
    st.caption(f"👤 యూజర్: **{current_user}** | Virtual Paper Trading (₹0 Risk)")
with head_col2:
    st.write("")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in_user = None
        st.rerun()

stocks_list = {
    "SBIN - NSE (State Bank of India)": "SBIN.NS",
    "SBIN - BSE (State Bank of India)": "SBIN.BO",
    "RELIANCE - NSE (Reliance Industries)": "RELIANCE.NS",
    "RELIANCE - BSE (Reliance Industries)": "RELIANCE.BO",
    "TCS - NSE (Tata Consultancy Services)": "TCS.NS",
    "HDFCBANK - NSE (HDFC Bank)": "HDFCBANK.NS",
    "ICICIBANK - NSE (ICICI Bank)": "ICICIBANK.NS",
    "INFY - NSE (Infosys)": "INFY.NS",
    "BHARTIARTL - NSE (Bharti Airtel)": "BHARTIARTL.NS",
    "ITC - NSE (ITC Limited)": "ITC.NS",
    "LT - NSE (Larsen & Toubro)": "LT.NS",
    "TATAMOTORS - NSE (Tata Motors)": "TATAMOTORS.NS"
}

timeframes = {
    "1m": ("1d", "1m"),
    "3m": ("1d", "3m"),
    "5m": ("1d", "5m"),
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
