"""
terap_nomor.py
==============
Terapkan nomor telepon hasil pencarian agen ke tabel `kontak_web`,
setelah diperiksa.

    python src/terap_nomor.py --dir kerja/nomor            # periksa saja
    python src/terap_nomor.py --dir kerja/nomor --tulis    # baru tulis

KENAPA ADA PEMERIKSA DI TENGAH:
    Nomor telepon adalah satu-satunya data di pipeline ini yang dipakai
    MENGHUBUNGI ORANG. Skor yang salah cuma membuang waktu; nomor yang
    salah membuat orang sales menelepon perusahaan lain, atau menelepon
    seseorang yang tidak ada urusannya.

    Proyek ini sudah pernah kena dua kali, keduanya tercatat:

      - nomor careline Danone "0813-888888-73" tersimpan terpotong jadi
        11 digit yang menyambung ke orang lain
      - nomor HP seorang PEMBELI ikut tersimpan dari halaman cek undian
        Alfamart, lengkap dengan namanya

    Karena itu modul ini menolak, bukan memperbaiki. Baris yang mencurigakan
    dibuang dengan alasannya, dan pekerjaannya diulang.

YANG DIPERIKSA DI SINI, dan bukan di kepala agen:
    1. bentuk nomornya masuk akal sebagai nomor Indonesia
    2. kelas yang diklaim COCOK dengan bentuk nomornya -- agen yang
       menulis "kantor" untuk nomor 08xx tertangkap di sini
    3. ada sumber_url dan bukti; nomor tanpa asal-usul tidak bisa
       dipertanggungjawabkan waktu orang sales bertanya "dari mana?"
    4. nomornya bukan bentuk contoh (deret naik, digit berulang)
"""

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import enrich_kontak as ek  # noqa: E402

DB = BASE / "data" / "leads.db"

# Penanda bahwa agen sendiri menyatakan nomor itu MILIK ENTITAS LAIN.
#
# Ini bukan kehati-hatian berlebihan. Agen pencari nomor Pronas menemukan
# 021-856 4454 di situs pronas.co.id dan menandainya "kantor" dengan
# benar -- itu memang landline kantor. Tapi kantornya PT Bahtera
# Wiraniaga Internusa, bukan PT Canning Indonesian Products, dan nama
# perusahaan yang dinilai tidak muncul sama sekali di situs itu.
#
# Bentuk nomornya sah, sumbernya sah, buktinya ada. Semua pemeriksaan
# mekanis lolos. Yang membuatnya salah cuma satu hal yang HANYA ada di
# prosa: itu nomor perusahaan lain. Jadi prosanya ikut dibaca -- bukan
# untuk menebak, melainkan untuk menangkap peringatan yang sudah ditulis
# agennya sendiri.
#
# Menulisnya diam-diam berarti orang sales menelepon perusahaan lain
# sambil mengira sedang menelepon lead-nya.
ENTITAS_LAIN = re.compile(
    r"(milik\s+(pt|cv)\s|bukan\s+(pt|cv|nomor|milik)|entitas\s+(lain|berbeda)"
    r"|perusahaan\s+lain|induk(nya)?\b)", re.IGNORECASE)

# Kelas yang dipakai agen -> kelas yang dipakai tabel kontak_web.
# "kantor" dan "cabang" keduanya jalur langsung, tapi dibedakan supaya
# antrian tidak menaikkan nomor cabang ke prioritas tertinggi -- pelajaran
# dari TIKI, yang nomor cabang Ambonnya sempat jadi nomor utama.
PETA_KELAS = {"kantor": "langsung", "cabang": "cabang",
              "layanan": "layanan", "seluler": "seluler"}


