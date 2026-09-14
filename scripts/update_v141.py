from __future__ import annotations
import calendar as cal
import json, math, os, re, time
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
import xml.etree.ElementTree as ET
import requests
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import update_data as base

DATA=base.DATA; CONFIG=base.CONFIG; TZ8=base.TZ8
UA={'User-Agent':'Mozilla/5.0 TreasuryAI/1.4.1 (+https://github.com/kenny17go/treasury-ai-market-dashboard)'}
load_cfg=base.load_cfg; load_json=base.load_json; save=base.save; clean=base.clean
update_market=base.update_market; update_stocks=base.update_stocks; update_news=base.update_news; update_brief=base.update_brief


def get(url, **kwargs):
    last=None
    for n in range(3):
        try:
            r=requests.get(url,headers={**UA,**kwargs.pop('headers',{})},timeout=18,**kwargs)
            r.raise_for_status(); return r
        except Exception as e:
            last=e; time.sleep(1.3*(n+1))
    raise last


def _local(tag): return tag.split('}')[-1]

def treasury_curve():
    year=datetime.now(TZ8).year
    url='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
    r=get(url,params={'data':'daily_treasury_yield_curve','field_tdr_date_value':str(year)})
    root=ET.fromstring(r.content); rows=[]
    for entry in root.iter():
        if _local(entry.tag)!='entry': continue
        d={}
        for node in entry.iter():
            key=_local(node.tag)
            if node.text and node.text.strip(): d[key]=node.text.strip()
        if d.get('NEW_DATE'): rows.append(d)
    if not rows: raise ValueError('Treasury XML contained no curve rows')
    rows.sort(key=lambda x:x['NEW_DATE'])
    return rows[-2:], url


def nyfed_rate(kind='effr'):
    url=f'https://www.newyorkfed.org/markets/reference-rates/{kind}'
    r=get(url)
    tables=pd.read_html(StringIO(r.text))
    for df in tables:
        if df.empty: continue
        cols=[' '.join(map(str,c)) if isinstance(c,tuple) else str(c) for c in df.columns]
        rate_idx=next((i for i,c in enumerate(cols) if re.search(r'RATE',c,re.I)),None)
        if rate_idx is None: continue
        try:
            rate=float(str(df.iloc[0,rate_idx]).replace('%','').strip())
        except: continue
        out={'value':rate,'date':str(df.iloc[0,0]),'source_url':url}
        target_idx=next((i for i,c in enumerate(cols) if 'TARGET' in c.upper()),None)
        if target_idx is not None:
            m=re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)',str(df.iloc[0,target_idx]))
            if m: out['target_low']=float(m.group(1)); out['target_high']=float(m.group(2))
        return out
    # HTML-text fallback
    text=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
    m=re.search(r'(\d{2}/\d{2})\s+(\d+\.\d+)\s+',text)
    if not m: raise ValueError(f'NY Fed {kind} table not parsed')
    out={'value':float(m.group(2)),'date':m.group(1),'source_url':url}
    tm=re.search(r'(\d+\.\d+)\s*[-–]\s*(\d+\.\d+)',text)
    if tm: out['target_low']=float(tm.group(1)); out['target_high']=float(tm.group(2))
    return out


def update_rates():
    now=datetime.now(timezone.utc).isoformat(); rows=[]; cache={}; source_parts=[]
    try:
        curves,url=treasury_curve(); source_parts.append('U.S. Treasury XML')
        latest,prev=curves[-1],curves[-2] if len(curves)>1 else curves[-1]
        mapping=[('DGS2','美債 2年','BC_2YEAR'),('DGS5','美債 5年','BC_5YEAR'),('DGS10','美債 10年','BC_10YEAR'),('DGS30','美債 30年','BC_30YEAR')]
        for sid,name,key in mapping:
            v=clean(latest.get(key)); p=clean(prev.get(key)); cache[sid]=[p,v]
            rows.append({'series':sid,'name':name,'value':v,'unit':'%','change_bps':clean((v-p)*100) if v is not None and p is not None else None,'date':latest.get('NEW_DATE'),'source':'U.S. Treasury'})
    except Exception as e: print('Treasury curve',e)
    for sid,a,b,name in [('2S10S','DGS2','DGS10','2Y10Y 利差'),('5S30S','DGS5','DGS30','5Y30Y 利差')]:
        try:
            cur=(cache[b][-1]-cache[a][-1])*100; prv=(cache[b][0]-cache[a][0])*100
            rows.append({'series':sid,'name':name,'value':clean(cur),'unit':'bps','change_bps':clean(cur-prv),'source':'U.S. Treasury derived'})
        except: rows.append({'series':sid,'name':name,'value':None,'unit':'bps','change_bps':None})
    for sid,name,kind in [('DFF','Fed Funds Effective','effr'),('SOFR','SOFR','sofr')]:
        try:
            x=nyfed_rate(kind); source_parts.append('New York Fed')
            rows.append({'series':sid,'name':name,'value':x['value'],'unit':'%','change_bps':None,'date':x.get('date'),'source':'New York Fed','target_low':x.get('target_low'),'target_high':x.get('target_high')})
        except Exception as e: print('NYFed',kind,e); rows.append({'series':sid,'name':name,'value':None,'unit':'%','change_bps':None})
    # ECB stays optional; robust runner preserves last valid observation when this source is unavailable.
    try:
        vals=base.fred_series('ECBDFR'); v=vals[-1]; p=vals[-2] if len(vals)>1 else v
        rows.append({'series':'ECBDFR','name':'ECB Deposit Rate','value':clean(v),'unit':'%','change_bps':clean((v-p)*100),'source':'FRED / ECB'})
    except Exception as e: print('ECB rate',e); rows.append({'series':'ECBDFR','name':'ECB Deposit Rate','value':None,'unit':'%','change_bps':None})
    save('rates.json',{'as_of':now,'source':' / '.join(dict.fromkeys(source_parts)) or 'official sources','rates':rows})


