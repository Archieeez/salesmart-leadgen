"""
enrich_kontak.py
----------------
Ambil nomor telepon kantor dari website resmi perusahaan.

Kenapa modul ini ada:
    Sumber discovery (GAPMMI, BPS, IDX, asosiasi) memberi NAMA dan/atau
    WEBSITE perusahaan, tapi hampir tidak pernah memberi NOMOR TELEPON.
    Modul ini menutup celah itu, sehingga sumber discovery mana pun
    bisa dipakai tanpa harus lengkap sendiri.

Prinsip:
    - Hanya mengambil data KONTAK PERUSAHAAN (bukan data pribadi).
      Sesuai batasan UU PDP yang sudah jadi ruang lingkup proyek ini.
    - WAJIB patuh robots.txt. Kalau situs melarang, dilewati dan dicatat.
    - Rate limit sopan. Ini bukan lomba kecepatan.

Pakai:
    python enrich_kontak.py --input seed_gapmmi.csv --db ../data/leads.db
    python enrich_kontak.py --input seed_gapmmi.csv --dry-run
"""

import argparse
import csv
import re
import sqlite3
import sys
import time

from urllib.parse import urljoin

import web
from web import (
    JEDA_ANTAR_SITUS,
    ambil_html,
    ambil_teks,
    boleh_ambil,
    cari_link,
    dari_cache,
    jeda_halaman,
    log,
)

# Halaman yang paling sering memuat nomor telepon kantor.
# Dipakai sebagai CADANGAN terakhir, kalau link kontak asli tidak ketemu
# karena navigasinya dirender JavaScript.
KANDIDAT_PATH = [
    "/contact", "/contact-us", "/contactus",
    "/kontak", "/kontak-kami", "/hubungi-kami", "/hubungi",
    "/id/kontak", "/en/contact",
    "/about/contact", "/tentang-kami/kontak",
    "/",
]

TEKS_KONTAK = re.compile(r"(kontak|contact|hubungi|reach\s*us)", re.IGNORECASE)


def link_kontak(html: str, root: str) -> list[str]:
    return cari_link(html, root, TEKS_KONTAK)


# --------------------------------------------------------------------------
# Ekstraksi nomor telepon Indonesia
# --------------------------------------------------------------------------

# Beberapa pola dipisah supaya bisa dibedakan saat klasifikasi.
POLA_TELEPON = [
    # Layanan pelanggan 4 digit: 1500-123, 1500123
    (r"\b1500[\s\-\.]?\d{3}\b", "layanan"),
    # Layanan pelanggan 0804: 0804-1-500500
    (r"\b0804[\s\-\.]?\d[\s\-\.]?\d{6}\b", "layanan"),
    # Format internasional: +62 21 1234 5678
    (r"\+62[\s\-\.]?\(?\d{2,3}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,5}", "umum"),
    # Kode area dalam kurung: (021) 1234 5678
    (r"\(0\d{2,3}\)[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,5}", "umum"),
    # Kode area polos: 021-1234 5678 / 0318412497
    # Catatan: notasi rentang seperti "4203047-48" sengaja TIDAK diperluas.
    # Yang diambil hanya nomor pertama.
    (r"\b0\d{2,3}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,5}\b", "umum"),
]

# Kata di sekitar angka yang menandakan itu BUKAN telepon.
KATA_BUKAN_TELEPON = re.compile(
    r"(npwp|nib|rekening|norek|va\b|virtual account|kode pos|"
    r"izin|sertifikat|isbn|issn|nomor induk|siup|tdp)",
    re.IGNORECASE,
)


def normalisasi_telepon(mentah: str) -> str | None:
    """Ubah ke format 62xxxxxxxxx. Return None kalau tidak masuk akal."""
    digit = re.sub(r"\D", "", mentah)

    if digit.startswith("62"):
        pass
    elif digit.startswith("0"):
        digit = "62" + digit[1:]
    elif digit.startswith("1500") or digit.startswith("140"):
        return digit  # nomor pendek, tidak pakai kode negara
    else:
        return None

    # Nomor Indonesia yang wajar: 62 + kode area + nomor = 10..13 digit.
    # Lebih dari 13 hampir selalu dua nomor yang tertulis menyatu, misal
    # "(021) 4287 3888/89" -> 62214287388889. Itu bukan satu nomor.
    if not (10 <= len(digit) <= 13):
        return None
    return digit


