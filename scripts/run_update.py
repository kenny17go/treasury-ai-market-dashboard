from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timedelta, timezone

import update_market as u

DATA = u.DATA
TZ8 = timezone(timedelta(hours=8))


def load(name):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def _num(value):
    s = str(value or '').replace(',', '').replace('%', '').replace('−', '-').strip()
    if s in ('', '-', '—'):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _signed_move(change_raw, pct_raw, context=''):
    """Normalize Yahoo Taiwan direction markers into signed numeric values."""
    change = _num(change_raw)
    pct = _num(pct_raw)
    text = f'{context} {change_raw} {pct_raw}'
    down = '▼' in text or '跌' in text
    up = '▲' in text or '漲' in text
    if down:
        if change is not None:
            change = -abs(change)
        if pct is not None:
            pct = -abs(pct)
    elif up:
        if change is not None:
            change = abs(change)
        if pct is not None:
            pct = abs(pct)
    return change, pct


def _field_index(fields, keywords):
    for i, f in enumerate(fields or []):
        text = str(f).replace(' ', '')
        if all(k in text for k in keywords):
            return i
    return None


def _find_twse_table(tables, key):
    return next((t for t in (tables or []) if key in str(t.get('title', ''))), None)


def _find_table_by_fields(tables, required):
    """Find a TWSE table by field names rather than unstable table titles."""
    for t in tables or []:
        fields = ''.join(str(x).replace(' ', '') for x in (t.get('fields') or []))
        if all(k in fields for k in required):
            return t
    return None


def _find_table_by_row_labels(tables, labels):
    """Find a TWSE table whose first column contains all requested labels."""
    for t in tables or []:
        first_col = [str(r[0]).replace(' ', '') for r in (t.get('data') or []) if r]
        if all(any(x.startswith(label) for x in first_col) for label in labels):
            return t
    return None


def _twse_html_stats(trade_date):
    """Fallback parser for the official TWSE market-statistics HTML table."""
    url = 'https://www.twse.com.tw/exchangeReport/MI_INDEX'
    r = u.get_http(
        url,
        params={'response': 'html', 'type': 'MS', 'date': trade_date.strftime('%Y%m%d')},
    )
    soup = u.BeautifulSoup(r.text, 'html.parser')
    turnover = volume = trades = up = down = flat = None

    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
        if not cells:
            continue
        label = cells[0].replace(' ', '')
        if label.startswith('1.一般股票') and len(cells) >= 4:
            turnover = _num(cells[1])
            volume = _num(cells[2])
            trades = _num(cells[3])
        elif label.startswith('上漲'):
            up = _num(cells[-1])
        elif label.startswith('下跌'):
            down = _num(cells[-1])
        elif label.startswith('持平'):
            flat = _num(cells[-1])

    return {
        'turnover_twd': turnover,
        'volume_shares': volume,
        'trade_count': int(trades) if trades is not None else None,
        'advance_count': int(up) if up is not None else None,
        'decline_count': int(down) if down is not None else None,
        'flat_count': int(flat) if flat is not None else None,
    }


