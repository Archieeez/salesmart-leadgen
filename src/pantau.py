"""
pantau.py
=========
Bangkitkan ulang SELURUH dasbor terus-menerus selama agen bekerja, supaya
halamannya hidup tanpa perlu di-push.

    python src/pantau.py            # tiap 4 detik
    python src/pantau.py --jeda 10  # lebih jarang

Lalu buka berkas LOKALNYA, bukan alamat GitHub Pages:

    docs/index.html     antrian + panel agen
    docs/agen.html      riwayat pembaca vs pemeriksa

Halamannya menyisipkan penyegaran otomatis sendiri selama mode ini
jalan, jadi cukup dibuka sekali.

KENAPA GITHUB PAGES TIDAK BISA HIDUP:
    Pages menyajikan berkas statis dari commit terakhir. Ia tidak punya
    cara mengetahui apa yang terjadi di komputer ini. Jadi selama
    halamannya dibuka lewat alamat github.io, satu-satunya cara isinya
    berubah memang push -- dan itu bukan kekurangan yang bisa ditambal
    dari sini, itu memang sifat hosting statis.

    Yang terbit di Pages adalah CUPLIKAN: benar pada saat di-push, dan
    panel agennya sudah tahu diri soal itu (lihat blok data-dibuat di
    buat_antrian.py -- halaman yang basi menulis "status tidak
    diketahui", bukan menebak).

KENAPA TIDAK PAKAI SERVER KECIL SAJA:
    Karena tidak perlu. Ketiga halaman ini berkas biasa tanpa fetch,
    jadi file:// cukup. Menambah server berarti menambah satu proses
    yang bisa mati diam-diam, demi keuntungan nol.
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# buat_antrian dan buat_agen punya mode --pantau sendiri: mereka
# menyisipkan meta refresh ke halamannya. buat_dashboard tidak, dan itu
# disengaja -- dasbor teknis tidak berubah tiap detik.
# (skrip, argumen, tiap berapa putaran)
#
# --segar, BUKAN --pantau: --pantau punya loopnya sendiri dan tidak pernah
# kembali, sehingga pemantau gabungan ini akan menggantung di halaman
# pertama selamanya. Loopnya ada di sini, satu untuk semua.
#
# IRAMA BERBEDA, dan ini bukan penghematan yang dicari-cari:
# buat_dashboard.py membaca bukti.db, dan selama panen bukti berjalan
# berkas itu sedang ditulisi terus. Sekali jalan diukur 35 DETIK -- lebih
# lama dari jeda pemantauannya sendiri, sehingga loopnya tidak akan pernah
# mengejar. Isinya juga tidak berubah tiap detik. Jadi ia ikut, tapi
# jarang.
HALAMAN = [
    ("buat_antrian.py", ["--segar"], 1),
    ("buat_agen.py", ["--segar"], 1),
    # 0 = TIDAK ikut loop, hanya waktu --sekali. Sekali jalan diukur
    # 35 detik selama panen berlangsung -- lebih lama dari jeda
    # pemantauannya sendiri, jadi ia bukan cuma lambat, ia MENGHALANGI
    # dua halaman yang justru ingin dilihat hidup. Dasbor teknis juga
    # bukan halaman yang ditonton saat agen bekerja.
    ("buat_dashboard.py", [], 0),
]


# Berapa putaran gagal BERUNTUN sebelum menyerah. Kegagalan sesaat itu
# WAJAR di sini: pemantau ini justru dipakai selama agen bekerja, dan
# agen yang sedang menulis mengunci database. Berhenti pada kegagalan
# pertama berarti pemantau mati persis di saat ia paling dibutuhkan --
# terjadi 3 Sep 2026 waktu panen bukti sedang mengunci bukti.db.
BATAS_GAGAL_BERUNTUN = 5


def sekali(putaran=0, diam=True):
    """Bangkitkan halaman yang jatah putarannya tiba.

    Return (berhasil, catatan_gagal).
    """
    gagal = []
    for skrip, argumen, tiap in HALAMAN:
        if tiap == 0 or putaran % tiap:
            continue
        r = subprocess.run(
            [sys.executable, str(BASE / "src" / skrip), *argumen],
            cwd=BASE, capture_output=diam, text=True,
            encoding="utf-8", errors="replace")
        if r.returncode != 0:
            pesan = (r.stderr or r.stdout or "").strip().splitlines()
            gagal.append(f"{skrip} (keluar {r.returncode}): "
                         f"{pesan[-1] if pesan else 'tanpa pesan'}")
    return (not gagal), gagal


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jeda", type=float, default=4.0)
    ap.add_argument("--sekali", action="store_true",
                    help="bangkitkan sekali lalu berhenti, tanpa penyegaran")
    args = ap.parse_args()

    if args.sekali:
        for skrip, _, _ in HALAMAN:
            subprocess.run([sys.executable, str(BASE / "src" / skrip)],
                           cwd=BASE)
        return

    print("Memantau. Ctrl+C untuk berhenti.")
    print("Buka berkas ini di peramban (bukan alamat github.io):")
    print(f"  {BASE / 'docs' / 'index.html'}")
    print(f"  {BASE / 'docs' / 'agen.html'}")
    print()
    n, beruntun = 0, 0
    try:
        while True:
            ok, gagal = sekali(n)
            jam = datetime.now().strftime("%H:%M:%S")
            if ok:
                n += 1
                beruntun = 0
                print(f"  [{n}] disegarkan {jam}", flush=True)
            else:
                beruntun += 1
                print(f"  [!] {jam} gagal ({beruntun}/"
                      f"{BATAS_GAGAL_BERUNTUN}): {'; '.join(gagal)}",
                      flush=True)
                if beruntun >= BATAS_GAGAL_BERUNTUN:
                    print("Gagal berturut-turut; berhenti. Ini bukan kunci "
                          "database sesaat, ada yang benar-benar rusak.")
                    return
            time.sleep(args.jeda)
    except KeyboardInterrupt:
        # Bangkitkan sekali lagi TANPA --pantau, supaya halaman yang
        # ditinggalkan berhenti menyegarkan diri dan tidak terus berkedip
        # setelah pemantauan dihentikan.
        print("\nMembangkitkan sekali lagi tanpa penyegaran otomatis...")
        for skrip, _, _ in HALAMAN:
            subprocess.run([sys.executable, str(BASE / "src" / skrip)],
                           cwd=BASE, capture_output=True)
        print("Selesai. Halaman berhenti menyegarkan diri.")


if __name__ == "__main__":
    main()
