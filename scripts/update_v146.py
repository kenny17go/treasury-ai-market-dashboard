from __future__ import annotations
from datetime import datetime, timedelta, timezone
import re
from bs4 import BeautifulSoup
import update_v145 as prev
from update_v145 import *

COUNTRY_FLAGS = {
    'United States':'🇺🇸','美國':'🇺🇸','US':'🇺🇸',
    'Taiwan':'🇹🇼','台灣':'🇹🇼','TW':'🇹🇼',
    'Japan':'🇯🇵','日本':'🇯🇵','JP':'🇯🇵',
    'China':'🇨🇳','中國':'🇨🇳','CN':'🇨🇳',
    'Eurozone':'🇪🇺','歐元區':'🇪🇺','EU':'🇪🇺',
    'Germany':'🇩🇪','德國':'🇩🇪', 'France':'🇫🇷','法國':'🇫🇷',
    'United Kingdom':'🇬🇧','英國':'🇬🇧','UK':'🇬🇧',
    'South Korea':'🇰🇷','韓國':'🇰🇷','KR':'🇰🇷',
    'Canada':'🇨🇦','加拿大':'🇨🇦','CA':'🇨🇦',
    'Australia':'🇦🇺','澳洲':'🇦🇺','AU':'🇦🇺'
}

IMPORTANT_TERMS = (
    'fomc|fed|聯準會|利率|央行|cpi|pce|ppi|非農|就業|失業|gdp|pmi|ism|零售|retail|'
    'consumer price|producer price|payroll|employment|unemployment|gross domestic|inflation|'
    'ecb|boj|日銀|台灣央行|人民銀行|pboc|出口|進口|trade balance|industrial production'
)


def _clean(v):
    s=re.sub(r'\s+',' ',str(v or '')).strip()
    return '' if s in ('--','—','-','N/A','NA') else s


def _importance(v, title=''):
    s=str(v or '').strip().lower()
    # Cnyes commonly renders importance with stars/icons; preserve useful text if present.
    digits=re.findall(r'[1-3]',s)
    if digits: return max(1,min(3,int(digits[0])))
    if any(x in s for x in ('high','高','★★★','●●●')): return 3
    if any(x in s for x in ('medium','中','★★','●●')): return 2
    if re.search(IMPORTANT_TERMS,title,re.I): return 3
    return 1


def _flag(country):
    c=_clean(country)
    for k,v in COUNTRY_FLAGS.items():
        if k.lower() in c.lower(): return v
    return '🌐'


def _canonical_country(country):
    c=_clean(country)
    maps={
        '美國':'United States','台灣':'Taiwan','日本':'Japan','中國':'China','大陸':'China',
        '歐元區':'Eurozone','德國':'Germany','法國':'France','英國':'United Kingdom',
        '韓國':'South Korea','加拿大':'Canada','澳洲':'Australia'
    }
    for k,v in maps.items():
        if k in c: return v
    return c or 'Global'


def _event_key(x):
    title=re.sub(r'[^a-z0-9\u4e00-\u9fff]+','',str(x.get('title','')).lower())
    # ignore time because the same release can be represented with slightly different timestamps
    return (x.get('date',''), title[:80])


