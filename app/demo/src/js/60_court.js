/* ---------- saha: pozisyon akisi ve son 10 sut ----------
   Konum: x 0-50 ft (yan cizgiden yan cizgiye), y potanin merkezinden ileri ft; hep hucum edilen potaya gore,
   bu yuzden top el degistirince yeni hucum orta sahadan girer. Topun yolu olaylardan kurulur: sut yerine pas
   noktalarindan gelir, potaya kavisle gider (yukseklik top buyuklugu ve golgeyle), ribaundda potadan sekip
   ribaundu alana gider; savunma ribaundu ve top kaybinda orta sahaya doner. Sut ve ribaund yerleri, saatleri
   ve takimlari veriden; pas noktalari ve sekme yonu yalnizca gorsel (olay sirasindan sabit secilir).
   Top her karede oyun saatine gore cizilir; sut isareti top potaya vardiginda belirir. */
const SHOTS_N=10;
const WP=[[25,26],[9,20],[41,20],[3,4],[47,4],[17,14],[33,14],[16,25],[34,25]];
const hr=(k,s)=>{const x=Math.sin(k*12.9898+s*78.233)*43758.5453;return x-Math.floor(x)};
function buildKf(g){
  const S=[], sh={}, se=[];
  (g.sh||[]).forEach(p=>sh[p[0]]=p);
  let pos=null, team=-1, live=false, tfree=0, tprev=-1, prevTot=0, lastEnd=-1e9, gap=0, lastKd=0;
  /* bolumler sirayla eklenir; bir bolum oncekinden once baslayacaksa ileri kaydirilir (top hic sicramasin) */
  const add=(t0,t1,x0,y0,x1,y1,k,tm,peak,hide)=>{
    if(t0<lastEnd){const d=lastEnd-t0;t0+=d;t1+=d}
    const s={t0,t1:Math.max(t1,t0+0.01),x0,y0,x1,y1,k,team:tm,peak:peak||0,hide:!!hide};
    S.push(s); lastEnd=s.t1; return s;
  };
  const nextT=k=>{for(let j=k+1;j<g.ev.length;j++)if(g.ev[j][8]>=1&&g.ev[j][8]<=5)return g.ev[j][0];return 1e9};
  const leave=()=>{if(live&&pos){add(tfree,tfree+0.8,pos.x,pos.y,pos.x,41.5,'x',team,0,1);tfree=lastEnd;gap=0.3}live=false;pos=null};
  const approach=(k,tm,tx,ty,te)=>{
    if(live&&pos&&team!==tm)leave();                     /* top el degistirdi ama olayi yok */
    let ts,x0,y0;
    if(!live||!pos){ts=Math.max(tfree+gap,te-20);x0=18+14*hr(k,1);y0=41.5}
    else{ts=Math.max(tfree,te-24);x0=pos.x;y0=pos.y}
    ts=Math.min(ts,te);
    const D=te-ts, pts=[[x0,y0]], n=D>16?3:(D>9?2:(D>4?1:0));
    for(let j=0;j<n;j++)pts.push(WP[Math.floor(hr(k,2+j)*WP.length)]);
    pts.push([tx,ty]);
    const step=D/(pts.length-1);
    for(let j=0;j<pts.length-1;j++)add(ts+j*step,ts+(j+1)*step,pts[j][0],pts[j][1],pts[j+1][0],pts[j+1][1],'m',tm);
    pos={x:tx,y:ty};team=tm;live=true;
  };
  g.ev.forEach((r,k)=>{
    const kd=r[8], tm=r[7], tot=r[2]+r[3], scored=tot>prevTot; prevTot=tot;
    let te=r[0];
    if(te<=tprev)te=tprev+((kd===2||lastKd===2)?0.9:0.35);   /* ayni saniyedeki olaylar arka arkaya */
    tprev=te; if(kd)lastKd=kd;
    if(kd===6){leave();pos={x:25,y:41.75};team=tm;live=tm>=0;tfree=te;gap=0;if(live)add(te,te,25,41.75,25,41.75,'m',tm);return}
    if(kd===7){if(live&&pos)add(Math.max(tfree,te),Math.max(tfree,te)+0.6,pos.x,pos.y,pos.x,pos.y,'x',team,0,1);
      live=false;pos=null;tfree=lastEnd;gap=0;return}
    if(kd===1&&sh[k]){
      const p=sh[k], x=p[1], y=Math.min(p[2],41);
      approach(k,tm,x,y,te);
      const d=Math.hypot(x-25,y), f=add(te,te+0.35+d/28,x,y,25,0.4,'f',tm,0.6+d/40); f.sh=p;
      se.push([f.t1,p]);
      if(p[4]){add(f.t1,f.t1+0.35,25,0.4,25,-0.8,'x',tm,0,1);live=false;team=1-tm;pos=null;tfree=lastEnd;gap=2.5}
      else{pos={x:25,y:0.4};tfree=f.t1}
      return;
    }
    if(kd===2&&tm>=0){
      if(live&&pos&&team!==tm)leave();
      const fromLine=!(live&&pos&&team===tm);
      add(Math.max(tfree,te-0.5),te,fromLine?25:pos.x,fromLine?13.75:pos.y,25,13.75,'m',tm);
      const f=add(te,te+0.3,25,13.75,25,0.4,'f',tm,0.5); f.ft=1; f.made=scored;
      if(scored){add(f.t1,f.t1+0.2,25,0.4,25,-0.8,'x',tm,0,1);live=false;team=1-tm;pos=null;tfree=lastEnd;gap=2.5}
      else{pos={x:25,y:0.4};team=tm;live=true;tfree=f.t1}
      return;
    }
    if((kd===3||kd===4)&&tm>=0){
      const th=(hr(k,5)-0.5)*2.6, rr=3+6*hr(k,6), x=25+rr*Math.sin(th), y=Math.max(0.5,1+rr*Math.cos(th));
      add(Math.max(tfree,te-0.8),te,pos?pos.x:25,pos?pos.y:0.4,x,y,'m',tm);
      if(kd===3){pos={x,y};team=tm;live=true;tfree=lastEnd}
      else{const tx=Math.min(te+2.4,Math.max(te+0.6,te+(nextT(k)-te)*0.45));
        add(te+0.15,tx,x,y,x+(25-x)*0.3,41.5,'x',tm,0,1);team=tm;live=false;pos=null;tfree=lastEnd;gap=0.3}
      return;
    }
    if(kd===5&&tm>=0){
      if(live&&pos&&team!==tm)leave();
      const w=WP[Math.floor(hr(k,7)*WP.length)];
      if(live&&pos)add(Math.max(tfree,te-1.5),te,pos.x,pos.y,w[0],w[1],'m',tm);
      else add(Math.max(tfree+gap,te-3),te,18+14*hr(k,1),41.5,w[0],w[1],'m',tm);
      const tx=Math.min(te+2,Math.max(te+0.5,te+(nextT(k)-te)*0.45));
      add(te+0.1,tx,w[0],w[1],w[0],41.5,'x',1-tm,0,1);
      team=1-tm;live=false;pos=null;tfree=lastEnd;gap=0.3;return;
    }
  });
  g._kf=S; g._se=se; g._fl=S.filter(s=>s.k==='f');
}
function ballAt(S,tau){
  let lo=0,hi=S.length-1,i=-1;
  while(lo<=hi){const m=(lo+hi)>>1; if(S[m].t0<=tau){i=m;lo=m+1}else hi=m-1}
  if(i<0)return null;
  const s=S[i];
  if(tau>=s.t1)return s.hide?null:{x:s.x1,y:s.y1,h:0,team:s.team,o:1};
  const u=(tau-s.t0)/(s.t1-s.t0);
  if(s.k==='f')return {x:s.x0+(s.x1-s.x0)*u,y:s.y0+(s.y1-s.y0)*u,h:4*u*(1-u)*s.peak,team:s.team,o:1,fl:1};
  const e=u*u*(3-2*u);
  return {x:s.x0+(s.x1-s.x0)*e,y:s.y0+(s.y1-s.y0)*e,h:0,team:s.team,o:s.k==='x'?1-u:1};
}
const teamCol=t=>t===1?'var(--home)':t===0?'var(--away)':'var(--muted)';
/* sut 3'luk mu: isabetlide kaynaktaki sayi, kacanda yer (23,75 ft yay, kosede 22 ft) */
const isThree=p=>{const d=Math.hypot(p[1]-25,p[2]);return p[4]?p[5]===3:(d>=23.6||(Math.abs(p[1]-25)>=21.9&&p[2]<=8.95))};
function shotFx(s,phase){
  const L=el('shotFx'), col=teamCol(s.team);
  if(phase==='start'){
    const mx=(s.x0+s.x1)/2, my=(s.y0+s.y1)/2-3.2*s.peak;
    const lab=s.ft?'serbest atış':(isThree(s.sh)?'şut · 3\'lük':'şut · 2\'lik');
    const ly=s.y0+3.7>41.5?s.y0-2.8:s.y0+3.7;
    L.innerHTML=`<path class="fx-arc" d="M${s.x0} ${s.y0} Q${mx.toFixed(2)} ${my.toFixed(2)} ${s.x1} ${s.y1}" stroke="${col}"/>`
      +`<circle class="fx-burst" cx="${s.x0}" cy="${s.y0}" r="1.3" stroke="${col}"/>`
      +`<text class="fx-lab" x="${s.x0}" y="${ly}" text-anchor="middle">${lab}</text>`;
  }else{
    const made=s.ft?s.made:s.sh[4]===1;
    L.insertAdjacentHTML('beforeend',`<circle class="fx-rim" cx="25" cy="0" r="1.2" stroke="${made?col:'var(--muted)'}"/>`
      +(s.ft?`<text class="fx-lab" x="25" y="-2.3" text-anchor="middle">${made?'+1':'kaçtı'}</text>`:''));
  }
  clearTimeout(L._t); L._t=setTimeout(()=>{L.textContent=''},1600);
}
/* bu karede (onceki kareden bu yana) baslayan / biten ucuslar; hizli oynatmada atlanan ucus da yakalanir */
function fxCheck(g,tau){
  const lt=g._lastTau; g._lastTau=tau;
  if(lt===undefined||tau<=lt||tau-lt>30||!g._fl)return;
  const F=g._fl; let lo=0,hi=F.length;
  while(lo<hi){const m=(lo+hi)>>1; if(F[m].t0<=lt)lo=m+1; else hi=m}
  let started=null; for(let i=lo;i<F.length&&F[i].t0<=tau;i++)started=F[i];
  if(started)shotFx(started,'start');
  let ended=null; for(let i=Math.max(0,lo-3);i<F.length&&F[i].t0<=tau;i++)if(F[i].t1>lt&&F[i].t1<=tau)ended=F[i];
  if(ended)shotFx(ended,'end');
}
function animCourt(){
  const g=G[sel], B=el('ball'), Sd=el('ballShadow'), Tr=el('ballTrail');
  const tau=T-g.tip, dur=g.ev[g.ev.length-1][0];
  const hide=()=>{B.style.display=Sd.style.display=Tr.style.display='none';el('ballHalo').style.opacity=0};
  if(!g.sh||tau<=0||tau>=dur)return hide();
  if(!g._kf)buildKf(g);
  fxCheck(g,tau);
  const b=ballAt(g._kf,tau);
  const Hl=el('ballHalo');
  if(!b||b.o<=0.02){Hl.style.opacity=0;return hide()}
  const col=teamCol(b.team), lift=1.6*b.h;
  B.style.display=Sd.style.display=Tr.style.display='';
  B.setAttribute('cx',b.x.toFixed(2)); B.setAttribute('cy',(b.y-lift).toFixed(2)); B.setAttribute('r',(0.95+0.75*b.h).toFixed(2));
  B.style.fill=col; B.style.opacity=b.o;
  Sd.setAttribute('cx',b.x.toFixed(2)); Sd.setAttribute('cy',(b.y+0.4).toFixed(2)); Sd.style.opacity=(0.3*b.o*(1-0.5*b.h)).toFixed(2);
  Hl.setAttribute('cx',b.x.toFixed(2)); Hl.setAttribute('cy',(b.y-lift).toFixed(2)); Hl.setAttribute('r',(2.1+0.9*b.h).toFixed(2));
  Hl.style.fill=col; Hl.style.opacity=b.fl?0.28:0;
  let pts='';
  for(let j=6;j>=0;j--){const q=ballAt(g._kf,tau-j*0.15); if(q&&q.o>0.05&&q.team===b.team)pts+=`${q.x.toFixed(2)},${(q.y-1.6*q.h).toFixed(2)} `}
  Tr.setAttribute('points',pts); Tr.style.stroke=col; Tr.style.opacity=(0.4*b.o).toFixed(2);
}
let courtSig='';
function drawCourt(g,st){
  const cap=el('courtCap'), G0=el('shots');
  if(!g.sh){if(courtSig!=='none'+sel){courtSig='none'+sel;G0.textContent='';cap.textContent='Bu maçta şut konumu yok.'}return}
  if(!g._kf)buildKf(g);
  const tau=st.s==='final'?1e9:st.s==='pre'?-1:T-g.tip;
  let lo=0,hi=g._se.length;                                /* potaya varmis sut sayisi */
  while(lo<hi){const m=(lo+hi)>>1; if(g._se[m][0]<=tau)lo=m+1; else hi=m}
  const sig=sel+':'+lo;
  animCourt();
  if(sig===courtSig)return;
  courtSig=sig;
  const vis=g._se.slice(Math.max(0,lo-SHOTS_N),lo).map(q=>q[1]);
  let s='';
  vis.forEach((p,i)=>{
    const newest=i===vis.length-1, op=(0.35+0.65*(i+1)/vis.length).toFixed(2);
    const col=teamCol(p[3]), e=g.ev[p[0]];
    const x=p[1], y=Math.min(p[2],41);
    const tip=`${perName(e[4])} ${e[5]} · ${p[3]?g.home:g.away} · ${p[4]?p[5]+' sayı':'kaçtı'}`;
    if(newest)s+=`<circle class="pulse" cx="${x}" cy="${y}" r="1.2" stroke="${col}"/>`;
    s+=p[4]?`<circle class="s-made" cx="${x}" cy="${y}" r="${newest?1.35:1.1}" fill="${col}" opacity="${op}"/>`
           :`<circle class="s-miss" cx="${x}" cy="${y}" r="${newest?1.15:0.95}" stroke="${col}" opacity="${op}"/>`;
    if(newest)s+=`<text class="lastlab" x="${x}" y="${y-2.1<-4.3?y+3.4:y-2.1}" text-anchor="middle">${p[4]?'+'+p[5]:'kaçtı'}</text>`;
    s+=`<circle class="hit" cx="${x}" cy="${y}" r="2.2"><title>${tip}</title></circle>`;
  });
  G0.innerHTML=s;
  cap.innerHTML=(lo
    ?`Son ${vis.length} şut. <span class="sw" style="background:var(--away)"></span>${g.away} `
     +`<span class="sw" style="background:var(--home)"></span>${g.home} · dolu: isabet, `
     +`<span class="sw o"></span>boş: kaçan. Serbest atışlar işaretlenmez.`
    :'Henüz şut yok.')
    +(g.syn?' Bu maçta şut yerleri de üretildi (eğitim sezonu 2022\'nin şut dağılımından).':' Top şut ve ribaund yerleri arasında akar; pas noktaları yalnızca görsel.');
}
