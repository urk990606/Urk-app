import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="centered")

if 'cash' not in st.session_state:
    st.session_state.cash = 100000.00
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}
if 'history' not in st.session_state:
    st.session_state.history = []

st.title("📈 URK")
st.caption("Virtual Paper Trading App (Stocks & Options)")

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

def render_pro_candlestick(df, title):
    fig = go.Figure(data=[go.Candlestick(
        x=df.index.strftime('%d %b %H:%M'),
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        increasing_line_color='#089981',
        decreasing_line_color='#F23645',
        increasing_fillcolor='#089981',
        decreasing_fillcolor='#F23645',
        name=title
    )])
    fig.update_xaxes(
        type='category', tickangle=-45, nticks=8, showgrid=True, gridcolor='#F0F3FA',
        showspikes=True, spikemode='across', spikesnap='cursor', spikecolor='#787B86', spikethickness=1, spikedash='dash'
    )
    fig.update_yaxes(
        side='right', showgrid=True, gridcolor='#F0F3FA',
        showspikes=True, spikemode='across', spikesnap='cursor', spikecolor='#787B86', spikethickness=1, spikedash='dash'
    )
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=14, color="#131722")),
        template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        xaxis_rangeslider_visible=False, height=400, margin=dict(l=10, r=10, t=40, b=20),
        hovermode="x unified", dragmode="pan", newshape=dict(line=dict(color="#2962FF", width=2))
    )
    config = {
        'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False,
        'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'drawrect', 'eraseshape']
    }
    st.plotly_chart(fig, use_container_width=True, config=config)

# 1. మూడు ఇండెక్స్‌ల లైవ్ ధరలు
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

