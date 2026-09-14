// V1.4.3 UI overrides
renderRates=function(r){
  const core=(r.rates||[]).filter(x=>['DGS2','DGS5','DGS10','DGS30'].includes(x.series));
  $('#rates').innerHTML=core.length?core.map(x=>`<div class="rate-card"><span>${esc((x.name||'').replace('美債 ',''))}</span><b>${x.value==null?'—':fmt(x.value,3)+'%'}</b><small class="${cls(x.change_bps)}">${x.change_bps==null?'—':sign(x.change_bps)+fmt(x.change_bps,1)+' bps'}</small></div>`).join(''):'<div class="empty">美債資料暫時無法取得。</div>';
};

renderCalendar=function(c){
  const badge=$('#calendarSourceBadge'),note=$('#calendarCostNote');
  if(badge) badge.textContent='Official · 14D';
  if(note) note.textContent=(c.source?`來源：${c.source}。 `:'')+(c.cost_note||'');
  const rows=(c.items||[]).slice(0,14);
  $('#calendar').innerHTML=rows.length?rows.map(x=>`<div class="cal-item"><div class="cal-date"><b>${esc((x.date||'').slice(5).replace('-','/'))}</b><span>${esc(x.time||'—')}</span></div><div class="cal-text"><b>${esc(x.title)}</b><br><span class="muted">${esc(x.country||'')} · ${esc(x.source||'Official')}</span></div></div>`).join(''):'<div class="empty">近期官方行事曆暫時無法取得。</div>';
  const now=new Date();
  const e=rows.map(x=>{const d=new Date(`${x.date}T${x.time||'00:00'}:00+08:00`);return{...x,ms:d-now}}).filter(x=>Number.isFinite(x.ms)&&x.ms>=0).sort((a,b)=>a.ms-b.ms)[0];
  if(e){const mins=Math.floor(e.ms/60000),days=Math.floor(mins/1440),hrs=Math.floor((mins%1440)/60);$('#nextEvent').innerHTML=`<div><span class="event-time">${esc((e.date||'').slice(5).replace('-','/'))}<br>${esc(e.time||'')}</span><b>${esc(e.title)}</b><small>${esc(e.source||e.country||'')}</small></div><strong>${days>0?`T-${days}d ${hrs}h`:`T-${hrs}h ${mins%60}m`}</strong>`}else $('#nextEvent').innerHTML='<span class="event-empty">等待下一個官方事件</span>';
};

renderNews=function(n){
  NEWS_DATA=n.items||[];
  const order=['美股','半導體','軟體 / AI','央行 / 利率','能源','歐洲','中國','地產','台灣'];
  const map=new Map(NEWS_DATA.map(x=>[x.category,x]));
  $('#news').innerHTML=order.map(cat=>{const x=map.get(cat);if(!x)return `<article class="news-summary-card"><div class="news-theme">${esc(cat)}</div><p class="muted">等待此主題最新財經消息</p></article>`;const text=x.summary&&x.summary.length>20?x.summary:x.title;return `<article class="news-summary-card"><div class="news-theme">${esc(cat)}</div><a href="${safeUrl(x.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(x.title)}</b></a><p>${esc(text)}</p><small>${esc(x.source||'')}</small></article>`}).join('');
};

load();
