"""
panen_bukti.py
==============
Panen halaman yang memuat BUKTI kebutuhan terhadap Salesmart.

KENAPA MODUL INI ADA:
    enrich_kontak.py memanen halaman KONTAK, karena dulu targetnya nomor
    telepon. Waktu halaman-halaman itu dipakai ulang untuk menilai
    kebutuhan, hasilnya kacau: Kalbe dapat skor distribusi NOL — padahal
    Kalbe mendistribusikan lewat Enseval dan punya ribuan medical
    representative. Halaman "Hubungi Kami" memang tidak pernah membahas
    jaringan distribusi.

    Jadi masalahnya bukan cara membaca, tapi HALAMAN YANG DIBACA.
    Modul ini memanen halaman yang benar: Tentang Kami, Bisnis, Jaringan
    Distribusi, Produk, dan Karier.

KENAPA HALAMAN KARIER PENTING:
    Bukti terkuat untuk `field_sales` bukan di brosur perusahaan, tapi di
    lowongan kerjanya. Perusahaan yang merekrut "Area Sales Manager" di 12
    kota membuktikan tim lapangan DAN skala sekaligus.

    Papan lowongan pihak ketiga TIDAK dipakai di sini: JobStreet dan Glints
    melarang lewat robots.txt, dan ToS papan lain belum diperiksa. Halaman
    karier di situs perusahaan sendiri tidak punya masalah itu.

Pakai:
    python panen_bukti.py --input ../data/seed_gapmmi.csv --cache ../data/.cache_html
    python panen_bukti.py --input ../data/seed_gapmmi.csv --dry-run --verbose

Hasilnya masuk ke data/bukti.db — TERPISAH dari leads.db. Teks halaman
adalah bahan mentah yang bisa dipanen ulang, bukan hasil kerja, jadi tidak
ikut dilacak git. Lihat pindah_bukti.py.
"""

import argparse
import csv
import re
import sqlite3
import sys
import time
from urllib.parse import urljoin

import web
from web import (JEDA_ANTAR_SITUS, ambil_html, boleh_ambil, cari_link,
                 jeda_halaman, log, teks_dari_html)

# --------------------------------------------------------------------------
# Halaman apa yang dicari
# --------------------------------------------------------------------------
# Tiap jenis punya polanya sendiri supaya bisa dicatat halaman mana
# menyumbang bukti apa. Ini penting waktu menilai: kalau LLM bilang sebuah
# perusahaan punya jaringan distribusi, kita bisa tunjuk halamannya.

JENIS_HALAMAN = {
    "tentang": re.compile(
        r"(tentang|about|profil|profile|company|perusahaan|sejarah|who\s*we\s*are)",
        re.I),
    "bisnis": re.compile(
        r"(bisnis|business|our\s*business|unit\s*usaha|divisi|division|"
        r"operasi|operation|what\s*we\s*do)", re.I),
    "distribusi": re.compile(
        r"(distribusi|distribution|jaringan|network|distributor|logistik|"
        r"logistics|supply\s*chain|rantai\s*pasok|cabang|branch|depo)", re.I),
    "produk": re.compile(
        r"(produk|product|brand|merek|portfolio|portofolio)", re.I),
    "karier": re.compile(
        r"(karier|karir|career|lowongan|vacanc|job|rekrutmen|recruitment|"
        r"bergabung|join\s*us|work\s*with\s*us)", re.I),
}

# Berapa halaman per jenis yang diambil. Ditahan kecil supaya sopan —
# 5 jenis x 2 = maksimum 10 halaman per situs, plus homepage.
MAKS_PER_JENIS = 2

# Teks yang lebih pendek dari ini hampir pasti halaman kosong / parkir.
MIN_PANJANG_TEKS = 200

# Pintu masuk alternatif kalau homepage ternyata cuma cangkang.
#
# Kenapa perlu: homepage kalbe.co.id mengembalikan 5.947 karakter HTML tapi
# hanya 12 karakter teks — itu halaman pengalih yang isinya dirender
# JavaScript, jadi tidak ada satu pun <a> untuk ditelusuri. Situs aslinya
# ada di /id/. Pola yang sama dipakai nestle.co.id/id, kino.co.id/id/,
# glico.com/id/, dan coca-cola.co.id/id/home.
PINTU_ALTERNATIF = ["/id/", "/id", "/en/", "/home", "/id/home"]

# Di bawah jumlah link ini, homepage dianggap cangkang dan pintu
# alternatif ikut dicoba.
MIN_LINK_HOMEPAGE = 3


# --------------------------------------------------------------------------
# Penyimpanan
# --------------------------------------------------------------------------

