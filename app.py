import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import hashlib
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

def h_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

if 'db' not in st.session_state:
    st.session_state.db = {
        "admin": {
            "pw": h_pw("Urk@2026"),
            "cash": 100000.0,
            "port": {},
            "hist": [],
            "rpnl": 0.0,
            "wl": ["SBIN - NSE", "RELIANCE - NSE", "TCS - NSE", "HDFCBANK - NSE"]
        }
    }

if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("📈 URK Paper Trading")
    t1, t2 = st.tabs(["🔐 Login", "📝 Sign Up"])
    with t1:
        u = st.text_input("Username", key="lu").strip()
        p = st.text_input("Password", type="password", key="lp")
        st.caption("Demo: admin / Urk@2026")
        if st.button("Login", use_container_width=True, type="primary"):
            if u in st.session_state.db and st.session_state.db[u]["pw"] == h_pw(p):
                st.session_state.user = u
                st.rerun()
            else:
                st.error("Wrong Username or Password!")
    with t2:
        nu = st.text_input("New Username", key="su").strip()
        npw = st.text_input("New Password", type="password", key="sp")
        if st.button("Create Account", use_container_width=True):
            if len(nu) >= 3 and len(npw) >= 4 and nu not in st.session_state.db:
                st.session_state.db[nu] = {"pw": h_pw(npw), "cash": 100000.0, "port": {}, "hist": [], "rpnl": 0.0, "wl": ["SBIN - NSE"]}
                st.success("Account Created! Now Login.")
            else:
                st.error("Invalid or existing username!")
    st.stop()

ud = st.session_state.db[st.session_state.user]

c_top1, c_top2 = st.columns([3, 1])
with c_top1:
    st.title("📈 URK")
    st.caption(f"User: **{st.session_state.user}** | Cash: **₹{ud['cash']:,.2f}**")
with c_top2:
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.user = None
        st.rerun()

stocks = {
    "SBIN - NSE": "SBIN.NS", "RELIANCE - NSE": "RELIANCE.NS",
    "TCS - NSE": "TCS.NS", "HDFCBANK - NSE": "HDFCBANK.NS",
    "ICICIBANK - NSE": "ICICIBANK.NS", "INFY - NSE": "INFY.NS",
    "ITC - NSE": "ITC.NS", "TATAMOTORS - NSE": "TATAMOTORS.NS"
}