def fetch_twse_official_snapshot():
    """Fetch authoritative TAIEX close and previous-session market statistics."""
    base = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
    today = datetime.now(TZ8).date()
    last_error = None

    for days_back in range(8):
        d = today - timedelta(days=days_back)
        try:
            r = u.get_http(
                base,
                params={'date': d.strftime('%Y%m%d'), 'type': 'ALLBUT0999', 'response': 'json'},
            )
            obj = r.json()
            if str(obj.get('stat', '')).upper() != 'OK':
                continue

            tables = obj.get('tables') or []
            idx_table = _find_twse_table(tables, '價格指數') or _find_table_by_fields(tables, ['收盤指數', '漲跌點數'])
            market_table = (
                _find_twse_table(tables, '市場成交資訊')
                or _find_table_by_fields(tables, ['成交金額', '成交股數'])
            )
            breadth_table = (
                _find_twse_table(tables, '漲跌證券數合計')
                or _find_table_by_row_labels(tables, ['上漲', '下跌'])
            )

            close = change = change_pct = None
            if idx_table:
                fields = idx_table.get('fields') or []
                row = next(
                    (x for x in (idx_table.get('data') or []) if x and '發行量加權股價指數' in str(x[0])),
                    None,
                )
                if row:
                    i_close = _field_index(fields, ['收盤', '指數'])
                    i_change = _field_index(fields, ['漲跌', '點數'])
                    i_pct = _field_index(fields, ['漲跌', '百分比'])
                    close = _num(row[i_close]) if i_close is not None and i_close < len(row) else None
                    change = _num(row[i_change]) if i_change is not None and i_change < len(row) else None
                    change_pct = _num(row[i_pct]) if i_pct is not None and i_pct < len(row) else None

                    sign_col = next(
                        (
                            i
                            for i, f in enumerate(fields)
                            if '+/-' in str(f) or '+／-' in str(f) or '(+/-)' in str(f) or '(+／-)' in str(f)
                        ),
                        None,
                    )
                    if sign_col is not None and sign_col < len(row):
                        marker = str(row[sign_col]).strip()
                        if marker in ('-', '－', '−'):
                            if change is not None:
                                change = -abs(change)
                            if change_pct is not None:
                                change_pct = -abs(change_pct)
                        elif marker in ('+', '＋'):
                            if change is not None:
                                change = abs(change)
                            if change_pct is not None:
                                change_pct = abs(change_pct)

                    # A negative percentage must never be paired with a positive point move.
                    if change is not None and change_pct is not None:
                        change = -abs(change) if change_pct < 0 else abs(change) if change_pct > 0 else change
                    if change_pct is None and close is not None and change is not None and close - change:
                        change_pct = change / (close - change) * 100

            turnover = volume = trades = None
            if market_table:
                fields = market_table.get('fields') or []
                rows = market_table.get('data') or []
                row = next(
                    (x for x in rows if x and str(x[0]).replace(' ', '').startswith('1.一般股票')),
                    None,
                )
                if row is None and rows:
                    row = rows[0]
                if row:
                    i_value = _field_index(fields, ['成交金額'])
                    i_volume = _field_index(fields, ['成交股數'])
                    i_trades = _field_index(fields, ['成交筆數'])
                    turnover = _num(row[i_value]) if i_value is not None and i_value < len(row) else None
                    volume = _num(row[i_volume]) if i_volume is not None and i_volume < len(row) else None
                    trades = _num(row[i_trades]) if i_trades is not None and i_trades < len(row) else None

            up = down = flat = None
            if breadth_table:
                for row in breadth_table.get('data') or []:
                    if not row:
                        continue
                    label = str(row[0]).replace(' ', '')
                    val = _num(row[-1])
                    if label.startswith('上漲'):
                        up = val
                    elif label.startswith('下跌'):
                        down = val
                    elif label.startswith('持平'):
                        flat = val

            # TWSE occasionally changes JSON table titles/schema. Fill only missing
            # fields from the official HTML market-statistics table for the same date.
            if turnover is None or volume is None or up is None or down is None:
                html_stats = _twse_html_stats(d)
                turnover = turnover if turnover is not None else html_stats.get('turnover_twd')
                volume = volume if volume is not None else html_stats.get('volume_shares')
                trades = trades if trades is not None else html_stats.get('trade_count')
                up = up if up is not None else html_stats.get('advance_count')
                down = down if down is not None else html_stats.get('decline_count')
                flat = flat if flat is not None else html_stats.get('flat_count')

            if close is None:
                raise ValueError('TAIEX close not found in official TWSE response')
            if turnover is None or volume is None:
                raise ValueError('TWSE turnover/volume not found in official response')

            directional = (up or 0) + (down or 0)
            return {
                'date': d.isoformat(),
                'index_close': close,
                'index_change': change,
                'index_change_pct': change_pct,
                'turnover_twd': turnover,
                'turnover_100m_twd': round(turnover / 100_000_000, 2),
                'volume_shares': volume,
                'volume_100m_shares': round(volume / 100_000_000, 2),
                'trade_count': int(trades) if trades is not None else None,
                'advance_count': int(up) if up is not None else None,
                'decline_count': int(down) if down is not None else None,
                'flat_count': int(flat) if flat is not None else None,
                'advance_pct': round(up / directional * 100, 1) if up is not None and directional else None,
                'decline_pct': round(down / directional * 100, 1) if down is not None and directional else None,
                'source': 'TWSE MI_INDEX official',
                'source_url': base,
            }
        except Exception as e:
            last_error = e

    raise RuntimeError(f'TWSE official snapshot unavailable: {last_error}')


