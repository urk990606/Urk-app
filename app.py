import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

st.title("📈 URK")
st.caption("Virtual Paper Trading App (₹0 Risk)")

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

# 1. మూడు ఇండెక్స్‌ల లైవ్ ధరలు
col_n, col_b, col_s = st.columns(3)
with col_n:
    n_p, n_c, n_pct = get_index_price("^NSEI")
    if n_p:
        st.metric("NIFTY 50", f"₹{n_p:,.0f}", f"{n_c:+.1f} ({n_pct:+.2f}%)")
with col_b:
    b_p, b_c, b_pct = get_index_price("^NSEBANK")
    if b_p:
        st.metric("BANK NIFTY", f"₹{b_p:,.0f}", f"{b_c:+.1f} ({b_pct:+.2f}%)")
with col_s:
    s_p, s_c, s_pct = get_index_price("^BSESN")
    if s_p:
        st.metric("BSE SENSEX", f"₹{s_p:,.0f}", f"{s_c:+.1f} ({s_pct:+.2f}%)")

# 2. TradingView కొత్త Advanced Chart విడ్జెట్ (iPad & Mobile సపోర్ట్‌తో)
def render_advanced_tv_chart(tv_symbol, interval="3"):
    config = {
        "autosize": True,
        "symbol": tv_symbol,
        "interval": interval,
        "timezone": "Asia/Kolkata",
        "theme": "light",
        "style": "1",
        "locale": "en",
        "allow_symbol_change": True,
        "hide_side_toolbar": False,
        "hide_top_toolbar": False,
        "withdateranges": True,
        "calendar": False,
        "support_host": "https://tradingview.com"
    }
    config_json = json.dumps(config)
    
    tv_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        html, body {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; }}
      </style>
    </head>
    <body>
      <div class="tradingview-widget-container" style="height:500px;width:100%;">
        <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%;"></div>
        <script type="text/javascript" src="https://tradingview.com" async>
        {config_json}
        </script>
      </div>
    </body>
    </html>
    """
    components.html(tv_html, height=510)

st.subheader("📊 TradingView చార్ట్ (Toolbox & Cursor)")

tv_symbols = {
    "BSE SENSEX (Index)": "BSE:SENSEX",
    "SBIN (NSE)": "NSE:SBIN",
    "RELIANCE (NSE)": "NSE:RELIANCE",
    "TCS (NSE)": "NSE:TCS",
    "HDFC BANK (NSE)": "NSE:HDFCBANK",
    "ICICI BANK (NSE)": "NSE:ICICIBANK",
    "INFOSYS (NSE)": "NSE:INFY",
    "TATA MOTORS (NSE)": "NSE:TATAMOTORS",
    "AXIS BANK (NSE)": "NSE:AXISBANK",
    "BAJAJ FINANCE (NSE)": "NSE:BAJFINANCE"
}

c1, c2 = st.columns(2)
with c1:
    tv_choice = st.selectbox("చార్ట్ సింబల్:", list(tv_symbols.keys()))
with c2:
    tv_interval = st.selectbox(
        "టైమ్ ఫ్రేమ్:",
        ["1", "3", "5", "15", "30", "60", "D"],
        index=1,
        format_func=lambda x: f"{x}m" if x.isdigit() else x
    )

render_advanced_tv_chart(tv_symbols[tv_choice], tv_interval)

st.info(f"💰 **వర్చువల్ బ్యాలెన్స్ (Available Cash):** ₹ {st.session_state.cash:,.2f}")
st.divider()

# 3. ట్రేడింగ్ కోసం స్టాక్ ఎంచుకోండి
st.subheader("📊 ఆర్డర్ ప్లేస్ చేయండి (Buy / Sell)")

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

if st.button("🔄 ధరలు రిఫ్రెష్ చేయండి (Refresh)"):
    st.cache_data.clear()
    st.rerun()

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

with st.expander("📜 ఆర్డర్ హిస్టరీ (Trade Book)"):
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
    else:
        st.write("ఇంకా ఎలాంటి ట్రేడ్స్ జరగలేదు.")
