from __future__ import annotations
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
import re
from bs4 import BeautifulSoup
import update_v146 as prev
from update_v146 import *

# V1.4.6a
# Calendar: Cnyes + official sources are primary, MacroMicro and Sinopac Futures
# are additional market-calendar layers, CTEE remains fallback/cross-check.
# News: replace forced topic buckets with five highest-value market stories.

MARKET_IMPACT_TERMS = {
    'fed':28,'fomc':30,'聯準會':30,'利率':22,'升息':24,'降息':24,
    'treasury':24,'美債':28,'殖利率':24,'cpi':28,'pce':28,'ppi':20,'非農':28,'gdp':20,
    'oil':24,'brent':28,'wti':26,'原油':28,'油價':28,'opec':24,
    'gold':20,'黃金':22,'日銀':22,'boj':22,'ecb':20,'央行':20,
    'tsmc':22,'台積電':22,'nvidia':22,'半導體':20,'ai':18,
    'china':18,'中國':18,'台股':18,'美股':18,'nasdaq':16,'標普':16,
}


def _impact_score(title, summary=''):
    s=(str(title or '')+' '+str(summary or '')).lower()
    score=0
    for k,v in MARKET_IMPACT_TERMS.items():
        if k.lower() in s: score+=v
    return min(score,120)


def _topic_hint(text):
    s=str(text or '').lower()
    rules=[
        ('Fed / 利率',('fed','fomc','聯準會','利率','升息','降息')),
        ('美債',('treasury','美債','殖利率','yield')),
        ('能源',('oil','brent','wti','opec','原油','油價','天然氣')),
        ('黃金',('gold','黃金','白銀','貴金屬')),
        ('AI / 半導體',('ai','nvidia','tsmc','台積電','半導體','晶片','openai')),
        ('日本',('boj','日銀','日圓','japan','日本')),
        ('中國',('china','中國','人民幣','人行','pboc')),
        ('台灣',('台股','台灣','台積電','新台幣')),
        ('美股',('美股','nasdaq','標普','dow','s&p')),
    ]
    for label,keys in rules:
        if any(k in s for k in keys): return label
    return '全球市場'