def ekstrak_telepon(teks: str) -> list[tuple[str, str]]:
    """
    Return list of (nomor_ternormalisasi, tipe_pola).
    Sudah dedup, urutan dipertahankan.
    """
    hasil = []
    terlihat = set()

    for pola, tipe in POLA_TELEPON:
        for m in re.finditer(pola, teks):
            # Buang kalau LABEL DI DEPANNYA menandakan ini bukan telepon.
            # Hanya menengok ke belakang: kalau ikut menengok ke depan,
            # label milik field BERIKUTNYA ikut terbaca dan nomor yang
            # sah malah dibuang.
            awal = max(0, m.start() - 40)
            if KATA_BUKAN_TELEPON.search(teks[awal:m.start()]):
                continue

            nomor = normalisasi_telepon(m.group())
            if nomor and nomor not in terlihat:
                terlihat.add(nomor)
                hasil.append((nomor, tipe))
    return hasil


# --------------------------------------------------------------------------
# Klasifikasi kualitas kontak
# (mencerminkan aturan yang sudah ada di rubrik.py)
# --------------------------------------------------------------------------

def klasifikasi_telepon(nomor: str, tipe_pola: str) -> str:
    """
    'layanan'  -> call center / customer service, bukan jalur kantor
    'langsung' -> kemungkinan jalur kantor
    """
    if tipe_pola == "layanan":
        return "layanan"
    if nomor.startswith("1500") or nomor.startswith("62804"):
        return "layanan"
    # 628xx = nomor seluler. Untuk perusahaan besar ini biasanya
    # nomor WA sekretariat, bukan jalur kantor resmi.
    if nomor.startswith("628"):
        return "seluler"
    return "langsung"


PERINGKAT_KELAS = {"langsung": 0, "seluler": 1, "layanan": 2}
MAKS_LINK_KONTAK = 4


def cari_kontak(website: str) -> dict:
    """
    Telusuri halaman kontak sampai ketemu JALUR KANTOR.

    Berhenti begitu dapat nomor apa pun terbukti salah: call center dan
    nomor seluler ikut terhitung "ok" padahal bukan jalur kantor.
    Sekarang penelusuran lanjut sampai dapat 'langsung', dan yang lebih
    buruk hanya dipakai kalau tidak ada yang lebih baik.
    """
    root, path_seed = web.akar(website)

    catatan = {
        "website": root,
        "telepon": None,
        "kelas_kontak": None,
        "sumber_halaman": None,
        "semua_nomor": [],
        "status": "tidak_ketemu",
        "hal": 0,          # jumlah halaman yang BERHASIL dibaca
    }

    diperiksa: set[str] = set()
    ditemukan: list[tuple[str, str, str]] = []   # (nomor, kelas, url)

    def periksa(url: str) -> bool:
        """Return True kalau sudah dapat jalur kantor (boleh berhenti)."""
        url = url.split("#")[0]
        if url in diperiksa:
            return False
        diperiksa.add(url)

        if not boleh_ambil(url):
            log(f"robots melarang {url}")
            catatan.setdefault("_ditolak_robots", 0)
            catatan["_ditolak_robots"] += 1
            return False

        teks = ambil_teks(url)
        jeda_halaman(url)
        if not teks:
            return False

        catatan["hal"] += 1
        nomor = ekstrak_telepon(teks)
        if not nomor:
            log(f"halaman terbaca ({len(teks)} char) tapi 0 nomor cocok")
            return False

        for n, tipe in nomor:
            ditemukan.append((n, klasifikasi_telepon(n, tipe), url))
        return any(k == "langsung" for _, k, _ in ditemukan)

    # --- urutan penelusuran ---------------------------------------------
    # 1. Homepage duluan: sumber link kontak yang sebenarnya.
    beranda = urljoin(root, "/")
    selesai = periksa(beranda)

    # 2. Path yang ditunjuk seed CSV. Sebelumnya dibuang begitu saja,
    #    padahal seed sengaja menunjuk halaman dalam.
    if not selesai and path_seed not in ("", "/"):
        selesai = periksa(urljoin(root, path_seed))

    # 3. Link kontak asli dari homepage.
    if not selesai:
        html, _ = ambil_html(beranda)
        if html:
            for url in link_kontak(html, root)[:MAKS_LINK_KONTAK]:
                if periksa(url):
                    selesai = True
                    break

    # 4. Terakhir baru menebak path — untuk situs yang navigasinya
    #    dirender JavaScript sehingga <a> tidak terbaca.
    if not selesai:
        for path in KANDIDAT_PATH:
            if periksa(urljoin(root, path)):
                break

    # --- putuskan ---------------------------------------------------------
    if not ditemukan:
        if catatan.pop("_ditolak_robots", 0) and catatan["hal"] == 0:
            catatan["status"] = "robots_disallowed"
        return catatan
    catatan.pop("_ditolak_robots", None)

    ditemukan.sort(key=lambda x: PERINGKAT_KELAS.get(x[1], 9))
    nomor, kelas, url = ditemukan[0]

    # dedup, urutan dipertahankan
    semua, terlihat = [], set()
    for n, _, _ in ditemukan:
        if n not in terlihat:
            terlihat.add(n)
            semua.append(n)

    catatan["telepon"] = nomor
    catatan["kelas_kontak"] = kelas
    catatan["sumber_halaman"] = url
    catatan["semua_nomor"] = semua
    catatan["status"] = "ok"
    return catatan


