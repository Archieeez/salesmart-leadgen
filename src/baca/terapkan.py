"""
baca/terapkan.py
================
Tulis hasil pembacaan agen ke tabel `kebutuhan`, setelah memverifikasi
kutipannya sendiri.

Pakai:
    python src/baca/terapkan.py --dir kerja/b1              # periksa saja
    python src/baca/terapkan.py --dir kerja/b1 --tulis      # tulis ke DB

Membaca `<dir>/hasil.json` dan `<dir>/daftar.json` yang dibuat
`siapkan.py`. Bentuk hasil.json:

    [{"nama", "nama_normal", "website", "pemeriksa_gagal",
      "final": {"dist_model": {...}, ..., "catatan", "koreksi",
                "penolakan": {"pesaing", "calon_mitra",
                              "vertikal_tertutup", "alasan"}}}]

`penolakan` boleh dihilangkan; kolom `penanda` lalu ditulis NULL dan
rubrik jatuh ke jalur prosa warisan. Kalau ADA, ia berdaulat — lihat
`rubrik.tandai_penolakan()`.

INI LAPIS KETIGA, DAN LAPISNYA BERBEDA DARI DUA YANG LAIN:
    Pembaca dan pemeriksa adalah agen — mereka menilai ARTI. Modul ini
    mesin, dan ia cuma memeriksa satu hal: apakah kutipannya benar-benar
    ADA di dokumen yang dibaca.

    Ketiganya ketat pada hal berbeda, dan itu bukan pemborosan. Kutipan
    Ajinomoto (2 Sep 2026) LOLOS di sini — karena normalisasi `\\s+`
    mencocokkan U+2028 dengan spasi — tapi GUGUR di `grep -F` pemeriksa.
    Yang literal ternyata lebih benar. Jangan buang salah satu lapisan.

MODE --tulis MENOLAK JALAN kalau masih ada kutipan yang gagal
verifikasi. Itu disengaja: penilaian yang kutipannya tidak bisa
ditemukan adalah penilaian yang tidak bisa dipertanggungjawabkan waktu
orang sales ditanya "dari mana Anda tahu?".

STATUS DITAHAN KALAU PEMERIKSA GAGAL JALAN:
    Kalau `pemeriksa_gagal` true, status TIDAK boleh naik ke
    `nilai_tegak` berapa pun jumlah kutipannya. Seluruh alasan pemeriksa
    ada adalah karena pembaca terbukti sering mengklaim melebihi
    buktinya; menandai bacaan yang belum diadu sebagai "tegak" persis
    kesalahan yang mau dihindari.
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rubrik  # noqa: E402
import publik  # noqa: E402

DB = BASE / "data" / "leads.db"
KOMP = list(rubrik.MAKS_KOMPONEN)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def muat_dok(path: str) -> str:
    """Ambil HANYA bagian TEKS HALAMAN TERPANEN.

    Sengaja memotong header: kalau seluruh berkas dipakai sebagai acuan,
    kutipan yang diambil agen dari bagian "petunjuk penyaring" atau dari
    "penilaian lama" akan lolos verifikasi — padahal itu justru yang
    dilarang. Pernah terjadi.
    """
    t = Path(path).read_text(encoding="utf-8")
    i = t.find("## TEKS HALAMAN TERPANEN")
    return norm(t[i:] if i >= 0 else t)


def pastikan_kolom_penanda(con):
    """Tambahkan kolom `penanda` kalau database dibuat sebelum 3 Sep 2026.

    Sengaja di sini dan bukan di skrip migrasi tersendiri: kolomnya baru
    berarti begitu ada hasil pembacaan yang mengisinya, jadi tempat yang
    tidak mungkin terlewat adalah jalur tulisnya sendiri.
    """
    kolom = {r[1] for r in con.execute("PRAGMA table_info(kebutuhan)")}
    if "penanda" not in kolom:
        con.execute("ALTER TABLE kebutuhan ADD COLUMN penanda TEXT")
        con.commit()
        print("kolom `penanda` ditambahkan ke tabel kebutuhan.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="folder dari siapkan.py")
    ap.add_argument("--tulis", action="store_true")
    ap.add_argument("--model", default="agen pembaca+pemeriksa",
                    help="dicatat di kolom `model`")
    args = ap.parse_args()

    folder = Path(args.dir)
    hasil = json.loads((folder / "hasil.json").read_text(encoding="utf-8"))
    daftar = {d["nama"]: d for d in json.loads(
        (folder / "daftar.json").read_text(encoding="utf-8"))}

    gagal, baris = [], []

    for h in hasil:
        nama = h["nama"]
        f = h["final"]
        dok = muat_dok(daftar[nama]["file"])

        rincian, bukti_kuat = {}, 0
        for k in KOMP:
            comp = dict(f[k])
            kut = norm(comp.get("kutipan", ""))
            if kut:
                if kut in dok or kut.lower() in dok.lower():
                    bukti_kuat += 1
                else:
                    gagal.append((nama, k, kut[:90]))
            rincian[k] = comp

        skor = {k: rubrik.nilai_pita(k, f[k]["label"]) for k in KOMP}
        need = sum(skor.values())
        status = "nilai_tegak" if bukti_kuat >= 3 else "bukti_belum_cukup"

        # Field boolean status jangan-telepon. Disimpan mentah supaya
        # rubrik tidak perlu menebaknya dari prosa; kalau pembaca tidak
        # mengisinya, kolomnya NULL dan jalur warisan yang dipakai.
        pen = f.get("penolakan")
        if isinstance(pen, dict):
            penanda = {k: bool(pen.get(k)) for k, _ in rubrik.PENANDA_TOLAK}
            penanda["alasan"] = norm(pen.get("alasan", ""))
        else:
            penanda = None

        catatan = norm(f.get("catatan", ""))
        koreksi = f.get("koreksi") or []
        if koreksi:
            catatan += (" [Pemeriksa mengoreksi pembaca: "
                        + "; ".join(k[:160] for k in koreksi[:4]) + "]")
        if h.get("pemeriksa_gagal"):
            status = "bukti_belum_cukup"
            catatan += (" [PERINGATAN: pemeriksa adversarial GAGAL JALAN. "
                        "Ini bacaan pembaca yang BELUM diadu; status "
                        "ditahan berapa pun jumlah kutipannya.]")

        baris.append({
            "nama": nama, "nama_normal": h["nama_normal"],
            "website": h["website"], "skor": skor, "need": need,
            "bukti_kuat": bukti_kuat, "status": status, "rincian": rincian,
            "penanda": penanda, "catatan": catatan,
            "asal": (daftar.get(nama) or {}).get("asal", ""),
            "dobel": rubrik.periksa_dobel_hitung(rincian),
        })

    baris.sort(key=lambda b: -b["need"])
    con = sqlite3.connect(DB)
    pastikan_kolom_penanda(con)
    publik.pastikan_kolom_asal(con)

    # Menolak menulis baris yang asal usulnya tidak tercatat. Bukan
    # kehati-hatian: baris ber-asal kosong DIBUANG publik.klausa() dari
    # antrian dan dari tiap berkas publik, jadi menulisnya berarti
    # menghilangkan lead yang barusan dinilai empat agen -- tanpa satu
    # pun pesan galat. Lebih baik berhenti di sini.
    tanpa_asal = [b["nama"] for b in baris if not b["asal"].strip()]
    if tanpa_asal:
        print("\nDITOLAK: asal usul tidak tercatat untuk "
              f"{len(tanpa_asal)} perusahaan:")
        for n in tanpa_asal:
            print(f"  - {n}")
        print("\ndaftar.json dibuat siapkan.py versi lama (sebelum --asal "
              "ada). Jalankan ulang siapkan.py dengan --asal, atau "
              "tambahkan field \"asal\" ke tiap entri daftar.json.")
        con.close()
        raise SystemExit(1)
    lama = {n: need for n, need in con.execute(
        "SELECT nama, need_score FROM kebutuhan")}

    print(f"{'perusahaan':<42}{'lama':>6}{'baru':>6}{'bukti':>7}  status")
    print("-" * 84)
    for b in baris:
        sl = str(lama.get(b["nama"], "-"))
        print(f"{b['nama'][:40]:<42}{sl:>6}{b['need']:>6}"
              f"{b['bukti_kuat']:>5}/4  {b['status']}"
              + ("  DOBEL: " + "; ".join(b["dobel"]) if b["dobel"] else "")
              + ("  TOLAK: " + rubrik.tandai_penolakan(
                    b["need"], b["skor"]["industry_fit"], b["catatan"],
                    b["penanda"])
                 if rubrik.tandai_penolakan(
                    b["need"], b["skor"]["industry_fit"], b["catatan"],
                    b["penanda"]) else ""))

    if gagal:
        print(f"\nKUTIPAN GAGAL VERIFIKASI MESIN ({len(gagal)}):")
        for nama, k, kut in gagal:
            print(f"  {nama} / {k}: {kut}")

    if not args.tulis:
        print("\n(mode periksa; tidak ada yang ditulis. Tambahkan --tulis.)")
        con.close()
        return

    if gagal:
        print("\nDITOLAK: masih ada kutipan yang gagal verifikasi. Bereskan "
              "dulu (edit hasil.json) atau kosongkan komponennya.")
        con.close()
        raise SystemExit(1)

    lama_cat = dict(con.execute("SELECT nama, catatan FROM kebutuhan"))
    for b in baris:
        cat = b["catatan"]
        cl = norm(lama_cat.get(b["nama"], "") or "")
        if cl:
            cat += f" [Riwayat bacaan lama: {cl[:400]}]"
        con.execute(
            """INSERT INTO kebutuhan
               (nama_normal, nama, website, dist_model, field_sales, scale,
                industry_fit, need_score, rincian, penanda, catatan, model,
                asal, bukti_kuat, status_nilai, dinilai_pada)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(nama_normal) DO UPDATE SET
                 nama=excluded.nama, website=excluded.website,
                 dist_model=excluded.dist_model,
                 field_sales=excluded.field_sales, scale=excluded.scale,
                 industry_fit=excluded.industry_fit,
                 need_score=excluded.need_score, rincian=excluded.rincian,
                 penanda=excluded.penanda,
                 catatan=excluded.catatan, model=excluded.model,
                 asal=excluded.asal,
                 bukti_kuat=excluded.bukti_kuat,
                 status_nilai=excluded.status_nilai,
                 dinilai_pada=CURRENT_TIMESTAMP""",
            (b["nama_normal"], b["nama"], b["website"],
             b["skor"]["dist_model"], b["skor"]["field_sales"],
             b["skor"]["scale"], b["skor"]["industry_fit"], b["need"],
             json.dumps(b["rincian"], ensure_ascii=False),
             json.dumps(b["penanda"], ensure_ascii=False)
             if b["penanda"] else None,
             cat, args.model, b["asal"], b["bukti_kuat"], b["status"]))
    con.commit()
    n = con.execute("SELECT count(*) FROM kebutuhan").fetchone()[0]
    con.close()
    print(f"\nDitulis {len(baris)} baris; tabel kebutuhan kini {n} baris.")
    print("Jangan lupa: python src/buat_antrian.py && "
          "python src/buat_dashboard.py && python src/ekspor_csv.py")


if __name__ == "__main__":
    main()
