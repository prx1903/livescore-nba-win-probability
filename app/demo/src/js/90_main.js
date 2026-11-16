/* ---------- çizim ---------- */
function drawMatch(){syncFeed();const g=G[sel],st=ST[sel];drawHero(g,st);drawCurve(g,st);drawRest(g,st);updateData();drawHome(g);drawWhatIf(g,st)}
function draw(){
  syncFeed(); rebuild(); layoutList();
  for(let i=0;i<G.length;i++)updateRow(i);
  drawListCounts();
  el('clock').textContent=hhmm(T);
  el('scrub').value=T;
  drawMatch();
}

/* ---------- oynatma ---------- */
function frame(ts){
  if(playing){
    const dt=lastFrame?(ts-lastFrame)/1000:0; lastFrame=ts;
    T=Math.min(DAY.dayEnd,T+dt*speed);
    if(T>=DAY.dayEnd)setPlay(false);
    if(ts-lastDraw>100){lastDraw=ts;draw()}
    else animCourt();                                /* saha her karede akar */
  }
  requestAnimationFrame(frame);
}
function setPlay(on){playing=on;lastFrame=on?performance.now():0;  /* ilk kare kaybolmasin diye */
  el('play').textContent=on?'❚❚':'▶';el('play').title=on?'Duraklat':'Oynat'}
el('play').onclick=()=>setPlay(!playing);
el('feedMode').onchange=e=>{feedMode=e.target.value;syncFeed();draw()};
el('speed').onchange=e=>{speed=+e.target.value};
el('scrub').min=DAY.dayStart; el('scrub').max=DAY.dayEnd; el('scrub').step=30;
el('scrub').oninput=e=>{T=+e.target.value;draw()};

/* ---------- görünüm ve tema ---------- */
function view(v){
  el('viewMatches').classList.toggle('hidden',v==='model');
  el('viewModel').classList.toggle('hidden',v!=='model');
  el('navM').setAttribute('aria-current',v==='model'?'false':'page');
  el('navD').setAttribute('aria-current',v==='model'?'page':'false');
  window.scrollTo(0,0);
}
el('navM').onclick=()=>view('matches'); el('navD').onclick=()=>view('model');
el('theme').onclick=()=>{const r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'};
el('filters').onclick=e=>{const b=e.target.closest('button');if(!b)return;filt=b.dataset.f;sig='';
  const vis=listOrder(ST,filt).flatMap(g=>g.ix);
  if(!vis.includes(sel)&&vis.length)sel=vis[0];
  draw()};
document.addEventListener('keydown',e=>{
  if(e.code==='Space'&&e.target.tagName!=='SELECT'&&e.target.tagName!=='INPUT'){e.preventDefault();setPlay(!playing)}
  if((e.code==='ArrowDown'||e.code==='ArrowUp')&&e.target.tagName!=='SELECT'&&e.target.tagName!=='INPUT'){e.preventDefault();
    const vis=listOrder(ST,filt).flatMap(g=>g.ix);
    const at=vis.indexOf(sel); if(at>=0){sel=vis[(at+(e.code==='ArrowDown'?1:vis.length-1))%vis.length];markSel();drawMatch()}}
});
rebuild(); sel=ST.findIndex(s=>s.s==='live'); if(sel<0)sel=0;
buildData(); drawCal(); drawTime(); drawAccText(); draw(); requestAnimationFrame(frame);
