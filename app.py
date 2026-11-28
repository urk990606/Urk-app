ud["bot_pos"] = {
                    "sym": sym,
                    "qty": qty,
                    "entry": ltp,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "time": now_ist.strftime("%H:%M:%S"),
                    "buy_ts": df_ch.index[-1] if not df_ch.empty else now_ist
                }
                ud["last_action_ts"] = now_ts
                ud["sound"] = "buy"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🟢 BUY: {qty} {sym} @ ₹{ltp:,.2f} (SL: ₹{sl_price}, TP: ₹{tp_price})")
                st.rerun()
            else:
                st.error("Insufficient Cash!")

        # 2. SELL ACTION (Stop-Loss, Target Profit లేదా Time Expired)
        elif has_pos:
            bp = ud["bot_pos"]
            exit_reason = None
            if ltp <= bp["sl_price"]:
                exit_reason = "🛑 STOP-LOSS HIT"
            elif ltp >= bp["tp_price"]:
                exit_reason = "🎯 TARGET HIT"
            elif elapsed >= interval_sec:
                exit_reason = "⏰ TIME EXIT"

            if exit_reason:
                pnl = round((ltp - bp["entry"]) * bp["qty"], 2)
                ud["cash"] = round(ud["cash"] + (ltp * bp["qty"]), 2)
                ud["rpnl"] = round(ud["rpnl"] + pnl, 2)
                ud["hist"].insert(0, {
                    "Asset": bp["sym"],
                    "Qty": bp["qty"],
                    "Buy Price (₹)": bp["entry"],
                    "Sell Price (₹)": ltp,
                    "P&L (₹)": f"{pnl:+,.2f}",
                    "Reason": exit_reason,
                    "Buy Time": bp["time"],
                    "Sell Time": now_ist.strftime("%H:%M:%S"),
                    "buy_ts": bp["buy_ts"],
                    "sell_ts": df_ch.index[-1] if not df_ch.empty else now_ist
                })
                ud["bot_pos"] = None
                ud["last_action_ts"] = now_ts
                ud["sound"] = "sell"
                ud["bot_logs"].insert(0, f"[{now_ist.strftime('%H:%M:%S')}] 🔴 SELL ({exit_reason}): {bp['qty']} {bp['sym']} @ ₹{ltp:,.2f} | P&L: ₹{pnl:+,.2f}")
                st.rerun()

    time.sleep(1)
    st.rerun()

# ---------------- TRADE HISTORY & LOGS ----------------
st.divider()
tab1, tab2 = st.tabs(["📜 Trade History (ట్రేడ్ హిస్టరీ)", "🤖 Bot Logs (లాగ్స్)"])

with tab1:
    if ud["hist"]:
        disp_df = pd.DataFrame(ud["hist"]).drop(columns=["buy_ts", "sell_ts"], errors="ignore")
        st.dataframe(disp_df, use_container_width=True, hide_index=True)
    else:
        st.info("ఇంకా ఎలాంటి ట్రేడ్స్ పూర్తి కాలేదు.")

with tab2:
    if ud["bot_logs"]:
        for log in ud["bot_logs"][:30]:
            st.text(log)
    else:
        st.info("లాగ్స్ ఖాళీగా ఉన్నాయి.")
