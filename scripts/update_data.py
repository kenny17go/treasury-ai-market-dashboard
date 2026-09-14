from __future__ import annotations
import os, json, math, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests, yaml, feedparser, pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; CONFIG=ROOT/'config'/'market.yml'; DATA.mkdir(exist_ok=True)
TZ8=timezone(timedelta(hours=8))
UA={'User-Agent':'Mozilla/5.0 TreasuryAI/1.0'}

def clean(v):
    try:
        f=float(v); return None if math.isnan(f) or math.isinf(f) else f
    except: return None

def save(name,obj):
    (DATA/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def hist_for(symbol):
    # Intraday first; fall back to daily. yfinance may occasionally throttle, so keep this isolated.
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
    if len(vals)<2: return {**item,'price':None,'change':None,'change_pct':None,'spark':[]}
    price=vals[-1]
    # Prefer previous session close from daily history.
    prev=None
    try:
        d=yf.Ticker(symbol).history(period='7d',interval='1d',auto_adjust=False,timeout=15)
        closes=[clean(x) for x in d['Close'].tolist() if clean(x) is not None]
        if len(closes)>=2: prev=closes[-2]
    except: pass
    if prev is None: prev=vals[0]
    change=price-prev; pct=(change/prev*100) if prev else None
    return {**item,'price':clean(price),'change':clean(change),'change_pct':clean(pct),'spark':vals[-48:]}

def load_cfg(): return yaml.safe_load(CONFIG.read_text(encoding='utf-8'))

def update_market(cfg):
    now=datetime.now(timezone.utc).isoformat()
    sections={}
    for sec in ('indices','taiwan','commodities','fx'):
        out=[]
        for item in cfg.get(sec,[]):
            q=quote(item); out.append(q); time.sleep(.1)
        sections[sec]=out
    save('market.json',{'as_of':now,'status':'Auto Update','source':'Yahoo Finance via yfinance',**sections})

def update_stocks(cfg):
    out=[]
    for item in cfg.get('stocks',[]):
        out.append(quote(item)); time.sleep(.1)
    save('stocks.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Yahoo Finance via yfinance','stocks':out})

def fred_series(series):
    url=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'
    r=requests.get(url,headers=UA,timeout=20); r.raise_for_status()
    from io import StringIO
    df=pd.read_csv(StringIO(r.text)); vals=pd.to_numeric(df[series],errors='coerce').dropna().tolist()
    return vals[-2:] if len(vals)>=2 else vals

def update_rates():
    mapping=[('DGS2','美債 2年'),('DGS10','美債 10年'),('DGS30','美債 30年')]
    rows=[]
    for sid,name in mapping:
        try:
            vals=fred_series(sid); value=vals[-1]; prev=vals[-2] if len(vals)>1 else value
            rows.append({'series':sid,'name':name,'value':clean(value),'change_bps':clean((value-prev)*100)})
        except Exception as e:
            print('FRED',sid,e); rows.append({'series':sid,'name':name,'value':None,'change_bps':None})
    save('rates.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'FRED / Federal Reserve H.15','rates':rows})

def clean_news_title(t):
    return re.sub(r'\s+-\s+[^-]{2,50}$','',t or '').strip()

def update_news():
    queries=['美股 Nvidia 半導體 財經','Fed 美債 利率 美元 財經','台灣 股市 外資 財經','中國 歐洲 經濟 財經']
    items=[]; seen=set()
    for q in queries:
        url='https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
        try:
            feed=feedparser.parse(url)
            for e in feed.entries[:8]:
                title=clean_news_title(e.get('title',''))
                key=title.lower()
                if not title or key in seen: continue
                seen.add(key)
                source='';
                if isinstance(e.get('source'),dict): source=e.source.get('title','')
                items.append({'title':title,'url':e.get('link','#'),'source':source,'published':e.get('published',''),'time':''})
        except Exception as ex: print('news',ex)
    save('news.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Google News RSS','items':items[:16]})

