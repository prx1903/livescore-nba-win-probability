/* ---------- dogruluk ---------- */
/* ACC is written by app/demo/build_page.py from results/baseline_report.txt and results/season_type_report.txt.
   No accuracy number is typed by hand in the page. */
const TIME_LAB=['1. çeyrek','2. çeyrek','3. çeyrek','4. çeyrek ilk 7 dk','son 5 dk','uzatma'];   /* order of ACC.time */
const SEASON_LAB={regular:'Normal sezon',playoff:'Playoff',playin:'Play-in'};
const f3=x=>x.toFixed(3).replace('.',',');
/* bitmis gercek macta dakikalik anlarda Brier: model ve yalniz mac oncesi olasilik (test olcumuyle ayni an tanimi).
   Always called with the original game (ORIG), never with the events left by a feed test. */
function gameBrier(g){
  if(g._br)return g._br;
  const dur=g.ev[g.ev.length-1][0], last=g.ev[g.ev.length-1], y=last[2]>last[3]?1:0;
  let k=0,sm=0,n=0;
  for(let t=0;t<dur;t+=60){
    while(k<g.ev.length&&g.ev[k][0]<=t)k++;
    if(t===2880)continue;                              /* the end of regulation is not a snapshot (as in the test) */
    const p=k?g.ev[k-1][1]:g.pre; sm+=(p-y)**2; n++;
  }
  return g._br={m:sm,p0:n*(g.pre-y)**2,n};
}
function tipBox(box){let t=box.querySelector('.vtip');if(!t){t=document.createElement('div');t.className='vtip';t.hidden=true;box.appendChild(t)}return t}
function bindTips(box){
  const t=tipBox(box);
  box.querySelectorAll('[data-tip]').forEach(c=>{
    c.addEventListener('pointerenter',()=>{const r=c.getBoundingClientRect(),b=box.getBoundingClientRect();
      t.innerHTML=c.dataset.tip;t.style.left=(r.left+r.width/2-b.left)+'px';t.style.top=(r.top+r.height/2-b.top)+'px';t.hidden=false});
    c.addEventListener('pointerleave',()=>{t.hidden=true});
  });
}
function drawCal(){
  const W=520,H=330,L=48,R=14,T=12,B=44, X=v=>L+(W-L-R)*v, Y=v=>T+(H-T-B)*(1-v);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Kalibrasyon: modelin tahmini ve gerçekleşen oran">`;
  [0,.25,.5,.75,1].forEach(v=>{
    s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/>`
      +`<text x="${L-8}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="var(--muted)">%${v*100}</text>`
      +`<text x="${X(v)}" y="${H-B+16}" text-anchor="middle" font-size="11" fill="var(--muted)">%${v*100}</text>`;
  });
  s+=`<line x1="${X(0)}" y1="${Y(0)}" x2="${X(1)}" y2="${Y(1)}" stroke="var(--axis)" stroke-width="1.5" stroke-dasharray="5 5"/>`
    +`<text x="${X(.6)-6}" y="${Y(.6)-9}" font-size="11" fill="var(--muted)" text-anchor="middle" transform="rotate(-${Math.atan((H-T-B)/(W-L-R))*180/Math.PI} ${X(.6)-6} ${Y(.6)-9})">mükemmel ayar</text>`;
  /* iki takım için: her test anı bir kez ev sahibi (p), bir kez deplasman (1 - p) olarak sayılır */
  const K=ACC.cal.length, CAL=ACC.cal.map((a,j)=>{const b=ACC.cal[K-1-j],n=a.n+b.n;
    return {n,p:(a.n*a.p+b.n*(1-b.p))/n,o:(a.n*a.o+b.n*(1-b.o))/n}});
  const pts=CAL.map(c=>`${X(c.p).toFixed(1)},${Y(c.o).toFixed(1)}`).join(' ');
  s+=`<polyline points="${pts}" fill="none" stroke="var(--sx-model)" stroke-width="2" stroke-linejoin="round"/>`;
  CAL.forEach(c=>{
    s+=`<circle cx="${X(c.p)}" cy="${Y(c.o)}" r="4.5" fill="var(--sx-model)" stroke="var(--surface)" stroke-width="2"/>`
      +`<circle cx="${X(c.p)}" cy="${Y(c.o)}" r="13" fill="transparent" data-tip="Model: <b>%${(c.p*100).toFixed(1).replace('.',',')}</b><br>Gerçekleşen: <b>%${(c.o*100).toFixed(1).replace('.',',')}</b><br>${fmt(c.n)} takım-an"/>`;
  });
  s+=`<text x="${(L+W-R)/2}" y="${H-6}" text-anchor="middle" font-size="12" fill="var(--ink-2)">Modelin bir takıma verdiği kazanma olasılığı</text>`
    +`<text x="12" y="${(T+H-B)/2}" text-anchor="middle" font-size="12" fill="var(--ink-2)" transform="rotate(-90 12 ${(T+H-B)/2})">O takımın kazandığı oran</text></svg>`;
  const box=el('calChart'); box.innerHTML=s; bindTips(box);
  const ex=CAL[8], pc=x=>'%'+(x*100).toFixed(0);
  el('calNote').textContent='Her nokta, modelin bir takıma benzer olasılık verdiği test anlarının bir grubu (10 grup). Her an iki kez sayılır: '
    +'bir kez ev sahibi, bir kez deplasman için. Nokta kesikli çizginin üstündeyse o takım tahminden sık kazanmış, altındaysa seyrek. '
    +`Örnek: modelin bir takıma ${pc(ex.p)} civarı verdiği ${fmt(ex.n)} durumda o takım ${pc(ex.o)} oranında kazandı. `
    +'Kaynak: results/v2/model_report.txt, test 2023-2026.';
}
function drawTime(){
  const W=620,H=300,L=48,R=118,T=14,B=40, n=ACC.time.length, gapOT=34;
  const X=i=>L+((W-L-R-gapOT)/(n-1))*i+(i===n-1?gapOT:0), Y=v=>T+(H-T-B)*(1-v/0.28);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Maçın bölümüne göre Brier hatası: model ve yalnız maç öncesi çizgi">`;
  [0,.05,.1,.15,.2,.25].forEach(v=>{
    s+=`<line x1="${L}" x2="${W-R+10}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/>`
      +`<text x="${L-8}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="var(--muted)">${v.toFixed(2).replace('.',',')}</text>`;
  });
  const xd=(X(n-2)+X(n-1))/2;
  s+=`<line x1="${xd}" x2="${xd}" y1="${T}" y2="${H-B}" stroke="var(--axis)" stroke-dasharray="3 4"/>`;
  ACC.time.forEach((c,i)=>{s+=`<text x="${X(i)}" y="${H-B+18}" text-anchor="middle" font-size="11" fill="var(--muted)">${TIME_LAB[i]}</text>`});
  [['s','var(--sx-base)','6 5','maç öncesi'],['m','var(--sx-model)','','model']].forEach(([k,col,dash,lab])=>{
    const pts=ACC.time.slice(0,n-1).map((c,i)=>`${X(i)},${Y(c[k]).toFixed(1)}`).join(' ');
    s+=`<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2" stroke-dasharray="${dash}" stroke-linejoin="round"/>`;
    ACC.time.forEach((c,i)=>{s+=`<circle cx="${X(i)}" cy="${Y(c[k])}" r="4.5" fill="${col}" stroke="var(--surface)" stroke-width="2"/>`});
    const c=ACC.time[n-1];
    s+=`<text x="${X(n-1)+12}" y="${Y(c[k])+4}" font-size="12" fill="var(--ink-2)">${lab} ${f3(c[k])}</text>`;
  });
  ACC.time.forEach((c,i)=>{
    s+=`<rect x="${X(i)-22}" y="${T}" width="44" height="${H-T-B}" fill="transparent" data-tip="<b>${TIME_LAB[i]}</b><br>Model: <b>${f3(c.m)}</b><br>Yalnız maç öncesi: ${f3(c.s)}<br>${fmt(c.n)} an"/>`;
  });
  s+=`<text x="12" y="${(T+H-B)/2}" text-anchor="middle" font-size="12" fill="var(--ink-2)" transform="rotate(-90 12 ${(T+H-B)/2})">Brier hatası</text></svg>`;
  const box=el('timeChart');
  box.innerHTML=`<div class="lg"><span><i style="border-color:var(--sx-model)"></i>model</span>`
    +`<span><i class="d" style="border-color:var(--sx-base)"></i>yalnız maç öncesi çizgi</span></div>`+s;
  bindTips(box);
}
/* veri paneli bir kez kurulur: içindeki bağlantılar her karede yeniden yaratılmaz */
function buildData(){
  el('data').innerHTML=`<div class="st"><i></i><span id="dSt"></span></div><span id="dTxt"></span>
       <span class="lastw" id="dLast" hidden></span>
       <small>Kurallar, sayaçlar ve akış testi <a href="#" class="linkbtn" id="toModel">Model bölümünde</a>.</small>`;
  el('toModel').onclick=e=>{e.preventDefault();view('model')};
}
const evTime=it=>perShort(it.t!==undefined?it.t:it.e[0]);
const ms=x=>{x=Math.max(0,Math.round(x));return Math.floor(x/60)+':'+String(x%60).padStart(2,'0')};
function perShort(t){if(t<=2880){const q=Math.min(4,Math.floor(t/720)+1);return 'P'+q+' '+ms(720-(t-(q-1)*720))}
  const o=Math.min(Math.floor((t-2880)/300)+1,Math.ceil((t-2880)/300)||1);return 'U'+o+' '+ms(300-((t-2880)-(o-1)*300))}
