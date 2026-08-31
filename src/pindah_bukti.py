"""
pindah_bukti.py
===============
Pindahkan tabel `halaman_bukti` dari leads.db ke bukti.db.

KENAPA DIPISAH:
    `halaman_bukti` menyimpan teks mentah halaman situs perusahaan —
    589.470 karakter untuk 27 perusahaan saja. Itu membuat leads.db
    melonjak dari 327 KB jadi 1 MB, dan akan naik terus tiap panen.

    Yang lebih penting: isinya bukan HASIL kerja, tapi BAHAN. Ia bisa
    dibuat ulang kapan saja dengan panen_bukti.py. Yang layak masuk git
    adalah hasilnya (tabel `kebutuhan`), bukan bahan mentahnya.

    Jadi:
      leads.db   -> dilacak git. Berisi lead, arsip, kontak, dan penilaian.
      bukti.db   -> TIDAK dilacak. Berisi teks halaman yang bisa dipanen ulang.

Aman dijalankan berulang. Kalau tabelnya sudah pindah, dia bilang begitu
dan tidak melakukan apa-apa.

Pakai:
    python src/pindah_bukti.py
"""

import shutil
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
DB_UTAMA = DATA / "leads.db"
DB_BUKTI = DATA / "bukti.db"


def tabel_ada(con, nama: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nama,)
    ).fetchone())


def main():
    if not DB_UTAMA.exists():
        print(f"Database tidak ditemukan: {DB_UTAMA}")
        raise SystemExit(1)

    con = sqlite3.connect(DB_UTAMA)
    if not tabel_ada(con, "halaman_bukti"):
        print("halaman_bukti sudah tidak ada di leads.db — tidak ada yang perlu dipindah.")
        con.close()
        return

    jml = con.execute("SELECT COUNT(*) FROM halaman_bukti").fetchone()[0]
    char = con.execute(
        "SELECT COALESCE(SUM(LENGTH(teks)), 0) FROM halaman_bukti").fetchone()[0]
    ukuran_lama = DB_UTAMA.stat().st_size
    con.close()

    print(f"Akan dipindah: {jml} baris, {char:,} karakter teks")
    print(f"leads.db sekarang: {ukuran_lama:,} byte")

    # Backup dulu. Aturan yang sama dipakai bersihkan_db.py.
    cadangan = DATA / "leads_backup_prapindah.db"
    shutil.copy2(DB_UTAMA, cadangan)
    print(f"Backup: {cadangan.name}")

    # Salin ke bukti.db lewat ATTACH — satu transaksi, tidak ada data
    # yang menggantung kalau gagal di tengah jalan.
    con = sqlite3.connect(DB_UTAMA)
    con.execute("ATTACH DATABASE ? AS bukti", (str(DB_BUKTI),))
    con.execute("""
        CREATE TABLE IF NOT EXISTS bukti.halaman_bukti (
            nama_normal   TEXT NOT NULL,
            nama          TEXT NOT NULL,
            website       TEXT,
            jenis         TEXT NOT NULL,
            url           TEXT NOT NULL,
            panjang       INTEGER,
            teks          TEXT,
            diambil_pada  TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (nama_normal, url)
        )""")
    con.execute("INSERT OR REPLACE INTO bukti.halaman_bukti SELECT * FROM main.halaman_bukti")
    con.commit()

    dipindah = con.execute("SELECT COUNT(*) FROM bukti.halaman_bukti").fetchone()[0]
    if dipindah < jml:
        print(f"GAGAL: hanya {dipindah}/{jml} baris tersalin. leads.db TIDAK diubah.")
        con.close()
        raise SystemExit(1)

    # Baru setelah tersalin utuh, yang lama dibuang.
    con.execute("DROP TABLE main.halaman_bukti")
    con.commit()
    con.execute("DETACH DATABASE bukti")
    con.close()

    # VACUUM merapikan ruang kosong bekas tabel tadi.
    con = sqlite3.connect(DB_UTAMA)
    con.execute("VACUUM")
    con.close()

    ukuran_baru = DB_UTAMA.stat().st_size
    print(f"\nSelesai. {dipindah} baris pindah ke {DB_BUKTI.name}")
    print(f"leads.db: {ukuran_lama:,} -> {ukuran_baru:,} byte "
          f"(turun {100 * (1 - ukuran_baru / ukuran_lama):.0f}%)")
    print(f"{DB_BUKTI.name}: {DB_BUKTI.stat().st_size:,} byte  (tidak dilacak git)")


if __name__ == "__main__":
    sys.exit(main())
