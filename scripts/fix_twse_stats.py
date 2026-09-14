from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import update_market as u

DATA = Path(__file__).resolve().parents[1] / 'data'
MARKET = DATA / 'market.json'
MI_INDEX_URL = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
YAHOO_TSE_URL = 'https://tw.stock.yahoo.com/s/tse.php'


def num(v):
    if v is None:
        return None
    s = str(v).replace(',', '').replace('%', '').replace('−', '-').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None


def normalize_date(raw):
    s = str(raw or '').strip().replace('-', '/')
    m = re.fullmatch(r'(\d{3,4})/(\d{1,2})/(\d{1,2})', s)
    if not m:
        return None
    year, month, day = map(int, m.groups())
    if year < 1911:
        year += 1911
    try:
        return datetime(year, month, day).strftime('%Y-%m-%d')
    except ValueError:
        return None


def twse_tables(date_text):
    r = u.get_http(
        MI_INDEX_URL,
        params={'date': date_text.replace('-', ''), 'type': 'ALLBUT0999', 'response': 'json'},
    )
    obj = r.json()
    if str(obj.get('stat', '')).upper() != 'OK':
        raise RuntimeError(f'TWSE MI_INDEX not OK: {obj.get("stat")}')
    return obj.get('tables') or []


def yahoo_regular_session_turnover(date_text):
    """Return the cash-market close turnover shown on Yahoo Taiwan's TSE page.

    This is intentionally the regular-session market headline amount used by
    Taiwan market pages/news. It does NOT use TWSE FMTQIK because FMTQIK adds
    after-hours/odd-lot/block components and therefore produces a larger number
    than the 13:30 close headline the dashboard is meant to show.
    """
    r = u.get_http(YAHOO_TSE_URL)
    soup = u.BeautifulSoup(r.text, 'html.parser')
    text = soup.get_text(' ', strip=True)

    # Prefer an explicit yyyy/mm/dd date on the page when available.
    dates = re.findall(r'20\d{2}/\d{1,2}/\d{1,2}', text)
    if dates:
        normalized = {normalize_date(x) for x in dates}
        if date_text not in normalized:
            raise RuntimeError(f'Yahoo TSE page date does not match {date_text}: {sorted(x for x in normalized if x)}')

    # Yahoo pages use wording such as 成交金額 6,309.17 億 or 成交6309.17億.
    patterns = [
        r'成交金額\s*([\d,]+(?:\.\d+)?)\s*億',
        r'成交\s*([\d,]+(?:\.\d+)?)\s*億',
    ]
    values = []
    for pat in patterns:
        for raw in re.findall(pat, text):
            v = num(raw)
            if v is not None and 100 <= v <= 30000:
                values.append(v)
    if not values:
        raise RuntimeError('Yahoo TSE regular-session turnover not found')

    # The first explicit 成交金額 figure is the market headline. Avoid summing
    # anything; summing categories was the source of the previous 6,653.16 error.
    return round(values[0], 2)


def stock_breadth(tables):
    """Read listed-stock up/down/flat counts from the TWSE breadth table.

    The dashboard label says 個股, so use the 股票 column, not 整體市場.
    The overall-market column includes ETF/warrant/etc. and can be in the
    thousands, which caused the incorrect 3,983 / 8,508 display.
    """
    for table in tables:
        rows = table.get('data') or []
        if not rows:
            continue
        labels = [str(row[0]).replace(' ', '') for row in rows if row]
        if not any(x.startswith('上漲') for x in labels) or not any(x.startswith('下跌') for x in labels):
            continue

        fields = [str(x).replace(' ', '') for x in (table.get('fields') or [])]
        stock_idx = next((i for i, f in enumerate(fields) if f == '股票' or f.endswith('股票')), None)
        if stock_idx is None:
            # Current TWSE layout: 類型 / 整體市場 / 股票
            stock_idx = 2 if len(fields) > 2 else None
        if stock_idx is None:
            continue

        up = down = flat = None
        for row in rows:
            if not row or stock_idx >= len(row):
                continue
            label = str(row[0]).replace(' ', '')
            value = num(row[stock_idx])
            if label.startswith('上漲'):
                up = int(value) if value is not None else None
            elif label.startswith('下跌'):
                down = int(value) if value is not None else None
            elif label.startswith('持平'):
                flat = int(value) if value is not None else None

        if up is not None and down is not None:
            return up, down, flat

    raise RuntimeError('TWSE MI_INDEX stock breadth table not found')


def main():
    market = json.loads(MARKET.read_text(encoding='utf-8'))
    stats = market.get('taiwan_stats') or {}
    date_text = stats.get('date') or next(
        (x.get('quote_date') for x in market.get('taiwan', []) if x.get('quote_date')),
        None,
    )
    if not date_text:
        raise RuntimeError('Taiwan trade date missing from market.json')
    date_text = datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y-%m-%d')

    # Do not overwrite with FMTQIK totals. The dashboard wants the regular cash
    # session headline amount shown at/after the close.
    turnover_100m = yahoo_regular_session_turnover(date_text)
    up, down, flat = stock_breadth(twse_tables(date_text))

    directional = up + down
    stats.update({
        'turnover_100m_twd': turnover_100m,
        'turnover_twd': round(turnover_100m * 100_000_000),
        'turnover_method': 'Yahoo Taiwan TSE regular-session headline; exact trade date',
        'turnover_trade_date': date_text,
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if directional else None,
        'decline_pct': round(down / directional * 100, 1) if directional else None,
        'breadth_scope': 'listed_stocks',
        'turnover_source': 'Yahoo股市',
        'breadth_source': 'TWSE MI_INDEX 股票欄',
        'source': 'TWSE official MI_INDEX + Yahoo Taiwan regular-session turnover',
    })

    market['taiwan_stats'] = stats
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'Taiwan close verified: date={date_text} turnover={turnover_100m}億元 '
        f'listed-stock breadth up={up} down={down} flat={flat}'
    )


if __name__ == '__main__':
    main()
