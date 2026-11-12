"""feed_checks.py testleri. Çalıştırma: python -m pytest tests  (pytest yoksa: python tests/test_feed_checks.py)"""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from feed_checks import FeedState, check_event, data_age, is_stale, spread_or_default


def test_normal_olay_kabul():
    s = FeedState()
    ok, w = check_event(s, 2, 0, 1, 20, 2860)
    assert ok and w == [] and (s.home, s.away, s.secs_left) == (2, 0, 2860)


def test_eksik_alan_atlanir():
    s = FeedState()
    ok, w = check_event(s, float('nan'), 0, 1, 20, 2860)
    assert not ok and s.n_rejected == 1 and s.n_accepted == 0


def test_saat_geri_giderse_atlanir_ve_durum_degismez():
    s = FeedState()
    check_event(s, 10, 8, 1, 300, 2580)
    ok, w = check_event(s, 12, 8, 1, 200, 2680)
    assert not ok and s.home == 10 and s.elapsed == 300


def test_skor_gerilerse_onceki_korunur():
    s = FeedState()
    check_event(s, 23, 17, 1, 600, 2280)
    ok, w = check_event(s, 20, 17, 1, 610, 2270)
    assert ok and s.home == 23 and any('geriledi' in x for x in w)


def test_buyuk_bosluk_uyarisi():
    s = FeedState()
    check_event(s, 10, 8, 1, 300, 2580)
    ok, w = check_event(s, 14, 8, 2, 900, 1980)
    assert ok and any('eksik olabilir' in x for x in w)


def test_periyot_atlama_uyarisi():
    s = FeedState()
    check_event(s, 10, 8, 1, 300, 2580)
    ok, w = check_event(s, 40, 38, 3, 1500, 1380)
    assert ok and any('Periyot' in x for x in w)


def test_sira_boslugu_uyarisi():
    s = FeedState()
    check_event(s, 2, 0, 1, 20, 2860, seq=1)
    ok, w = check_event(s, 4, 0, 1, 40, 2840, seq=4)
    assert ok and any('2 olay eksik' in x for x in w)


def test_tekrar_eden_olay_atlanir():
    s = FeedState()
    check_event(s, 2, 0, 1, 20, 2860, seq=5)
    ok, w = check_event(s, 2, 0, 1, 20, 2860, seq=5)
    assert not ok and s.n_rejected == 1


def test_bayat_veri():
    assert not is_stale(data_age(100.0, 110.0), 30)
    assert is_stale(data_age(100.0, 140.5), 30)


def test_cizgi_yoksa_uyari():
    v, w = spread_or_default(float('nan'))
    assert v == 0.0 and w is not None
    v, w = spread_or_default(-4.5)
    assert v == -4.5 and w is None


if __name__ == '__main__':
    n = 0
    for name, f in list(globals().items()):
        if name.startswith('test_') and callable(f):
            f(); n += 1
    print(f'{n} test geçti')
