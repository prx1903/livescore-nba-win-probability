const G=DAY.games, TYPES=DAY.types;
/* takim adlari ve en sik olay turlerinin Turkcesi (listede olmayan olay ingilizce kalir) */
const NAME={ATL:'Atlanta Hawks',BKN:'Brooklyn Nets',BOS:'Boston Celtics',CHA:'Charlotte Hornets',CHI:'Chicago Bulls',
CLE:'Cleveland Cavaliers',DAL:'Dallas Mavericks',DEN:'Denver Nuggets',DET:'Detroit Pistons',GS:'Golden State Warriors',
HOU:'Houston Rockets',IND:'Indiana Pacers',LAC:'LA Clippers',LAL:'Los Angeles Lakers',MEM:'Memphis Grizzlies',
MIA:'Miami Heat',MIL:'Milwaukee Bucks',MIN:'Minnesota Timberwolves',NO:'New Orleans Pelicans',NY:'New York Knicks',
OKC:'Oklahoma City Thunder',ORL:'Orlando Magic',PHI:'Philadelphia 76ers',PHX:'Phoenix Suns',POR:'Portland Trail Blazers',
SA:'San Antonio Spurs',SAC:'Sacramento Kings',TOR:'Toronto Raptors',UTAH:'Utah Jazz',WSH:'Washington Wizards'};
const EVTR={'Defensive Rebound':'Defansif ribaund','Substitution':'Oyuncu değişikliği','Jump Shot':'Sıçrayarak şut',
'Offensive Rebound':'Ofansif ribaund','Pullup Jump Shot':'Durup sıçrayarak şut','Shooting Foul':'Şut faulü',
'Free Throw - 1 of 2':'Serbest atış (1/2)','Free Throw - 2 of 2':'Serbest atış (2/2)','Free Throw - 1 of 1':'Serbest atış (1/1)',
'Free Throw - 1 of 3':'Serbest atış (1/3)','Free Throw - 2 of 3':'Serbest atış (2/3)','Free Throw - 3 of 3':'Serbest atış (3/3)',
'Driving Layup Shot':'Potaya girerek turnike','Personal Foul':'Kişisel faul','Full Timeout':'Mola',
'Short Timeout':'Kısa mola','Driving Floating Jump Shot':'Potaya girerek floater','Bad Pass\nTurnover':'Hatalı pas, top kaybı',
'Step Back Jump Shot':'Geri adımla şut','Lost Ball Turnover':'Top kaybı','Running Layup Shot':'Koşarak turnike',
'Running Jump Shot':'Koşarak şut','Driving Finger Roll Layup':'Potaya girerek finger roll','Running Pullup Jump Shot':'Koşarak durup şut',
'Cutting Layup Shot':'Boşalarak turnike','End Period':'Periyot bitti','Tip Shot':'Tap-in','Alley Oop Dunk Shot':'Alley-oop smaç',
'Fade Away Jump Shot':'Geriye kaykılarak şut','Out of Bounds - Bad Pass Turnover':'Hatalı pas, aut','Dunk Shot':'Smaç',
'Layup Shot Putback':'Hücum ribaundundan turnike','Driving Dunk Shot':'Potaya girerek smaç','Hook Shot':'Kanca şut',
'Offensive Foul':'Hücum faulü','Traveling':'Adım ihlali','Loose Ball Foul':'Mücadele faulü','Turnaround Jump Shot':'Dönerek şut',
'Driving Hook Shot':'Potaya girerek kanca','Block Shot':'Blok','Kicked Ball Violation':'Ayakla oynama',
'Delay of Game':'Oyunu geciktirme','Jump Ball':'Hava atışı','Ejection':'Oyundan atılma','End Game':'Maç bitti',
'Defensive 3-Seconds Technical':'3 saniye ihlali','Technical Foul':'Teknik faul','Flagrant Foul Type 1':'Faul (flagrant 1)',
/* uretilmis macin genel olay metinleri */
'Made 2-pt shot':'İki sayılık basket','Made 3-pt shot':'Üç sayılık basket','Missed shot':'Kaçan şut',
'Offensive rebound':'Ofansif ribaund','Defensive rebound':'Defansif ribaund','Turnover':'Top kaybı',
'Shooting foul':'Şut faulü','Personal foul':'Kişisel faul','Start of period':'Periyot başladı',
'End of period':'Periyot bitti','Jump ball':'Hava atışı','End of game':'Maç bitti'};
const evtr=i=>{const t=TYPES[i];if(EVTR[t])return EVTR[t];
  const f=/^Free throw (\d) of (\d)( \(and-one\))? (made|missed)$/.exec(t);
  return f?`Serbest atış (${f[2]==='1'&&f[3]?'basket +1':f[1]+'/'+f[2]}) ${f[4]==='made'?'girdi':'kaçtı'}`:t};
const el=id=>document.getElementById(id);
const fmt=n=>n.toLocaleString('tr-TR');
const pct=p=>Math.round(p*100);
/* Probability as text. Before the end of a game nothing is certain: a value that rounds to 100 is written ">%99"
   and one that rounds to 0 "<%1"; only a finished game (fin) shows %100 and %0. */
const pcr=(r,fin)=>fin?'%'+r:r>=100?'>%99':r<=0?'<%1':'%'+r;
const pcs=(p,fin)=>pcr(pct(p),fin);
/* the other team's share of a home probability p: 100 minus the rounded home value, so that the two add up to 100 */
const pcsA=(p,fin)=>pcr(100-pct(p),fin);
const pc1=x=>x>0&&x<0.0005?'<%0,1':'%'+(x*100).toFixed(1).replace('.',',');
const hhmm=s=>String(Math.floor(s/3600)%24).padStart(2,'0')+':'+String(Math.floor(s/60)%60).padStart(2,'0');
/* oyun saati: 1 dakikanin altinda onda birlik gosterilir */
const mmss=r=>r>=60?Math.floor(r/60)+':'+String(Math.floor(r%60)).padStart(2,'0'):Math.max(0,r).toFixed(1);
const perName=p=>p>4?(p-4)+'. uzatma':p+'. periyot';

