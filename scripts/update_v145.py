from __future__ import annotations
from datetime import datetime, timezone
import html, re
import requests, feedparser
from bs4 import BeautifulSoup
import update_v144 as prev
from update_v144 import *

# V1.4.6: dual-source financial news radar with 12 Treasury-oriented themes.
PREFERRED_SOURCES_145 = {
    '鉅亨網':100,'Anue鉅亨':100,'經濟日報':98,'自由財經':96,'路透':95,'Reuters':95,
    '彭博':93,'Bloomberg':93,'華爾街日報':92,'Wall Street Journal':92,'WSJ':92,
    '金融時報':90,'Financial Times':90,'工商時報':86,'MoneyDJ':84,'Yahoo奇摩股市':82,
    '中央社':80,'CNBC':78,'MarketWatch':76,'財訊':74,'今周刊':72
}

THEME_QUERIES_145 = {
    '美股':'美股 標普500 那斯達克 道瓊 華爾街 財報 美股期貨',
    '美債':'美國公債 美債 Treasury 殖利率 2年 10年 30年 殖利率曲線',
    '半導體':'半導體 台積電 NVIDIA AMD ASML 晶片 AI伺服器 HBM',
    '軟體 / AI':'人工智慧 AI 軟體 Microsoft Google Meta OpenAI 雲端 科技',
    '央行':'聯準會 Fed FOMC ECB BOJ 央行 升息 降息 利率決策',
    '美國數據':'美國 CPI PPI 非農 就業 GDP 零售銷售 PMI 消費者信心 經濟數據',
    '能源 / 油價':'原油 WTI Brent OPEC 天然氣 能源 油價',
    '貴金屬 / 黃金':'黃金 金價 白銀 貴金屬 COMEX 美元 實質利率',
    '歐洲':'歐洲 ECB 歐元 英國 德國 法國 經濟 股市 歐債',
    '日本':'日本 日銀 BOJ 日圓 日本公債 JGB 日本經濟 日股',
    '中國':'中國 人民幣 經濟 房市 股市 刺激政策 人民銀行',
    '台灣':'台股 加權指數 外資 台積電 新台幣 央行 出口 財經',
}


def clean_news_title_145(value):
    text=BeautifulSoup(html.unescape(str(value or '')),'html.parser').get_text(' ',strip=True)
    text=re.sub(r'\s+',' ',text).strip()
    known='|'.join(re.escape(k) for k in sorted(PREFERRED_SOURCES_145,key=len,reverse=True))
    text=re.sub(rf'\s+-\s+(?:{known})\s*$','',text,flags=re.I)
    return text.strip()


def news_key_145(title):
    return re.sub(r'[\W_]+','',clean_news_title_145(title).lower(),flags=re.UNICODE)[:180]


def source_score_145(source):
    s=(source or '').lower(); best=0
    for k,v in PREFERRED_SOURCES_145.items():
        if k.lower() in s: best=max(best,v)
    return best


def clean_summary_145(raw,title):
    txt=BeautifulSoup(html.unescape(str(raw or '')),'html.parser').get_text(' ',strip=True)
    txt=re.sub(r'\s+',' ',txt).strip()
    if not txt or txt.lower()==title.lower(): return ''
    if len(txt)>220: txt=txt[:220].rstrip(' ,;，；')+'…'
    return txt


def google_candidates_145(query):
    q=f'{query} when:3d'
    url='https://news.google.com/rss/search?q='+requests.utils.quote(q)+'&hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
    r=get142(url,headers={'Accept':'application/rss+xml,application/xml,text/xml,*/*'})
    feed=feedparser.parse(r.content)
    out=[]
    for i,e in enumerate(feed.entries[:50]):
        title=clean_news_title_145(e.get('title',''))
        if not title: continue
        source=e.source.get('title','') if isinstance(e.get('source'),dict) else ''
        score=source_score_145(source)+max(0,50-i)+(20 if re.search(r'[\u4e00-\u9fff]',title) else 0)
        out.append({'title':title,'summary':clean_summary_145(e.get('summary') or e.get('description') or '',title),'source':source or 'Google News','url':e.get('link','#'),'published':e.get('published',''),'score':score,'provider':'Google News'})
    return out


def bing_candidates_145(query):
    url='https://www.bing.com/news/search?q='+requests.utils.quote(query)+'&format=rss&setlang=zh-tw'
    r=get142(url,headers={'Accept':'application/rss+xml,application/xml,text/xml,*/*'})
    feed=feedparser.parse(r.content)
    out=[]
    for i,e in enumerate(feed.entries[:40]):
        title=clean_news_title_145(e.get('title',''))
        if not title: continue
        source=''
        if isinstance(e.get('source'),dict): source=e.source.get('title','') or ''
        if not source:
            m=re.search(r'\s+-\s+([^\-]{2,40})$',str(e.get('title','')))
            if m: source=m.group(1).strip()
        score=source_score_145(source)+max(0,35-i)+(18 if re.search(r'[\u4e00-\u9fff]',title) else 0)
        out.append({'title':title,'summary':clean_summary_145(e.get('summary') or e.get('description') or '',title),'source':source or 'Bing News','url':e.get('link','#'),'published':e.get('published',''),'score':score,'provider':'Bing News'})
    return out


def update_news():
    rows=[]; used=set(); providers=set()
    for cat,q in THEME_QUERIES_145.items():
        candidates=[]
        try:
            got=google_candidates_145(q); candidates.extend(got)
            if got: providers.add('Google News RSS')
        except Exception as e: print('Google news',cat,e)
        try:
            got=bing_candidates_145(q); candidates.extend(got)
            if got: providers.add('Bing News RSS')
        except Exception as e: print('Bing news',cat,e)
        local={}
        for x in candidates:
            k=news_key_145(x['title'])
            if not k: continue
            if k not in local or x.get('score',0)>local[k].get('score',0): local[k]=x
        ranked=sorted(local.values(),key=lambda z:z.get('score',0),reverse=True)
        chosen=None
        for x in ranked:
            k=news_key_145(x['title'])
            if k in used: continue
            chosen=x; used.add(k); break
        if not chosen: continue
        second=next((x for x in ranked if news_key_145(x['title'])!=news_key_145(chosen['title']) and news_key_145(x['title']) not in used),None)
        paragraph=chosen.get('summary','').strip()
        if not paragraph:
            paragraph=f"主要焦點：{chosen['title']}。"
        if second and len(paragraph)<130:
            paragraph += f" 延伸關注：{second['title']}。"
        item={k:v for k,v in chosen.items() if k not in ('score','provider')}
        item['category']=cat; item['summary']=paragraph
        rows.append(item)
    save('news.json',{
        'as_of':datetime.now(timezone.utc).isoformat(),
        'source':' + '.join(sorted(providers)) if providers else 'news feeds unavailable',
        'strategy':'12 themes; financial publishers ranked first; one focus per theme',
        'items':rows
    })

update_market=prev.update_market
