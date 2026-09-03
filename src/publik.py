"""
publik.py
=========
Satu tempat yang memutuskan: baris ini boleh terbit ke publik atau tidak.

KENAPA MODUL INI ADA, dan kenapa ia keras:
    BPS menjawab 3 Sep 2026 bahwa nama dan alamat perusahaan dari
    Direktori Industri Manufaktur boleh dimanfaatkan tanpa izin tertulis
    -- karena larangan pada terbitannya menyasar **reproduksi/penerbitan
    kembali publikasi**, bukan pemakaian isinya.

    Kalimat yang sama menetapkan batasnya. Repo ini PUBLIK: `data/*.csv`
    dilacak git dan `docs/*.html` tayang di GitHub Pages. Menaruh baris
    berasal-BPS ke sana adalah persis penerbitan kembali yang dilarang.

    Bryan juga sudah menyanggupinya tertulis kepada BPS. Jadi ini bukan
    kehati-hatian yang dipilih sendiri; ini garis antara yang diizinkan
    dan yang dilarang.

    Aturan yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa
    ada yang sengaja melanggarnya. Karena itu modul ini bukan cuma
    menyediakan penyaring -- ia juga PEMERIKSA yang bisa dijalankan dan
    GAGAL dengan berisik.

CARA DIPAKAI:
    from publik import boleh_terbit
    if not boleh_terbit(baris_sumber): lewati

    python src/publik.py        # periksa seluruh keluaran; exit 1 kalau bocor
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Sumber yang isinya TIDAK BOLEH ikut terbit. Dicocokkan sebagai awalan,
# supaya "bps-direktori-manufaktur-2025" dan "bps-direktori-sumut-2023"
# ikut tertangkap tanpa perlu didaftar satu per satu.
SUMBER_DILINDUNGI = ("bps",)

# Berkas yang BENAR-BENAR terbit: dilacak git di repo publik, atau tayang
# lewat GitHub Pages.
KELUARAN_PUBLIK = [
    "data/leads_export.csv",
    "data/leads_arsip_export.csv",
    "data/kontak_web_export.csv",
    "data/kebutuhan_export.csv",
    "docs/index.html",
    "docs/teknis.html",
    "docs/agen.html",
]

# Database kerja untuk baris berasal-BPS. TIDAK dilacak git, sama seperti
# bukti.db. Dipisah supaya batasnya struktural, bukan bergantung pada
# ingatan orang yang menulis query berikutnya.
DB_BPS = BASE / "data" / "bps.db"


def boleh_terbit(sumber) -> bool:
    """False kalau baris dari sumber ini tidak boleh masuk berkas publik."""
    s = (sumber or "").strip().lower()
    return not s.startswith(SUMBER_DILINDUNGI)


def _norm(nama: str) -> str:
    s = (nama or "").upper()
    s = re.sub(r"\b(PT|CV|TBK|PERSERO|INDONESIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _nama_dari(db: Path, sql: str) -> set:
    if not db.exists():
        return set()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {_norm(r[0]) for r in con.execute(sql) if r[0]}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


def nama_dilindungi() -> set:
    """Nama yang keberadaannya di daftar kita HANYA berasal dari BPS.

    Perusahaan yang juga kita kenal dari sumber lain tidak dilindungi:
    keberadaannya tidak berasal dari publikasi itu, jadi menerbitkannya
    bukan menerbitkan ulang publikasi itu.

    Dipakai hanya sebagai jaring kedua. Pemeriksaan utama membaca ASAL
    USUL per baris, bukan mencocokkan nama -- lihat periksa().
    """
    bps = _nama_dari(DB_BPS, "SELECT nama FROM perusahaan_bps")
    if not bps:
        return set()
    lain = set()
    dbl = BASE / "data" / "leads.db"
    lain |= _nama_dari(dbl, "SELECT name FROM leads")
    lain |= _nama_dari(dbl, "SELECT nama FROM leads_arsip")
    lain |= _nama_dari(dbl, "SELECT nama FROM kontak_web")
    lain |= _nama_dari(dbl, "SELECT nama FROM kebutuhan")
    for csv_nama in ("companies_scored.csv", "companies_prioritas.csv"):
        f = BASE / "data" / csv_nama
        if f.exists():
            import csv as _csv
            with open(f, encoding="utf-8") as fh:
                for r in _csv.DictReader(fh):
                    n = r.get("company_name") or r.get("nama") or ""
                    if n:
                        lain.add(_norm(n))
    return {n for n in bps if n and n not in lain}


def _dilacak_git(jalur: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", jalur],
                       cwd=BASE, capture_output=True, text=True)
    return r.returncode == 0


def _asal_bps_di_db() -> dict:
    """Berapa baris ber-ASAL BPS di tiap tabel yang ikut terbit.

    Ini pemeriksaan UTAMA, dan sengaja tidak mencocokkan nama sama
    sekali. Percobaan pertama (3 Sep 2026) memindai teks berkas publik
    dan mencari nama yang ada di bps.db. Hasilnya tujuh "kebocoran" yang
    semuanya SALAH:

      - 'SAHABAT' cocok sebagai potongan di dalam nama lain mana pun
      - 'NUTRIFOOD' masuk pipeline dari GAPMMI, bukan dari BPS; ia
        kebetulan juga tercantum di direktori

    Pelajarannya sama dengan yang sudah mahal di proyek ini: yang
    diperiksa harus PENGAMATAN, bukan kesimpulan. Asal-usul sebuah baris
    adalah fakta yang dicatat waktu baris itu masuk; kemiripan nama cuma
    dugaan. Dan gerbang yang sering salah pada akhirnya dimatikan orang.
    """
    dbl = BASE / "data" / "leads.db"
    if not dbl.exists():
        return {}
    con = sqlite3.connect(f"file:{dbl}?mode=ro", uri=True)
    hasil = {}
    for tabel, kolom in (("leads", "source"),
                         ("leads_arsip", "source"),
                         ("kontak_web", "sumber_discovery"),
                         ("kebutuhan", "model")):
        try:
            n = con.execute(
                f"SELECT count(*) FROM {tabel} "
                f"WHERE lower(COALESCE({kolom},'')) LIKE 'bps%'").fetchone()[0]
            if n:
                hasil[tabel] = n
        except sqlite3.Error:
            pass
    con.close()
    return hasil


def periksa() -> list:
    """Cari kebocoran. Return daftar masalah; kosong berarti aman."""
    masalah = []

    # 1. UTAMA: adakah baris ber-asal BPS di tabel yang ikut terbit?
    for tabel, n in _asal_bps_di_db().items():
        masalah.append(
            f"tabel {tabel} di leads.db memuat {n} baris ber-asal BPS. "
            "leads.db dilacak git dan diekspor ke CSV publik; pindahkan "
            "ke data/bps.db atau tandai supaya tidak ikut terbit.")

    # 2. leads.db tidak boleh dilacak git begitu ia memuat baris BPS.
    #    Berkas biner tidak bisa disaring sebagian: ia memuatnya atau
    #    tidak.
    if masalah and _dilacak_git("data/leads.db"):
        masalah.append(
            "data/leads.db DILACAK GIT sementara ia memuat baris BPS. "
            "Keluarkan dari git (git rm --cached) sebelum commit "
            "berikutnya.")

    return masalah


def dugaan() -> list:
    """Kecocokan NAMA yang mungkin -- keterangan, BUKAN penghenti.

    Sengaja dipisah dari periksa() dan sengaja tidak pernah menggagalkan
    ekspor. Pencocokan nama di sini terbukti sering salah, dan sebabnya
    bukan bisa ditambal dengan ambang yang lebih ketat:

      'SAHABAT'                     cocok sebagai potongan nama lain
      'NUTRIFOOD'                   masuk dari GAPMMI, bukan dari BPS
      'ASAHIMAS FLAT GLASS'         ada di leads dari OSM, tapi tercatat
                                    "Asahimas Flat Glass (Flat Glass)"
      'GARUDAFOOD PUTRA PUTRI JAYA' ada dari GAPMMI sebagai "Garudafood"

    Dua nama untuk perusahaan yang sama tidak bisa dipastikan sama dari
    ejaannya, dan memaksakannya berarti menuduh kebocoran yang tidak
    terjadi. Gerbang yang salah tiga kali tiap jalan akan dimatikan
    orang, lalu kebocoran yang SUNGGUHAN ikut lewat.

    Yang menjaga garisnya adalah periksa(), yang membaca asal-usul baris
    -- fakta yang dicatat saat baris itu masuk, bukan dugaan dari nama.
    """
    hasil = []
    terlindungi = {n for n in nama_dilindungi()
                   if len(n) >= 18 and len(n.split()) >= 3}
    if not terlindungi:
        return hasil
    for jalur in KELUARAN_PUBLIK:
        f = BASE / jalur
        if not f.exists():
            continue
        isi = _norm(f.read_text(encoding="utf-8", errors="replace"))
        kena = [n for n in terlindungi if n in isi]
        if kena:
            hasil.append(f"{jalur}: {len(kena)} nama mirip, mis. "
                         f"{kena[0][:46]!r}")
    return hasil


def main():
    terlindungi = nama_dilindungi()
    print(f"Sumber terlindungi : {', '.join(SUMBER_DILINDUNGI)}*")
    print(f"Database BPS       : "
          f"{'ada' if DB_BPS.exists() else 'belum ada'} ({DB_BPS.name})")
    print(f"Nama terlindungi   : {len(terlindungi)}")
    print()
    d = dugaan()
    if d:
        print("Keterangan (BUKAN kebocoran; pencocokan nama memang sering "
              "salah, lihat dugaan() di src/publik.py):")
        for x in d:
            print(f"  ~ {x}")
        print()

    masalah = periksa()
    if not masalah:
        print("AMAN. Tidak ada baris ber-asal BPS di keluaran publik.")
        return
    print(f"BOCOR — {len(masalah)} masalah:")
    for m in masalah:
        print(f"  - {m}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
