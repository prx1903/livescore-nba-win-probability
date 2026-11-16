/* ---------- skor dağılımı modeli ----------
   The score-distribution model (src/v2) for one game state, the same calculation as src/v2/refmodel.py
   (tests/test_model_parity.py compares the two on random states). MODEL is written by build_page.py from
   results/v2/sim_params.json.
   ScoreModel.state(t, per, homeScore, awayScore, mu_m, mu_t, ms, ts):
     t elapsed game seconds, per period (5+ = overtime), mu_m / mu_t pre-game expected regulation margin / total,
     ms / ts margin / total at the start of each period (optional, for the period outcomes).
     Returns pw (home wins), pot (overtime), mu and sd of the margin at the end of regulation (of the overtime
     period when per > 4), exp_h / exp_a expected final score, periods, and parts (the pieces of mu). */
const ScoreModel=(()=>{
  function erfc(x){
    if(x<0)return 2-erfc(-x);
    if(x<2.5){let sum=x,term=x;const x2=x*x;for(let n=1;n<300;n++){term*=-x2/n;const add=term/(2*n+1);sum+=add;if(Math.abs(add)<1e-17*Math.abs(sum))break}return 1-2/Math.sqrt(Math.PI)*sum}
    let t=x;for(let n=80;n>=1;n--)t=x+(n/2)/t;return Math.exp(-x*x)/Math.sqrt(Math.PI)/t;
  }
  const Phi=z=>0.5*erfc(-z/Math.SQRT2);
  const Q=z=>0.5*erfc(z/Math.SQRT2);       // 1 - Phi(z)
  function interp(x,arr){x=Math.min(Math.max(x,0),2880);const i=Math.min(Math.floor(x/60),47);const f=(x-i*60)/60;return arr[i]+(arr[i+1]-arr[i])*f}
  const sOf=k=>interp(k,MODEL.share);
  function hOf(tau){const x=Math.min(Math.max(tau/60,1e-9),48);const E=MODEL.H_EDGES;let i=0;while(i<E.length&&E[i]<x)i++;const g=Math.min(Math.max(i-1,0),MODEL.h.length-1);return MODEL.h[g]}
  function qOT(mu_m){const O=MODEL.OT,mu=O.c*mu_m*300/2880,sd=Math.sqrt(O.v),hb=O.h;const pw=Q((hb-mu)/sd),pl=Phi((-hb-mu)/sd);return [pw/(pw+pl),1-pw-pl]}
  function state(t,per,hs,as,mu_m,mu_t,ms,ts){
    const m=hs-as,O=MODEL.OT,b=MODEL.b,out={};const [q,tie1]=qOT(mu_m);out.q=q;
    if(per<=4){
      const k=Math.min(t,2880),s=sOf(k),tau=2880-k;
      const rm=mu_m*s+b*m*s,rt=mu_t*s,mu=m+rm,sd=Math.sqrt(Math.max(interp(tau,MODEL.Vm),1e-9)),hb=hOf(tau);
      const phi=Q((hb-mu)/sd),pt=Phi((hb-mu)/sd)-Phi((-hb-mu)/sd);
      Object.assign(out,{ot:false,pw:Math.min(Math.max(phi+pt*q,1e-6),1-1e-6),pot:pt,mu,sd,band:hb,mu_t:hs+as+rt,sd_t:Math.sqrt(Math.max(interp(tau,MODEL.Vt),1e-9)),cov:interp(tau,MODEL.Cmt),p_reg_win:phi,p_reg_loss:1-phi-pt,
        parts:{now:m,line:mu_m*s,shrink:b*m*s},s,tau});
      const nOT=1/(1-tie1),otm=O.c*mu_m*300/2880;
      out.exp_h=hs+(rt+rm)/2+pt*nOT*(O.pts_mean+otm)/2;out.exp_a=as+(rt-rm)/2+pt*nOT*(O.pts_mean-otm)/2;
      const pers=[];
      for(let j=1;j<=4;j++){
        const st=720*(j-1),en=720*j;
        if(k>=en||per>j){pers.push(null);continue}
        const a0=Math.min(Math.max(k,st),en),sr=sOf(a0)-sOf(en),adj=b*m*s,frac=s>1e-9?sr/s:0,mean_inc=mu_m*sr+adj*frac;
        const full=interp(2880-st,MODEL.Vm)-interp(2880-en,MODEL.Vm),part=interp(2880-a0,MODEL.Vm)-interp(2880-en,MODEL.Vm);
        const v=MODEL.v_per[j-1]*(full>0?part/full:0);
        const started=k>=st&&ms&&(j in ms);
        const so_m=started?m-ms[j]:0,so_t=started?(hs+as)-ts[j]:0;
        const mu_j=so_m+mean_inc,sd_j=Math.sqrt(Math.max(v,1e-9));
        const ph=Q((0.5-mu_j)/sd_j),ptj=Phi((0.5-mu_j)/sd_j)-Phi((-0.5-mu_j)/sd_j),tot_j=so_t+mu_t*sr;
        pers.push({ph,pt:ptj,pa:1-ph-ptj,eh:(tot_j+mu_j)/2,ea:(tot_j-mu_j)/2});
      }
      out.periods=pers;
    }else{
      const end=2880+300*(per-4),tl=Math.max(end-t,0);
      const mu=m+O.c*mu_m*tl/2880,sd=Math.sqrt(Math.max(O.v*tl/300,1e-9)),hb=O.h;
      const phi=Q((hb-mu)/sd),pt=Phi((hb-mu)/sd)-Phi((-hb-mu)/sd);
      Object.assign(out,{ot:true,pw:Math.min(Math.max(phi+pt*q,1e-6),1-1e-6),pot:1,mu,sd,band:hb,p_reg_win:phi,p_reg_loss:1-phi-pt,periods:[null,null,null,null],
        parts:{now:m,line:mu-m,shrink:0},tl});
      const nMore=pt/(1-tie1);
      out.exp_h=hs+(O.pts_mean*tl/300+(mu-m))/2+nMore*O.pts_mean/2;out.exp_a=as+(O.pts_mean*tl/300-(mu-m))/2+nMore*O.pts_mean/2;
      out.mu_t=out.exp_h+out.exp_a;out.sd_t=Math.sqrt(O.pts_var*tl/300+1e-9);out.cov=0;
    }
    return out;
  }
  return {state,qOT,Phi};
})();

/* ---------- lojistik model ----------
   Win probability of the home team: the same formula as src/winprob.py (tests/test_model_parity.py compares them).
   LOGIT is written by build_page.py from models/model_coefficients.json.
   margin = home - away; secsLeft = seconds left in regulation, in overtime seconds left in that overtime;
   spread > 0: the home team is the favourite. */
function winProb(margin,secsLeft,isOt,spread){
  const tl=Math.max(secsLeft,0);
  const f={m_over_sqrt_tl:margin/Math.sqrt(tl+1),is_ot:isOt?1:0,spread_x_tl:spread*(tl/2880),spread_x_sqrt_tl:spread*Math.sqrt(tl/2880),m:margin};
  let z=LOGIT.intercept;
  LOGIT.features.forEach((n,i)=>{z+=LOGIT.coef[i]*f[n]});
  return 1/(1+Math.exp(-z));
}
