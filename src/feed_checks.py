"""
Canlı veri akışı kontrolleri: eksik, bozuk veya geciken veriyi yakalar.

Model yalnızca kabul edilen son duruma (skor, periyot, kalan süre) göre olasılık hesaplar.
Bir olay reddedilirse ya da şüpheliyse, neden olduğu sade bir uyarı metniyle döner;
arayüz bu metni kullanıcıya gösterir.

Kurallar:
  - Skor, periyot, süre alanlarından biri boşsa olay atlanır.
  - Olay sıra numarası (seq) verilirse: önceki numaradan küçük ya da eşitse olay tekrar/sıra dışı sayılıp atlanır;
    araya boşluk girerse olay kabul edilir ve kaç olayın eksik olduğu bildirilir.
  - Oyun saati geri giderse olay atlanır (sıra dışı ya da bozuk olay).
  - Skor gerilerse önceki skor korunur ve uyarı verilir (veri hattındaki "çalışan maksimum" kuralıyla aynı).
    Not: gerçek bir hakem düzeltmesi de skoru düşürebilir; bu durumda uyarı kullanıcıya gösterilir.
  - Periyot birden fazla atlarsa ya da iki olay arasında MAX_GAP_GAME_SEC'ten uzun oyun süresi geçerse
    olay kabul edilir ama "arada olay eksik olabilir" uyarısı verilir.
  - Gerçek saatle STALE_AFTER_SEC saniyeden uzun süre yeni olay gelmezse veri "bayat" sayılır.
  - Maç öncesi çizgi (spread) yoksa 0 (denk maç) kullanılır ve bu açıkça bildirilir.
"""
import math
from dataclasses import dataclass, field

MAX_GAP_GAME_SEC = 120.0
STALE_AFTER_SEC = 30.0


@dataclass
class FeedState:
    home: int = 0
    away: int = 0
    period: int = 1
    elapsed: float = 0.0          # oyun saatiyle geçen süre (sn), normal süre 0-2880, her uzatma +300
    secs_left: float = 2880.0     # normal sürede kalan sn; uzatmada o uzatmada kalan sn
    n_accepted: int = 0
    n_rejected: int = 0
    n_warnings: int = 0
    last_seq: int = 0


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def check_event(state, home, away, period, elapsed, secs_left, seq=None):
    """Yeni olayı kontrol eder. Dönüş: (kabul_edildi, uyarılar). Kabul edilirse state güncellenir."""
    if any(_missing(v) for v in (home, away, period, elapsed, secs_left)):
        state.n_rejected += 1
        return False, ['Olayda eksik alan var, atlandı.']
    home, away, period = int(home), int(away), int(period)
    elapsed, secs_left = float(elapsed), float(secs_left)
    warnings = []
    if seq is not None and not _missing(seq):
        seq = int(seq)
        if state.last_seq and seq <= state.last_seq:
            state.n_rejected += 1
            return False, [f'Olay tekrar etti ya da sırası bozuk (sıra {state.last_seq} -> {seq}), atlandı.']
        if state.last_seq and seq > state.last_seq + 1:
            warnings.append(f'{seq - state.last_seq - 1} olay eksik (sıra {state.last_seq} -> {seq}); skor ve süre son gelen olaydan alındı.')
    if state.n_accepted and elapsed < state.elapsed - 0.5:
        state.n_rejected += 1
        return False, [f'Oyun saati geri gitti ({state.elapsed:.0f} -> {elapsed:.0f} sn), olay atlandı.']
    if home < state.home or away < state.away:
        warnings.append(f'Skor geriledi ({state.away}-{state.home} -> {away}-{home}), önceki skor korundu.')
        home, away = max(home, state.home), max(away, state.away)
    if period > state.period + 1:
        warnings.append(f'Periyot {state.period} -> {period} atladı, arada olay eksik olabilir.')
    if state.n_accepted and elapsed - state.elapsed > MAX_GAP_GAME_SEC:
        warnings.append(f'{elapsed - state.elapsed:.0f} sn oyun süresince olay gelmedi, veri eksik olabilir.')
    state.home, state.away, state.period = home, away, period
    state.elapsed, state.secs_left = elapsed, secs_left
    state.n_accepted += 1
    if seq is not None and not _missing(seq):
        state.last_seq = seq
    state.n_warnings += len(warnings)
    return True, warnings


def data_age(last_event_wall, now_wall):
    """Son olaydan bu yana geçen gerçek süre (sn)."""
    return max(0.0, now_wall - last_event_wall)


def is_stale(age_sec, stale_after=STALE_AFTER_SEC):
    return age_sec > stale_after


def spread_or_default(spread):
    """Dönüş: (kullanılacak çizgi, uyarı ya da None)."""
    if _missing(spread):
        return 0.0, 'Maç öncesi çizgi (güç farkı) yok: iki takım denk kabul edildi, olasılık yalnızca skordan geliyor.'
    return float(spread), None
