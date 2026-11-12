"""
Canlı akış simülasyonu: geçmiş bir maçı olay olay "canlı yayın" gibi akıtır.
  üretici (thread)  -> kuyruk (Queue) -> tüketici: olayı kontrol eder, skor/süre durumunu günceller, olasılığı hesaplar, yazdırır.

Kullanım:
  python3 live_replay.py --data <veri_klasoru> --model model_coefficients.json --game <game_id> [--speed 20] [--out live_state.json]
  --speed 0   : bekleme yok (test için). --speed 1: oyun saati gerçek hızda (çeyrek araları yok sayılır).
  --list      : veri klasöründeki test maçlarından birkaç game_id gösterir.
Her olayda --out dosyasına son durum yazılır; bir arayüz bu dosyayı okuyarak canlı gösterim yapabilir.

Üretilmiş maç (gerçek değil; src/simulation/game_simulator.py):
  python3 live_replay.py --model model_coefficients.json --sim --home BOS --away LAL --season 2025 [--sim-seed 7] [--speed 60]
  --home/--away/--season verilmezse rastgele seçilir. Güçler o sezonun takım puanlarından gelir; aynı tohum aynı maçı verir.
  --data gerekmez; --repo verilmezse deponun kök klasörü kullanılır.

Eksik ve geciken veri (bkz. feed_checks.py):
  - Bozuk ya da eksik olaylar atlanır veya uyarıyla kabul edilir; model yalnızca kabul edilen son durumu kullanır.
  - --stale-after saniye (gerçek saat) yeni olay gelmezse durum dosyasında "stale": true yazılır ve uyarı basılır.
  - Maç öncesi çizgi yoksa bu açıkça bildirilir.
  Test için eksik/geciken veri üretme:
  --drop-rate 0.3          : olayların %30'unu rastgele düşür (--seed ile tekrarlanabilir)
  --delay-at 200 --delay-sec 40 : 200. olaydan önce akışı 40 sn durdur
"""
import argparse, json, os, queue, random, threading, time
import pandas as pd
from winprob import load_model, predict
from feed_checks import FeedState, check_event, data_age, is_stale, spread_or_default, STALE_AFTER_SEC

ap = argparse.ArgumentParser()
ap.add_argument('--data'); ap.add_argument('--model', required=True)
ap.add_argument('--game', type=int); ap.add_argument('--speed', type=float, default=20.0)
ap.add_argument('--out', default='live_state.json'); ap.add_argument('--list', action='store_true')
ap.add_argument('--stale-after', type=float, default=STALE_AFTER_SEC)
ap.add_argument('--drop-rate', type=float, default=0.0); ap.add_argument('--seed', type=int, default=0)
ap.add_argument('--delay-at', type=int, default=-1); ap.add_argument('--delay-sec', type=float, default=0.0)
ap.add_argument('--sim', action='store_true'); ap.add_argument('--home', default='random')
ap.add_argument('--away', default='random'); ap.add_argument('--season', default='random')
ap.add_argument('--sim-seed', type=int, default=0)
ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = ap.parse_args()

if a.sim:
    # synthetic game: same event columns as pbp_clean, so the rest of the script is unchanged
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'simulation'))
    import game_simulator as gs
    inp = gs.Inputs(a.repo)
    year, home, away = gs.pick_matchup(inp, a.season, a.home, a.away, seed=a.sim_seed)
    info, ev = gs.simulate_game(inp, year, home, away, seed=a.sim_seed)
    a.game = info['game_id']
    g = pd.Series(dict(home_abbrev=home, away_abbrev=away, spread_home=info['spread_home'],
                       game_date=f'üretilmiş maç ({year - 1}-{str(year)[2:]} güçleri, tohum {a.sim_seed})',
                       home_final=info['home_final'], away_final=info['away_final'], home_win_final=info['home_win_final']))
else:
    if not a.data:
        ap.error('--data gerekli (ya da --sim)')
    games = pd.read_csv(os.path.join(a.data, 'games.csv')).set_index('game_id')
    if a.list:
        print(games[(games.file_year >= 2023) & games.is_valid & games.has_ot].head(10)[['game_date', 'home_abbrev', 'away_abbrev', 'home_final', 'away_final']])
        raise SystemExit
    g = games.loc[a.game]
    year = int(g.file_year)
    ev = pd.read_parquet(os.path.join(a.data, 'pbp_clean', f'pbp_clean_{year}.parquet'))
    ev = ev[ev.game_id == a.game].sort_values('game_play_number').reset_index(drop=True)
