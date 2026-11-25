import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="URK Paper Trading", page_icon="📈", layout="wide")

VALID_USERS = {"urk": "1234", "friend": "5678"}

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>📈 URK Paper Trading</h1>", unsafe_allow_html=True)
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

MASTER_SYMBOLS = {
    "NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK", "BSE SENSEX": "^BSESN",
    "SBIN.NS": "SBIN.NS", "RELIANCE.NS": "RELIANCE.NS", "TCS.NS": "TCS.NS",
    "HDFCBANK.NS": "HDFCBANK.NS", "ICICIBANK.NS": "ICICIBANK.NS", "INFY.NS": "INFY.NS",
    "TATAMOTORS.NS": "TATAMOTORS.NS", "BAJFINANCE.NS": "BAJFINANCE.NS", "LT.NS": "LT.NS"
}

timeframes = {
    "1m": ("1d", "1m"), "3m": ("1d", "3m"), "5m": ("2d", "5m"),
    "15m": ("5d", "15m"), "1h": ("1mo", "1h"), "1D": ("6mo", "1d")
}

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
        if c > ps and pc > ps: stop[i] = max(ps, c - nl)
        elif c < ps and pc < ps: stop[i] = min(ps, c + nl)
        elif c > ps: stop[i] = c - nl
        else: stop[i] = c + nl
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
    fig.add_trace(go.Candlestick(x=x_lbl, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='#089981', decreasing_line_color='#F23645', increasing_fillcolor='#089981', decreasing_fillcolor='#F23645', name='Price'))
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
    def execute_trade(side, item_name, qty, price, is_option=False):
    total_val = round(qty * price, 2)
    if side == "BUY":
        if st.session_state.cash >= total_val:
            st.session_state.cash -= total_val
            if item_name in st.session_state.holdings:
                old_q = st.session_state.holdings[item_name]['qty']
                old_a = st.session_state.holdings[item_name]['avg']
                new_q = old_q + qty
                st.session_state.holdings[item_name]['qty'] = new_q
                st.session_state.holdings[item_name]['avg'] = round(((old_q * old_a) + total_val) / new_q, 2)
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

h1, h2, h3 = st.columns([2, 2, 1])
with h1:
    st.title("📈 URK")
with h2:
    st.metric("💰 Available Cash", f"₹ {st.session_state.cash:,.2f}")
with h3:
    st.write("")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

cn, cb, cs = st.columns(3)
n_p, n_c, n_pct = get_quote("^NSEI")
b_p, b_c, b_pct = get_quote("^NSEBANK")
s_p, s_c, s_pct = get_quote("^BSESN")

with cn:
    if n_p: st.metric("NIFTY 50", f"₹{n_p:,.0f}", f"{n_c:+.1f} ({n_pct:+.2f}%)")
with cb:
    if b_p: st.metric("BANK NIFTY", f"₹{b_p:,.0f}", f"{b_c:+.1f} ({b_pct:+.2f}%)")
with cs:
    if s_p: st.metric("BSE SENSEX", f"₹{s_p:,.0f}", f"{s_c:+.1f} ({s_pct:+.2f}%)")

page_chart, page_wl, page_hold, page_pnl = st.tabs(["📊 Chart & Trade", "⭐ Watchlist (3 Pages)", "💼 Holdings", "💰 P&L Report"])

