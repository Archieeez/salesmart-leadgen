"""
ekspor_csv.py
=============
Ekspor isi database ke CSV supaya perubahannya bisa dibaca lewat git.

KENAPA FILE INI ADA:
    README sudah lama menyebut aturannya: "Karena git tidak bisa menampilkan
    perbedaan file binary, isi database juga diekspor ke CSV agar
    perubahannya bisa dibaca lewat riwayat commit."

    Tapi tidak ada skrip yang melakukannya — ekspornya dibuat manual. Aturan
    yang bergantung pada ingatan manusia pasti melenceng: begitu satu tabel
    lupa diekspor, riwayat commit-nya berbohong tanpa ada yang tahu.

    File ini membuat aturan itu bisa dijalankan.

YANG TIDAK DIEKSPOR:
    Tabel `halaman_bukti` sengaja dilewati. Isinya teks mentah situs orang
    (ratusan ribu karakter), bukan hasil kerja, dan bisa dibuat ulang kapan
    saja dengan panen_bukti.py. Tempatnya di bukti.db yang tidak dilacak git.

Pakai:
    python src/ekspor_csv.py
"""

import csv
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
DB = DATA / "leads.db"

# tabel -> (nama file, kolom yang diekspor, urutan)
#
# Urutan baris HARUS sama dengan ekspor manual yang sudah ada di repo
# (berdasarkan nama). Sekali urutannya berubah, seluruh 991 baris terlihat
# berubah padahal datanya sama persis — dan diff yang seharusnya terbaca
# jadi tidak berguna.
#
# Kolom stempel waktu (discovered_at, diambil_pada, dinilai_pada) sengaja
# DIBUANG dari ekspor. Kalau ikut, tiap kali skrip dijalankan ulang seluruh
# baris terlihat berubah padahal datanya sama — riwayat commit jadi penuh
# derau dan perubahan yang sungguhan malah tenggelam.
EKSPOR = {
    "leads": (
        "leads_export.csv",
        ["osm_id", "name", "category", "city", "address", "phone",
         "website", "latitude", "longitude"],
        "name",
    ),
    "leads_arsip": (
        "leads_arsip_export.csv",
        ["osm_id", "name", "category", "city", "phone", "alasan"],
        "name",
    ),
    "kontak_web": (
        "kontak_web_export.csv",
        ["nama", "website", "telepon", "kelas_kontak", "status",
         "semua_nomor", "sumber_halaman", "sumber_discovery"],
        "nama",
    ),
    "kebutuhan": (
        "kebutuhan_export.csv",
        ["nama", "website", "dist_model", "field_sales", "scale",
         "industry_fit", "need_score", "catatan", "model"],
        "need_score DESC, nama",
    ),
}


def tabel_ada(con, nama: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nama,)
    ).fetchone())


def main():
    if not DB.exists():
        print(f"Database tidak ditemukan: {DB}")
        raise SystemExit(1)

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    for tabel, (berkas, kolom, urut) in EKSPOR.items():
        if not tabel_ada(con, tabel):
            print(f"  {tabel:<16} dilewati — tabel belum ada")
            continue

        baris = con.execute(
            f"SELECT {', '.join(kolom)} FROM {tabel} ORDER BY {urut}"
        ).fetchall()

        tujuan = DATA / berkas
        with open(tujuan, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(kolom)
            for r in baris:
                w.writerow([r[k] for k in kolom])

        print(f"  {tabel:<16} {len(baris):>5} baris -> {berkas}")

    if tabel_ada(con, "halaman_bukti"):
        n = con.execute("SELECT COUNT(*) FROM halaman_bukti").fetchone()[0]
        print(f"\n  CATATAN: halaman_bukti ({n} baris) masih ada di leads.db.")
        print("  Tabel itu tidak diekspor dan tidak seharusnya di-commit.")
        print("  Pindahkan dengan: python src/pindah_bukti.py")

    con.close()
    print("\nSelesai.")


if __name__ == "__main__":
    sys.exit(main())