# 2. క్యాండిల్‌స్టిక్ చార్ట్ సెక్షన్
with st.expander("📊 లైవ్ క్యాండిల్‌స్టిక్ చార్ట్ (Cursor & Toolbox)", expanded=True):
    chart_options = {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
        "BSE SENSEX": "^BSESN",
        "SBIN (NSE)": "SBIN.NS",
        "RELIANCE (NSE)": "RELIANCE.NS",
        "TCS (NSE)": "TCS.NS",
        "HDFC BANK (NSE)": "HDFCBANK.NS"
    }
    c1, c2 = st.columns(2)
    with c1:
        selected_chart = st.selectbox("చార్ట్ ఎంచుకోండి:", list(chart_options.keys()))
    with c2:
        selected_tf = st.selectbox("టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1)

    p_val, i_val = timeframes[selected_tf]
    candle_df = get_candle_data(chart_options[selected_chart], p_val, i_val)
    if not candle_df.empty:
        render_pro_candlestick(candle_df, f"{selected_chart} • {selected_tf}")

st.info(f"💰 **వర్చువల్ బ్యాలెన్స్ (Available Cash):** ₹ {st.session_state.cash:,.2f}")

# 3. ట్యాబ్స్: OPTION CHAIN & STOCKS TRADING
tab_opt, tab_stk = st.tabs(["⛓️ Option Chain (CE / PE)", "📈 Stocks Trading (EQ)"])

# --- TAB 1: OPTION CHAIN ---
with tab_opt:
    st.subheader("⛓️ Live Option Chain")
    
    opt_indices = {
        "NIFTY 50": {"spot": n_p or 25350, "step": 50, "lot": 75, "base_iv": 115},
        "BANK NIFTY": {"spot": b_p or 62585, "step": 100, "lot": 30, "base_iv": 280},
        "BSE SENSEX": {"spot": s_p or 82436, "step": 100, "lot": 20, "base_iv": 310}
    }
    
    sel_opt_idx = st.selectbox("ఇండెక్స్ ఎంచుకోండి (Option Chain):", list(opt_indices.keys()))
    idx_info = opt_indices[sel_opt_idx]
    spot_price = idx_info["spot"]
    step = idx_info["step"]
    lot_size = idx_info["lot"]
    base_prem = idx_info["base_iv"]
    
    # ATM స్ట్రైక్ ధర కనుక్కోవడం
    atm_strike = round(spot_price / step) * step
    strikes = [atm_strike + (i * step) for i in range(-6, 7)]
    
    # Option Chain పట్టిక తయారు చేయడం
    chain_rows = []
    option_prices = {}
    
    for strike in strikes:
        diff = spot_price - strike
        # Call (CE) ప్రీమియం లెక్క
        ce_intrinsic = max(0, diff)
        ce_time_val = max(5.0, base_prem * np.exp(-abs(diff) / (step * 4.5)))
        ce_ltp = round(ce_intrinsic + ce_time_val, 2)
        
        # Put (PE) ప్రీమియం లెక్క
        pe_intrinsic = max(0, -diff)
        pe_time_val = max(5.0, base_prem * np.exp(-abs(diff) / (step * 4.5)))
        pe_ltp = round(pe_intrinsic + pe_time_val, 2)
        
        strike_label = f"{strike} (ATM)" if strike == atm_strike else f"{strike}"
        
        chain_rows.append({
            "CALL OI (L)": round(np.random.uniform(15, 85), 1),
            "CALL LTP (₹)": ce_ltp,
            "STRIKE": strike_label,
            "PUT LTP (₹)": pe_ltp,
            "PUT OI (L)": round(np.random.uniform(15, 85), 1)
        })
        
        option_prices[f"{sel_opt_idx} {strike} CE"] = ce_ltp
        option_prices[f"{sel_opt_idx} {strike} PE"] = pe_ltp

    st.caption(f"📍 **Spot Price:** ₹{spot_price:,.2f} | **1 Lot Size:** {lot_size} Qty")
    st.dataframe(pd.DataFrame(chain_rows), use_container_width=True, hide_index=True)
    
    # Option ఆర్డర్ ప్లేస్ చేసే బాక్స్
    st.markdown("### ⚡ Option ఆర్డర్ (Buy / Sell)")
    oc1, oc2, oc3 = st.columns(3)
    with oc1:
        chosen_strike = st.selectbox("Strike Price:", strikes, index=6)
    with oc2:
        opt_type = st.selectbox("రకం (CE / PE):", ["CE", "PE"])
    with oc3:
        lots = st.number_input("Lots (లాట్లు):", min_value=1, value=1, step=1)
        
    contract_name = f"{sel_opt_idx} {chosen_strike} {opt_type}"
    contract_ltp = option_prices[contract_name]
    total_qty = lots * lot_size
    order_val = round(contract_ltp * total_qty, 2)
    
    st.write(f"**{contract_name}** | ప్రీమియం: **₹{contract_ltp}** | మొత్తం క్వాంటిటీ: **{total_qty}** | విలువ: **₹{order_val:,.2f}**")
    
    ob1, ob2 = st.columns(2)
    with ob1:
        if st.button("🟢 BUY OPTION", use_container_width=True):
            if st.session_state.cash >= order_val:
                st.session_state.cash -= order_val
                if contract_name in st.session_state.portfolio:
                    old_q = st.session_state.portfolio[contract_name]['qty']
                    old_a = st.session_state.portfolio[contract_name]['avg_price']
                    new_q = old_q + total_qty
                    new_a = ((old_q * old_a) + order_val) / new_q
                    st.session_state.portfolio[contract_name] = {'qty': new_q, 'avg_price': round(new_a, 2), 'ltp': contract_ltp}
                else:
                    st.session_state.portfolio[contract_name] = {'qty': total_qty, 'avg_price': contract_ltp, 'ltp': contract_ltp}
                st.session_state.history.append({
                    "సమయం": datetime.now().strftime("%H:%M:%S"),
                    "రకం": "BUY (OPT)",
                    "స్టాక్": contract_name,
                    "క్వాంటిటీ": total_qty,
                    "ధర": f"₹{contract_ltp}"
                })
                st.success(f"{contract_name} ({lots} Lot) కొనుగోలు చేశారు!")
                st.rerun()
            else:
                st.error("సరిపడా బ్యాలెన్స్ లేదు!")
    with ob2:
        if st.button("🔴 SELL / EXIT OPTION", use_container_width=True):
            if contract_name in st.session_state.portfolio and st.session_state.portfolio[contract_name]['qty'] >= total_qty:
                st.session_state.cash += order_val
                st.session_state.portfolio[contract_name]['qty'] -= total_qty
                if st.session_state.portfolio[contract_name]['qty'] == 0:
                    del st.session_state.portfolio[contract_name]
                st.session_state.history.append({
                    "సమయం": datetime.now().strftime("%H:%M:%S"),
                    "రకం": "SELL (OPT)",
                    "స్టాక్": contract_name,
                    "క్వాంటిటీ": total_qty,
                    "ధర": f"₹{contract_ltp}"
                })
