import streamlit as st
import yfinance as yf
import pandas as pd

# URK యాప్ సెట్టింగ్స్ & కస్టమ్ లోగో
urk_logo = "https://ui-avatars.com"

st.set_page_config(
    page_title="URK Paper Trading",
    page_icon=urk_logo,
    layout="centered",
    initial_sidebar_state="collapsed"
)

# యాప్ లాగా క్లీన్ లుక్ కోసం మెనూలు దాచడం
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# వర్చువల్ వాలెట్ (₹1,00,000 ప్రారంభ బ్యాలెన్స్)
if 'balance' not in st.session_state:
    st.session_state.balance = 100000.0
if 'holdings' not in st.session_state:
    st.session_state.holdings = {}  # {stock: {'qty': 0, 'avg_price': 0.0}}
if 'history' not in st.session_state:
    st.session_state.history = []

# హెడర్
st.markdown("<h1 style='text-align: center; color: #2962FF;'>📈 URK</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Virtual Paper Trading App (₹0 Risk)</p>", unsafe_allow_html=True)

# వర్చువల్ బ్యాలెన్స్ కార్డ్
st.info(f"💰 **వర్చువల్ బ్యాలెన్స్ (Available Cash):** ₹ {st.session_state.balance:,.2f}")
st.divider()

# 1. స్టాక్ ఎంపిక & లైవ్ ధర
st.subheader("📊 స్టాక్ ఎంచుకోండి")
stocks = {
    "SBIN (State Bank of India)": "SBIN.NS",
    "YESBANK (Yes Bank)": "YESBANK.NS",
    "IDEA (Vodafone Idea)": "IDEA.NS",
    "TATASTEEL (Tata Steel)": "TATASTEEL.NS",
    "RELIANCE (Reliance Ind)": "RELIANCE.NS",
    "INFY (Infosys)": "INFY.NS"
}

selected_name = st.selectbox("స్టాక్ పేరు:", list(stocks.keys()))
symbol = stocks[selected_name]
qty = st.number_input("క్వాంటిటీ (షేర్ల సంఖ్య):", min_value=1, value=10, step=1)

# లైవ్ మార్కెట్ ధర తీసుకోవడం
try:
    ticker = yf.Ticker(symbol)
    live_price = float(ticker.fast_info['last_price'])
    st.metric(label=f"{selected_name} లైవ్ ధర", value=f"₹ {live_price:.2f}")
except:
    live_price = 0.0
    st.warning("లైవ్ ధర లోడ్ కాలేదు. దయచేసి రీఫ్రెష్ చేయండి.")

# 2. Paper BUY / SELL బటన్లు
col1, col2 = st.columns(2)
total_value = live_price * qty

with col1:
    if st.button("🟢 BUY (కొనుగోలు)", use_container_width=True):
        if live_price > 0:
            if st.session_state.balance >= total_value:
                st.session_state.balance -= total_value
                if selected_name in st.session_state.holdings:
                    old_qty = st.session_state.holdings[selected_name]['qty']
                    old_avg = st.session_state.holdings[selected_name]['avg_price']
                    new_qty = old_qty + qty
                    new_avg = ((old_qty * old_avg) + total_value) / new_qty
                    st.session_state.holdings[selected_name] = {'qty': new_qty, 'avg_price': new_avg}
                else:
                    st.session_state.holdings[selected_name] = {'qty': qty, 'avg_price': live_price}
                
                st.session_state.history.append(f"BUY {qty} {selected_name} @ ₹{live_price:.2f}")
                st.success(f"కొనుగోలు పూర్తయింది! ₹{total_value:,.2f} కట్ అయింది.")
                st.rerun()
            else:
                st.error("మీ వర్చువల్ బ్యాలెన్స్ సరిపోదు!")

with col2:
    if st.button("🔴 SELL (అమ్మకం)", use_container_width=True):
        if selected_name in st.session_state.holdings and st.session_state.holdings[selected_name]['qty'] >= qty:
            st.session_state.balance += total_value
            st.session_state.holdings[selected_name]['qty'] -= qty
            if st.session_state.holdings[selected_name]['qty'] == 0:
                del st.session_state.holdings[selected_name]
            
            st.session_state.history.append(f"SELL {qty} {selected_name} @ ₹{live_price:.2f}")
            st.warning(f"అమ్మకం పూర్తయింది! ₹{total_value:,.2f} జమ అయింది.")
            st.rerun()
        else:
            st.error("అమ్మడానికి మీ దగ్గర అన్ని షేర్లు లేవు!")

st.divider()

# 3. పోర్ట్‌ఫోలియో & లాభనష్టాలు (Live P&L)
st.subheader("💼 నా పోర్ట్‌ఫోలియో (Holdings & P&L)")
if st.session_state.holdings:
    for stock, data in st.session_state.holdings.items():
        s_sym = stocks[stock]
        try:
            curr_p = float(yf.Ticker(s_sym).fast_info['last_price'])
        except:
            curr_p = data['avg_price']
        
        pnl = (curr_p - data['avg_price']) * data['qty']
        pnl_color = "green" if pnl >= 0 else "red"
        st.markdown(f"**{stock}** | Qty: `{data['qty']}` | కొన్న ధర: `₹{data['avg_price']:.2f}` | ప్రస్తుత ధర: `₹{curr_p:.2f}` | P&L: :{pnl_color}[**₹{pnl:+.2f}**]")
else:
    st.caption("ప్రస్తుతం మీ పోర్ట్‌ఫోలియోలో షేర్లు ఏవీ లేవు.")

# 4. ఆర్డర్ హిస్టరీ & రీసెట్
with st.expander("📜 ఆర్డర్ హిస్టరీ (Trade Book)"):
    for h in reversed(st.session_state.history):
        st.text(h)

if st.button("🔄 బ్యాలెన్స్ మళ్ళీ ₹1,00,000 కి రీసెట్ చేయండి"):
    st.session_state.balance = 100000.0
    st.session_state.holdings = {}
    st.session_state.history = []
    st.rerun()
