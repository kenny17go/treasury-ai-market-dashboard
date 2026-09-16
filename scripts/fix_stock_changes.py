from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
STOCKS_PATH = ROOT / 'data' / 'stocks.json'
ET = ZoneInfo('America/New_York')


def clean(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def index_date(idx):
    """Return a yfinance timestamp as an America/New_York calendar date."""
    try:
        ts = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
        if getattr(ts, 'tzinfo', None) is None:
            return ts.date()
        return ts.astimezone(ET).date()
    except Exception:
        return None


def corrected_quote(symbol):
    ticker = yf.Ticker(symbol)

    # Use regular-session intraday data for the displayed price and its actual
    # trading date. This avoids guessing whether Yahoo has already appended
    # today's daily candle.
    intraday = ticker.history(
        period='5d', interval='30m', auto_adjust=False,
        prepost=False, timeout=15,
    )
    if intraday is None or intraday.empty or 'Close' not in intraday:
        return None

    intraday = intraday.dropna(subset=['Close'])
    if intraday.empty:
        return None

    price = clean(intraday['Close'].iloc[-1])
    price_date = index_date(intraday.index[-1])
    if price is None or price_date is None:
        return None

    daily = ticker.history(
        period='10d', interval='1d', auto_adjust=False,
        prepost=False, timeout=15,
    )
    if daily is None or daily.empty or 'Close' not in daily:
        return None

    rows = []
    for idx, value in daily['Close'].items():
        d = index_date(idx)
        v = clean(value)
        if d is not None and v is not None:
            rows.append((d, v))
    rows.sort(key=lambda x: x[0])

    # Correct reference-close rule:
    # - If Yahoo daily already contains the price date, use the session before it.
    # - If Yahoo daily has NOT appended the price date yet, its latest older row
    #   is itself the previous official close.
    older = [(d, v) for d, v in rows if d < price_date]
    if not older:
        return None
    prev_date, prev_close = older[-1]

    change = price - prev_close
    pct = change / prev_close * 100 if prev_close else None
    spark = [clean(v) for v in intraday['Close'].tolist()]
    spark = [v for v in spark if v is not None][-48:]

    return {
        'price': price,
        'change': change,
        'change_pct': pct,
        'spark': spark,
        'price_date': price_date.isoformat(),
        'prev_close': prev_close,
        'prev_close_date': prev_date.isoformat(),
    }


def main():
    if not STOCKS_PATH.exists():
        raise SystemExit('data/stocks.json not found')

    obj = json.loads(STOCKS_PATH.read_text(encoding='utf-8'))
    fixed = 0
    failed = []

    for stock in obj.get('stocks', []):
        symbol = stock.get('symbol')
        if not symbol:
            continue
        try:
            q = corrected_quote(symbol)
            if not q:
                failed.append(symbol)
                continue
            stock.update(q)
            fixed += 1
        except Exception as exc:
            print('stock change correction failed', symbol, exc)
            failed.append(symbol)

    obj['as_of'] = datetime.now(timezone.utc).isoformat()
    obj['source'] = 'Yahoo Finance via yfinance; change vs prior official regular-session close'
    obj['change_basis'] = 'previous official regular-session close matched by trading date'
    obj['change_fix_count'] = fixed
    if failed:
        obj['change_fix_failed'] = failed
    else:
        obj.pop('change_fix_failed', None)

    STOCKS_PATH.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'Corrected {fixed} stock quotes; failed={failed}')


if __name__ == '__main__':
    main()
