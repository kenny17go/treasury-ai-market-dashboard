from __future__ import annotations
import json, traceback
from pathlib import Path
from datetime import datetime, timezone
import update_v142 as u

DATA = u.DATA

def load(name):
    p = DATA / name
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def merge_quote_sections(new, old, keys):
    for sec in keys:
        old_map = {x.get('symbol') or x.get('name'): x for x in old.get(sec, [])}
        merged = []
        for x in new.get(sec, []):
            k = x.get('symbol') or x.get('name')
            ox = old_map.get(k, {})
            if x.get('price') is None and ox.get('price') is not None:
                x = {**ox, **{kk: vv for kk, vv in x.items() if vv not in (None, [], '')}}
            merged.append(x)
        new[sec] = merged
    return new

def merge_rates(new, old):
    old_map = {x.get('series'): x for x in old.get('rates', [])}
    out=[]
    for x in new.get('rates', []):
        ox=old_map.get(x.get('series'), {})
        if x.get('value') is None and ox.get('value') is not None:
            x={**ox, **{k:v for k,v in x.items() if v is not None}}
            x['fallback']=True
        out.append(x)
    present={x.get('series') for x in out}
    for sid,ox in old_map.items():
        if sid not in present and ox.get('value') is not None:
            out.append({**ox,'fallback':True})
    new['rates']=out
    return new

def restore_if_empty(name, old, predicate):
    new=load(name)
    if predicate(new):
        return new
    if old:
        old['fallback_at']=datetime.now(timezone.utc).isoformat()
        old['fallback_reason']='latest source unavailable; preserving last good data'
        save(name, old)
        return old
    return new

def main():
    cfg=u.load_cfg()
    old={n:load(n) for n in ['market.json','stocks.json','rates.json','news.json','calendar.json','positioning.json','professional.json','brief.json']}

    stages=[
        ('market', lambda:u.update_market(cfg)),
        ('stocks', lambda:u.update_stocks(cfg)),
        ('rates', u.update_rates),
        ('news', u.update_news),
        ('calendar', u.update_calendar),
        ('positioning', u.update_positioning),
        ('professional', u.update_professional),
    ]
    for name, fn in stages:
        try:
            fn()
        except Exception as e:
            print(f'[WARN] {name} stage failed: {e}')
            traceback.print_exc()

    m=merge_quote_sections(load('market.json'), old['market.json'], ['indices','pulse','taiwan','commodities','fx']); save('market.json',m)
    s=merge_quote_sections(load('stocks.json'), old['stocks.json'], ['stocks']); save('stocks.json',s)
    r=merge_rates(load('rates.json'), old['rates.json']); save('rates.json',r)

    restore_if_empty('news.json', old['news.json'], lambda x: bool(x.get('items')))
    # Calendar source may be valid even on a no-event day. Only restore old data when the provider itself is unavailable.
    restore_if_empty('calendar.json', old['calendar.json'], lambda x: x.get('status')=='ok')
    restore_if_empty('positioning.json', old['positioning.json'], lambda x: x.get('status')=='ok' and x.get('tx_foreign',{}).get('oi_net_contracts') is not None)

    p=load('professional.json'); oldp=old['professional.json']
    fp=p.get('fed_pricing') or {}; ofp=oldp.get('fed_pricing') or {}
    if not fp.get('outcomes') and ofp.get('outcomes'):
        p['fed_pricing']={**ofp,'fallback':True}
    if not p.get('yield_curve') and oldp.get('yield_curve'): p['yield_curve']=oldp['yield_curve']
    if not p.get('policy_rates') and oldp.get('policy_rates'): p['policy_rates']=oldp['policy_rates']
    save('professional.json',p)

    try:
        u.update_brief()
    except Exception as e:
        print('[WARN] brief stage failed:',e)
        traceback.print_exc()
        if old['brief.json']: save('brief.json',old['brief.json'])

    print('V1.4.2 update completed; calendar, policy rates, Fed probability and financial-news source filters enabled.')

if __name__=='__main__':
    main()
