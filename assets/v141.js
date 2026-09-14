// V1.4.1 UI overrides. Loaded after app.js, then reloads data once using the upgraded renderers.
renderRates=function(r){
  const core=(r.rates||[]).filter(x=>['DGS2','DGS5','DGS10','DGS30'].includes(x.series));
  $('#rates').innerHTML=core.length?core.map(x=>{const val=x.value==null?'—':`${fmt(x.value,3)}%`;const ch=x.change_bps==null?'—':`${sign(x.change_bps)}${fmt(x.change_bps,1)} bps`;return `<div class="rate-item"><div><div class="rate-name">${esc(x.name)}</div><div class="rate-value">${val}</div><div class="rate-source">${esc(x.source||'')}</div></div><div class="rate-change ${cls(x.change_bps)}">${ch}</div></div>`}).join(''):'<div class="empty">美債資料暫時無法取得，等待下一次官方資料更新。</div>';
};

renderProfessional=function(p){
  $('#yieldCurve').innerHTML=(p.yield_curve||[]).length?(p.yield_curve||[]).map(x=>`<div class="curve-point"><span>${esc((x.name||'').replace('美債 ',''))}</span><b>${x.value==null?'—':fmt(x.value,3)+'%'}</b><small class="${cls(x.change_bps)}">${x.change_bps==null?'—':sign(x.change_bps)+fmt(x.change_bps,1)+' bps'}</small></div>`).join(''):'<div class="empty">等待 U.S. Treasury 官方曲線資料。</div>';
  $('#policyRates').innerHTML=(p.policy_rates||[]).length?(p.policy_rates||[]).map(x=>`<div class="policy-row"><span>${esc(x.name)}</span><b>${x.value==null?'—':fmt(x.value,3)+'%'}</b></div>`).join(''):'<div class="empty">政策利率資料更新中</div>';
  const f=p.fed_pricing||{}, outcomes=f.outcomes||[];
  if(outcomes.length){
    const range=(o)=>o.target_low!=null&&o.target_high!=null?`${fmt(o.target_low,2)}–${fmt(o.target_high,2)}%`:`${o.change_bps>0?'+':''}${o.change_bps}bp`;
    const rows=outcomes.map((o,i)=>`<div class="prob-row ${i===0?'primary':''}"><div><b>${esc(o.label)} ${o.change_bps===0?'':(o.change_bps>0?'+':'')+o.change_bps+'bp'}</b><small>${range(o)}</small></div><strong>${fmt(o.probability,1)}%</strong><div class="prob-bar"><span style="width:${Math.max(0,Math.min(100,Number(o.probability)||0))}%"></span></div></div>`).join('');
    $('#fedPricing').innerHTML=`<div class="fed-meeting"><div><span>Next FOMC</span><b>${esc(f.meeting_date||'—')}</b></div><div><span>倒數</span><b>${f.days_to_meeting==null?'—':f.days_to_meeting+' 天'}</b></div></div>${rows}<div class="fed-detail"><span>${esc(f.contract||'')}</span><span>Price ${f.futures_price==null?'—':fmt(f.futures_price,3)}</span><span>EFFR ${f.effective_rate==null?'—':fmt(f.effective_rate,3)+'%'}</span></div><small class="method-note">${esc(f.methodology||'')}</small>`;
  }else $('#fedPricing').innerHTML='<div class="empty">Fed Funds Futures 月別合約資料暫時無法取得；不以 0% 代替缺值。</div>';
  $('#asiaFx').innerHTML=(p.asia_fx||[]).map(x=>`<div class="asia-row"><span>${esc(x.name)}</span><b>${x.price==null?'—':fmt(x.price,x.decimals??3)}</b><em class="${cls(x.change_pct)}">${pct(x.change_pct)}</em></div>`).join('');
};

