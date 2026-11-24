import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# పేజీ సెట్టింగ్స్
st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

# సెషన్ స్టేట్ (డబ్బు, పోర్ట్‌ఫోలియో, ఆర్డర్ హిస్టరీ స్టోర్ చేయడానికి)
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

# హెడర్
st.title("📈 URK")
st.caption("Virtual Paper Trading App (₹0 Risk)")

# 1. NIFTY 50 లైవ్ ఇండెక్స్ డేటా తెచ్చే ఫంక్షన్
@st.cache_data(ttl=60) # ప్రతి 60 సెకన్లకు డేటా అప్‌డేట్ అవుతుంది
def get_nifty_data():
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="2d")
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            curr_price = hist['Close'].iloc[-1]
            change = curr_price - prev_close
            pct = (change / prev_close) * 100
            return round(curr_price, 2), round(change, 2), round(pct, 2)
        elif len(hist) == 1:
            return round(hist['Close'].iloc[-1], 2), 0.0, 0.0
    except Exception:
        pass
    return None, None, None

# Nifty 50 బ్యానర్ చూపించడం
nifty_price, nifty_chg, nifty_pct = get_nifty_data()
if nifty_price:
    st.metric(
        label="📊 NIFTY 50 (NSE Live)",
        value=f"₹ {nifty_price:,.2f}",
        delta=f"{nifty_chg:+.2f} ({nifty_pct:+.2f}%)"
    )

# వర్చువల్ బ్యాలెన్స్ బాక్స్
st.info(f"💰 **వర్చువల్ బ్యాలెన్స్ (Available Cash):** ₹ {st.session_state.cash:,.2f}")

st.divider()

# 2. స్టాక్ ఎంచుకోండి (Nifty 50 స్టాక్స్)
st.subheader("📊 స్టాక్ ఎంచుకోండి")

nifty_stocks = {
    "SBIN (State Bank of India)": "SBIN.NS",
    "RELIANCE (Reliance Industries)": "RELIANCE.NS",
    "TCS (Tata Consultancy Services)": "TCS.NS",
    "HDFCBANK (HDFC Bank)": "HDFCBANK.NS",
    "ICICIBANK (ICICI Bank)": "ICICIBANK.NS",
    "INFY (Infosys)": "INFY.NS",
    "BHARTIARTL (Bharti Airtel)": "BHARTIARTL.NS",
    "ITC (ITC Limited)": "ITC.NS",
    "LT (Larsen & Toubro)": "LT.NS",
    "TATAMOTORS (Tata Motors)": "TATAMOTORS.NS"
}

selected_name = st.selectbox("స్టాక్ పేరు:", list(nifty_stocks.keys()))
ticker = nifty_stocks[selected_name]

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
else:
    st.warning("ప్రస్తుతం లైవ్ ధర లోడ్ అవ్వడం లేదు. మళ్ళీ ప్రయత్నించండి.")

# రిఫ్రెష్ బటన్ (తాజా ధర కోసం)
if st.button("🔄 ధర రిఫ్రెష్ చేయండి (Refresh Price)"):
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

# 3. పోర్ట్‌ఫోలియో (Holdings & P&L)
st.subheader("💼 నా పోర్ట్‌ఫోలియో (Holdings & P&L)")
if st.session_state.portfolio:
    port_data = []
    for s_name, info in st.session_state.portfolio.items():
        curr_p = get_stock_price(nifty_stocks[s_name]) or info['avg_price']
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

# 4. ఆర్డర్ హిస్టరీ
with st.expander("📜 ఆర్డర్ హిస్టరీ (Trade Book)"):
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
    else:
        st.write("ఇంకా ఎలాంటి ట్రేడ్స్ జరగలేదు.")
