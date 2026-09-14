from __future__ import annotations
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup
import update_v146a as prev
from update_v146a import *

# V1.4.6b
# - Add official Taiwan CBC / BOJ / ECB monetary-policy schedules.
# - Keep important economic data from Cnyes / MacroMicro / US official sources.
# - Fix "今日 3 件事": only today's Taipei-date events may enter the list.


def calendar_from_cbc_official():
    """Taiwan CBC scheduled board meetings from the official CBC site."""
    index='https://www.cbc.gov.tw/tw/lp-357-1.html'
    r=get142(index,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    soup=BeautifulSoup(r.text,'html.parser')
    links=[]
    for a in soup.find_all('a',href=True):
        txt=re.sub(r'\s+',' ',a.get_text(' ',strip=True))
        if '中央銀行理監事聯席會議預定日期' in txt:
            links.append(urljoin(index,a['href']))
    # Current page normally exposes the newest annual schedule first.
    urls=links[:3] or [index]
    now=datetime.now(TZ8); out=[]; seen=set()
    for url in urls:
        try:
            rr=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
            text=BeautifulSoup(rr.text,'html.parser').get_text(' ',strip=True)
            for ry,mm,dd in re.findall(r'(?<!\d)(1\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日',text):
                year=int(ry)+1911
                if year < now.year or year > now.year+1: continue
                date=f'{year:04d}-{int(mm):02d}-{int(dd):02d}'
                if date in seen: continue
                seen.add(date)
                out.append({'date':date,'time':'—','title':'台灣央行理監事聯席會議 / 會後記者會','country':'Taiwan','flag':'🇹🇼','importance':3,'actual':'','forecast':'','previous':'','source':'中央銀行（台灣）'})
        except Exception as e:
            print('calendar CBC',url,e)
    return out


def calendar_from_ecb_official():
    """ECB monetary-policy meeting Day 2 / press-conference dates."""
    url='https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html'
    r=get142(url,headers={'Accept-Language':'en,zh-TW;q=0.8'})
    soup=BeautifulSoup(r.text,'html.parser'); out=[]
    for node in soup.find_all(['tr','li','p','div']):
        txt=re.sub(r'\s+',' ',node.get_text(' ',strip=True)).strip()
        if 'monetary policy meeting' not in txt.lower(): continue
        # Prefer the decision/press-conference day when the page says Day 2.
        if 'day 1' in txt.lower() and 'day 2' not in txt.lower(): continue
        m=re.search(r'(?<!\d)(\d{2})/(\d{2})/(20\d{2})(?!\d)',txt)
        if not m: continue
        date=f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
        out.append({'date':date,'time':'—','title':'ECB 貨幣政策會議 / 利率決議與記者會','country':'Eurozone','flag':'🇪🇺','importance':3,'actual':'','forecast':'','previous':'','source':'European Central Bank'})
    uniq={_event_key(x):x for x in out}
    return list(uniq.values())


def calendar_from_boj_official():
    """BOJ scheduled Monetary Policy Meetings from the official BOJ schedule page."""
    url='https://www.boj.or.jp/en/mopo/mpmsche_minu/'
    r=get142(url,headers={'Accept-Language':'en,ja;q=0.8'})
    soup=BeautifulSoup(r.text,'html.parser'); now=datetime.now(TZ8)
    heading=None
    for h in soup.find_all(['h2','h3','h4']):
        if h.get_text(' ',strip=True)==str(now.year):
            heading=h; break
    table=heading.find_next('table') if heading else soup.find('table')
    if table is None: return []
    months={'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sept':9,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    out=[]
    for tr in table.find_all('tr'):
        cells=[re.sub(r'\s+',' ',c.get_text(' ',strip=True)).strip() for c in tr.find_all(['th','td'])]
        if not cells: continue
        s=cells[0]
        m=re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.\s*(\d{1,2}).*?,\s*(\d{1,2})\s*\(',s)
        if not m: continue
        month=months[m.group(1)]; decision_day=int(m.group(3))
        date=f'{now.year:04d}-{month:02d}-{decision_day:02d}'
        out.append({'date':date,'time':'—','title':'日本銀行金融政策決定會合 / 政策聲明','country':'Japan','flag':'🇯🇵','importance':3,'actual':'','forecast':'','previous':'','source':'Bank of Japan'})
    return out


def update_calendar():
    now=datetime.now(TZ8); end=now+timedelta(days=21)
    layers=[]
    def add(name, fn, priority):
        try:
            got=fn() or []
            layers.append((priority,name,got))
            print('calendar',name,'rows',len(got))
        except Exception as e:
            print('calendar',name,'failed',e); layers.append((priority,name,[]))

    # Aggregated economic-data layers.
    add('鉅亨網', prev.calendar_from_cnyes, 2)
    try:
        official_us=prev._official_calendar() or []
    except Exception as e:
        print('calendar official US failed',e); official_us=[]
    layers.append((1,'BLS/BEA/Federal Reserve',official_us))
    add('財經M平方', prev.calendar_from_macromicro, 3)
    add('永豐期貨', prev.calendar_from_sinopac, 4)
    add('工商時報', prev.calendar_from_ctee, 5)

    # Official central-bank layers for Taiwan, Japan and the euro area.
    add('中央銀行（台灣）', calendar_from_cbc_official, 1)
    add('Bank of Japan', calendar_from_boj_official, 1)
    add('European Central Bank', calendar_from_ecb_official, 1)

    merged={}
    for priority,name,items in sorted(layers,key=lambda z:z[0],reverse=True):
        for raw in items:
            x=dict(raw)
            try: d=datetime.fromisoformat(x.get('date','')).replace(tzinfo=TZ8)
            except Exception: continue
            if not (now-timedelta(days=1)<=d<=end): continue
            title=x.get('title','')
            if not re.search(IMPORTANT_TERMS,title,re.I) and int(x.get('importance') or 1)<2: continue
            x['flag']=x.get('flag') or _flag(x.get('country'))
            k=_event_key(x); old=merged.get(k)
            if old is None:
                x['_priority']=priority; merged[k]=x; continue
            better=x if priority < old.get('_priority',99) else old
            other=old if better is x else x
            for fld in ('actual','forecast','previous','time','country','flag'):
                if (not _clean(better.get(fld)) or better.get(fld)=='—') and _clean(other.get(fld)) and other.get(fld)!='—':
                    better[fld]=other[fld]
            better['importance']=max(int(better.get('importance') or 1),int(other.get('importance') or 1))
            sources=[s.strip() for s in (better.get('source','')+' / '+other.get('source','')).split('/') if s.strip()]
            better['source']=' / '.join(dict.fromkeys(sources))
            better['_priority']=min(priority,old.get('_priority',99)); merged[k]=better

    items=[]
    for x in merged.values():
        x.pop('_priority',None); items.append(x)
    items.sort(key=lambda z:(z.get('date',''),z.get('time','99:99'),-int(z.get('importance') or 1)))
    active=[name for _,name,got in layers if got]
    save('calendar.json',{
        'as_of':datetime.now(timezone.utc).isoformat(),
        'status':'ok' if items else 'unavailable',
        'source':' + '.join(dict.fromkeys(active)) if active else 'calendar sources unavailable',
        'source_mode':'Global multi-source + official central banks',
        'window_days':21,
        'cost_note':'重要經濟數據：鉅亨網／財經M平方＋BLS／BEA；央行動態：Fed、台灣央行、BOJ、ECB 官方來源優先。永豐期貨與工商時報作備援／交叉參考。',
        'items':items[:80]
    })


def update_brief():
    m,s,r,n,c=[load_json(x) for x in ('market.json','stocks.json','rates.json','news.json','calendar.json')]
    out=market_recap(m,s,r,n,c)
    today=datetime.now(TZ8).date().isoformat()
    todays_events=[x for x in (c.get('items') or []) if x.get('date')==today]
    todays_events.sort(key=lambda x:(-int(x.get('importance') or 1),x.get('time','99:99')))
    today_top=[f"{x.get('flag','')} {x.get('time','—')} {x.get('country','')}｜{x.get('title','重要經濟事件')}".strip() for x in todays_events[:3]]

    # If today's official/economic calendar has fewer than three items, use only
    # news published on today's Taipei date. Never pull a future calendar event.
    if len(today_top)<3:
        for x in n.get('items',[]):
            if len(today_top)>=3: break
            pub=x.get('published','')
            dt=None
            if pub:
                try:
                    from email.utils import parsedate_to_datetime
                    dt=parsedate_to_datetime(pub)
                    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    dt=dt.astimezone(TZ8)
                except Exception: dt=None
            if dt and dt.date().isoformat()==today and x.get('title'):
                today_top.append('新聞｜'+x['title'])
    if not today_top:
        today_top=['今日暫無已確認的高重要性經濟事件；不以未來日期事件補位。']
    out['today_top']=today_top[:3]
    out['as_of']=datetime.now(timezone.utc).isoformat()
    save('brief.json',out)


update_news=prev.update_news
update_market=prev.update_market
