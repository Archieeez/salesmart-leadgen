"""
baca/prompt.py
==============
Bangkitkan prompt PEMBACA dan PEMERIKSA dari sumber kebenaran yang sama
dengan rubriknya.

KENAPA MODUL INI ADA:
    Sampai 3 Sep 2026, kedua prompt itu DIKETIK ULANG setiap kali alur
    dijalankan. Artinya isinya bergantung pada ingatan orang yang
    mengetiknya saat itu — termasuk apakah ia ingat menyebutkan SEMUA
    jebakan, ingat melarang kutipan dari bagian petunjuk, dan ingat
    bahwa field `penolakan` sekarang boolean.

    Proyek ini sudah menolak pola itu sekali: deskripsi pita TIDAK
    ditulis ulang di prompt, ia dibangkitkan dari `rubrik.PITA` supaya
    tidak mungkin melenceng diam-diam. Prompt agennya diperlakukan sama
    sekarang, dengan alasan yang sama persis.

    Aturan yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa
    ada yang sengaja melanggarnya.

YANG DIBANGKITKAN, bukan ditulis tangan:
    - daftar label sah per komponen           <- rubrik.PITA
    - bentuk field `penolakan`                <- rubrik.PENANDA_TOLAK
    - jalur berkas yang harus dibaca/ditulis  <- folder kerja
    - daftar jebakan beserta KORBANNYA        <- KEGAGALAN di bawah

YANG TETAP DITULIS TANGAN, dan memang seharusnya:
    - pembagian peran pembaca vs pemeriksa
    - perintah "tugasmu MEMBANTAH", yang bukan turunan data apa pun
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "src"))

import rubrik  # noqa: E402

# Kegagalan nyata yang pernah lolos, beserta korbannya. Angka-angka ini
# yang membuat peringatannya dipercaya; peringatan tanpa korban terbaca
# seperti basa-basi dan diabaikan.
KEGAGALAN = [
    ("KALIMAT LOWONGAN vs KALIMAT CAKUPAN",
     '"Bersedia ditempatkan di seluruh Indonesia" adalah syarat PELAMAR, '
     "bukan klaim cakupan perusahaan.",
     "Nutrifood 80 -> 70"),
    ("KALIMAT KONSUMEN vs KALIMAT PEKERJA",
     '"Kunjungi gerai terdekat" adalah ajakan ke PEMBELI, bukan bukti tim '
     "lapangan.",
     "Alfamart 85 -> 70"),
    ("ANGKA NOL BERUNTUN",
     '"0 Gerai 0 Cabang 0 Karyawan" adalah penghitung JavaScript yang gagal '
     "termuat, BUKAN data. Jangan dipakai menaikkan maupun menurunkan.",
     "Indomaret, Musim Mas"),
    ("STATISTIK PELANGGAN vs STATISTIK PERUSAHAAN",
     '"160+ Cities" yang berdiri sebaris dengan "1.600+ Clients" adalah '
     "sebaran MILIK PELANGGAN.",
     "TransTRACK pola 90 -> bacaan 15"),
    ("KUTIPAN YANG DINORMALKAN DIAM-DIAM",
     "Kutipan yang tampak verbatim ternyata sudah diubah spasinya "
     "(U+2028 jadi spasi biasa). Verifikasi mesin memakai regex meloloskannya; "
     "pencocokan HARFIAH menangkapnya.",
     "Ajinomoto"),
    ("NAMA TEMPAT DI DALAM NAMA PRODUK",
     'Penyaring pola menduga "5 provinsi, 13 kota" dari daftar RESEP: '
     '"Nasi Bali", "Sop Ikan Khas Batam", "Gulai Rebung Asam Bengkulu '
     'Pendap". Nama daerah di situs produsen makanan sering nama MASAKAN, '
     "bukan lokasi operasi. Periksa kalimat tempat nama itu berdiri "
     "sebelum memakainya untuk scale.",
     "Sasa Inti, ditangkap pemeriksa 4 Sep 2026"),
]


def daftar_label() -> str:
    """Label sah per komponen, langsung dari rubrik.PITA."""
    baris = []
    for komponen in rubrik.MAKS_KOMPONEN:
        label = " | ".join(lab for _, lab, _, _ in rubrik.PITA[komponen])
        baris.append(f"  {komponen}: {label}")
    return "\n".join(baris)


def bentuk_penolakan() -> str:
    """Field boolean penolakan, langsung dari rubrik.PENANDA_TOLAK."""
    kunci = ", ".join(f'"{k}": false' for k, _ in rubrik.PENANDA_TOLAK)
    return "{" + kunci + ', "alasan": ""}'


def _jebakan(nomor_awal: int = 1) -> str:
    baris = []
    for i, (judul, isi, korban) in enumerate(KEGAGALAN, nomor_awal):
        baris.append(f"{i}. {judul}\n   {isi}\n   (Pernah terjadi: {korban}.)")
    return "\n".join(baris)


def prompt_pembaca(dok: Path, aturan: Path, keluar: Path, nama: str) -> str:
    return f"""Kamu agen PEMBACA dalam alur penilaian tiga langkah proyek
