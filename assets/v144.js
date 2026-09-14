// V1.4.4 UI: Taiwan turnover/breadth + themed news fallback presentation.
const _renderMarketV144Base=renderMarket;
renderMarket=function(m){
  _renderMarketV144Base(m);
  const el=$('#taiwanMarkets'); if(!el)return;
  const idx=(m.taiwan||[]).find(x=>x.symbol==='^TWII') || (m.taiwan||[])[0];
  const s=m.taiwan_stats||{};
  const idxHtml=idx?`<div class="mini-market tw-index-row"><div><div class="label">台灣加權指數</div><div class="value">${fmt(idx.price)}</div></div><div class="delta ${cls(idx.change_pct)}">${pct(idx.change_pct)}</div></div>`:'';
  const turnover=s.turnover_100m_twd==null?'—':`${fmt(s.turnover_100m_twd,1)} 億`;
  const up=s.advance_pct==null?'—':`${fmt(s.advance_pct,1)}%`;
  const down=s.decline_pct==null?'—':`${fmt(s.decline_pct,1)}%`;
  const upCount=s.advance_count==null?'—':fmt(s.advance_count,0);
  const downCount=s.decline_count==null?'—':fmt(s.decline_count,0);
  const barUp=s.advance_pct==null?50:Math.max(0,Math.min(100,Number(s.advance_pct)));
  el.innerHTML=idxHtml+`<div class="twse-stats"><div class="tw-stat turnover"><span>加權市場成交值</span><b>${turnover}</b><small>${esc(s.date||'')} · TWSE</small></div><div class="tw-stat breadth"><span>上漲 vs 下跌個股</span><div class="breadth-values"><b class="up">${up}</b><em>${upCount} 檔</em><b class="down">${down}</b><em>${downCount} 檔</em></div><div class="breadth-bar"><i style="width:${barUp}%"></i></div><small>僅以上漲＋下跌股票計算方向佔比</small></div></div>`;
};

const _renderNewsV144Base=renderNews;
renderNews=function(n){
  NEWS_DATA=n.items||[];
  const order=['美股','半導體','軟體 / AI','央行 / 利率','能源','歐洲','中國','地產','台灣'];
  const map=new Map(NEWS_DATA.map(x=>[x.category,x]));
  $('#news').innerHTML=order.map(cat=>{const x=map.get(cat);if(!x)return `<article class="news-summary-card missing"><div class="news-theme">${esc(cat)}</div><p>此主題目前沒有取得可用新聞。</p></article>`;const paragraph=(x.summary&&x.summary.trim())||x.title;return `<article class="news-summary-card"><div class="news-theme">${esc(cat)}</div><a href="${safeUrl(x.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(x.title)}</b></a><p>${esc(paragraph)}</p><small>${esc(x.source||'財經新聞')} ${x.published?'· '+esc(x.published):''}</small></article>`}).join('');
};

load();
