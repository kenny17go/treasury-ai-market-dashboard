from __future__ import annotations
import os, json, math, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests, yaml, feedparser, pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; CONFIG=ROOT/'config'/'market.yml'; DATA.mkdir(exist_ok=True)
TZ8=timezone(timedelta(hours=8)); UA={'User-Agent':'Mozilla/5.0 TreasuryAI/1.4'}

def clean(v):
    try:
        f=float(v); return None if math.isnan(f) or math.isinf(f) else f
    except: return None

def save(name,obj): (DATA/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def load_json(name):
    try:return json.loads((DATA/name).read_text(encoding='utf-8'))
    except:return {}
def load_cfg(): return yaml.safe_load(CONFIG.read_text(encoding='utf-8'))

def hist_for(symbol):
    for period,interval in [('5d','30m'),('1mo','1d')]:
        try:
            h=yf.Ticker(symbol).history(period=period,interval=interval,auto_adjust=False,prepost=False,timeout=15)
            if h is not None and not h.empty and 'Close' in h:
                vals=[clean(x) for x in h['Close'].tolist() if clean(x) is not None]
                if len(vals)>=2:return vals[-60:]
        except Exception as e: print('history',symbol,e)
    return []

def quote(item):
    symbol=item['symbol']; vals=hist_for(symbol)
    if len(vals)<2:return {**item,'price':None,'change':None,'change_pct':None,'spark':[]}
    price=vals[-1]; prev=None
    try:
        d=yf.Ticker(symbol).history(period='7d',interval='1d',auto_adjust=False,timeout=15)
        closes=[clean(x) for x in d['Close'].tolist() if clean(x) is not None]
        if len(closes)>=2: prev=closes[-2]
    except: pass
    if prev is None: prev=vals[0]
    change=price-prev; pct=(change/prev*100) if prev else None
    return {**item,'price':clean(price),'change':clean(change),'change_pct':clean(pct),'spark':vals[-48:]}

def update_market(cfg):
    sections={}
    for sec in ('indices','pulse','taiwan','commodities','fx'):
        out=[]
        for item in cfg.get(sec,[]): out.append(quote(item)); time.sleep(.08)
        sections[sec]=out
    save('market.json',{'as_of':datetime.now(timezone.utc).isoformat(),'status':'Auto Update','source':'Yahoo Finance via yfinance',**sections})

def update_stocks(cfg):
    out=[]
    for item in cfg.get('stocks',[]): out.append(quote(item)); time.sleep(.08)
    save('stocks.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Yahoo Finance via yfinance','stocks':out})

def fred_series(series):
    r=requests.get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}',headers=UA,timeout=20); r.raise_for_status()
    from io import StringIO
    df=pd.read_csv(StringIO(r.text)); vals=pd.to_numeric(df[series],errors='coerce').dropna().tolist(); return vals[-2:] if len(vals)>=2 else vals

def update_rates():
    mapping=[('DGS2','美債 2年'),('DGS5','美債 5年'),('DGS10','美債 10年'),('DGS30','美債 30年'),('SOFR','SOFR'),('DFF','Fed Funds Effective'),('ECBDFR','ECB Deposit Rate')]
    rows=[]; cache={}
    for sid,name in mapping:
        try:
            vals=fred_series(sid); cache[sid]=vals; value=vals[-1]; prev=vals[-2] if len(vals)>1 else value
            rows.append({'series':sid,'name':name,'value':clean(value),'unit':'%','change_bps':clean((value-prev)*100)})
        except Exception as e:
            print('FRED',sid,e); rows.append({'series':sid,'name':name,'value':None,'unit':'%','change_bps':None})
    for sid,a,b,name in [('2S10S','DGS2','DGS10','2Y10Y 利差'),('5S30S','DGS5','DGS30','5Y30Y 利差')]:
        try:
            va,vb=cache[a],cache[b]; cur=(vb[-1]-va[-1])*100; prv=((vb[-2] if len(vb)>1 else vb[-1])-(va[-2] if len(va)>1 else va[-1]))*100
            rows.append({'series':sid,'name':name,'value':clean(cur),'unit':'bps','change_bps':clean(cur-prv)})
        except: rows.append({'series':sid,'name':name,'value':None,'unit':'bps','change_bps':None})
    save('rates.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'FRED / Federal Reserve / ECB','rates':rows})

def clean_news_title(t):
    t=re.sub(r'\s+-\s+[^-]{2,50}$','',t or '').strip()
    return re.sub(r'\s+',' ',t)

def news_key(t):
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]','',t.lower())[:120]

def news_category(t):
    s=t.lower()
    rules=[
        ('Fed / Rates',['fed','fomc','利率','美債','殖利率','降息','升息','央行','cpi','ppi','非農']),
        ('AI / 半導體',['nvidia','nvda','amd','台積電','tsmc','半導體','ai','晶片','asml']),
        ('台灣市場',['台股','台灣','外資','台積電','新台幣','twd']),
        ('中國 / 亞洲',['中國','大陸','人民幣','cnh','日本','日圓','boj','韓國']),
        ('歐洲',['歐洲','ecb','歐元','德國','英國','boe'])]
    for cat,keys in rules:
        if any(k in s for k in keys): return cat
    return '全球市場'

