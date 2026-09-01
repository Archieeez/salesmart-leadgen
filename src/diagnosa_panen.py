"""
diagnosa_panen.py
=================
Cari tahu KENAPA sebuah situs pulang dengan nol halaman.

KENAPA MODUL INI ADA:
    panen_log mencatat `jml_halaman`, jadi kita tahu 81 dari 189 situs
    gagal — tapi tidak tahu sebabnya. Ketiga sebab di bawah ini kelihatan
    identik di log (sama-sama nol), padahal penanganannya bertolak
    belakang:

      situs mati        -> buang, jangan dicoba lagi selamanya
      dirender JS       -> butuh keputusan headless browser
      dilarang robots   -> tutup buku, memang tidak boleh

    Tanpa memisahkan ketiganya, "panen ulang" berarti menabrak tembok yang
    sama berulang kali, dan diskusi headless browser tidak punya angka.

INI DIAGNOSIS, BUKAN PANEN:
    Modul ini hanya mengambil SATU halaman per situs (homepage) untuk
    menentukan sebab. Tidak menulis apa pun ke halaman_bukti. Hasilnya
    masuk ke kolom `sebab` di panen_log dan ke sebuah CSV.

    Karena cuma satu halaman per domain, ia jauh lebih ringan daripada
    panen penuh — tapi JEDA_ANTAR_SITUS tetap dipatuhi, dan robots.txt
    diperiksa sebelum request apa pun dikirim.

BISA DILANJUTKAN:
    Situs yang sudah punya `sebab` dilewati. Jadi kalau prosesnya putus di
    tengah (batas waktu tugas latar belakang ~10 menit), jalankan lagi
    perintah yang sama dan ia menyambung dari tempat berhenti.

Pakai:
    python diagnosa_panen.py --cache ../data/.cache_html
    python diagnosa_panen.py --ulangi          # abaikan sebab lama
    python diagnosa_panen.py --ringkas         # cuma tampilkan rekap
"""

import argparse
import csv
import sqlite3
import sys
import time
from pathlib import Path

import web
from web import JEDA_ANTAR_SITUS, ambil_html, ambil_teks_polos, boleh_ambil, log

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"

# Di bawah ini, halaman dianggap cangkang tanpa teks. Angkanya sengaja
# sama dengan MIN_PANJANG_TEKS di panen_bukti.py supaya diagnosis dan
# panen memakai garis yang sama.
MIN_TEKS = 200

# Sebab yang mungkin, beserta artinya buat langkah berikutnya.
ARTI = {
    "robots_larang":  "robots.txt melarang - tutup buku, memang tidak boleh",
    "situs_mati":     "domain tidak menjawab - buang dari daftar",
    "http_error":     "server menjawab tapi bukan 200 - kemungkinan pindah/tutup",
    "bukan_html":     "yang dikembalikan bukan halaman HTML",
    "js_render":      "HTML ada tapi teksnya kosong - dirender JavaScript",
    "teks_ada":       "teks sebenarnya ADA - kegagalan panen perlu diperiksa",
}


def pastikan_kolom(con):
    """Tambah kolom sebab kalau panen_log masih versi lama."""
    kolom = {r[1] for r in con.execute("PRAGMA table_info(panen_log)")}
    if "sebab" not in kolom:
        con.execute("ALTER TABLE panen_log ADD COLUMN sebab TEXT")
    if "sebab_detail" not in kolom:
        con.execute("ALTER TABLE panen_log ADD COLUMN sebab_detail TEXT")
    if "didiagnosa_pada" not in kolom:
        con.execute("ALTER TABLE panen_log ADD COLUMN didiagnosa_pada TEXT")
    con.commit()


def daftar_gagal(con, ulangi: bool):
    """Situs yang pernah dicoba tapi tidak menyumbang satu halaman pun."""
    sql = """
        SELECT p.nama_normal, p.nama, p.website
        FROM panen_log p
        WHERE NOT EXISTS (
            SELECT 1 FROM halaman_bukti h WHERE h.nama_normal = p.nama_normal
        )
    """
    if not ulangi:
        sql += " AND (p.sebab IS NULL OR p.sebab = '')"
    sql += " ORDER BY p.nama"
    return con.execute(sql).fetchall()


