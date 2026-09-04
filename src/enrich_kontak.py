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

# Halaman yang menyebut LOKASI/ALAMAT. Dipakai sebagai langkah terakhir
# sebelum menebak path -- lihat cari_kontak() langkah 3b untuk alasannya
# dan untuk kenapa polanya boleh lebih longgar di posisi itu.
TEKS_LOKASI = re.compile(
    r"(\blokasi\b|\blocation(s)?\b|\balamat\b|kantor\s*kami|our\s*office"
    r"|office\s*location|alamat\s*kantor)", re.IGNORECASE)

# Halaman yang MENDAFTAR TEMPAT MILIK ORANG LAIN. Dikecualikan dari
# TEKS_LOKASI, dan bukan karena kehati-hatian teoretis.
#
# Waktu langkah 3b pertama dipasang (4 Sep 2026), uji A/B-nya langsung
# menunjukkan satu perbaikan dan satu KEMUNDURAN. Epson Indonesia
# berpindah dari nomor seluler ke
#     https://www.epson.co.id/Support/ServiceCenterLocator
# yang memuat 160+ nomor -- dan yang terpilih milik PT LAYSANDER
# TECHNOLOGY, mitra servis, bukan Epson. Deteksi daftar cabang menahannya
# dari kelas `langsung`, tapi nomor yang tersimpan tetap milik
# perusahaan lain: pola kegagalan Pronas, kali ini dibuat sendiri.
#
# Locator, dealer, dan daftar toko memang MENDAFTAR PIHAK LAIN. Itu
# sifat halamannya, bukan kecelakaan, jadi disaring dari judulnya.
BUKAN_LOKASI_SENDIRI = re.compile(
    r"(locator|service\s*cent|pusat\s*servis|dealer|reseller|distributor"
    r"|store\s*list|daftar\s*toko|mitra|partner)", re.IGNORECASE)

# Ditahan kecil: ini langkah cadangan, bukan penelusuran utama, dan
# polanya lebih longgar sehingga lebih mungkin menunjuk halaman keliru.
MAKS_LINK_LOKASI = 3


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
    # SELULER TIGA KELOMPOK, harus di ATAS pola umum supaya dicoba dulu:
    # "0813-888888-73". Pola umum berhenti di batas kata setelah kelompok
    # KEDUA dan menghasilkan 0813888888 -- 10 digit, lolos gerbang panjang,
    # dan menyambung ke orang lain kalau ditelepon. Ini yang terjadi pada
    # careline Danone 3 Sep 2026.
    (r"\b08\d{1,2}[\s\-\.]?\d{3,6}[\s\-\.]?\d{2,5}\b", "umum"),
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

# Penanda bahwa nomor itu milik ORANG, bukan perusahaan. Dicari ke DEPAN,
# dalam jendela sempit, dan sengaja terpisah dari KATA_BUKAN_TELEPON yang
# menengok ke belakang.
#
# KENAPA HARUS MENENGOK KE DEPAN: pada halaman cek undian Alfamart
# tertulis "No. HP: +62 8xx-xxxx-xxx Nama: <nama seorang pembeli>". Labelnya
# sendiri ("No. HP") justru label telepon yang SAH -- yang membuatnya
# terlarang adalah nama orang yang menempel SESUDAHNYA. Tanpa lihat ke
# depan, nomor seluler milik seorang pembeli tersimpan sebagai kontak
# perusahaan. Aturan proyek: data kontak level perusahaan saja (UU PDP).
#
# Jendelanya dijaga sempit (40 karakter) karena melebarkannya persis
# kesalahan yang dulu membuat penengokan ke depan dibuang: label field
# BERIKUTNYA ikut terbaca dan nomor yang sah malah dibuang.
KATA_DATA_PRIBADI = re.compile(
    r"(\bnama\b|atas\s*nama|\ba\.?n\.?\s|pemenang|peserta|pelanggan\s*yth)",
    re.IGNORECASE,
)

