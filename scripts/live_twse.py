from __future__ import annotations

import json
import re
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / 'data' / 'market.json'
TZ8 = timezone(timedelta(hours=8))
MIS_URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
YAHOO_TSE_URL = 'https://tw.stock.yahoo.com/s/tse.php'

UA = {
    'User-Agent': 'Mozilla/5.0 MarketOnePage/1.4.13',
    'Referer': 'https://mis.twse.com.tw/stock/index.jsp',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.7',
}


def num(v):
    if v is None:
        return None
    s = str(v).replace(',', '').replace('%', '').replace('−', '-').strip()
    if s in ('', '-', '—'):
        return None
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None


def in_cash_session(now: datetime) -> bool:
    # TWSE regular cash market: Monday-Friday 09:00-13:30 Taipei time.
    return now.weekday() < 5 and time(9, 0) <= now.time() < time(13, 30)


def fetch_taiex_live():
    r = requests.get(
        MIS_URL,
        params={'ex_ch': 'tse_t00.tw', 'json': '1', 'delay': '0', '_': int(datetime.now().timestamp() * 1000)},
        headers=UA,
        timeout=15,
    )
    r.raise_for_status()
    obj = r.json()
    if str(obj.get('rtcode')) != '0000' or not obj.get('msgArray'):
        raise RuntimeError(f'TWSE MIS failed: {obj.get("rtmessage") or obj.get("rtcode")}')
    q = obj['msgArray'][0]
    price = num(q.get('z'))
    prev = num(q.get('y'))
    # At the first moments after open, z can briefly be '-'. Prefer pz when available.
    if price is None:
        price = num(q.get('pz'))
    if price is None or prev is None:
        raise RuntimeError('TWSE MIS live price/previous close missing')
    change = price - prev
    pct = change / prev * 100 if prev else None
    raw_date = str(q.get('d') or '')
    quote_date = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}' if len(raw_date) == 8 else None
    return {
        'price': price,
        'change': change,
        'change_pct': pct,
        'quote_date': quote_date,
        'quote_time': q.get('t'),
        'open': num(q.get('o')),
        'high': num(q.get('h')),
        'low': num(q.get('l')),
        'prev_close': prev,
        'source': 'TWSE MIS official',
        'source_url': MIS_URL,
    }


def fetch_intraday_market_stats(expected_date: str | None):
    """Best-effort intraday turnover/breadth from Yahoo's Taiwan market overview.

    If Yahoo serves only a JS shell to the GitHub runner, return None rather than
    overwriting the last verified TWSE close statistics with fabricated values.
    """
    r = requests.get(YAHOO_TSE_URL, headers={**UA, 'Referer': 'https://tw.stock.yahoo.com/'}, timeout=15)
    r.raise_for_status()
    text = BeautifulSoup(r.text, 'html.parser').get_text(' ', strip=True)

    turnover = None
    for pat in (
        r'成交金額\s*([\d,]+(?:\.\d+)?)\s*億',
        r'成交\s*金額\s*([\d,]+(?:\.\d+)?)\s*億',
    ):
        m = re.search(pat, text)
        if m:
            turnover = num(m.group(1))
            break

    def first_count(label):
        # Yahoo's overview commonly renders e.g. 漲家數 423/18 (total/limit-up).
        m = re.search(label + r'\s*([\d,]+)\s*(?:/\s*[\d,]+)?', text)
        return int(num(m.group(1))) if m and num(m.group(1)) is not None else None

    up = first_count('漲家數')
    down = first_count('跌家數')
    flat = first_count('平家數')

    if turnover is None and (up is None or down is None):
        return None
    if turnover is not None and not (0 <= turnover <= 30000):
        turnover = None
    directional = (up or 0) + (down or 0)
    return {
        'date': expected_date,
        'turnover_100m_twd': turnover,
        'turnover_twd': round(turnover * 100_000_000) if turnover is not None else None,
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if up is not None and directional else None,
        'decline_pct': round(down / directional * 100, 1) if down is not None and directional else None,
        'session': 'intraday',
        'turnover_source': 'Yahoo股市盤中大盤',
        'breadth_source': 'Yahoo股市盤中大盤',
    }


def main():
    now = datetime.now(TZ8)
    if not in_cash_session(now):
        print('TWSE live overlay skipped: outside 09:00-13:30 cash session')
        return

    market = json.loads(MARKET.read_text(encoding='utf-8'))
    live = fetch_taiex_live()
    if live.get('quote_date') != now.strftime('%Y-%m-%d'):
        raise RuntimeError(f'TWSE MIS returned stale date: {live.get("quote_date")}')

    taiwan = market.get('taiwan') or []
    row = next((x for x in taiwan if x.get('symbol') == '^TWII'), None)
    if row is None:
        row = {'symbol': '^TWII', 'name': '台灣加權指數', 'decimals': 2, 'spark': []}
        taiwan.insert(0, row)
    row.update({k: v for k, v in live.items() if k not in ('source_url',)})
    spark = [x for x in (row.get('spark') or []) if isinstance(x, (int, float))]
    if not spark or abs(spark[-1] - live['price']) > 1e-9:
        spark.append(live['price'])
    row['spark'] = spark[-48:]
    market['taiwan'] = taiwan

    stats = market.get('taiwan_stats') or {}
    intraday = None
    try:
        intraday = fetch_intraday_market_stats(live.get('quote_date'))
    except Exception as e:
        print('Yahoo intraday market stats unavailable:', e)

    if intraday:
        # Only overwrite fields actually observed. Preserve last verified close for missing ones.
        for key, value in intraday.items():
            if value is not None:
                stats[key] = value
        stats['session'] = 'intraday'
        stats['live_stats'] = True
    else:
        # Keep yesterday's complete close figures and label them truthfully.
        stats['session'] = 'previous_close'
        stats['live_stats'] = False
    market['taiwan_stats'] = stats
    market['as_of'] = datetime.now(timezone.utc).isoformat()
    market['taiwan_live'] = {
        'session': 'cash_open',
        'quote_time': live.get('quote_time'),
        'quote_date': live.get('quote_date'),
        'source': 'TWSE MIS official',
        'stats_live': bool(intraday),
    }
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'TWSE live overlay: {live["quote_date"]} {live.get("quote_time")} '
        f'TAIEX={live["price"]:.2f} change={live["change"]:+.2f} ({live["change_pct"]:+.2f}%) '
        f'stats_live={bool(intraday)}'
    )


if __name__ == '__main__':
    main()
