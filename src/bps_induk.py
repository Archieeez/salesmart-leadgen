"""
bps_induk.py
============
Pisahkan kandidat BPS yang situsnya MILIK SENDIRI dari yang cuma
menumpang situs induk/grup — sebelum satu pun agen membacanya.

KENAPA MODUL INI ADA:
    Bryan memutuskan 4 September 2026: anak usaha TIDAK boleh dinilai
    dari bukti di situs induknya. Kutipan harus dari halaman yang bicara
    tentang entitas itu sendiri.

    Tanpa penegak, keputusan itu tetap dijalankan — tapi dibayar di
    tempat termahal. Panen 97 situs BPS menghasilkan ini:

        AGRINDO INDAH PERSADA, PT    95   10 halaman
        MULTI NABATI SULAWESI, PT    95   10 halaman
        MULTIMAS NABATI ASAHAN, PT   95   10 halaman
        WILMAR PADI INDONESIA, PT    95   10 halaman

    Empat perusahaan, empat skor 95, **sepuluh halaman yang persis
    sama**: wilmar-international.com. Penyaring pola tidak tahu itu,
    karena ia membaca teks halaman dan teksnya memang kaya bahasa
    distribusi. Yang kaya bukan keempat anak usahanya — melainkan
    grupnya.

    Kalau keempatnya masuk antrian baca, empat kali jalan agen habis
    untuk sampai ke kesimpulan yang SUDAH TERCATAT waktu situsnya
    ditemukan: "Tidak punya situs sendiri; ini situs grup induk Wilmar."
    Itu persis kegagalan Agel Langgeng 3 Sep — dinilai 15 karena
    satu-satunya halaman terpanen adalah beranda induknya.

DUA TANDA, DAN KENAPA KEDUANYA PERLU:

    1. CATATAN PENEMUAN. Agen pencari situs sudah menuliskannya waktu
       memverifikasi domain. Ini pengamatan, dibuat orang/agen yang
       sedang melihat situsnya, bukan tebakan dari nama.

    2. HOST DIPAKAI BERSAMA. Kalau dua kandidat menunjuk host yang sama,
       paling banyak satu di antaranya pemiliknya. Tanda ini tidak
       bergantung pada prosa sama sekali — ia berlaku walau catatannya
       kosong, salah ketik, atau ditulis dengan kalimat yang tidak
       terduga.

    Tanda 1 menangkap induk yang TIDAK dipakai bersama (wingscorp.com
    cuma dipakai Gawi Makmur; indofood.com cuma Indofood Fortuna).
    Tanda 2 menangkap yang catatannya bungkam. Keduanya menangkap kasus
    yang tidak ditangkap satunya, jadi tidak ada yang bisa dibuang.

YANG SENGAJA TIDAK DILAKUKAN:
    Halaman yang telanjur terpanen TIDAK dihapus dari bukti.db. Panen
    itu fakta yang terjadi, dan `panen_log` dipakai `--lewati-sudah`
    untuk tidak mengulang situs yang sama. Yang disaring adalah ANTRIAN
    BACA, bukan riwayat.

Pakai:
    python src/bps_induk.py                       # laporan saja
    python src/bps_induk.py --tulis               # simpan ke bps.db
    python src/bps_induk.py --saring kerja/x.csv  # buang dari antrian baca
"""

import argparse
import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_BPS = BASE / "data" / "bps.db"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# Kalimat yang dipakai agen pencari situs waktu ia menemukan bahwa
# domainnya bukan milik badan hukum yang dicari. Didaftar apa adanya
# dari catatan yang SUDAH ada di bps.db, bukan dikarang: pola yang
# dikarang akan meleset dari cara agennya benar-benar menulis.
POLA_INDUK = re.compile(
    r"tidak punya situs sendiri"
    r"|situs induk"
    r"|situs grup"
    r"|dialihkan ke .{0,40}situs induk",
    re.I,
)

# Catatan yang justru MENEGASKAN kepemilikan. Diperiksa lebih dulu,
# karena satu baris bisa memuat keduanya: "Situs merek Cimory, dimiliki
# PT ini sendiri (nama badan hukum tercantum di footer)" menyebut kata
# 'merek' tapi menyatakan kepemilikan dengan jelas.
POLA_SENDIRI = re.compile(
    r"situs perusahaan sendiri"
    r"|dimiliki PT ini sendiri"
    r"|ini situs korporat"
    r"|badan hukumnya PT",
    re.I,
)


def host(url: str) -> str:
    h = re.sub(r"^https?://", "", (url or "").strip().lower())
    return re.sub(r"^www\.", "", h).split("/")[0]


def kunci_nama(nama: str) -> str:
    """Bentuk nama yang menyamakan ejaan berbeda untuk entitas yang sama.

    Direktori BPS memuat entitas yang sama dua kali dengan ejaan
    berbeda — 'GARUDA FOOD PUTRA PUTRI JAYA, PT' dan 'GARUDAFOOD PUTRA
    PUTRI JAYA, PT' adalah satu perusahaan, dan keduanya menunjuk
    garudafood.com.

    Tanpa langkah ini, tanda "host dipakai bersama" MENUDUH keduanya
    memakai situs induk — padahal garudafood.com memang situs mereka
    sendiri. Dua hal yang tampak sama di data (dua nama, satu host)
    ternyata dua persoalan berbeda dengan obat berbeda: yang satu
    dibuang seluruhnya, yang satu dibaca sekali. Menyamakannya membuat
    laporan modul ini keliru pada kasus yang justru paling jelas.
    """
    s = re.sub(r"\b(PT|CV|UD|TBK|PERSERO)\b", " ", (nama or "").upper())
    return re.sub(r"[^A-Z0-9]", "", s)