salesmart-leadgen. Kamu menilai SATU perusahaan: {nama}

LANGKAH:
1. Baca aturan penilaian lengkap: {aturan}
2. Baca dokumen perusahaannya: {dok}
   Baca SELURUH berkas, jangan sebagian.
3. Tulis hasilnya ke: {keluar}

ATURAN BUKTI — ini yang paling menentukan:
- Kutipan harus VERBATIM, disalin persis karakter-per-karakter, dan HANYA
  dari bagian "## TEKS HALAMAN TERPANEN".
- Bagian "Konteks dari memori proyek", "Penilaian LAMA", dan "Petunjuk
  penyaring otomatis" TIDAK BOLEH dikutip. Ketiganya ada supaya kamu tahu
  apa yang sudah diduga — bukan supaya disalin. Mengutip dari sana akan
  ditolak pemeriksa.
- Kalau tidak ada kalimat pendukung, KOSONGKAN kutipan dan pilih pita
  TERENDAH yang masih bisa dipertahankan.
- Tidak adanya bukti BUKAN bukti ketiadaan. Katakan lewat keyakinan
  "rendah", jangan mengarang.
- Penilaian LAMA di dokumen itu dugaan sebelumnya, bukan jawaban. Kamu
  boleh menaikkan ATAU menurunkan — tapi hanya dengan kutipan yang kamu
  temukan sendiri.

JEBAKAN YANG SUDAH PERNAH MELOLOSKAN PENILAIAN SALAH:
{_jebakan()}

LABEL YANG SAH (pakai persis salah satunya):
{daftar_label()}

BENTUK {keluar.name} — satu objek JSON:

{{
  "dist_model":   {{"label": "...", "kutipan": "...", "sumber_url": "...", "keyakinan": "tinggi|sedang|rendah"}},
  "field_sales":  {{"label": "...", "kutipan": "...", "sumber_url": "...", "keyakinan": "..."}},
  "scale":        {{"label": "...", "kutipan": "...", "sumber_url": "...", "keyakinan": "..."}},
  "industry_fit": {{"label": "...", "kutipan": "...", "sumber_url": "...", "keyakinan": "..."}},
  "catatan": "beberapa kalimat: kenapa perusahaan ini butuh / tidak butuh Salesmart, dan apa yang masih lemah buktinya",
  "penolakan": {bentuk_penolakan()}
}}

FIELD `penolakan` DIISI BOOLEAN, JANGAN LEWAT PROSA. Jangan menulis
"bukan pesaing" atau "boleh ditelepon" di dalam `catatan`. Sebelum field
ini ada, kalimat penyangkalan seperti itu justru membuat lead terbaik
hari itu (Arta Boga, 85, bukti 4/4) tertandai JANGAN TELEPON.

