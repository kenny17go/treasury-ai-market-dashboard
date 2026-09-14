from __future__ import annotations
from datetime import datetime, timezone
from io import StringIO
import math, os, re
import requests, feedparser, pandas as pd, yfinance as yf
from bs4 import BeautifulSoup
from update_v141 import *

UA142={'User-Agent':'Mozilla/5.0 TreasuryAI/1.4.2 (+https://github.com/kenny17go/treasury-ai-market-dashboard)','Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'}


def get142(url, **kwargs):
    last=None
    for n in range(3):
        try:
            headers={**UA142,**kwargs.pop('headers',{})}
            r=requests.get(url,headers=headers,timeout=18,**kwargs)
            r.raise_for_status(); return r
        except Exception as e:
            last=e
            import time; time.sleep(1.0*(n+1))
    raise last


def nyfed_rate(kind='effr'):
    url=f'https://www.newyorkfed.org/markets/reference-rates/{kind}?lv=true'
    r=get142(url)
    soup=BeautifulSoup(r.text,'html.parser')
    # Prefer actual rendered table rows and avoid pandas/html5lib dependency here.
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if len(cells)<2 or not re.fullmatch(r'\d{2}/\d{2}',cells[0]):
            continue
        try: rate=float(cells[1].replace('%','').strip())
        except: continue
        out={'value':rate,'date':cells[0],'source_url':url}
        joined=' '.join(cells)
        m=re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)',joined)
        if m:
            out['target_low']=float(m.group(1)); out['target_high']=float(m.group(2))
        return out
    text=soup.get_text(' ',strip=True)
    m=re.search(r'(\d{2}/\d{2})\s+(\d+\.\d+)\s+',text)
    if not m: raise ValueError(f'NY Fed {kind} not parsed')
    out={'value':float(m.group(2)),'date':m.group(1),'source_url':url}
    tm=re.search(r'(\d+\.\d+)\s*[-–]\s*(\d+\.\d+)',text)
    if tm:
        out['target_low']=float(tm.group(1)); out['target_high']=float(tm.group(2))
    return out