renderPositioning=function(p){
  const x=p?.tx_foreign||{},el=$('#foreignPositioning');if(!el)return;
  if(p?.status!=='ok'||x.oi_net_contracts==null){el.innerHTML='<div class="empty compact-empty">TAIFEX 外資台指期資料暫時無法取得；保留上一筆有效值時會標示 fallback。</div>';return}
  el.innerHTML=`<div class="position-main"><span>未平倉淨部位</span><b class="${cls(x.oi_net_contracts)}">${sign(x.oi_net_contracts)}${fmt(x.oi_net_contracts,0)} 口</b></div><div class="position-grid"><div><span>多單</span><strong>${fmt(x.oi_long_contracts,0)}</strong></div><div><span>空單</span><strong>${fmt(x.oi_short_contracts,0)}</strong></div><div><span>當日淨額</span><strong class="${cls(x.trade_net_contracts)}">${sign(x.trade_net_contracts)}${fmt(x.trade_net_contracts,0)}</strong></div></div><small>臺股期貨 · 外資 · ${esc(x.date||'')} · TAIFEX 官方</small>`;
};

renderPulse=function(m,r){
  const v=(m.pulse||[]).find(x=>x.symbol==='^VIX'),ru=(m.pulse||[]).find(x=>x.symbol==='^RUT'),so=(r.rates||[]).find(x=>x.series==='SOFR'),cv=(r.rates||[]).find(x=>x.series==='2S10S');
  const val=(x,d=2,s='')=>x==null?'—':fmt(x,d)+s;
  const a=[v&&['VIX',val(v.price,2),pct(v.change_pct)],ru&&['Russell 2000',val(ru.price,2),pct(ru.change_pct)],so&&['SOFR',val(so.value,3,'%'),so.change_bps==null?'—':`${sign(so.change_bps)}${fmt(so.change_bps,1)} bps`],cv&&['2Y10Y',cv.value==null?'—':`${sign(cv.value)}${fmt(cv.value,1)} bps`,cv.change_bps==null?'—':`${sign(cv.change_bps)}${fmt(cv.change_bps,1)} bps`]].filter(Boolean);
  $('#pulseGrid').innerHTML=a.map(x=>`<article class="pulse-card"><div class="pulse-name">${x[0]}</div><div class="pulse-row"><div class="pulse-value">${x[1]}</div><div>${x[2]}</div></div></article>`).join('');
};

renderCalendar=function(c){
  const badge=$('#calendarSourceBadge'),note=$('#calendarCostNote');
  if(badge) badge.textContent=c.source_mode==='api-key'?'Calendar · API':c.source_mode==='investing-public'?'Calendar · Public':'Calendar';
  if(note) note.textContent=(c.source?`來源：${c.source}。 `:'')+(c.cost_note||'');
  $('#calendar').innerHTML=(c.items||[]).slice(0,12).map(x=>`<div class="cal-item"><div class="cal-time">${esc(x.time||'—')}</div><div class="cal-text"><b>${esc(x.title)}</b><br><span class="muted">${esc(x.country||'')} · A ${esc(x.actual||'—')} / F ${esc(x.forecast||'—')} / P ${esc(x.previous||'—')}</span>${x.surprise!=null?`<span class="surprise ${cls(x.surprise)}">Δ ${sign(x.surprise)}${fmt(x.surprise,2)}</span>`:''}</div></div>`).join('')||'<div class="empty">今日行事曆資料暫時不可用；系統不會用假資料填補。</div>';
  const now=taipei().h*60+taipei().m,e=(c.items||[]).map(x=>{const z=(x.time||'').split(':').map(Number);return{...x,min:z.length===2?z[0]*60+z[1]-now:null}}).filter(x=>x.min!=null&&x.min>=0).sort((a,b)=>a.min-b.min)[0];
  $('#nextEvent').innerHTML=e?`<div><span class="event-time">${esc(e.time)}</span><b>${esc(e.title)}</b><small>${esc(e.country)}</small></div><strong>T-${Math.floor(e.min/60)}h ${e.min%60}m</strong>`:'<span class="event-empty">今日暫無後續事件或資料尚未更新</span>';
};

// app.js performs an initial load before this override file executes. Refresh once so V1.4.1 renderers take effect immediately.
load();
