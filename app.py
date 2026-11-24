import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# పేజీ సెట్టింగ్స్
st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

# సెషన్ స్టేట్
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

# హెడర్
st.title("📈 URK")
st.caption("Virtual Paper Trading App (₹0 Risk)")

# టైమ్ ఫ్రేమ్ సెట్టింగ్స్ (3m తో సహా)
timeframes = {
    "1m": ("1d", "1m"),
    "3m": ("1d", "3m"),
    "5m": ("1d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("1mo", "1h"),
    "1D": ("6mo", "1d")
}

# ఇండెక్స్ లైవ్ ధర తెచ్చే ఫంక్షన్
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

# OHLC (Open, High, Low, Close) క్యాండిల్ డేటా తెచ్చే ఫంక్షన్
@st.cache_data(ttl=60)
def get_candle_data(symbol, period, interval):
    try:
        ticker_obj = yf.Ticker(symbol)
        if interval == "3m":
            df = ticker_obj.history(period="1d", interval="1m")
            if not df.empty:
                df_3m = df.resample('3min').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last'
                }).dropna()
                return df_3m
            return pd.DataFrame()
        else:
            df = ticker_obj.history(period=period, interval=interval)
            return df[['Open', 'High', 'Low', 'Close']].dropna() if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# Dhan తరహా డార్క్ క్యాండిల్‌స్టిక్ చార్ట్ గీసే ఫంక్షన్
def plot_dhan_candlestick(df, title):
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        increasing_line_color='#00E676',  # Dhan గ్రీన్ క్యాండిల్
        decreasing_line_color='#FF5252',  # Dhan రెడ్ క్యాండిల్
        increasing_fillcolor='#00E676',
        decreasing_fillcolor='#FF5252',
        name=title
    )])
    
    # మార్కెట్ లేని సమయాల్లో ఖాళీ గ్యాప్స్ తీసేయడానికి
    fig.update_xaxes(
        type='category',
        tickangle=-45,
        nticks=8,
        showgrid=True,
        gridcolor='#1E222D'
    )
    fig.update_yaxes(
        side='right', # కుడి వైపు ధర స్కేల్ (Dhan / TradingView లాగా)
        showgrid=True,
        gridcolor='#1E222D'
    )
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=14, color="#E0E0E0")),
        template="plotly_dark",
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        xaxis_rangeslider_visible=False,
        height=380,
        margin=dict(l=10, r=10, t=35, b=20),
        dragmode="pan"
    )
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# 1. మూడు ఇండెక్స్‌ల లైవ్ ధరలు
indices = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "BSE SENSEX": "^BSESN"
}

col_n, col_b, col_s = st.columns(3)
with col_n:
    n_p, n_c, n_pct = get_index_price("^NSEI")
    if n_p: st.metric("NIFTY 50", f"₹{n_p:,.0f}", f"{n_c:+.1f} ({n_pct:+.2f}%)")
with col_b:
    b_p, b_c, b_pct = get_index_price("^NSEBANK")
    if b_p: st.metric("BANK NIFTY", f"₹{b_p:,.0f}", f"{b_c:+.1f} ({b_pct:+.2f}%)")
with col_s:
    s_p, s_c, s_pct = get_index_price("^BSESN")
    if s_p: st.metric("BSE SENSEX", f"₹{s_p:,.0f}", f"{s_c:+.1f} ({s_pct:+.2f}%)")

