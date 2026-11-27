with t2:
    st.subheader("📊 Pro Chart & UT Signals")
    cc1, cc2, cc3 = st.columns((2, 1, 1))
    c_sym = cc1.selectbox("Chart Asset:", stocks, key="chart_sym")
    c_tf = cc2.selectbox("Chart TF:", ["3m", "5m", "15m", "1D"], index=1, key="chart_tf")
    c_ha = cc3.checkbox("Heikin Ashi Chart", value=True, key="chart_ha")

    cdf = calc_famous_ut_bot(get_data(c_sym, c_tf), ut_key, ut_atr, c_ha)
    if not cdf.empty:
        # చివరి 80 క్యాండిల్స్ మాత్రమే క్లీన్‌గా జూమ్ చేసి చూపిస్తుంది
        cdf_view = cdf.tail(80).copy()
        x_labels = cdf_view.index.strftime("%d %b %H:%M") if c_tf != "1D" else cdf_view.index.strftime("%d %b %Y")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=x_labels,
            open=cdf_view["Open"],
            high=cdf_view["High"],
            low=cdf_view["Low"],
            close=cdf_view["Close"],
            name="Price"
        ))

        if "UT_Trail" in cdf_view.columns:
            fig.add_trace(go.Scatter(
                x=x_labels,
                y=cdf_view["UT_Trail"],
                mode="lines",
                name="UT Stop Line",
                line=dict(color="orange", width=2)
            ))
            buys = cdf_view[cdf_view["Buy_Signal"]]
            sells = cdf_view[cdf_view["Sell_Signal"]]
            if not buys.empty:
                b_x = buys.index.strftime("%d %b %H:%M") if c_tf != "1D" else buys.index.strftime("%d %b %Y")
                fig.add_trace(go.Scatter(x=b_x, y=buys["Low"] * 0.999, mode="markers", name="BUY", marker=dict(symbol="triangle-up", size=14, color="lime")))
            if not sells.empty:
                s_x = sells.index.strftime("%d %b %H:%M") if c_tf != "1D" else sells.index.strftime("%d %b %Y")
                fig.add_trace(go.Scatter(x=s_x, y=sells["High"] * 1.001, mode="markers", name="SELL", marker=dict(symbol="triangle-down", size=14, color="red")))

        fig.update_layout(
            height=480,
            xaxis_rangeslider_visible=False,
            xaxis=dict(type="category", nticks=8),
            template="plotly_dark",
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ ఈ స్టాక్‌కు ప్రస్తుతం Yahoo Finance నుండి డేటా రాలేదు. వేరే TF (5m లేదా 15m) ప్రయత్నించండి.")
