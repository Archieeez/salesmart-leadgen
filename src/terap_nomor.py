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
import publik  # noqa: E402

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

# Kata yang MEMBALIK arti frasa di atas.
#
# KENAPA PERLU, dan kenapa ini bukan kehati-hatian teoretis: 4 Sep 2026
# gerbang ini menolak DUA nomor yang benar sekaligus. Agen Madusari
# menulis "Nama perusahaan yang dicari benar-benar menempel pada nomor,
# BUKAN ENTITAS LAIN", dan agen Sarimelati menulis "jadi BUKAN NOMOR
# ENTITAS LAIN". Keduanya PENYANGKALAN — persis penegasan yang kita
# inginkan — dan regex membacanya sebagai peringatan.
#
# Cacatnya ada di regex itu sendiri: alternatif `bukan\s+nomor` dipasang
# untuk menangkap "bukan nomor Canning", tapi ia juga menangkap "bukan
# nomor entitas lain" yang artinya kebalikannya.
#
# Ini pengulangan pelajaran Arta Boga: kalimat penyangkalan yang dibaca
# regex sebagai pernyataan. Obat yang benar sudah dipakai di sana — field
# TERSTRUKTUR — dan dipasang di bawah sebagai `entitas_cocok`. Penanganan
# penyangkalan ini untuk baris yang tidak punya field itu.

# Penyangkalnya sering berjarak satu-dua kata dari frasanya:
# "bukan NOMOR entitas lain", "tidak ADA INDIKASI perusahaan lain".
# Dibatasi dua kata supaya "bukan" yang berjarak satu kalimat tidak
# ikut dianggap menyangkal.
NEGASI = re.compile(r"(bukan|tidak|nol|tanpa)(\s+\w+){0,2}\W*$",
                    re.IGNORECASE)

# Jendela ke belakang untuk mencari penyangkalnya. Sempit: "bukan" yang
# berjarak satu kalimat tidak sedang menyangkal frasa ini.
JENDELA_NEGASI = 24


