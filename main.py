import time
import schedule
import MetaTrader5 as mt5
from strategy import check_signal
from trader import place_order, close_positions_at_eod
from llm_brain import review_market

SYMBOL = "XAUUSD"
LOOP_SECONDS = 60

def run_loop():
    mt5.initialize()
    if not mt5.account_info():
        raise RuntimeError("MT5 connection failed - is the terminal running?")

    schedule.every(1).hours.do(review_market)

    print("Agent running. Ctrl+C to stop.")
    try:
        while True:
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