def ecb_deposit_rate():
    url='https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html'
    r=get142(url); soup=BeautifulSoup(r.text,'html.parser')
    today=datetime.now(TZ8).date(); year=today.year; candidates=[]
    months={'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
    current_year=None
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if not cells: continue
        for c in cells[:2]:
            ym=re.fullmatch(r'(20\d{2})',c)
            if ym: current_year=int(ym.group(1))
        dm=None
        for c in cells:
            m=re.search(r'(\d{1,2})\s+([A-Z][a-z]{2})',c)
            if m and m.group(2) in months:
                dm=(int(m.group(1)),months[m.group(2)]); break
        if not dm or not current_year: continue
        d=datetime(current_year,dm[1],dm[0]).date()
        if d>today: continue
        nums=[]
        for c in cells:
            if re.fullmatch(r'\d+(?:\.\d+)?',c):
                v=float(c)
                if v<20 and not (v==float(current_year)): nums.append(v)
        if nums:
            candidates.append((d,nums[0]))
    if not candidates: raise ValueError('ECB deposit rate not parsed')
    d,v=max(candidates,key=lambda x:x[0])
    return {'value':v,'date':d.isoformat(),'source_url':url}


def update_rates():
    # Treasury curve still comes from the official U.S. Treasury XML implementation in V1.4.1.
    now=datetime.now(timezone.utc).isoformat(); rows=[]; cache={}; sources=[]
    try:
        curves,_=treasury_curve(); latest,prev=curves[-1],curves[-2] if len(curves)>1 else curves[-1]
        mapping=[('DGS2','美債 2年','BC_2YEAR'),('DGS5','美債 5年','BC_5YEAR'),('DGS10','美債 10年','BC_10YEAR'),('DGS30','美債 30年','BC_30YEAR')]
        for sid,name,key in mapping:
            v=clean(latest.get(key)); p=clean(prev.get(key)); cache[sid]=[p,v]
            rows.append({'series':sid,'name':name,'value':v,'unit':'%','change_bps':clean((v-p)*100) if v is not None and p is not None else None,'date':latest.get('NEW_DATE'),'source':'U.S. Treasury'})
        sources.append('U.S. Treasury')
    except Exception as e: print('Treasury curve',e)
    for sid,a,b,name in [('2S10S','DGS2','DGS10','2Y10Y 利差'),('5S30S','DGS5','DGS30','5Y30Y 利差')]:
        try:
            cur=(cache[b][-1]-cache[a][-1])*100; prv=(cache[b][0]-cache[a][0])*100
            rows.append({'series':sid,'name':name,'value':clean(cur),'unit':'bps','change_bps':clean(cur-prv),'source':'U.S. Treasury derived'})
        except: rows.append({'series':sid,'name':name,'value':None,'unit':'bps','change_bps':None})
    for sid,name,kind in [('DFF','Fed Funds Effective','effr'),('SOFR','SOFR','sofr')]:
        try:
            x=nyfed_rate(kind); rows.append({'series':sid,'name':name,'value':x['value'],'unit':'%','change_bps':None,'date':x.get('date'),'source':'New York Fed','target_low':x.get('target_low'),'target_high':x.get('target_high')}); sources.append('New York Fed')
        except Exception as e: print('NYFed',kind,e); rows.append({'series':sid,'name':name,'value':None,'unit':'%','change_bps':None})
    try:
        x=ecb_deposit_rate(); rows.append({'series':'ECBDFR','name':'ECB Deposit Rate','value':x['value'],'unit':'%','change_bps':None,'date':x['date'],'source':'ECB'}); sources.append('ECB')
    except Exception as e: print('ECB',e); rows.append({'series':'ECBDFR','name':'ECB Deposit Rate','value':None,'unit':'%','change_bps':None})
    save('rates.json',{'as_of':now,'source':' / '.join(dict.fromkeys(sources)) or 'official sources','rates':rows})


def _parse_dt(v):
    if not v:return None
    s=str(v).strip().replace('Z','+00:00')
    try:
        d=datetime.fromisoformat(s)
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ8)
    except: return None


def _importance(v):
    s=str(v or '').lower()
    if s in ('high','3','3.0'):return 3
    if s in ('medium','med','2','2.0'):return 2
    try:return max(1,min(3,int(float(v))))
    except:return 2


def _calendar_item(e, default_country=''):
    def first(*keys):
        for k in keys:
            if k in e and e.get(k) not in (None,''): return e.get(k)
        return ''
    dt=_parse_dt(first('scheduledAt','scheduled_at','datetime','dateTime','timestamp','date'))
    title=str(first('eventName','event','name','title','indicator','category')).strip()
    if not title:return None
    country=str(first('country','countryName','country_name','region') or default_country).strip()
    currency=str(first('currency','code')).upper().strip()
    actual=str(first('actual','Actual')).strip(); forecast=str(first('forecast','consensus','Forecast')).strip(); previous=str(first('previous','Previous','prior')).strip()
    a,f=_num(actual),_num(forecast)
    return {'time':dt.strftime('%H:%M') if dt else '--:--','date':dt.date().isoformat() if dt else '', 'title':title,'country':country,'currency':currency,'importance':_importance(first('importance','impact','tier')),'actual':actual,'forecast':forecast,'previous':previous,'surprise':clean(a-f) if a is not None and f is not None else None}


def calendar_from_altmarkets():
    url='https://alternativemarkets.ai/api/v1/calendar'
    r=get142(url,params={'importance':3}); payload=r.json(); raw=payload.get('data',payload) if isinstance(payload,dict) else payload
    if not isinstance(raw,list): raise ValueError('Alternative Markets calendar response not a list')
    today=datetime.now(TZ8).date().isoformat(); items=[]
    for e in raw:
        if not isinstance(e,dict):continue
        x=_calendar_item(e)
        if x and (not x['date'] or x['date']==today):items.append(x)
    return sorted(items,key=lambda x:x['time']), url


