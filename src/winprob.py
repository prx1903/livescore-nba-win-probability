"""Baseline modelin tek yerde tanımlı tahmin fonksiyonu (eğitimle aynı özellikler)."""
import json, math

def load_model(path):
    return json.load(open(path, encoding='utf-8'))

def features(margin, secs_left, is_ot, spread):
    """margin = ev sahibi - deplasman; secs_left = normal sürede kalan sn, uzatmada o uzatmada kalan sn;
    spread > 0: ev sahibi favori."""
    return {
        'm_over_sqrt_tl': margin / math.sqrt(secs_left + 1.0),
        'is_ot': 1.0 if is_ot else 0.0,
        'spread_x_tl': spread * (secs_left / 2880.0),
        'spread_x_sqrt_tl': spread * math.sqrt(secs_left / 2880.0),
        'm': float(margin),
    }

def predict(model, margin, secs_left, is_ot, spread):
    """Ev sahibinin kazanma olasiligi. Model turu 'kind' alanindan okunur;
    alan yoksa eski katsayi modeli varsayilir (davranis degismedi)."""
    k = model.get('kind', 'logistic_coeffs') if isinstance(model, dict) else 'logistic_coeffs'
    if k == 'sklearn':
        return float(model['estimator'].predict_proba(_design(model, margin, secs_left, is_ot, spread))[0, 1])
    if k == 'ensemble':
        ps = [predict(m, margin, secs_left, is_ot, spread) for m in model['_members']]
        return float(sum(ps) / len(ps))
    f = features(margin, secs_left, is_ot, spread)
    z = model['intercept'] + sum(c * f[n] for n, c in zip(model['features'], model['coef']))
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# 28 Ekim 2026: tek predict arayuzu. Yukaridaki load_model/features/predict
# imzalari ve davranisi degismedi; asagisi yeni model turlerini ekler.
# Model dosyasi turu 'kind' alanindan okunur:
#   'logistic_coeffs'  -> yukaridaki katsayi sozlugu (varsayilan, eski dosyalar)
#   'sklearn'          -> joblib ile kaydedilmis sklearn modeli + ozellik tarifi
#   'ensemble'         -> uye modellerin olasilik ortalamasi
# sklearn/joblib yalnizca gerektiginde ice aktarilir: eski JSON modeli saf
# standart kutuphaneyle calismaya devam eder.
# ---------------------------------------------------------------------------
import os

def _kind(model):
    if isinstance(model, dict) and 'kind' in model:
        return model['kind']
    return 'logistic_coeffs'

def load(path):
    """Model dosyasini turune gore yukler. JSON ise katsayi modeli, .joblib ise sklearn."""
    if str(path).endswith('.joblib'):
        import joblib
        m = joblib.load(path)
        m['kind'] = m.get('kind', 'sklearn')
        return m
    m = load_model(path)
    if _kind(m) == 'ensemble':
        base = os.path.dirname(os.path.abspath(path))
        m['_members'] = [load(p if os.path.isabs(p) else os.path.join(base, p)) for p in m['members']]
    return m

def _design(model, margin, secs_left, is_ot, spread):
    f = features(margin, secs_left, is_ot, spread)
    f['m'] = float(margin); f['tl'] = float(secs_left)
    f['spread'] = float(spread); f['is_ot'] = 1.0 if is_ot else 0.0
    return [[f[c] for c in model['input_features']]]

def predict_state(model, state):
    """state: {'margin','secs_left','is_ot','spread'}. Tum model turlerinde ayni cagri."""
    return predict(model, state['margin'], state['secs_left'], state['is_ot'], state['spread'])

def predict_many(model, states):
    """Birden cok durum icin olasilik listesi. Bos liste icin bos liste doner."""
    return [predict_state(model, s) for s in states]
