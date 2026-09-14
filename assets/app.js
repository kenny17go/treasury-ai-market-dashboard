const $ = s => document.querySelector(s);
const fmt = (n, d=2) => Number.isFinite(Number(n)) ? Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
const cls = n => Number(n)>0 ? 'up' : Number(n)<0 ? 'down' : 'neutral';
const sign = n => Number(n)>0 ? '+' : '';
const pct = n => Number.isFinite(Number(n)) ? `${sign(n)}${Number(n).toFixed(2)}%` : '—';

async function getJSON(path){ const r=await fetch(`${path}?v=${Date.now()}`,{cache:'no-store'}); if(!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); }
function drawSpark(canvas, values, positive=true){
  const dpr=window.devicePixelRatio||1, rect=canvas.getBoundingClientRect(); if(!rect.width) return;
  canvas.width=rect.width*dpr; canvas.height=rect.height*dpr; const c=canvas.getContext('2d'); c.scale(dpr,dpr);
  const w=rect.width,h=rect.height, arr=(values||[]).map(Number).filter(Number.isFinite); if(arr.length<2) return;
  const min=Math.min(...arr), max=Math.max(...arr), span=(max-min)||1, pad=4;
  const pts=arr.map((v,i)=>[pad+(i/(arr.length-1))*(w-pad*2), pad+(1-(v-min)/span)*(h-pad*2)]);
  const stroke=positive?'#079b82':'#d64b5d', fill=positive?'rgba(7,155,130,.10)':'rgba(214,75,93,.10)';
  c.beginPath(); pts.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y)); c.lineWidth=2;c.strokeStyle=stroke;c.stroke();
  c.lineTo(pts.at(-1)[0],h);c.lineTo(pts[0][0],h);c.closePath();c.fillStyle=fill;c.fill();
}
function heroCard(q){return `<article class="hero-card"><div class="eyebrow">${q.name}</div><div class="big-row"><div class="big-num">${fmt(q.price,q.decimals??2)}</div><div class="change ${cls(q.change_pct)}">${pct(q.change_pct)}<span class="abs-change">${sign(q.change)}${fmt(q.change,2)} 點</span></div></div><canvas class="spark" data-spark='${JSON.stringify(q.spark||[])}' data-pos="${Number(q.change_pct)>=0}"></canvas></article>`}
function updateFreshness(asOf){
  const el=$('#dataFreshness'); if(!el) return;
  if(!asOf){el.textContent='No data';el.className='freshness stale';return;}
  const mins=Math.max(0,Math.round((Date.now()-new Date(asOf).getTime())/60000));
  if(mins<=45){el.textContent=`Fresh · ${mins}m`;el.className='freshness fresh';}
  else if(mins<=180){el.textContent=`Delayed · ${mins}m`;el.className='freshness delayed';}
  else{el.textContent=`Stale · ${Math.round(mins/60)}h`;el.className='freshness stale';}
}
function renderMarket(m){
  $('#reportDate').textContent = m.as_of ? `${new Date(m.as_of).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})} 更新` : '等待更新';
  $('#marketStatus').textContent = m.status || 'Auto Update'; updateFreshness(m.as_of);
  $('#heroIndices').innerHTML=(m.indices||[]).slice(0,4).map(heroCard).join('') || '<div class="empty">尚無市場資料。</div>';
  $('#taiwanMarkets').innerHTML=(m.taiwan||[]).map(q=>`<div class="mini-market"><div><div class="label">${q.name}</div><div class="value">${fmt(q.price,q.decimals??2)}</div></div><div class="delta ${cls(q.change_pct)}">${pct(q.change_pct)}<br>${sign(q.change)}${fmt(q.change,2)}</div><canvas data-spark='${JSON.stringify(q.spark||[])}' data-pos="${Number(q.change_pct)>=0}"></canvas></div>`).join('');
  $('#commodities').innerHTML=(m.commodities||[]).map(q=>`<div class="quote-name">${q.name}</div><div class="quote-val">${fmt(q.price,q.decimals??2)}</div><div class="quote-chg ${cls(q.change_pct)}">${pct(q.change_pct)}</div>`).join('');
  $('#fx').innerHTML=(m.fx||[]).map(q=>`<div class="quote-name">${q.name}</div><div class="quote-val">${fmt(q.price,q.decimals??4)}</div><div class="quote-chg ${cls(q.change_pct)}">${pct(q.change_pct)}</div>`).join('');
}
function rateDisplay(x){ return x.unit==='bps' ? `${sign(x.value)}${fmt(x.value,1)} bps` : `${fmt(x.value,3)}%`; }
function renderRates(r){
  const core=(r.rates||[]).filter(x=>['DGS2','DGS10','DGS30'].includes(x.series));
  $('#rates').innerHTML=core.map(x=>`<div class="rate-item"><div><div class="rate-name">${x.name}</div><div class="rate-value">${rateDisplay(x)}</div></div><div class="rate-change ${cls(x.change_bps)}">${sign(x.change_bps)}${fmt(x.change_bps,1)} bps</div></div>`).join('') || '<div class="empty">利率資料尚未更新。</div>';
}
function renderPulse(m,r){
  const marketPulse=m.pulse||[]; const rates=r.rates||[];
  const vix=marketPulse.find(x=>x.symbol==='^VIX'); const rut=marketPulse.find(x=>x.symbol==='^RUT');
  const sofr=rates.find(x=>x.series==='SOFR'); const curve=rates.find(x=>x.series==='2S10S');
  const cards=[];
  if(vix) cards.push({name:'VIX',value:fmt(vix.price,2),change:pct(vix.change_pct),tone:cls(vix.change_pct),note:'波動率'});
  if(rut) cards.push({name:'Russell 2000',value:fmt(rut.price,2),change:pct(rut.change_pct),tone:cls(rut.change_pct),note:'美國小型股'});
  if(sofr) cards.push({name:'SOFR',value:sofr.value==null?'—':`${fmt(sofr.value,3)}%`,change:sofr.change_bps==null?'—':`${sign(sofr.change_bps)}${fmt(sofr.change_bps,1)} bps`,tone:cls(sofr.change_bps),note:'隔夜資金成本'});
  if(curve) cards.push({name:'2Y10Y',value:curve.value==null?'—':`${sign(curve.value)}${fmt(curve.value,1)} bps`,change:curve.change_bps==null?'—':`${sign(curve.change_bps)}${fmt(curve.change_bps,1)} bps`,tone:cls(curve.value),note:'殖利率曲線'});
  $('#pulseGrid').innerHTML=cards.map(x=>`<article class="pulse-card"><div class="pulse-note">${x.note}</div><div class="pulse-name">${x.name}</div><div class="pulse-row"><div class="pulse-value">${x.value}</div><div class="pulse-change ${x.tone}">${x.change}</div></div></article>`).join('') || '<div class="empty">Treasury Pulse 尚未更新。</div>';
}
function taipeiParts(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',hour12:false,weekday:'short',hour:'2-digit',minute:'2-digit'}).formatToParts(new Date());
  const get=t=>parts.find(x=>x.type===t)?.value; return {weekday:get('weekday'),hour:Number(get('hour')),minute:Number(get('minute'))};
}
function sessionState(open,close,h,m){const x=h*60+m,o=open[0]*60+open[1],c=close[0]*60+close[1];return x>=o&&x<c?'open':'closed'}
function renderSessions(){
  const t=taipeiParts(); const weekday=['Mon','Tue','Wed','Thu','Fri'].includes(t.weekday); const sessions=[
    {name:'亞洲',sub:'Taipei / Tokyo',open:[8,0],close:[15,0]},
    {name:'歐洲',sub:'London / Frankfurt',open:[15,0],close:[24,0]},
    {name:'美國',sub:'New York',open:[21,30],close:[24,0]}
  ];
  $('#sessionStrip').innerHTML=sessions.map(s=>{const st=weekday?sessionState(s.open,s.close,t.hour,t.minute):'closed';return `<div class="session ${st}"><span class="session-dot"></span><div><b>${s.name}</b><small>${s.sub}</small></div><em>${st==='open'?'OPEN':'CLOSED'}</em></div>`}).join('');
}
function eventMinutes(x){ if(!x?.time||!/^[0-2]\d:[0-5]\d$/.test(x.time)) return null; const [h,m]=x.time.split(':').map(Number); const t=taipeiParts(); return h*60+m-(t.hour*60+t.minute); }
function renderNextEvent(c){
  const events=(c.items||[]).map(x=>({...x,_mins:eventMinutes(x)})).filter(x=>x._mins!=null&&x._mins>=0).sort((a,b)=>a._mins-b._mins);
  const e=events[0]; if(!e){$('#nextEvent').innerHTML='<span class="event-empty">今日暫無後續高重要性事件</span>';return;}
  const h=Math.floor(e._mins/60),m=e._mins%60, countdown=h?`${h}h ${m}m`:`${m}m`;
  $('#nextEvent').innerHTML=`<div><span class="event-time">${e.time}</span><b>${e.title}</b><small>${e.country||''}</small></div><strong>T-${countdown}</strong>`;
}
function signalTone(value, inverse=false){if(!Number.isFinite(Number(value)))return 'neutral';const v=Number(value)*(inverse?-1:1);return v>0?'up':v<0?'down':'neutral'}
function arrow(v){return Number(v)>0?'↑':Number(v)<0?'↓':'→'}
function renderSignals(m,r,b){
  const dxy=(m.fx||[]).find(x=>x.name==='DXY'); const r10=(r.rates||[]).find(x=>x.series==='DGS10'); const sp=(m.indices||[]).find(x=>x.symbol==='^GSPC'); const vix=(m.pulse||[]).find(x=>x.symbol==='^VIX');
  const rows=[
    {name:'USD',value:dxy?.change_pct,text:dxy?`${arrow(dxy.change_pct)} ${pct(dxy.change_pct)}`:'—',tone:signalTone(dxy?.change_pct),desc:'DXY 日變動'},
    {name:'10Y Yield',value:r10?.change_bps,text:r10?.change_bps==null?'—':`${arrow(r10.change_bps)} ${sign(r10.change_bps)}${fmt(r10.change_bps,1)} bps`,tone:signalTone(r10?.change_bps),desc:'美債 10Y'},
    {name:'Equity',value:sp?.change_pct,text:sp?`${arrow(sp.change_pct)} ${pct(sp.change_pct)}`:'—',tone:signalTone(sp?.change_pct),desc:'S&P 500'},
    {name:'Volatility',value:vix?.change_pct,text:vix?`${arrow(vix.change_pct)} ${pct(vix.change_pct)}`:'—',tone:signalTone(vix?.change_pct,true),desc:'VIX；下降視為正向'}
  ];
  $('#deskSignals').innerHTML=rows.map(x=>`<div class="signal-row"><span class="signal-light ${x.tone}"></span><div><b>${x.name}</b><small>${x.desc}</small></div><strong class="${x.tone}">${x.text}</strong></div>`).join('');
}
function renderWatch(b){
  $('#watchBadge').textContent=b.mode==='openai'?'AI':'Rules'; const items=b.todays_watch||[];
  $('#todayWatch').innerHTML=items.length?items.slice(0,4).map((x,i)=>`<div class="watch-item"><span>${String(i+1).padStart(2,'0')}</span><div>${x}</div></div>`).join(''):'<div class="empty">Today's Watch 等待更新。</div>';
}
function renderBriefing(b){
  const rec=b.yesterday_top||[], today=b.today_top||[];
  $('#yesterdayTop').innerHTML=rec.length?rec.slice(0,3).map((x,i)=>`<div class="brief-item"><span>${i+1}</span><div>${x}</div></div>`).join(''):'<div class="empty">昨日摘要等待更新。</div>';
  $('#todayTop').innerHTML=today.length?today.slice(0,3).map((x,i)=>`<div class="brief-item"><span>${i+1}</span><div>${x}</div></div>`).join(''):'<div class="empty">今日焦點等待更新。</div>';
}
function renderStocks(s){ $('#stockUpdated').textContent=s.as_of?`更新：${new Date(s.as_of).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})}`:''; $('#stockGrid').innerHTML=(s.stocks||[]).map(q=>`<article class="stock-card"><div class="stock-top"><div><div class="ticker">${q.label||q.symbol}</div><div class="stock-price">${fmt(q.price,q.decimals??2)}</div></div><div class="stock-change ${cls(q.change_pct)}">${pct(q.change_pct)}</div></div><canvas class="spark" data-spark='${JSON.stringify(q.spark||[])}' data-pos="${Number(q.change_pct)>=0}"></canvas></article>`).join('') || '<div class="empty">自選股資料尚未更新。</div>'; }
function renderNews(n){ $('#news').innerHTML=(n.items||[]).slice(0,12).map(x=>`<div class="news-item"><span class="news-dot"></span><div class="news-title"><a href="${x.url}" target="_blank" rel="noopener">${x.title}</a></div><div class="news-meta">${x.source||''}${x.time?' · '+x.time:''}</div></div>`).join('') || '<div class="empty">新聞尚未更新。</div>'; }
function renderCalendar(c){ $('#calendar').innerHTML=(c.items||[]).slice(0,12).map(x=>`<div class="cal-item"><div class="cal-time">${x.time||'—'}</div><div class="cal-text">${x.title}<span class="importance">${'●'.repeat(Math.min(3,Number(x.importance)||1))}</span><br><span class="muted">${x.country||''}${x.actual?` · Actual ${x.actual}`:''}${x.forecast?` · Forecast ${x.forecast}`:''}</span></div></div>`).join('') || '<div class="empty">今日無高重要性事件，或資料源暫時不可用。</div>'; }
function renderBrief(b){ $('#aiBadge').textContent=b.mode==='openai'?'AI':'Rules'; $('#aiView').innerHTML=`<div class="lead">${b.headline||'市場摘要等待更新'}</div>${(b.bullets||[]).length?`<ul>${b.bullets.map(x=>`<li>${x}</li>`).join('')}</ul>`:''}`; const score=Math.max(0,Math.min(100,Number(b.risk_score??50))); $('#riskMeter').innerHTML=`<div class="gauge"><div class="gauge-bar"><span class="gauge-dot" style="left:${score}%"></span></div><div class="gauge-labels"><span>Risk-off</span><span>Neutral</span><span>Risk-on</span></div><div class="risk-text">${b.risk_label||'中性'} · ${score}/100</div></div>`; }
function repaint(){document.querySelectorAll('[data-spark]').forEach(c=>{try{drawSpark(c,JSON.parse(c.dataset.spark||'[]'),c.dataset.pos==='true')}catch{}})}
async function load(){
  $('#refreshBtn').disabled=true; renderSessions();
  try{ const [m,r,s,n,c,b]=await Promise.all([getJSON('data/market.json'),getJSON('data/rates.json'),getJSON('data/stocks.json'),getJSON('data/news.json'),getJSON('data/calendar.json'),getJSON('data/brief.json')]); renderMarket(m);renderRates(r);renderPulse(m,r);renderSignals(m,r,b);renderWatch(b);renderBriefing(b);renderStocks(s);renderNews(n);renderCalendar(c);renderNextEvent(c);renderBrief(b); requestAnimationFrame(repaint); }
  catch(e){console.error(e); $('#heroIndices').innerHTML='<article class="panel"><b>資料載入失敗</b><p class="muted">請先執行 GitHub Action「Update market data」，或檢查 data/*.json 是否存在。</p></article>';}
  finally{$('#refreshBtn').disabled=false}
}
$('#refreshBtn').addEventListener('click',load); window.addEventListener('resize',()=>requestAnimationFrame(repaint)); setInterval(()=>{renderSessions();},60000); load();
