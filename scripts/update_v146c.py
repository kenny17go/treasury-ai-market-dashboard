from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup

# IMPORTANT: keep module aliases explicit.  Previous versions used wildcard imports
# and the name `prev` was silently overwritten by an older module in the import
# chain.  That made Calendar / Brief fail while the robust runner restored old JSON.
import update_data as base
import update_v142 as v142
import update_v143 as v143
import update_v144 as v144
import update_v146 as v146
import update_v146a as v146a

DATA = base.DATA
TZ8 = base.TZ8
load_cfg = base.load_cfg
load_json = base.load_json
save = base.save

# Stable stage bindings used by run_update.py.
update_market = v144.update_market
update_stocks = base.update_stocks
update_rates = v142.update_rates
update_news = v146a.update_news
update_positioning = base.update_positioning
update_professional = v142.update_professional

IMPORTANT_TERMS = v146.IMPORTANT_TERMS


def _clean(v):
    s = re.sub(r'\s+', ' ', str(v or '')).strip()
    return '' if s in ('--', '—', '-', 'N/A', 'NA') else s


def _flag(country):
    return v146._flag(country)


def _event_key(x):
    title = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', str(x.get('title', '')).lower())
    return (x.get('date', ''), title[:100])


def _importance(title, value=3):
    try:
        return max(1, min(3, int(value)))
    except Exception:
        return 3 if re.search(IMPORTANT_TERMS, title or '', re.I) else 2


def _generic_calendar_rows(soup, source, default_country='Global'):
    """Best-effort parser for finance-calendar pages that may expose tables/cards."""
    out = []
    now = datetime.now(TZ8)

    # Table parser first.
    try:
        out.extend(v146._parse_table_by_headers(soup, source))
    except Exception:
        pass

    # Card/list fallback.  Only retain market-moving terms.
    for node in soup.find_all(['li', 'article', 'tr']):
        txt = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
        if len(txt) < 12 or len(txt) > 420 or not re.search(IMPORTANT_TERMS, txt, re.I):
            continue
        dm = re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', txt)
        sm = re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})(?!\d)', txt)
        if dm:
            date = f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
        elif sm:
            date = f'{now.year:04d}-{int(sm.group(1)):02d}-{int(sm.group(2)):02d}'
        else:
            continue
        tm = re.search(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)', txt)
        time_txt = f'{int(tm.group(1)):02d}:{tm.group(2)}' if tm else '—'
        country = default_country
        cmap = [('美國','United States'),('台灣','Taiwan'),('日本','Japan'),('中國','China'),('歐元區','Eurozone'),('德國','Germany'),('英國','United Kingdom')]
        for needle, canonical in cmap:
            if needle in txt:
                country = canonical
                break
        actual = forecast = previous = ''
        m = re.search(r'(?:結果|實際|Actual)\s*[:：]?\s*([^\s|]+)', txt, re.I)
        if m: actual = _clean(m.group(1))
        m = re.search(r'(?:預估|Forecast)\s*[:：]?\s*([^\s|]+)', txt, re.I)
        if m: forecast = _clean(m.group(1))
        m = re.search(r'(?:前值|Previous)\s*[:：]?\s*([^\s|]+)', txt, re.I)
        if m: previous = _clean(m.group(1))
        title = txt[:180]
        out.append({'date':date,'time':time_txt,'title':title,'country':country,'flag':_flag(country),
                    'importance':_importance(title),'actual':actual,'forecast':forecast,'previous':previous,'source':source})

    uniq = {}
    for x in out:
        k = _event_key(x)
        if k not in uniq or len(x.get('title','')) < len(uniq[k].get('title','')):
            uniq[k] = x
    return list(uniq.values())


def calendar_from_cnyes():
    # Use V1.4.6's explicit Cnyes parser; failures simply return no rows.
    return v146.calendar_from_cnyes()