def calendar_from_xoomar():
    today=datetime.now(TZ8).date().isoformat(); url='https://xoomar.com/api/markets/calendar'
    r=get142(url,params={'from':today,'to':today,'importance':'high'}); payload=r.json(); raw=payload.get('data',payload) if isinstance(payload,dict) else payload
    if not isinstance(raw,list): raise ValueError('Xoomar calendar response not a list')
    items=[]
    for e in raw:
        if not isinstance(e,dict):continue
        x=_calendar_item(e,'United States')
        if x and (not x['date'] or x['date']==today):items.append(x)
    return sorted(items,key=lambda x:x['time']), url


def update_calendar():
    api=(os.getenv('TRADING_ECONOMICS_API_KEY') or '').strip(); items=[]; source=''; mode=''; ok=False
    if api:
        try:
            items=calendar_from_te_key(api); source='Trading Economics API'; mode='api-key'; ok=True
        except Exception as e: print('TE calendar',e)
    if not ok:
        try:
            items,url=calendar_from_altmarkets(); source='Alternative Markets economic calendar'; mode='free-json'; ok=True
        except Exception as e: print('Alternative Markets calendar',e)
    if not ok:
        try:
            items,url=calendar_from_xoomar(); source='Xoomar official-source calendar'; mode='free-json-us'; ok=True
        except Exception as e: print('Xoomar calendar',e)
    save('calendar.json',{'as_of':datetime.now(timezone.utc).isoformat(),'status':'ok' if ok else 'unavailable','source':source or 'unavailable','source_mode':mode or 'unavailable','cost_note':'目前優先使用免 API Key 的公開 JSON 行事曆；若啟用 Trading Economics API Key，可能依供應商方案產生費用。','items':items})


def zq_price(symbol):
    # Yahoo first.
    try:
        t=yf.Ticker(symbol)
        for period,interval in [('5d','30m'),('1mo','1d')]:
            h=t.history(period=period,interval=interval,auto_adjust=False,timeout=15)
            vals=[clean(x) for x in h['Close'].tolist() if clean(x) is not None] if h is not None and not h.empty else []
            if vals:return vals[-1]
    except Exception as e: print('Yahoo ZQ',symbol,e)
    # Public TradingView contract table fallback.
    meeting=next_fomc(); code=f"ZQ{MONTH_CODE[meeting.month]}{meeting.year}" if meeting else ''
    try:
        r=get142('https://www.tradingview.com/symbols/CBOT-ZQ1%21/contracts/')
        text=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
        m=re.search(re.escape(code)+r'.{0,180}?(9\d\.\d{2,4})',text,re.S)
        if m:return float(m.group(1))
    except Exception as e: print('TradingView ZQ',e)
    raise ValueError(f'No Fed Funds futures price for {symbol}')


def fed_probability(rates):
    meeting=next_fomc()
    if not meeting:return None
    effr_row=next((x for x in rates if x.get('series')=='DFF' and x.get('value') is not None),None)
    if not effr_row:return None
    effr=float(effr_row['value']); low=effr_row.get('target_low'); high=effr_row.get('target_high')
    symbol=zq_contract_symbol(meeting); price=zq_price(symbol); avg=100-price
    days=cal.monthrange(meeting.year,meeting.month)[1]; pre=meeting.day; post=days-pre
    if post<=0: raise ValueError('No post-meeting days in contract month')
    post_rate=(avg*days-effr*pre)/post; delta=(post_rate-effr)*100
    lower=math.floor(delta/25.0)*25.0; upper=lower+25.0; p_upper=max(0,min(1,(delta-lower)/25.0)); p_lower=1-p_upper
    outcomes=[]
    for step,p in [(lower,p_lower),(upper,p_upper)]:
        label='維持' if abs(step)<1e-8 else ('升息' if step>0 else '降息')
        out={'change_bps':round(step),'label':label,'probability':round(p*100,1)}
        if low is not None and high is not None:
            out['target_low']=round(float(low)+step/100,2); out['target_high']=round(float(high)+step/100,2)
        outcomes.append(out)
    outcomes.sort(key=lambda x:x['probability'],reverse=True)
    return {'meeting_date':meeting.isoformat(),'days_to_meeting':(meeting-datetime.now(TZ8).date()).days,'contract':symbol,'futures_price':price,'monthly_implied_rate':avg,'effective_rate':effr,'post_meeting_implied_rate':post_rate,'current_target_low':low,'current_target_high':high,'outcomes':outcomes,'methodology':'以會議月份 30-Day Fed Funds Futures 的整月平均 EFFR 定價，按會議前/後日數拆解，再在相鄰 25bp 結果間線性內插；概念依 CME FedWatch methodology，本站自行估算，非 CME 官方 FedWatch。','source':'30-Day Fed Funds monthly futures + New York Fed EFFR + Federal Reserve FOMC calendar'}