def update_news():
    # Use several broad market queries instead of category-by-category scraping.
    # This improves hit-rate and lets ranking choose the five stories that matter most.
    queries=[
        '全球市場 Fed 美債 油價 黃金 美股 亞洲 台股 AI when:2d',
        '金融市場 央行 通膨 殖利率 原油 半導體 中國 日本 台灣 when:2d',
        'Reuters Bloomberg 財經 市場 利率 油價 AI 台股 when:2d',
    ]
    pool=[]; providers=set()
    for q in queries:
        try:
            got=prev.google_candidates_145(q); pool.extend(got)
            if got: providers.add('Google News RSS')
        except Exception as e: print('Google broad news',e)
        try:
            got=prev.bing_candidates_145(q.replace(' when:2d','')); pool.extend(got)
            if got: providers.add('Bing News RSS')
        except Exception as e: print('Bing broad news',e)

    # Normalize, rank, and deduplicate. Prefer strong financial publishers, Chinese
    # headlines, recency order, and stories with measurable market impact.
    local={}
    for i,x in enumerate(pool):
        title=prev.clean_news_title_145(x.get('title',''))
        if not title: continue
        k=prev.news_key_145(title)
        if not k: continue
        summary=prev.clean_summary_145(x.get('summary',''),title)
        source=x.get('source','')
        score=prev.source_score_145(source)+_impact_score(title,summary)+max(0,35-min(i,35))
        if re.search(r'[\u4e00-\u9fff]',title): score+=15
        row={**x,'title':title,'summary':summary,'score':score,'topic':_topic_hint(title+' '+summary)}
        if k not in local or score>local[k].get('score',0): local[k]=row

    ranked=sorted(local.values(),key=lambda z:z.get('score',0),reverse=True)
    selected=[]; topic_counts={}
    for x in ranked:
        topic=x.get('topic','全球市場')
        # Soft diversity: no more than two stories with the same topic hint.
        if topic_counts.get(topic,0)>=2: continue
        # Avoid near-duplicate headlines using token overlap.
        words=set(re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+',x['title'].lower()))
        duplicate=False
        for y in selected:
            yw=set(re.findall(r'[A-Za-z0-9\u4e00-\u9fff]+',y['title'].lower()))
            if words and yw and len(words & yw)/max(1,min(len(words),len(yw)))>=0.65:
                duplicate=True; break
        if duplicate: continue
        selected.append(x); topic_counts[topic]=topic_counts.get(topic,0)+1
        if len(selected)>=5: break

    rows=[]
    for rank,x in enumerate(selected,1):
        paragraph=(x.get('summary') or '').strip()
        if not paragraph: paragraph=f"主要焦點：{x['title']}。"
        item={k:v for k,v in x.items() if k not in ('score','provider')}
        item['rank']=rank
        item['summary']=paragraph
        rows.append(item)

    save('news.json',{
        'as_of':datetime.now(timezone.utc).isoformat(),
        'source':' + '.join(sorted(providers)) if providers else 'news feeds unavailable',
        'strategy':'Top 5 market stories; source quality + recency + market impact + deduplication; no forced categories',
        'items':rows
    })


def _generic_calendar_rows(soup, source, default_date=None):
    # First use V1.4.6 table parser.
    rows=prev._parse_table_by_headers(soup,source,default_date)
    if rows: return rows
    # Generic card/list parser for sites that do not expose semantic tables.
    out=[]
    now=datetime.now(TZ8)
    for node in soup.find_all(['li','article','div']):
        txt=re.sub(r'\s+',' ',node.get_text(' ',strip=True)).strip()
        if len(txt)<12 or len(txt)>500: continue
        if not re.search(IMPORTANT_TERMS,txt,re.I): continue
        dm=re.search(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',txt)
        sm=re.search(r'(?<!\d)(\d{1,2})[/-](\d{1,2})(?!\d)',txt)
        if dm:
            date=f'{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}'
        elif sm:
            date=f'{now.year:04d}-{int(sm.group(1)):02d}-{int(sm.group(2)):02d}'
        else:
            date=default_date or now.date().isoformat()
        tm=re.search(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)',txt)
        time_txt=f'{int(tm.group(1)):02d}:{tm.group(2)}' if tm else '—'
        country='Global'
        for c in ('美國','台灣','日本','中國','歐元區','德國','法國','英國','韓國','加拿大','澳洲'):
            if c in txt: country=_canonical_country(c); break
        actual='';forecast='';previous=''
        m=re.search(r'(?:結果|實際|Actual)\s*[:：]?\s*([^\s|]+)',txt,re.I); actual=_clean(m.group(1)) if m else ''
        m=re.search(r'(?:預估|Forecast)\s*[:：]?\s*([^\s|]+)',txt,re.I); forecast=_clean(m.group(1)) if m else ''
        m=re.search(r'(?:前值|Previous)\s*[:：]?\s*([^\s|]+)',txt,re.I); previous=_clean(m.group(1)) if m else ''
        title=re.sub(r'^(?:20\d{2}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2})\s*','',txt)
        title=title[:180]
        out.append({'date':date,'time':time_txt,'title':title,'country':country,'flag':_flag(country),
                    'importance':_importance('',title),'actual':actual,'forecast':forecast,'previous':previous,'source':source})
    # Reduce nested duplicate nodes.
    uniq={}
    for x in out:
        k=_event_key(x)
        if k not in uniq or len(x.get('title',''))<len(uniq[k].get('title','')): uniq[k]=x
    return list(uniq.values())


def calendar_from_macromicro():
    url='https://www.macromicro.me/calendar'
    r=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    return _generic_calendar_rows(BeautifulSoup(r.text,'html.parser'),'財經M平方')


def calendar_from_sinopac():
    # Sinopac publishes a weekly calendar index. Try the index first, then follow
    # the newest calendar link(s) if hrefs are exposed in HTML.
    base='https://www.spf.com.tw/sinopacSPF/research/list_180fdcacb04000005fa4adef23dd5137.do'
    r=get142(base,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
    soup=BeautifulSoup(r.text,'html.parser')
    rows=_generic_calendar_rows(soup,'永豐期貨')
    links=[]
    for a in soup.find_all('a',href=True):
        txt=a.get_text(' ',strip=True)
        if '財經行事曆' in txt:
            links.append(urljoin(base,a['href']))
    for url in links[:3]:
        try:
            rr=get142(url,headers={'Accept-Language':'zh-TW,zh;q=0.9,en;q=0.7'})
            rows.extend(_generic_calendar_rows(BeautifulSoup(rr.text,'html.parser'),'永豐期貨'))
        except Exception as e: print('calendar Sinopac detail',url,e)
    return rows


def update_calendar():
    now=datetime.now(TZ8); end=now+timedelta(days=14)
    layers=[]
    def add(name, fn, priority):
        try:
            got=fn() or []
            layers.append((priority,name,got))
            print('calendar',name,'rows',len(got))
        except Exception as e:
            print('calendar',name,'failed',e); layers.append((priority,name,[]))

    add('鉅亨網', prev.calendar_from_cnyes, 1)
    # Official US release calendars remain a high-confidence source.
    try:
        official=prev._official_calendar() or []
    except Exception as e:
        print('calendar official failed',e); official=[]
    layers.append((1,'BLS/BEA/Federal Reserve',official))
    add('財經M平方', calendar_from_macromicro, 2)
    add('永豐期貨', calendar_from_sinopac, 3)
    add('工商時報', prev.calendar_from_ctee, 4)

    merged={}
    for priority,name,items in sorted(layers,key=lambda z:z[0],reverse=True):
        for x in items:
            try: d=datetime.fromisoformat(x.get('date','')).replace(tzinfo=TZ8)
            except Exception: continue
            if not (now-timedelta(days=1)<=d<=end): continue
            if not re.search(IMPORTANT_TERMS,x.get('title',''),re.I) and int(x.get('importance') or 1)<2: continue
            x['flag']=x.get('flag') or _flag(x.get('country'))
            k=_event_key(x); old=merged.get(k)
            if old is None:
                x['_priority']=priority; merged[k]=x; continue
            # lower priority number = preferred source
            better=x if priority < old.get('_priority',99) else old
            other=old if better is x else x
            for fld in ('actual','forecast','previous','time','country','flag'):
                if not _clean(better.get(fld)) and _clean(other.get(fld)): better[fld]=other[fld]
            better['importance']=max(int(better.get('importance') or 1),int(other.get('importance') or 1))
            sources=[s.strip() for s in (better.get('source','')+' / '+other.get('source','')).split('/') if s.strip()]
            better['source']=' / '.join(dict.fromkeys(sources))
            better['_priority']=min(priority,old.get('_priority',99)); merged[k]=better

    items=[]
    for x in merged.values():
        x.pop('_priority',None); items.append(x)
    items.sort(key=lambda z:(z.get('date',''),z.get('time','99:99'),-int(z.get('importance') or 1)))
    active=[name for _,name,got in layers if got]
    if official: active.insert(1,'BLS/BEA/Federal Reserve')
    save('calendar.json',{
        'as_of':datetime.now(timezone.utc).isoformat(),
        'status':'ok' if items else 'unavailable',
        'source':' + '.join(dict.fromkeys(active)) if active else 'calendar sources unavailable',
        'source_mode':'Cnyes + official primary; MacroMicro enrichment; Sinopac + CTEE fallback/cross-check',
        'window_days':14,
        'cost_note':'鉅亨網＋官方來源為主；財經M平方補強全球事件；永豐期貨與工商時報作備援/交叉參考。前值、預估、實際值僅在來源可取得時顯示。',
        'items':items[:60]
    })

update_market=prev.update_market