def update_news():
    queries=['美股 Nvidia 半導體 財經','Fed 美債 利率 美元 財經','台灣 股市 外資 財經','中國 歐洲 經濟 財經']; items=[]; seen=set(); seen_url=set()
    for q in queries:
        try:
            feed=feedparser.parse('https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant')
            for e in feed.entries[:12]:
                title=clean_news_title(e.get('title','')); url=e.get('link','#'); key=news_key(title)
                if not title or len(key)<6 or key in seen or url in seen_url: continue
                seen.add(key); seen_url.add(url); source=e.source.get('title','') if isinstance(e.get('source'),dict) else ''
                items.append({'title':title,'url':url,'source':source,'published':e.get('published',''),'time':'','category':news_category(title)})
        except Exception as ex: print('news',ex)
    save('news.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Google News RSS','items':items[:30]})

def parse_num(v):
    if v is None:return None
    m=re.search(r'-?\d+(?:\.\d+)?',str(v).replace(',',''))
    return float(m.group()) if m else None

def update_calendar():
    items=[]; api_key=(os.getenv('TRADING_ECONOMICS_API_KEY') or '').strip(); credential=api_key or 'guest:guest'; mode='api-key' if api_key else 'guest'
    source='Trading Economics API' if api_key else 'Trading Economics guest API'
    cost_note='API key 方案可能需要付費訂閱，依 Trading Economics 方案為準。' if api_key else 'Guest 模式目前不需本站 API key，但資料範圍與可用性可能受限。'
    try:
        r=requests.get('https://api.tradingeconomics.com/calendar',params={'c':credential},headers=UA,timeout=25); r.raise_for_status(); raw=r.json(); today=datetime.now(TZ8).date(); countries={'United States','Japan','Euro Area','China','Taiwan','United Kingdom','Canada'}
        for e in raw:
            try:
                dt=datetime.fromisoformat(str(e.get('Date','')).replace('Z','+00:00')); dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc); local=dt.astimezone(TZ8)
                if local.date()!=today or e.get('Country') not in countries: continue
                imp=int(e.get('Importance') or 1)
                if imp<2: continue
                actual=e.get('Actual') or ''; forecast=e.get('Forecast') or ''; previous=e.get('Previous') or ''
                a,f=parse_num(actual),parse_num(forecast); surprise=clean(a-f) if a is not None and f is not None else None
                items.append({'time':local.strftime('%H:%M'),'title':e.get('Event') or e.get('Category') or 'Economic event','country':e.get('Country',''),'importance':imp,'actual':actual,'forecast':forecast,'previous':previous,'surprise':surprise})
            except: continue
    except Exception as e: print('calendar',e)
    save('calendar.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':source,'source_mode':mode,'cost_note':cost_note,'items':sorted(items,key=lambda x:x['time'])[:24]})

def parse_int(v):
    try:return int(str(v).replace(',','').replace('+','').strip())
    except:return None

