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
function renderStocks(s){ $('#stockUpdated').textContent=s.as_of?`更新：${new Date(s.as_of).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})}`:''; $('#stockGrid').innerHTML=(s.stocks||[]).map(q=>`<article class="stock-card"><div class="stock-top"><div><div class="ticker">${q.label||q.symbol}</div><div class="stock-price">${fmt(q.price,q.decimals??2)}</div></div><div class="stock-change ${cls(q.change_pct)}">${pct(q.change_pct)}</div></div><canvas class="spark" data-spark='${JSON.stringify(q.spark||[])}' data-pos="${Number(q.change_pct)>=0}"></canvas></article>`).join('') || '<div class="empty">自選股資料尚未更新。</div>'; }
function renderNews(n){ $('#news').innerHTML=(n.items||[]).slice(0,12).map(x=>`<div class="news-item"><span class="news-dot"></span><div class="news-title"><a href="${x.url}" target="_blank" rel="noopener">${x.title}</a></div><div class="news-meta">${x.source||''}${x.time?' · '+x.time:''}</div></div>`).join('') || '<div class="empty">新聞尚未更新。</div>'; }
function renderCalendar(c){ $('#calendar').innerHTML=(c.items||[]).slice(0,12).map(x=>`<div class="cal-item"><div class="cal-time">${x.time||'—'}</div><div class="cal-text">${x.title}<span class="importance">${'●'.repeat(Math.min(3,Number(x.importance)||1))}</span><br><span class="muted">${x.country||''}${x.actual?` · Actual ${x.actual}`:''}${x.forecast?` · Forecast ${x.forecast}`:''}</span></div></div>`).join('') || '<div class="empty">今日無高重要性事件，或資料源暫時不可用。</div>'; }
function renderBrief(b){ $('#aiBadge').textContent=b.mode==='openai'?'AI':'Rules'; $('#aiView').innerHTML=`<div class="lead">${b.headline||'市場摘要等待更新'}</div>${(b.bullets||[]).length?`<ul>${b.bullets.map(x=>`<li>${x}</li>`).join('')}</ul>`:''}`; const score=Math.max(0,Math.min(100,Number(b.risk_score??50))); $('#riskMeter').innerHTML=`<div class="gauge"><div class="gauge-bar"><span class="gauge-dot" style="left:${score}%"></span></div><div class="gauge-labels"><span>Risk-off</span><span>Neutral</span><span>Risk-on</span></div><div class="risk-text">${b.risk_label||'中性'} · ${score}/100</div></div>`; }
function repaint(){document.querySelectorAll('[data-spark]').forEach(c=>{try{drawSpark(c,JSON.parse(c.dataset.spark||'[]'),c.dataset.pos==='true')}catch{}})}
async function load(){
  $('#refreshBtn').disabled=true;
  try{ const [m,r,s,n,c,b]=await Promise.all([getJSON('data/market.json'),getJSON('data/rates.json'),getJSON('data/stocks.json'),getJSON('data/news.json'),getJSON('data/calendar.json'),getJSON('data/brief.json')]); renderMarket(m);renderRates(r);renderPulse(m,r);renderStocks(s);renderNews(n);renderCalendar(c);renderBrief(b); requestAnimationFrame(repaint); }
  catch(e){console.error(e); $('#heroIndices').innerHTML='<article class="panel"><b>資料載入失敗</b><p class="muted">請先執行 GitHub Action「Update market data」，或檢查 data/*.json 是否存在。</p></article>';}
  finally{$('#refreshBtn').disabled=false}
}
$('#refreshBtn').addEventListener('click',load); window.addEventListener('resize',()=>requestAnimationFrame(repaint)); load();
