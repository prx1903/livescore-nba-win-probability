/* ---------- ne olurdu? ----------
   A scenario for the selected game: the user sets the period, the time left in it and the score.
   Win probability: headlineProb(), the model of the match screen (logistic). Overtime probability and expected
   final score: ScoreModel (score-distribution model). Until the user changes a control the scenario follows
   the game; "Maçın şu anki durumuna dön" switches back to following. */
const WI={follow:true,g:-1,per:1,rem:720,h:0,a:0};
const perLen=per=>per<=4?720:300;
/* Home win probability of the match screen for a game state. The one place to change if the headline model changes. */
function headlineProb(g,per,rem,h,a){
  return winProb(h-a,per<=4?(4-per)*720+rem:rem,per>4,g.sp);
}
/* Everything the scenario shows. decided: no time left in the last period and the score is not tied. */
function wiCompute(g,per,rem,h,a){
  const decided=per>=4&&rem<=0&&h!==a;
  const t=per<=4?(per-1)*720+(720-rem):2880+300*(per-5)+(300-rem);
  const sm=ScoreModel.state(t,per,h,a,g.mu,g.mt,null,null);
  return {decided,p:decided?(h>a?1:0):headlineProb(g,per,rem,h,a),pot:decided?0:sm.pot,eh:decided?h:sm.exp_h,ea:decided?a:sm.exp_a};
}
const pc1=x=>'%'+(x*100).toFixed(1).replace('.',',');
const WI_ROWS=[2160,1440,720,360,180,60,10];        /* seconds left in regulation shown in the table */
function drawWhatIf(g,st){
  if(WI.g!==sel){WI.g=sel;WI.follow=true}
  if(WI.follow){WI.per=Math.min(st.pe,7);WI.rem=Math.min(Math.round(st.rem),perLen(WI.per));WI.h=st.h;WI.a=st.a}
  const {per,rem,h,a}=WI, c=wiCompute(g,per,rem,h,a);
  /* following the game: show exactly the probability of the match screen (it belongs to the last event) */
  const p=WI.follow?st.p:c.p, ph=pct(p);
  const act=document.activeElement;
  [['wiPer',per],['wiRem',rem],['wiA',a],['wiH',h]].forEach(([id,v])=>{const x=el(id);if(x!==act||WI.follow)x.value=v});
  el('wiRem').max=perLen(per);
  el('wiRemOut').textContent=mmss(rem);
  el('wiALab').textContent=g.away+' (deplasman) skoru'; el('wiHLab').textContent=g.home+' (ev sahibi) skoru';
  el('wiReset').hidden=WI.follow;
  el('wiBarH').style.width=ph+'%'; el('wiBarA').style.width=(100-ph)+'%';
  el('wiLabA').innerHTML=`<span class="num">%${100-ph}</span>${g.away}`;
  el('wiLabH').innerHTML=`${g.home}<span class="num" style="margin:0 0 0 6px">%${ph}</span>`;
  const now=pct(st.p), d=ph-now;
  el('wiOut').innerHTML=`
    <dt>Senaryo</dt><dd>${perName(per)}, ${mmss(rem)} kala · ${g.away} ${a} – ${h} ${g.home}</dd>`
    +(WI.follow?'<dt>Durum</dt><dd>maçın şu anki durumu izleniyor</dd>'
      :`<dt>Maçın şu anki durumunda</dt><dd>${g.away} %${100-now} · ${g.home} %${now}</dd>
    <dt>Senaryonun farkı</dt><dd>${d===0?'fark yok':`${d>0?g.home:g.away} için +${Math.abs(d)} yüzde puanı`}</dd>`)
    +`<dt>Uzatma olasılığı</dt><dd>${c.decided?'maç bitmiş olurdu':per>4?'uzatma oynanıyor':pc1(c.pot)}</dd>
    <dt>Beklenen maç sonu skoru</dt><dd>${g.away} ${Math.round(c.ea)} – ${Math.round(c.eh)} ${g.home}</dd>`;
  const m=h-a, lead=m===0?'beraberlik':`${m>0?g.home:g.away} ${Math.abs(m)} sayı önde`;
  el('wiTabH').textContent=`Aynı fark (${lead}), farklı kalan süre`;
  el('wiTab').innerHTML=`<thead><tr><th>Normal sürede kalan</th><th>${g.away}</th><th>${g.home}</th></tr></thead><tbody>`
    +WI_ROWS.map(tl=>{const q=pct(winProb(m,tl,false,g.sp));
      return `<tr><td>${tl>=60?tl/60+' dk':tl+' sn'}</td><td>%${100-q}</td><td>%${q}</td></tr>`}).join('')+'</tbody>';
  el('wiNote').textContent='Senaryo bir tahmindir, kesin sonuç değildir. Kazanma olasılığı maç ekranındaki modelden gelir; '
    +'uzatma olasılığı ve beklenen skor ayrı bir modelden (skor dağılımı modeli) geldiği için aralarında küçük farklar olabilir.'
    +(g.syn?' Bu maç gerçek değil: üretilmiş bir maç.':'');
}
function wiRead(){
  const per=+el('wiPer').value, n=x=>Math.min(250,Math.max(0,Math.round(+x||0)));
  WI.follow=false; WI.per=per; WI.rem=Math.min(+el('wiRem').value,perLen(per)); WI.a=n(el('wiA').value); WI.h=n(el('wiH').value);
  drawWhatIf(G[sel],ST[sel]);
}
['wiPer','wiRem','wiA','wiH'].forEach(id=>el(id).addEventListener('input',wiRead));
el('wiReset').onclick=()=>{WI.follow=true;drawWhatIf(G[sel],ST[sel])};
