from __future__ import annotations
from datetime import datetime, timezone
import re, html
import requests, feedparser
from bs4 import BeautifulSoup
import update_v143 as prev
from update_v143 import *

PREFERRED_SOURCES = {
    '鉅亨網':100,'Anue鉅亨':100,'經濟日報':98,'自由財經':96,'路透':95,'Reuters':95,
    '彭博':93,'Bloomberg':93,'華爾街日報':92,'Wall Street Journal':92,'WSJ':92,
    '金融時報':90,'Financial Times':90,'工商時報':84,'MoneyDJ':82,'Yahoo奇摩股市':80,
    'CNBC':78,'MarketWatch':76,'財訊':74,'今周刊':72
}

THEME_QUERIES = {
    '美股':'美股 標普500 那斯達克 道瓊 財報 華爾街',
    '半導體':'半導體 台積電 NVIDIA AMD ASML 晶片 AI伺服器',
    '軟體 / AI':'人工智慧 AI 軟體 Microsoft Google Meta OpenAI 科技',
    '央行 / 利率':'聯準會 Fed FOMC 利率 美債 殖利率 央行 降息 升息',
    '能源':'原油 WTI Brent OPEC 天然氣 能源 油價',
    '歐洲':'歐洲 ECB 歐元 英國 德國 法國 經濟 股市',
    '中國':'中國 人民幣 經濟 房市 股市 刺激政策',
    '地產':'房地產 房貸 REIT 商用不動產 地產 利率',
    '台灣':'台股 加權指數 外資 台積電 新台幣 財經',
}


def _source_score(source):
    s=(source or '').lower()
    best=0
    for k,v in PREFERRED_SOURCES.items():
        if k.lower() in s: best=max(best,v)
    return best


def _clean_summary(raw, title):
    txt=BeautifulSoup(html.unescape(raw or ''),'html.parser').get_text(' ',strip=True)
    txt=re.sub(r'\s+',' ',txt).strip()
    # Google News RSS often repeats the headline and source. Keep a short readable paragraph only.
    if not txt or txt.lower()==(title or '').lower(): return title
    if len(txt)>260: txt=txt[:257].rsplit(' ',1)[0]+'…'
    return txt


def _google_news_candidates(query):
    q=f'{query} when:2d'
    url='https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
    try:
        r=get142(url,headers={'Accept':'application/rss+xml,application/xml,text/xml,*/*'})
        feed=feedparser.parse(r.content)
    except Exception:
        feed=feedparser.parse(url)
    out=[]
    for i,e in enumerate(feed.entries[:40]):
        title=clean_news_title(e.get('title',''))
        if not title: continue
        source=e.source.get('title','') if isinstance(e.get('source'),dict) else ''
        score=_source_score(source) + max(0,40-i)
        # Prefer Traditional-Chinese / Chinese headlines but still allow strong international financial sources.
        if re.search(r'[\u4e00-\u9fff]',title): score+=20
        summary=_clean_summary(e.get('summary') or e.get('description') or '',title)
        out.append({'title':title,'summary':summary,'source':source,'url':e.get('link','#'),'published':e.get('published',''),'score':score})
    return out


def update_news():
    rows=[]; used=set()
    for cat,q in THEME_QUERIES.items():
        try:
            candidates=_google_news_candidates(q)
        except Exception as e:
            print('news',cat,e); candidates=[]
        chosen=None
        for x in sorted(candidates,key=lambda z:z.get('score',0),reverse=True):
            k=news_key(x['title'])
            if k in used: continue
            used.add(k); chosen=x; break
        if chosen:
            chosen.pop('score',None); chosen['category']=cat; rows.append(chosen)
    save('news.json',{'as_of':datetime.now(timezone.utc).isoformat(),'source':'Google News RSS · broad themed finance search · preferred financial publishers ranked first','items':rows})


def _to_int(s):
    m=re.search(r'-?\d[\d,]*',str(s or ''))
    return int(m.group().replace(',','')) if m else None


def twse_market_stats():
    url='https://www.twse.com.tw/exchangeReport/MI_INDEX?response=html&type=MS'
    r=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9'})
    soup=BeautifulSoup(r.text,'html.parser')
    turnover=None; up=None; down=None; flat=None
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'])]
        if not cells: continue
        first=cells[0].replace(' ','')
        if first.startswith('1.一般股票') and len(cells)>=2:
            turnover=_to_int(cells[1])
        elif first.startswith('上漲') and len(cells)>=3:
            up=_to_int(cells[-1])
        elif first.startswith('下跌') and len(cells)>=3:
            down=_to_int(cells[-1])
        elif first.startswith('持平') and len(cells)>=3:
            flat=_to_int(cells[-1])
    text=soup.get_text(' ',strip=True)
    dm=re.search(r'(\d{3})年(\d{2})月(\d{2})日',text)
    trade_date=None
    if dm:
        trade_date=f'{int(dm.group(1))+1911:04d}-{dm.group(2)}-{dm.group(3)}'
    if turnover is None and up is None and down is None:
        raise ValueError('TWSE market statistics not parsed')
    directional=(up or 0)+(down or 0)
    return {
        'date':trade_date,
        'turnover_twd':turnover,
        'turnover_100m_twd':round(turnover/100_000_000,1) if turnover is not None else None,
        'advance_count':up,'decline_count':down,'flat_count':flat,
        'advance_pct':round((up/directional)*100,1) if up is not None and directional else None,
        'decline_pct':round((down/directional)*100,1) if down is not None and directional else None,
        'source':'TWSE MI_INDEX'
    }


def update_market(cfg):
    prev.update_market(cfg)
    m=load_json('market.json')
    # Remove OTC index from the Taiwan card; keep the weighted index only.
    m['taiwan']=[x for x in (m.get('taiwan') or []) if x.get('symbol')=='^TWII' or '加權' in str(x.get('name',''))]
    try:
        m['taiwan_stats']=twse_market_stats()
    except Exception as e:
        print('TWSE market stats',e)
        old=m.get('taiwan_stats') or {}
        if old: old['fallback']=True; m['taiwan_stats']=old
    save('market.json',m)
