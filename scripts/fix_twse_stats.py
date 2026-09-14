from __future__ import annotations

import json
from pathlib import Path

import update_market as u

DATA = Path(__file__).resolve().parents[1] / 'data'
MARKET = DATA / 'market.json'


def num(v):
    s = str(v or '').replace(',', '').replace('%', '').replace('−', '-').strip()
    if s in ('', '-', '—'):
        return None
    try:
        return float(s)
    except Exception:
        return None


def field_index(fields, keyword):
    for i, f in enumerate(fields or []):
        if keyword in str(f).replace(' ', ''):
            return i
    return None


def table_for_date(date_text):
    url = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
    r = u.get_http(url, params={'date': date_text.replace('-', ''), 'type': 'ALLBUT0999', 'response': 'json'})
    obj = r.json()
    if str(obj.get('stat', '')).upper() != 'OK':
        raise RuntimeError(f'TWSE MI_INDEX not OK: {obj.get("stat")}')
    return obj.get('tables') or []


def total_turnover(tables):
    for t in tables:
        fields = t.get('fields') or []
        vi = field_index(fields, '成交金額')
        if vi is None:
            continue
        rows = t.get('data') or []
        # Prefer an explicit total row when TWSE supplies one.
        for row in rows:
            if not row or vi >= len(row):
                continue
            label = str(row[0]).replace(' ', '')
            if '合計' in label or '總計' in label:
                v = num(row[vi])
                if v is not None:
                    return v
        # Otherwise sum the mutually exclusive security-category rows.
        vals = []
        for row in rows:
            if not row or vi >= len(row):
                continue
            label = str(row[0]).replace(' ', '')
            if '合計' in label or '總計' in label:
                continue
            v = num(row[vi])
            if v is not None:
                vals.append(v)
        if vals:
            return sum(vals)
    return None


def breadth(tables):
    # First preference: a row-based summary table with Up/Down columns.
    for t in tables:
        fields = t.get('fields') or []
        ui = field_index(fields, '上漲')
        di = field_index(fields, '下跌')
        fi = field_index(fields, '持平')
        if ui is None or di is None:
            continue
        rows = t.get('data') or []
        preferred = next((r for r in rows if r and '股票' in str(r[0])), None)
        row = preferred or (rows[0] if rows else None)
        if row and ui < len(row) and di < len(row):
            up, down = num(row[ui]), num(row[di])
            flat = num(row[fi]) if fi is not None and fi < len(row) else None
            if up is not None and down is not None:
                return int(up), int(down), int(flat) if flat is not None else None

    # Second preference: legacy table with 上漲/下跌/持平 as first-column labels.
    for t in tables:
        up = down = flat = None
        for row in t.get('data') or []:
            if not row:
                continue
            label = str(row[0]).replace(' ', '')
            value = num(row[-1])
            if label.startswith('上漲'):
                up = value
            elif label.startswith('下跌'):
                down = value
            elif label.startswith('持平'):
                flat = value
        if up is not None and down is not None:
            return int(up), int(down), int(flat) if flat is not None else None
    return None, None, None


def main():
    market = json.loads(MARKET.read_text(encoding='utf-8'))
    stats = market.get('taiwan_stats') or {}
    date_text = stats.get('date') or next((x.get('quote_date') for x in market.get('taiwan', []) if x.get('quote_date')), None)
    if not date_text:
        raise RuntimeError('Taiwan trade date missing from market.json')

    tables = table_for_date(date_text)
    turnover = total_turnover(tables)
    up, down, flat = breadth(tables)

    if turnover is not None:
        stats['turnover_twd'] = turnover
        stats['turnover_100m_twd'] = round(turnover / 100_000_000, 2)
    if up is not None and down is not None:
        stats['advance_count'] = up
        stats['decline_count'] = down
        stats['flat_count'] = flat
        directional = up + down
        stats['advance_pct'] = round(up / directional * 100, 1) if directional else None
        stats['decline_pct'] = round(down / directional * 100, 1) if directional else None

    # Volume is intentionally no longer displayed in the Taiwan-market UI.
    market['taiwan_stats'] = stats
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"TWSE stats corrected: date={date_text} turnover={stats.get('turnover_100m_twd')}億元 up={stats.get('advance_count')} down={stats.get('decline_count')}")


if __name__ == '__main__':
    main()