@st.cache_data(ttl=30)
def get_price(sym):
    try:
        df = yf.Ticker(sym).history(period="2d")
        if len(df) >= 2:
            c, p = df['Close'].iloc[-1], df['Close'].iloc[-2]
            return round(c, 2), round(c - p, 2), round(((c - p) / p) * 100, 2)
        elif len(df) == 1:
            return round(df['Close'].iloc[-1], 2), 0.0, 0.0
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=60)
def get_candles(sym, tf):
    try:
        p_map = {"1m": ("1d", "1m"), "3m": ("1d", "1m"), "5m": ("1d", "5m"), "15m": ("5d", "15m"), "1D": ("6mo", "1d")}
        per, inter = p_map[tf]
        df = yf.Ticker(sym).history(period=per, interval=inter)
        if df.empty:
            return pd.DataFrame()
        if tf == "3m":
            df = df.resample('3min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        return df
    except Exception:
        return pd.DataFrame()

def add_ind(df):
    df = df.copy()
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    df['VWAP'] = (tp * vol).groupby(df.index.date).cumsum() / vol.groupby(df.index.date).cumsum()
    
    tr = pd.concat([df['High']-df['Low'], (df['High']-df['Close'].shift()).abs(), (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=0.1, adjust=False).mean()
    hl2 = (df['High'] + df['Low']) / 2
    ub, lb = hl2 + 3 * atr, hl2 - 3 * atr
    st_line, d = [np.nan]*len(df), [1]*len(df)
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > ub.iloc[i-1]: d[i] = 1
        elif df['Close'].iloc[i] < lb.iloc[i-1]: d[i] = -1
        else: d[i] = d[i-1]
        st_line[i] = lb.iloc[i] if d[i] == 1 else ub.iloc[i]
    df['ST_Up'] = np.where(np.array(d) == 1, st_line, np.nan)
    df['ST_Dn'] = np.where(np.array(d) == -1, st_line, np.nan)
    
    stop = [0.0]*len(df)
    for i in range(1, len(df)):
        c, pc, ps = df['Close'].iloc[i], df['Close'].iloc[i-1], stop[i-1]
        nl = atr.iloc[i]
        if c > ps and pc > ps: stop[i] = max(ps, c - nl)
        elif c < ps and pc < ps: stop[i] = min(ps, c + nl)
        else: stop[i] = c - nl if c > ps else c + nl
    df['UT_Buy'] = (df['Close'] > stop) & (df['Close'].shift() <= pd.Series(stop, index=df.index).shift())
    df['UT_Sell'] = (df['Close'] < stop) & (df['Close'].shift() >= pd.Series(stop, index=df.index).shift())
    return df

if st.button("🔄 Refresh Prices"):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3 = st.tabs(["📊 Trade & Charts", "⭐ Watchlist", "💼 P&L & Portfolio"])

with tab1:
    c1, c2 = st.columns(2)
    ch_map = {"NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK", **stocks}
    sel_ch = c1.selectbox("Chart:", list(ch_map.keys()))
    sel_tf = c2.selectbox("Timeframe:", ["1m", "3m", "5m", "15m", "1D"], index=1)
    
    i1, i2, i3, i4 = st.columns(4)
    u_on = i1.checkbox("UT Bot", True)
    e_on = i2.checkbox("9 EMA", True)
    v_on = i3.checkbox("VWAP", True)
    s_on = i4.checkbox("Supertrend", True)

    cdf = get_candles(ch_map[sel_ch], sel_tf)
    if not cdf.empty:
        cdf = add_ind(cdf)
        xl = cdf.index.strftime('%d %b %H:%M')
        fig = go.Figure([go.Candlestick(x=xl, open=cdf['Open'], high=cdf['High'], low=cdf['Low'], close=cdf['Close'], name="Price")])
        if e_on: fig.add_trace(go.Scatter(x=xl, y=cdf['EMA9'], line=dict(color='blue', width=1.5), name='9 EMA'))
        if v_on: fig.add_trace(go.Scatter(x=xl, y=cdf['VWAP'], line=dict(color='orange', width=1.5), name='VWAP'))
        if s_on:
            fig.add_trace(go.Scatter(x=xl, y=cdf['ST_Up'], line=dict(color='green', width=2), name='ST Bull'))
            fig.add_trace(go.Scatter(x=xl, y=cdf['ST_Dn'], line=dict(color='red', width=2), name='ST Bear'))
        if u_on:
            b_df, s_df = cdf[cdf['UT_Buy']], cdf[cdf['UT_Sell']]
            fig.add_trace(go.Scatter(x=b_df.index.strftime('%d %b %H:%M'), y=b_df['Low']*0.999, mode='markers+text', text=['BUY']*len(b_df), textposition='bottom center', marker=dict(symbol='triangle-up', size=10, color='green'), name='UT Buy'))
            fig.add_trace(go.Scatter(x=s_df.index.strftime('%d %b %H:%M'), y=s_df['High']*1.001, mode='markers+text', text=['SELL']*len(s_df), textposition='top center', marker=dict(symbol='triangle-down', size=10, color='red'), name='UT Sell'))
        fig.update_layout(xaxis_rangeslider_visible=False, height=400, margin=dict(l=5, r=5, t=30, b=5))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    s_name = st.selectbox("Select Stock:", list(stocks.keys()))
    qty = st.number_input("Quantity:", 1, 10000, 10)
    lp, chg, pct = get_price(stocks[s_name])
    if lp:
        st.metric(s_name, f"₹{lp:,.2f}", f"{chg:+.2f} ({pct:+.2f}%)")
        b1, b2 = st.columns(2)
        if b1.button("🟢 BUY", use_container_width=True) and ud['cash'] >= lp * qty:
            ud['cash'] -= lp * qty
            if s_name in ud['port']:
                oq, oa = ud['port'][s_name]['qty'], ud['port'][s_name]['avg']
                ud['port'][s_name] = {'qty': oq+qty, 'avg': round(((oq*oa)+(lp*qty))/(oq+qty), 2)}
            else:
                ud['port'][s_name] = {'qty': qty, 'avg': lp}
            ud['hist'].append({"Time": datetime.now().strftime("%H:%M:%S"), "Type": "BUY", "Stock": s_name, "Qty": qty, "Price": lp, "P&L": "-"})
            st.rerun()
        if b2.button("🔴 SELL", use_container_width=True) and s_name in ud['port'] and ud['port'][s_name]['qty'] >= qty:
            pnl = round((lp - ud['port'][s_name]['avg']) * qty, 2)
            ud['rpnl'] += pnl
            ud['cash'] += lp * qty
            ud['port'][s_name]['qty'] -= qty
            if ud['port'][s_name]['qty'] == 0: del ud['port'][s_name]
            ud['hist'].append({"Time": datetime.now().strftime("%H:%M:%S"), "Type": "SELL", "Stock": s_name, "Qty": qty, "Price": lp, "P&L": f"₹{pnl:+,.2f}"})
            st.rerun()

with tab2:
    add_s = st.selectbox("Add Stock:", list(stocks.keys()), key="wla")
    if st.button("➕ Add to Watchlist") and add_s not in ud['wl']:
        ud['wl'].append(add_s)
        st.rerun()
    rows = []
    for w in ud['wl']:
        p, c, pc = get_price(stocks[w])
        rows.append({"Stock": w, "Price": f"₹{p:,.2f}" if p else "-", "Change": f"{c:+.2f} ({pc:+.2f}%)" if p else "-"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tab3:
    inv, cur, p_rows = 0.0, 0.0, []
    for k, v in ud['port'].items():
        cp, _, _ = get_price(stocks[k])
        cp = cp or v['avg']
        inv += v['qty'] * v['avg']
        cur += v['qty'] * cp
        p_rows.append({"Stock": k, "Qty": v['qty'], "Avg": v['avg'], "LTP": cp, "P&L": round((cp - v['avg'])*v['qty'], 2)})
    upnl = cur - inv
    m1, m2, m3 = st.columns(3)
    m1.metric("Realized P&L", f"₹{ud['rpnl']:+,.2f}")
    m2.metric("Unrealized P&L", f"₹{upnl:+,.2f}")
    m3.metric("Total P&L", f"₹{ud['rpnl']+upnl:+,.2f}")
    if p_rows: st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
    if ud['hist']: st.dataframe(pd.DataFrame(ud['hist'][::-1]), use_container_width=True, hide_index=True)