def calendar_from_macromicro():
    url = 'https://www.macromicro.me/calendar'
    r = v142.get142(url, headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    return _generic_calendar_rows(BeautifulSoup(r.text, 'html.parser'), '財經M平方')


def calendar_from_sinopac():
    base_url = 'https://www.spf.com.tw/sinopacSPF/research/list_180fdcacb04000005fa4adef23dd5137.do'
    r = v142.get142(base_url, headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    soup = BeautifulSoup(r.text, 'html.parser')
    rows = _generic_calendar_rows(soup, '永豐期貨')
    for a in soup.find_all('a', href=True):
        if '財經行事曆' not in a.get_text(' ', strip=True):
            continue
        try:
            rr = v142.get142(urljoin(base_url, a['href']), headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
            rows.extend(_generic_calendar_rows(BeautifulSoup(rr.text, 'html.parser'), '永豐期貨'))
        except Exception:
            pass
        if len(rows) >= 30:
            break
    return rows


def calendar_from_ctee():
    return v146.calendar_from_ctee()


def calendar_from_cbc_official():
    """Taiwan CBC meetings, with official-page parsing plus verified 2026 fallback."""
    out = []
    index = 'https://www.cbc.gov.tw/tw/lp-357-1.html'
    try:
        r = v142.get142(index, headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            if '中央銀行理監事聯席會議預定日期' in re.sub(r'\s+', ' ', a.get_text(' ', strip=True)):
                links.append(urljoin(index, a['href']))
        for url in (links[:3] or [index]):
            rr = v142.get142(url, headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
            text = BeautifulSoup(rr.text, 'html.parser').get_text(' ', strip=True)
            for ry, mm, dd in re.findall(r'(?<!\d)(1\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', text):
                year = int(ry) + 1911
                if year != datetime.now(TZ8).year: continue
                out.append({'date':f'{year:04d}-{int(mm):02d}-{int(dd):02d}','time':'—','title':'台灣央行理監事聯席會議 / 會後記者會','country':'Taiwan','flag':'🇹🇼','importance':3,'actual':'','forecast':'','previous':'','source':'中央銀行（台灣）'})
    except Exception as e:
        print('calendar CBC parser', e)

    if not out and datetime.now(TZ8).year == 2026:
        for date in ('2026-09-17','2026-12-17'):
            out.append({'date':date,'time':'—','title':'台灣央行理監事聯席會議 / 會後記者會','country':'Taiwan','flag':'🇹🇼','importance':3,'actual':'','forecast':'','previous':'','source':'中央銀行（台灣）官方年度日程'})
    return out


def calendar_from_boj_official():
    """BOJ monetary-policy meetings; verified 2026 dates backstop parser drift."""
    out = []
    url = 'https://www.boj.or.jp/en/mopo/mpmsche_minu/'
    try:
        r = v142.get142(url, headers={'Accept-Language':'en,ja;q=0.8'})
        text = re.sub(r'\s+', ' ', BeautifulSoup(r.text, 'html.parser').get_text(' ', strip=True))
        # Match ranges such as Sep. 17, 18 (Thu., Fri.) and use the decision day.
        months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sept':9,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        for mon, _start, endday in re.findall(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.\s*(\d{1,2})\s*,\s*(\d{1,2})', text):
            out.append({'date':f'{datetime.now(TZ8).year:04d}-{months[mon]:02d}-{int(endday):02d}','time':'—','title':'日本銀行金融政策決定會合 / 政策聲明','country':'Japan','flag':'🇯🇵','importance':3,'actual':'','forecast':'','previous':'','source':'Bank of Japan'})
    except Exception as e:
        print('calendar BOJ parser', e)
    if not out and datetime.now(TZ8).year == 2026:
        for date in ('2026-09-18','2026-10-30','2026-12-18'):
            out.append({'date':date,'time':'—','title':'日本銀行金融政策決定會合 / 政策聲明','country':'Japan','flag':'🇯🇵','importance':3,'actual':'','forecast':'','previous':'','source':'Bank of Japan 官方年度日程'})
    return out


def calendar_from_ecb_official():
    """ECB monetary-policy decision dates, with verified 2026 fallback."""
    out = []
    url = 'https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html'
    try:
        r = v142.get142(url, headers={'Accept-Language':'en,zh-TW;q=0.8'})
        soup = BeautifulSoup(r.text, 'html.parser')
        for node in soup.find_all(['tr','li','p']):
            txt = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
            if 'monetary policy meeting' not in txt.lower(): continue
            if 'day 1' in txt.lower() and 'day 2' not in txt.lower(): continue
            m = re.search(r'(?<!\d)(\d{2})/(\d{2})/(20\d{2})(?!\d)', txt)
            if not m: continue
            out.append({'date':f'{m.group(3)}-{m.group(2)}-{m.group(1)}','time':'—','title':'ECB 貨幣政策會議 / 利率決議與記者會','country':'Eurozone','flag':'🇪🇺','importance':3,'actual':'','forecast':'','previous':'','source':'European Central Bank'})
    except Exception as e:
        print('calendar ECB parser', e)
    if not out and datetime.now(TZ8).year == 2026:
        for date in ('2026-10-29','2026-12-17'):
            out.append({'date':date,'time':'—','title':'ECB 貨幣政策會議 / 利率決議與記者會','country':'Eurozone','flag':'🇪🇺','importance':3,'actual':'','forecast':'','previous':'','source':'European Central Bank 官方年度日程'})
    return out


def verified_eurostat_releases():
    """Small verified backstop for high-impact Eurostat releases in the current window."""
    if datetime.now(TZ8).year != 2026:
        return []
    rows = [
        ('2026-09-17','17:00','歐元區 HICP / CPI（8月終值）',3,'Eurostat'),
        ('2026-10-02','17:00','歐元區 HICP / CPI（9月初值）',3,'Eurostat'),
        ('2026-10-05','17:00','歐元區工業生產者物價 PPI',2,'Eurostat'),
        ('2026-10-30','18:00','歐元區 GDP（第3季初值）',3,'Eurostat'),
    ]
    return [{'date':d,'time':t,'title':title,'country':'Eurozone','flag':'🇪🇺','importance':imp,'actual':'','forecast':'','previous':'','source':src} for d,t,title,imp,src in rows]


def update_calendar():
    now = datetime.now(TZ8)
    end = now + timedelta(days=60)
    layers = []

    def add(name, fn, priority):
        try:
            got = fn() or []
            print('calendar', name, 'rows', len(got))
            layers.append((priority, name, got))
        except Exception as e:
            print('calendar', name, 'failed', e)
            layers.append((priority, name, []))

    # Official central banks / statistical agencies first.
    add('BLS', v143.calendar_from_bls, 1)
    add('BEA', v143.calendar_from_bea, 1)
    add('Federal Reserve', v143.calendar_from_fomc, 1)
    add('中央銀行（台灣）', calendar_from_cbc_official, 1)
    add('Bank of Japan', calendar_from_boj_official, 1)
    add('European Central Bank', calendar_from_ecb_official, 1)
    add('Eurostat', verified_eurostat_releases, 1)

    # Market-calendar enrichment / cross checks.
    add('鉅亨網', calendar_from_cnyes, 2)
    add('財經M平方', calendar_from_macromicro, 3)
    add('永豐期貨', calendar_from_sinopac, 4)
    add('工商時報', calendar_from_ctee, 5)

    merged = {}
    for priority, _name, items in sorted(layers, key=lambda z: z[0], reverse=True):
        for raw in items:
            x = dict(raw)
            try:
                d = datetime.fromisoformat(x.get('date','')).replace(tzinfo=TZ8)
            except Exception:
                continue
            if not (now - timedelta(days=1) <= d <= end):
                continue
            title = x.get('title','')
            if not re.search(IMPORTANT_TERMS, title, re.I) and int(x.get('importance') or 1) < 2:
                continue
            x['country'] = x.get('country') or 'Global'
            x['flag'] = x.get('flag') or _flag(x['country'])
            x['importance'] = _importance(title, x.get('importance', 2))
            k = _event_key(x)
            old = merged.get(k)
            if old is None:
                x['_priority'] = priority
                merged[k] = x
                continue
            better = x if priority < old.get('_priority', 99) else old
            other = old if better is x else x
            for fld in ('actual','forecast','previous','time','country','flag'):
                if (not _clean(better.get(fld)) or better.get(fld) == '—') and _clean(other.get(fld)) and other.get(fld) != '—':
                    better[fld] = other[fld]
            better['importance'] = max(int(better.get('importance') or 1), int(other.get('importance') or 1))
            sources = [s.strip() for s in (better.get('source','') + ' / ' + other.get('source','')).split('/') if s.strip()]
            better['source'] = ' / '.join(dict.fromkeys(sources))
            better['_priority'] = min(priority, old.get('_priority', 99))
            merged[k] = better

    items = []
    for x in merged.values():
        x.pop('_priority', None)
        items.append(x)
    items.sort(key=lambda z: (z.get('date',''), z.get('time','99:99'), -int(z.get('importance') or 1)))
    active = [name for _, name, got in layers if got]
    save('calendar.json', {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'status': 'ok' if items else 'unavailable',
        'source': ' + '.join(dict.fromkeys(active)) if active else 'calendar sources unavailable',
        'source_mode': 'Official global central banks + official statistics + market-calendar enrichment',
        'window_days': 60,
        'cost_note': '央行動態以 Fed、台灣央行、BOJ、ECB 官方日程為優先；重要數據以 BLS、BEA、Eurostat 及鉅亨／M平方等來源補強，永豐期貨與工商時報交叉參考。',
        'items': items[:100]
    })
    if not items:
        raise RuntimeError('calendar generated zero usable events')


def update_brief():
    m, s, r, n, c = [load_json(x) for x in ('market.json','stocks.json','rates.json','news.json','calendar.json')]
    out = base.market_recap(m, s, r, n, c)
    today = datetime.now(TZ8).date().isoformat()

    todays_events = [x for x in (c.get('items') or []) if x.get('date') == today]
    todays_events.sort(key=lambda x: (-int(x.get('importance') or 1), x.get('time','99:99')))
    today_top = [f"{x.get('flag','')} {x.get('time','—')} {x.get('country','')}｜{x.get('title','重要經濟事件')}".strip() for x in todays_events[:3]]

    # Fill only with news PUBLISHED TODAY in Taipei.  Never borrow future calendar rows.
    if len(today_top) < 3:
        for x in n.get('items', []):
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
    save('brief.json', out)