def fetch_taiwan_futures_quote():
    """Fetch the front-month Taiwan Index Futures quote from Yahoo Taiwan."""
    url = 'https://tw.stock.yahoo.com/future/futures.html'
    r = u.get_http(url)
    soup = u.BeautifulSoup(r.text, 'html.parser')

    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
        try:
            idx = cells.index('台指期近一')
        except ValueError:
            continue

        row_text = ' '.join(cells)
        rest = cells[idx + 1:]
        if rest and rest[0].startswith('WTX'):
            symbol = rest.pop(0)
        else:
            symbol = 'WTX&'
        if len(rest) < 6:
            continue

        price = _num(rest[2])
        if price is None:
            continue
        change, change_pct = _signed_move(rest[3], rest[4], row_text)
        return {
            'name': '台指期近一',
            'symbol': symbol,
            'price': price,
            'bid': _num(rest[0]),
            'ask': _num(rest[1]),
            'change': change,
            'change_pct': change_pct,
            'volume': _num(rest[5]),
            'quote_time': rest[-1] if rest and re.fullmatch(r'\d{1,2}:\d{2}:\d{2}', rest[-1]) else None,
            'direction_marker': '▼' if change_pct is not None and change_pct < 0 else ('▲' if change_pct is not None and change_pct > 0 else ''),
            'source': 'Yahoo股市',
            'source_url': url,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
        }

    text = soup.get_text('\n', strip=True)
    m = re.search(
        r'台指期近一\s*WTX&\s*([\d,.+-]+)\s*([\d,.+-]+)\s*([\d,.+-]+)\s*([▲▼]?)\s*([\d,.+-]+)\s*\(?([\d,.+-]+)%?\)?\s*([\d,]+)',
        text,
        re.S,
    )
    if m:
        change, change_pct = _signed_move(m.group(5), m.group(6), m.group(4))
        return {
            'name': '台指期近一',
            'symbol': 'WTX&',
            'bid': _num(m.group(1)),
            'ask': _num(m.group(2)),
            'price': _num(m.group(3)),
            'change': change,
            'change_pct': change_pct,
            'volume': _num(m.group(7)),
            'quote_time': None,
            'direction_marker': m.group(4),
            'source': 'Yahoo股市',
            'source_url': url,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
        }

    raise ValueError('Taiwan Index Futures quote not parsed')


def merge_quote_sections(new, old, keys):
    for sec in keys:
        old_map = {x.get('symbol') or x.get('name'): x for x in old.get(sec, [])}
        merged = []
        for x in new.get(sec, []):
            k = x.get('symbol') or x.get('name')
            ox = old_map.get(k, {})
            if x.get('price') is None and ox.get('price') is not None:
                x = {**ox, **{kk: vv for kk, vv in x.items() if vv not in (None, [], '')}}
            merged.append(x)
        new[sec] = merged
    if not new.get('taiwan_stats') and old.get('taiwan_stats'):
        new['taiwan_stats'] = {**old['taiwan_stats'], 'fallback': True}
    return new


def merge_rates(new, old):
    old_map = {x.get('series'): x for x in old.get('rates', [])}
    out = []
    for x in new.get('rates', []):
        ox = old_map.get(x.get('series'), {})
        if x.get('value') is None and ox.get('value') is not None:
            x = {**ox, **{k: v for k, v in x.items() if v is not None}}
            x['fallback'] = True
        out.append(x)
    present = {x.get('series') for x in out}
    for sid, ox in old_map.items():
        if sid not in present and ox.get('value') is not None:
            out.append({**ox, 'fallback': True})
    new['rates'] = out
    return new


def restore_if_empty(name, old, predicate):
    new = load(name)
    if predicate(new):
        return new
    if old:
        old['fallback_at'] = datetime.now(timezone.utc).isoformat()
        old['fallback_reason'] = 'latest source unavailable; preserving last good data'
        save(name, old)
        return old
    return new


