// V1.4.6d reliability patch
// The data pipeline is producing the new calendar correctly. This file makes sure
// the browser always renders that data after all older UI patches have loaded.
renderCalendar=function(c){
  const badge=$('#calendarSourceBadge'), note=$('#calendarCostNote');
  if(badge) badge.textContent='Global · Official + Multi-source';
  if(note) note.textContent=(c.source?`來源：${c.source}。 `:'')+(c.cost_note||'');

  const rows=(c.items||[]).slice(0,24);
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dayLabel=d=>{
    if(!d) return '';
    if(d===today) return '今天';
    const p=d.split('-');
    return p.length===3?`${Number(p[1])}/${Number(p[2])}`:d;
  };
  const imp=x=>{const n=Math.max(1,Math.min(3,Number(x)||1));return `<span class="cal-importance imp-${n}" aria-label="重要度 ${n}">${'●'.repeat(n)}${'○'.repeat(3-n)}</span>`};
  const val=(label,v)=>`<span><em>${label}</em><b>${v==null||v===''?'—':esc(v)}</b></span>`;

  $('#calendar').innerHTML=rows.length?rows.map(x=>`<div class="cal-item cal-v146"><div class="cal-date"><b>${esc(dayLabel(x.date))}</b><span>${esc(x.time||'—')}</span></div><div class="cal-text"><div class="cal-title-line"><span class="cal-flag">${esc(x.flag||'🌐')}</span><b>${esc(x.title||'')}</b>${imp(x.importance)}</div><div class="cal-country">${esc(x.country||'')} · ${esc(x.source||'')}</div><div class="cal-values">${val('前值',x.previous)}${val('預估',x.forecast)}${val('實際',x.actual)}</div></div></div>`).join(''):'<div class="empty">近期財經行事曆暫時無法取得；不使用假資料填補。</div>';

  const now=new Date();
  const events=rows.map(x=>{
    if(!x.date) return null;
    let hh=9,mm=0,unknown=true;
    const m=String(x.time||'').match(/^(\d{1,2}):(\d{2})$/);
    if(m){hh=Number(m[1]);mm=Number(m[2]);unknown=false;}
    const [y,mo,d]=x.date.split('-').map(Number);
    const when=new Date(Date.UTC(y,mo-1,d,hh-8,mm));
    return {...x,when,unknown};
  }).filter(Boolean).filter(x=>x.when.getTime()>=now.getTime()-30*60000).sort((a,b)=>a.when-b.when);
  const e=events[0];
  if(e){
    const mins=Math.max(0,Math.round((e.when-now)/60000));
    const countdown=mins<1440?`T-${Math.floor(mins/60)}h ${mins%60}m`:`T-${Math.floor(mins/1440)}d`;
    $('#nextEvent').innerHTML=`<div><span class="event-time">${esc(dayLabel(e.date))} ${esc(e.time||'—')}</span><b>${esc((e.flag||'')+' '+e.title)}</b><small>${esc(e.source||e.country||'')}</small></div><strong>${e.unknown?'Upcoming':countdown}</strong>`;
  }else{
    $('#nextEvent').innerHTML='<span class="event-empty">近期暫無後續高重要性事件</span>';
  }
};

// Guarantee that the block labelled "今日 3 件事" always has three visible rows.
// Real same-day events/news are shown first; missing rows are explicitly marked as
// unconfirmed instead of borrowing future calendar events.
const _renderBrief146d=renderBrief;
renderBrief=function(b){
  _renderBrief146d(b);
  const el=$('#todayTop');
  if(!el) return;
  const real=(b.today_top||[]).slice(0,3);
  const rows=[...real];
  while(rows.length<3){
    rows.push(`今日暫無第 ${rows.length+1} 項已確認的重要事件；不以未來事件補位。`);
  }
  el.innerHTML=rows.map((x,i)=>`<div class="brief-item"><span>${i+1}</span><div>${esc(x)}</div></div>`).join('');
};

// v146.js starts a load before this final patch is evaluated. Run one final load
// after the overrides above so the page cannot remain on the previous renderer.
setTimeout(()=>{ if(typeof load==='function') load(); },0);
