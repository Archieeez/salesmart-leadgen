"""
baca/rekam.py
=============
Rekam apa yang benar-benar terjadi dalam satu jalannya agen, supaya bisa
ditampilkan dan diperiksa ulang nanti.

MASALAH YANG DISELESAIKAN:
    Bagian paling berharga dari alur ini adalah PERSELISIHAN antara
    pembaca dan pemeriksa — pemeriksa menjatuhkan Nutrifood 80->70,
    Alfamart 85->70, TransTRACK 90->15, dan menurunkan dua keyakinan
    Arta Boga. Perselisihan itu hidup di `kerja/<label>/` yang tidak
    dilacak git, dan HILANG begitu foldernya dihapus.

    Yang tersisa di database cuma angka akhirnya. Angka akhir tidak bisa
    menjawab "kenapa saya harus percaya ini?" — yang menjawabnya adalah
    "ini yang sempat dibantah, dan begini bantahan itu berakhir".

YANG DIREKAM OTOMATIS, tanpa bergantung pada ingatan siapa pun:
    - label & skor pembaca per komponen, dibandingkan keputusan akhir
    - tiap koreksi pemeriksa, apa adanya
    - hasil verifikasi kutipan per komponen, termasuk yang GAGAL
    - dari halaman mana tiap kutipan diambil

YANG HARUS DIPASOK ORKESTRATOR, karena memang cuma dia yang tahu:
    lama jalan, token, jumlah panggilan alat tiap agen. Ditaruh di
    `kerja/<label>/telemetri.json`. Kalau berkas itu tidak ada, kolomnya
    kosong dan halamannya bilang "tidak tercatat" — BUKAN nol, karena nol
    itu klaim yang salah.
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rubrik  # noqa: E402

DB = BASE / "data" / "leads.db"
KOMP = list(rubrik.MAKS_KOMPONEN)

DDL = """
CREATE TABLE IF NOT EXISTS jalan_agen (
    jalan        TEXT NOT NULL,   -- label folder kerja, mis. "antrian-3sep"
    nama_normal  TEXT NOT NULL,
    nama         TEXT,
    pada         TEXT,            -- waktu perekaman, UTC
    ditulis      INTEGER,         -- 1 kalau hasilnya masuk tabel kebutuhan
    pemeriksa_gagal INTEGER,
    skor_pembaca INTEGER,
    skor_akhir   INTEGER,
    bukti_kuat   INTEGER,
    komponen     TEXT,            -- JSON: per komponen, pembaca vs akhir
    koreksi      TEXT,            -- JSON: daftar koreksi pemeriksa
    telemetri    TEXT,            -- JSON: lama/token/alat per agen, boleh NULL
    PRIMARY KEY (jalan, nama_normal)
);
"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def muat_dok(path: str) -> str:
    """Ambil HANYA bagian TEKS HALAMAN TERPANEN — sama seperti terapkan.py.

    Disamakan dengan sengaja: kalau modul ini memverifikasi terhadap
    seluruh berkas sementara terapkan.py memverifikasi terhadap potongan,
    halamannya akan melaporkan "lolos" untuk kutipan yang sebenarnya
    ditolak. Dua ukuran berbeda untuk hal yang sama selalu berakhir
    begitu.
    """
    t = Path(path).read_text(encoding="utf-8")
    i = t.find("## TEKS HALAMAN TERPANEN")
    return norm(t[i:] if i >= 0 else t)


def _baca_pembaca(folder: Path, slug: str):
    """Bacaan pembaca. Nama berkasnya sempat berubah 3 Sep 2026."""
    for kandidat in (f"pembaca-{slug}.json", "pembaca.json"):
        f = folder / kandidat
        if f.exists():
            isi = json.loads(f.read_text(encoding="utf-8"))
            return isi[0] if isinstance(isi, list) else isi
    return None


def _semua_hasil(folder: Path):
    """Keputusan akhir pemeriksa, dari hasil-*.json atau hasil.json."""
    berkas = sorted(folder.glob("hasil-*.json")) or [folder / "hasil.json"]
    for f in berkas:
        if not f.exists():
            continue
        isi = json.loads(f.read_text(encoding="utf-8"))
        for h in (isi if isinstance(isi, list) else [isi]):
            yield h


def slug_dari(nama: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nama.lower()).strip("-")[:48]


