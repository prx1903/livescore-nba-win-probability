/* ---------- ev sahibi avantajı ----------
   Model farkı bahis çizgisinden alır: beklenen fark = a + b·çizgi. Çizgi ev sahibi avantajını zaten içerir; modelde ayrı
   bir avantaj girdisi yoktur. Ayrım bir tahmindir: avantaj = takım güç puanları güncellenirken öğrenilen lig geneli
   ev sahibi farkı (H, maç öncesi değer). Sezon ortalamaları DAY.date'ten önce oynanmış maçlardan. */
const sg1=x=>(x>0?'+':x<0?'−':'')+Math.abs(x).toFixed(1).replace('.',',');
const DATE_TR=(d=>d.getDate()+' '+['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'][d.getMonth()])(new Date(DAY.date+'T12:00:00'));
/* fark, lehine olduğu takımın adıyla: "NY lehine 3,3 sayı" */
const side=(g,x)=>Math.abs(x)<0.05?'denk':`${x>0?g.home:g.away} lehine ${Math.abs(x).toFixed(1).replace('.',',')} sayı`;
function drawHome(g){
  if(el('homeSplit').dataset.g===String(g.id))return;
  el('homeSplit').dataset.g=g.id;
  const HM=DAY.home,b=HM.b[1],vp=b*g.H,cur=HM.seasons[HM.seasons.length-1];
  el('homeSplit').innerHTML=`
    <dt>Lig geneli ev sahibi avantajı (tahmin)</dt><dd>${sg1(g.H)} sayı</dd>
    <dt>Modelin beklediği fark</dt><dd>${side(g,g.mu)}</dd>
    <dt>— ev sahibi avantajından</dt><dd>${side(g,vp)}</dd>
    <dt>— takımların güç farkından</dt><dd>${side(g,g.mu-vp)}</dd>`;
  el('homeTxt').textContent='Model ev sahibi avantajını ayrı bir girdi olarak kullanmaz: beklenen farkı bahis çizgisinden alır ve çizgi bu avantajı zaten içerir. '
    +'Buradaki ayrım bir tahmindir. Avantajın büyüklüğü, takım güç puanları güncellenirken öğrenilen lig geneli ev sahibi farkıdır. '
    +`Model çizgiyi ${b.toFixed(2).replace('.',',')} ile çarptığı için (geçmiş maçlarda gerçekleşen fark çizgiden biraz küçük kalmış) ev sahibi payı avantajdan biraz küçük çıkar.`
    +(g.syn?' Üretilmiş maçta güçler ve avantaj sezon sonu değerleridir.':'');
  /* sezon grafiği: çubuk = gerçekleşen ortalama normal süre farkı, nokta = ortalama bahis çizgisi */
  const S=HM.seasons,W=640,H=250,L=40,R=10,T0=12,B=34,PW=W-L-R,PH=H-T0-B,bw=PW/S.length;
  const mx=Math.ceil(Math.max(...S.map(x=>Math.max(x.margin,x.spread)))+0.5);
  const X=i=>L+bw*i+bw/2,Y=v=>T0+PH*(1-v/mx),w=Math.min(24,bw-8);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Sezon sezon ev sahibi avantajı">`;
  for(let k=0;k<=mx;k++)s+=`<line x1="${L}" x2="${W-R}" y1="${Y(k)}" y2="${Y(k)}" stroke="${k?'var(--grid)':'var(--axis)'}"/>`
    +`<text x="${L-8}" y="${Y(k)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${k?'+'+k:0}</text>`;
  S.forEach((d,i)=>{const cx=X(i),y=Y(d.margin),hh=Y(0)-y,r=Math.min(4,w/2,hh);
    s+=`<path d="M${cx-w/2} ${Y(0)} V${y+r} Q${cx-w/2} ${y} ${cx-w/2+r} ${y} H${cx+w/2-r} Q${cx+w/2} ${y} ${cx+w/2} ${y+r} V${Y(0)} Z" fill="${d.partial?'var(--accent)':'var(--axis)'}"/>`
      +`<circle cx="${cx}" cy="${Y(d.spread)}" r="4.5" fill="var(--ink)" stroke="var(--surface)" stroke-width="2"/>`
      +`<text x="${cx}" y="${H-B+16}" text-anchor="middle" font-size="11" fill="${d.partial?'var(--ink)':'var(--muted)'}">${d.season.slice(2,4)}-${d.season.slice(5)}</text>`
      +`<rect x="${cx-bw/2}" y="${T0}" width="${bw}" height="${PH}" fill="transparent" data-tip="<b>${d.season}</b>${d.partial?' ('+DATE_TR+'\'a kadar)':''}<br>${fmt(d.n)} normal sezon maçı<br>Normal süre farkı: <b>${sg1(d.margin)}</b><br>Bahis çizgisi: ${sg1(d.spread)}<br>Ev sahibi kazandı: %${(d.home_win*100).toFixed(1).replace('.',',')}"/>`;
  });
  s+=`<text x="12" y="${T0+PH/2}" text-anchor="middle" font-size="12" fill="var(--ink-2)" transform="rotate(-90 12 ${T0+PH/2})">sayı, ev sahibi lehine</text></svg>`;
  const box=el('homeChart');
  box.innerHTML=`<div class="lg"><span><i style="border-top:10px solid var(--axis);width:10px;vertical-align:0"></i>gerçekleşen ortalama normal süre farkı</span>`
    +`<span><i style="border:0;width:9px;height:9px;border-radius:50%;background:var(--ink);vertical-align:0"></i>ortalama bahis çizgisi</span>`
    +`<span><i style="border-top:10px solid var(--accent);width:10px;vertical-align:0"></i>${cur.season}, ${DATE_TR}'a kadar</span></div>`+s;
  bindTips(box);
  const po=HM.playoff;
  el('homePO').textContent=`${cur.season} normal sezonunda ${DATE_TR}'a kadar (${fmt(cur.n)} maç) ortalama çizgi ${sg1(cur.spread)}, gerçekleşen ortalama normal süre farkı ${sg1(cur.margin)} sayı, ev sahibi kazanma oranı %${(cur.home_win*100).toFixed(1).replace('.',',')}. `
    +`${S[0].season} ile ${S[S.length-2].season} arasındaki playoff maçlarında (${fmt(po.n)} maç) ortalama fark ${sg1(po.margin)}, ortalama çizgi ${sg1(po.spread)}, ev sahibi kazanma %${(po.home_win*100).toFixed(1).replace('.',',')}. `
    +'Sezonlar arasındaki değişimin nedenleri bu veriden ayrılamaz.';
}