function updateData(){
  const fs=feedState(sel),L=fs.k?fs.L[fs.k-1]:null,g=G[sel];
  el('data').className='datapanel'+(fs.s==='warn'?' warn':fs.s==='bad'?' bad':'');
  el('dSt').textContent=FS_TXT[fs.s];
  el('dTxt').textContent=!L?'Henüz olay gelmedi.'
    :`${fmt(L.acc)} olay işlendi, ${fmt(L.rej)} atlandı, ${fmt(L.miss)} olay ulaşmadı.`+(fs.s==='bad'?` ${f0(fs.age)} saniyedir yeni veri gelmedi; gösterilen olasılık güncel olmayabilir.`:'');
  const last=fs.items[fs.items.length-1];
  el('dLast').hidden=!(last&&fs.s!=='ok'); if(last)el('dLast').textContent='Son uyarı: '+last.m;
  /* Model bölümü */
  const sb=el('fsSt'); sb.className='fs-st'+(fs.s==='warn'?' warn':fs.s==='bad'?' bad':''); sb.querySelector('span').textContent=FS_TXT[fs.s];
  el('fsGame').textContent=`Maç: ${g.away} @ ${g.home}${g.syn?' (üretilmiş maç)':''}, gün saati ${hhmm(T)}. Test: `
    +({normal:'normal akış; bu maçın verisi eksiksiz olduğu için uyarı beklenmez.',drop:'olayların yaklaşık %30\'u ulaşmıyor; skor ve olasılık son ulaşan olaydan.',
       delay:'akış maçın ortasında ('+perShort(g.feed.stall?g.feed.stall[0]:0)+') 40 sn duruyor; 30 sn geçince veri bayat sayılır.'})[feedMode];
  el('fsAcc').textContent=L?fmt(L.acc):0; el('fsRej').textContent=L?fmt(L.rej):0;
  el('fsMiss').textContent=L?fmt(L.miss):0; el('fsWarn').textContent=L?fmt(L.warn):0;
  el('fsAge').textContent=fs.s==='pre'?'–':fs.age===0?'maç bitti':f0(fs.age)+' sn önce';
  const ul=el('fsWarns'), its=fs.items.slice(-6).reverse();
  ul.innerHTML=its.length?its.map(x=>`<li><span class="t">${evTime(x)}</span><span>${x.m}</span></li>`).join('')
    :'<li><span class="t"></span><span>Uyarı yok.</span></li>';
}

