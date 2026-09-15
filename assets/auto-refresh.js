// Periodically reload dashboard JSON so an already-open iPhone/Safari page follows market updates.
(function(){
  let running=false;
  function taipeiParts(){
    const p=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
    const get=t=>p.find(x=>x.type===t)?.value;
    return {weekday:get('weekday'),mins:Number(get('hour'))*60+Number(get('minute'))};
  }
  function cashOpen(){
    const t=taipeiParts();
    return ['Mon','Tue','Wed','Thu','Fri'].includes(t.weekday)&&t.mins>=540&&t.mins<810;
  }
  async function refresh(){
    if(running||document.hidden||typeof load!=='function') return;
    running=true;
    try{await load();}catch(e){console.warn('auto refresh failed',e)}finally{running=false}
  }
  // Backend refreshes about every 5 minutes during Taiwan cash hours. Poll a bit faster
  // so the browser notices the newest committed JSON without requiring a manual reload.
  setInterval(()=>{ if(cashOpen()) refresh(); },120000);
  setInterval(()=>{ if(!cashOpen()) refresh(); },600000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden) refresh()});
})();