DDL_LOG = """
CREATE TABLE IF NOT EXISTS panen_log (
    nama_normal     TEXT PRIMARY KEY,
    nama            TEXT NOT NULL,
    website         TEXT,
    jml_halaman     INTEGER,
    dicoba_pada     TEXT DEFAULT CURRENT_TIMESTAMP,
    -- Diisi diagnosa_panen.py, bukan modul ini. Kolomnya ikut di sini
    -- supaya database baru punya bentuk yang sama dengan yang lama.
    sebab           TEXT,
    sebab_detail    TEXT,
    didiagnosa_pada TEXT
);
"""

DDL = """
CREATE TABLE IF NOT EXISTS halaman_bukti (
    nama_normal   TEXT NOT NULL,
    nama          TEXT NOT NULL,
    website       TEXT,
    jenis         TEXT NOT NULL,
    url           TEXT NOT NULL,
    panjang       INTEGER,
    teks          TEXT,
    diambil_pada  TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (nama_normal, url)
);
"""


def normalisasi_nama(nama: str) -> str:
    """Sama semangatnya dengan bersihkan_db.py: buang PT/CV, tanda baca."""
    s = nama.upper()
    s = re.sub(r"\b(PT|CV|TBK|PERSERO|INDONESIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def simpan(db_path: str, baris: dict):
    con = sqlite3.connect(db_path)
    con.execute(DDL)
    con.execute(
        """INSERT OR REPLACE INTO halaman_bukti
           (nama_normal, nama, website, jenis, url, panjang, teks)
           VALUES (?,?,?,?,?,?,?)""",
        (normalisasi_nama(baris["nama"]), baris["nama"], baris["website"],
         baris["jenis"], baris["url"], baris["panjang"], baris["teks"]),
    )
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Panen
# --------------------------------------------------------------------------

def panen_situs(website: str) -> list[dict]:
    """Kembalikan daftar halaman bukti untuk satu situs."""
    root, path_seed = web.akar(website)
    hasil: list[dict] = []
    diperiksa: set[str] = set()
    html_halaman: dict[str, str] = {}

    def ambil(url: str, jenis: str) -> bool:
        url = url.split("#")[0]
        if url in diperiksa:
            return False
        diperiksa.add(url)

        if not boleh_ambil(url):
            log(f"robots melarang {url}")
            return False

        html, alasan = ambil_html(url)
        log(f"GET {url} -> {alasan}")
        jeda_halaman(url)
        if html is None:
            return False
        # Disimpan supaya halaman ini bisa dipakai sebagai sumber link
        # tanpa meminta ulang ke server.
        html_halaman[url] = html
        teks = teks_dari_html(html)
        if not teks or len(teks) < MIN_PANJANG_TEKS:
            return False

        hasil.append({"jenis": jenis, "url": url,
                      "panjang": len(teks), "teks": teks})
        return True

    # 1. Homepage — selalu, dan sumber semua link berikutnya.
    beranda = urljoin(root, "/")
    ambil(beranda, "beranda")

    # 2. Path yang ditunjuk seed CSV, kalau memang menunjuk halaman dalam.
    url_seed = ""
    if path_seed not in ("", "/"):
        url_seed = urljoin(root, path_seed)
        ambil(url_seed, "seed")

    # 3. Kumpulkan sumber link.
    #
    #    HALAMAN SEED DIDAHULUKAN, dan ini bukan soal selera.
    #    Sebelumnya link cuma digali dari homepage. Akibatnya seed yang
    #    menunjuk mondelezinternational.com/indonesia TETAP menghasilkan
    #    sepuluh halaman korporat GLOBAL: halaman Indonesia-nya memang ikut
    #    terambil, tapi link untuk ditelusuri diambil dari homepage global.
    #    Danone dan DSV kena persis hal yang sama, dan ketiganya berakhir
    #    di need score 10-15 karena bukti Indonesianya tidak pernah terbaca.
    #
    #    Seed ditaruh di depan supaya jatah MAKS_PER_JENIS habis untuk
    #    halaman Indonesia dulu, baru sisanya dari homepage.
    sumber_html: list[str] = []
    if url_seed and url_seed in html_halaman:
        sumber_html.append(html_halaman[url_seed])
    html, _ = ambil_html(beranda)
    if html:
        sumber_html.append(html)

    jml_link = sum(len(cari_link(html, root, p)) for p in JENIS_HALAMAN.values()) \
        if html else 0
    if jml_link < MIN_LINK_HOMEPAGE:
        log(f"homepage cuma {jml_link} link — coba pintu alternatif")
        for path in PINTU_ALTERNATIF:
            url = urljoin(root, path)
            if url in diperiksa or not boleh_ambil(url):
                continue
            h, _ = ambil_html(url)
            jeda_halaman(url)
            if not h:
                continue
            if sum(len(cari_link(h, root, p)) for p in JENIS_HALAMAN.values()):
                sumber_html.append(h)
                ambil(url, "beranda")
                break

    # 4. Link per jenis, dari semua sumber yang terkumpul.
    for jenis, pola in JENIS_HALAMAN.items():
        n = 0
        for h in sumber_html:
            for url in cari_link(h, root, pola):
                if n >= MAKS_PER_JENIS:
                    break
                if ambil(url, jenis):
                    n += 1

    return hasil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV: nama,website,sumber")
    ap.add_argument("--db", default="../data/bukti.db",
                    help="teks halaman masuk ke bukti.db, BUKAN leads.db — "
                         "isinya bahan mentah yang bisa dipanen ulang, "
                         "jadi tidak dilacak git")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--lewati-sudah", action="store_true",
                    help="lewati perusahaan yang sudah ada di halaman_bukti; "
                         "dipakai untuk melanjutkan panen yang terputus")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--cache", default="",
                    help="folder cache HTML mentah; kosong = tanpa cache")
    args = ap.parse_args()

    web.setel(verbose=args.verbose, cache_dir=args.cache or None)

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.lewati_sudah:
        con = sqlite3.connect(args.db)
        con.execute(DDL_LOG)
        con.execute(DDL)
        # Yang dilewati adalah yang sudah DICOBA, bukan yang berhasil.
        # Mayoritas situs OSM menghasilkan nol halaman; kalau patokannya
        # keberhasilan, situs mati diulang terus tiap panen dilanjutkan.
        sudah = {r[0] for r in con.execute("SELECT nama_normal FROM panen_log")}
        sudah |= {r[0] for r in con.execute(
            "SELECT DISTINCT nama_normal FROM halaman_bukti")}
        con.close()
        semula = len(rows)
        rows = [r for r in rows
                if normalisasi_nama(r["nama"].strip()) not in sudah]
        print(f"melanjutkan: {semula - len(rows)} sudah dipanen, "
              f"{len(rows)} tersisa")
        print()

    if args.limit:
        rows = rows[: args.limit]

    total_hal = 0
    tanpa_hal = 0
    per_jenis: dict[str, int] = {}

    for i, row in enumerate(rows, 1):
        nama = row["nama"].strip()
        website = row["website"].strip()
        if not website:
            continue

        halaman = panen_situs(website)
        root, _ = web.akar(website)

        for h in halaman:
            per_jenis[h["jenis"]] = per_jenis.get(h["jenis"], 0) + 1
            if not args.dry_run:
                simpan(args.db, {"nama": nama, "website": root, **h})

        if not args.dry_run:
            con = sqlite3.connect(args.db)
            con.execute(DDL_LOG)
            con.execute(
                """INSERT INTO panen_log
                       (nama_normal, nama, website, jml_halaman, dicoba_pada)
                   VALUES (?,?,?,?,datetime('now'))
                   ON CONFLICT(nama_normal) DO UPDATE SET
                       nama        = excluded.nama,
                       website     = excluded.website,
                       jml_halaman = excluded.jml_halaman,
                       dicoba_pada = excluded.dicoba_pada,
                       -- Diagnosis lama dibuang HANYA kalau panen kali
                       -- ini berhasil; sebab kegagalan lama jadi basi.
                       sebab           = CASE WHEN excluded.jml_halaman > 0
                                              THEN NULL ELSE panen_log.sebab END,
                       sebab_detail    = CASE WHEN excluded.jml_halaman > 0
                                              THEN NULL ELSE panen_log.sebab_detail END,
                       didiagnosa_pada = CASE WHEN excluded.jml_halaman > 0
                                              THEN NULL ELSE panen_log.didiagnosa_pada END
                """,
                (normalisasi_nama(nama), nama, root, len(halaman)))
            con.commit()
            con.close()

        total_hal += len(halaman)
        if not halaman:
            tanpa_hal += 1

        jenis_ada = sorted({h["jenis"] for h in halaman})
        print(f"[{i}/{len(rows)}] {nama[:32]:<34} {len(halaman):>2} hal   "
              f"{', '.join(jenis_ada) if jenis_ada else '(kosong)'}")

        if not args.cache:
            time.sleep(JEDA_ANTAR_SITUS)

    print("\n--- ringkasan ---")
    print(f"perusahaan            {len(rows)}")
    print(f"tanpa halaman sama sekali  {tanpa_hal}")
    print(f"total halaman dipanen {total_hal}")
    print()
    for jenis in ["beranda", "seed"] + list(JENIS_HALAMAN):
        if jenis in per_jenis:
            print(f"  {jenis:<12} {per_jenis[jenis]}")
    if args.dry_run:
        print("\n(dry-run: tidak ada yang ditulis ke database)")


if __name__ == "__main__":
    sys.exit(main())
