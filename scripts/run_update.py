from __future__ import annotations
import json, traceback
from datetime import datetime, timezone
import update_v146c as u

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
    if not new.get('taiwan_stats') and old.get('taiwan_stats'):
        new['taiwan_stats']={**old['taiwan_stats'],'fallback':True}
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
    if predicate(new): return new
    if old:
        old['fallback_at']=datetime.now(timezone.utc).isoformat()
        old['fallback_reason']='latest source unavailable; preserving last good data'
        save(name, old)
        return old
    return new

def main():
    cfg=u.load_cfg()
    old={n:load(n) for n in ['market.json','stocks.json','rates.json','news.json','calendar.json','positioning.json','professional.json','brief.json']}
    critical_failures=[]
    stages=[
        ('market', lambda:u.update_market(cfg), False),
        ('stocks', lambda:u.update_stocks(cfg), False),
        ('rates', u.update_rates, False),
        ('news', u.update_news, False),
        ('calendar', u.update_calendar, True),
        ('positioning', u.update_positioning, False),
        ('professional', u.update_professional, False),
    ]
    for name, fn, critical in stages:
        try:
            fn()
        except Exception as e:
            print(f'[WARN] {name} stage failed: {e}')
            traceback.print_exc()
            if critical:
                critical_failures.append(f'{name}: {e}')

    save('market.json',merge_quote_sections(load('market.json'), old['market.json'], ['indices','pulse','taiwan','commodities','fx']))
    save('stocks.json',merge_quote_sections(load('stocks.json'), old['stocks.json'], ['stocks']))
    save('rates.json',merge_rates(load('rates.json'), old['rates.json']))
    restore_if_empty('news.json', old['news.json'], lambda x: bool(x.get('items')))
    restore_if_empty('calendar.json', old['calendar.json'], lambda x: x.get('status')=='ok' and bool(x.get('items')))
    restore_if_empty('positioning.json', old['positioning.json'], lambda x: x.get('status')=='ok' and x.get('tx_foreign',{}).get('oi_net_contracts') is not None)
    p=load('professional.json'); oldp=old['professional.json']
    if not p.get('yield_curve') and oldp.get('yield_curve'): p['yield_curve']=oldp['yield_curve']
    if not p.get('policy_rates') and oldp.get('policy_rates'): p['policy_rates']=oldp['policy_rates']
    save('professional.json',p)

    try:
        u.update_brief()
    except Exception as e:
        print('[WARN] brief stage failed:',e)
        traceback.print_exc()
        if old['brief.json']:
            save('brief.json',old['brief.json'])
        critical_failures.append(f'brief: {e}')

    # Validate the two areas that previously looked successful while actually
    # failing and silently restoring stale JSON.
    cal=load('calendar.json'); brief=load('brief.json')
    if cal.get('source_mode') != 'Official global central banks + official statistics + market-calendar enrichment':
        critical_failures.append('calendar validation: new V1.4.6c schema was not generated')
    if brief.get('today_filter') != 'calendar date == Taipei today; news published date == Taipei today; future events forbidden':
        critical_failures.append('brief validation: strict Taipei-today filter was not generated')

    if critical_failures:
        raise RuntimeError('Critical data pipeline failure(s): ' + ' | '.join(critical_failures))
    print('V1.4.6c update completed and validated: global calendar + strict today filtering are live.')

if __name__=='__main__': main()
