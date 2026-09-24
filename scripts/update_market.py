from __future__ import annotations

import calendar as cal
import html
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import feedparser
import pandas as pd
import requests
import yaml
import yfinance as yf
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CONFIG = ROOT / 'config' / 'market.yml'
DATA.mkdir(exist_ok=True)
TZ8 = timezone(timedelta(hours=8))
ET_ZONE = ZoneInfo('America/New_York')
UA = {
    'User-Agent': 'Mozilla/5.0 MarketOnePage/1.4.7 (+https://github.com/kenny17go/treasury-ai-market-dashboard)',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.7',
}


def clean(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def load_json(name):
    try:
        return json.loads((DATA / name).read_text(encoding='utf-8'))
    except Exception:
        return {}


def load_cfg():
    return yaml.safe_load(CONFIG.read_text(encoding='utf-8'))


def get_http(url, **kwargs):
    last = None
    headers = {**UA, **kwargs.pop('headers', {})}
    for n in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=18, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(1.0 * (n + 1))
    raise last


# ---------- Market quotes ----------
def hist_for(symbol):
    for period, interval in [('5d', '30m'), ('1mo', '1d')]:
        try:
            h = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False, prepost=False, timeout=15)
            if h is not None and not h.empty and 'Close' in h:
                vals = [clean(x) for x in h['Close'].tolist()]
                vals = [x for x in vals if x is not None]
                if len(vals) >= 2:
                    return vals[-60:]
        except Exception as e:
            print('history', symbol, e)
    return []


def quote(item):
    symbol = item['symbol']
    vals = hist_for(symbol)
    if len(vals) < 2:
        return {**item, 'price': None, 'change': None, 'change_pct': None, 'spark': []}
    price = vals[-1]
    prev = None
    try:
        d = yf.Ticker(symbol).history(period='7d', interval='1d', auto_adjust=False, timeout=15)
        closes = [clean(x) for x in d['Close'].tolist()]
        closes = [x for x in closes if x is not None]
        if len(closes) >= 2:
            prev = closes[-2]
    except Exception:
        pass
    if prev is None:
        prev = vals[0]
    change = price - prev
    pct = (change / prev * 100) if prev else None
    return {**item, 'price': clean(price), 'change': clean(change), 'change_pct': clean(pct), 'spark': vals[-48:]}


def _to_int(s):
    m = re.search(r'-?\d[\d,]*', str(s or ''))
    return int(m.group().replace(',', '')) if m else None


