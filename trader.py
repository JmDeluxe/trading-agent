import csv
import os
from datetime import datetime, timedelta

import MetaTrader5 as mt5

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.csv")
_pending_reasons = {}

SYMBOLS = []  # set by main.py on startup

def set_symbols(symbols):
    global SYMBOLS
    SYMBOLS = symbols

# --- risk settings ---
LOT_SIZE = 0.01
SL_DOLLARS = 3.0      # stop loss distance in $ (gold price units)
TP_DOLLARS = 15.0     # far TP cap so winners can keep running (trailing exits first)
TRAIL_START = 2.0     # start trailing once trade is +$2
TRAIL_DOLLARS = 1.0   # trail SL $1 behind price -> locks in peak-$1
MAX_POSITIONS = 1     # don't stack trades
DAILY_LOSS_LIMIT = 6.0    # stop trading for the day after this much realized loss
COOLDOWN_MINUTES = 30     # no re-entry this long after a losing trade
_last_loss_time = None
_daily_pnl_date = None
_daily_pnl = 0.0

def risk_gate():
    """Returns (ok, reason). Checks daily loss limit + post-loss cooldown."""
    global _daily_pnl_date, _daily_pnl, _last_loss_time
    today = datetime.now().date()
    if _daily_pnl_date != today:
        _daily_pnl_date = today
        _daily_pnl = 0.0
        if _last_loss_time is not None and _last_loss_time.date() != today:
            _last_loss_time = None
    if _daily_pnl <= -DAILY_LOSS_LIMIT:
        return False, f"daily loss limit hit (today: {_daily_pnl:.2f})"
    if _last_loss_time is not None:
        elapsed = (datetime.now() - _last_loss_time).total_seconds() / 60
        if elapsed < COOLDOWN_MINUTES:
            return False, f"cooldown after loss ({COOLDOWN_MINUTES - elapsed:.0f} min left)"
    return True, ""

def record_result(deals_since_last=None):
    """Call each loop: sync realized P/L from broker history into risk state."""
    global _daily_pnl, _last_loss_time
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now) or []
    pnl = sum(d.profit for d in deals
              if d.entry == 1 and d.magic in (0, 123456) and d.symbol in SYMBOLS)
    _daily_pnl = pnl
    losses = [d for d in deals if d.entry == 1 and d.profit < 0 and d.symbol in SYMBOLS
              and d.magic in (0, 123456)]
    if losses:
        _last_loss_time = datetime.fromtimestamp(max(d.time for d in losses))

def update_trailing_stops():
    """Move SL to lock in profit once a trade is up TRAIL_START.
    For SELL: SL trails above price at TRAIL_DOLLARS distance."""
    for pos in mt5.positions_get() or []:
        if pos.magic != 123456 or pos.symbol not in SYMBOLS:
            continue
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            continue
        if pos.type == mt5.POSITION_TYPE_SELL:
            profit_dollars = pos.price_open - tick.ask
            candidate = round(tick.ask + TRAIL_DOLLARS, mt5.symbol_info(pos.symbol).digits)
            # only move SL DOWN (tighter for a short) when profit >= start
            if profit_dollars >= TRAIL_START and candidate < pos.sl:
                modify_sl(pos, candidate)
        else:
            profit_dollars = tick.bid - pos.price_open
            candidate = round(tick.bid - TRAIL_DOLLARS, mt5.symbol_info(pos.symbol).digits)
            if profit_dollars >= TRAIL_START and candidate > pos.sl:
                modify_sl(pos, candidate)

def modify_sl(pos, new_sl):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "sl": new_sl,
        "tp": pos.tp,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Trailing: {pos.symbol} SL -> {new_sl}")
    else:
        print(f"Trail failed: {result.retcode} {result.comment}")

def close_position(pos, reason):
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return
    is_buy_pos = pos.type == mt5.POSITION_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy_pos else mt5.ORDER_TYPE_BUY,
        "price": tick.bid if is_buy_pos else tick.ask,
        "deviation": 20,
        "magic": 123456,
        "comment": f"exit-{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        realized = result.profit if hasattr(result, "profit") else 0
        log_trade(pos, realized, reason)
        print(f"Closed {pos.symbol} ({reason}): P/L ${realized:.2f}")
    else:
        print(f"Close failed: {result.retcode} {result.comment}")

def log_trade(pos, profit, reason):
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["time", "symbol", "dir", "entry", "close_profit", "reason"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), pos.symbol,
                    "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    pos.price_open, f"{profit:.2f}", reason])

def check_reversal_exit():
    """Close a bot position when the SMA trend flips against it."""
    from strategy import current_trend
    for pos in mt5.positions_get() or []:
        if pos.magic != 123456 or pos.symbol not in SYMBOLS:
            continue
        trend = current_trend(pos.symbol)
        if trend is None:
            continue
        if pos.type == mt5.POSITION_TYPE_SELL and trend == "BUY":
            close_position(pos, "reversal")
        elif pos.type == mt5.POSITION_TYPE_BUY and trend == "SELL":
            close_position(pos, "reversal")

def check_trend_confirms(symbol, action):
    """Optional guard - always True for now (kept for future filters)."""
    return True

def place_order(signal):
    symbol = signal["symbol"]
    ok, reason = risk_gate()
    if not ok:
        print(f"No trade: {reason}")
        return
    if len(mt5.positions_get(symbol=symbol) or []) >= MAX_POSITIONS:
        return
    if check_trend_confirms(symbol, signal["action"]) is False:
        print(f"Skip {signal['action']}: trend confirms not met")
        return
    from strategy import market_state
    ms = market_state(symbol)
    if ms is None or not signal.get("fresh_crossover"):
        print("No trade: waiting for fresh crossover")
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    info = mt5.symbol_info(symbol)

    order_type = mt5.ORDER_TYPE_BUY if signal["action"] == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if signal["action"] == "BUY" else tick.bid

    digits = info.digits
    if signal["action"] == "BUY":
        sl = round(price - SL_DOLLARS, digits)
        tp = round(price + TP_DOLLARS, digits)
    else:
        sl = round(price + SL_DOLLARS, digits)
        tp = round(price - TP_DOLLARS, digits)

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