from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import update_market as u

DATA = Path(__file__).resolve().parents[1] / 'data'
MARKET = DATA / 'market.json'
FMTQIK_URL = 'https://www.twse.com.tw/exchangeReport/FMTQIK'
MI_INDEX_URL = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'


def num(v):
    if v is None:
        return None
    s = str(v).replace(',', '').replace('%', '').replace('−', '-').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None


def normalize_twse_date(raw):
    """Normalize TWSE dates such as 115/09/14 or 2026/09/14 to YYYY-MM-DD."""
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


def field_index(fields, keyword):
    for i, f in enumerate(fields or []):
        if keyword in str(f).replace(' ', ''):
            return i
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


def _fmtqik_json_turnover(date_text):
    """Read the exact trading-date row from official FMTQIK JSON.

    Important: do not sum MI_INDEX security-category rows. Those categories are
    not guaranteed to be mutually exclusive with the official market headline
    definition, which previously produced 6,653.16 億 instead of 6,309.17 億.
    """
    r = u.get_http(FMTQIK_URL, params={'response': 'json', 'date': date_text.replace('-', '')})
    obj = r.json()
    fields = obj.get('fields') or []
    value_idx = field_index(fields, '成交金額')
    if value_idx is None:
        value_idx = 2  # documented FMTQIK order: 日期/成交股數/成交金額/...

    arrays = []
    if isinstance(obj.get('data'), list):
        arrays.append(obj['data'])
    for key, value in obj.items():
        if key != 'data' and key.startswith('data') and isinstance(value, list):
            arrays.append(value)

    for rows in arrays:
        for row in rows:
            if not row or normalize_twse_date(row[0]) != date_text:
                continue
            if value_idx >= len(row):
                continue
            value = num(row[value_idx])
            if value is not None:
                return value
    return None


def _fmtqik_html_turnover(date_text):
    """Second official-source parser for the same FMTQIK report."""
    r = u.get_http(FMTQIK_URL, params={'response': 'html', 'date': date_text.replace('-', '')})
    soup = u.BeautifulSoup(r.text, 'html.parser')
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        header = [x.get_text(' ', strip=True).replace(' ', '') for x in rows[0].find_all(['th', 'td'])]
        value_idx = next((i for i, x in enumerate(header) if '成交金額' in x), None)
        if value_idx is None:
            continue
        for tr in rows[1:]:
            cells = [x.get_text(' ', strip=True) for x in tr.find_all(['th', 'td'])]
            if not cells or normalize_twse_date(cells[0]) != date_text or value_idx >= len(cells):
                continue
            value = num(cells[value_idx])
            if value is not None:
                return value
    return None


def fmtqik_turnover(date_text):
    value = _fmtqik_json_turnover(date_text)
    if value is not None:
        return value, 'FMTQIK JSON exact-date row'
    value = _fmtqik_html_turnover(date_text)
    if value is not None:
        return value, 'FMTQIK HTML exact-date row'
    raise RuntimeError(f'TWSE FMTQIK exact-date turnover missing for {date_text}')


def market_breadth(tables):
    """Read the official close headline up/down counts from MI_INDEX.

    TWSE breadth tables commonly expose 類型 / 整體市場 / 股票. The published
    market-close headline count for 2026-09-14 is 341 up / 674 down, which is
    the 整體市場 column. The narrower 股票 column was 332 / 665 and was the
    reason the previous display differed from the official closing summary.
    """
    for table in tables:
        rows = table.get('data') or []
        if not rows:
            continue
        labels = [str(row[0]).replace(' ', '') for row in rows if row]
        if not any(x.startswith('上漲') for x in labels) or not any(x.startswith('下跌') for x in labels):
            continue

        fields = [str(x).replace(' ', '') for x in (table.get('fields') or [])]
        overall_idx = next((i for i, f in enumerate(fields) if '整體市場' in f), None)
        if overall_idx is None:
            overall_idx = 1 if len(fields) > 1 else None
        if overall_idx is None:
            continue

        up = down = flat = None
        for row in rows:
            if not row or overall_idx >= len(row):
                continue
            label = str(row[0]).replace(' ', '')
            value = num(row[overall_idx])
            if label.startswith('上漲'):
                up = int(value) if value is not None else None
            elif label.startswith('下跌'):
                down = int(value) if value is not None else None
            elif label.startswith('持平'):
                flat = int(value) if value is not None else None

        if up is not None and down is not None:
            return up, down, flat

    raise RuntimeError('TWSE MI_INDEX overall-market breadth table not found')


def main():
    market = json.loads(MARKET.read_text(encoding='utf-8'))
    stats = market.get('taiwan_stats') or {}
    date_text = stats.get('date') or next(
        (x.get('quote_date') for x in market.get('taiwan', []) if x.get('quote_date')),
        None,
    )
    if not date_text:
        raise RuntimeError('Taiwan trade date missing from market.json')

    # Guard against silently applying a monthly or adjacent-date value.
    date_text = datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y-%m-%d')
    turnover, turnover_method = fmtqik_turnover(date_text)
    up, down, flat = market_breadth(twse_tables(date_text))

    turnover_100m = round(turnover / 100_000_000, 2)
    if not (100 <= turnover_100m <= 30_000):
        raise RuntimeError(f'TWSE turnover sanity check failed: {turnover_100m} 億元')

    directional = up + down
    stats.update({
        'turnover_twd': turnover,
        'turnover_100m_twd': turnover_100m,
        'turnover_method': turnover_method,
        'turnover_trade_date': date_text,
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if directional else None,
        'decline_pct': round(down / directional * 100, 1) if directional else None,
        'breadth_scope': 'overall_market',
        'source': 'TWSE official FMTQIK + MI_INDEX',
        'source_url': FMTQIK_URL,
    })

    market['taiwan_stats'] = stats
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'TWSE verified: date={date_text} turnover={turnover_100m}億元 '
        f'({turnover_method}) up={up} down={down} flat={flat}'
    )


if __name__ == '__main__':
    main()
