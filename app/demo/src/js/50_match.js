/* ---------- maç başlığı ---------- */
function drawHero(g,st){
  const live=st.s==='live', pre=st.s==='pre', ph=pct(st.p);
  const chip=pre?`<span class="chip">${hhmm(g.tip)}'da başlıyor</span>`
    :live?`<span class="chip live"><span class="dot" style="margin:0"></span>Canlı</span><span>${perName(st.pe)}, ${mmss(st.rem)}</span>`
    :`<span class="chip">Bitti</span><span>${st.pe>4?(st.pe-4)+' uzatma':'normal süre'}</span>`;
  const fs=feedState(sel);
  el('st').innerHTML=(g.syn?'<span class="chip">üretilmiş maç</span>':'')+chip+(!live?''
    :fs.s==='bad'?'<span class="chip warn">veri bayat</span>':fs.s==='warn'?'<span class="chip warn">veri uyarısı</span>'
    :'<span class="chip ok">akış normal</span>');
  const sA=pre?'':`<span class="pts">${st.a}</span>`, sH=pre?'':`<span class="pts">${st.h}</span>`;
  el('sc').innerHTML=`
    <div class="team"><div class="badge" style="background:var(--away)">${g.away}</div>
      <div class="nm"><div class="ab">${NAME[g.away]||g.away}</div><div class="sub">deplasman</div></div>${sA}</div>
    <div class="dash">–</div>
    <div class="team h"><div class="badge" style="background:var(--home)">${g.home}</div>
      <div class="nm"><div class="ab">${NAME[g.home]||g.home}</div><div class="sub">ev sahibi</div></div>${sH}</div>`;
  el('barH').style.width=ph+'%'; el('barA').style.width=(100-ph)+'%';
  el('labA').innerHTML=`<span class="num">%${100-ph}</span>${g.away}`;
  el('labH').innerHTML=`${g.home}<span class="num" style="margin:0 0 0 6px">%${ph}</span>`;
  const pre0=pct(g.pre);
  const nm=t=>NAME[t]||t, fav0=pre0>=50?[g.home,pre0]:[g.away,100-pre0];
  el('tugTxt').textContent=pre
    ? `Maç başlamadan önce kazanma olasılığı: ${nm(g.away)} %${100-pre0}, ${nm(g.home)} %${pre0}. Bu sayılar yalnızca takımların gücünden ve ev sahipliğinden geliyor.`
    : st.s==='final'
    ? `Maç bitti: ${nm(st.h>st.a?g.home:g.away)} kazandı (${st.a}–${st.h}). Maç öncesi kazanma olasılığı: ${nm(g.away)} %${100-pre0}, ${nm(g.home)} %${pre0}.`
    : `Kazanma olasılığı: ${nm(g.away)} %${100-ph}, ${nm(g.home)} %${ph}. Maç başlamadan önce ${nm(fav0[0])} %${fav0[1]} ile favoriydi. Gösterilen değerler tahmindir, kesin sonuç değildir.`;
  if(g.syn)el('tugTxt').textContent+=` Bu maç gerçek değil: ${g.synNote}.`;
}

