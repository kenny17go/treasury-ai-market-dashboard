// V1.4.8 consolidated UI overrides.
// app.js performs the initial load; this file only overrides final renderers.

function txSessionInfo(){
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
  const get=t=>parts.find(x=>x.type===t)?.value;
  const w=get('weekday'), mins=Number(get('hour'))*60+Number(get('minute'));
  const weekday=['Mon','Tue','Wed','Thu','Fri'].includes(w);
  const earlyNight=['Tue','Wed','Thu','Fri','Sat'].includes(w)&&mins<300;
  const day=weekday&&mins>=525&&mins<825;
  const night=(weekday&&mins>=900)||earlyNight;
  if(day) return {label:'日盤',state:'open',detail:'08:45–13:45'};
  if(night) return {label:'夜盤',state:'open',detail:'15:00–05:00'};
  return {label:'休市',state:'closed',detail:'目前非一般交易時段'};
}

function renderTaiwanFutures(q){
  const box=$('#taiwanFuturesQuote'), badge=$('#txSessionBadge');
  if(!box||!badge) return;
  const sess=txSessionInfo();
  badge.textContent=sess.label;
  badge.className=`tag tx-session ${sess.state}`;
  if(!q||q.price==null){
    box.innerHTML=`<div class="empty compact-empty">台指期近月報價暫時無法取得。<small>${esc(sess.detail)}</small></div>`;
    return;
  }
  const time=q.quote_time?` · ${esc(q.quote_time)}`:'';
  const fallback=q.fallback?' · Last valid':'';
  const marker=Number(q.change_pct)<0?'▼':Number(q.change_pct)>0?'▲':'';
  const volume=q.volume==null?'—':`${fmt(q.volume,0)} 口`;
  box.innerHTML=`<div class="tx-quote-main"><div><span>${esc(q.name||'台指期近一')} <em>${esc(q.symbol||'WTX&')}</em></span><b>${fmt(q.price,0)}</b></div><div class="tx-change ${cls(q.change_pct)}"><strong>${marker} ${pct(q.change_pct)}</strong><small>${q.change==null?'—':`${sign(q.change)}${fmt(q.change,0)}`}</small></div></div><div class="tx-quote-meta"><span>${esc(sess.detail)} · 成交量 <b>${volume}</b></span><span>${esc(q.source||'Yahoo股市')}${time}${fallback}</span></div>`;
}

renderMarket = function(m){
  const report=$('#reportDate'), status=$('#marketStatus');
  if(report) report.textContent=m.as_of?new Date(m.as_of).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})+' 更新':'等待更新';
  if(status) status.textContent=m.status||'Auto Update';
  fresh(m.as_of);

  const heroEl=$('#heroIndices');
  if(heroEl) heroEl.innerHTML=(m.indices||[]).slice(0,4).map(hero).join('')||'<div class="empty">尚無市場資料</div>';

  const tw=$('#taiwanMarkets');
  if(tw){
    const idx=(m.taiwan||[]).find(x=>x.symbol==='^TWII')||(m.taiwan||[])[0];
    const s=m.taiwan_stats||{};
    const official=s.source==='TWSE MI_INDEX official'||idx?.source==='TWSE official';
    const idxHtml=idx?`<div class="mini-market tw-index-row"><div><div class="label">台灣加權指數</div><div class="value">${fmt(idx.price)}</div><small>${esc(idx.quote_date||s.date||'')} · ${official?'TWSE 官方':'資料來源待確認'}</small></div><div class="delta ${cls(idx.change_pct)}">${pct(idx.change_pct)}<small>${idx.change==null?'':`${sign(idx.change)}${fmt(idx.change,2)} 點`}</small></div></div>`:'<div class="empty">台灣加權指數官方資料暫時無法取得。</div>';
    const turnover=s.turnover_100m_twd==null?'—':`${fmt(s.turnover_100m_twd,2)} 億元`;
    const volume=s.volume_100m_shares==null?'—':`${fmt(s.volume_100m_shares,2)} 億股`;
    const up=s.advance_pct==null?'—':`${fmt(s.advance_pct,1)}%`;
    const down=s.decline_pct==null?'—':`${fmt(s.decline_pct,1)}%`;
    const upCount=s.advance_count==null?'—':fmt(s.advance_count,0);
    const downCount=s.decline_count==null?'—':fmt(s.decline_count,0);
    const barUp=s.advance_pct==null?50:Math.max(0,Math.min(100,Number(s.advance_pct)));
    tw.innerHTML=idxHtml+`<div class="twse-stats"><div class="tw-stat turnover"><span>上市成交金額</span><b>${turnover}</b><small>${esc(s.date||'')} · TWSE 官方</small></div><div class="tw-stat volume"><span>上市成交量</span><b>${volume}</b><small>成交股數 · TWSE 官方</small></div><div class="tw-stat breadth"><span>上漲 vs 下跌個股</span><div class="breadth-values"><b class="up">${up}</b><em>${upCount} 檔</em><b class="down">${down}</b><em>${downCount} 檔</em></div><div class="breadth-bar"><i style="width:${barUp}%"></i></div><small>方向佔比不含持平股票</small></div></div>`;
  }
  renderTaiwanFutures(m.taiwan_futures);

  const commodities=$('#commodities');
  if(commodities) commodities.innerHTML=(m.commodities||[]).map(q=>`<div>${esc(q.name)}</div><div>${q.price==null?'—':fmt(q.price)}</div><div class="${cls(q.change_pct)}">${pct(q.change_pct)}</div>`).join('');
  const fx=$('#fx');
  if(fx) fx.innerHTML=(m.fx||[]).slice(0,9).map(q=>`<div>${esc(q.name)}</div><div>${q.price==null?'—':fmt(q.price,q.decimals??4)}</div><div class="${cls(q.change_pct)}">${pct(q.change_pct)}</div>`).join('');
};

