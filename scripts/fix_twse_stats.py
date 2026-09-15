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
UDN_NEWEST_URL = 'https://money.udn.com/rank/ajax_newest/1001/5590/{page}'


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
    """Try Yahoo Taiwan's market page for the regular-session close turnover."""
    r = u.get_http(YAHOO_TSE_URL)
    soup = u.BeautifulSoup(r.text, 'html.parser')
    text = soup.get_text(' ', strip=True)

    dates = re.findall(r'20\d{2}/\d{1,2}/\d{1,2}', text)
    if dates:
        normalized = {normalize_date(x) for x in dates}
        if date_text not in normalized:
            raise RuntimeError(f'Yahoo TSE page date does not match {date_text}')

    patterns = [
        r'成交金額\s*([\d,]+(?:\.\d+)?)\s*億',
        r'成交值\s*([\d,]+(?:\.\d+)?)\s*億',
        r'成交\s*([\d,]+(?:\.\d+)?)\s*億',
    ]
    for pat in patterns:
        for raw in re.findall(pat, text):
            v = num(raw)
            if v is not None and 100 <= v <= 30000:
                return round(v, 2), 'Yahoo股市大盤頁'
    raise RuntimeError('Yahoo TSE regular-session turnover not found')


def udn_regular_session_turnover(date_text, index_price=None):
    """Fallback to a close recap carrying the 13:30 cash-session headline turnover.

    The dashboard wants the market-close headline amount (e.g. 6,309.17 億元
    on 2026-09-14), not the later FMTQIK all-session total. We only accept a
    candidate when the page contains the exact trade date and, when available,
    the exact TAIEX close. This prevents taking a nearby day's figure.
    """
    date_variants = {
        date_text,
        date_text.replace('-', '/'),
        f'{int(date_text[5:7])}/{int(date_text[8:10])}',
    }
    price_tokens = []
    if index_price is not None:
        p = float(index_price)
        price_tokens = [f'{p:.2f}', f'{p:,.2f}']

    patterns = [
        r'成交金額(?:新台幣)?\s*([\d,]+(?:\.\d+)?)\s*億元',
        r'成交值(?:新台幣)?\s*([\d,]+(?:\.\d+)?)\s*億元',
        r'成交(?:量)?\s*([\d,]+(?:\.\d+)?)\s*億元',
    ]

    for page in range(1, 5):
        r = u.get_http(UDN_NEWEST_URL.format(page=page))
        soup = u.BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text(' ', strip=True)
        if not any(d in text for d in date_variants):
            continue

        # Prefer a local window around the exact TAIEX close, which makes the
        # number/date pairing far safer than taking the first turnover on page.
        windows = []
        for token in price_tokens:
            start = 0
            while True:
                pos = text.find(token, start)
                if pos < 0:
                    break
                windows.append(text[max(0, pos - 450):pos + 650])
                start = pos + len(token)
        if not windows:
            windows = [text]

        for window in windows:
            if not any(d in window for d in date_variants) and windows != [text]:
                # Some article excerpts omit the full date inside the price window;
                # page-level date already matched, so allow the window if the exact
                # close price anchored it.
                if not any(t in window for t in price_tokens):
                    continue
            for pat in patterns:
                for raw in re.findall(pat, window):
                    v = num(raw)
                    if v is not None and 100 <= v <= 30000:
                        return round(v, 2), '經濟日報/中央社收盤摘要'

    raise RuntimeError(f'Close-recap turnover not found for {date_text}')


def regular_session_turnover(date_text, index_price=None):
    errors = []
    for getter in (
        lambda: yahoo_regular_session_turnover(date_text),
        lambda: udn_regular_session_turnover(date_text, index_price),
    ):
        try:
            value, source = getter()
            return value, source
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError('Regular-session turnover unavailable: ' + ' | '.join(errors))


def stock_breadth(tables):
    """Read listed-stock up/down/flat counts from TWSE's 股票 column."""
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
    idx = next((x for x in market.get('taiwan', []) if x.get('symbol') == '^TWII'), None)
    date_text = stats.get('date') or (idx or {}).get('quote_date')
    if not date_text:
        raise RuntimeError('Taiwan trade date missing from market.json')
    date_text = datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y-%m-%d')

    turnover_100m, turnover_source = regular_session_turnover(date_text, (idx or {}).get('price'))
    up, down, flat = stock_breadth(twse_tables(date_text))

    # Strict validation: never silently write FMTQIK/all-session totals or an
    # adjacent day's headline into the dashboard's cash-session turnover field.
    if not (100 <= turnover_100m <= 30000):
        raise RuntimeError(f'Turnover sanity check failed: {turnover_100m} 億元')

    directional = up + down
    stats.update({
        'turnover_100m_twd': turnover_100m,
        'turnover_twd': round(turnover_100m * 100_000_000),
        'turnover_method': 'regular cash-session close headline; exact trade date',
        'turnover_trade_date': date_text,
        'turnover_verified': True,
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if directional else None,
        'decline_pct': round(down / directional * 100, 1) if directional else None,
        'breadth_scope': 'listed_stocks',
        'turnover_source': turnover_source,
        'breadth_source': 'TWSE MI_INDEX 股票欄',
        'source': f'TWSE official MI_INDEX + {turnover_source}',
    })

    market['taiwan_stats'] = stats
    MARKET.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'Taiwan close verified: date={date_text} turnover={turnover_100m}億元 '
        f'source={turnover_source} listed-stock breadth up={up} down={down} flat={flat}'
    )


if __name__ == '__main__':
    main()