model = load_model(a.model)
spread, spread_warning = spread_or_default(g.spread_home)
q = queue.Queue(maxsize=50); DONE = object()


def producer():
    rng = random.Random(a.seed)
    prev_t = 0.0
    for i, r in enumerate(ev.itertuples()):
        if a.speed > 0:
            time.sleep(max(r.game_seconds_elapsed - prev_t, 0) / a.speed)
        prev_t = max(prev_t, r.game_seconds_elapsed)
        if i == a.delay_at:
            time.sleep(a.delay_sec)  # test: gecikme
        if a.drop_rate > 0 and i < len(ev) - 1 and rng.random() < a.drop_rate:
            continue  # test: eksik olay (son olay hiç düşürülmez)
        q.put(r)
    q.put(DONE)


threading.Thread(target=producer, daemon=True).start()
print(f"{g.away_abbrev} @ {g.home_abbrev}  {g.game_date}  spread(ev sahibi)={spread:+.1f}  hız={a.speed}x")
print('Not: gösterilen değerler olasılıktır, kesin sonuç değildir.')
if spread_warning:
    print('UYARI:', spread_warning)
if a.sim:
    print('Bu maç üretildi, gerçek bir maç değil; olay metinleri genel ifadelerdir.')

fs = FeedState()
history, recent_warnings = [], []
last_wall = time.monotonic()
stale_reported = False
state = None


def write_state(stale, age):
    json.dump({'game_id': a.game, 'home': g.home_abbrev, 'away': g.away_abbrev, 'synthetic': a.sim, 'latest': state,
               'n_events': len(history), 'n_rejected': fs.n_rejected, 'n_warnings': fs.n_warnings,
               'data_age_sec': round(age, 1), 'stale': stale, 'spread_missing': spread_warning is not None,
               'warnings_recent': recent_warnings[-5:]},
              open(a.out, 'w', encoding='utf-8'), ensure_ascii=False)


while True:
    try:
        r = q.get(timeout=1.0)
    except queue.Empty:
        age = data_age(last_wall, time.monotonic())
        if is_stale(age, a.stale_after):
            if not stale_reported:
                msg = f'{age:.0f} sn\'dir yeni veri gelmedi: gösterilen olasılık güncel olmayabilir.'
                print('UYARI:', msg); recent_warnings.append(msg); stale_reported = True
            if state is not None:
                write_state(True, age)
        continue
    if r is DONE:
        break
    last_wall = time.monotonic()
    if stale_reported:
        print('Veri akışı yeniden başladı.'); stale_reported = False
    ok, warns = check_event(fs, r.home_score, r.away_score, r.period_number, r.game_seconds_elapsed,
                            r.start_game_seconds_remaining, seq=r.game_play_number)
    for w in warns:
        print('UYARI:', w); recent_warnings.append(w)
    if not ok:
        continue
    p = predict(model, fs.home - fs.away, fs.secs_left, fs.period > 4, spread)
    state = {'period': fs.period, 'clock': r.clock_display_value, 'home': fs.home, 'away': fs.away,
             'p_home_win': round(p, 4), 'event': r.type_text}
    history.append(state)
    write_state(False, 0.0)
    print(f"P{state['period']} {state['clock']:>5}  {g.away_abbrev} {state['away']:3d} - {state['home']:3d} {g.home_abbrev}  "
          f"P({g.home_abbrev} kazanır)={p:5.1%}  {state['event']}")
print(f"Bitti. Son skor {g.away_abbrev} {g.away_final} - {g.home_final} {g.home_abbrev}; son olasılık {history[-1]['p_home_win']:.1%}; {'üretilen sonuç' if a.sim else 'gerçek'}: "
      f"{'ev sahibi kazandı' if g.home_win_final else 'deplasman kazandı'}")
print(f"Kabul edilen olay: {fs.n_accepted}, atlanan: {fs.n_rejected}, uyarı: {fs.n_warnings}")