# Nomor yang bentuknya jelas contoh/isian formulir, bukan nomor sungguhan.
#   0821-2345-6789  -> deret naik 6 digit atau lebih
#   0812-3333-3333  -> satu digit diulang 7 kali atau lebih
# Keduanya praktis mustahil pada nomor Indonesia yang benar-benar dipakai.
_DERET_NAIK = re.compile(
    r"(?=(0123456|1234567|2345678|3456789|4567890))")
_DIGIT_DIULANG = re.compile(r"(\d)\1{6,}")


def nomor_contoh(digit: str) -> bool:
    """True kalau deretan angkanya berbentuk contoh, bukan nomor nyata."""
    return bool(_DERET_NAIK.search(digit) or _DIGIT_DIULANG.search(digit))


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
    if nomor_contoh(digit):
        return None
    return digit


def ekstrak_telepon(teks: str) -> list[tuple[str, str, int]]:
    """
    Return list of (nomor_ternormalisasi, tipe_pola, posisi_di_teks).

    Posisinya ikut dikembalikan supaya pemanggil bisa melihat KATA DI
    SEKITAR nomor -- itulah satu-satunya cara membedakan nomor kantor
    pusat dari salah satu dari 71 nomor cabang.

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
            if KATA_DATA_PRIBADI.search(teks[m.end():m.end() + 40]):
                continue

            nomor = normalisasi_telepon(m.group())

            # Masih ada angka yang menempel SESUDAH kecocokan, dan yang
            # cocok ini nomor seluler? Berarti pola berhenti di tengah
            # nomor. Buang, jangan simpan potongannya -- lebih baik tidak
            # punya nomor daripada punya nomor yang salah sambung.
            # Nomor kantor sengaja TIDAK ikut aturan ini: "021-4203047-48"
            # itu notasi RENTANG, dan bagian pertamanya sudah bisa
            # ditelepon apa adanya.
            #
            # SPASI TIDAK DIHITUNG sebagai penyambung. Kalau ikut dihitung,
            # nomor yang UTUH pun terbuang begitu ada nomor lain
            # sesudahnya -- "0813-888888-73 0-800-13-60360" persis
            # bentuk itu, dan gerbangnya justru membuang jawaban benarnya.
            if (nomor and nomor.startswith("628")
                    and re.match(r"[\-\.]\d", teks[m.end():m.end() + 2])):
                continue
            if nomor and nomor not in terlihat:
                terlihat.add(nomor)
                hasil.append((nomor, tipe, m.start()))
    return hasil


# --------------------------------------------------------------------------
# Klasifikasi kualitas kontak
# (mencerminkan aturan yang sudah ada di rubrik.py)
# --------------------------------------------------------------------------

def klasifikasi_telepon(nomor: str, tipe_pola: str) -> str:
    """
    'layanan'  -> call center / customer service, bukan jalur kantor
    'langsung' -> kemungkinan jalur kantor

    Kelas 'cabang' TIDAK diputuskan di sini: ia tidak bisa dikenali dari
    bentuk nomornya, hanya dari halaman tempat nomor itu berdiri. Lihat
    cari_kontak().
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


PERINGKAT_KELAS = {"langsung": 0, "cabang": 1, "seluler": 2, "layanan": 3}
MAKS_LINK_KONTAK = 4

# Penanda bahwa nomor di dekatnya adalah KANTOR PUSAT.
#
# KENAPA PERLU: halaman kontak TIKI memuat 71 nomor -- satu per cabang,
# dari Ambon sampai Sorong. Semuanya sah, semuanya berkelas "langsung",
# dan pemilih lama mengambil yang KEBETULAN muncul pertama: 0911 347857,
# cabang Ambon. Orang sales yang menelepon dari antrian akan menelepon
# cabang Ambon untuk menawarkan sistem ke perusahaan berkantor pusat di
# Jakarta.
#
# Nomor cabang tidak salah sebagai data; ia salah sebagai NOMOR YANG
# DITELEPON DULUAN. Jadi yang diubah bukan apa yang dipanen, melainkan
# mana yang dipilih jadi nomor utama.
PENANDA_PUSAT = re.compile(
    r"(kantor\s*pusat|head\s*office|kantor\s*utama|pusat\s*informasi)",
    re.IGNORECASE,
)