def update_calendar():
    items=[]
    # Trading Economics provides a limited guest feed. If unavailable, dashboard gracefully shows an empty state.
    try:
        r=requests.get('https://api.tradingeconomics.com/calendar?c=guest:guest',headers=UA,timeout=25); r.raise_for_status(); raw=r.json()
        today=datetime.now(TZ8).date(); countries={'United States','Japan','Euro Area','China','Taiwan','United Kingdom','Canada'}
        for e in raw:
            try:
                dt=datetime.fromisoformat(str(e.get('Date','')).replace('Z','+00:00'))
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                local=dt.astimezone(TZ8)
                if local.date()!=today or e.get('Country') not in countries: continue
                imp=int(e.get('Importance') or 1)
                if imp<2: continue
                items.append({'time':local.strftime('%H:%M'),'title':e.get('Event') or e.get('Category') or 'Economic event','country':e.get('Country',''),'importance':imp,'actual':e.get('Actual') or '','forecast':e.get('Forecast') or ''})
            except: continue
    except Exception as e: print('calendar',e)
    items=sorted(items,key=lambda x:x['time'])[:18]
    save('calendar.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Trading Economics guest feed when available','items':items})

def load_json(name):
    try:return json.loads((DATA/name).read_text(encoding='utf-8'))
    except:return {}

def rules_brief(market,stocks,rates):
    indices=[x for x in market.get('indices',[]) if x.get('change_pct') is not None]
    st=[x for x in stocks.get('stocks',[]) if x.get('change_pct') is not None]
    avg=sum(x['change_pct'] for x in indices)/len(indices) if indices else 0
    score=max(0,min(100,round(50+avg*12)))
    label='偏多' if score>=62 else '偏空' if score<=38 else '中性'
    best=max(st,key=lambda x:x['change_pct'],default=None); worst=min(st,key=lambda x:x['change_pct'],default=None)
    r10=next((x for x in rates.get('rates',[]) if x.get('series')=='DGS10'),None)
    bullets=[]
    if indices: bullets.append('主要美股指數平均變動 '+f'{avg:+.2f}%'+('，風險偏好改善。' if avg>0 else '，風險偏好轉弱。'))
    if best and worst: bullets.append(f"自選股強勢為 {best.get('label',best['symbol'])} {best['change_pct']:+.2f}%；較弱為 {worst.get('label',worst['symbol'])} {worst['change_pct']:+.2f}%。")
    if r10 and r10.get('value') is not None: bullets.append(f"美債10年殖利率 {r10['value']:.3f}%，單日變動 {r10.get('change_bps',0):+.1f} bps。")
    return {'mode':'rules','headline':f'市場風險情緒：{label}','bullets':bullets,'risk_score':score,'risk_label':label}

def openai_brief(base,market,stocks,rates):
    key=os.getenv('OPENAI_API_KEY');
    if not key:return base
    model=os.getenv('OPENAI_MODEL','gpt-5.6-luna')
    payload={'model':model,'input':[{'role':'system','content':'你是金融市場晨報編輯。只根據輸入數據，以繁體中文寫1句標題與3個精簡重點，不做投資建議，不捏造。輸出JSON：headline, bullets。'},{'role':'user','content':json.dumps({'market':market,'stocks':stocks,'rates':rates},ensure_ascii=False)[:28000]}]}
    try:
        r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=45); r.raise_for_status(); data=r.json()
        text=''
        for o in data.get('output',[]):
            for c in o.get('content',[]):
                if c.get('type')=='output_text': text+=c.get('text','')
        text=text.strip().removeprefix('```json').removesuffix('```').strip(); parsed=json.loads(text)
        base.update({'mode':'openai','headline':parsed.get('headline',base['headline']),'bullets':parsed.get('bullets',base['bullets'])})
    except Exception as e: print('OpenAI optional brief failed:',e)
    return base

def update_brief():
    m,s,r=load_json('market.json'),load_json('stocks.json'),load_json('rates.json')
    base=rules_brief(m,s,r); out=openai_brief(base,m,s,r); out['as_of']=datetime.now(timezone.utc).isoformat(); save('brief.json',out)

def main():
    cfg=load_cfg(); update_market(cfg); update_stocks(cfg); update_rates(); update_news(); update_calendar(); update_brief()
if __name__=='__main__': main()
