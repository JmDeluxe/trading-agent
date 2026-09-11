import time
import schedule
import MetaTrader5 as mt5
from strategy import check_signal, market_state
from trader import place_order, update_trailing_stops, set_symbols, check_reversal_exit, record_result, risk_gate
from llm_brain import review_market

SYMBOL = "XAUUSDm"
LOOP_SECONDS = 60

def run_loop():
    mt5.initialize()
    if not mt5.account_info():
        raise RuntimeError("MT5 connection failed - is the terminal running?")
    set_symbols([SYMBOL])

    schedule.every(1).hours.do(review_market)

    print("Agent running. Ctrl+C to stop.")
    try:
        while True:
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                print(f"[{time.strftime('%H:%M:%S')}] {SYMBOL} not found - check exact symbol name in Market Watch (e.g. XAUUSDm)")
            else:
                positions = mt5.positions_get(symbol=SYMBOL) or []
                pos_txt = ""
                if positions:
                    p = positions[0]
                    pos_txt = f" | SL={p.sl} TP={p.tp} P/L=${p.profit:.2f}"
                else:
                    ms = market_state(SYMBOL)
                    if ms:
                        mode = "CHOPPY-skip" if ms["choppy"] else f"trend={ms['trend']}"
                        pos_txt = f" | {mode} gap={ms['spread']:.3f} atr={ms['atr']:.3f}"
                    ok, block_reason = risk_gate()
                    if not ok:
                        pos_txt = f" | IDLE: {block_reason}"
                print(f"[{time.strftime('%H:%M:%S')}] {SYMBOL} bid={tick.bid} ask={tick.ask} open={len(positions)}{pos_txt}")
                update_trailing_stops()
                check_reversal_exit()
                record_result()
                signal = check_signal(SYMBOL)
                if signal:
                    print(f"Signal: {signal}")
                    place_order(signal)
            schedule.run_pending()
            time.sleep(LOOP_SECONDS)
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run_loop()