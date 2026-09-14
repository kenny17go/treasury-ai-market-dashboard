from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import update_market as u

DATA = Path(__file__).resolve().parents[1] / 'data'
MARKET = DATA / 'market.json'


def num(v):
    if v is None:
        return None
    s = str(v).replace(',', '').replace('%', '').replace('−', '-').strip()
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None


def field_index(fields, keyword):
    for i, f in enumerate(fields or []):
        if keyword in str(f).replace(' ', ''):
            return i
    return None


def twse_tables(date_text):
    url = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
    r = u.get_http(
        url,
        params={'date': date_text.replace('-', ''), 'type': 'ALLBUT0999', 'response': 'json'},
    )
    obj = r.json()
    if str(obj.get('stat', '')).upper() != 'OK':
        raise RuntimeError(f'TWSE MI_INDEX not OK: {obj.get("stat")}')
    return obj.get('tables') or []


def fmtqik_turnover(date_text):
    """Return official total market turnover from TWSE FMTQIK.

    FMTQIK is the official daily market-statistics series and its 成交金額 is
    the full market total used by TWSE/CNA market-close reports. This avoids
    accidentally showing the 1.一般股票 subtotal.
    """
    dt = datetime.strptime(date_text, '%Y-%m-%d')
    roc_date = f'{dt.year - 1911:03d}/{dt.month:02d}/{dt.day:02d}'
    r = u.get_http(
        'https://www.twse.com.tw/exchangeReport/FMTQIK',
        params={'response': 'json', 'date': dt.strftime('%Y%m%d')},
    )
    obj = r.json()
    for row in obj.get('data') or []:
        if row and str(row[0]).strip() == roc_date and len(row) >= 3:
            value = num(row[2])
            if value is not None:
                return value
    return None


def mi_index_total_turnover(tables):
    """Fallback: read the explicit 總計(1~15) row from MI_INDEX."""
    for table in tables:
        fields = table.get('fields') or []
        vi = field_index(fields, '成交金額')
        if vi is None:
            continue
        for row in table.get('data') or []:
            if not row or vi >= len(row):
                continue
            label = str(row[0]).replace(' ', '')
            if label.startswith('總計'):
                value = num(row[vi])
                if value is not None:
                    return value
    return None


def stock_breadth(tables):
    """Read listed-stock up/down/flat counts from TWSE breadth table.

    TWSE currently provides rows such as 上漲(漲停), 下跌(跌停), 持平 and
    columns 類型 / 整體市場 / 股票. We explicitly use the 股票 column.
    Values may look like 341(12), so only the leading count is parsed.
    """
    for table in tables:
        rows = table.get('data') or []
        if not rows:
            continue
        labels = [str(row[0]).replace(' ', '') for row in rows if row]
        if not any(x.startswith('上漲') for x in labels):
            continue
        if not any(x.startswith('下跌') for x in labels):
            continue

        fields = [str(x).replace(' ', '') for x in (table.get('fields') or [])]
        stock_idx = next((i for i, f in enumerate(fields) if f == '股票' or f.endswith('股票')), None)
        if stock_idx is None:
            # Current TWSE layout is 類型 / 整體市場 / 股票.
            stock_idx = 2

        up = down = flat = None
        for row in rows:
            if not row:
                continue
            label = str(row[0]).replace(' ', '')
            if stock_idx >= len(row):
                continue
            value = num(row[stock_idx])
            if label.startswith('上漲'):
                up = int(value) if value is not None else None
            elif label.startswith('下跌'):
                down = int(value) if value is not None else None
            elif label.startswith('持平'):
                flat = int(value) if value is not None else None

        if up is not None and down is not None:
            return up, down, flat

    return None, None, None


def main():
    market = json.loads(MARKET.read_text(encoding='utf-8'))
    stats = market.get('taiwan_stats') or {}
    date_text = stats.get('date') or next(
        (x.get('quote_date') for x in market.get('taiwan', []) if x.get('quote_date')),
        None,
    )
    if not date_text:
        raise RuntimeError('Taiwan trade date missing from market.json')

    tables = twse_tables(date_text)

    turnover = fmtqik_turnover(date_text)
    if turnover is None:
        turnover = mi_index_total_turnover(tables)

    up, down, flat = stock_breadth(tables)

    if turnover is None:
        raise RuntimeError(f'TWSE TOTAL turnover missing for {date_text}')
    if up is None or down is None:
        raise RuntimeError(f'TWSE STOCK breadth missing for {date_text}: up={up}, down={down}')

    directional = up + down
    stats.update({
        'turnover_twd': turnover,
        'turnover_100m_twd': round(turnover / 100_000_000, 2),
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if directional else None,
        'decline_pct': round(down / directional * 100, 1) if directional else None,
        'source': 'TWSE official FMTQIK + MI_INDEX',
        'source_url': 'https://www.twse.com.tw/exchangeReport/FMTQIK',
    })

    # Cash-market volume remains in JSON for diagnostics/backward compatibility,
    # but the Taiwan-market UI intentionally does not display it.
    market['taiwan_stats'] = stats
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'TWSE corrected: date={date_text} '
        f'turnover={stats["turnover_100m_twd"]}億元 '
        f'up={up} down={down} flat={flat}'
    )


if __name__ == '__main__':
    main()
