"""
bps_ekstrak.py
==============
Ambil nama dan alamat perusahaan dari Direktori Industri Manufaktur BPS,
lalu simpan ke `data/bps.db`.

    python src/bps_ekstrak.py --halaman 40-80      # coba dulu
    python src/bps_ekstrak.py --periksa            # mutu, tanpa menulis
    python src/bps_ekstrak.py --tulis              # semuanya, ke bps.db

DASAR HUKUMNYA — baca sebelum mengubah apa pun di sini:
    BPS menjawab 3 Sep 2026 (SILASTIK #50964) bahwa nama dan alamat
    perusahaan dari publikasi ini **boleh dimanfaatkan tanpa izin
    tertulis**, karena larangan pada terbitannya menyasar
    **reproduksi/penerbitan kembali publikasi**, bukan pemakaian isinya.

    Karena itu modul ini HANYA mengambil nama dan alamat. Nilai produksi,
    jumlah tenaga kerja, dan kode KBLI tidak diambil -- bukan karena sulit,
    tapi karena itu di luar yang dinyatakan boleh.

    Hasilnya masuk `data/bps.db` yang TIDAK dilacak git. Repo ini publik;
    meng-commit-nya adalah persis penerbitan kembali yang dilarang.
    Penegaknya `src/publik.py`, dan `ekspor_csv.py` menolak jalan kalau
    ada yang bocor. Lihat CATATAN_SUMBER_DATA.md.

KENAPA pdfplumber DAN BUKAN pdftotext:
    Tiga mode pdftotext sudah diuji dan ketiganya gagal; angkanya ada di
    docs/CATATAN_EKSTRAKSI_PDF.md (yang terbaik cuma 44% record utuh,
    dengan batas nama yang sering salah). Sebabnya satu: teks yang sudah
    dirata kehilangan informasi yang justru dibutuhkan.

    Dengan koordinat, tiga cacat itu hilang sekaligus:

    1. KOLOM dipisah dari posisi x, bukan ditebak dari pola spasi.
       Awal kolom terbaca tegas di x = 70, 240, 400.
    2. WATERMARK dibuang dari TINGGI HURUFNYA. Teks isi tingginya <= 12;
       "https://www.bps.go.id" dirender 22-30.
    3. BATAS RECORD dibaca dari jarak vertikal. Antar baris dalam satu
       record 11,3; antar record >= 17.

    Penyaringan watermark dilakukan per KARAKTER, bukan per kata, dan itu
    bukan kerapian: pdfplumber menggabungkan huruf watermark dengan teks
    di sebelahnya jadi satu kata. Kata 's70852' adalah watermark 's'
    ditambah kode pos '70852'. Menyaring per kata akan ikut membuang kode
    posnya, dan tidak ada yang akan tahu.
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF = BASE / "data" / "direktori-industri-manufaktur-2025.pdf"
DB = BASE / "data" / "bps.db"
SUMBER = "bps-direktori-manufaktur-2025"

# Ambang, semuanya diukur dari PDF-nya sendiri (lihat docstring).
TINGGI_ISI_MAKS = 12       # di atas ini = watermark
BATAS_KOLOM = (235, 395)   # x0: <235 kolom 0, <395 kolom 1, sisanya kolom 2
JARAK_RECORD = 14.0        # jarak vertikal yang memisahkan dua record

DDL = """
CREATE TABLE IF NOT EXISTS perusahaan_bps (
    nama        TEXT NOT NULL,
    alamat      TEXT,
    halaman     INTEGER,
    kolom       INTEGER,
    bagian      TEXT,       -- kelompok industri, dari daftar isi
    sumber      TEXT,
    diambil_pada TEXT,
    PRIMARY KEY (nama, alamat)
);
"""

# KELOMPOK INDUSTRI — ini penyaring paling berharga di seluruh berkas ini.
#
# Direktorinya TIDAK alfabetis dari awal sampai akhir. Ia terbagi 24
# kelompok industri, dan tiap kelompok alfabetis A-Z sendiri. Ketahuan
# karena halaman 300 mulai "MIKALINDO", 700 "KURNIA", 1100 "GARDA" --
# urutannya mengulang.
#
# Batas antar bagian dideteksi dari titik urutan alfabet MUNDUR lintas
# halaman; hasilnya 23 batas, persis sejumlah judul di daftar isi
# (halaman 9-10). Dua sumber yang bebas satu sama lain memberi angka yang
# sama, jadi pemetaannya bukan tebakan.
#
# Nilainya: 35.136 nama tidak mungkin dibaca semua (~1.300 sesi pada
# langit-langit 25 perusahaan per sesi). Dengan kelompok ini, vertikal
# inti Salesmart -- makanan, minuman, farmasi -- bisa dipisahkan SEBELUM
# sepeser perhatian dikeluarkan, dan `industry_fit` praktis sudah
# diketahui tanpa membaca satu situs pun.
BAGIAN = [
    (19,   "Industri Makanan"),
    (285,  "Industri Minuman"),
    (319,  "Industri Pengolahan Tembakau"),
    (353,  "Industri Tekstil"),
    (423,  "Industri Pakaian Jadi"),
    (483,  "Industri Kulit, Barang dari Kulit dan Alas Kaki"),
    (515,  "Industri Kayu, Barang dari Kayu dan Gabus"),
    (557,  "Industri Kertas dan Barang dari Kertas"),
    (593,  "Industri Pencetakan dan Reproduksi Media Rekaman"),
    (637,  "Industri Produk dari Batu Bara dan Pengilangan Minyak Bumi"),
    (655,  "Industri Bahan Kimia dan Barang dari Bahan Kimia"),
    (745,  "Industri Farmasi, Produk Obat Kimia dan Obat Tradisional"),
    (769,  "Industri Karet, Barang dari Karet dan Plastik"),
    (881,  "Industri Barang Galian Bukan Logam"),
    (947,  "Industri Logam Dasar"),
    (987,  "Industri Barang Logam, Bukan Mesin dan Peralatannya"),
    (1065, "Industri Komputer, Barang Elektronik dan Optik"),
    (1091, "Industri Peralatan Listrik"),
    (1129, "Industri Mesin dan Perlengkapan YTDL"),
    (1177, "Industri Kendaraan Bermotor, Trailer dan Semi Trailer"),
    (1219, "Industri Alat Angkutan Lainnya"),
    (1253, "Industri Furnitur"),
    (1303, "Industri Pengolahan Lainnya"),
    (1337, "Industri Reparasi dan Pemasangan Mesin dan Peralatan"),
]

# Vertikal inti Salesmart: barang konsumsi bermerek yang didorong ke pasar
# lewat jaringan distribusi dan tim sales lapangan.
BAGIAN_INTI = {
    "Industri Makanan",
    "Industri Minuman",
    "Industri Farmasi, Produk Obat Kimia dan Obat Tradisional",
}


def bagian_halaman(nomor: int) -> str:
    """Kelompok industri untuk sebuah halaman. Kosong untuk halaman muka."""
    nama = ""
    for awal, judul in BAGIAN:
        if nomor >= awal:
            nama = judul
        else:
            break
    return nama

# Baris yang MENGAWALI alamat. Dipakai untuk menentukan di mana nama
# berhenti -- nama bisa membungkus tanpa koma ("CAKE BAKERY PASTRY" lalu
# "NABILA"), jadi tidak bisa sekadar mengambil baris pertama.
AWAL_ALAMAT = re.compile(
    r"^(JL\b|JLN\b|Jl\.|Jln\.|DESA\b|DSN\b|DUSUN\b|KP\.|KAMPUNG\b|KOMPLEK\b"
    r"|KOMP\.|PERUM\b|Kawasan\b|KAWASAN\b|BLOK\b|RT\b|RW\b|GG\b|Gg\.|Jalan\b)",
    re.IGNORECASE)
ADA_ALAMAT = re.compile(r"(Kec\.|Kab\.|Kota\s|\bRT\b|\bRW\b|\d{5}\b)")

PROVINSI = re.compile(
    r"(Jawa (Barat|Timur|Tengah)|DI Yogyakarta|DKI Jakarta|Banten|Bali"
    r"|Sumatera \w+|Kalimantan \w+|Sulawesi \w+|Nusa Tenggara \w+"
    r"|Kepulauan \w+|Riau|Jambi|Lampung|Aceh|Papua\w*|Maluku\w*|Bengkulu"
    r"|Gorontalo|Bangka Belitung)")


def _mirip_nama(t: str) -> bool:
    huruf = [c for c in t if c.isalpha()]
    if not huruf:
        return False
    return sum(1 for c in huruf if c.isupper()) / len(huruf) > 0.85


def baris_halaman(hal):
    """Baris teks per kolom, watermark sudah dibuang."""
    bersih = hal.filter(
        lambda o: o.get("object_type") != "char"
        or o.get("height", 99) <= TINGGI_ISI_MAKS)
    kata = bersih.extract_words()

    # BUANG YANG DI LUAR AREA HALAMAN.
    #
    # Sebagian halaman memuat SALINAN seluruh isinya di koordinat x
    # negatif (-520, -360, -190) -- tak terlihat waktu dibaca manusia,
    # tapi ikut terbaca pdfplumber. Halaman 41 punya 910 kata sementara
    # halaman 40 dan 42 masing-masing ~460: separuhnya salinan.
    #
    # Salinan itu jatuh ke kolom 0 (x < 235) dan menempel dengan isi
    # aslinya, menghasilkan record berisi empat perusahaan sekaligus:
    # "BALI EKSTRAK UTAMA BALI ES, PT BALI HIGHLANDS ORGANIK, ...".
    #
    # Ketahuan dari memverifikasi tiap nama ke teks mentah halamannya,
    # bukan dari membaca hasil yang kelihatan rapi.
    lebar = float(hal.width)
    kata = [w for w in kata if 0 <= w["x0"] <= lebar]

    kolom = [[], [], []]
    for w in kata:
        k = 0 if w["x0"] < BATAS_KOLOM[0] else (
            1 if w["x0"] < BATAS_KOLOM[1] else 2)
        kolom[k].append(w)

    for k, kk in enumerate(kolom):
        baris = {}
        for w in kk:
            baris.setdefault(round(w["top"], 1), []).append(w)
        urut = sorted(baris)
        blok, kini = [], []
        for i, t in enumerate(urut):
            teks = " ".join(w["text"]
                            for w in sorted(baris[t], key=lambda w: w["x0"]))
            teks = " ".join(teks.split())
            if kini and (t - urut[i - 1]) > JARAK_RECORD:
                blok.append(kini)
                kini = []
            if teks:
                kini.append(teks)
        if kini:
            blok.append(kini)
        yield k, blok


def pecah(blok):
    """Blok baris -> (nama, alamat). None kalau tidak meyakinkan."""
    if not blok:
        return None
    nama = []
    for i, b in enumerate(blok):
        if i and (AWAL_ALAMAT.search(b) or ADA_ALAMAT.search(b)
                  or not _mirip_nama(b)):
            break
        if not _mirip_nama(b):
            break
        nama.append(b)
    else:
        i = len(blok)
    if not nama:
        return None
    n = " ".join(nama)
    # "CAHAYA PILAR KENCANA," + "PT" -> rapatkan komanya
    n = re.sub(r",\s+", ", ", n).strip(" ,")
    a = " ".join(blok[len(nama):]).strip()
    if len(n) < 3 or len(n) > 120:
        return None
    return n, a


def ekstrak(halaman=None):
    import pdfplumber
    hasil = []
    with pdfplumber.open(PDF) as pdf:
        total = len(pdf.pages)
        rentang = halaman or range(1, total + 1)
        for nomor in rentang:
            if nomor < 1 or nomor > total:
                continue
            hal = pdf.pages[nomor - 1]
            for k, blok_kolom in baris_halaman(hal):
                for blok in blok_kolom:
                    p = pecah(blok)
                    if p:
                        hasil.append((p[0], p[1], nomor, k,
                                      bagian_halaman(nomor)))
    return hasil


def mutu(hasil):
    """Berapa yang alamatnya benar-benar lengkap. Angka ini yang menentukan
    layak-tidaknya dipakai, bukan jumlah barisnya."""
    n = len(hasil)
    prov = sum(1 for _, a, _, _, _ in hasil if PROVINSI.search(a or ""))
    pos = sum(1 for _, a, _, _, _ in hasil if re.search(r"\b\d{5}\b", a or ""))
    kosong = sum(1 for _, a, _, _, _ in hasil if not (a or "").strip())

    # DUA PERUSAHAAN MENEMPEL JADI SATU RECORD — cacat yang paling mahal,
    # karena hasilnya tetap terlihat masuk akal. Tandanya: satu nama
    # memuat lebih dari satu bentuk badan usaha, mis.
    # "BALI ES, PT BALI HIGHLANDS ORGANIK, ... BANGKIT GIAT USAHA".
    #
    # Pernah terjadi karena sebagian halaman memuat salinan isinya di
    # koordinat x negatif. Sudah ditambal, tapi pemeriksaannya ditinggal
    # di sini: ia berjalan sendiri di 1.392 halaman, sedangkan verifikasi
    # kata-per-kata ke teks mentah terlalu lambat untuk seluruh buku.
    # Ambangnya TIGA, bukan dua. "TBK, PT" adalah kombinasi yang SAH di
    # Indonesia -- CENTRAL PROTEINA PRIMA TBK, PT dan CHAROEN POKPHAND
    # INDONESIA TBK, PT memang bernama begitu. Ambang dua membuat
    # pemeriksa ini berteriak 25 kali untuk nama yang benar semua, dan
    # pemeriksa yang sering salah pada akhirnya diabaikan orang.
    bentuk = re.compile(r"\b(PT|CV|UD|TBK|PERSERO|PERUM|KOPERASI)\b")
    dobel = sum(1 for nm, _, _, _, _ in hasil if len(bentuk.findall(nm)) >= 3)

    panjang = sum(1 for nm, _, _, _, _ in hasil if len(nm) > 70)
    return {"total": n, "ada_provinsi": prov, "ada_kodepos": pos,
            "alamat_kosong": kosong, "nama_dobel": dobel,
            "nama_kepanjangan": panjang}


def simpan(hasil):
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    pada = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.executemany(
        "INSERT OR IGNORE INTO perusahaan_bps "
        "(nama, alamat, halaman, kolom, bagian, sumber, diambil_pada) "
        "VALUES (?,?,?,?,?,?,?)",
        [(n, a, h, k, b, SUMBER, pada) for n, a, h, k, b in hasil])
    con.commit()
    n = con.execute("SELECT count(*) FROM perusahaan_bps").fetchone()[0]
    con.close()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--halaman", default="",
                    help="rentang, mis. 40-80. Kosong = semua")
    ap.add_argument("--tulis", action="store_true")
    ap.add_argument("--contoh", type=int, default=6)
    args = ap.parse_args()

    if not PDF.exists():
        raise SystemExit(f"PDF tidak ada: {PDF}")

    rentang = None
    if args.halaman:
        a, _, b = args.halaman.partition("-")
        rentang = range(int(a), int(b or a) + 1)

    hasil = ekstrak(rentang)
    m = mutu(hasil)
    print(f"record terbaca   : {m['total']}")
    print(f"  ada provinsi   : {m['ada_provinsi']} "
          f"({m['ada_provinsi'] * 100 // max(m['total'], 1)}%)")
    print(f"  ada kode pos   : {m['ada_kodepos']} "
          f"({m['ada_kodepos'] * 100 // max(m['total'], 1)}%)")
    print(f"  alamat kosong  : {m['alamat_kosong']}")
    print(f"  nama DOBEL     : {m['nama_dobel']}  "
          f"(dua perusahaan menempel; harus 0)")
    print(f"  nama > 70 huruf: {m['nama_kepanjangan']}")
    print()
    for n, a, h, k, b in hasil[:args.contoh]:
        print(f"  [{h}/{k}] {n}   <{b}>")
        print(f"        {a[:96]}")

    if not args.tulis:
        print("\n(mode periksa; tidak ada yang ditulis. Tambahkan --tulis.)")
        return

    total = simpan(hasil)
    print(f"\nDitulis ke {DB.name}; kini {total} baris.")
    print("bps.db TIDAK dilacak git. Jalankan `python src/publik.py` "
          "sebelum commit berikutnya.")


if __name__ == "__main__":
    main()