renderRates = function(r){
  const all=(r&&r.rates)||[];
  const core=all.filter(x=>['DGS2','DGS5','DGS10','DGS30'].includes(x.series));
  const by=Object.fromEntries(all.map(x=>[x.series,x]));
  const box=$('#rates');
  if(!box) return;

  const cards=core.length?core.map(x=>`<div class="rate-card"><span>${esc((x.name||'').replace('美債 ',''))}</span><b>${x.value==null?'—':fmt(x.value,3)+'%'}</b><small class="${cls(x.change_bps)}">${x.change_bps==null?'日變化 —':`日變化 ${sign(x.change_bps)}${fmt(x.change_bps,1)} bps`}</small></div>`).join(''):'<div class="empty">美債資料暫時無法取得。</div>';

  const calc=(longRate,shortRate)=>{
    if(!longRate||!shortRate||longRate.value==null||shortRate.value==null) return {value:null,change:null};
    return {
      value:(Number(longRate.value)-Number(shortRate.value))*100,
      change:(longRate.change_bps==null||shortRate.change_bps==null)?null:Number(longRate.change_bps)-Number(shortRate.change_bps)
    };
  };
  const s210=by['2S10S']?.value!=null?{value:Number(by['2S10S'].value),change:by['2S10S'].change_bps}:calc(by.DGS10,by.DGS2);
  const s230=calc(by.DGS30,by.DGS2);
  const spreadChip=(label,s)=>`<div class="spread-chip"><span>${label}</span><b>${s.value==null?'—':`${sign(s.value)}${fmt(s.value,1)} bps`}</b><small class="${cls(s.change)}">${s.change==null?'日變化 —':`日變化 ${sign(s.change)}${fmt(s.change,1)} bps`}</small></div>`;
  box.innerHTML=cards+`<div class="spread-strip">${spreadChip('2Y10Y Spread',s210)}${spreadChip('2Y30Y Spread',s230)}</div>`;
};

renderPositioning = function(p){
  const x=p?.tx_foreign||{}, el=$('#foreignPositioning');
  if(!el) return;
  if(p?.status!=='ok'||x.oi_net_contracts==null){
    el.innerHTML='<div class="empty compact-empty">TAIFEX 外資台指期資料暫時無法取得。</div>';
    return;
  }
  el.innerHTML=`<div class="position-main"><span>未平倉淨部位</span><b class="${cls(x.oi_net_contracts)}">${sign(x.oi_net_contracts)}${fmt(x.oi_net_contracts,0)} 口</b></div><div class="position-grid"><div><span>多單</span><strong>${fmt(x.oi_long_contracts,0)}</strong></div><div><span>空單</span><strong>${fmt(x.oi_short_contracts,0)}</strong></div><div><span>當日淨額</span><strong class="${cls(x.trade_net_contracts)}">${sign(x.trade_net_contracts)}${fmt(x.trade_net_contracts,0)}</strong></div></div><small>臺股期貨 · 外資 · ${esc(x.date||'')} · TAIFEX 官方</small>`;
};