# Sejauh mana ke belakang penanda itu dicari dari posisi nomornya.
# Cukup untuk menampung "Kantor Pusat PT X, Jl ... Telp." dalam satu
# blok alamat, tapi tidak sampai menyeberang ke blok cabang berikutnya.
JENDELA_PUSAT = 300

# Penanda bahwa nomor di dekatnya LAYANAN KONSUMEN, bukan jalur kantor.
#
# KENAPA PERLU, dan kenapa bentuk nomornya tidak cukup: halaman kontak
# sasa.co.id memuat
#
#   "Layanan Konsumen  Untuk pertanyaan terkait produk, saran, ...
#    silakan menghubungi layanan konsumen kami.  +62 21 5616293
#    Kantor Pusat Sasa Inti  Jl. Letjen S. Parman Kav. 32-34 ..."
#
# Nomornya landline Jakarta biasa -- tidak 1500, tidak 0804 -- jadi
# klasifikasi_telepon() menyebutnya 'langsung'. Dan blok "Kantor Pusat"
# di bawahnya justru TIDAK memuat nomor sama sekali. Hasilnya: nomor
# layanan konsumen naik jadi jalur kantor prioritas tertinggi.
#
# Ini pengulangan pelajaran TIKI dan Pronas dengan wajah ketiga: yang
# menentukan sebuah nomor itu APA bukan bentuknya, melainkan label yang
# berdiri di depannya.
PENANDA_LAYANAN = re.compile(
    r"(layanan\s*(konsumen|pelanggan)|customer\s*(service|care)|"
    r"call\s*center|pusat\s*layanan|hubungi\s*layanan)",
    re.IGNORECASE,
)

# Lebih sempit daripada JENDELA_PUSAT. Judul "Layanan Konsumen" berdiri
# tepat di atas nomornya; jendela lebar justru membuat satu judul di
# puncak halaman menurunkan setiap nomor di bawahnya.
JENDELA_LAYANAN = 200


# Penanda bahwa nomor di dekatnya milik CABANG, bukan kantor pusat.
#
# Anggota ketiga dari keluarga yang sama, dan ditemukan dengan cara yang
# sama: halaman kontak airnavindonesia.co.id memuat
#
#   "AirNav Kantor Cabang JATSC Gedung 611 ... Telp. +62 21-5506122
#    AirNav Kantor Cabang MATSC ... Telp. +62 411-4813210
#    Head Office Gedung AirNav Indonesia Jl. Ir. H. Juanda No.1 ..."
#
# Nomor pertama landline Jakarta yang sah, dan kantor pusatnya memang
# ADA di halaman itu — tapi berdiri SESUDAHNYA. Deteksi daftar cabang
# yang lama tidak menolong: ia menuntut 5+ nomor kantor, sementara
# halaman ini cuma punya tiga.
#
# PENANDA_PUSAT menengok ke belakang dan tidak menemukan apa-apa, jadi
# nomor cabang menang. Yang menyelesaikannya bukan menambah jendela,
# melainkan mengenali label cabang itu sendiri.
PENANDA_CABANG = re.compile(
    r"(kantor\s*cabang|cabang\s+[A-Z]|branch\s*office|kantor\s*perwakilan|"
    r"kantor\s*wilayah)",
    re.IGNORECASE,
)

JENDELA_CABANG = 200


# Nama badan hukum yang berdiri di dalam teks halaman.
#
# KENAPA PERLU: 4 Sep 2026 pemanen nomor hampir menyimpan 021 3503881
# sebagai kontak Agel Langgeng. Nomor itu berdiri persis di bawah
# "PT. Kapal Api Global" di kapalapiglobal.com -- situs INDUK. Bentuk
# nomornya sah, halamannya sah, label "Kantor Pusat" pun ada; yang
# membuatnya salah cuma satu hal, dan hal itu TERTULIS di halaman:
# nama perusahaan lain.
#
# Kesalahan yang sama sudah pernah nyaris masuk lewat pronas.co.id
# (nomor PT Bahtera Wiraniaga Internusa). Dua kali, dan dua-duanya
# ketahuan cuma karena ada orang yang memeriksa dengan tangan.
# Kata pertama nama dipaksa >=3 huruf. Tanpa itu regex ini menangkap
# potongan seperti "PT L" lalu melaporkannya sebagai badan hukum lain --
# kena Lola Mina, 4 Sep 2026. Nama perusahaan tidak pernah sepatah huruf.
#
# BATAS YANG DIAKUI, bukan dibereskan: singkatan tidak dikenali. Nomor
# "Industri Nuklir Indonesia" ditandai berdiri di bawah "PT INUKI" --
# padahal INUKI adalah singkatan namanya sendiri. Mencocokkan singkatan
# butuh kamus yang tidak kita punya, dan karena penjaga ini hanya
# MELAPOR, positif palsu semacam itu cuma menambah satu baris untuk
# dibaca orang, bukan membuang nomor yang benar.
PENANDA_BADAN_HUKUM = re.compile(
    r"\b(?:PT|CV|UD)\.?\s+((?:[A-Z][\w'’\-]{2,})(?:\s+[A-Z][\w'’\-]*){0,5})")

