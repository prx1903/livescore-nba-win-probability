/* ---------- maç listesi: satırlar bir kez kurulur, sonra yerinde güncellenir ----------
   (her karede yeniden kurulsaydı, akış oynarken satıra tıklamak çalışmazdı) */
const ROW=[];
function makeRow(i){
  const g=G[i], b=document.createElement('button');
  b.className='mrow'; b.type='button';
  b.innerHTML=`<div class="when"></div>
    <div><div class="tm ta"><span>${g.away}</span><span class="sa"></span></div>
         <div class="tm th"><span>${g.home}</span><span class="sh"></span></div></div>
    <div class="pr"><span class="num pp"></span><br><span class="pf"></span></div>
    <div class="minibar"><i class="aa"></i><i class="hh"></i></div>
    <div class="rowwarn" hidden></div>${g.syn?'<div class="syntag">üretilmiş maç, gerçek değil</div>':''}`;
  b.addEventListener('pointerdown',()=>{sel=i;markSel();drawMatch()});
  const q=c=>b.querySelector(c);
  ROW[i]={b,when:q('.when'),ta:q('.ta'),th:q('.th'),sa:q('.sa'),sh:q('.sh'),
          pp:q('.pp'),pf:q('.pf'),aa:q('.aa'),hh:q('.hh'),warn:q('.rowwarn')};
  return b;
}
G.forEach((g,i)=>makeRow(i));
function updateRow(i){
  const g=G[i], st=ST[i], r=ROW[i], pre=st.s==='pre', ph=pct(st.p);
  r.when.innerHTML=pre?hhmm(g.tip)
    :st.s==='live'?`<span class="live"><span class="dot"></span>P${st.pe}</span><br>${mmss(st.rem)}`:'Bitti';
  r.sa.textContent=pre?'':st.a; r.sh.textContent=pre?'':st.h;
  r.ta.className='tm ta'+(st.a>st.h?' lead':'')+(pre?' dim':'');
  r.th.className='tm th'+(st.h>st.a?' lead':'')+(pre?' dim':'');
  r.pp.textContent='%'+(ph>=50?ph:100-ph); r.pf.textContent=ph>=50?g.home:g.away;
  r.aa.style.width=(100-ph)+'%'; r.hh.style.width=ph+'%';
  const fs=feedState(i);
  r.warn.hidden=!(st.s==='live'&&(fs.s==='warn'||fs.s==='bad')); r.warn.textContent=fs.s==='bad'?'veri bayat':'veri uyarısı';
}
let sig='';
/* Rows in the order they are shown: groups live, not started, finished; inside a group by game index.
   The list, the filter buttons and the arrow keys all use this one order. */
function listOrder(states,f){
  const by={live:[],pre:[],final:[]};
  states.forEach((s,i)=>by[s.s].push(i));
  return [['Canlı','live'],['Başlamadı','pre'],['Bitti','final']]
    .filter(([,k])=>by[k].length&&(f==='all'||f===k)).map(([lab,k])=>({lab,k,ix:by[k]}));
}
function layoutList(){
  const gs=listOrder(ST,filt);
  const nsig=gs.map(g=>g.lab+g.ix.join(',')).join('|');
  if(nsig===sig)return;
  sig=nsig;
  const L=el('list'); L.textContent='';
  gs.forEach(g=>{
    const h=document.createElement('div'); h.className='glab';
    h.innerHTML=`${g.lab} <span style="color:var(--muted);font-weight:400">${g.ix.length}</span>`;
    L.appendChild(h); g.ix.forEach(i=>L.appendChild(ROW[i].b));
  });
  markSel();
}
function markSel(){ROW.forEach((r,i)=>r.b.setAttribute('aria-current',i===sel))}
function drawListCounts(){
  const c={live:0,pre:0,final:0}; ST.forEach(s=>c[s.s]++);
  el('cnt').textContent=`${G.length} maç`;
  el('filters').querySelectorAll('button').forEach(b=>{
    b.setAttribute('aria-pressed',b.dataset.f===filt);
    if(b.dataset.f!=='all')b.textContent=({live:'Canlı',final:'Bitti',pre:'Başlamadı'})[b.dataset.f]+' '+c[b.dataset.f];
  });
}

