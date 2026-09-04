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
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
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
         "industry_fit", "need_score", "bukti_kuat", "status_nilai",
         "penanda", "catatan", "model"],
        "status_nilai, need_score DESC, nama",
    ),
}


import publik  # noqa: E402


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

        # Penyaring terbit ada DI QUERY, bukan sesudahnya. Kalau baris
        # terlarang ikut terbaca lalu dibuang waktu menulis, satu
        # `continue` yang lupa cukup untuk menerbitkannya — dan berkasnya
        # tetap terlihat wajar. Lihat publik.klausa().
        baris = con.execute(
            f"SELECT {', '.join(kolom)} FROM {tabel} "
            f"WHERE {publik.klausa(tabel)} ORDER BY {urut}"
        ).fetchall()
        semua = con.execute(f"SELECT count(*) FROM {tabel}").fetchone()[0]
        ditahan = semua - len(baris)

        tujuan = DATA / berkas
        with open(tujuan, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(kolom)
            for r in baris:
                w.writerow([r[k] for k in kolom])

        # Jumlah yang DITAHAN ikut dicetak. Penyaring yang bekerja diam-diam
        # tidak bisa dibedakan dari penyaring yang membuang terlalu banyak.
        tahan = f"  ({ditahan} ditahan, tidak boleh terbit)" if ditahan else ""
        print(f"  {tabel:<16} {len(baris):>5} baris -> {berkas}{tahan}")

    if tabel_ada(con, "halaman_bukti"):
        n = con.execute("SELECT COUNT(*) FROM halaman_bukti").fetchone()[0]
        print(f"\n  CATATAN: halaman_bukti ({n} baris) masih ada di leads.db.")
        print("  Tabel itu tidak diekspor dan tidak seharusnya di-commit.")
        print("  Pindahkan dengan: python src/pindah_bukti.py")

    con.close()
    print("\nSelesai.")

    # Gerbang terakhir, dan sengaja di sini: berkas publik baru saja
    # ditulis, jadi inilah satu-satunya titik yang tahu isinya persis.
    # Kalau bocor, ia exit 1 — lihat gerbang_publik() di bawah.
    gerbang_publik()



def gerbang_publik():
    """Tolak jalan kalau ada baris berasal-BPS di keluaran publik.

    Ditaruh SESUDAH penulisan, bukan sebelum: yang perlu diperiksa adalah
    berkas yang baru saja ditulis, bukan yang lama. Kalau bocor, exit 1
    supaya jalur apa pun yang memanggilnya ikut berhenti dan tidak ada
    yang diam-diam melanjutkan ke commit.

    Lihat src/publik.py untuk kenapa garis ini bukan kehati-hatian
    pilihan sendiri.
    """
    masalah = publik.periksa()
    if not masalah:
        return
    print("\nEKSPOR DITOLAK — ada yang tidak boleh terbit:")
    for m in masalah:
        print(f"  - {m}")
    print("\nBerkas sudah ditulis, TAPI JANGAN DI-COMMIT sebelum ini beres.")
    raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