def kumpulkan(folder: Path, ditulis: bool):
    daftar = {d["nama"]: d for d in json.loads(
        (folder / "daftar.json").read_text(encoding="utf-8"))}
    telemetri = {}
    f_tel = folder / "telemetri.json"
    if f_tel.exists():
        telemetri = json.loads(f_tel.read_text(encoding="utf-8"))

    baris = []
    for h in _semua_hasil(folder):
        nama = h["nama"]
        if nama not in daftar:
            print(f"  LEWAT: {nama} tidak ada di daftar.json")
            continue
        slug = slug_dari(nama)
        dok = muat_dok(daftar[nama]["file"])
        pembaca = _baca_pembaca(folder, slug)
        final = h["final"]

        komponen, skor_p, skor_a, kuat = [], 0, 0, 0
        for k in KOMP:
            fa = final[k]
            pa = (pembaca or {}).get(k, {})
            nilai_a = rubrik.nilai_pita(k, fa["label"])
            nilai_p = (rubrik.nilai_pita(k, pa["label"])
                       if pa.get("label") else None)
            kut = norm(fa.get("kutipan", ""))
            lolos = bool(kut) and (kut in dok or kut.lower() in dok.lower())
            if lolos:
                kuat += 1
            skor_a += nilai_a
            if nilai_p is not None:
                skor_p += nilai_p
            komponen.append({
                "komponen": k,
                "label_pembaca": pa.get("label"),
                "nilai_pembaca": nilai_p,
                "keyakinan_pembaca": pa.get("keyakinan"),
                "label_akhir": fa["label"],
                "nilai_akhir": nilai_a,
                "keyakinan_akhir": fa.get("keyakinan"),
                "berubah": bool(pa) and pa.get("label") != fa["label"],
                "keyakinan_turun": bool(pa) and (
                    pa.get("keyakinan") != fa.get("keyakinan")),
                "kutipan": fa.get("kutipan", ""),
                "sumber_url": fa.get("sumber_url", ""),
                "kutipan_lolos": lolos,
            })

        baris.append({
            "nama_normal": h["nama_normal"], "nama": nama,
            "ditulis": int(ditulis),
            "pemeriksa_gagal": int(bool(h.get("pemeriksa_gagal"))),
            "skor_pembaca": skor_p if pembaca else None,
            "skor_akhir": skor_a, "bukti_kuat": kuat,
            "komponen": komponen,
            "koreksi": final.get("koreksi") or [],
            "telemetri": telemetri.get(slug),
        })
    return baris


def simpan(jalan: str, baris: list):
    con = sqlite3.connect(DB)
    con.executescript(DDL)
    pada = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for b in baris:
        con.execute(
            """INSERT INTO jalan_agen
               (jalan, nama_normal, nama, pada, ditulis, pemeriksa_gagal,
                skor_pembaca, skor_akhir, bukti_kuat, komponen, koreksi,
                telemetri)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(jalan, nama_normal) DO UPDATE SET
                 pada=excluded.pada, ditulis=excluded.ditulis,
                 pemeriksa_gagal=excluded.pemeriksa_gagal,
                 skor_pembaca=excluded.skor_pembaca,
                 skor_akhir=excluded.skor_akhir,
                 bukti_kuat=excluded.bukti_kuat,
                 komponen=excluded.komponen, koreksi=excluded.koreksi,
                 telemetri=excluded.telemetri""",
            (jalan, b["nama_normal"], b["nama"], pada, b["ditulis"],
             b["pemeriksa_gagal"], b["skor_pembaca"], b["skor_akhir"],
             b["bukti_kuat"],
             json.dumps(b["komponen"], ensure_ascii=False),
             json.dumps(b["koreksi"], ensure_ascii=False),
             json.dumps(b["telemetri"], ensure_ascii=False)
             if b["telemetri"] else None))
    con.commit()
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--jalan", default="",
                    help="label jalannya agen; default nama folder")
    ap.add_argument("--ditulis", action="store_true",
                    help="tandai bahwa hasilnya masuk tabel kebutuhan")
    args = ap.parse_args()

    folder = Path(args.dir)
    jalan = args.jalan or folder.name
    baris = kumpulkan(folder, args.ditulis)
    if not baris:
        print("Tidak ada yang direkam.")
        return
    simpan(jalan, baris)

    for b in baris:
        sp = "-" if b["skor_pembaca"] is None else b["skor_pembaca"]
        ubah = sum(1 for k in b["komponen"] if k["berubah"])
        gagal = sum(1 for k in b["komponen"] if not k["kutipan_lolos"])
        print(f"  {b['nama'][:34]:<36} pembaca {sp:>4} -> akhir "
              f"{b['skor_akhir']:>3}  koreksi {len(b['koreksi'])}  "
              f"label berubah {ubah}  kutipan gagal {gagal}")
    print(f"\n{len(baris)} perusahaan direkam ke jalan_agen (jalan '{jalan}').")


if __name__ == "__main__":
    main()