def _num(v):
    if v is None:return None
    m=re.search(r'-?\d+(?:\.\d+)?',str(v).replace(',',''))
    return float(m.group()) if m else None


def calendar_from_investing():
    urls=['https://ph.investing.com/economic-calendar/','https://www.investing.com/economic-calendar/']
    last=None
    for url in urls:
        try:
            r=get(url,headers={'Accept-Language':'en-US,en;q=0.9'})
            tables=pd.read_html(StringIO(r.text)); candidates=[]
            for df in tables:
                cols=[str(c) for c in df.columns]
                if any('Event' in c for c in cols) and any('Actual' in c for c in cols): candidates.append(df)
            if not candidates: raise ValueError('no economic calendar table')
            df=max(candidates,key=len); df.columns=[str(c).strip() for c in df.columns]
            def col(*names):
                return next((c for c in df.columns if any(n.lower() in c.lower() for n in names)),None)
            tc,cc,ec=col('Time'),col('Cur','Currency'),col('Event')
            ac,fc,pc=col('Actual'),col('Forecast','Consensus'),col('Previous')
            countries={'USD':'United States','EUR':'Euro Area','JPY':'Japan','CNY':'China','CNH':'China','TWD':'Taiwan','GBP':'United Kingdom','CAD':'Canada'}
            high=['cpi','ppi','gdp','nonfarm','payroll','unemployment','interest rate','fed','fomc','ecb','boj','retail sales','pce','ism','pmi','jobless']
            items=[]
            for _,row in df.iterrows():
                cur=str(row.get(cc,'')).strip().upper() if cc else ''
                if cur not in countries: continue
                title=str(row.get(ec,'')).strip()
                if not title or title.lower()=='nan': continue
                t=str(row.get(tc,'')).strip() if tc else ''
                if not re.match(r'^\d{1,2}:\d{2}$',t): continue
                actual='' if ac is None or pd.isna(row.get(ac)) else str(row.get(ac)).strip()
                forecast='' if fc is None or pd.isna(row.get(fc)) else str(row.get(fc)).strip()
                previous='' if pc is None or pd.isna(row.get(pc)) else str(row.get(pc)).strip()
                a,f=_num(actual),_num(forecast); surprise=clean(a-f) if a is not None and f is not None else None
                importance=3 if any(k in title.lower() for k in high) else 2
                items.append({'time':t.zfill(5),'title':title,'country':countries[cur],'currency':cur,'importance':importance,'actual':actual,'forecast':forecast,'previous':previous,'surprise':surprise})
            if items:return sorted(items,key=lambda x:x['time'])[:30],url
        except Exception as e: last=e
    raise last or ValueError('Investing calendar unavailable')


def calendar_from_te_key(key):
    r=get('https://api.tradingeconomics.com/calendar',params={'c':key}); raw=r.json(); today=datetime.now(TZ8).date(); items=[]
    countries={'United States','Japan','Euro Area','China','Taiwan','United Kingdom','Canada'}
    for e in raw:
        try:
            dt=datetime.fromisoformat(str(e.get('Date','')).replace('Z','+00:00')); dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc); local=dt.astimezone(TZ8)
            if local.date()!=today or e.get('Country') not in countries: continue
            imp=int(e.get('Importance') or 1)
            if imp<2: continue
            actual=e.get('Actual') or ''; forecast=e.get('Forecast') or ''; previous=e.get('Previous') or ''
            a,f=_num(actual),_num(forecast)
            items.append({'time':local.strftime('%H:%M'),'title':e.get('Event') or e.get('Category') or 'Economic event','country':e.get('Country',''),'importance':imp,'actual':actual,'forecast':forecast,'previous':previous,'surprise':clean(a-f) if a is not None and f is not None else None})
        except: pass
    return sorted(items,key=lambda x:x['time'])[:30]


def update_calendar():
    api=(os.getenv('TRADING_ECONOMICS_API_KEY') or '').strip(); items=[]; source=''; mode=''
    if api:
        try:
            items=calendar_from_te_key(api); source='Trading Economics API'; mode='api-key'
        except Exception as e: print('TE calendar',e)
    if not items:
        try:
            items,url=calendar_from_investing(); source='Investing.com public economic calendar'; mode='investing-public'
        except Exception as e: print('Investing calendar',e)
    save('calendar.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':source or 'unavailable','source_mode':mode or 'unavailable','cost_note':'Investing.com 公開頁面不需本站 API Key；若啟用 Trading Economics API Key，可能依供應商方案產生費用。','items':items})