with page_chart:
    with st.expander("📊 ప్రో క్యాండిల్‌స్టిక్ చార్ట్ + UT Bot Alerts (ఓపెన్ / క్లోజ్)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1: sel_c = st.selectbox("సింబల్:", list(MASTER_SYMBOLS.keys()))
        with c2: sel_tf = st.selectbox("టైమ్ ఫ్రేమ్:", list(timeframes.keys()), index=1)
        with c3: ut_k = st.number_input("UT Key:", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
        with c4: ut_a = st.number_input("UT ATR:", min_value=1, max_value=50, value=10, step=1)
        t1, t2 = st.columns(2)
        with t1: show_ut = st.checkbox("🤖 UT Bot Alerts", value=True)
        with t2: show_ema = st.checkbox("📈 9 & 20 EMA", value=True)
        pv, iv = timeframes[sel_tf]
        cdf = get_candle_data(MASTER_SYMBOLS[sel_c], pv, iv)
        if not cdf.empty:
            render_chart(cdf, f"{sel_c} • {sel_tf}", show_ut=show_ut, key_val=ut_k, atr_per=ut_a, show_ema=show_ema)

    st.divider()
    sub_opt, sub_stk = st.tabs(["⛓️ Option Chain (CE / PE)", "📈 Stocks Order (EQ)"])
    
    with sub_opt:
        opt_idx = {
            "NIFTY 50": {"spot": n_p or 25350, "step": 50, "lot": 75, "iv": 115},
            "BANK NIFTY": {"spot": b_p or 62585, "step": 100, "lot": 30, "iv": 280},
            "BSE SENSEX": {"spot": s_p or 82436, "step": 100, "lot": 20, "iv": 310}
        }
        s_opt = st.selectbox("ఇండెక్స్:", list(opt_idx.keys()))
        info = opt_idx[s_opt]
        atm = round(info["spot"] / info["step"]) * info["step"]
        strikes = [atm + (i * info["step"]) for i in range(-5, 6)]
        rows, opt_prices = [], {}
        for st_p in strikes:
            diff = info["spot"] - st_p
            ce = round(max(0, diff) + max(5.0, info["iv"] * np.exp(-abs(diff) / (info["step"] * 4.5))), 2)
            pe = round(max(0, -diff) + max(5.0, info["iv"] * np.exp(-abs(diff) / (info["step"] * 4.5))), 2)
            rows.append({"CALL LTP (₹)": ce, "STRIKE": f"{st_p} (ATM)" if st_p == atm else f"{st_p}", "PUT LTP (₹)": pe})
            opt_prices[f"{s_opt} {st_p} CE"] = ce
            opt_prices[f"{s_opt} {st_p} PE"] = pe
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        oc1, oc2, oc3 = st.columns(3)
        with oc1: ch_st = st.selectbox("Strike:", strikes, index=5)
        with oc2: o_type = st.selectbox("Type:", ["CE", "PE"])
        with oc3: lots = st.number_input("Lots:", min_value=1, value=1, step=1)
        c_name = f"{s_opt} {ch_st} {o_type}"
        c_ltp = opt_prices[c_name]
        t_qty = lots * info["lot"]
        st.write(f"**{c_name}** | LTP: **₹{c_ltp}** | Qty: **{t_qty}** | విలువ: **₹{c_ltp * t_qty:,.2f}**")
        ob1, ob2 = st.columns(2)
        with ob1:
            if st.button("🟢 BUY OPTION", use_container_width=True): execute_trade("BUY", c_name, t_qty, c_ltp, True)
        with ob2:
            if st.button("🔴 SELL OPTION", use_container_width=True): execute_trade("SELL", c_name, t_qty, c_ltp, True)

    with sub_stk:
        eq_symbols = {k: v for k, v in MASTER_SYMBOLS.items() if not v.startswith("^")}
        s_name = st.selectbox("స్టాక్:", list(eq_symbols.keys()))
        s_qty = st.number_input("Qty:", min_value=1, value=10, step=1)
        lp, _, _ = get_quote(eq_symbols[s_name])
        if lp:
            st.markdown(f"### {s_name}: ₹ {lp:,.2f}")
            sb1, sb2 = st.columns(2)
            with sb1:
                if st.button("🟢 BUY STOCK", use_container_width=True): execute_trade("BUY", s_name, s_qty, lp, False)
            with sb2:
                if st.button("🔴 SELL STOCK", use_container_width=True): execute_trade("SELL", s_name, s_qty, lp, False)

with page_wl:
    st.subheader("⭐ My Watchlists (3 Pages)")
    wl_t1, wl_t2, wl_t3 = st.tabs(["📌 Watchlist 1", "📌 Watchlist 2", "📌 Watchlist 3"])
    def render_wl(wl_key, tid):
        ca1, ca2 = st.columns([3, 1])
        with ca1: new_s = st.selectbox("స్టాక్ యాడ్:", list(MASTER_SYMBOLS.keys()), key=f"s_{tid}")
        with ca2:
            st.write("")
            if st.button("➕ Add", key=f"a_{tid}", use_container_width=True):
                if new_s not in st.session_state[wl_key]:
                    st.session_state[wl_key].append(new_s)
                    st.rerun()
        for item in st.session_state[wl_key]:
            p, c, pct = get_quote(MASTER_SYMBOLS[item])
            w1, w2, w3, w4 = st.columns([3, 2, 2, 1])
            w1.write(f"**{item}**")
            w2.write(f"₹ {p:,.2f}" if p else "...")
            if c is not None: w3.markdown(f":{'green' if c>=0 else 'red'}[{c:+.2f} ({pct:+.2f}%)]")
            if w4.button("🗑️", key=f"d_{tid}_{item}"):
                st.session_state[wl_key].remove(item)
                st.rerun()
    with wl_t1: render_wl("wl_1", "1")
    with wl_t2: render_wl("wl_2", "2")
    with wl_t3: render_wl("wl_3", "3")

with page_hold:
    st.subheader("💼 నా Holdings & Positions")
    if st.session_state.holdings:
        for h_name, info in list(st.session_state.holdings.items()):
            if info['is_opt']:
                cp = opt_prices.get(h_name, info['ltp'])
            else:
                qp, _, _ = get_quote(MASTER_SYMBOLS.get(h_name, h_name))
                cp = qp if qp else info['avg']
            pnl = (cp - info['avg']) * info['qty']
            hc1, hc2, hc3, hc4 = st.columns([3, 2, 2, 1.5])
            hc1.write(f"**{h_name}** (Qty: {info['qty']} | Avg: ₹{info['avg']})")
            hc2.write(f"LTP: ₹{cp:,.2f}")
            hc3.markdown(f"P&L: :{'green' if pnl>=0 else 'red'}[**₹{pnl:+.2f}**]")
            if hc4.button("❌ Exit", key=f"ex_{h_name}"): execute_trade("SELL", h_name, info['qty'], cp, info['is_opt'])
    else:
        st.info("ప్రస్తుతం Holdings ఖాళీగా ఉన్నాయి.")

with page_pnl:
    st.subheader("💰 P&L Report & Trade Book")
    unreal = 0.0
    for k, v in st.session_state.holdings.items():
        if v['is_opt']:
            cp = opt_prices.get(k, v['ltp'])
        else:
            qp, _, _ = get_quote(MASTER_SYMBOLS.get(k, k))
            cp = qp if qp else v['avg']
        unreal += (cp - v['avg']) * v['qty']
    p1, p2, p3 = st.columns(3)
    p1.metric("💵 Realized P&L", f"₹ {st.session_state.realized_pnl:+.2f}")
    p2.metric("⏳ Unrealized P&L", f"₹ {unreal:+.2f}")
    p3.metric("🏆 Net P&L", f"₹ {st.session_state.realized_pnl + unreal:+.2f}")
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True, hide_index=True)
    if st.button("🔄 Reset Account (₹1,00,000)"):
        st.session_state.cash, st.session_state.holdings, st.session_state.history, st.session_state.realized_pnl = 100000.00, {}, [], 0.0
        st.rerun()

# END OF URK APP