/* ---------- eğri ---------- */
function drawCurve(g,st){
  const W=1000,H=200,PL=74,PR=10,PT=14,PB=20;
  const n=st.k, step=Math.max(1,Math.ceil(n/170)), cur=[];
  for(let i=0;i<n;i+=step)cur.push(g.ev[i]);
  if(n&&cur[cur.length-1]!==g.ev[n-1])cur.push(g.ev[n-1]);
  const tot=g.ev[g.ev.length-1][0];
  const maxT=st.s==='pre'?2880:Math.max(2880,tot);
  const X=t=>PL+(W-PL-PR)*t/maxT, Y=p=>PT+(H-PT-PB)*(1-p);
  let s=`<svg class="curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="Kazanma olasılığının maç içindeki seyri">`;
  [0,.25,.5,.75,1].forEach(p=>{
    s+=`<line x1="${PL}" x2="${W-PR}" y1="${Y(p)}" y2="${Y(p)}" stroke="var(--grid)" stroke-width="1" vector-effect="non-scaling-stroke"/>`
      +`<text x="${PL-6}" y="${Y(p)+4}" text-anchor="end" font-size="13" fill="var(--muted)">${p===.5?'%50':(p>.5?g.home:g.away)+' %'+pct(Math.max(p,1-p))}</text>`;
  });
  const nper=maxT>2880?4+Math.ceil((maxT-2880)/300):4;
  let t0=0;
  for(let p=1;p<=nper;p++){
    const t1=Math.min(p<=4?p*720:2880+(p-4)*300,maxT);
    if(p>1)s+=`<line x1="${X(t0)}" x2="${X(t0)}" y1="${PT}" y2="${H-PB}" stroke="var(--axis)" stroke-width="1" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>`;
    s+=`<text x="${X((t0+t1)/2)}" y="${H-PB+14}" text-anchor="middle" font-size="11" fill="var(--muted)">${perName(p)}</text>`;
    t0=t1;
  }
  s+=`<line x1="${PL}" x2="${W-PR}" y1="${Y(.5)}" y2="${Y(.5)}" stroke="var(--axis)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  if(cur.length>1){
    const pts=cur.map(c=>`${X(c[0]).toFixed(1)},${Y(c[1]).toFixed(1)}`).join(' ');
    const poly=`<polygon points="${X(cur[0][0])},${Y(.5)} ${pts} ${X(cur[cur.length-1][0])},${Y(.5)}"`;
    s+=`<defs><clipPath id="cUp"><rect x="${PL}" y="${PT}" width="${W-PL-PR}" height="${Y(.5)-PT}"/></clipPath>`
      +`<clipPath id="cDn"><rect x="${PL}" y="${Y(.5)}" width="${W-PL-PR}" height="${H-PB-Y(.5)}"/></clipPath></defs>`
      +poly+` fill="var(--home-wash)" clip-path="url(#cUp)"/>`+poly+` fill="var(--away-wash)" clip-path="url(#cDn)"/>`
      +`<polyline points="${pts}" fill="none" stroke="var(--home)" stroke-width="2.2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    /* su anki nokta: oyun saati olaylar arasinda da aktigi icin imlec sagda ilerler */
    s+=`<line x1="${X(st.el)}" x2="${X(st.el)}" y1="${PT}" y2="${H-PB}" stroke="var(--accent)" stroke-width="1" stroke-dasharray="2 3" vector-effect="non-scaling-stroke" opacity=".55"/>`
      +`<circle cx="${X(cur[cur.length-1][0])}" cy="${Y(cur[cur.length-1][1])}" r="4.5" fill="var(--home)" stroke="var(--surface)" stroke-width="2"/>`;
  }else{
    s+=`<line x1="${PL}" x2="${W-PR}" y1="${Y(g.pre)}" y2="${Y(g.pre)}" stroke="var(--home)" stroke-width="2" stroke-dasharray="6 5" vector-effect="non-scaling-stroke"/>`
      +`<text x="${(PL+W)/2}" y="${Y(g.pre)-10}" text-anchor="middle" font-size="12" fill="var(--muted)">maç öncesi beklenti</text>`;
  }
  el('curveWrap').innerHTML=s+'</svg>';
  el('curveCap').textContent=st.s==='pre'?'Maç başlamadı; çizgi maç öncesi beklentiyi gösteriyor.'
    :`Çizgi yukarıdaysa ${g.home}, aşağıdaysa ${g.away} kazanmaya daha yakın; orta çizgi iki takım için %50.`;
}

