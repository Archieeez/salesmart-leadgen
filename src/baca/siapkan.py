"""
baca/siapkan.py
===============
Rakit satu berkas .md per perusahaan sebagai bahan baca untuk agen
penilai, plus `aturan.md` yang dibangkitkan dari `rubrik.PITA`.

ALUR LENGKAPNYA — tiga langkah, jangan dipotong:

    1. python src/baca/siapkan.py --nama "Alfamart" "TIKI" --keluar kerja/b1
    2. jalankan agen: PEMBACA menilai, lalu PEMERIKSA membantahnya,
       hasil akhirnya disimpan sebagai kerja/b1/hasil.json
    3. python src/baca/terapkan.py --dir kerja/b1            # periksa dulu
       python src/baca/terapkan.py --dir kerja/b1 --tulis    # baru tulis

KENAPA DUA LAPIS AGEN, BUKAN SATU:
    Pembaca tunggal terbukti berulang kali mengklaim melebihi buktinya.
    Yang tertangkap pemeriksa selama 2 Sep 2026:

      Nutrifood  "Bersedia ditempatkan di seluruh area di Indonesia"
                 dipakai sebagai bukti cakupan nasional. Itu klausa
                 KESEDIAAN PENEMPATAN PELAMAR di sebuah lowongan.
                 80 -> 70.
      Alfamart   "Dengan mengunjungi toko Alfamart terdekat..." dipakai
                 sebagai bukti tim lapangan. Itu instruksi kepada
                 KONSUMEN. 85 -> 70.
      Ajinomoto  kutipan yang tampak verbatim ternyata sudah dinormalkan
                 diam-diam (U+2028 diubah jadi spasi).
      TransTRACK "160+ Cities across Indonesia" dipakai sebagai sebaran
                 perusahaan. Itu sebaran unit langganan MILIK PELANGGAN.
                 Pola menilai 90, bacaan akhir 15.

    Pemeriksa diberi SATU tugas: membantah. Bukan meninjau, bukan
    menyempurnakan. Bedanya besar di hasil.

LAPIS KETIGA ADA DI terapkan.py — verifikasi kutipan oleh mesin.
    Ketiganya ketat pada hal yang berbeda, dan itu disengaja: kutipan
    Ajinomoto LOLOS verifikasi mesin (regex \\s+ mencocokkan U+2028) tapi
    GUGUR di grep -F pemeriksa. Jangan buang salah satu lapisan.

SUSUNAN TIAP DOKUMEN, berurutan:
    identitas -> konteks dari memori proyek -> penilaian LAMA ->
    petunjuk penyaring otomatis -> TEKS HALAMAN TERPANEN

    Agen diminta mengutip HANYA dari bagian terakhir. Bagian sebelumnya
    diberikan supaya ia tahu apa yang sudah diduga — bukan supaya
    dikutip. Pemeriksa secara khusus disuruh menolak kutipan yang
    ternyata diambil dari bagian petunjuk; itu pernah terjadi.
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

import nilai_kebutuhan as nk       # noqa: E402
import rubrik                      # noqa: E402
import saring_bukti as sb          # noqa: E402

DATA = BASE / "data"

# Konteks yang HANYA diketahui dari memori proyek, bukan dari situsnya.
# Tanpa ini pembaca tidak punya cara tahu bahwa Smart GPS itu pesaing,
# atau bahwa angka di situs Musim Mas berbentuk animasi penghitung.
KONTEKS = {
    "Smart GPS Bandung":
        "PESAING/tetangga produk Salesmart (penjual GPS tracker). Nilai "
        "tetap jujur per rubrik, TAPI sebut status pesaing itu "
        "terang-terangan di catatan — catatan itulah yang dipakai sistem "
        "untuk menandai jangan-telepon.",
    "TransTRACK.ID":
        "PESAING LANGSUNG (platform telematika armada/GPS). Sama: sebut "
        "status pesaingnya di catatan.",
    "Kantor Maxim Indonesia":
        "Aplikasi ride-hailing. Daftar ratusan kota di situsnya adalah "
        "kota LAYANAN APLIKASI, bukan titik distribusi barang.",
    "Mondelez Indonesia":
        "Tidak punya situs operasional Indonesia; yang terpanen situs "
        "global. Ingat aturan lingkup entitas.",
    "DSV Contract Logistics Indonesia - Headoffice":
        "Tidak punya situs Indonesia (semua pola locale 404); yang "
        "terpanen konten global. Ingat aturan lingkup entitas.",
    "PT Musim Mas":
        "Angka-angka di situsnya berbentuk penghitung animasi JavaScript "
        "sehingga tidak ikut terpanen sebagai teks. Nilai dari teks yang "
        "ADA saja.",
    "PT Arta Boga Cemerlang":
        "Lengan distribusi FMCG Orang Tua Group. Sempat salah dicap "
        "'diblokir robots.txt'; ternyata tidak pernah tertutup. Halaman "
        "yang terpanen masih sedikit, jadi ketiadaan bukti untuk sebuah "
        "komponen kemungkinan besar berarti halamannya belum dipanen, "
        "bukan faktanya tidak ada.",
}

# Aturan tambahan proyek yang TIDAK bisa dibangkitkan dari rubrik.PITA,
# karena bentuknya keputusan, bukan pita nilai.
ATURAN_TAMBAHAN = """

ATURAN TAMBAHAN PROYEK (sudah final, jangan diperdebatkan):

