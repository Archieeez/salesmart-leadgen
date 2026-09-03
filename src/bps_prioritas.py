"""
bps_prioritas.py
================
Susun daftar pendek dari 35.129 perusahaan direktori BPS: yang layak
dibayar perhatian lebih dulu.

    python src/bps_prioritas.py            # lihat
    python src/bps_prioritas.py --tulis    # simpan ke bps.db

MASALAH YANG DISELESAIKAN:
    Direktori memberi 35 ribu nama. Langit-langit pembacaan agen ~25
    perusahaan per sesi, jadi membacanya semua butuh ~1.300 sesi. Menambah
    nama tidak menyelesaikan apa pun kalau tidak ada cara memilih.

DUA SINYAL, KEDUANYA GRATIS — tidak perlu membuka satu situs pun:

1. KELOMPOK INDUSTRI. Direktorinya terbagi 24 kelompok (lihat
   bps_ekstrak.BAGIAN). Tiga di antaranya vertikal inti Salesmart:
   makanan, minuman, farmasi. 21 sisanya B2B berat yang industry_fit-nya
   rendah. 35.129 -> 8.602.

2. JUMLAH PROVINSI TEMPAT PABRIKNYA. Perusahaan dengan pabrik di
   beberapa provinsi PUNYA operasi distribusi lintas wilayah menurut
   definisinya sendiri -- itu bukan dugaan dari nama atau dari kata-kata
   pemasaran, melainkan konsekuensi dari alamat yang tercetak di
   direktori resmi. 8.602 -> 236.

KENAPA PROVINSI DAN BUKAN JUMLAH PABRIK:
    Dua pabrik di kabupaten bertetangga bisa jadi satu kompleks yang
    terdaftar dua kali. Dua pabrik di dua provinsi tidak mungkin begitu.
    Provinsi adalah ukuran yang lebih sulit dipalsukan oleh cara
    pendataan.

YANG BELUM DIPUNYAI DAFTAR INI: alamat situs web. Direktori BPS tidak
memuatnya, sedangkan agen pembaca butuh situs untuk dibaca. Mencarikan
situs untuk tiap kandidat adalah pekerjaan berikutnya, dan itu sebabnya
daftar ini disimpan -- supaya pencarian situs berjalan atas daftar yang
sudah mengerucut, bukan atas 35 ribu.
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import bps_ekstrak as bx  # noqa: E402

DB_BPS = BASE / "data" / "bps.db"
DB = BASE / "data" / "leads.db"
MIN_PROVINSI = 2

DDL = """
CREATE TABLE IF NOT EXISTS prioritas_bps (
    kunci       TEXT PRIMARY KEY,   -- nama yang sudah dinormalkan
    nama        TEXT,               -- nama seperti tercetak di direktori
    bagian      TEXT,
    provinsi    INTEGER,            -- berapa provinsi punya pabriknya
    daftar_provinsi TEXT,
    alamat_contoh   TEXT,
    website     TEXT,               -- diisi belakangan; direktori tak punya
    catatan     TEXT
);
"""


def kunci(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"\b(PT|CV|UD|TBK|PERSERO|PERUM|INDONESIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sudah_dikenal() -> set:
    """Perusahaan yang sudah ada di pipeline dari sumber mana pun.

    Dikeluarkan dari daftar pendek bukan karena tidak menarik, tapi
    karena sudah punya jalurnya sendiri -- memasukkannya lagi berarti
    mengerjakan dua kali dan menghasilkan dua baris untuk satu
    perusahaan.
    """
    kenal = set()
    if DB.exists():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        for sql in ("SELECT name FROM leads",
                    "SELECT name FROM leads_arsip",
                    "SELECT nama FROM kontak_web",
                    "SELECT nama FROM kebutuhan"):
            try:
                kenal |= {kunci(r[0]) for r in con.execute(sql) if r[0]}
            except sqlite3.Error:
                pass
        con.close()
    for nama in ("companies_scored.csv", "companies_prioritas.csv"):
        f = BASE / "data" / nama
        if f.exists():
            with open(f, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    n = r.get("company_name") or r.get("nama") or ""
                    if n:
                        kenal.add(kunci(n))
    return kenal


def susun():
    prov = re.compile(bx.PROVINSI.pattern)
    con = sqlite3.connect(f"file:{DB_BPS}?mode=ro", uri=True)
    pabrik, contoh = defaultdict(set), {}
    for nama, alamat, bagian in con.execute(
            "SELECT nama, alamat, bagian FROM perusahaan_bps "
            "WHERE bagian IN (?,?,?)", tuple(bx.BAGIAN_INTI)):
        k = kunci(nama)
        if not k:
            continue
        m = prov.search(alamat or "")
        pabrik[k].add(m.group(0) if m else "?")
        contoh.setdefault(k, (nama, bagian, alamat))
    con.close()

    kenal = sudah_dikenal()
    hasil = []
    for k, pset in pabrik.items():
        n = len([p for p in pset if p != "?"])
        if n < MIN_PROVINSI:
            continue
        nama, bagian, alamat = contoh[k]
        hasil.append({
            "kunci": k, "nama": nama, "bagian": bagian, "provinsi": n,
            "daftar_provinsi": "; ".join(sorted(p for p in pset if p != "?")),
            "alamat_contoh": alamat, "website": None,
            "catatan": "sudah ada di pipeline" if k in kenal else "",
        })
    hasil.sort(key=lambda x: (-x["provinsi"], x["nama"]))
    return hasil


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tulis", action="store_true")
    ap.add_argument("--contoh", type=int, default=12)
    args = ap.parse_args()

    if not DB_BPS.exists():
        raise SystemExit("data/bps.db belum ada. Jalankan bps_ekstrak.py.")

    hasil = susun()
    baru = [h for h in hasil if not h["catatan"]]
    print(f"kandidat >= {MIN_PROVINSI} provinsi, vertikal inti : {len(hasil)}")
    print(f"  sudah ada di pipeline                : "
          f"{len(hasil) - len(baru)}")
    print(f"  BELUM disentuh                       : {len(baru)}")
    print()
    for h in baru[:args.contoh]:
        print(f"  {h['provinsi']:>2} prov  {h['nama'][:44]:<46}"
              f"{h['bagian'][:20]}")

    if not args.tulis:
        print("\n(mode lihat; tidak ada yang ditulis. Tambahkan --tulis.)")
        return

    con = sqlite3.connect(DB_BPS)
    con.executescript(DDL)
    con.executemany(
        "INSERT INTO prioritas_bps "
        "(kunci,nama,bagian,provinsi,daftar_provinsi,alamat_contoh,"
        " website,catatan) VALUES "
        "(:kunci,:nama,:bagian,:provinsi,:daftar_provinsi,:alamat_contoh,"
        " :website,:catatan) "
        "ON CONFLICT(kunci) DO UPDATE SET "
        "  provinsi=excluded.provinsi, "
        "  daftar_provinsi=excluded.daftar_provinsi, "
        "  catatan=excluded.catatan",
        hasil)
    con.commit()
    n = con.execute("SELECT count(*) FROM prioritas_bps").fetchone()[0]
    con.close()
    print(f"\nDitulis ke bps.db tabel prioritas_bps; kini {n} baris.")
    print("Kolom `website` sengaja kosong — direktori BPS tidak memuatnya, "
          "dan itu pekerjaan berikutnya.")


if __name__ == "__main__":
    main()