def twse_market_stats():
    url = 'https://www.twse.com.tw/exchangeReport/MI_INDEX?response=html&type=MS'
    r = get_http(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    turnover = up = down = flat = None
    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'])]
        if not cells:
            continue
        first = cells[0].replace(' ', '')
        if first.startswith('1.一般股票') and len(cells) >= 2:
            turnover = _to_int(cells[1])
        elif first.startswith('上漲') and len(cells) >= 3:
            up = _to_int(cells[-1])
        elif first.startswith('下跌') and len(cells) >= 3:
            down = _to_int(cells[-1])
        elif first.startswith('持平') and len(cells) >= 3:
            flat = _to_int(cells[-1])
    text = soup.get_text(' ', strip=True)
    dm = re.search(r'(\d{3})年(\d{2})月(\d{2})日', text)
    trade_date = f'{int(dm.group(1))+1911:04d}-{dm.group(2)}-{dm.group(3)}' if dm else None
    if turnover is None and up is None and down is None:
        raise ValueError('TWSE market statistics not parsed')
    directional = (up or 0) + (down or 0)
    return {
        'date': trade_date,
        'turnover_twd': turnover,
        'turnover_100m_twd': round(turnover / 100_000_000, 1) if turnover is not None else None,
        'advance_count': up,
        'decline_count': down,
        'flat_count': flat,
        'advance_pct': round(up / directional * 100, 1) if up is not None and directional else None,
        'decline_pct': round(down / directional * 100, 1) if down is not None and directional else None,
        'source': 'TWSE MI_INDEX',
    }


def update_market(cfg):
    sections = {}
    for sec in ('indices', 'pulse', 'taiwan', 'commodities', 'fx'):
        out = []
        for item in cfg.get(sec, []):
            out.append(quote(item))
            time.sleep(.08)
        sections[sec] = out
    sections['taiwan'] = [x for x in sections.get('taiwan', []) if x.get('symbol') == '^TWII' or '加權' in str(x.get('name', ''))]
    old = load_json('market.json')
    try:
        sections['taiwan_stats'] = twse_market_stats()
    except Exception as e:
        print('TWSE market stats', e)
        if old.get('taiwan_stats'):
            sections['taiwan_stats'] = {**old['taiwan_stats'], 'fallback': True}
    save('market.json', {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'status': 'Auto Update',
        'source': 'Yahoo Finance via yfinance / TWSE',
        **sections,
    })


def update_stocks(cfg):
    out = []
    for item in cfg.get('stocks', []):
        out.append(quote(item))
        time.sleep(.08)
    save('stocks.json', {'as_of': datetime.now(timezone.utc).isoformat(), 'source': 'Yahoo Finance via yfinance', 'stocks': out})


# ---------- Rates ----------
def _local(tag):
    return tag.split('}')[-1]


def treasury_curve():
    year = datetime.now(TZ8).year
    url = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
    r = get_http(url, params={'data': 'daily_treasury_yield_curve', 'field_tdr_date_value': str(year)})
    root = ET.fromstring(r.content)
    rows = []
    for entry in root.iter():
        if _local(entry.tag) != 'entry':
            continue
        d = {}
        for node in entry.iter():
            key = _local(node.tag)
            if node.text and node.text.strip():
                d[key] = node.text.strip()
        if d.get('NEW_DATE'):
            rows.append(d)
    if not rows:
        raise ValueError('Treasury XML contained no curve rows')
    rows.sort(key=lambda x: x['NEW_DATE'])
    return rows[-2:], url


def nyfed_rate(kind='effr'):
    url = f'https://www.newyorkfed.org/markets/reference-rates/{kind}?lv=true'
    r = get_http(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
        if len(cells) < 2 or not re.fullmatch(r'\d{2}/\d{2}', cells[0]):
            continue
        try:
            rate = float(cells[1].replace('%', '').strip())
        except Exception:
            continue
        out = {'value': rate, 'date': cells[0], 'source_url': url}
        m = re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)', ' '.join(cells))
        if m:
            out['target_low'] = float(m.group(1))
            out['target_high'] = float(m.group(2))
        return out
    text = soup.get_text(' ', strip=True)
    m = re.search(r'(\d{2}/\d{2})\s+(\d+\.\d+)\s+', text)
    if not m:
        raise ValueError(f'NY Fed {kind} not parsed')
    out = {'value': float(m.group(2)), 'date': m.group(1), 'source_url': url}
    tm = re.search(r'(\d+\.\d+)\s*[-–]\s*(\d+\.\d+)', text)
    if tm:
        out['target_low'] = float(tm.group(1))
        out['target_high'] = float(tm.group(2))
    return out


def ecb_deposit_rate():
    url = 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html'
    r = get_http(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    today = datetime.now(TZ8).date()
    candidates = []
    months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    current_year = None
    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
        for c in cells[:2]:
            ym = re.fullmatch(r'(20\d{2})', c)
            if ym:
                current_year = int(ym.group(1))
        dm = None
        for c in cells:
            m = re.search(r'(\d{1,2})\s+([A-Z][a-z]{2})', c)
            if m and m.group(2) in months:
                dm = (int(m.group(1)), months[m.group(2)])
                break
        if not dm or not current_year:
            continue
        d = datetime(current_year, dm[1], dm[0]).date()
        if d > today:
            continue
        nums = []
        for c in cells:
            if re.fullmatch(r'\d+(?:\.\d+)?', c):
                v = float(c)
                if v < 20:
                    nums.append(v)
        if nums:
            candidates.append((d, nums[0]))
    if not candidates:
        raise ValueError('ECB deposit rate not parsed')
    d, v = max(candidates, key=lambda x: x[0])
    return {'value': v, 'date': d.isoformat(), 'source_url': url}


def update_rates():
    rows, cache, sources = [], {}, []
    try:
        curves, _ = treasury_curve()
        latest, prev = curves[-1], curves[-2] if len(curves) > 1 else curves[-1]
        for sid, name, key in [('DGS2','美債 2年','BC_2YEAR'),('DGS5','美債 5年','BC_5YEAR'),('DGS10','美債 10年','BC_10YEAR'),('DGS30','美債 30年','BC_30YEAR')]:
            v, p = clean(latest.get(key)), clean(prev.get(key))
            cache[sid] = [p, v]
            rows.append({'series': sid, 'name': name, 'value': v, 'unit': '%', 'change_bps': clean((v-p)*100) if v is not None and p is not None else None, 'date': latest.get('NEW_DATE'), 'source': 'U.S. Treasury'})
        sources.append('U.S. Treasury')
    except Exception as e:
        print('Treasury curve', e)
    for sid, a, b, name in [('2S10S','DGS2','DGS10','2Y10Y 利差'),('5S30S','DGS5','DGS30','5Y30Y 利差')]:
        try:
            cur = (cache[b][-1] - cache[a][-1]) * 100
            prv = (cache[b][0] - cache[a][0]) * 100
            rows.append({'series': sid, 'name': name, 'value': clean(cur), 'unit': 'bps', 'change_bps': clean(cur-prv), 'source': 'U.S. Treasury derived'})
        except Exception:
            rows.append({'series': sid, 'name': name, 'value': None, 'unit': 'bps', 'change_bps': None})
    for sid, name, kind in [('DFF','Fed Funds Effective','effr'),('SOFR','SOFR','sofr')]:
        try:
            x = nyfed_rate(kind)
            rows.append({'series': sid, 'name': name, 'value': x['value'], 'unit': '%', 'change_bps': None, 'date': x.get('date'), 'source': 'New York Fed', 'target_low': x.get('target_low'), 'target_high': x.get('target_high')})
            sources.append('New York Fed')
        except Exception as e:
            print('NYFed', kind, e)
            rows.append({'series': sid, 'name': name, 'value': None, 'unit': '%', 'change_bps': None})
    try:
        x = ecb_deposit_rate()
        rows.append({'series': 'ECBDFR', 'name': 'ECB Deposit Rate', 'value': x['value'], 'unit': '%', 'change_bps': None, 'date': x['date'], 'source': 'ECB'})
        sources.append('ECB')
    except Exception as e:
        print('ECB', e)
        rows.append({'series': 'ECBDFR', 'name': 'ECB Deposit Rate', 'value': None, 'unit': '%', 'change_bps': None})
    save('rates.json', {'as_of': datetime.now(timezone.utc).isoformat(), 'source': ' / '.join(dict.fromkeys(sources)) or 'official sources', 'rates': rows})


# ---------- Fed probability / professional JSON ----------
FOMC_DATES = [date(2026,9,16),date(2026,10,28),date(2026,12,9),date(2027,1,27),date(2027,3,17),date(2027,4,28),date(2027,6,9),date(2027,7,28),date(2027,9,15),date(2027,10,27),date(2027,12,8)]
MONTH_CODE = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}


def next_fomc(today=None):
    today = today or datetime.now(TZ8).date()
    return next((d for d in FOMC_DATES if d >= today), None)


def zq_contract_symbol(d):
    return f"ZQ{MONTH_CODE[d.month]}{str(d.year)[-2:]}.CBT"


def zq_price(symbol):
    try:
        t = yf.Ticker(symbol)
        for period, interval in [('5d','30m'),('1mo','1d')]:
            h = t.history(period=period, interval=interval, auto_adjust=False, timeout=15)
            vals = [clean(x) for x in h['Close'].tolist()] if h is not None and not h.empty else []
            vals = [x for x in vals if x is not None]
            if vals:
                return vals[-1]
    except Exception as e:
        print('Yahoo ZQ', symbol, e)
    meeting = next_fomc()
    code = f"ZQ{MONTH_CODE[meeting.month]}{meeting.year}" if meeting else ''
    try:
        r = get_http('https://www.tradingview.com/symbols/CBOT-ZQ1%21/contracts/')
        text = BeautifulSoup(r.text, 'html.parser').get_text(' ', strip=True)
        m = re.search(re.escape(code) + r'.{0,180}?(9\d\.\d{2,4})', text, re.S)
        if m:
            return float(m.group(1))
    except Exception as e:
        print('TradingView ZQ', e)
    raise ValueError(f'No Fed Funds futures price for {symbol}')


def fed_probability(rates):
    meeting = next_fomc()
    if not meeting:
        return None
    effr_row = next((x for x in rates if x.get('series') == 'DFF' and x.get('value') is not None), None)
    if not effr_row:
        return None
    effr = float(effr_row['value'])
    low, high = effr_row.get('target_low'), effr_row.get('target_high')
    symbol = zq_contract_symbol(meeting)
    price = zq_price(symbol)
    avg = 100 - price
    days = cal.monthrange(meeting.year, meeting.month)[1]
    pre = meeting.day
    post = days - pre
    if post <= 0:
        raise ValueError('No post-meeting days in contract month')
    post_rate = (avg * days - effr * pre) / post
    delta = (post_rate - effr) * 100
    lower = math.floor(delta / 25.0) * 25.0
    upper = lower + 25.0
    p_upper = max(0, min(1, (delta - lower) / 25.0))
    p_lower = 1 - p_upper
    outcomes = []
    for step, p in [(lower, p_lower), (upper, p_upper)]:
        label = '維持' if abs(step) < 1e-8 else ('升息' if step > 0 else '降息')
        out = {'change_bps': round(step), 'label': label, 'probability': round(p * 100, 1)}
        if low is not None and high is not None:
            out['target_low'] = round(float(low) + step / 100, 2)
            out['target_high'] = round(float(high) + step / 100, 2)
        outcomes.append(out)
    outcomes.sort(key=lambda x: x['probability'], reverse=True)
    return {
        'meeting_date': meeting.isoformat(),
        'days_to_meeting': (meeting - datetime.now(TZ8).date()).days,
        'contract': symbol,
        'futures_price': price,
        'monthly_implied_rate': avg,
        'effective_rate': effr,
        'post_meeting_implied_rate': post_rate,
        'current_target_low': low,
        'current_target_high': high,
        'outcomes': outcomes,
        'methodology': '以會議月份 30-Day Fed Funds Futures 的整月平均 EFFR 定價，按會議前/後日數拆解，再在相鄰 25bp 結果間線性內插；概念依 CME FedWatch methodology，本站自行估算，非 CME 官方 FedWatch。',
        'source': '30-Day Fed Funds monthly futures + New York Fed EFFR + Federal Reserve FOMC calendar',
    }


def update_professional():
    m, r = load_json('market.json'), load_json('rates.json')
    rates = r.get('rates', [])
    curve = [x for x in rates if x.get('series') in ('DGS2','DGS5','DGS10','DGS30')]
    policies = [x for x in rates if x.get('series') in ('DFF','ECBDFR') and x.get('value') is not None]
    try:
        fed = fed_probability(rates)
    except Exception as e:
        print('Fed probability', e)
        fed = None
    fx = m.get('fx', [])
    getfx = lambda name: next((x for x in fx if x.get('name') == name), None)
    asia = [getfx(x) for x in ('USD/TWD','USD/JPY','USD/CNH','USD/HKD','USD/SGD','USD/KRW') if getfx(x)]
    save('professional.json', {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'yield_curve': curve,
        'policy_rates': policies,
        'fed_pricing': fed,
        'twd': {'usd_twd': getfx('USD/TWD'), 'dxy': getfx('DXY'), 'usd_cnh': getfx('USD/CNH')},
        'asia_fx': asia,
        'rates_source': 'U.S. Treasury / New York Fed / ECB official sources',
    })


# ---------- TAIFEX ----------
def parse_int(v):
    try:
        return int(str(v).replace(',', '').replace('+', '').strip())
    except Exception:
        return None


def update_positioning():
    url = 'https://www.taifex.com.tw/cht/3/futContractsDateExcel'
    result = {'product':'臺股期貨','identity':'外資','date':None,'trade_net_contracts':None,'oi_long_contracts':None,'oi_short_contracts':None,'oi_net_contracts':None}
    try:
        r = get_http(url)
        text = BeautifulSoup(r.text, 'html.parser').get_text(' ', strip=True)
        dm = re.search(r'日期\s*(\d{4}/\d{2}/\d{2})', text)
        result['date'] = dm.group(1) if dm else None
        tables = pd.read_html(StringIO(r.text))
        found = False
        for df in tables:
            for _, row in df.iterrows():
                cells = [str(x).strip() for x in row.tolist()]
                joined = ' | '.join(cells)
                if '臺股期貨' not in joined or '外資' not in joined:
                    continue
                nums = []
                for c in cells:
                    if '臺股期貨' in c or c == '外資' or c.lower() == 'nan':
                        continue
                    v = parse_int(c)
                    if v is not None:
                        nums.append(v)
                if len(nums) >= 13 and nums[0] in range(1, 100):
                    nums = nums[1:]
                if len(nums) >= 12:
                    result.update({'trade_long_contracts':nums[0],'trade_short_contracts':nums[2],'trade_net_contracts':nums[4],'oi_long_contracts':nums[6],'oi_short_contracts':nums[8],'oi_net_contracts':nums[10]})
                    found = True
                    break
            if found:
                break
        if not found:
            raise ValueError('TAIFEX 臺股期貨/外資 row not parsed')
        status = 'ok'
    except Exception as e:
        print('TAIFEX positioning', e)
        status = 'unavailable'
    save('positioning.json', {'as_of':datetime.now(timezone.utc).isoformat(),'source':'TAIFEX 三大法人-區分各期貨契約','source_url':url,'status':status,'tx_foreign':result})


# ---------- News ----------
PREFERRED_SOURCES = {
    '鉅亨網':100,'Anue鉅亨':100,'經濟日報':98,'自由財經':96,'路透':95,'Reuters':95,
    '彭博':93,'Bloomberg':93,'華爾街日報':92,'Wall Street Journal':92,'WSJ':92,
    '金融時報':90,'Financial Times':90,'工商時報':86,'MoneyDJ':84,'Yahoo奇摩股市':82,
    '中央社':80,'CNBC':78,'MarketWatch':76,'財訊':74,'今周刊':72,
}
MARKET_IMPACT_TERMS = {
    'fed':28,'fomc':30,'聯準會':30,'利率':22,'升息':24,'降息':24,'treasury':24,'美債':28,'殖利率':24,
    'cpi':28,'pce':28,'ppi':20,'非農':28,'gdp':20,'oil':24,'brent':28,'wti':26,'原油':28,'油價':28,'opec':24,
    'gold':20,'黃金':22,'日銀':22,'boj':22,'ecb':20,'央行':20,'tsmc':22,'台積電':22,'nvidia':22,'半導體':20,
    'ai':18,'china':18,'中國':18,'台股':18,'美股':18,'nasdaq':16,'標普':16,
}


def clean_news_title(value):
    text = BeautifulSoup(html.unescape(str(value or '')), 'html.parser').get_text(' ', strip=True)
    text = re.sub(r'\s+', ' ', text).strip()
    known = '|'.join(re.escape(k) for k in sorted(PREFERRED_SOURCES, key=len, reverse=True))
    return re.sub(rf'\s+-\s+(?:{known})\s*$', '', text, flags=re.I).strip()


def news_key(title):
    return re.sub(r'[\W_]+', '', clean_news_title(title).lower(), flags=re.UNICODE)[:180]


def source_score(source):
    s = (source or '').lower()
    return max([v for k, v in PREFERRED_SOURCES.items() if k.lower() in s] or [0])


def clean_summary(raw, title):
    txt = BeautifulSoup(html.unescape(str(raw or '')), 'html.parser').get_text(' ', strip=True)
    txt = re.sub(r'\s+', ' ', txt).strip()
    if not txt or txt.lower() == title.lower():
        return ''
    return txt[:220].rstrip(' ,;，；') + ('…' if len(txt) > 220 else '')


def google_candidates(query):
    url = 'https://news.google.com/rss/search?q=' + requests.utils.quote(f'{query} when:3d') + '&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
    r = get_http(url, headers={'Accept': 'application/rss+xml,application/xml,text/xml,*/*'})
    feed = feedparser.parse(r.content)
    out = []
    for i, e in enumerate(feed.entries[:50]):
        title = clean_news_title(e.get('title', ''))
        if not title:
            continue
        source = e.source.get('title', '') if isinstance(e.get('source'), dict) else ''
        out.append({'title':title,'summary':clean_summary(e.get('summary') or e.get('description') or '', title),'source':source or 'Google News','url':e.get('link','#'),'published':e.get('published',''),'score':source_score(source)+max(0,50-i)+(20 if re.search(r'[\u4e00-\u9fff]',title) else 0),'provider':'Google News'})
    return out


def bing_candidates(query):
    url = 'https://www.bing.com/news/search?q=' + requests.utils.quote(query) + '&format=rss&setlang=zh-tw'
    r = get_http(url, headers={'Accept': 'application/rss+xml,application/xml,text/xml,*/*'})
    feed = feedparser.parse(r.content)
    out = []
    for i, e in enumerate(feed.entries[:40]):
        title = clean_news_title(e.get('title', ''))
        if not title:
            continue
        source = e.source.get('title', '') if isinstance(e.get('source'), dict) else ''
        out.append({'title':title,'summary':clean_summary(e.get('summary') or e.get('description') or '', title),'source':source or 'Bing News','url':e.get('link','#'),'published':e.get('published',''),'score':source_score(source)+max(0,35-i)+(18 if re.search(r'[\u4e00-\u9fff]',title) else 0),'provider':'Bing News'})
    return out


def impact_score(title, summary=''):
    s = (str(title or '') + ' ' + str(summary or '')).lower()
    return min(sum(v for k, v in MARKET_IMPACT_TERMS.items() if k.lower() in s), 120)


def topic_hint(text):
    s = str(text or '').lower()
    rules = [('Fed / 利率',('fed','fomc','聯準會','利率','升息','降息')),('美債',('treasury','美債','殖利率','yield')),('能源',('oil','brent','wti','opec','原油','油價','天然氣')),('黃金',('gold','黃金','白銀','貴金屬')),('AI / 半導體',('ai','nvidia','tsmc','台積電','半導體','晶片','openai')),('日本',('boj','日銀','日圓','japan','日本')),('中國',('china','中國','人民幣','人行','pboc')),('台灣',('台股','台灣','台積電','新台幣')),('美股',('美股','nasdaq','標普','dow','s&p'))]
    for label, keys in rules:
        if any(k in s for k in keys):
            return label
    return '全球市場'


def update_news():
    queries = ['全球市場 Fed 美債 油價 黃金 美股 亞洲 台股 AI', '金融市場 央行 通膨 殖利率 原油 半導體 中國 日本 台灣', 'Reuters Bloomberg 財經 市場 利率 油價 AI 台股']
    pool, providers = [], set()
    for q in queries:
        try:
            got = google_candidates(q)
            pool.extend(got)
            if got:
                providers.add('Google News RSS')
        except Exception as e:
            print('Google broad news', e)
        try:
            got = bing_candidates(q)
            pool.extend(got)
            if got:
                providers.add('Bing News RSS')
        except Exception as e:
            print('Bing broad news', e)
    local = {}
    for i, x in enumerate(pool):
        title = clean_news_title(x.get('title', ''))
        k = news_key(title)
        if not title or not k:
            continue
        summary = clean_summary(x.get('summary', ''), title)
        score = source_score(x.get('source','')) + impact_score(title, summary) + max(0,35-min(i,35)) + (15 if re.search(r'[\u4e00-\u9fff]',title) else 0)
        row = {**x, 'title': title, 'summary': summary, 'score': score, 'topic': topic_hint(title + ' ' + summary)}
        if k not in local or score > local[k].get('score', 0):
            local[k] = row
    selected, topic_counts = [], {}
    for x in sorted(local.values(), key=lambda z: z.get('score',0), reverse=True):
        topic = x.get('topic','全球市場')
        if topic_counts.get(topic,0) >= 2:
            continue
        words = set(re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+', x['title'].lower()))
        if any(words and (yw := set(re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+', y['title'].lower()))) and len(words & yw)/max(1,min(len(words),len(yw))) >= .65 for y in selected):
            continue
        selected.append(x)
        topic_counts[topic] = topic_counts.get(topic,0) + 1
        if len(selected) >= 5:
            break
    asset_map = {
        'Fed / 利率':['UST','USD','Equity'],'美債':['UST','USD','Equity'],
        '能源':['WTI / Brent','Inflation','Equity'],'黃金':['Gold','USD','UST'],
        'AI / 半導體':['SOX','Nasdaq','TSM / NVDA'],'日本':['JPY','Nikkei','UST'],
        '中國':['CNH','China Equity','Commodities'],'台灣':['TAIEX','TWD','TSM'],
        '美股':['S&P 500','Nasdaq','UST'],'全球市場':['Global Equity','USD','UST']
    }
    rows = []
    for rank, x in enumerate(selected, 1):
        item = {k:v for k,v in x.items() if k not in ('score','provider')}
        item['rank'] = rank
        item['summary'] = (x.get('summary') or '').strip() or f"主要焦點：{x['title']}。"
        src = min(25, round(source_score(x.get('source','')) / 4))
        imp = min(35, round(impact_score(x.get('title',''), x.get('summary','')) * 35 / 120))
        rec = max(8, 20 - (rank-1)*2)
        diversity = 10 if x.get('topic') != '全球市場' else 6
        readability = 10 if re.search(r'[\\u4e00-\\u9fff]', x.get('title','')) else 6
        item['importance_score'] = min(100, src + imp + rec + diversity + readability)
        item['related_assets'] = asset_map.get(x.get('topic','全球市場'), asset_map['全球市場'])
        reasons = []
        if imp >= 20: reasons.append('高市場影響主題')
        if src >= 20: reasons.append('高品質財經來源')
        if rec >= 16: reasons.append('時效性高')
        if diversity >= 10: reasons.append('具明確資產關聯')
        item['why_selected'] = '、'.join(reasons[:3]) or '依來源品質、時效與市場關聯排序'
        rows.append(item)
    save('news.json', {'as_of':datetime.now(timezone.utc).isoformat(),'source':' + '.join(sorted(providers)) if providers else 'news feeds unavailable','strategy':'Market Brief V1: source quality + recency + market impact + topic diversity + deduplication; rule-based, no AI required','engine':'Market Importance Engine V1','items':rows})


# ---------- Economic calendar ----------
COUNTRY_FLAGS = {'United States':'🇺🇸','美國':'🇺🇸','US':'🇺🇸','Taiwan':'🇹🇼','台灣':'🇹🇼','TW':'🇹🇼','Japan':'🇯🇵','日本':'🇯🇵','JP':'🇯🇵','China':'🇨🇳','中國':'🇨🇳','CN':'🇨🇳','Eurozone':'🇪🇺','歐元區':'🇪🇺','EU':'🇪🇺','Germany':'🇩🇪','德國':'🇩🇪','France':'🇫🇷','法國':'🇫🇷','United Kingdom':'🇬🇧','英國':'🇬🇧','UK':'🇬🇧','South Korea':'🇰🇷','韓國':'🇰🇷','Canada':'🇨🇦','加拿大':'🇨🇦','Australia':'🇦🇺','澳洲':'🇦🇺'}
IMPORTANT_TERMS = 'fomc|fed|聯準會|利率|央行|cpi|pce|ppi|非農|就業|失業|gdp|pmi|ism|零售|retail|consumer price|producer price|payroll|employment|unemployment|gross domestic|inflation|ecb|boj|日銀|台灣央行|人民銀行|pboc|出口|進口|trade balance|industrial production'


def _text(v):
    s = re.sub(r'\s+', ' ', str(v or '')).strip()
    return '' if s in ('--','—','-','N/A','NA') else s


def flag(country):
    c = _text(country)
    for k, v in COUNTRY_FLAGS.items():
        if k.lower() in c.lower():
            return v
    return '🌐'


def canonical_country(country):
    c = _text(country)
    for k, v in {'美國':'United States','台灣':'Taiwan','日本':'Japan','中國':'China','大陸':'China','歐元區':'Eurozone','德國':'Germany','法國':'France','英國':'United Kingdom','韓國':'South Korea','加拿大':'Canada','澳洲':'Australia'}.items():
        if k in c:
            return v
    return c or 'Global'


def event_key(x):
    title = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', str(x.get('title','')).lower())
    return x.get('date',''), title[:100]


def importance(title, value=2):
    try:
        return max(1, min(3, int(value)))
    except Exception:
        return 3 if re.search(IMPORTANT_TERMS, title or '', re.I) else 2


def parse_table_by_headers(soup, source, default_date=None):
    out = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        headers = [_text(x.get_text(' ',strip=True)) for x in rows[0].find_all(['th','td'])]
        joined = '|'.join(headers)
        if not any(k in joined for k in ('數據項目','事件','項目')):
            continue
        def idx(*names):
            return next((i for i,h in enumerate(headers) if any(n in h for n in names)), None)
        i_time, i_country, i_title = idx('時間','台北時間'), idx('國家','地區'), idx('數據項目','事件','項目')
        i_imp, i_actual, i_fcst, i_prev = idx('重要'), idx('結果','實際','Actual'), idx('預估','市場預估','Forecast'), idx('前值','Previous')
        for tr in rows[1:]:
            cells = [_text(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]
            if not cells or i_title is None or i_title >= len(cells):
                continue
            title = cells[i_title]
            if not title or title in ('當日無資料!','當日無資料'):
                continue
            country = canonical_country(cells[i_country] if i_country is not None and i_country < len(cells) else 'Global')
            text = ' '.join(cells)
            date_txt = default_date or datetime.now(TZ8).date().isoformat()
            dm = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', text)
            if dm:
                date_txt = f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
            out.append({'date':date_txt,'time':cells[i_time] if i_time is not None and i_time < len(cells) else '—','title':title,'country':country,'flag':flag(country),'importance':importance(title,cells[i_imp] if i_imp is not None and i_imp < len(cells) else 2),'actual':cells[i_actual] if i_actual is not None and i_actual < len(cells) else '','forecast':cells[i_fcst] if i_fcst is not None and i_fcst < len(cells) else '','previous':cells[i_prev] if i_prev is not None and i_prev < len(cells) else '','source':source})
    return out


def generic_calendar_rows(soup, source, default_country='Global'):
    out = parse_table_by_headers(soup, source)
    now = datetime.now(TZ8)
    for node in soup.find_all(['li','article','tr']):
        txt = re.sub(r'\s+', ' ', node.get_text(' ',strip=True)).strip()
        if len(txt) < 12 or len(txt) > 420 or not re.search(IMPORTANT_TERMS, txt, re.I):
            continue
        dm = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', txt)
        sm = re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})(?!\d)', txt)
        if dm:
            date_txt = f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
        elif sm:
            date_txt = f'{now.year:04d}-{int(sm.group(1)):02d}-{int(sm.group(2)):02d}'
        else:
            continue
        tm = re.search(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)', txt)
        time_txt = f'{int(tm.group(1)):02d}:{tm.group(2)}' if tm else '—'
        country = default_country
        for needle, canonical in [('美國','United States'),('台灣','Taiwan'),('日本','Japan'),('中國','China'),('歐元區','Eurozone'),('德國','Germany'),('英國','United Kingdom')]:
            if needle in txt:
                country = canonical
                break
        def grab(label):
            m = re.search(label + r'\s*[:：]?\s*([^\s|]+)', txt, re.I)
            return _text(m.group(1)) if m else ''
        title = txt[:180]
        out.append({'date':date_txt,'time':time_txt,'title':title,'country':country,'flag':flag(country),'importance':importance(title,2),'actual':grab('(?:結果|實際|Actual)'),'forecast':grab('(?:預估|Forecast)'),'previous':grab('(?:前值|Previous)'),'source':source})
    uniq = {}
    for x in out:
        k = event_key(x)
        if k not in uniq or len(x.get('title','')) < len(uniq[k].get('title','')):
            uniq[k] = x
    return list(uniq.values())


def _unfold_ics(text):
    lines = []
    for raw in text.replace('\r\n','\n').split('\n'):
        if raw.startswith((' ','\t')) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def calendar_from_bls(days=60):
    r = get_http('https://www.bls.gov/schedule/news_release/bls.ics', headers={'Accept':'text/calendar,*/*'})
    events, cur = [], None
    for line in _unfold_ics(r.text):
        if line == 'BEGIN:VEVENT':
            cur = {}
        elif line == 'END:VEVENT' and cur is not None:
            events.append(cur); cur = None
        elif cur is not None and ':' in line:
            k, v = line.split(':', 1); cur[k] = v
    now, end, out = datetime.now(TZ8), datetime.now(TZ8)+timedelta(days=days), []
    for e in events:
        dtline = next(((k,v) for k,v in e.items() if k.startswith('DTSTART')), None)
        if not dtline:
            continue
        k, v = dtline
        try:
            if re.fullmatch(r'\d{8}T\d{6}',v):
                tz = ET_ZONE if 'America/New_York' in k else timezone.utc
                dt = datetime.strptime(v,'%Y%m%dT%H%M%S').replace(tzinfo=tz).astimezone(TZ8)
            elif re.fullmatch(r'\d{8}',v):
                dt = datetime.strptime(v,'%Y%m%d').replace(tzinfo=ET_ZONE).astimezone(TZ8)
            else:
                continue
        except Exception:
            continue
        if now-timedelta(hours=2) <= dt <= end:
            out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':(e.get('SUMMARY') or 'BLS release').replace('\\,',',').replace('\\n',' '),'country':'United States','flag':'🇺🇸','importance':3,'actual':'','forecast':'','previous':'','source':'BLS'})
    return out


def calendar_from_bea(days=60):
    r = get_http('https://www.bea.gov/news/schedule')
    soup = BeautifulSoup(r.text,'html.parser')
    now, end, out = datetime.now(TZ8), datetime.now(TZ8)+timedelta(days=days), []
    monthmap = {m:i for i,m in enumerate(['','January','February','March','April','May','June','July','August','September','October','November','December'])}
    for tr in soup.find_all('tr'):
        cells = [c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        joined = ' '.join(cells)
        m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s+(AM|PM)', joined)
        if not m:
            continue
        try:
            dt = datetime.strptime(f'{now.year}-{monthmap[m.group(1)]:02d}-{int(m.group(2)):02d} {m.group(3)} {m.group(4)}','%Y-%m-%d %I:%M %p').replace(tzinfo=ET_ZONE).astimezone(TZ8)
        except Exception:
            continue
        if now-timedelta(hours=2) <= dt <= end and cells:
            out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':cells[-1],'country':'United States','flag':'🇺🇸','importance':3,'actual':'','forecast':'','previous':'','source':'BEA'})
    return out


def calendar_from_fomc(days=60):
    now, end, out = datetime.now(TZ8), datetime.now(TZ8)+timedelta(days=days), []
    for d in FOMC_DATES:
        dt = datetime(d.year,d.month,d.day,14,0,tzinfo=ET_ZONE).astimezone(TZ8)
        if now-timedelta(hours=2) <= dt <= end:
            out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':'FOMC 利率決議 / 記者會','country':'United States','flag':'🇺🇸','importance':3,'actual':'','forecast':'','previous':'','source':'Federal Reserve'})
    return out


def calendar_from_cnyes():
    rows = []
    for url in ['https://www.cnyes.com/economy/country/US','https://www.cnyes.com/economy/country/TW','https://www.cnyes.com/economy/country/JP','https://www.cnyes.com/economy/country/CN','https://www.cnyes.com/economy/events']:
        try:
            rows.extend(parse_table_by_headers(BeautifulSoup(get_http(url).text,'html.parser'),'鉅亨網'))
        except Exception as e:
            print('calendar Cnyes', url, e)
    return rows


def calendar_from_macromicro():
    return generic_calendar_rows(BeautifulSoup(get_http('https://www.macromicro.me/calendar').text,'html.parser'),'財經M平方')


def calendar_from_sinopac():
    base = 'https://www.spf.com.tw/sinopacSPF/research/list_180fdcacb04000005fa4adef23dd5137.do'
    r = get_http(base)
    soup = BeautifulSoup(r.text,'html.parser')
    rows = generic_calendar_rows(soup,'永豐期貨')
    for a in soup.find_all('a',href=True):
        if '財經行事曆' not in a.get_text(' ',strip=True):
            continue
        try:
            rows.extend(generic_calendar_rows(BeautifulSoup(get_http(urljoin(base,a['href'])).text,'html.parser'),'永豐期貨'))
        except Exception:
            pass
        if len(rows) >= 30:
            break
    return rows


def calendar_from_ctee():
    return parse_table_by_headers(BeautifulSoup(get_http('https://ctee.com.tw/stock/calendar').text,'html.parser'),'工商時報')


def calendar_from_cbc_official():
    out = []
    index = 'https://www.cbc.gov.tw/tw/lp-357-1.html'
    try:
        soup = BeautifulSoup(get_http(index).text,'html.parser')
        links = [urljoin(index,a['href']) for a in soup.find_all('a',href=True) if '中央銀行理監事聯席會議預定日期' in re.sub(r'\s+',' ',a.get_text(' ',strip=True))]
        for url in (links[:3] or [index]):
            text = BeautifulSoup(get_http(url).text,'html.parser').get_text(' ',strip=True)
            for ry, mm, dd in re.findall(r'(?<!\d)(1\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', text):
                year = int(ry)+1911
                if year == datetime.now(TZ8).year:
                    out.append({'date':f'{year:04d}-{int(mm):02d}-{int(dd):02d}','time':'—','title':'台灣央行理監事聯席會議 / 會後記者會','country':'Taiwan','flag':'🇹🇼','importance':3,'actual':'','forecast':'','previous':'','source':'中央銀行（台灣）'})
    except Exception as e:
        print('calendar CBC parser', e)
    if not out and datetime.now(TZ8).year == 2026:
        out = [{'date':d,'time':'—','title':'台灣央行理監事聯席會議 / 會後記者會','country':'Taiwan','flag':'🇹🇼','importance':3,'actual':'','forecast':'','previous':'','source':'中央銀行（台灣）官方年度日程'} for d in ('2026-09-17','2026-12-17')]
    return out


def calendar_from_boj_official():
    out = []
    try:
        text = re.sub(r'\s+',' ',BeautifulSoup(get_http('https://www.boj.or.jp/en/mopo/mpmsche_minu/').text,'html.parser').get_text(' ',strip=True))
        months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sept':9,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        for mon, _start, endday in re.findall(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.\s*(\d{1,2})\s*,\s*(\d{1,2})', text):
            out.append({'date':f'{datetime.now(TZ8).year:04d}-{months[mon]:02d}-{int(endday):02d}','time':'—','title':'日本銀行金融政策決定會合 / 政策聲明','country':'Japan','flag':'🇯🇵','importance':3,'actual':'','forecast':'','previous':'','source':'Bank of Japan'})
    except Exception as e:
        print('calendar BOJ parser', e)
    if not out and datetime.now(TZ8).year == 2026:
        out = [{'date':d,'time':'—','title':'日本銀行金融政策決定會合 / 政策聲明','country':'Japan','flag':'🇯🇵','importance':3,'actual':'','forecast':'','previous':'','source':'Bank of Japan 官方年度日程'} for d in ('2026-09-18','2026-10-30','2026-12-18')]
    return out


def calendar_from_ecb_official():
    out = []
    try:
        soup = BeautifulSoup(get_http('https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html').text,'html.parser')
        for node in soup.find_all(['tr','li','p']):
            txt = re.sub(r'\s+',' ',node.get_text(' ',strip=True)).strip()
            if 'monetary policy meeting' not in txt.lower() or ('day 1' in txt.lower() and 'day 2' not in txt.lower()):
                continue
            m = re.search(r'(?<!\d)(\d{2})/(\d{2})/(20\d{2})(?!\d)', txt)
            if m:
                out.append({'date':f'{m.group(3)}-{m.group(2)}-{m.group(1)}','time':'—','title':'ECB 貨幣政策會議 / 利率決議與記者會','country':'Eurozone','flag':'🇪🇺','importance':3,'actual':'','forecast':'','previous':'','source':'European Central Bank'})
    except Exception as e:
        print('calendar ECB parser', e)
    if not out and datetime.now(TZ8).year == 2026:
        out = [{'date':d,'time':'—','title':'ECB 貨幣政策會議 / 利率決議與記者會','country':'Eurozone','flag':'🇪🇺','importance':3,'actual':'','forecast':'','previous':'','source':'European Central Bank 官方年度日程'} for d in ('2026-10-29','2026-12-17')]
    return out


def verified_eurostat_releases():
    if datetime.now(TZ8).year != 2026:
        return []
    rows = [('2026-09-17','17:00','歐元區 HICP / CPI（8月終值）',3),('2026-10-02','17:00','歐元區 HICP / CPI（9月初值）',3),('2026-10-05','17:00','歐元區工業生產者物價 PPI',2),('2026-10-30','18:00','歐元區 GDP（第3季初值）',3)]
    return [{'date':d,'time':t,'title':title,'country':'Eurozone','flag':'🇪🇺','importance':imp,'actual':'','forecast':'','previous':'','source':'Eurostat'} for d,t,title,imp in rows]


def update_calendar():
    now, end, layers = datetime.now(TZ8), datetime.now(TZ8)+timedelta(days=60), []
    def add(name, fn, priority):
        try:
            got = fn() or []
            print('calendar', name, 'rows', len(got))
            layers.append((priority,name,got))
        except Exception as e:
            print('calendar', name, 'failed', e)
            layers.append((priority,name,[]))
    add('BLS', calendar_from_bls, 1); add('BEA', calendar_from_bea, 1); add('Federal Reserve', calendar_from_fomc, 1)
    add('中央銀行（台灣）', calendar_from_cbc_official, 1); add('Bank of Japan', calendar_from_boj_official, 1); add('European Central Bank', calendar_from_ecb_official, 1); add('Eurostat', verified_eurostat_releases, 1)
    add('鉅亨網', calendar_from_cnyes, 2); add('財經M平方', calendar_from_macromicro, 3); add('永豐期貨', calendar_from_sinopac, 4); add('工商時報', calendar_from_ctee, 5)
    merged = {}
    for priority, _name, items in sorted(layers,key=lambda z:z[0],reverse=True):
        for raw in items:
            x = dict(raw)
            try:
                d = datetime.fromisoformat(x.get('date','')).replace(tzinfo=TZ8)
            except Exception:
                continue
            if not (now-timedelta(days=1) <= d <= end):
                continue
            title = x.get('title','')
            if not re.search(IMPORTANT_TERMS,title,re.I) and int(x.get('importance') or 1) < 2:
                continue
            x['country'] = x.get('country') or 'Global'; x['flag'] = x.get('flag') or flag(x['country']); x['importance'] = importance(title,x.get('importance',2))
            k = event_key(x); old = merged.get(k)
            if old is None:
                x['_priority'] = priority; merged[k] = x; continue
            better = x if priority < old.get('_priority',99) else old
            other = old if better is x else x
            for fld in ('actual','forecast','previous','time','country','flag'):
                if (not _text(better.get(fld)) or better.get(fld) == '—') and _text(other.get(fld)) and other.get(fld) != '—':
                    better[fld] = other[fld]
            better['importance'] = max(int(better.get('importance') or 1),int(other.get('importance') or 1))
            sources = [s.strip() for s in (better.get('source','')+' / '+other.get('source','')).split('/') if s.strip()]
            better['source'] = ' / '.join(dict.fromkeys(sources)); better['_priority'] = min(priority,old.get('_priority',99)); merged[k] = better
    items = []
    for x in merged.values():
        x.pop('_priority',None); items.append(x)
    items.sort(key=lambda z:(z.get('date',''),z.get('time','99:99'),-int(z.get('importance') or 1)))
    active = [name for _,name,got in layers if got]
    save('calendar.json', {'as_of':datetime.now(timezone.utc).isoformat(),'status':'ok' if items else 'unavailable','source':' + '.join(dict.fromkeys(active)) if active else 'calendar sources unavailable','source_mode':'Official global central banks + official statistics + market-calendar enrichment','window_days':60,'cost_note':'央行動態以 Fed、台灣央行、BOJ、ECB 官方日程為優先；重要數據以 BLS、BEA、Eurostat 及鉅亨／M平方等來源補強。','items':items[:100]})
    if not items:
        raise RuntimeError('calendar generated zero usable events')


# ---------- Brief ----------
def market_recap(market, stocks, rates, news, calendar):
    indices = [x for x in market.get('indices',[]) if x.get('change_pct') is not None]
    st = [x for x in stocks.get('stocks',[]) if x.get('change_pct') is not None]
    avg = sum(x['change_pct'] for x in indices)/len(indices) if indices else 0
    vix = next((x for x in market.get('pulse',[]) if x.get('symbol') == '^VIX'), None)
    score = max(0,min(100,round(50+avg*12+(-8 if vix and vix.get('price',0)>=25 else 5 if vix and vix.get('price') is not None and vix['price']<16 else 0))))
    label = '偏多' if score >= 62 else '偏空' if score <= 38 else '中性'
    r10 = next((x for x in rates.get('rates',[]) if x.get('series') == 'DGS10'), None)
    curve = next((x for x in rates.get('rates',[]) if x.get('series') == '2S10S'), None)
    dxy = next((x for x in market.get('fx',[]) if x.get('name') == 'DXY'), None)
    best = max(st,key=lambda x:x['change_pct'],default=None); worst = min(st,key=lambda x:x['change_pct'],default=None)
    bullets = []
    if indices: bullets.append(f"主要美股指數平均變動 {avg:+.2f}%。")
    if r10 and r10.get('value') is not None: bullets.append(f"美債10年殖利率 {r10['value']:.3f}%，日變動 {(r10.get('change_bps') or 0):+.1f} bps。")
    if best and worst: bullets.append(f"自選股強勢 {best.get('label',best['symbol'])} {best['change_pct']:+.2f}%；較弱 {worst.get('label',worst['symbol'])} {worst['change_pct']:+.2f}%。")
    if curve and curve.get('value') is not None: bullets.append(f"2Y10Y 利差 {curve['value']:+.1f} bps。")
    yesterday = [f"美股主要指數平均 {avg:+.2f}%，風險情緒{label}。"]
    if r10 and r10.get('value') is not None: yesterday.append(f"10Y 美債殖利率 {r10['value']:.3f}%。")
    if dxy and dxy.get('change_pct') is not None: yesterday.append(f"DXY 日變動 {dxy['change_pct']:+.2f}%。")
    watch = []
    if r10: watch.append(f"利率：10Y 日變動 {(r10.get('change_bps') or 0):+.1f} bps。")
    if dxy: watch.append(f"美元：DXY 日變動 {(dxy.get('change_pct') or 0):+.2f}%。")
    if vix: watch.append(f"波動率：VIX {(vix.get('price') or 0):.2f}。")
    if curve: watch.append(f"曲線：2Y10Y {(curve.get('value') or 0):+.1f} bps。")
    return {'mode':'rules','headline':f'市場風險情緒：{label}','bullets':bullets[:4],'risk_score':score,'risk_label':label,'yesterday_top':yesterday[:3],'today_top':[],'todays_watch':watch[:4]}


def update_brief():
    m, s, r, n, c = [load_json(x) for x in ('market.json','stocks.json','rates.json','news.json','calendar.json')]
    out = market_recap(m,s,r,n,c)
    today = datetime.now(TZ8).date().isoformat()
    events = [x for x in c.get('items',[]) if x.get('date') == today]
    events.sort(key=lambda x:(-int(x.get('importance') or 1),x.get('time','99:99')))
    today_top = [f"{x.get('flag','')} {x.get('time','—')} {x.get('country','')}｜{x.get('title','重要經濟事件')}".strip() for x in events[:3]]
    if len(today_top) < 3:
        for x in n.get('items',[]):
            if len(today_top) >= 3:
                break
            pub = x.get('published','')
            if not pub or not x.get('title'):
                continue
            try:
                dt = parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(TZ8)
            except Exception:
                continue
            if dt.date().isoformat() == today:
                today_top.append('新聞｜' + x['title'])
    if not today_top:
        today_top = ['今日暫無已確認的高重要性事件；不以未來日期事件補位。']
    out['today_top'] = today_top[:3]
    out['today_date_taipei'] = today
    out['today_filter'] = 'calendar date == Taipei today; news published date == Taipei today; future events forbidden'
    out['as_of'] = datetime.now(timezone.utc).isoformat()
    save('brief.json',out)