def parse_int(v):
    try:return int(str(v).replace(',','').replace('+','').strip())
    except:return None


def update_positioning():
    url='https://www.taifex.com.tw/cht/3/futContractsDateExcel'; result={'product':'臺股期貨','identity':'外資','date':None,'trade_net_contracts':None,'oi_long_contracts':None,'oi_short_contracts':None,'oi_net_contracts':None}
    try:
        r=get(url); text=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True); dm=re.search(r'日期\s*(\d{4}/\d{2}/\d{2})',text); result['date']=dm.group(1) if dm else None
        tables=pd.read_html(StringIO(r.text)); found=False
        for df in tables:
            if found:break
            # pandas expands rowspan cells, which is much more reliable than raw tr parsing here.
            for _,row in df.iterrows():
                cells=[str(x).strip() for x in row.tolist()]
                joined=' | '.join(cells)
                if '臺股期貨' not in joined or '外資' not in joined: continue
                nums=[]
                for c in cells:
                    if '臺股期貨' in c or c=='外資' or c.lower()=='nan': continue
                    v=parse_int(c)
                    if v is not None: nums.append(v)
                # Ignore serial number if pandas preserved it as the first numeric field.
                if len(nums)>=13 and nums[0] in range(1,100): nums=nums[1:]
                if len(nums)>=12:
                    result.update({'trade_long_contracts':nums[0],'trade_short_contracts':nums[2],'trade_net_contracts':nums[4],'oi_long_contracts':nums[6],'oi_short_contracts':nums[8],'oi_net_contracts':nums[10]}); found=True; break
        if not found: raise ValueError('TAIFEX 臺股期貨/外資 row not parsed')
        status='ok'
    except Exception as e: print('TAIFEX positioning',e); status='unavailable'
    save('positioning.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'TAIFEX 三大法人-區分各期貨契約','source_url':url,'status':status,'tx_foreign':result})


FOMC_DATES=[date(2026,9,16),date(2026,10,28),date(2026,12,9),date(2027,1,27),date(2027,3,17),date(2027,4,28),date(2027,6,9),date(2027,7,28),date(2027,9,15),date(2027,10,27),date(2027,12,8)]
MONTH_CODE={1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}

def zq_contract_symbol(d): return f"ZQ{MONTH_CODE[d.month]}{str(d.year)[-2:]}.CBT"

def zq_price(symbol):
    t=yf.Ticker(symbol)
    for period,interval in [('5d','30m'),('1mo','1d')]:
        try:
            h=t.history(period=period,interval=interval,auto_adjust=False,timeout=15)
            vals=[clean(x) for x in h['Close'].tolist() if clean(x) is not None] if h is not None and not h.empty else []
            if vals:return vals[-1]
        except Exception as e: print('ZQ',symbol,e)
    raise ValueError(f'No price for {symbol}')


def next_fomc(today=None):
    today=today or datetime.now(TZ8).date()
    return next((d for d in FOMC_DATES if d>=today),None)


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
    return {'meeting_date':meeting.isoformat(),'days_to_meeting':(meeting-datetime.now(TZ8).date()).days,'contract':symbol,'futures_price':price,'monthly_implied_rate':avg,'effective_rate':effr,'post_meeting_implied_rate':post_rate,'current_target_low':low,'current_target_high':high,'outcomes':outcomes,'methodology':'以會議月份 30-Day Fed Funds Futures 的整月平均 EFFR 定價，按會議前/後日數拆解，再在相鄰 25bp 結果間線性內插；概念依 CME FedWatch methodology，本站自行估算，非 CME 官方 FedWatch。','source':'Yahoo Finance ZQ monthly contract + New York Fed EFFR + Federal Reserve FOMC calendar'}


def update_professional():
    m=load_json('market.json'); r=load_json('rates.json'); rates=r.get('rates',[])
    curve=[x for x in rates if x.get('series') in ('DGS2','DGS5','DGS10','DGS30')]
    policies=[x for x in rates if x.get('series') in ('DFF','ECBDFR') and x.get('value') is not None]
    try: fed=fed_probability(rates)
    except Exception as e: print('Fed probability',e); fed=None
    fx=m.get('fx',[]); getfx=lambda name: next((x for x in fx if x.get('name')==name),None)
    asia=[getfx(x) for x in ('USD/TWD','USD/JPY','USD/CNH','USD/HKD','USD/SGD','USD/KRW') if getfx(x)]
    save('professional.json',{'as_of':datetime.now(timezone.utc).isoformat(),'yield_curve':curve,'policy_rates':policies,'fed_pricing':fed,'twd':{'usd_twd':getfx('USD/TWD'),'dxy':getfx('DXY'),'usd_cnh':getfx('USD/CNH')},'asia_fx':asia,'rates_source':'U.S. Treasury official XML; Cbonds may be used as a visual cross-check, not as the primary automated feed.'})
