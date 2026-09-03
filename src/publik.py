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


def nama_dilindungi() -> set:
    """Nama perusahaan yang HANYA diketahui dari sumber terlindungi.

    Perusahaan yang juga ditemukan dari sumber lain (OSM, asosiasi, riset
    manual) TIDAK terlindungi: keberadaannya di daftar kita tidak berasal
    dari publikasi BPS, jadi menerbitkannya bukan menerbitkan ulang
    publikasi itu. Yang dilindungi adalah baris yang keberadaannya
    memang datang dari sana.
    """
    if not DB_BPS.exists():
        return set()
    con = sqlite3.connect(f"file:{DB_BPS}?mode=ro", uri=True)
    try:
        bps = {_norm(r[0]) for r in con.execute(
            "SELECT nama FROM perusahaan_bps")}
    except sqlite3.Error:
        bps = set()
    finally:
        con.close()

    lain = set()
    dbl = BASE / "data" / "leads.db"
    if dbl.exists():
        c = sqlite3.connect(f"file:{dbl}?mode=ro", uri=True)
        try:
            lain = {_norm(r[0]) for r in c.execute(
                "SELECT name FROM leads WHERE COALESCE(source,'') NOT LIKE 'bps%'")}
        except sqlite3.Error:
            pass
        finally:
            c.close()
    return {n for n in bps if n and n not in lain}


def _dilacak_git(jalur: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", jalur],
                       cwd=BASE, capture_output=True, text=True)
    return r.returncode == 0


def periksa() -> list:
    """Cari kebocoran. Return daftar masalah; kosong berarti aman."""
    masalah = []
    terlindungi = nama_dilindungi()

    # 1. leads.db tidak boleh dilacak git begitu ia memuat baris BPS.
    #    Berkas biner tidak bisa disaring sebagian: ia memuatnya atau
    #    tidak. Selama belum ada baris BPS, melacaknya tetap benar.
    if DB_BPS.exists() and _dilacak_git("data/leads.db"):
        con = sqlite3.connect(f"file:{BASE / 'data' / 'leads.db'}?mode=ro",
                              uri=True)
        try:
            n = con.execute("SELECT count(*) FROM leads "
                            "WHERE COALESCE(source,'') LIKE 'bps%'").fetchone()[0]
        except sqlite3.Error:
            n = 0
        finally:
            con.close()
        if n:
            masalah.append(
                f"data/leads.db DILACAK GIT dan memuat {n} baris berasal-BPS. "
                "Berkas biner tidak bisa disaring sebagian — keluarkan dari "
                "git (git rm --cached) sebelum commit berikutnya.")

    # 2. Nama terlindungi tidak boleh muncul di keluaran publik.
    if terlindungi:
        for jalur in KELUARAN_PUBLIK:
            f = BASE / jalur
            if not f.exists():
                continue
            isi = _norm(f.read_text(encoding="utf-8", errors="replace"))
            kena = [n for n in terlindungi if n and len(n) > 6 and n in isi]
            if kena:
                masalah.append(
                    f"{jalur} memuat {len(kena)} nama yang hanya diketahui "
                    f"dari publikasi BPS, mis. {kena[0][:40]!r}")
    return masalah


def main():
    terlindungi = nama_dilindungi()
    print(f"Sumber terlindungi : {', '.join(SUMBER_DILINDUNGI)}*")
    print(f"Database BPS       : "
          f"{'ada' if DB_BPS.exists() else 'belum ada'} ({DB_BPS.name})")
    print(f"Nama terlindungi   : {len(terlindungi)}")
    print()
    masalah = periksa()
    if not masalah:
        print("AMAN. Tidak ada baris berasal-BPS di keluaran publik.")
        return
    print(f"BOCOR — {len(masalah)} masalah:")
    for m in masalah:
        print(f"  - {m}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