def update_professional():
    m=load_json('market.json'); r=load_json('rates.json'); rates=r.get('rates',[])
    curve=[x for x in rates if x.get('series') in ('DGS2','DGS5','DGS10','DGS30')]
    policies=[x for x in rates if x.get('series') in ('DFF','ECBDFR') and x.get('value') is not None]
    try: fed=fed_probability(rates)
    except Exception as e: print('Fed probability',e); fed=None
    fx=m.get('fx',[]); getfx=lambda name: next((x for x in fx if x.get('name')==name),None)
    asia=[getfx(x) for x in ('USD/TWD','USD/JPY','USD/CNH','USD/HKD','USD/SGD','USD/KRW') if getfx(x)]
    save('professional.json',{'as_of':datetime.now(timezone.utc).isoformat(),'yield_curve':curve,'policy_rates':policies,'fed_pricing':fed,'twd':{'usd_twd':getfx('USD/TWD'),'dxy':getfx('DXY'),'usd_cnh':getfx('USD/CNH')},'asia_fx':asia,'rates_source':'U.S. Treasury / New York Fed / ECB official sources'})


NEWS_SOURCES=[
    ('鉅亨網','anue.com',100),('經濟日報','money.udn.com',98),('自由財經','ec.ltn.com.tw',96),
    ('華爾街日報','cn.wsj.com',90),('金融時報','ftchinese.com',88),('彭博社','bloomberg.com',86),('路透社','reuters.com',86)
]

def _zh_ratio(s):
    if not s:return 0
    return len(re.findall(r'[\u4e00-\u9fff]',s))/max(1,len(s))


def update_news():
    items=[]; seen=set()
    for label,domain,priority in NEWS_SOURCES:
        queries=[f'site:{domain} 財經 市場',f'site:{domain} 聯準會 美股 台股 利率']
        for q in queries:
            try:
                feed=feedparser.parse('https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant')
                for e in feed.entries[:10]:
                    title=base.clean_news_title(e.get('title','')); key=base.news_key(title)
                    if not title or len(key)<6 or key in seen:continue
                    seen.add(key)
                    src=e.source.get('title','') if isinstance(e.get('source'),dict) else ''
                    # Site-restricted query is the gate; use preferred label when Google source metadata is noisy.
                    source=label if not src or src.lower() in ('google news','google 新聞') else src
                    items.append({'title':title,'url':e.get('link','#'),'source':source,'published':e.get('published',''),'time':'','category':base.news_category(title),'priority':priority,'zh_score':_zh_ratio(title)})
            except Exception as ex: print('news',label,ex)
    items.sort(key=lambda x:(x['zh_score']>0.08,x['priority'],x.get('published','')),reverse=True)
    for x in items:x.pop('zh_score',None);x.pop('priority',None)
    save('news.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Google News RSS · preferred financial publishers','preferred_sources':[x[0] for x in NEWS_SOURCES],'items':items[:30]})
