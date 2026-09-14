// V1.4.6e: iPhone/PWA cleanup, calendar note cleanup, Treasury curve spreads.
(function(){
  const oldCalendar = window.renderCalendar;
  if (typeof oldCalendar === 'function') {
    window.renderCalendar = function(c){
      const clone = {...(c||{})};
      clone.cost_note = String(clone.cost_note||'')
        .replace(/，?永豐期貨與工商時報交叉參考。?/g,'')
        .replace(/；\s*。/g,'。');
      oldCalendar(clone);
    };
  }

  window.renderRates = function(r){
    const all=(r&&r.rates)||[];
    const core=all.filter(x=>['DGS2','DGS5','DGS10','DGS30'].includes(x.series));
    const bySeries=Object.fromEntries(all.map(x=>[x.series,x]));
    const box=document.querySelector('#rates');
    if(!box) return;

    const cards=core.map(x=>`<div class="rate-item"><div><div class="rate-name">${esc(x.name)}</div><div class="rate-value">${x.value==null?'—':fmt(x.value,3)+'%'}</div></div><div class="rate-change ${cls(x.change_bps)}">${x.change_bps==null?'—':`${sign(x.change_bps)}${fmt(x.change_bps,1)} bps`}</div></div>`).join('');

    const r2=bySeries.DGS2, r10=bySeries.DGS10, r30=bySeries.DGS30;
    const spread=(longRate, shortRate)=>{
      if(!longRate || !shortRate || longRate.value==null || shortRate.value==null) return {value:null,change:null};
      const value=(Number(longRate.value)-Number(shortRate.value))*100;
      const change=(longRate.change_bps==null || shortRate.change_bps==null)?null:Number(longRate.change_bps)-Number(shortRate.change_bps);
      return {value,change};
    };
    const s210=bySeries['2S10S']?.value!=null ? {value:Number(bySeries['2S10S'].value),change:bySeries['2S10S'].change_bps} : spread(r10,r2);
    const s230=spread(r30,r2);
    const chip=(label,s)=>`<div class="spread-chip"><span>${label}</span><b>${s.value==null?'—':`${sign(s.value)}${fmt(s.value,1)} bps`}</b><small class="${cls(s.change)}">${s.change==null?'日變化 —':`日變化 ${sign(s.change)}${fmt(s.change,1)} bps`}</small></div>`;

    box.innerHTML = cards + `<div class="spread-strip">${chip('2Y10Y Spread',s210)}${chip('2Y30Y Spread',s230)}</div>`;
  };

  setTimeout(()=>{ if(typeof window.load==='function') window.load(); },0);
})();