def diagnosa(website: str) -> tuple[str, str]:
    """Ambil homepage sekali, kembalikan (sebab, detail)."""
    if not website:
        return "situs_mati", "tidak ada alamat situs di log"

    if not boleh_ambil(website):
        return "robots_larang", "robots.txt melarang User-Agent kita"

    html, alasan = ambil_html(website)

    if html is None:
        if alasan.startswith("gagal:"):
            return "situs_mati", alasan
        if alasan.startswith("http "):
            return "http_error", alasan
        if alasan.startswith("bukan html"):
            return "bukan_html", alasan
        return "situs_mati", alasan

    teks = ambil_teks_polos(website) or ""
    n = len(teks.strip())
    if n < MIN_TEKS:
        return "js_render", f"{alasan} -> hanya {n} char teks"
    return "teks_ada", f"{alasan} -> {n} char teks"


def rekap(con):
    baris = con.execute("""
        SELECT COALESCE(NULLIF(sebab,''),'belum_didiagnosa') AS s, COUNT(*)
        FROM panen_log p
        WHERE NOT EXISTS (
            SELECT 1 FROM halaman_bukti h WHERE h.nama_normal = p.nama_normal
        )
        GROUP BY s ORDER BY COUNT(*) DESC
    """).fetchall()
    total = sum(n for _, n in baris)
    print()
    print("=" * 66)
    print(f"SEBAB KEGAGALAN PANEN  ({total} situs nol halaman)")
    print("=" * 66)
    for sebab, n in baris:
        print(f"  {n:>3}  {sebab:<18} {ARTI.get(sebab, '')}")
    return baris


def tulis_csv(con, keluar: Path):
    baris = con.execute("""
        SELECT p.nama, p.website, p.sebab, p.sebab_detail, p.didiagnosa_pada
        FROM panen_log p
        WHERE NOT EXISTS (
            SELECT 1 FROM halaman_bukti h WHERE h.nama_normal = p.nama_normal
        )
        AND p.sebab IS NOT NULL AND p.sebab <> ''
        ORDER BY p.sebab, p.nama
    """).fetchall()
    with open(keluar, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["nama", "website", "sebab", "detail", "didiagnosa_pada"])
        w.writerows(baris)
    print(f"\n  rincian ditulis ke {keluar}  ({len(baris)} baris)")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-bukti", default=str(DATA / "bukti.db"))
    ap.add_argument("--cache", default="",
                    help="folder cache HTML; sangat disarankan supaya situs "
                         "orang tidak kena request ulang")
    ap.add_argument("--keluar", default=str(DATA / "diagnosa_panen.csv"))
    ap.add_argument("--ulangi", action="store_true",
                    help="diagnosa ulang yang sudah punya sebab")
    ap.add_argument("--ringkas", action="store_true",
                    help="jangan ambil apa pun, cuma tampilkan rekap")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    web.setel(verbose=args.verbose, cache_dir=args.cache or None)

    con = sqlite3.connect(args.db_bukti)
    pastikan_kolom(con)

    if args.ringkas:
        rekap(con)
        tulis_csv(con, Path(args.keluar))
        con.close()
        return

    antrian = daftar_gagal(con, args.ulangi)
    if args.limit:
        antrian = antrian[:args.limit]

    print(f"{len(antrian)} situs perlu didiagnosa.\n")

    for i, (nn, nama, website) in enumerate(antrian, 1):
        sebab, detail = diagnosa(website)
        con.execute(
            "UPDATE panen_log SET sebab=?, sebab_detail=?, "
            "didiagnosa_pada=datetime('now') WHERE nama_normal=?",
            (sebab, detail, nn))
        con.commit()   # per baris, supaya putus di tengah tidak hilang
        print(f"[{i}/{len(antrian)}] {nama[:38]:<38} {sebab:<14} {detail[:44]}")
        time.sleep(JEDA_ANTAR_SITUS)

    rekap(con)
    tulis_csv(con, Path(args.keluar))
    con.close()


if __name__ == "__main__":
    main()