# Sejauh mana ke belakang nama badan hukum dicari dari posisi nomornya.
# Selebar blok alamat: "PT X, Jl ..., Kota ..., Telp." muat, tapi tidak
# menyeberang ke blok perusahaan berikutnya.
JENDELA_BADAN = 240

# Kata yang tidak membedakan satu perusahaan dari yang lain.
_KATA_UMUM = {"PT", "CV", "UD", "TBK", "PERSERO", "INDONESIA", "GROUP",
              "GLOBAL", "JAYA", "UTAMA", "MAKMUR", "SEJAHTERA", "MANDIRI",
              "ABADI", "PERKASA", "INTERNATIONAL", "NUSANTARA", "PRIMA"}


def _token(nama: str) -> set:
    """Kata pembeda dari sebuah nama perusahaan."""
    kata = re.findall(r"[A-Za-z][\w'’]*", (nama or "").upper())
    return {k for k in kata if len(k) > 3 and k not in _KATA_UMUM}


def entitas_asing(nama_lead: str, teks: str, posisi: int) -> str | None:
    """Nama badan hukum LAIN yang berdiri paling dekat di depan nomor.

    Return nama itu kalau ditemukan, None kalau tidak ada nama sama
    sekali ATAU nama terdekatnya memang perusahaan yang dicari.

    KETIADAAN NAMA BUKAN ALASAN MENOLAK. Halaman kontak Cimory menulis
    "CIMORY TOWER ... Contact: (021) 5874630" tanpa menyebut badan
    hukumnya sama sekali, dan nomor itu benar. Yang menolak hanyalah
    nama LAIN yang hadir -- bukan nama sendiri yang absen.
    """
    if not nama_lead:
        return None
    milik = _token(nama_lead)
    if not milik:
        return None
    awal = max(0, posisi - JENDELA_BADAN)
    kandidat = list(PENANDA_BADAN_HUKUM.finditer(teks[awal:posisi]))
    if not kandidat:
        return None
    m = kandidat[-1]                       # yang paling dekat ke nomor
    ketemu = m.group(1)
    if _token(ketemu) & milik:
        return None
    return f"PT {ketemu}".strip()


def _label_terdekat(teks: str, posisi: int) -> str | None:
    """Label mana yang berdiri PALING DEKAT di depan sebuah nomor.

    Bukan sekadar "ada atau tidak": satu halaman kontak sering memuat
    kedua label, dan yang menentukan arti sebuah nomor adalah label
    yang paling akhir sebelum ia -- bukan label mana pun yang kebetulan
    ada di halaman itu.

    Return 'pusat', 'layanan', 'cabang', atau None.
    """
    awal_p = max(0, posisi - JENDELA_PUSAT)
    awal_l = max(0, posisi - JENDELA_LAYANAN)
    awal_c = max(0, posisi - JENDELA_CABANG)
    cocok = []
    for m in PENANDA_PUSAT.finditer(teks[awal_p:posisi]):
        cocok.append((awal_p + m.end(), "pusat"))
    for m in PENANDA_LAYANAN.finditer(teks[awal_l:posisi]):
        cocok.append((awal_l + m.end(), "layanan"))
    for m in PENANDA_CABANG.finditer(teks[awal_c:posisi]):
        cocok.append((awal_c + m.end(), "cabang"))
    if not cocok:
        return None
    return max(cocok)[1]

