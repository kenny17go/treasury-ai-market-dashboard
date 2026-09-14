from __future__ import annotations
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from io import StringIO
import html, re
import feedparser, requests
from bs4 import BeautifulSoup
from update_v142 import *

ET = ZoneInfo('America/New_York')

NEWS_CATEGORIES = {
    '美股': '美股 標普 那斯達克 道瓊 財報',
    '半導體': '半導體 台積電 NVIDIA AMD ASML 晶片',
    '軟體 / AI': 'AI 人工智慧 軟體 Microsoft Google Meta OpenAI',
    '央行 / 利率': 'Fed 聯準會 FOMC 利率 美債 殖利率 央行',
    '能源': '原油 WTI Brent OPEC 天然氣 能源',
    '歐洲': '歐洲 ECB 歐元 英國 德國 法國 財經',
    '中國': '中國 人民幣 經濟 房市 股票 財經',
    '地產': '房地產 REIT 房貸 商用不動產 地產 財經',
    '台灣': '台股 台灣 外資 台積電 新台幣 財經',
}
PREFERRED = '(鉅亨網 OR 經濟日報 OR 自由財經 OR 路透社 OR Reuters OR 彭博 OR Bloomberg OR 華爾街日報 OR WSJ OR 金融時報 OR Financial Times)'


def _strip_html(s):
    text=BeautifulSoup(html.unescape(s or ''),'html.parser').get_text(' ',strip=True)
    return re.sub(r'\s+',' ',text).strip()


def update_news():
    rows=[]; seen=set()
    for cat,terms in NEWS_CATEGORIES.items():
        q=f'{terms} {PREFERRED}'
        url='https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
        best=None
        try:
            feed=feedparser.parse(url)
            for e in feed.entries[:20]:
                title=clean_news_title(e.get('title',''))
                if not title: continue
                key=news_key(title)
                if key in seen: continue
                source=e.source.get('title','') if isinstance(e.get('source'),dict) else ''
                desc=_strip_html(e.get('summary') or e.get('description') or '')
                # Google RSS descriptions are often title-heavy. Keep only genuinely useful extra text.
                summary=desc if desc and desc.lower()!=title.lower() and len(desc)>len(title)+12 else ''
                best={'category':cat,'title':title,'summary':summary,'source':source,'url':e.get('link','#'),'published':e.get('published','')}
                seen.add(key); break
        except Exception as ex: print('news category',cat,ex)
        if best: rows.append(best)
    save('news.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Google News RSS · curated financial categories','items':rows})


def _unfold_ics(text):
    lines=[]
    for raw in text.replace('\r\n','\n').split('\n'):
        if raw.startswith((' ','\t')) and lines: lines[-1]+=raw[1:]
        else: lines.append(raw)
    return lines


def calendar_from_bls(days=14):
    url='https://www.bls.gov/schedule/news_release/bls.ics'
    r=get142(url,headers={'Accept':'text/calendar,*/*'})
    lines=_unfold_ics(r.text); events=[]; cur=None
    for line in lines:
        if line=='BEGIN:VEVENT': cur={}
        elif line=='END:VEVENT' and cur is not None:
            events.append(cur); cur=None
        elif cur is not None and ':' in line:
            k,v=line.split(':',1); cur[k]=v
    now=datetime.now(TZ8); end=now+timedelta(days=days); out=[]
    for e in events:
        dtline=next(((k,v) for k,v in e.items() if k.startswith('DTSTART')),None)
        if not dtline: continue
        k,v=dtline
        try:
            if re.fullmatch(r'\d{8}T\d{6}',v):
                tz=ET if 'America/New_York' in k else timezone.utc
                dt=datetime.strptime(v,'%Y%m%dT%H%M%S').replace(tzinfo=tz).astimezone(TZ8)
            elif re.fullmatch(r'\d{8}',v):
                dt=datetime.strptime(v,'%Y%m%d').replace(tzinfo=ET).astimezone(TZ8)
            else: continue
        except: continue
        if not (now-timedelta(hours=2) <= dt <= end): continue
        title=(e.get('SUMMARY') or 'BLS release').replace('\\,',',').replace('\\n',' ')
        out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':title,'country':'United States','importance':3,'actual':'','forecast':'','previous':'','source':'BLS'})
    return out


def calendar_from_bea(days=14):
    url='https://www.bea.gov/news/schedule'
    r=get142(url); soup=BeautifulSoup(r.text,'html.parser'); now=datetime.now(TZ8); end=now+timedelta(days=days); out=[]
    monthmap={m:i for i,m in enumerate(['','January','February','March','April','May','June','July','August','September','October','November','December'])}
    year=now.year
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if len(cells)<2: continue
        joined=' '.join(cells)
        m=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s+(AM|PM)',joined)
        if not m: continue
        try:
            dt=datetime.strptime(f'{year}-{monthmap[m.group(1)]:02d}-{int(m.group(2)):02d} {m.group(3)} {m.group(4)}','%Y-%m-%d %I:%M %p').replace(tzinfo=ET).astimezone(TZ8)
        except: continue
        if not (now-timedelta(hours=2) <= dt <= end): continue
        title=cells[-1]
        if len(title)<4: continue
        out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':title,'country':'United States','importance':3,'actual':'','forecast':'','previous':'','source':'BEA'})
    return out


def calendar_from_fomc(days=60):
    now=datetime.now(TZ8); end=now+timedelta(days=days); out=[]
    for d in FOMC_DATES:
        dt=datetime(d.year,d.month,d.day,14,0,tzinfo=ET).astimezone(TZ8)
        if now-timedelta(hours=2) <= dt <= end:
            out.append({'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'title':'FOMC 利率決議 / 記者會','country':'United States','importance':3,'actual':'','forecast':'','previous':'','source':'Federal Reserve'})
    return out


def update_calendar():
    items=[]; sources=[]
    for name,fn in [('BLS',calendar_from_bls),('BEA',calendar_from_bea),('Federal Reserve',calendar_from_fomc)]:
        try:
            got=fn(); items.extend(got)
            if got: sources.append(name)
        except Exception as e: print('calendar',name,e)
    # Deduplicate same release and sort over the next 14 days. On weekends this still shows the next business-day events.
    seen=set(); dedup=[]
    for x in sorted(items,key=lambda z:(z.get('date',''),z.get('time',''))):
        k=(x.get('date'),x.get('time'),re.sub(r'\s+',' ',x.get('title','').lower()))
        if k in seen: continue
        seen.add(k); dedup.append(x)
    status='ok' if dedup else 'unavailable'
    save('calendar.json',{'as_of':datetime.now(timezone.utc).isoformat(),'status':status,'source':' + '.join(sources) if sources else 'official sources unavailable','source_mode':'official','window_days':14,'cost_note':'官方來源：BLS、BEA、Federal Reserve；免 API Key。顯示未來 14 天重要事件，週末也不會因「今日無事件」而整區空白。','items':dedup[:40]})