renderCalendar = function(c){
  const badge=$('#calendarSourceBadge'), note=$('#calendarCostNote'), list=$('#calendar');
  if(badge) badge.textContent='Global · Official + Multi-source';
  const cleanedNote=String(c?.cost_note||'').replace(/，?永豐期貨與工商時報交叉參考。?/g,'').replace(/；\s*。/g,'。').trim();
  if(note) note.textContent=(c?.source?`來源：${c.source}。 `:'')+cleanedNote;

  const rows=(c?.items||[]).slice(0,24);
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dayLabel=d=>{
    if(!d) return '—';
    if(d===today) return '今天';
    const p=d.split('-');
    return p.length===3?`${Number(p[1])}/${Number(p[2])}`:d;
  };
  const imp=x=>{const n=Math.max(1,Math.min(3,Number(x)||1));return `<span class="cal-importance imp-${n}" aria-label="重要度 ${n}">${'●'.repeat(n)}${'○'.repeat(3-n)}</span>`};
  const val=(label,v)=>`<span><em>${label}</em><b>${v==null||v===''?'—':esc(v)}</b></span>`;
  if(list) list.innerHTML=rows.length?rows.map(x=>`<div class="cal-item cal-v147"><div class="cal-date"><b>${esc(dayLabel(x.date))}</b><span>${esc(x.time||'—')}</span></div><div class="cal-text"><div class="cal-title-line"><span class="cal-flag">${esc(x.flag||'🌐')}</span><b>${esc(x.title||'')}</b>${imp(x.importance)}</div><div class="cal-country">${esc(x.country||'')} ${x.source?'· '+esc(x.source):''}</div><div class="cal-values">${val('前值',x.previous)}${val('預估',x.forecast)}${val('實際',x.actual)}</div></div></div>`).join(''):'<div class="empty">近期財經行事曆暫時無法取得；不使用假資料填補。</div>';

  const now=new Date();
  const events=rows.map(x=>{
    if(!/^\d{4}-\d{2}-\d{2}$/.test(x.date||'')) return null;
    const m=String(x.time||'').match(/^(\d{1,2}):(\d{2})$/);
    const hh=m?Number(m[1]):9, mm=m?Number(m[2]):0;
    const [y,mo,d]=x.date.split('-').map(Number);
    const when=new Date(Date.UTC(y,mo-1,d,hh-8,mm));
    return {...x,when,timeKnown:!!m};
  }).filter(Boolean).filter(x=>x.when.getTime()>=now.getTime()-30*60000).sort((a,b)=>a.when-b.when);
  const e=events[0], next=$('#nextEvent');
  if(next){
    if(e){
      const mins=Math.max(0,Math.round((e.when-now)/60000));
      const countdown=mins<1440?`T-${Math.floor(mins/60)}h ${mins%60}m`:`T-${Math.floor(mins/1440)}d`;
      next.innerHTML=`<div><span class="event-time">${esc(dayLabel(e.date))} ${esc(e.time||'—')}</span><b>${esc((e.flag||'')+' '+(e.title||''))}</b><small>${esc(e.source||e.country||'')}</small></div><strong>${e.timeKnown?countdown:'Upcoming'}</strong>`;
    }else next.innerHTML='<span class="event-empty">近期暫無後續高重要性事件</span>';
  }
};

renderNews = function(n){
  NEWS_DATA=n?.items||[];
  const rows=NEWS_DATA.slice(0,5), box=$('#news');
  if(!box) return;
  box.innerHTML=rows.length?rows.map((x,i)=>{
    const paragraph=(x.summary&&x.summary.trim())||x.title||'';
    const score=x.importance_score==null?'—':Math.round(Number(x.importance_score));
    const assets=(x.related_assets||[]).slice(0,3).map(a=>`<span class="news-cat">${esc(a)}</span>`).join('');
    return `<article class="news-summary-card top-news-card"><div class="news-theme">市場焦點 ${i+1}${x.topic?' · '+esc(x.topic):''}<span class="news-score">Impact ${score}</span></div><a href="${safeUrl(x.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(x.title||'')}</b></a><p>${esc(paragraph)}</p><div class="news-impact-row"><strong>關聯市場</strong>${assets}</div><div class="news-why"><strong>入選原因</strong> ${esc(x.why_selected||'依來源品質、時效與市場影響度排序')}</div><small>${esc(x.source||'財經新聞')} ${x.published?'· '+esc(x.published):''}</small></article>`;
  }).join(''):'<div class="empty">目前沒有取得可用的重點市場新聞。</div>';
};

const _renderBriefV147=renderBrief;
renderBrief = function(b){
  _renderBriefV147(b);
  const el=$('#todayTop');
  if(!el) return;
  const rows=(b?.today_top||[]).slice(0,3);
  while(rows.length<3) rows.push(`今日暫無第 ${rows.length+1} 項已確認的重要事件；不以未來事件補位。`);
  el.innerHTML=rows.map((x,i)=>`<div class="brief-item"><span>${i+1}</span><div>${esc(x)}</div></div>`).join('');
};

renderSignals = function(){};

document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&$('#watchlistModal')?.classList.contains('show')) closeWatchlist();
});