def sebut_entitas_lain(teks: str) -> str | None:
    """Return frasa yang menuduh nomor ini milik entitas lain, atau None.

    Frasa yang DISANGKAL diabaikan. Frasa `bukan ...` yang ternyata
    diikuti "entitas lain"/"perusahaan lain" juga diabaikan: itu
    penyangkalan bertingkat, bukan tuduhan.
    """
    for m in ENTITAS_LAIN.finditer(teks or ""):
        frasa = m.group(0)
        sebelum = teks[max(0, m.start() - JENDELA_NEGASI):m.start()]
        if NEGASI.search(sebelum):
            continue
        if frasa.lower().startswith(("bukan", "tidak")):
            sesudah = teks[m.end():m.end() + 30].lower()
            if "entitas lain" in sesudah or "perusahaan lain" in sesudah:
                continue
        return frasa
    return None


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

    # FIELD TERSTRUKTUR LEBIH DULU, prosa cuma jalur warisan.
    #
    # Kalau agen mengisi `entitas_cocok`, itu yang BERDAULAT dan prosa
    # tidak dibaca sama sekali — termasuk waktu isinya "ya". Persis
    # rancangan `penanda` di rubrik, dan alasannya sama: regex prosa
    # tidak bisa membedakan pernyataan dari penyangkalan, dan dua nomor
    # yang benar sudah pernah ditolak karenanya (Madusari, Sarimelati,
    # 4 Sep 2026).
    # `entitas_cocok` menjawab SATU pertanyaan: apakah nomor ini milik
    # badan hukum yang dinilai? Ia BUKAN tempat menaruh keraguan lain.
    #
    # Batas itu ditegaskan agen pencari nomor Canning 4 Sep 2026, dan
    # alasannya benar: ia ragu apakah nomor dari portal bursa kerja masih
    # DIANGKAT, bukan apakah nomor itu MILIK Canning. Kalau keraguan
    # kesegaran ikut dialirkan ke sini, kolom ini berhenti berarti "milik
    # entitas lain" dan berubah jadi "saya agak ragu" -- dan gerbang ini
    # kehilangan sinyal yang justru dibangun untuk menangkap kasus
    # Bahtera Wiraniaga. Keraguan kesegaran tempatnya di `catatan`, dan
    # panggilan pertama yang membuktikannya.
    cocok = (r.get("entitas_cocok") or "").strip().lower()
    if cocok:
        if cocok not in ("ya", "yes", "true", "1"):
            salah.append("agen menyatakan entitas_cocok bukan 'ya': "
                         f"{cocok!r}")
        return salah

    frasa = sebut_entitas_lain(r.get("catatan") or "")
    if frasa:
        salah.append("agennya sendiri menandai nomor ini milik ENTITAS "
                     f"LAIN ({frasa!r})")
    return salah


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="kerja/nomor")
    ap.add_argument("--tulis", action="store_true")
    # Sampai 4 Sep 2026 nilai ini HARDCODE 'nomor-4sep'. Itu aman selama
    # semua nomor berasal dari kolam yang sama, dan berhenti aman di menit
    # nomor untuk kandidat BPS dipanen: barisnya akan tercatat ber-asal
    # 'nomor-4sep', lolos publik.klausa(), lalu terbit. Provenansi tidak
    # boleh ditebak dari tanggal jalannya skrip.
    ap.add_argument("--asal", required=True,
                    help="asal usul kandidat, mis. bps-direktori-manufaktur-2025, "
                         "gapmmi, riset-manual. Yang berawalan 'bps' tidak "
                         "akan terbit ke berkas publik.")
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

    # SATU FOLDER = SATU ASAL, dan itu ditegakkan, bukan diingat.
    #
    # `--asal` berlaku untuk SELURUH folder. 4 Sep 2026 sebuah agen
    # menyalin hasilnya ke DUA folder sekaligus supaya aman, dan itu
    # justru membuat berkas Canning (asal riset-manual) duduk di folder
    # batch BPS. Menjalankan ulang folder itu akan menulis Canning
    # ber-asal 'bps-...' -- provenansi rusak, dan lead yang sah malah
    # ikut DITAHAN dari dasbor publik oleh publik.klausa().
    #
    # Diperiksa terhadap asal yang SUDAH tercatat di database, karena itu
    # fakta, bukan tebakan.
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    asal_lama = {}
    for tabel, kolom in (("kebutuhan", "asal"),
                         ("kontak_web", "sumber_discovery")):
        try:
            for n, a in con.execute(f"SELECT nama, {kolom} FROM {tabel}"):
                if a:
                    asal_lama.setdefault(n, a)
        except sqlite3.Error:
            pass
    con.close()

    # Yang dibandingkan bukan teks asalnya, melainkan AKIBATNYA: boleh
    # terbit atau tidak. 'gapmmi' vs 'riset-manual' sama-sama boleh
    # terbit dan tidak perlu diributkan; 'bps-...' vs apa pun yang lain
    # mengubah apakah barisnya muncul di dasbor publik, dan itu yang
    # harus berhenti.
    bentrok = [(n, asal_lama[n]) for n, _ in lolos
               if n in asal_lama
               and publik.boleh_terbit(asal_lama[n]) is not
                   publik.boleh_terbit(args.asal)]
    if bentrok:
        print(f"\nDITOLAK: --asal '{args.asal}' bentrok dengan asal yang "
              "sudah tercatat:")
        for n, a in bentrok:
            print(f"  {n[:44]:<46} sudah ber-asal {a!r}")
        print("\nSatu folder = satu asal. Pindahkan baris yang tidak "
              "sekelompok ke foldernya sendiri.")
        raise SystemExit(1)

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
            "VALUES (?,?,?,?,?,?,?,'ok',?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(nama_normal) DO UPDATE SET "
            "  telepon=excluded.telepon, kelas_kontak=excluded.kelas_kontak, "
            "  sumber_halaman=excluded.sumber_halaman, "
            "  sumber_discovery=excluded.sumber_discovery, "
            "  diambil_pada=CURRENT_TIMESTAMP",
            (ek.normalisasi_nama(nama), nama, dikenal.get(nama) or "",
             digit, kelas, (r.get("sumber_url") or "").strip(), digit,
             args.asal))
    con.commit()
    n = con.execute("SELECT count(*) FROM kontak_web").fetchone()[0]
    con.close()
    print(f"\nDitulis. kontak_web kini {n} baris.")


if __name__ == "__main__":
    main()
