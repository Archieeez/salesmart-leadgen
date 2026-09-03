"""
bps_situs.py
============
Terapkan hasil pencarian situs oleh agen ke `bps.db`, setelah diperiksa.

    python src/bps_situs.py --dir kerja/situs            # periksa saja
    python src/bps_situs.py --dir kerja/situs --tulis    # baru tulis

KENAPA ADA PEMERIKSA DI TENGAH:
    Agen pencari bekerja dari hasil pencarian web, dan hasil pencarian
    penuh jebakan yang bentuknya persis seperti jawaban benar:

      - portal lowongan kerja (jobstreet, karir.com, glints) memuat nama
        perusahaan di judul halamannya, jadi terlihat seperti situs resmi
      - direktori alamat dan situs data saham juga begitu
      - media sosial bukan situs perusahaan

    Larangan itu sudah ditulis di prompt agennya. Modul ini menegakkannya
    di mesin, karena aturan yang cuma ada di prompt bergantung pada agen
    yang mematuhinya -- dan satu agen yang lalai sudah cukup untuk
    memasukkan data yang salah tanpa ada yang tahu.

JEBAKAN YANG SUDAH TERBUKTI, semuanya lolos kalau yang dicek cuma
status code. Dicatat di sini karena tiap satu bentuk kegagalan yang
BERBEDA, dan daftar ini yang dipakai menyusun prompt agen berikutnya:

    indokom.co.id        terindeks lengkap  -> "Domain Expired"
    yummychoice.co.id    HTTP 200           -> halaman webmail
    indoworld.co.id      HTTP 200           -> login Outlook Web Access
    gawimakmur.com       HTTP 200 + judul   -> placeholder hosting Rumahweb
                                               "Selamat, website X telah aktif"
    cocolabakery.com     200 + judul COCOK  -> toko roti di San Jose, AS
    megajaya.co.id       200 + isi rapi     -> penjual wire rope, industri lain
    heinzabc.co.id       dikutip Wikipedia  -> 301 ke situs konsumen AS

Judul yang cocok pun bukan bukti. Yang membuktikan: alamat, provinsi,
mata uang, dan nama badan hukum di dalam isinya.

KENAPA URL TIDAK DIVERIFIKASI ULANG DI SINI:
    Agen sudah membuka tiap situs dan mencatat buktinya. Membukanya lagi
    berarti memukul situs orang dua kali untuk hal yang sama. Yang
    diperiksa modul ini adalah BENTUK dan ASAL URL-nya, bukan isinya.
"""

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB_BPS = BASE / "data" / "bps.db"

# Host yang BUKAN situs perusahaan, betapapun namanya muncul di sana.
HOST_TERLARANG = re.compile(
    r"(jobstreet|karir\.com|glints|kalibrr|indeed|loker|jobs?\.|lowongan"
    r"|linkedin|facebook|instagram|twitter|x\.com|tiktok|youtube"
    r"|idnfinancials|investing\.com|stockanalysis|jitta|idx\.co\.id"
    r"|ksei\.co\.id|wikipedia|liputan6|detik|kompas|tribunnews"
    r"|idalamat|contact\.page|dataindonesia|onesearch|repository"
    r"|\.go\.id$|\.ac\.id$)", re.IGNORECASE)

KEYAKINAN = {"tinggi", "sedang", "rendah", ""}


def periksa_baris(r):
    """Return daftar alasan kenapa baris ini ditolak. Kosong = lolos."""
    salah = []
    web = (r.get("website") or "").strip()
    yak = (r.get("keyakinan") or "").strip().lower()

    if yak not in KEYAKINAN:
        salah.append(f"keyakinan tidak dikenal: {yak!r}")
    if not web:
        if yak and yak != "":
            salah.append("website kosong tapi keyakinan terisi")
        return salah                      # tidak ketemu = sah, bukan salah

    u = urlparse(web if "//" in web else "https://" + web)
    if u.scheme not in ("http", "https"):
        salah.append(f"skema URL aneh: {web!r}")
    if not u.netloc or "." not in u.netloc:
        salah.append(f"host tidak masuk akal: {web!r}")
    if HOST_TERLARANG.search(u.netloc):
        salah.append(f"host terlarang (bukan situs perusahaan): {u.netloc}")
    if not yak:
        salah.append("ada website tapi keyakinan kosong")
    if not (r.get("bukti") or "").strip():
        salah.append("tidak ada bukti yang dicatat")
    return salah


