/* ---------- veri akışı kontrolleri ----------
   src/feed_checks.py ile aynı kurallar ve aynı uyarı metinleri. Her maçın olayları kontrolden geçer;
   akış testi (eksik olay / gecikme) maç ekranında seçili maça uygulanır ve o maç yalnızca ulaşan olaylardan çizilir.
   "Son veri": gün saatine göre son olayın ne kadar önce geldiği; 1x hızda gerçek saniyedir. */
const FEED={MAX_GAP:120,STALE:30,DELAY:40,DROP:0.3};
const isMiss=x=>x===null||x===undefined||(typeof x==='number'&&isNaN(x));
function f0(x){const r=Math.round(x),v=(Math.abs(x%1)===0.5&&r%2!==0)?r-1:r;return (v===0&&(x<0||Object.is(x,-0)))?'-0':String(v)}   // Python '.0f' gibi
function feedNew(){return {home:0,away:0,period:1,elapsed:0,nAcc:0,nRej:0,nWarn:0,lastSeq:null}}
function feedCheck(S,home,away,period,elapsed,secsLeft,seq){
  if([home,away,period,elapsed,secsLeft].some(isMiss)){S.nRej++;return {ok:false,w:['Olayda eksik alan var, atlandı.']}}
  home=Math.trunc(home);away=Math.trunc(away);period=Math.trunc(period);elapsed=+elapsed;
  const w=[];
  if(!isMiss(seq)){seq=Math.trunc(seq);
    if(S.lastSeq!==null&&seq<=S.lastSeq){S.nRej++;return {ok:false,w:['Olay tekrar etti ya da sırası bozuk (sıra '+S.lastSeq+' -> '+seq+'), atlandı.']}}
    if(S.lastSeq!==null&&seq>S.lastSeq+1)w.push((seq-S.lastSeq-1)+' olay eksik (sıra '+S.lastSeq+' -> '+seq+'); skor ve süre son gelen olaydan alındı.')}
  if(S.nAcc&&elapsed<S.elapsed-0.5){S.nRej++;return {ok:false,w:['Oyun saati geri gitti ('+f0(S.elapsed)+' -> '+f0(elapsed)+' sn), olay atlandı.']}}
  if(home<S.home||away<S.away){w.push('Skor geriledi ('+S.away+'-'+S.home+' -> '+away+'-'+home+'), önceki skor korundu.');home=Math.max(home,S.home);away=Math.max(away,S.away)}
  if(period>S.period+1)w.push('Periyot '+S.period+' -> '+period+' atladı, arada olay eksik olabilir.');
  if(S.nAcc&&elapsed-S.elapsed>FEED.MAX_GAP)w.push(f0(elapsed-S.elapsed)+' sn oyun süresince olay gelmedi, veri eksik olabilir.');
  S.home=home;S.away=away;S.period=period;S.elapsed=elapsed;S.nAcc++;
  if(!isMiss(seq))S.lastSeq=seq;S.nWarn+=w.length;
  return {ok:true,w,home,away}
}
function prng(seed){let a=seed|0;return()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
/* Bir maçı akış kontrolünden geçirir. mode: normal | drop (olayların ~%30'u ulaşmaz, son olay hep ulaşır)
   | delay (maçın ortasında akış 40 sn durur; o aralıktaki olaylar akış dönünce birlikte gelir).
   Dönüş: yalnızca kabul edilen olaylardan kurulmuş maç (şutlar yeni sıraya göre) ve olay başına kayıt. */
function feedGame(g,mode){
  const S=feedNew(),rnd=prng(7),ev=[],log=[],map=new Map(),n=g.ev.length,mid=g.ev[n>>1][0];let pend=[];
  g.ev.forEach((e,i)=>{
    if(mode==='drop'&&i<n-1&&rnd()<FEED.DROP)return;
    const r=feedCheck(S,e[2],e[3],e[4],e[0],0,i+1);
    if(!r.ok){pend.push(...r.w);return}
    let t=e[0]; if(mode==='delay'&&t>mid&&t<mid+FEED.DELAY)t=mid+FEED.DELAY;
    map.set(i,ev.length); ev.push([t,e[1],r.home,r.away,e[4],e[5],e[6],e[7],e[8]]);
    log.push({w:pend.concat(r.w),acc:S.nAcc,rej:S.nRej,warn:S.nWarn,miss:S.lastSeq-S.nAcc-S.nRej}); pend=[];
  });
  const out={};
  for(const k in g)if(k[0]!=='_')out[k]=g[k];                   /* önbellekler (_kf, _br ...) kopyalanmaz */
  out.ev=ev; out.sh=(g.sh||[]).filter(p=>map.has(p[0])).map(p=>[map.get(p[0])].concat(p.slice(1)));
  out.feed={mode,log,stall:mode==='delay'?[mid,mid+FEED.DELAY]:null};
  return out;
}
const ORIG=G.slice();
ORIG.forEach(g=>{g.feed=feedGame(g,'normal').feed});
let feedMode='normal', FT={i:-1,mode:'normal'};
/* test yalnızca seçili maça: seçim ya da test değişince eski maç geri konur */
function syncFeed(){
  if(FT.i===sel&&FT.mode===feedMode)return;
  if(FT.i>=0)G[FT.i]=ORIG[FT.i];
  FT={i:sel,mode:feedMode};
  if(feedMode!=='normal')G[sel]=feedGame(ORIG[sel],feedMode);
  ST[sel]=stateOf(G[sel]);
}
/* bir maçın şu anki akış durumu: ok | warn (son 120 oyun saniyesinde uyarı) | bad (veri bayat) */
function feedState(i){
  const g=G[i],st=ST[i],L=g.feed.log;
  if(st.s==='pre')return {s:'pre',k:0,L,items:[],age:null};
  const k=st.k,e0=Math.min(T-g.tip,g.ev[g.ev.length-1][0]);
  const age=st.s==='live'?e0-g.ev[k-1][0]:0, stale=st.s==='live'&&age>FEED.STALE;
  const items=[];let lastW=-1e9;
  for(let j=0;j<k;j++)if(L[j].w.length){lastW=g.ev[j][0];L[j].w.forEach(m=>items.push({e:g.ev[j],m}))}
  const sl=g.feed.stall;
  if(sl&&e0>=sl[1])items.push({e:g.ev[k-1],t:sl[1],m:'Veri akışı '+FEED.DELAY+' sn durdu ve yeniden başladı; bu sürede olasılık güncel olmayabilirdi.'});
  if(stale)items.push({e:g.ev[k-1],t:e0,m:f0(age)+' sn\'dir yeni veri gelmedi: gösterilen olasılık güncel olmayabilir.'});
  return {s:stale?'bad':(e0-lastW<=FEED.MAX_GAP?'warn':'ok'),k,L,items,age};
}
const FS_TXT={ok:'Akış normal',warn:'Veri uyarısı var',bad:'Veri bayat',pre:'Maç başlamadı'};

