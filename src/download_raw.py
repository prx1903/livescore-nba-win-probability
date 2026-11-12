"""
hoopR-nba-data ham play-by-play dosyalarını indirir (sportsdataverse/hoopR-nba-data, ESPN kaynaklı).

Kullanım:
  python src/download_raw.py --out data/raw --from 2013 --to 2026
  python src/download_raw.py --out data/raw --from 2013 --to 2026 --dry-run    # yalnızca HEAD isteği atar, indirmez

Davranış:
  - data/raw/MANIFEST.csv bu projede kullanılan dosyaların boyut ve SHA-256 değerlerini tutar.
  - Dosya zaten varsa ve boyutu MANIFEST ile aynıysa atlanır.
  - İndirilen dosyanın SHA-256'sı MANIFEST ile karşılaştırılır. Fark çıkarsa uyarı verilir:
    yukarı akış dosyaları güncellenir (özellikle son sezon), bu durumda sonuçlar README'deki sayılardan sapabilir.
  - İstekler arasında 1 sn beklenir.
Dosya yılı sezonun BİTİŞ yılıdır (2024 = 2023-24). Yeniden dağıtım koşulları için data/README.md'ye bakın.
"""
import argparse, csv, hashlib, os, sys, time
import requests

BASE = 'https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/pbp/parquet/play_by_play_{y}.parquet'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='data/raw')
    ap.add_argument('--from', dest='y0', type=int, default=2013)
    ap.add_argument('--to', dest='y1', type=int, default=2026)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--base', default=BASE, help='URL şablonu; {y} dosya yılıyla değiştirilir (test için)')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    manifest = {}
    mpath = os.path.join(a.out, 'MANIFEST.csv')
    if os.path.exists(mpath):
        with open(mpath, newline='', encoding='utf-8') as f:
            manifest = {r['file']: r for r in csv.DictReader(f)}

    failed = []
    for y in range(a.y0, a.y1 + 1):
        name = f'play_by_play_{y}.parquet'
        dest = os.path.join(a.out, name)
        url = a.base.format(y=y)
        exp = manifest.get(name)
        if os.path.exists(dest) and exp and os.path.getsize(dest) == int(exp['bytes']):
            print(f'{name}: var, boyut MANIFEST ile aynı, atlandı')
            continue
        try:
            if a.dry_run:
                r = requests.head(url, allow_redirects=True, timeout=30)
                print(f'{name}: HTTP {r.status_code}, content-length={r.headers.get("content-length")}, beklenen={exp["bytes"] if exp else "?"}')
                if r.status_code != 200:
                    failed.append(name)
                continue
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                tmp = dest + '.part'
                with open(tmp, 'wb') as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(tmp, dest)
            size, digest = os.path.getsize(dest), sha256(dest)
            if exp and (size != int(exp['bytes']) or digest != exp['sha256']):
                print(f'{name}: indirildi ({size} bayt) UYARI: MANIFEST ile farklı (yukarı akış güncellenmiş olabilir)')
            else:
                print(f'{name}: indirildi ({size} bayt), MANIFEST ile aynı' if exp else f'{name}: indirildi ({size} bayt), MANIFEST kaydı yok')
        except requests.RequestException as e:
            print(f'{name}: HATA {e}')
            failed.append(name)
        time.sleep(1.0)
    if failed:
        print('Başarısız:', failed)
        sys.exit(1)


if __name__ == '__main__':
    main()
