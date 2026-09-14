// V1.4.6b calendar rendering patch
function renderCalendar(c){
  const badge=$('#calendarSourceBadge'),note=$('#calendarCostNote');
  if(badge) badge.textContent='Global · Multi-source';
  if(note) note.textContent=c.cost_note||c.source||'';
  const rows=c.items||[];
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dayLabel=d=>{
    if(!d) return '';
    if(d===today) return '今天';
    const p=d.split('-');
    return p.length===3?`${Number(p[1])}/${Number(p[2])}`:d;
  };
  $('#calendar').innerHTML=rows.slice(0,16).map(x=>`<div class="cal-item"><div class="cal-time"><small>${esc(dayLabel(x.date))}</small><br>${esc(x.time||'—')}</div><div class="cal-text"><b>${esc((x.flag||'')+' '+x.title)}</b><br><span class="muted">${esc(x.country||'')} · A ${esc(x.actual||'—')} / F ${esc(x.forecast||'—')} / P ${esc(x.previous||'—')}</span>${x.surprise!=null?`<span class="surprise ${cls(x.surprise)}">Δ ${sign(x.surprise)}${fmt(x.surprise,2)}</span>`:''}</div></div>`).join('')||(c.status==='ok'?'<div class="empty">近期無高重要性事件</div>':'<div class="empty">近期行事曆資料暫時不可用；系統不會用假資料填補。</div>');

  const now=new Date();
  const events=rows.map(x=>{
    if(!x.date) return null;
    let hh=9,mm=0,unknown=true;
    const m=String(x.time||'').match(/^(\d{1,2}):(\d{2})$/);
    if(m){hh=Number(m[1]);mm=Number(m[2]);unknown=false;}
    const [y,mo,d]=x.date.split('-').map(Number);
    // Taipei is UTC+8 year-round.
    const when=new Date(Date.UTC(y,mo-1,d,hh-8,mm));
    return {...x,when,unknown};
  }).filter(Boolean).filter(x=>x.when.getTime()>=now.getTime()-30*60000).sort((a,b)=>a.when-b.when);
  const e=events[0];
  if(e){
    const mins=Math.max(0,Math.round((e.when-now)/60000));
    const countdown=mins<1440?`T-${Math.floor(mins/60)}h ${mins%60}m`:`T-${Math.floor(mins/1440)}d`;
    $('#nextEvent').innerHTML=`<div><span class="event-time">${esc(dayLabel(e.date))} ${esc(e.time||'—')}</span><b>${esc((e.flag||'')+' '+e.title)}</b><small>${esc(e.country||'')}</small></div><strong>${e.unknown?'Upcoming':countdown}</strong>`;
  }else{
    $('#nextEvent').innerHTML='<span class="event-empty">近期暫無後續高重要性事件</span>';
  }
}
