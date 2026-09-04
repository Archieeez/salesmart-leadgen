"""
uji_gerbang.py
==============
Pastikan tiap query yang isinya bisa terbit sudah lewat publik.klausa().

KENAPA MODUL INI ADA:
    4 Sep 2026, waktu data/leads.db dikeluarkan dari git dan penyaring
    terbit dipasang, saya menambahkan publik.klausa() ke ekspor_csv,
    buat_antrian dan buat_dashboard — lalu menjalankan uji negatif:
    satu baris palsu ber-asal BPS dimasukkan ke database, seluruh
    keluaran dibangkitkan ulang, dan namanya dicari di berkas hasilnya.

    Namanya KETEMU di docs/index.html.

    Bukan di query yang saya saring, melainkan di jalur KEEMPAT yang
    tidak terpikir: panel denyut agen di agen_status.py, yang menyusun
    kalimat "menilai <nama> — skor 100" dari tiga tabel sekaligus. Tiga
    modul yang saya periksa satu-satu tidak memuat kebocorannya.

    Pelajaran yang mahal di proyek ini berulang lagi: yang diperiksa
    harus PENGAMATAN, bukan daftar tempat yang saya ingat. Dan uji yang
    harus diingat orang untuk dijalankan sama saja dengan tidak ada.

APA YANG DIPERIKSA — dan kenapa BUKAN dengan menjalankan query:
    Berkas ini membaca KODE, bukan data. Tiap panggilan yang berisi
    "FROM <tabel>" untuk tabel yang punya kolom asal usul harus
    menyebut publik.klausa() di panggilan yang sama.

    Pemeriksaan runtime sudah ada dan tetap jadi lapis utama —
    publik.periksa() membaca berkas yang SUDAH ditulis. Tapi ia cuma
    menyalak kalau kebetulan ada baris terlarang di database saat itu.
    Selama belum ada satu pun lead BPS masuk, query baru yang lupa
    menyaring akan lolos diam-diam sampai berbulan-bulan kemudian.
    Lint ini menyalak di menit query-nya ditulis.

Pakai:
    python src/uji_gerbang.py        # exit 1 kalau ada yang lolos
"""

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import publik  # noqa: E402

# Modul yang menulis berkas terbit. Kalau menambah modul baru yang
# menghasilkan berkas di publik.KELUARAN_PUBLIK, daftarkan di sini —
# lint yang tidak tahu sebuah berkas ada tidak bisa menjaganya.
PENULIS_PUBLIK = [
    "src/ekspor_csv.py",
    "src/buat_antrian.py",
    "src/buat_dashboard.py",
    "src/agen_status.py",
]

# jalan_agen tidak punya kolom asal sendiri; ia disaring lewat subquery
# ke kebutuhan. Nama tabelnya tetap didaftar supaya query barunya ikut
# wajib menyebut klausa().
TABEL_DIJAGA = set(publik.KOLOM_ASAL) | {"jalan_agen"}

POLA_FROM = re.compile(r"\bFROM\s+([a-z_]+)", re.I)


def _teks_panggilan(node: ast.Call) -> str:
    """Semua argumen sebuah panggilan sebagai satu teks.

    Dipakai ast.unparse supaya bagian f-string ikut terbaca apa adanya:
    `f"WHERE {publik.klausa('kebutuhan')}"` menyisakan jejak
    "publik.klausa" di teksnya, sementara membaca Constant saja akan
    kehilangan justru bagian yang sedang dicari.
    """
    potong = []
    for a in list(node.args) + [k.value for k in node.keywords]:
        try:
            potong.append(ast.unparse(a))
        except Exception:
            pass
    return " ".join(potong)


def _nama_pemegang_klausa(pohon: ast.AST) -> set:
    """Variabel yang isinya hasil publik.klausa(...).

    Query panjang sering menyimpan klausanya di variabel lebih dulu:

        kl_l = publik.klausa("leads")
        q(f"SELECT ... FROM leads WHERE {kl_l} GROUP BY city")

    Tanpa langkah ini, lima query yang MEMANG sudah disaring dilaporkan
    sebagai pelanggaran. Lint yang menuduh kode yang benar akan dibuat
    diam oleh orang berikutnya, dan sesudah itu ia tidak menjaga apa
    pun — jadi memperbaiki lintnya lebih murah daripada menulis ulang
    query supaya cocok dengan lintnya.
    """
    nama = set()
    for n in ast.walk(pohon):
        if not isinstance(n, (ast.Assign, ast.AnnAssign)):
            continue
        nilai = n.value
        if nilai is None:
            continue
        sasaran = n.targets if isinstance(n, ast.Assign) else [n.target]
        # Bongkar `a, b = klausa(x), klausa(y)` jadi pasangan.
        pasangan = []
        for s in sasaran:
            if isinstance(s, ast.Tuple) and isinstance(nilai, ast.Tuple):
                pasangan += list(zip(s.elts, nilai.elts))
            else:
                pasangan.append((s, nilai))
        for t, v in pasangan:
            if isinstance(t, ast.Name) and "klausa" in ast.unparse(v):
                nama.add(t.id)
    return nama


def periksa_berkas(jalur: Path) -> list:
    masalah = []
    pohon = ast.parse(jalur.read_text(encoding="utf-8"))
    pemegang = _nama_pemegang_klausa(pohon)
    for node in ast.walk(pohon):
        if not isinstance(node, ast.Call):
            continue
        teks = _teks_panggilan(node)
        if "FROM" not in teks.upper():
            continue
        tabel = {m.group(1).lower() for m in POLA_FROM.finditer(teks)}
        kena = tabel & TABEL_DIJAGA
        if not kena:
            continue
        if "publik.klausa" in teks or "klausa(" in teks:
            continue
        if any(re.search(rf"\b{re.escape(v)}\b", teks) for v in pemegang):
            continue
        masalah.append((node.lineno, sorted(kena),
                        " ".join(teks.split())[:110]))
    return masalah


def main():
    total = 0
    for rel in PENULIS_PUBLIK:
        f = BASE / rel
        if not f.exists():
            print(f"  ! {rel} tidak ada — daftar PENULIS_PUBLIK basi")
            total += 1
            continue
        masalah = periksa_berkas(f)
        if not masalah:
            print(f"  OK  {rel}")
            continue
        total += len(masalah)
        for lineno, tabel, cuplik in masalah:
            print(f"  X   {rel}:{lineno} query ke {', '.join(tabel)} "
                  "tanpa publik.klausa()")
            print(f"      {cuplik}")

    if total:
        print(f"\nGAGAL: {total} query bisa menerbitkan baris terlarang.")
        print("Tambahkan WHERE {publik.klausa('<tabel>')} ke query itu.")
        return 1
    print("\nAMAN. Tiap query ke tabel ber-asal sudah lewat publik.klausa().")
    return 0


if __name__ == "__main__":
    sys.exit(main())