# --------------------------------------------------------------------------
# Penyimpanan
# --------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS kontak_web (
    nama_normal     TEXT PRIMARY KEY,
    nama            TEXT NOT NULL,
    website         TEXT,
    telepon         TEXT,
    kelas_kontak    TEXT,
    sumber_halaman  TEXT,
    semua_nomor     TEXT,
    status          TEXT,
    sumber_discovery TEXT,
    diambil_pada    TEXT DEFAULT CURRENT_TIMESTAMP
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
        """INSERT OR REPLACE INTO kontak_web
           (nama_normal, nama, website, telepon, kelas_kontak,
            sumber_halaman, semua_nomor, status, sumber_discovery)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            normalisasi_nama(baris["nama"]),
            baris["nama"],
            baris["website"],
            baris["telepon"],
            baris["kelas_kontak"],
            baris["sumber_halaman"],
            ",".join(baris["semua_nomor"]),
            baris["status"],
            baris.get("sumber_discovery", ""),
        ),
    )
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV: nama,website,sumber")
    ap.add_argument("--db", default="../data/leads.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="tampilkan hasil, jangan tulis ke database")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true",
                    help="tampilkan tiap request beserta alasan gagalnya")
    ap.add_argument("--cache", default="",
                    help="folder cache HTML mentah; kosong = tanpa cache")
    args = ap.parse_args()

    web.setel(verbose=args.verbose, cache_dir=args.cache or None)

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    ringkasan = {"ok": 0, "tidak_ketemu": 0, "robots_disallowed": 0}
    kelas_hitung = {"langsung": 0, "seluler": 0, "layanan": 0}

    for i, row in enumerate(rows, 1):
        nama = row["nama"].strip()
        website = row["website"].strip()
        if not website:
            continue

        hasil = cari_kontak(website)
        hasil["nama"] = nama
        hasil["sumber_discovery"] = row.get("sumber", "")

        ringkasan[hasil["status"]] = ringkasan.get(hasil["status"], 0) + 1
        kk = hasil["kelas_kontak"]
        if kk:
            kelas_hitung[kk] = kelas_hitung.get(kk, 0) + 1

        if args.verbose:
            print(f"  --- {nama} ({hasil['website']})")
        print(
            f"[{i}/{len(rows)}] {nama:<32} "
            f"{hasil['status']:<18} "
            f"hal={hasil.get('hal', 0):<3} "
            f"{hasil['telepon'] or '-':<16} "
            f"{kk or '-'}"
        )

        if not args.dry_run:
            simpan(args.db, hasil)

        if not args.cache:
            time.sleep(JEDA_ANTAR_SITUS)

    print("\n--- ringkasan ---")
    for k, v in ringkasan.items():
        print(f"{k:<22} {v}")
    total = sum(ringkasan.values()) or 1
    print()
    for k, v in kelas_hitung.items():
        print(f"kelas {k:<16} {v}")
    print()
    ok = ringkasan.get("ok", 0)
    langsung = kelas_hitung.get("langsung", 0)
    print(f"hit rate umum          {ok / total:6.1%}  ({ok}/{total})")
    print(f"hit rate JALUR KANTOR  {langsung / total:6.1%}  ({langsung}/{total})"
          f"   <-- angka yang dinilai")


if __name__ == "__main__":
    sys.exit(main())