def periksa(r):
    """Return daftar alasan penolakan. Kosong = lolos."""
    salah = []
    tel = (r.get("telepon") or "").strip()
    kelas = (r.get("kelas") or "").strip().lower()

    if not tel:
        if kelas:
            salah.append("telepon kosong tapi kelas terisi")
        return salah                      # tidak ketemu = sah

    if kelas not in PETA_KELAS:
        salah.append(f"kelas tidak dikenal: {kelas!r}")

    digit = ek.normalisasi_telepon(tel)
    if not digit:
        salah.append(f"nomor tidak lolos normalisasi: {tel!r}")
    else:
        # Kelas yang diklaim harus cocok dengan bentuk nomornya. Agen
        # bisa saja menulis "kantor" untuk nomor HP tanpa sadar.
        bentuk = ("layanan" if digit.startswith(("1500", "62800", "62804"))
                  else "seluler" if digit.startswith("628")
                  else "kantor")
        if kelas in ("kantor", "cabang") and bentuk != "kantor":
            salah.append(f"diklaim {kelas} tapi bentuknya {bentuk}: {tel}")
        if kelas == "seluler" and bentuk != "seluler":
            salah.append(f"diklaim seluler tapi bentuknya {bentuk}: {tel}")

    u = urlparse((r.get("sumber_url") or "").strip())
    if not u.netloc:
        salah.append("tidak ada sumber_url yang sah")
    if not (r.get("bukti") or "").strip():
        salah.append("tidak ada bukti konteks yang dicatat")

    catatan = (r.get("catatan") or "")
    if ENTITAS_LAIN.search(catatan):
        salah.append("agennya sendiri menandai nomor ini milik ENTITAS LAIN")
    return salah


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="kerja/nomor")
    ap.add_argument("--tulis", action="store_true")
    args = ap.parse_args()

    folder = BASE / args.dir
    baris = []
    for f in sorted(folder.glob("hasil*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            baris += list(csv.DictReader(fh))
    if not baris:
        raise SystemExit(f"Tidak ada hasil*.csv di {folder}")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    dikenal = {r[0]: r[1] for r in con.execute(
        "SELECT nama, website FROM kebutuhan")}
    con.close()
    # Sebagian lead bernilai tinggi TIDAK ada di tabel `kebutuhan` -- mereka
    # dinilai lewat riset manual di companies_scored.csv dan tidak pernah
    # naik ke penilaian berbukti. Paragon (skor 100, pemilik Wardah) salah
    # satunya. Tanpa ini, nomor kantornya ditolak sebagai "nama asing"
    # padahal perusahaannya ada di antrian.
    csv_skor = BASE / "data" / "companies_scored.csv"
    if csv_skor.exists():
        with open(csv_skor, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                n = (r.get("company_name") or "").strip()
                if n and n not in dikenal:
                    dikenal[n] = (r.get("website") or "").strip()

    lolos, ditolak, kosong, asing = [], [], 0, []
    for r in baris:
        nama = (r.get("nama") or "").strip()
        if nama not in dikenal:
            asing.append(nama)
            continue
        s = periksa(r)
        if s:
            ditolak.append((nama, r.get("telepon", ""), s))
        elif not (r.get("telepon") or "").strip():
            kosong += 1
        else:
            lolos.append((nama, r))

    from collections import Counter
    kel = Counter((r.get("kelas") or "").lower() for _, r in lolos)
    print(f"baris dibaca   : {len(baris)}")
    print(f"  diterima     : {len(lolos)}  "
          f"(kantor {kel['kantor']}, cabang {kel['cabang']}, "
          f"layanan {kel['layanan']}, seluler {kel['seluler']})")
    print(f"  tidak ketemu : {kosong}")
    print(f"  DITOLAK      : {len(ditolak)}")
    for n, t, s in ditolak:
        print(f"     {n[:30]:<32}{t[:22]:<24}{'; '.join(s)}")
    for n in asing:
        print(f"     asing: {n!r} tidak ada di tabel kebutuhan")

    if not args.tulis:
        print("\n(mode periksa; tidak ada yang ditulis. Tambahkan --tulis.)")
        return

    con = sqlite3.connect(DB)
    con.execute(ek.DDL) if hasattr(ek, "DDL") else None
    for nama, r in lolos:
        digit = ek.normalisasi_telepon(r["telepon"])
        kelas = PETA_KELAS[(r.get("kelas") or "").lower()]
        con.execute(
            "INSERT INTO kontak_web (nama_normal, nama, website, telepon, "
            " kelas_kontak, sumber_halaman, semua_nomor, status, "
            " sumber_discovery, diambil_pada) "
            "VALUES (?,?,?,?,?,?,?,'ok','nomor-4sep',CURRENT_TIMESTAMP) "
            "ON CONFLICT(nama_normal) DO UPDATE SET "
            "  telepon=excluded.telepon, kelas_kontak=excluded.kelas_kontak, "
            "  sumber_halaman=excluded.sumber_halaman, "
            "  sumber_discovery=excluded.sumber_discovery, "
            "  diambil_pada=CURRENT_TIMESTAMP",
            (ek.normalisasi_nama(nama), nama, dikenal.get(nama) or "",
             digit, kelas, (r.get("sumber_url") or "").strip(), digit))
    con.commit()
    n = con.execute("SELECT count(*) FROM kontak_web").fetchone()[0]
    con.close()
    print(f"\nDitulis. kontak_web kini {n} baris.")


if __name__ == "__main__":
    main()