def update_positioning():
    url='https://www.taifex.com.tw/cht/3/futContractsDateExcel'; result={'product':'臺股期貨','identity':'外資','date':None,'trade_net_contracts':None,'oi_long_contracts':None,'oi_short_contracts':None,'oi_net_contracts':None}
    try:
        r=requests.get(url,headers=UA,timeout=25); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser'); text=soup.get_text(' ',strip=True)
        m=re.search(r'日期\s*(\d{4}/\d{2}/\d{2})',text); result['date']=m.group(1) if m else None
        current_product=None
        for tr in soup.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'])]
            if not cells: continue
            if '臺股期貨' in cells: current_product='臺股期貨'
            identities=[i for i,x in enumerate(cells) if x in ('自營商','投信','外資')]
            if current_product=='臺股期貨' and identities:
                i=identities[0]
                if cells[i]=='外資':
                    nums=[parse_int(x) for x in cells[i+1:]]; nums=[x for x in nums if x is not None]
                    if len(nums)>=12:
                        result.update({'trade_long_contracts':nums[0],'trade_short_contracts':nums[2],'trade_net_contracts':nums[4],'oi_long_contracts':nums[6],'oi_short_contracts':nums[8],'oi_net_contracts':nums[10]})
                        break
        if result.get('oi_net_contracts') is None: raise ValueError('TAIFEX TX foreign row not parsed')
        status='ok'
    except Exception as e:
        print('TAIFEX positioning',e); status='unavailable'
    save('positioning.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'TAIFEX 三大法人-區分各期貨契約','source_url':url,'status':status,'tx_foreign':result})

def update_professional():
    m=load_json('market.json'); r=load_json('rates.json'); rates=r.get('rates',[])
    curve=[x for x in rates if x.get('series') in ('DGS2','DGS5','DGS10','DGS30')]
    policies=[x for x in rates if x.get('series') in ('DFF','ECBDFR')]
    fed=next((x for x in policies if x.get('series')=='DFF'),None); ff=None
    try:
        q=quote({'symbol':'ZQ=F','name':'30-Day Fed Funds Futures','decimals':3}); implied=(100-q['price']) if q.get('price') is not None else None
        current=fed.get('value') if fed else None; basis=(implied-current)*100 if current is not None and implied is not None else None
        easing_bps=(current-implied)*100 if current is not None and implied is not None else None
        proxy=max(0,min(100,easing_bps/25*100)) if easing_bps is not None else None
        ff={'symbol':'ZQ=F','name':'30-Day Fed Funds Futures (front-month continuous)','futures_price':q.get('price'),'futures_change_pct':q.get('change_pct'),'implied_rate':clean(implied),'effective_rate':clean(current),'basis_bps':clean(basis),'cut_bias_bps':clean(easing_bps),'easing_probability_proxy':clean(proxy),'source':'Yahoo Finance / FRED','note':'100 - futures price 為近月隱含平均有效聯邦基金利率的粗略代理；非 CME FedWatch 官方會議機率。'}
    except Exception as e: print('fed futures',e)
    fx=m.get('fx',[]); get=lambda name: next((x for x in fx if x.get('name')==name),None)
    asia=[get(x) for x in ('USD/TWD','USD/JPY','USD/CNH','USD/HKD','USD/SGD','USD/KRW') if get(x)]
    twd={'usd_twd':get('USD/TWD'),'dxy':get('DXY'),'usd_cnh':get('USD/CNH')}
    save('professional.json',{'as_of':datetime.now(timezone.utc).isoformat(),'yield_curve':curve,'policy_rates':policies,'fed_pricing':ff,'twd':twd,'asia_fx':asia})

def market_recap(market,stocks,rates,news,calendar):
    indices=[x for x in market.get('indices',[]) if x.get('change_pct') is not None]; st=[x for x in stocks.get('stocks',[]) if x.get('change_pct') is not None]; avg=sum(x['change_pct'] for x in indices)/len(indices) if indices else 0
    vix=next((x for x in market.get('pulse',[]) if x.get('symbol')=='^VIX'),None); score=max(0,min(100,round(50+avg*12+(-8 if vix and vix.get('price',0)>=25 else 5 if vix and vix.get('price') is not None and vix['price']<16 else 0)))); label='偏多' if score>=62 else '偏空' if score<=38 else '中性'
    r10=next((x for x in rates.get('rates',[]) if x.get('series')=='DGS10'),None); curve=next((x for x in rates.get('rates',[]) if x.get('series')=='2S10S'),None); dxy=next((x for x in market.get('fx',[]) if x.get('name')=='DXY'),None)
    best=max(st,key=lambda x:x['change_pct'],default=None); worst=min(st,key=lambda x:x['change_pct'],default=None); bullets=[]
    if indices: bullets.append(f"主要美股指數平均變動 {avg:+.2f}%。")
    if r10 and r10.get('value') is not None: bullets.append(f"美債10年殖利率 {r10['value']:.3f}%，日變動 {r10.get('change_bps',0):+.1f} bps。")
    if best and worst: bullets.append(f"自選股強勢 {best.get('label',best['symbol'])} {best['change_pct']:+.2f}%；較弱 {worst.get('label',worst['symbol'])} {worst['change_pct']:+.2f}%。")
    if curve and curve.get('value') is not None: bullets.append(f"2Y10Y 利差 {curve['value']:+.1f} bps。")
    y=[f"美股主要指數平均 {avg:+.2f}%，風險情緒偏{label}。"]
    if r10:y.append(f"10Y 美債殖利率 {r10.get('value',0):.3f}%。")
    if dxy:y.append(f"DXY 日變動 {dxy.get('change_pct',0):+.2f}%。")
    today=[f"{e.get('time','--:--')} {e.get('country','')}｜{e.get('title','重要經濟事件')}" for e in sorted(calendar.get('items',[]),key=lambda x:(-int(x.get('importance') or 1),x.get('time','99:99')))[:3]]
    if len(today)<3:
        for x in news.get('items',[]):
            if len(today)>=3: break
            if x.get('title') and x['title'] not in today: today.append(x['title'])
    watch=[]
    if r10: watch.append(f"利率：10Y 日變動 {r10.get('change_bps',0):+.1f} bps。")
    if dxy: watch.append(f"美元：DXY 日變動 {dxy.get('change_pct',0):+.2f}%。")
    if vix: watch.append(f"波動率：VIX {vix.get('price',0):.2f}。")
    if curve: watch.append(f"曲線：2Y10Y {curve.get('value',0):+.1f} bps。")
    return {'mode':'rules','headline':f'市場風險情緒：{label}','bullets':bullets[:4],'risk_score':score,'risk_label':label,'yesterday_top':y[:3],'today_top':today[:3],'todays_watch':watch[:4]}

def update_brief():
    m,s,r,n,c=[load_json(x) for x in ('market.json','stocks.json','rates.json','news.json','calendar.json')]; out=market_recap(m,s,r,n,c); out['as_of']=datetime.now(timezone.utc).isoformat(); save('brief.json',out)

def main():
    cfg=load_cfg(); update_market(cfg); update_stocks(cfg); update_rates(); update_news(); update_calendar(); update_positioning(); update_professional(); update_brief()
if __name__=='__main__': main()