/* numbers and notes of the Model view */
const f4=x=>x.toFixed(4).replace('.',',');
const sg4=x=>(x<0?'−':'+')+Math.abs(x).toFixed(4).replace('.',',');
function drawAccText(){
  const o=ACC.overall,t=ACC.time,S=ACC.season;
  el('tBrier').textContent=f4(o.m); el('tLogloss').textContent=f4(o.ll); el('tN').textContent=fmt(o.n);
  el('timeNote').textContent=`İlk çeyrekte model (${f3(t[0].m)}) maç öncesi çizgiye (${f3(t[0].s)}) yakın; skor ve süre biriktikçe hata düşüyor, `
    +`son 5 dakikada ${f3(t[4].m)}. Uzatma ayrı gösterildi (${fmt(t[5].n)} an). Kaynak: results/v2/model_report.txt (model), results/baseline_report.txt (maç öncesi çizgi); test 2023-2026.`;
  const [md,mlo,mhi]=o.diff;
  el('modelNote').textContent=`Ekrandaki bütün olasılıklar skor dağılımı modelinden gelir; üstteki sayılar onun. Karşılaştırma için lojistik model: `
    +`Brier ${f4(o.logit.m)}, log kayıp ${f4(o.logit.ll)}. İki modelin Brier farkı ${sg4(md)}, %95 aralık [${sg4(mlo)}, ${sg4(mhi)}]; `
    +(mlo<0&&mhi>0?'aralık sıfırı içerdiği için iki model bu veriyle ayırt edilemiyor.':'aralık sıfırı içermiyor.');
  el('seasonRows').innerHTML=S.rows.map(r=>`<tr><td>${SEASON_LAB[r.key]}</td><td>${fmt(r.n)}</td><td>${fmt(r.snaps)}</td>`
    +`<td>${f4(r.brier)}</td><td>${f4(r.lo)} – ${f4(r.hi)}</td><td>${f4(r.ll)}</td></tr>`).join('');
  const [d,lo,hi]=S.diff, pin=S.rows.find(r=>r.key==='playin');
  el('seasonNote').textContent=`Playoff ile normal sezon arasındaki Brier farkı ${sg4(d)}, %95 aralık [${sg4(lo)}, ${sg4(hi)}]. `
    +(lo<0&&hi>0?'Aralık sıfırı içerdiği için fark bu veriyle ayırt edilemiyor. ':'Aralık sıfırı içermiyor. ')
    +`Play-in satırı ${fmt(pin.n)} maça dayanıyor, yalnızca bilgi amaçlı. `
    +`Bu tabloda Brier önce her maçın içinde, sonra maçlar arasında ortalanır; lojistik modelin bütün test anlarındaki ortalaması ${f4(o.logit.m)}.`;
}