def klasifikasi(rows):
    """Return {nama: (milik_sendiri: bool, sebab: str)}.

    `rows` adalah (nama, website, catatan).
    """
    per_host = defaultdict(list)
    for nama, web, _ in rows:
        per_host[host(web)].append(nama)

    # Ejaan kembar dari entitas yang sama. Yang pertama menurut urutan
    # abjad dipertahankan supaya hasilnya sama tiap kali dijalankan;
    # sisanya dibuang sebagai DUPLIKAT, bukan sebagai situs induk.
    per_kunci = defaultdict(list)
    for nama, _, _ in rows:
        per_kunci[kunci_nama(nama)].append(nama)
    duplikat = {}
    for k, nama_nama in per_kunci.items():
        if len(nama_nama) > 1:
            utama, *sisa = sorted(nama_nama)
            for n in sisa:
                duplikat[n] = utama

    hasil = {}
    for nama, web, catatan in rows:
        c = catatan or ""
        h = host(web)
        # Kembarannya tidak dihitung sebagai "kandidat lain yang memakai
        # host ini" — kalau ikut dihitung, satu perusahaan dituduh
        # menumpang situsnya sendiri.
        kunci = kunci_nama(nama)
        berbagi = [n for n in per_host[h]
                   if n != nama and kunci_nama(n) != kunci]

        if nama in duplikat:
            hasil[nama] = (False, f"ejaan kembar dari {duplikat[nama]} — "
                                  "entitas yang sama, dibaca sekali saja")
            continue

        if POLA_SENDIRI.search(c):
            sebab = "catatan penemuan menyatakan situsnya milik sendiri"
            # Tetap dicatat kalau host-nya dipakai bersama: satu di antara
            # mereka pemiliknya, dan yang ini mengaku pemiliknya.
            if berbagi:
                sebab += f"; host dipakai bersama {len(berbagi)} kandidat lain"
            hasil[nama] = (True, sebab)
            continue

        if POLA_INDUK.search(c):
            hasil[nama] = (False, "catatan penemuan: situs induk/grup")
            continue

        if berbagi:
            hasil[nama] = (
                False,
                f"host {h} dipakai bersama {len(berbagi)} kandidat lain "
                f"({berbagi[0]}) dan tidak ada catatan kepemilikan")
            continue

        hasil[nama] = (True, "host tidak dipakai bersama, catatan tidak "
                             "menyebut induk")
    return hasil


def muat(db: Path):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT nama, website, catatan FROM prioritas_bps "
        "WHERE COALESCE(website,'') <> ''").fetchall()
    con.close()
    return rows


def tulis(db: Path, hasil: dict):
    con = sqlite3.connect(db)
    kolom = {r[1] for r in con.execute("PRAGMA table_info(prioritas_bps)")}
    if "situs_sendiri" not in kolom:
        con.execute("ALTER TABLE prioritas_bps ADD COLUMN situs_sendiri INTEGER")
        con.execute("ALTER TABLE prioritas_bps ADD COLUMN sebab_situs TEXT")
        print("kolom `situs_sendiri` + `sebab_situs` ditambahkan.")
    for nama, (sendiri, sebab) in hasil.items():
        con.execute("UPDATE prioritas_bps SET situs_sendiri=?, sebab_situs=? "
                    "WHERE nama=?", (1 if sendiri else 0, sebab, nama))
    con.commit()
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tulis", action="store_true",
                    help="simpan klasifikasi ke bps.db")
    ap.add_argument("--saring", default="",
                    help="CSV antrian baca; baris bersitus induk dibuang "
                         "dan ditulis ulang ke <nama>-tersaring.csv")
    args = ap.parse_args()

    rows = muat(DB_BPS)
    hasil = klasifikasi(rows)
    induk = {n for n, (s, _) in hasil.items() if not s}

    n_kembar = sum(1 for n in induk if "ejaan kembar" in hasil[n][1])
    print(f"{len(rows)} kandidat BPS bersitus")
    print(f"  milik sendiri  {len(rows) - len(induk)}  <- boleh dibaca")
    print(f"  situs induk    {len(induk) - n_kembar}  <- bukti milik entitas lain")
    print(f"  ejaan kembar   {n_kembar}  <- entitas yang sama, dibaca sekali")
    print()
    for nama in sorted(induk):
        print(f"  x  {nama[:44]:<46} {hasil[nama][1][:60]}")

    if args.tulis:
        tulis(DB_BPS, hasil)
        print(f"\nDitulis ke {DB_BPS.name}.")

    if args.saring:
        f = Path(args.saring)
        baris = list(csv.DictReader(open(f, encoding="utf-8")))
        simpan = [r for r in baris if r["nama"].strip() not in induk]
        buang = [r["nama"].strip() for r in baris
                 if r["nama"].strip() in induk]
        keluar = f.with_name(f.stem + "-tersaring.csv")
        with open(keluar, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=baris[0].keys())
            w.writeheader()
            w.writerows(simpan)
        print(f"\nantrian baca: {len(baris)} -> {len(simpan)} "
              f"({len(buang)} dibuang karena situs induk)")
        for n in buang:
            print(f"    dibuang: {n}")
        print(f"  -> {keluar}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
