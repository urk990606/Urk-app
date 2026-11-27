ltp = get_ltp(bot_sym)
    df_bot = add_ema_vwap(get_data(bot_sym, bot_tf))

    if ltp is not None:
        # 1. ముందుగా ACTIVE TRADE & MANUAL EXIT పైనే కనిపించేలా పెట్టాము!
        if isinstance(ud.get("bot_pos"), dict):
            p = ud["bot_pos"]
            pltp = get_ltp(p["sym"]) or ltp
            if ud["bot_on"] and u_tr and pltp > p.get("hi", p["entry"]):
                diff = round(pltp - p.get("hi", p["entry"]), 2)
                if diff >= 0.5:
                    ud["bot_pos"]["hi"] = pltp
                    ud["bot_pos"]["sl"] = round(p["sl"] + diff, 2)
                    p = ud["bot_pos"]

            rpnl = round((pltp - p["entry"]) * p["qty"], 2)
            st.success(f"✅ **ACTIVE ORDER:** {p['sym']} | Qty: {p['qty']} | Entry: ₹{p['entry']} | LTP: ₹{pltp}")
            st.info(f"{'🟢' if rpnl>=0 else '🔴'} **SL:** ₹{p['sl']} | **TGT:** ₹{p['tgt']} | **Live P&L: ₹{rpnl:+,.2f}**")

            if st.button("🚨 EXIT TRADE NOW (Manual Exit)", type="primary", use_container_width=True):
                ud["rpnl"] = round(ud["rpnl"] + rpnl, 2)
                ud["cash"] = round(ud["cash"] + pltp * p["qty"], 2)
                ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": p["sym"], "Type": "MANUAL-EXIT", "Qty": p["qty"], "Price": pltp, "P&L": rpnl})
                ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] 🚨 MANUAL EXIT {p['sym']} @ ₹{pltp} | P&L: ₹{rpnl:+,.2f}")
                ud["bot_pos"], ud["sound"] = None, "exit"
                st.rerun()

            if ud["bot_on"]:
                reason = "SL HIT" if pltp <= p["sl"] else ("TARGET HIT" if pltp >= p["tgt"] else ("SQUARE-OFF" if curr_t >= sq_t else None))
                if reason:
                    ud["rpnl"] = round(ud["rpnl"] + rpnl, 2)
                    ud["cash"] = round(ud["cash"] + pltp * p["qty"], 2)
                    ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": p["sym"], "Type": reason, "Qty": p["qty"], "Price": pltp, "P&L": rpnl})
                    ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] 🔔 {reason}: {p['sym']} @ ₹{pltp} | P&L: ₹{rpnl:+,.2f}")
                    ud["bot_pos"], ud["sound"] = None, "exit"
                    st.rerun()

        # 2. ఆ తర్వాత Live LTP, 9 EMA, VWAP మెట్రిక్స్ చూపిస్తుంది
        cond_ok = False
        if not df_bot.empty and "EMA9" in df_bot.columns:
            e9_val = round(float(df_bot["EMA9"].iloc[-1]), 2)
            vw_val = round(float(df_bot["VWAP"].iloc[-1]), 2)
            cond_ok = (ltp > e9_val) and (ltp > vw_val)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Live LTP", f"₹{ltp}")
            m2.metric("9 EMA", f"₹{e9_val}")
            m3.metric("VWAP", f"₹{vw_val}")
            m4.metric("Signal", "🟢 IN TRADE" if isinstance(ud.get("bot_pos"), dict) else ("🟢 BUY READY" if cond_ok else "⏳ WAIT"))
        else:
            st.metric("Live LTP", f"₹{ltp}")

        # 3. NEW ENTRY LOGIC
        if not isinstance(ud.get("bot_pos"), dict) and ud["bot_on"] and in_win and ud["trades_today"] < max_tr and cond_ok:
            cost = round(ltp * bot_qty, 2)
            if ud["cash"] >= cost:
                ud["cash"] = round(ud["cash"] - cost, 2)
                ud["bot_pos"] = {
                    "sym": bot_sym,
                    "qty": bot_qty,
                    "entry": ltp,
                    "hi": ltp,
                    "sl": round(ltp - sl_pts, 2),
                    "tgt": round(ltp + tgt_pts, 2),
                }
                ud["trades_today"] += 1
                ud["hist"].append({"Time": now_ist.strftime("%H:%M:%S"), "Asset": bot_sym, "Type": "EMA-VWAP-BUY", "Qty": bot_qty, "Price": ltp, "P&L": 0.0})
                ud["bot_logs"].append(f"[{now_ist.strftime('%H:%M:%S')}] 🟢 BUY {bot_sym} x{bot_qty} @ ₹{ltp} (LTP > 9EMA & VWAP)")
                ud["sound"] = "buy"
                st.rerun()
            else:
                st.warning(f"⚠️ Insufficient Cash! Need ₹{cost:,.2f}, Available ₹{ud['cash']:,.2f}")