def main():
    cfg = u.load_cfg()
    old = {
        n: load(n)
        for n in [
            'market.json',
            'stocks.json',
            'rates.json',
            'news.json',
            'calendar.json',
            'positioning.json',
            'professional.json',
            'brief.json',
        ]
    }
    critical_failures = []

    stages = [
        ('market', lambda: u.update_market(cfg), False),
        ('stocks', lambda: u.update_stocks(cfg), False),
        ('rates', u.update_rates, False),
        ('news', u.update_news, False),
        ('calendar', u.update_calendar, True),
        ('positioning', u.update_positioning, False),
        ('professional', u.update_professional, False),
    ]
    for name, fn, critical in stages:
        try:
            fn()
        except Exception as e:
            print(f'[WARN] {name} stage failed: {e}')
            traceback.print_exc()
            if critical:
                critical_failures.append(f'{name}: {e}')

    market = merge_quote_sections(
        load('market.json'),
        old['market.json'],
        ['indices', 'pulse', 'taiwan', 'commodities', 'fx'],
    )

    try:
        snap = fetch_twse_official_snapshot()
        old_tw = next((x for x in market.get('taiwan', []) if x.get('symbol') == '^TWII'), {})
        market['taiwan'] = [
            {
                'symbol': '^TWII',
                'name': '台灣加權指數',
                'price': snap['index_close'],
                'change': snap['index_change'],
                'change_pct': snap['index_change_pct'],
                'spark': old_tw.get('spark', []),
                'quote_date': snap['date'],
                'source': 'TWSE official',
            }
        ]
        market['taiwan_stats'] = snap
        market['source'] = 'Yahoo Finance via yfinance / TWSE official MI_INDEX'
        print(
            f"TWSE official: {snap['date']} TAIEX={snap['index_close']} "
            f"volume={snap.get('volume_100m_shares')}億股 "
            f"turnover={snap.get('turnover_100m_twd')}億元 "
            f"up={snap.get('advance_count')} down={snap.get('decline_count')}"
        )
    except Exception as e:
        print('[WARN] official TWSE snapshot failed:', e)
        traceback.print_exc()
        old_stats = old['market.json'].get('taiwan_stats') or {}
        old_tw = next(
            (x for x in old['market.json'].get('taiwan', []) if x.get('source') == 'TWSE official'),
            None,
        )
        if old_tw and old_stats.get('source') == 'TWSE MI_INDEX official':
            market['taiwan'] = [old_tw]
            market['taiwan_stats'] = {**old_stats, 'fallback': True}
        else:
            market['taiwan'] = []
            market['taiwan_stats'] = {
                'source': 'TWSE MI_INDEX official',
                'status': 'unavailable',
            }

    try:
        market['taiwan_futures'] = fetch_taiwan_futures_quote()
    except Exception as e:
        print('[WARN] Taiwan futures quote failed:', e)
        if old['market.json'].get('taiwan_futures'):
            market['taiwan_futures'] = {**old['market.json']['taiwan_futures'], 'fallback': True}
        else:
            market['taiwan_futures'] = {
                'name': '台指期近一',
                'symbol': 'WTX&',
                'price': None,
                'change': None,
                'change_pct': None,
                'source': 'Yahoo股市',
                'status': 'unavailable',
            }
    save('market.json', market)

    save('stocks.json', merge_quote_sections(load('stocks.json'), old['stocks.json'], ['stocks']))
    save('rates.json', merge_rates(load('rates.json'), old['rates.json']))
    restore_if_empty('news.json', old['news.json'], lambda x: bool(x.get('items')))
    restore_if_empty(
        'calendar.json',
        old['calendar.json'],
        lambda x: x.get('status') == 'ok' and bool(x.get('items')),
    )
    restore_if_empty(
        'positioning.json',
        old['positioning.json'],
        lambda x: x.get('status') == 'ok' and x.get('tx_foreign', {}).get('oi_net_contracts') is not None,
    )

    p = load('professional.json')
    oldp = old['professional.json']
    if not p.get('yield_curve') and oldp.get('yield_curve'):
        p['yield_curve'] = oldp['yield_curve']
    if not p.get('policy_rates') and oldp.get('policy_rates'):
        p['policy_rates'] = oldp['policy_rates']
    save('professional.json', p)

    try:
        u.update_brief()
    except Exception as e:
        print('[WARN] brief stage failed:', e)
        traceback.print_exc()
        if old['brief.json']:
            save('brief.json', old['brief.json'])
        critical_failures.append(f'brief: {e}')

    cal = load('calendar.json')
    brief = load('brief.json')
    if cal.get('source_mode') != 'Official global central banks + official statistics + market-calendar enrichment':
        critical_failures.append('calendar validation: consolidated schema was not generated')
    if brief.get('today_filter') != 'calendar date == Taipei today; news published date == Taipei today; future events forbidden':
        critical_failures.append('brief validation: strict Taipei-today filter was not generated')

    if critical_failures:
        raise RuntimeError('Critical data pipeline failure(s): ' + ' | '.join(critical_failures))
    print('Consolidated updater completed and validated successfully.')


if __name__ == '__main__':
    main()
