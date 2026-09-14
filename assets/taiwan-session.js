// Taiwan market session presentation layer.
// Keeps the last complete TWSE close before the cash market opens, and labels
// Taiwan index futures as day/night live or the most recent session close.

function taiwanNowParts(){
  const parts=new Intl.DateTimeFormat('en-CA',{
    timeZone:'Asia/Taipei',weekday:'short',year:'numeric',month:'2-digit',day:'2-digit',
    hour:'2-digit',minute:'2-digit',hour12:false
  }).formatToParts(new Date());
  const get=t=>parts.find(x=>x.type===t)?.value;
  return {
    weekday:get('weekday'),
    date:`${get('year')}-${get('month')}-${get('day')}`,
    mins:Number(get('hour'))*60+Number(get('minute'))
  };
}

function taiwanCashState(dataDate){
  const t=taiwanNowParts();
  const weekday=['Mon','Tue','Wed','Thu','Fri'].includes(t.weekday);
  const live=weekday&&t.mins>=540&&t.mins<810; // 09:00–13:30
  const afterClose=weekday&&t.mins>=810;
  const isToday=dataDate===t.date;

  if(live&&isToday) return {label:'盤中',detail:'今日盤中'};
  if(live&&!isToday) return {label:'前一交易日收盤',detail:'前一交易日收盤 · 等待今日盤中資料'};
  if(afterClose&&isToday) return {label:'今日收盤',detail:'今日收盤'};
  return {label:'前一交易日收盤',detail:'前一交易日收盤'};
}

function txSessionInfo(){
  const t=taiwanNowParts();
  const weekday=['Mon','Tue','Wed','Thu','Fri'].includes(t.weekday);
  const earlyNight=['Tue','Wed','Thu','Fri','Sat'].includes(t.weekday)&&t.mins<300;
  const day=weekday&&t.mins>=525&&t.mins<825; // 08:45–13:45
  const dayClosed=weekday&&t.mins>=825&&t.mins<900; // 13:45–15:00
  const night=(weekday&&t.mins>=900)||earlyNight; // 15:00–05:00

  if(day) return {label:'日盤',state:'open',detail:'日盤即時 · 08:45–13:45'};
  if(dayClosed) return {label:'日盤收盤',state:'closed',detail:'日盤收盤'};
  if(night) return {label:'夜盤',state:'open',detail:'夜盤即時 · 15:00–05:00'};
  return {label:'夜盤收盤',state:'closed',detail:'最近夜盤收盤'};
}

renderTaiwanFutures=function(q){
  const box=$('#taiwanFuturesQuote'),badge=$('#txSessionBadge');
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
};

const _renderMarketTaiwanSession=renderMarket;
renderMarket=function(m){
  _renderMarketTaiwanSession(m);
  const s=m?.taiwan_stats||{};
  const idx=(m?.taiwan||[]).find(x=>x.symbol==='^TWII')||(m?.taiwan||[])[0];
  const dataDate=idx?.quote_date||s.date||'';
  const state=taiwanCashState(dataDate);

  const indexMeta=document.querySelector('#taiwanMarkets .tw-index-row small');
  if(indexMeta) indexMeta.textContent=`${state.detail} · ${dataDate||'—'} · TWSE 官方`;

  const turnoverMeta=document.querySelector('#taiwanMarkets .tw-stat.turnover small');
  if(turnoverMeta) turnoverMeta.textContent=`${state.detail} · ${dataDate||'—'} · TWSE 官方`;

  const volumeMeta=document.querySelector('#taiwanMarkets .tw-stat.volume small');
  if(volumeMeta) volumeMeta.textContent=`${state.detail} · 成交股數 · TWSE 官方`;

  const breadthMeta=document.querySelector('#taiwanMarkets .tw-stat.breadth small');
  if(breadthMeta) breadthMeta.textContent=`${state.detail} · 方向佔比不含持平股票`;
};