Laporkan kembali: label dan skor tiap komponen, beserta alasan singkatnya.
"""


def prompt_pemeriksa(dok: Path, aturan: Path, bacaan: Path, daftar: Path,
                     keluar: Path, nama: str) -> str:
    return f"""Kamu agen PEMERIKSA ADVERSARIAL dalam alur penilaian tiga
langkah proyek salesmart-leadgen. Perusahaannya: {nama}

TUGASMU CUMA SATU: MEMBANTAH. Bukan meninjau, bukan menyempurnakan, bukan
menyetujui dengan catatan. Cari alasan kenapa penilaian pembaca SALAH atau
KETERLALUAN. Kalau setelah berusaha keras kamu tidak menemukan cacat,
barulah kamu boleh membiarkannya berdiri — dan katakan terus terang bahwa
kamu sudah mencoba membantah dan gagal.

Kenapa peranmu ada: pembaca tunggal terbukti berulang kali mengklaim
melebihi buktinya. Daftar korbannya ada di bawah, lengkap dengan angkanya.

BERKAS:
  aturan penilaian : {aturan}
  dokumen sumber   : {dok}
  bacaan pembaca   : {bacaan}
  identitas        : {daftar}
  tulis hasil ke   : {keluar}

YANG WAJIB DIPERIKSA, satu per satu:

1. VERIFIKASI KUTIPAN SECARA HARFIAH. Jangan percaya klaim pembaca bahwa
   kutipannya sudah cocok. Uji sendiri dengan pencocokan LITERAL — Python
   `kutipan in teks` atau `grep -F` — BUKAN regex yang menormalkan spasi.
   Batasi pencarian HANYA ke bagian "## TEKS HALAMAN TERPANEN". Kutipan
   yang ternyata diambil dari bagian "Konteks", "Penilaian LAMA", atau
   "Petunjuk penyaring" HARUS ditolak; itu pernah terjadi.
2. SATU FAKTA SATU KOMPONEN. Apakah dua komponen naik dari fakta yang
   sama? Pengecualian sah: satu kalimat memuat dua fakta yang benar-benar
   berbeda. Komponen di pita nilai 0 tidak menaikkan apa pun.
3. LINGKUP ENTITAS. Bukti harus tentang operasi entitas Indonesia yang
   dinilai. Situs global yang bercerita soal operasi dunia bukan bukti.
4. VERTIKAL ASURANSI/PEMBIAYAAN TERTUTUP: industry_fit selalu
   "tidak_relevan".
5. DAFTAR LOKASI adalah bukti sah untuk scale (dropdown depo, daftar
   cabang). Tapi FORMULIR ALAMAT generik berisi semua provinsi BUKAN
   bukti apa pun.
6. Apakah label yang dipilih benar-benar yang TERENDAH yang masih bisa
   dipertahankan oleh kutipannya? Kalau kutipannya lebih lemah dari
   labelnya, TURUNKAN.
7. Field `penolakan`: apakah booleannya benar? Periksa sendiri, jangan
   percaya pembaca.

JEBAKAN YANG SUDAH PERNAH MELOLOSKAN PENILAIAN SALAH — serang SEMUANYA ({len(KEGAGALAN)} jebakan):
{_jebakan()}

LABEL YANG SAH:
{daftar_label()}

KELUARAN: tulis {keluar} — array berisi satu objek:

[{{
  "nama": "...", "nama_normal": "...", "website": "...",
  "pemeriksa_gagal": false,
  "final": {{ ...bentuknya sama persis dengan bacaan pembaca (empat
             komponen, catatan, penolakan), TAPI berisi keputusan
             AKHIR-mu setelah membantah — turunkan apa pun yang tidak
             tahan uji...,
             "koreksi": ["satu string per koreksi: apa yang pembaca
                         klaim, dan kenapa itu keliru"] }}
}}]

Ambil `nama`, `nama_normal`, dan `website` PERSIS dari {daftar.name}.
Kalau kamu tidak mengoreksi apa pun, isi "koreksi" dengan array kosong.

Laporkan: koreksi apa saja yang kamu buat, skor akhirnya, dan uji literal
mana yang kamu jalankan.
"""
