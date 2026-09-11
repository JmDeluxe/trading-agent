import MetaTrader5 as mt5

def sma(rates, period):
    closes = [r["close"] for r in rates]
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def check_signal(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50:
        return None
    fast = sma(rates, 20)
    slow = sma(rates, 50)
    if fast is None or slow is None:
        return None
    if fast > slow:
        return {"action": "BUY", "symbol": symbol}
    if fast < slow:
        return {"action": "SELL", "symbol": symbol}
    return None