# Halaman yang isinya DAFTAR CABANG, bukan kontak perusahaan.
PENANDA_DAFTAR_CABANG = re.compile(
    r"(kontak\s*cabang|daftar\s*cabang|cabang\s*kami|lokasi\s*cabang|"
    r"branch\s*(list|office|network)|daftar\s*(kantor|gerai|outlet))",
    re.IGNORECASE,
)

# Kalau satu halaman memuat sebanyak ini nomor kantor tanpa satu pun
# penanda kantor pusat, ia daftar cabang walau judulnya tidak berkata
# begitu. Halaman kontak biasa memuat satu sampai tiga nomor.
AMBANG_DAFTAR_CABANG = 5


def cari_kontak(website: str, nama: str = "") -> dict:
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
    # (nomor, kelas, url, pusat) -- `pusat` True kalau di teks halaman
    # nomor itu berdiri di dekat penanda "Kantor Pusat"/"Head Office".
    ditemukan: list[tuple[str, str, str, bool]] = []

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

        kelas_awal = [(n, klasifikasi_telepon(n, tipe), posisi)
                      for n, tipe, posisi in nomor]
        label = {posisi: _label_terdekat(teks, posisi)
                 for _, _, posisi in kelas_awal}
        pusat = {pos: (lab == "pusat") for pos, lab in label.items()}

        # Landline yang berdiri di bawah judul layanan konsumen TURUN
        # kelas sebelum apa pun dihitung -- termasuk sebelum jumlah
        # "nomor kantor" dipakai menebak halaman daftar cabang.
        # Landline turun kelas menurut label terdekat di depannya:
        # judul layanan konsumen -> `layanan`, judul kantor cabang ->
        # `cabang`. Keduanya sebelum apa pun dihitung, termasuk sebelum
        # jumlah "nomor kantor" dipakai menebak halaman daftar cabang.
        TURUN = {"layanan": "layanan", "cabang": "cabang"}
        kelas_awal = [
            (n, TURUN.get(label[pos], k) if k == "langsung" else k, pos)
            for n, k, pos in kelas_awal]

        # NOMOR YANG BERDIRI DI BAWAH NAMA BADAN HUKUM LAIN DILAPORKAN,
        # TIDAK DIBUANG. Percobaan pertama membuangnya, dan uji A/B ke 61
        # nomor tersimpan langsung menolaknya: lima hasil berubah dan tiga
        # di antaranya MUNDUR -- PT. Erela kembali ke nomor OSM yang sudah
        # terbukti salah, TransTRACK turun dari jalur kantor ke seluler,
        # dan R2plan jadi TERPOTONG SATU DIGIT karena nomor utuhnya dibuang
        # lalu potongan yang tumpang tindih menang.
        #
        # Sebabnya jelas sesudah dilihat: halaman perusahaan wajar menyebut
        # mitra, klien, atau anggota grup di dekat nomornya sendiri. Nama
        # lain yang hadir BUKAN bukti nomor itu milik orang lain.
        #
        # Jadi sinyalnya disimpan, bukan dipakai memutus. Ia muncul di
        # ringkasan jalan supaya orang yang menulis ke database melihatnya
        # -- persis kasus Agel Langgeng, yang tertangkap 4 Sep 2026 hanya
        # karena ada orang yang memeriksa dengan tangan.
        for n, k, pos in kelas_awal:
            asing = entitas_asing(nama, teks, pos)
            if asing:
                log(f"{n} berdiri di bawah {asing!r}, bukan {nama!r}")
                catatan.setdefault("entitas_asing", []).append(f"{n}: {asing}")

        # Daftar cabang? Nomornya sah semua, tapi tidak satu pun kantor
        # pusat -- dan yang muncul pertama cuma kebetulan. Halaman kontak
        # TIKI memuat 71 nomor berurut dari Ambon; tanpa aturan ini, orang
        # sales menelepon cabang Ambon untuk menawarkan sistem nasional.
        jml_kantor = sum(1 for _, k, _ in kelas_awal if k == "langsung")
        daftar_cabang = (
            bool(PENANDA_DAFTAR_CABANG.search(teks))
            or jml_kantor >= AMBANG_DAFTAR_CABANG
        ) and not any(pusat.values())
        if daftar_cabang:
            log(f"halaman ini daftar cabang ({jml_kantor} nomor kantor, "
                f"tanpa penanda kantor pusat) -- dicatat sebagai cabang")

        for n, kelas, posisi in kelas_awal:
            if kelas == "langsung" and daftar_cabang:
                kelas = "cabang"
            ditemukan.append((n, kelas, url, pusat[posisi]))

        # Berhenti hanya kalau yang didapat jalur kantor DAN kelihatan
        # kantor pusat. Kalau yang ketemu baru nomor cabang, teruskan --
        # halaman lain mungkin memuat kantor pusatnya.
        return any(k == "langsung" and p for _, k, _, p in ditemukan)

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

    # 3b. Halaman LOKASI/ALAMAT — hanya kalau halaman kontak gagal.
    #
    # KENAPA ADA, dan kenapa baru di sini: nomor kantor PT Madusari
    # Nusaperdana (lead berskor 95, tertinggi yang kami punya) ada di
    #     https://www.madusarifoods.com/page/lokasi
    # di bawah judul "Marketing Office" bersama nama badan hukumnya.
    # Halaman /kontak-nya sendiri NOL nomor telepon. Modul ini cuma
    # menelusuri link ber-teks kontak/contact/hubungi, jadi halaman itu
    # tidak pernah dilihat, dan nomornya akhirnya ditemukan agen.
    #
    # Ditaruh SESUDAH langkah 3 dan dijaga `if not selesai` karena
    # polanya lebih longgar daripada TEKS_KONTAK: diukur 4 Sep 2026, ia
    # cocok di 24 situs tapi sebagian besar derau (publikasi BCG, SDK
    # TomTom, artikel berita ber-judul "lokasi"). Sebagai langkah
    # terakhir, derau itu cuma memakan satu-dua request pada situs yang
    # memang belum memberi apa pun — dan nomor yang salah tetap disaring
    # _label_terdekat serta pemeriksaan bentuk di bawah.
    if not selesai:
        html, _ = ambil_html(beranda)
        if html:
            kandidat = [u for u in cari_link(html, root, TEKS_LOKASI)
                        if not BUKAN_LOKASI_SENDIRI.search(u)]
            for url in kandidat[:MAKS_LINK_LOKASI]:
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

    # Kelas dulu (kantor > seluler > call center), baru penanda kantor
    # pusat. Urutan kemunculan cuma jadi pemutus terakhir -- dulu ia
    # satu-satunya pemutus, dan itulah yang menyerahkan TIKI ke cabang
    # Ambon.
    ditemukan.sort(key=lambda x: (PERINGKAT_KELAS.get(x[1], 9), not x[3]))
    nomor, kelas, url, _ = ditemukan[0]

    # dedup, urutan dipertahankan
    semua, terlihat = [], set()
    for n, _, _, _ in ditemukan:
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
    peringatan_asing = []

    for i, row in enumerate(rows, 1):
        nama = row["nama"].strip()
        website = row["website"].strip()
        if not website:
            continue

        hasil = cari_kontak(website, nama)
        hasil["nama"] = nama
        hasil["sumber_discovery"] = row.get("sumber", "")

        asing = hasil.pop("entitas_asing", None)
        if asing:
            peringatan_asing.append((nama, asing))
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

    # Peringatan situs induk. TIDAK menghentikan apa pun -- sinyalnya
    # terlalu berisik untuk memutus (lihat cari_kontak), tapi cukup
    # berguna untuk dibaca orang sebelum menulis ke database.
    if peringatan_asing:
        print(f"\nPERIKSA TANGAN — {len(peringatan_asing)} nomor berdiri di "
              "bawah nama badan hukum LAIN:")
        for nama, daftar in peringatan_asing:
            for baris in daftar:
                print(f"  {nama[:34]:<36} {baris[:70]}")
        print("  (nomor tetap disimpan; ini bukan vonis, cuma sinyal)")


if __name__ == "__main__":
    sys.exit(main())