# 2. Dhan తరహా క్యాండిల్‌స్టిక్ చార్ట్ సెక్షన్
with st.expander("📊 క్యాండిల్‌స్టిక్ చార్ట్ (NIFTY 50 / BANK NIFTY / SENSEX)", expanded=True):
    selected_idx_name = st.radio("ఇండెక్స్:", list(indices.keys()), horizontal=True)
    selected_tf = st.radio("టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1, horizontal=True)
    
    p_val, i_val = timeframes[selected_tf]
    candle_df = get_candle_data(indices[selected_idx_name], p_val, i_val)
    
    if not candle_df.empty:
        plot_dhan_candlestick(candle_df, f"{selected_idx_name} ({selected_tf})")
    else:
        st.info("ప్రస్తుతం ఈ టైమ్ ఫ్రేమ్‌కు క్యాండిల్ డేటా అందుబాటులో లేదు.")

# వర్చువల్ బ్యాలెన్స్ బాక్స్
st.info(f"💰 **వర్చువల్ బ్యాలెన్స్ (Available Cash):** ₹ {st.session_state.cash:,.2f}")

st.divider()

# 3. స్టాక్ ఎంచుకోండి (NSE & BSE స్టాక్స్)
st.subheader("📊 ట్రేడింగ్ కోసం స్టాక్ ఎంచుకోండి")

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

selected_name = st.selectbox("స్టాక్ పేరు:", list(stocks_list.keys()))
ticker = stocks_list[selected_name]

qty = st.number_input("క్వాంటిటీ (షేర్ల సంఖ్య):", min_value=1, value=10, step=1)

# ఎంచుకున్న స్టాక్ లైవ్ ధర
@st.cache_data(ttl=30)
def get_stock_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d", interval="1m")
        if not data.empty:
            return round(data['Close'].iloc[-1], 2)
        return round(stock.fast_info['last_price'], 2)
    except Exception:
        return None

live_price = get_stock_price(ticker)

if live_price:
    st.write(f"**{selected_name} లైవ్ ధర**")
    st.markdown(f"## ₹ {live_price:,.2f}")
    
    # స్టాక్ క్యాండిల్ చార్ట్
    with st.expander(f"🕯️ {selected_name} క్యాండిల్‌స్టిక్ చార్ట్ చూడండి"):
        s_tf = st.radio("స్టాక్ టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1, horizontal=True, key="s_tf")
        sp_val, si_val = timeframes[s_tf]
        s_candle_df = get_candle_data(ticker, sp_val, si_val)
        if not s_candle_df.empty:
            plot_dhan_candlestick(s_candle_df, f"{selected_name} ({s_tf})")
else:
    st.warning("ప్రస్తుతం లైవ్ ధర లోడ్ అవ్వడం లేదు. మళ్ళీ ప్రయత్నించండి.")

# రిఫ్రెష్ బటన్
if st.button("🔄 ధరలు & క్యాండిల్స్ రిఫ్రెష్ చేయండి (Refresh)"):
    st.cache_data.clear()
    st.rerun()

# BUY / SELL బటన్లు
col1, col2 = st.columns(2)

with col1:
    if st.button("🟢 BUY (కొనుగోలు)", use_container_width=True) and live_price:
        total_cost = live_price * qty
        if st.session_state.cash >= total_cost:
            st.session_state.cash -= total_cost
            if selected_name in st.session_state.portfolio:
                old_qty = st.session_state.portfolio[selected_name]['qty']
                old_avg = st.session_state.portfolio[selected_name]['avg_price']
                new_qty = old_qty + qty
                new_avg = ((old_qty * old_avg) + total_cost) / new_qty
                st.session_state.portfolio[selected_name] = {'qty': new_qty, 'avg_price': round(new_avg, 2)}
            else:
                st.session_state.portfolio[selected_name] = {'qty': qty, 'avg_price': live_price}
            
            st.session_state.history.append({
                "సమయం": datetime.now().strftime("%H:%M:%S"),
                "రకం": "BUY",
                "స్టాక్": selected_name,
                "క్వాంటిటీ": qty,
                "ధర": f"₹{live_price}"
            })
            st.success(f"{qty} షేర్లు కొనుగోలు చేశారు!")
            st.rerun()
        else:
            st.error("సరిపడా వర్చువల్ బ్యాలెన్స్ లేదు!")

with col2:
    if st.button("🔴 SELL (అమ్మకం)", use_container_width=True) and live_price:
        if selected_name in st.session_state.portfolio and st.session_state.portfolio[selected_name]['qty'] >= qty:
            total_gain = live_price * qty
            st.session_state.cash += total_gain
            st.session_state.portfolio[selected_name]['qty'] -= qty
            if st.session_state.portfolio[selected_name]['qty'] == 0:
                del st.session_state.portfolio[selected_name]
            
            st.session_state.history.append({
                "సమయం": datetime.now().strftime("%H:%M:%S"),
                "రకం": "SELL",
                "స్టాక్": selected_name,
                "క్వాంటిటీ": qty,
                "ధర": f"₹{live_price}"
            })
            st.success(f"{qty} షేర్లు అమ్మేశారు!")
            st.rerun()
        else:
            st.error("మీ పోర్ట్‌ఫోలియోలో ఇన్ని షేర్లు లేవు!")

st.divider()

# 4. పోర్ట్‌ఫోలియో (Holdings & P&L)
st.subheader("💼 నా పోర్ట్‌ఫోలియో (Holdings & P&L)")
if st.session_state.portfolio:
    port_data = []
    for s_name, info in st.session_state.portfolio.items():
        curr_p = get_stock_price(stocks_list[s_name]) or info['avg_price']
        pnl = (curr_p - info['avg_price']) * info['qty']
        port_data.append({
            "స్టాక్": s_name,
            "షేర్లు": info['qty'],
            "కొన్న ధర": f"₹{info['avg_price']}",
            "ప్రస్తుత ధర": f"₹{curr_p}",
            "లాభం/నష్టం (P&L)": f"₹{pnl:+.2f}"
        })
    st.dataframe(pd.DataFrame(port_data), use_container_width=True)
else:
    st.write("ప్రస్తుతం మీ పోర్ట్‌ఫోలియోలో షేర్లు ఏవీ లేవు.")

# 5. ఆర్డర్ హిస్టరీ
with st.expander("📜 ఆర్డర్ హిస్టరీ (Trade Book)"):
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
    else:
