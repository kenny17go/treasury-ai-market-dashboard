// V1.4.6a UI: multi-source economic calendar + Top 5 market news.
renderCalendar=function(c){
  const badge=$('#calendarSourceBadge'),note=$('#calendarCostNote');
  if(badge) badge.textContent='Multi-source · 14D';
  if(note) note.textContent=(c.source?`來源：${c.source}。 `:'')+(c.cost_note||'');
  const rows=(c.items||[]).slice(0,20);
  const imp=x=>{const n=Math.max(1,Math.min(3,Number(x)||1));return `<span class="cal-importance imp-${n}" aria-label="重要度 ${n}">${'●'.repeat(n)}${'○'.repeat(3-n)}</span>`};
  const val=(label,v)=>`<span><em>${label}</em><b>${v==null||v===''?'—':esc(v)}</b></span>`;
  $('#calendar').innerHTML=rows.length?rows.map(x=>`<div class="cal-item cal-v146"><div class="cal-date"><b>${esc((x.date||'').slice(5).replace('-','/'))}</b><span>${esc(x.time||'—')}</span></div><div class="cal-text"><div class="cal-title-line"><span class="cal-flag">${esc(x.flag||'🌐')}</span><b>${esc(x.title||'')}</b>${imp(x.importance)}</div><div class="cal-country">${esc(x.country||'')} · ${esc(x.source||'')}</div><div class="cal-values">${val('前值',x.previous)}${val('預估',x.forecast)}${val('實際',x.actual)}</div></div></div>`).join(''):'<div class="empty">近期財經行事曆暫時無法取得；不使用假資料填補。</div>';
  const now=new Date();
  const e=rows.map(x=>{if(!/^\d{2}:\d{2}$/.test(x.time||''))return null;const d=new Date(`${x.date}T${x.time}:00+08:00`);return{...x,ms:d-now}}).filter(x=>x&&Number.isFinite(x.ms)&&x.ms>=0).sort((a,b)=>a.ms-b.ms)[0];
  if(e){const mins=Math.floor(e.ms/60000),days=Math.floor(mins/1440),hrs=Math.floor((mins%1440)/60);$('#nextEvent').innerHTML=`<div><span class="event-time">${esc((e.date||'').slice(5).replace('-','/'))}<br>${esc(e.time||'')}</span><b>${esc(e.flag||'🌐')} ${esc(e.title||'')}</b><small>${esc(e.source||e.country||'')}</small></div><strong>${days>0?`T-${days}d ${hrs}h`:`T-${hrs}h ${mins%60}m`}</strong>`}else $('#nextEvent').innerHTML='<span class="event-empty">等待下一個重要事件</span>';
};

renderNews=function(n){
  NEWS_DATA=n.items||[];
  const rows=NEWS_DATA.slice(0,5);
  $('#news').innerHTML=rows.length?rows.map((x,i)=>{const paragraph=(x.summary&&x.summary.trim())||x.title;return `<article class="news-summary-card top-news-card"><div class="news-theme">重點 ${i+1}${x.topic?' · '+esc(x.topic):''}</div><a href="${safeUrl(x.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(x.title)}</b></a><p>${esc(paragraph)}</p><small>${esc(x.source||'財經新聞')} ${x.published?'· '+esc(x.published):''}</small></article>`}).join(''):'<div class="empty">目前沒有取得可用的重點市場新聞。</div>';
};

load();
