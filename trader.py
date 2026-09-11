import MetaTrader5 as mt5

# --- risk settings ---
LOT_SIZE = 0.01
SL_POINTS = 200      # stop loss in points
TP_POINTS = 400      # take profit in points
MAX_POSITIONS = 1    # don't stack trades

def place_order(signal):
    symbol = signal["symbol"]
    if len(mt5.positions_get(symbol=symbol) or []) >= MAX_POSITIONS:
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    order_type = mt5.ORDER_TYPE_BUY if signal["action"] == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if signal["action"] == "BUY" else tick.bid
    point = mt5.symbol_info(symbol).point
    sl = price - SL_POINTS * point if signal["action"] == "BUY" else price + SL_POINTS * point
    tp = price + TP_POINTS * point if signal["action"] == "BUY" else price - TP_POINTS * point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 123456,
        "comment": "hybrid-agent",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.retcode} {result.comment}")
    else:
        print(f"Order placed: {signal['action']} {symbol} @ {price}")