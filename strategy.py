import MetaTrader5 as mt5

CHOPPY_FACTOR = 0.5   # min SMA gap as fraction of ATR - below this = too choppy to trade

def sma(rates, period):
    closes = [r["close"] for r in rates]
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def atr(rates, period=14):
    """Average size of price movement per bar - our 'volatility ruler'."""
    trs = []
    for i in range(1, len(rates)):
        high = rates[i]["high"]
        low = rates[i]["low"]
        prev_close = rates[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period

def market_state(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    if rates is None or len(rates) < 50:
        return None
    fast = sma(rates, 20)
    slow = sma(rates, 50)
    a = atr(rates, 14)
    if fast is None or slow is None or a is None:
        return None
    spread = fast - slow
    trend = "BUY" if spread > 0 else ("SELL" if spread < 0 else None)
    choppy = abs(spread) < CHOPPY_FACTOR * a
    return {"trend": trend, "spread": spread, "atr": a, "choppy": choppy}

def current_trend(symbol):
    s = market_state(symbol)
    return s["trend"] if s else None

def check_signal(symbol):
    """Signal only on a FRESH crossover: previous M15 bar had no trend
    (inside the choppy/no-trade zone), current bar has one."""
    s = market_state(symbol)
    if s is None or s["trend"] is None or s["choppy"]:
        return None
    # was the previous bar inside the dead zone?
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 51)
    if rates is None or len(rates) < 51:
        return None
    prev_rates = rates[:-1]
    fast_p = sma(prev_rates, 20)
    slow_p = sma(prev_rates, 50)
    if fast_p is None or slow_p is None:
        return None
    prev_spread = fast_p - slow_p
    prev_trend = "BUY" if prev_spread > 0 else ("SELL" if prev_spread < 0 else None)
    was_choppy = abs(prev_spread) < CHOPPY_FACTOR * s["atr"]
    if was_choppy or prev_trend is None or prev_trend == s["trend"]:
        return None
    return {"action": s["trend"], "symbol": symbol, "fresh_crossover": True}