/* ---------- skor dağılımı, "şu an neden", güç skalası ----------
   All three read the score-distribution model (ScoreModel) for the state after the last event that arrived,
   the same state as the probability at the top of the match screen. */
function modelState(g,st){
  const e=st.k?g.ev[st.k-1]:null;
  return ScoreModel.state(e?e[0]:0,e?e[4]:1,st.h,st.a,g.mu,g.mt,null,null);
}
/* Probability that the margin (home - away) at the end of regulation, or of the overtime being played, falls in
   each range: away by 11+, 6-10, 1-5, tie, home by 1-5, 6-10, 11+. The seven values add up to 1. */
function distCells(sm){
  const z=x=>ScoreModel.Phi((x-sm.mu)/sm.sd), cut=[-10.5,-5.5,-sm.band,sm.band,5.5,10.5].map(z), e=[0,...cut,1];
  return e.slice(1).map((v,i)=>Math.max(0,v-e[i]));
}
function drawDist(g,st){
  if(st.s==='final'){
    el('dist').innerHTML=`<p class="note" style="margin-top:14px">Maç bitti. Sonuç: ${g.away} ${st.a} – ${st.h} ${g.home}, fark ${Math.abs(st.h-st.a)} sayı${st.pe>4?', uzatmada':''}.</p>`;
    return;
  }
  const sm=modelState(g,st), c=distCells(sm), ot=sm.ot;
  const lab=[g.away+' 11+',g.away+' 6–10',g.away+' 1–5',ot?'berabere: yeni uzatma':'berabere: uzatma',g.home+' 1–5',g.home+' 6–10',g.home+' 11+'];
  const col=i=>i<3?'var(--away)':i>3?'var(--home)':'var(--muted)';
  el('dist').innerHTML=`<div class="dist" role="table" aria-label="Fark aralıklarının olasılığı">`
    +c.map((p,i)=>`<div role="cell"><i style="height:${(p*100).toFixed(1)}%;background:${col(i)}"></i><div class="p">${pcs(p,false)}</div><div class="l">${lab[i]}</div></div>`).join('')
    +`</div><p class="note">${ot?'Bu uzatmanın':'Normal sürenin'} sonunda farkın hangi aralıkta olacağı (sayı farkıyla önde biten takım). `
    +(ot?'':`Uzatma olasılığı ${pc1(sm.pot)}. `)
    +`Beklenen maç sonu skoru (uzatma dahil): ${g.away} ${Math.round(sm.exp_a)} – ${Math.round(sm.exp_h)} ${g.home}. Bunlar tahmindir, kesin sonuç değildir.</p>`;
}
function drawWhy(g,st){
  if(st.s==='final'){el('why').innerHTML='<p class="note" style="margin-top:14px">Maç bitti; sonuç belli olduğu için açıklanacak bir tahmin yok.</p>';return}
  const sm=modelState(g,st), P=sm.parts, row=(k,v)=>`<tr><td>${k}</td><td>${v}</td></tr>`;
  let rows=row('Şu anki skor farkı',side(g,P.now));
  if(sm.ot)rows+=row('Kalan uzatma süresinde beklenen (takım gücü ve ev sahipliği)',side(g,P.line));
  else{
    const hv=DAY.home.b[1]*g.H*sm.s;           /* home-advantage share of the pre-game expectation, as in the panel below */
    rows+=row('Kalan sürede takım gücünden beklenen',side(g,P.line-hv))+row('Kalan sürede ev sahibi avantajından beklenen',side(g,hv))
      +row('Farkın erimesi (öndeki takım farkın bir kısmını genelde geri verir)',side(g,P.shrink));
  }
  rows+=`<tr><td><b>${sm.ot?'Uzatma':'Normal süre'} sonunda beklenen fark</b></td><td><b>${side(g,sm.mu)}</b></td></tr>`;
  el('why').innerHTML=`<table class="t" style="margin-top:8px"><tbody>${rows}</tbody></table>`
    +`<p class="note">Beklenen fark kesin değildir: gerçek fark bundan tipik olarak ${sm.sd.toFixed(1).replace('.',',')} sayı kadar sapar. `
    +`Beklenen fark bu sapmaya göre ne kadar büyükse olasılık o kadar uca yaklaşır; süre azaldıkça sapma küçülür. `
    +`Sonuç: ${g.away} ${pcsA(st.p,false)}, ${g.home} ${pcs(st.p,false)}. Ev sahibi payı bir tahmindir (aşağıdaki "Ev sahibi avantajı" bölümü).</p>`;
}
/* Strength scale: the pre-game line on an axis from "away favoured by 20" to "home favoured by 20". */
function drawScale(g){
  const key=g.id+(isDark()?'d':'l'); if(el('scale').dataset.k===key)return; el('scale').dataset.k=key;
  const W=640,H=64,L=40,R=40,X=v=>L+(W-L-R)*(Math.max(-20,Math.min(20,v))+20)/40, y=26;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Güç skalası: maç öncesi çizgi">`
    +`<line x1="${X(-20)}" x2="${X(0)}" y1="${y}" y2="${y}" stroke="var(--away)" stroke-width="6" stroke-linecap="round"/>`
    +`<line x1="${X(0)}" x2="${X(20)}" y1="${y}" y2="${y}" stroke="var(--home)" stroke-width="6" stroke-linecap="round"/>`;
  [-20,-10,0,10,20].forEach(v=>{s+=`<line x1="${X(v)}" x2="${X(v)}" y1="${y-8}" y2="${y+8}" stroke="var(--axis)"/>`
    +`<text x="${X(v)}" y="${y+24}" text-anchor="middle" font-size="11" fill="var(--muted)">${v===0?'denk':(v<0?g.away:g.home)+' '+Math.abs(v)}</text>`});
  s+=`<circle cx="${X(g.sp)}" cy="${y}" r="8" fill="var(--ink)" stroke="var(--surface)" stroke-width="3"/></svg>`;
  el('scale').innerHTML=s;
  el('scaleTxt').textContent=`Skala, maç başlamadan önceki güç farkını sayı olarak gösterir: işaret bahis çizgisinde (${side(g,g.sp)}). `
    +`Çizgi takımların gücünü ve ev sahibi avantajını birlikte içerir; model bu maçta ${side(g,g.mu)} bekliyor.`;
}