def _parse_table_by_headers(soup, source, default_date=None):
    out=[]
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        if not rows: continue
        headers=[_clean(x.get_text(' ',strip=True)) for x in rows[0].find_all(['th','td'])]
        joined='|'.join(headers)
        if not any(k in joined for k in ('數據項目','事件','項目')): continue
        def idx(*names):
            for i,h in enumerate(headers):
                if any(n in h for n in names): return i
            return None
        i_time=idx('時間','台北時間'); i_country=idx('國家','地區'); i_title=idx('數據項目','事件','項目')
        i_imp=idx('重要'); i_actual=idx('結果','實際','Actual'); i_fcst=idx('預估','市場預估','Forecast'); i_prev=idx('前值','Previous')
        for tr in rows[1:]:
            cells=[_clean(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]
            if not cells or i_title is None or i_title>=len(cells): continue
            title=cells[i_title]
            if not title or title in ('當日無資料!','當日無資料'): continue
            country=cells[i_country] if i_country is not None and i_country<len(cells) else 'Global'
            time_txt=cells[i_time] if i_time is not None and i_time<len(cells) else ''
            # Find a YYYY/MM/DD or MM/DD date in the row when present, otherwise use current Taipei date.
            text=' '.join(cells); date=default_date or datetime.now(TZ8).date().isoformat()
            dm=re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',text)
            if dm: date=f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
            actual=cells[i_actual] if i_actual is not None and i_actual<len(cells) else ''
            forecast=cells[i_fcst] if i_fcst is not None and i_fcst<len(cells) else ''
            previous=cells[i_prev] if i_prev is not None and i_prev<len(cells) else ''
            cc=_canonical_country(country)
            out.append({
                'date':date,'time':time_txt or '—','title':title,'country':cc,'flag':_flag(cc),
                'importance':_importance(cells[i_imp] if i_imp is not None and i_imp<len(cells) else '',title),
                'actual':actual,'forecast':forecast,'previous':previous,'source':source
            })
    return out


def calendar_from_cnyes():
    # Cnyes is the preferred market-calendar layer because it exposes importance,
    # actual, forecast and previous values in Taipei-oriented calendar pages.
    urls=[
        'https://www.cnyes.com/economy/country/US',
        'https://www.cnyes.com/economy/country/TW',
        'https://www.cnyes.com/economy/country/JP',
        'https://www.cnyes.com/economy/country/CN',
        'https://www.cnyes.com/economy/events',
        'https://www.cnyes.com/economy/indicator/Page/schedule.aspx'
    ]
    rows=[]
    for url in urls:
        try:
            r=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
            rows.extend(_parse_table_by_headers(BeautifulSoup(r.text,'html.parser'),'鉅亨網'))
        except Exception as e: print('calendar Cnyes',url,e)
    return rows


def calendar_from_ctee():
    # CTEE is cross-check/fallback only. Its page can block automated requests,
    # therefore failure here must never blank the calendar.
    url='https://ctee.com.tw/stock/calendar'
    r=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    return _parse_table_by_headers(BeautifulSoup(r.text,'html.parser'),'工商時報')


def _official_calendar():
    rows=[]
    for name,fn in [('BLS',calendar_from_bls),('BEA',calendar_from_bea),('Federal Reserve',calendar_from_fomc)]:
        try:
            got=fn();
            for x in got:
                x['flag']=_flag(x.get('country'))
                x['importance']=_importance(x.get('importance'),x.get('title',''))
            rows.extend(got)
        except Exception as e: print('calendar official',name,e)
    return rows


def update_calendar():
    now=datetime.now(TZ8); end=now+timedelta(days=14)
    cnyes=[]; ctee=[]; official=[]
    try: cnyes=calendar_from_cnyes()
    except Exception as e: print('calendar Cnyes stage',e)
    official=_official_calendar()
    try: ctee=calendar_from_ctee()
    except Exception as e: print('calendar CTEE fallback',e)

    # Source preference: Cnyes enriched market calendar -> official -> CTEE cross-check.
    merged={}
    for priority,items in [(3,ctee),(2,official),(1,cnyes)]:
        for x in items:
            try:
                d=datetime.fromisoformat(x.get('date','')).replace(tzinfo=TZ8)
            except Exception: continue
            if not (now-timedelta(days=1) <= d <= end): continue
            if not re.search(IMPORTANT_TERMS,x.get('title',''),re.I) and x.get('importance',1)<2: continue
            x['flag']=x.get('flag') or _flag(x.get('country'))
            k=_event_key(x)
            old=merged.get(k)
            if old is None:
                x['_priority']=priority; merged[k]=x; continue
            # Lower numeric priority is better. Enrich missing fields from secondary sources.
            better=x if priority < old.get('_priority',99) else old
            other=old if better is x else x
            for fld in ('actual','forecast','previous','time','country','flag'):
                if not _clean(better.get(fld)) and _clean(other.get(fld)): better[fld]=other[fld]
            better['importance']=max(int(better.get('importance') or 1),int(other.get('importance') or 1))
            if other.get('source') and other.get('source') not in better.get('source',''):
                better['source']=better.get('source','')+' / '+other.get('source','')
            better['_priority']=min(priority,old.get('_priority',99)); merged[k]=better

    items=[]
    for x in merged.values():
        x.pop('_priority',None); items.append(x)
    items.sort(key=lambda z:(z.get('date',''), z.get('time','99:99'), -int(z.get('importance') or 1)))
    status='ok' if items else 'unavailable'
    source_parts=[]
    if cnyes: source_parts.append('鉅亨網')
    if official: source_parts.append('BLS/BEA/Federal Reserve')
    if ctee: source_parts.append('工商時報')
    save('calendar.json',{
        'as_of':datetime.now(timezone.utc).isoformat(),
        'status':status,
        'source':' + '.join(source_parts) if source_parts else 'calendar sources unavailable',
        'source_mode':'Cnyes + official; CTEE fallback/cross-check',
        'window_days':14,
        'cost_note':'鉅亨網＋官方來源為主；工商時報作備援/交叉參考。重要度為來源標示或規則判定；Actual/Forecast/Previous 以可取得資料為準。',
        'items':items[:50]
    })

# Keep all V1.4.5 market/news behavior, including the 12-theme News Radar.
update_news=prev.update_news
update_market=prev.update_market
