"""
publik.py
=========
Satu tempat yang memutuskan: baris ini boleh terbit ke publik atau tidak.

KENAPA MODUL INI ADA, dan kenapa ia keras:
    BPS menjawab 3 Sep 2026 bahwa nama dan alamat perusahaan dari
    Direktori Industri Manufaktur boleh dimanfaatkan tanpa izin tertulis
    -- karena larangan pada terbitannya menyasar **reproduksi/penerbitan
    kembali publikasi**, bukan pemakaian isinya.

    Kalimat yang sama menetapkan batasnya. Repo ini PUBLIK: `data/*.csv`
    dilacak git dan `docs/*.html` tayang di GitHub Pages. Menaruh baris
    berasal-BPS ke sana adalah persis penerbitan kembali yang dilarang.

    Bryan juga sudah menyanggupinya tertulis kepada BPS. Jadi ini bukan
    kehati-hatian yang dipilih sendiri; ini garis antara yang diizinkan
    dan yang dilarang.

    Aturan yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa
    ada yang sengaja melanggarnya. Karena itu modul ini bukan cuma
    menyediakan penyaring -- ia juga PEMERIKSA yang bisa dijalankan dan
    GAGAL dengan berisik.

CARA DIPAKAI:
    from publik import boleh_terbit
    if not boleh_terbit(baris_sumber): lewati

    python src/publik.py        # periksa seluruh keluaran; exit 1 kalau bocor
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Sumber yang isinya TIDAK BOLEH ikut terbit. Dicocokkan sebagai awalan,
# supaya "bps-direktori-manufaktur-2025" dan "bps-direktori-sumut-2023"
# ikut tertangkap tanpa perlu didaftar satu per satu.
SUMBER_DILINDUNGI = ("bps",)

# Berkas yang BENAR-BENAR terbit: dilacak git di repo publik, atau tayang
# lewat GitHub Pages.
KELUARAN_PUBLIK = [
    "data/leads_export.csv",
    "data/leads_arsip_export.csv",
    "data/kontak_web_export.csv",
    "data/kebutuhan_export.csv",
    "docs/index.html",
    "docs/teknis.html",
    "docs/agen.html",
]

# Database kerja untuk baris berasal-BPS. TIDAK dilacak git, sama seperti
# bukti.db. Dipisah supaya batasnya struktural, bukan bergantung pada
# ingatan orang yang menulis query berikutnya.
DB_BPS = BASE / "data" / "bps.db"

# Sejak 4 Sep 2026 data/leads.db JUGA tidak dilacak git. Bryan memutuskan
# itu waktu lead berasal-BPS mulai masuk pipeline, dan sebabnya
# struktural: berkas BINER tidak bisa disaring sebagian — ia memuat baris
# terlarang atau tidak. Yang dilacak sebagai gantinya adalah ekspor CSV,
# yang tiap barisnya lewat klausa() di bawah.
DB_UTAMA = BASE / "data" / "leads.db"

# Kolom yang mencatat ASAL USUL baris di tiap tabel yang ikut terbit.
#
# Didaftar di satu tempat karena ketiga kolomnya bernama BERBEDA-BEDA,
# dan satu di antaranya pernah salah dipilih dengan akibat yang tidak
# kelihatan: sampai 4 Sep 2026 gerbang ini memeriksa
# `kebutuhan.model LIKE 'bps%'` — padahal kolom `model` menyimpan nama
# model LLM yang menilai ("claude-opus-5 (pembaca+pemeriksa)"), bukan
# sumber datanya. Nilai berawalan 'bps' tidak akan PERNAH muncul di sana,
# jadi gerbangnya hijau apa pun isi tabelnya. Kolom `kebutuhan.asal`
# ditambahkan persis untuk menutup itu.
#
# Pelajaran yang sama dengan robots.txt kemarin: gerbang yang memeriksa
# kolom yang salah tidak terlihat berbeda dari gerbang yang lolos.
KOLOM_ASAL = {
    "leads": "source",
    "leads_arsip": "source",
    "kontak_web": "sumber_discovery",
    "kebutuhan": "asal",
}


def boleh_terbit(sumber) -> bool:
    """False kalau baris dari sumber ini tidak boleh masuk berkas publik."""
    s = (sumber or "").strip().lower()
    return bool(s) and not s.startswith(SUMBER_DILINDUNGI)


def klausa(tabel: str, alias: str = "") -> str:
    """Potongan SQL untuk WHERE — benar hanya untuk baris yang boleh terbit.

    WAJIB dipakai setiap modul yang menulis berkas publik: ekspor_csv.py,
    buat_antrian.py (docs/index.html tayang di GitHub Pages) dan
    buat_dashboard.py. Sengaja satu fungsi dan bukan kalimat WHERE yang
    disalin ke tiap query — penyaring yang disalin akan ketinggalan di
    satu tempat, dan tempat itulah yang terbit.

    MENUTUP WAKTU TIDAK TAHU: baris ber-asal kosong ikut terbuang, sama
    seperti baris ber-asal BPS. Kalau ia ikut terbit, satu kolom yang
    lupa diisi cukup untuk menerbitkan baris yang tidak boleh terbit.
    Supaya baris begitu tidak hilang diam-diam, periksa() menyalak
    terpisah untuk asal yang kosong.
    """
    k = f"{alias}.{KOLOM_ASAL[tabel]}" if alias else KOLOM_ASAL[tabel]
    pola = " AND ".join(
        f"lower(COALESCE({k},'')) NOT LIKE '{s}%'" for s in SUMBER_DILINDUNGI)
    return f"(COALESCE({k},'') <> '' AND {pola})"


def pastikan_kolom_asal(con):
    """Tambahkan `kebutuhan.asal` kalau belum ada.

    Ditaruh di publik.py dan bukan di skrip migrasi tersendiri supaya
    setiap jalur yang menyentuh kolom ini — jalur tulis maupun jalur
    ekspor — bisa memanggilnya. Sengaja TIDAK mengisi baris lama:
    mengisi otomatis berarti baris yang asalnya lupa dicatat diam-diam
    dianggap boleh terbit, dan itu persis kegagalan yang mau dicegah.
    Baris lama diisi sekali lewat migrasi yang tercatat di git.
    """
    kolom = {r[1] for r in con.execute("PRAGMA table_info(kebutuhan)")}
    if "asal" not in kolom:
        con.execute("ALTER TABLE kebutuhan ADD COLUMN asal TEXT")
        con.commit()
        print("kolom `asal` ditambahkan ke tabel kebutuhan.")


def _norm(nama: str) -> str:
    s = (nama or "").upper()
    s = re.sub(r"\b(PT|CV|TBK|PERSERO|INDONESIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _nama_dari(db: Path, sql: str) -> set:
    if not db.exists():
        return set()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {_norm(r[0]) for r in con.execute(sql) if r[0]}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


def nama_dilindungi() -> set:
    """Nama yang keberadaannya di daftar kita HANYA berasal dari BPS.

    Perusahaan yang juga kita kenal dari sumber lain tidak dilindungi:
    keberadaannya tidak berasal dari publikasi itu, jadi menerbitkannya
    bukan menerbitkan ulang publikasi itu.

    Dipakai hanya sebagai jaring kedua. Pemeriksaan utama membaca ASAL
    USUL per baris, bukan mencocokkan nama -- lihat periksa().
    """
    bps = _nama_dari(DB_BPS, "SELECT nama FROM perusahaan_bps")
    if not bps:
        return set()
    lain = set()
    dbl = BASE / "data" / "leads.db"
    lain |= _nama_dari(dbl, "SELECT name FROM leads")
    lain |= _nama_dari(dbl, "SELECT nama FROM leads_arsip")
    lain |= _nama_dari(dbl, "SELECT nama FROM kontak_web")
    lain |= _nama_dari(dbl, "SELECT nama FROM kebutuhan")
    for csv_nama in ("companies_scored.csv", "companies_prioritas.csv"):
        f = BASE / "data" / csv_nama
        if f.exists():
            import csv as _csv
            with open(f, encoding="utf-8") as fh:
                for r in _csv.DictReader(fh):
                    n = r.get("company_name") or r.get("nama") or ""
                    if n:
                        lain.add(_norm(n))
    return {n for n in bps if n and n not in lain}


def _dilacak_git(jalur: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", jalur],
                       cwd=BASE, capture_output=True, text=True)
    return r.returncode == 0


NAMA_KOLOM = {"leads": "name", "leads_arsip": "name",
              "kontak_web": "nama", "kebutuhan": "nama"}


def _con_utama():
    if not DB_UTAMA.exists():
        return None
    return sqlite3.connect(f"file:{DB_UTAMA}?mode=ro", uri=True)


def _asal_kosong() -> dict:
    """Berapa baris yang asal-usulnya TIDAK tercatat, per tabel.

    Baris begini tidak berbahaya bagi berkas publik — klausa() sudah
    membuangnya. Yang berbahaya adalah ia HILANG DIAM-DIAM: lead yang
    sah tidak muncul di antrian dan tidak ada yang bertanya kenapa.
    Jadi ini dilaporkan sebagai masalah tersendiri, bukan digabung
    dengan kebocoran.
    """
    con = _con_utama()
    if con is None:
        return {}
    hasil = {}
    for tabel, kolom in KOLOM_ASAL.items():
        try:
            n = con.execute(
                f"SELECT count(*) FROM {tabel} "
                f"WHERE COALESCE({kolom},'') = ''").fetchone()[0]
            if n:
                hasil[tabel] = n
        except sqlite3.Error:
            pass
    con.close()
    return hasil


def _nama_terlindungi_persis() -> set:
    """Nama PERSIS (apa adanya, bukan dinormalkan) dari baris ber-asal BPS.

    Nama yang juga dipegang baris LAIN yang boleh terbit dikeluarkan:
    keberadaannya di daftar kita tidak berasal dari publikasi BPS, jadi
    menerbitkannya bukan menerbitkan ulang publikasi itu.
    """
    con = _con_utama()
    if con is None:
        return set()
    terlindungi, bebas = set(), set()
    for tabel, kolom in KOLOM_ASAL.items():
        nk = NAMA_KOLOM[tabel]
        try:
            baris = con.execute(
                f"SELECT {nk}, COALESCE({kolom},'') FROM {tabel}").fetchall()
        except sqlite3.Error:
            continue
        for nama, asal in baris:
            if not nama:
                continue
            (bebas if boleh_terbit(asal) else terlindungi).add(nama.strip())
    con.close()
    return {n for n in terlindungi if n and n not in bebas}


def _bocor_di_berkas() -> list:
    """Nama terlindungi yang BENAR-BENAR ada di berkas yang terbit.

    Ini PENGAMATAN atas berkas yang sudah ditulis, bukan kesimpulan dari
    isi database — dan itu bedanya dengan percobaan 3 Sep 2026 yang
    menghasilkan tujuh "kebocoran" palsu. Yang dicari sekarang adalah
    string nama PENUH milik baris yang provenansinya tercatat BPS,
    bukan potongan nama mana pun yang kebetulan ada di bps.db:

      'SAHABAT'    dulu cocok sebagai potongan nama lain -> tidak lagi,
                   yang dicocokkan nama penuh satu baris nyata
      'NUTRIFOOD'  masuk dari GAPMMI -> barisnya ber-asal 'gapmmi',
                   jadi ia tidak pernah masuk daftar terlindungi

    Penyaring sesungguhnya tetap klausa() di jalur tulis. Fungsi ini
    jaring kedua: ia memeriksa apakah penyaring itu benar-benar bekerja,
    dengan melihat hasilnya alih-alih mempercayainya.
    """
    nama = _nama_terlindungi_persis()
    if not nama:
        return []
    temuan = []
    for jalur in KELUARAN_PUBLIK:
        f = BASE / jalur
        if not f.exists():
            continue
        teks = f.read_text(encoding="utf-8", errors="replace")
        kena = sorted(n for n in nama if n in teks)
        if kena:
            temuan.append((jalur, kena))
    return temuan


def periksa() -> list:
    """Cari kebocoran. Return daftar masalah; kosong berarti aman."""
    masalah = []

    # 1. UTAMA: nama ber-asal BPS yang benar-benar muncul di berkas terbit.
    for jalur, kena in _bocor_di_berkas():
        contoh = ", ".join(kena[:5]) + (" ..." if len(kena) > 5 else "")
        masalah.append(
            f"{jalur} memuat {len(kena)} nama ber-asal BPS: {contoh}. "
            "Berkas ini terbit publik; jalur yang menulisnya belum "
            "memakai publik.klausa().")

    # 2. data/leads.db TIDAK BOLEH dilacak git — tanpa syarat, bukan
    #    "begitu ia memuat baris BPS". Sampai 4 Sep 2026 syarat itulah
    #    yang dipakai, dan syarat begitu menaruh gerbangnya SESUDAH
    #    kebocoran: begitu satu baris BPS masuk, berkas biner yang
    #    memuatnya sudah ada di riwayat git dan tidak bisa ditarik lagi.
    #    Berkas biner tidak bisa disaring sebagian.
    if _dilacak_git("data/leads.db"):
        masalah.append(
            "data/leads.db DILACAK GIT. Berkas biner tidak bisa disaring "
            "sebagian, jadi ia tidak boleh dilacak sama sekali. "
            "Keluarkan dengan: git rm --cached data/leads.db")

    # 3. Baris tanpa asal. Tidak bocor — klausa() membuangnya — tapi
    #    justru itu masalahnya: ia lenyap dari antrian tanpa jejak.
    for tabel, n in _asal_kosong().items():
        masalah.append(
            f"tabel {tabel} punya {n} baris tanpa kolom "
            f"`{KOLOM_ASAL[tabel]}` terisi. Baris itu DIBUANG dari semua "
            "keluaran publik oleh publik.klausa(); isi asalnya supaya "
            "tidak hilang diam-diam.")

    return masalah


def dugaan() -> list:
    """Kecocokan NAMA yang mungkin -- keterangan, BUKAN penghenti.

    Sengaja dipisah dari periksa() dan sengaja tidak pernah menggagalkan
    ekspor. Pencocokan nama di sini terbukti sering salah, dan sebabnya
    bukan bisa ditambal dengan ambang yang lebih ketat:

      'SAHABAT'                     cocok sebagai potongan nama lain
      'NUTRIFOOD'                   masuk dari GAPMMI, bukan dari BPS
      'ASAHIMAS FLAT GLASS'         ada di leads dari OSM, tapi tercatat
                                    "Asahimas Flat Glass (Flat Glass)"
      'GARUDAFOOD PUTRA PUTRI JAYA' ada dari GAPMMI sebagai "Garudafood"

    Dua nama untuk perusahaan yang sama tidak bisa dipastikan sama dari
    ejaannya, dan memaksakannya berarti menuduh kebocoran yang tidak
    terjadi. Gerbang yang salah tiga kali tiap jalan akan dimatikan
    orang, lalu kebocoran yang SUNGGUHAN ikut lewat.

    Yang menjaga garisnya adalah periksa(), yang membaca asal-usul baris
    -- fakta yang dicatat saat baris itu masuk, bukan dugaan dari nama.
    """
    hasil = []
    terlindungi = {n for n in nama_dilindungi()
                   if len(n) >= 18 and len(n.split()) >= 3}
    if not terlindungi:
        return hasil
    for jalur in KELUARAN_PUBLIK:
        f = BASE / jalur
        if not f.exists():
            continue
        isi = _norm(f.read_text(encoding="utf-8", errors="replace"))
        kena = [n for n in terlindungi if n in isi]
        if kena:
            hasil.append(f"{jalur}: {len(kena)} nama mirip, mis. "
                         f"{kena[0][:46]!r}")
    return hasil


def main():
    terlindungi = nama_dilindungi()
    print(f"Sumber terlindungi : {', '.join(SUMBER_DILINDUNGI)}*")
    print(f"Database BPS       : "
          f"{'ada' if DB_BPS.exists() else 'belum ada'} ({DB_BPS.name})")
    print(f"Nama terlindungi   : {len(terlindungi)}")
    print()
    d = dugaan()
    if d:
        print("Keterangan (BUKAN kebocoran; pencocokan nama memang sering "
              "salah, lihat dugaan() di src/publik.py):")
        for x in d:
            print(f"  ~ {x}")
        print()

    masalah = periksa()
    if not masalah:
        print("AMAN. Tidak ada baris ber-asal BPS di keluaran publik.")
        return
    print(f"BOCOR — {len(masalah)} masalah:")
    for m in masalah:
        print(f"  - {m}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