1. LINGKUP ENTITAS: bukti harus tentang operasi entitas INDONESIA.
   Situs global yang menceritakan operasi dunia ("offices in 50
   countries") BUKAN bukti untuk entitas Indonesianya.
2. SATU FAKTA SATU KOMPONEN: fakta yang sama tidak boleh MENAIKKAN dua
   komponen. Tapi kalau satu kalimat memuat DUA FAKTA BERBEDA
   (mis. "500 outlet di 34 provinsi" = jaringan DAN sebaran), itu bukan
   dobel hitung. Komponen yang duduk di pita terendah (nilai 0) tidak
   menaikkan apa pun, jadi kutipan yang sama di sana juga bukan
   pelanggaran.
3. VERTIKAL ASURANSI/PEMBIAYAAN TERTUTUP: industry_fit selalu
   "tidak_relevan". Polis dan kredit bukan barang yang berpindah lewat
   jaringan distribusi fisik.
4. DAFTAR LOKASI ADALAH BUKTI SAH untuk scale: dropdown "Pilih Area
   Depot" berisi 53 kota, atau daftar BRANCH OFFICES, layak dikutip.
   Tapi FORMULIR ALAMAT generik (semua provinsi + ratusan "Kabupaten X"
   untuk alamat rumah pelamar) BUKAN bukti apa-apa.
5. Skor tinggi dengan industry_fit "tidak_relevan" berarti PENOLAKAN —
   tetap nilai jujur; keputusannya diambil sistem.

JEBAKAN YANG SUDAH PERNAH MELOLOSKAN PENILAIAN SALAH — periksa keempatnya:

a. KALIMAT LOWONGAN vs KALIMAT CAKUPAN. "Bersedia ditempatkan di
   seluruh Indonesia" adalah syarat PELAMAR, bukan klaim cakupan
   perusahaan. (Menjatuhkan Nutrifood 80 -> 70.)
b. KALIMAT KONSUMEN vs KALIMAT PEKERJA. "Kunjungi gerai terdekat"
   adalah ajakan ke PEMBELI, bukan bukti tim lapangan. (Menjatuhkan
   Alfamart 85 -> 70.)
c. ANGKA NOL BERUNTUN. "0 Gerai 0 Cabang 0 Karyawan" adalah penghitung
   JavaScript yang gagal termuat, BUKAN data. Jangan dipakai menaikkan
   maupun menurunkan.
d. STATISTIK PELANGGAN vs STATISTIK PERUSAHAAN. "160+ Cities" yang
   berdiri di blok bersama "1.600+ Clients" adalah sebaran MILIK
   PELANGGAN. (Menjatuhkan TransTRACK dari pola 90 ke bacaan 15.)
"""


def slug(n: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")[:48]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nama", nargs="+", required=True,
                    help="nama perusahaan, persis seperti di bukti.db")
    ap.add_argument("--keluar", required=True,
                    help="folder keluaran, mis. kerja/b1")
    args = ap.parse_args()

    out = Path(args.keluar)
    out.mkdir(parents=True, exist_ok=True)

    per = {p["nama"]: p for p in nk.muat_perusahaan(str(DATA / "bukti.db"))}

    con = sqlite3.connect(DATA / "leads.db")
    con.row_factory = sqlite3.Row
    lama = {r["nama"]: dict(r) for r in con.execute("SELECT * FROM kebutuhan")}
    con.close()

    kategori = sb.muat_kategori()
    daftar = []

    for nama in args.nama:
        if nama not in per:
            print(f"  LEWAT (belum dipanen): {nama}")
            continue
        p = per[nama]
        dok = nk.rakit_dokumen(p)

        halaman = [h["teks"] or "" for h in p["halaman"]]
        h = sb.saring(" ".join(halaman), kategori.get(nama, ""),
                      halaman=halaman)
        petunjuk = [f"- {k}: pola menduga '{h[k]['label']}' karena: "
                    f"{h[k]['kutipan'][:220]}"
                    for k in rubrik.MAKS_KOMPONEN if h[k]["kutipan"]]

        kepala = [f"# {nama}", f"website: {p['website']}",
                  f"nama_normal: {p['nama_normal']}", ""]
        if nama in KONTEKS:
            kepala += ["## Konteks dari memori proyek", KONTEKS[nama], ""]
        if nama in lama:
            r = lama[nama]
            kepala += ["## Penilaian LAMA (boleh direvisi kalau bukti baru "
                       "lebih kuat — TAPI hanya dengan kutipan yang kamu "
                       "temukan sendiri)",
                       f"need_score {r['need_score']}, "
                       f"status {r['status_nilai']}",
                       f"catatan lama: {r['catatan']}",
                       f"rincian lama: {r['rincian']}", ""]
        if petunjuk:
            kepala += ["## Petunjuk penyaring otomatis (dugaan MESIN, WAJIB "
                       "diperiksa ulang ke teks — sering salah)"] + petunjuk
            kepala += [""]
        kepala += ["## TEKS HALAMAN TERPANEN", "", dok]

        f = out / (slug(nama) + ".md")
        f.write_text("\n".join(kepala), encoding="utf-8")
        daftar.append({"nama": nama, "nama_normal": p["nama_normal"],
                       "website": p["website"], "file": str(f.resolve()),
                       "chars": len(dok)})
        print(f"{len(dok):>7}  {nama}")

    (out / "aturan.md").write_text(
        nk.SISTEM.format(aturan=nk.bangun_aturan()) + ATURAN_TAMBAHAN,
        encoding="utf-8")
    (out / "daftar.json").write_text(
        json.dumps(daftar, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(daftar)} dokumen -> {out.resolve()}")
    print("Berikutnya: jalankan agen pembaca + pemeriksa, simpan hasilnya")
    print(f"sebagai {out}/hasil.json, lalu:")
    print(f"  python src/baca/terapkan.py --dir {args.keluar}")


if __name__ == "__main__":
    main()
