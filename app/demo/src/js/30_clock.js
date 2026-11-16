/* ---------- gün saati ---------- */
let T=DAY.startAt;
let playing=false, speed=20, sel=0, filt='all', lastFrame=0, lastDraw=0;

/* Bir macin gun saatindeki durumu.
   Gun saati ile oyun saati 1:1: 1x hizda ekrandaki sure saniyede bir saniye azalir.
   Oyun saati surekli akar, skor ise son gelen olaydan okunur.
   A finished game has a known result: p is 1 or 0 for the winner, not the model's value at the last event.
   Veride olaylar arasinda satir yok: olaylar ortalama 6, en fazla 30 oyun saniyesi arayla geliyor. */
function stateOf(g){
  const last=g.ev[g.ev.length-1], tot=last[0], e0=T-g.tip;
  if(e0<=0)return {s:'pre',p:g.pre,h:0,a:0,pe:1,rem:720,k:0,el:0};
  if(e0>=tot)return {s:'final',p:last[2]>last[3]?1:0,h:last[2],a:last[3],pe:last[4],rem:0,k:g.ev.length,el:tot};
  let lo=0,hi=g.ev.length-1,k=0;
  while(lo<=hi){const m=(lo+hi)>>1; if(g.ev[m][0]<=e0){k=m+1;lo=m+1}else hi=m-1}
  k=Math.max(1,k); const e=g.ev[k-1];
  let pe,rem;
  if(e0<=2880){pe=Math.min(4,Math.floor(e0/720)+1); rem=720-(e0-(pe-1)*720)}
  else{const o=Math.floor((e0-2880)/300)+1; pe=4+o; rem=300-((e0-2880)-(o-1)*300)}
  return {s:'live',p:e[1],h:e[2],a:e[3],pe,rem,k,el:e0};
}
let ST=G.map(()=>null);
const rebuild=()=>{for(let i=0;i<G.length;i++)ST[i]=stateOf(G[i])};