/* ---------- alt bölümler ve sağ sütun ---------- */
function drawRest(g,st){
  const per=[]; let prevH=0,prevA=0,lastH=0,lastA=0,cp=0;
  for(let i=0;i<st.k;i++){const e=g.ev[i];
    if(e[4]!==cp){ if(cp)per.push([cp,lastH-prevH,lastA-prevA]); prevH=lastH; prevA=lastA; cp=e[4]; }
    lastH=e[2]; lastA=e[3];}
  if(cp)per.push([cp,lastH-prevH,lastA-prevA]);
  el('per').innerHTML=per.length?per.map((p,ix)=>{
    const now=ix===per.length-1&&st.s==='live';
    return `<div class="percard ${now?'now':''}"><div class="p">${perName(p[0])}${now?' (oynanıyor)':''}</div>
     <div class="s">${p[2]}–${p[1]}</div></div>`}).join('')
    :'<div class="stub">Maç başlamadı.</div>';
  el('pre').innerHTML=`
    <dt>Maç öncesi çizgi</dt><dd>${(g.sp>0?g.home:g.away)} ${Math.abs(g.sp).toFixed(1).replace('.',',')} sayı favori</dd>
    <dt>Maç öncesi olasılık</dt><dd>${g.away} %${100-pct(g.pre)} · ${g.home} %${pct(g.pre)}</dd>
    <dt>İşlenen olay</dt><dd>${fmt(st.k)}</dd>${g.syn?`<dt>Kaynak</dt><dd>${g.synNote}</dd>`:''}${st.s!=='final'?''
      :g.syn?'<dt>Doğruluk</dt><dd>üretilmiş maç, ölçüme katılmaz</dd>'
      :(b=>`<dt>Bu maçta hata (Brier)</dt><dd>model ${f3(b.m/b.n)} · yalnız maç öncesi ${f3(b.p0/b.n)}</dd>`)(gameBrier(ORIG[sel]))}`;
  const c={live:0,pre:0,final:0}; ST.forEach(s=>c[s.s]++);
  const liveIx=G.map((x,i)=>i).filter(i=>ST[i].s==='live');
  const closest=liveIx.slice().sort((a,b)=>Math.abs(ST[a].h-ST[a].a)-Math.abs(ST[b].h-ST[b].a))[0];
  const flip=liveIx.filter(i=>(G[i].pre>=.5)!==(ST[i].p>=.5));
  el('sum').innerHTML=`<div class="big">
      <div><span>${c.live}</span><em>canlı</em></div>
      <div><span>${c.final}</span><em>bitti</em></div>
      <div><span>${c.pre}</span><em>başlamadı</em></div></div>
    ${closest!==undefined?`<p>En yakın maç ${G[closest].away} ${ST[closest].a} – ${ST[closest].h} ${G[closest].home}, ${Math.abs(ST[closest].h-ST[closest].a)} sayı fark.</p>`:''}
    ${flip.length?`<p>Maç öncesi favorisi artık favori değil: ${flip.map(i=>G[i].away+'–'+G[i].home).join(', ')}.</p>`
      :liveIx.length?'<p>Maç öncesi favoriler hâlâ favori.</p>':''}
    ${(()=>{const fin=G.map((x,i)=>i).filter(i=>ST[i].s==='final'&&!G[i].syn);if(!fin.length)return'';
      let m=0,p=0,n=0;fin.forEach(i=>{const b=gameBrier(ORIG[i]);m+=b.m;p+=b.p0;n+=b.n});
      return `<p>Biten ${fin.length} gerçek maçta tahmin hatası (Brier, 0 en iyi): model <b>${f3(m/n)}</b>, yalnız maç öncesi olasılıkla ${f3(p/n)}. Küçük örnek; 2023-2026 testinde ${fmt(ACC.overall.games)} maçta ${f3(ACC.overall.m)} ve ${f3(ACC.overall.s)}.</p>`})()}`;
  const last=[];
  for(let i=st.k-1;i>=0&&last.length<6;i--)last.push(g.ev[i]);
  el('feed').innerHTML=last.length?last.map(e=>
    `<li><span class="t">P${e[4]} ${e[5]}</span><span>${evtr(e[6])} <span style="color:var(--muted)">(${e[3]}–${e[2]})</span></span></li>`).join('')
    :'<li><span class="t">—</span><span>Maç başlamadı.</span></li>';
  drawCourt(g,st);
}