def muat(folder: Path):
    baris = []
    for f in sorted(folder.glob("hasil*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                r["_berkas"] = f.name
                baris.append(r)
    return baris


def kunci(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"\b(PT|CV|UD|TBK|PERSERO|PERUM|INDONESIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="kerja/situs")
    ap.add_argument("--tulis", action="store_true")
    args = ap.parse_args()

    folder = BASE / args.dir
    if not folder.exists():
        raise SystemExit(f"Folder tidak ada: {folder}")

    baris = muat(folder)
    if not baris:
        raise SystemExit(f"Tidak ada hasil*.csv di {folder}")

    con = sqlite3.connect(f"file:{DB_BPS}?mode=ro", uri=True)
    dikenal = {r[0] for r in con.execute("SELECT kunci FROM prioritas_bps")}
    con.close()

    lolos, ditolak, tak_ketemu, asing = [], [], 0, []
    gagal = []
    for r in baris:
        k = kunci(r.get("nama", ""))
        if k not in dikenal:
            asing.append(r.get("nama", ""))
            continue
        salah = periksa_baris(r)
        if salah:
            ditolak.append((r.get("nama", ""), r.get("website", ""), salah))
        elif not (r.get("website") or "").strip():
            tak_ketemu += 1
            # DITANDAI, bukan dilewatkan diam-diam. Baris yang sudah
            # dicari dan tidak ketemu terlihat sama persis dengan baris
            # yang belum pernah dicari -- keduanya website NULL. Tanpa
            # penanda ini, gelombang berikutnya mencarinya lagi, dan
            # pekerjaan yang sudah gagal diulang tanpa ada yang sadar.
            gagal.append((k, (r.get("catatan") or "").strip()))
        else:
            lolos.append((k, r))

    from collections import Counter
    yak = Counter((r.get("keyakinan") or "").lower() for _, r in lolos)
    print(f"baris dibaca      : {len(baris)}")
    print(f"  situs diterima  : {len(lolos)}  "
          f"(tinggi {yak['tinggi']}, sedang {yak['sedang']}, "
          f"rendah {yak['rendah']})")
    print(f"  tidak ketemu    : {tak_ketemu}")
    print(f"  DITOLAK         : {len(ditolak)}")
    print(f"  nama asing      : {len(asing)}")
    for n, w, s in ditolak[:10]:
        print(f"     {n[:34]:<36}{w[:34]:<36}{'; '.join(s)}")
    for n in asing[:5]:
        print(f"     asing: {n!r} tidak ada di prioritas_bps")

    if not args.tulis:
        print("\n(mode periksa; tidak ada yang ditulis. Tambahkan --tulis.)")
        return

    con = sqlite3.connect(DB_BPS)
    for k, c in gagal:
        con.execute(
            "UPDATE prioritas_bps SET catatan=? WHERE kunci=? AND catatan=''",
            (f"dicari, TIDAK KETEMU. {c[:160]}".strip(), k))
    for k, r in lolos:
        con.execute(
            "UPDATE prioritas_bps SET website=?, catatan=? WHERE kunci=?",
            ((r.get("website") or "").strip(),
             f"{(r.get('keyakinan') or '').strip()}: "
             f"{(r.get('catatan') or r.get('bukti') or '').strip()[:180]}",
             k))
    con.commit()
    n = con.execute("SELECT count(*) FROM prioritas_bps "
                    "WHERE website IS NOT NULL").fetchone()[0]
    con.close()
    print(f"\nDitulis. Kandidat bersitus kini {n}.")


if __name__ == "__main__":
    main()
