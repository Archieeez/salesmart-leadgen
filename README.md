# salesmart-leadgen

Agen pencari lead B2B untuk Salesmart — proyek belajar AI engineering.

Target: menemukan perusahaan Indonesia yang **butuh** platform manajemen tim
sales lapangan, lengkap dengan nama, telepon kantor, website, dan alamat.
Semua data bersumber legal, level perusahaan saja (patuh UU PDP).

**Lihat hasilnya:** buka `docs/index.html` di browser.

## Status

| Fase | Status |
|------|--------|
| Phase 0 — kalibrasi rubric manual | Selesai |
| Phase 1 — pipeline data tanpa AI | Berjalan |
| Phase 2 — ekstraksi sinyal via LLM | Belum |
| Phase 3 — orkestrasi agen | Belum |
| Phase 4 — pelacakan hasil & evaluasi pivot | Belum |

Google Places API menunggu verifikasi billing. Sementara ini memakai
OpenStreetMap via Overpass API sebagai sumber pengganti.

## Hasil sejauh ini

| Metrik | Angka |
|---|---|
| Entri mentah dipanen | 1.416 |
| Entri bersih | 991 |
| Punya nomor telepon | 125 |
| Punya website | 180 |
| Dibuang saat pembersihan | 425 |
| Cocok profil klien ideal | 27 (3,2%) |

Rincian yang dibuang: 209 mall, 145 duplikat entitas, 48 noise
gedung/pemerintah, 23 cabang/gerai.

Angka 3,2% itu **baseline pembanding** — dipakai nanti untuk menilai apakah
query Places API yang tertarget menghasilkan relevansi lebih tinggi.

## Struktur

```
src/    kode
data/   database & hasil ekspor CSV
docs/   dashboard visual (buka index.html)
```

Dua database, sengaja dipisah:

| File | Dilacak git? | Isi |
|---|---|---|
| `data/leads.db` | ya | lead, arsip, kontak, hasil penilaian kebutuhan |
| `data/bukti.db` | **tidak** | teks mentah halaman situs — bahan, bisa dipanen ulang |

| File | Fungsi |
|------|--------|
| `src/discover_osm.py` | Panen dari OSM, 10 kota x 10 kategori, bisa dilanjut |
| `src/bersihkan_db.py` | Pembersihan retroaktif + dedup entitas, dengan backup |
| `src/cek_db.py` | Ukur kualitas per kategori, sampel acak |
| `src/cek_arsip.py` | Audit entri yang dibuang beserta alasannya |
| `src/rubrik.py` | Aturan penilaian — gerbang kualitas kontak + need score |
| `src/hitung_prioritas.py` | Urutkan lead berdasarkan kebutuhan |
| `src/query_plan.py` | 160 query Places API tervalidasi |
| `src/buat_dashboard.py` | Hasilkan `docs/index.html` dari database |
| `src/web.py` | Lapisan ambil-halaman bersama: robots.txt, cache, fallback http |
| `src/enrich_kontak.py` | Cari telepon kantor dari situs resmi (hit rate 33%) |
| `src/panen_bukti.py` | Panen halaman Tentang/Bisnis/Distribusi/Karier jadi bukti |
| `src/nilai_kebutuhan.py` | Phase 2: isi 4 komponen Need Score via LLM |
| `src/ekspor_csv.py` | Ekspor semua tabel ke CSV supaya diff-nya terbaca git |
| `src/pindah_bukti.py` | Pindahkan `halaman_bukti` ke `bukti.db` (sekali jalan) |

Cara menjalankan: lihat `CARA_JALANKAN.md`.

## Pelajaran utama

**Label spesifik jauh mengalahkan label generik.** Di OSM,
`office=consulting` punya cakupan telepon 60% sementara `office=company`
hanya 12%. Pola sama muncul saat validasi query Places: `"pabrik plastik"`
menghasilkan pabrik asli dengan nomor telepon, sedangkan
`"perusahaan manufaktur"` hanya menghasilkan iklan lowongan kerja.

**Dedup harus di tingkat entitas, bukan tingkat ID sumber.** Dedup berbasis
`PRIMARY KEY` meloloskan 145 duplikat karena `PT. Bakti Mandiri Perkasa` dan
`PT BAKTI MANDIRI PERKASA` punya `osm_id` berbeda meski nomor teleponnya
sama persis.

**Nomor call-center bukan lead.** Format `1500-xxx` dan `0804-xxx` adalah
layanan pelanggan, bukan jalur ke pengambil keputusan.

**Ukur kebutuhan, bukan ukuran perusahaan.** Traveloka dan Tokopedia adalah
perusahaan besar dengan divisi marketing kuat, tapi tidak punya tim sales
lapangan — sehingga tidak cocok untuk produk ini. Rubric lama tidak bisa
membedakan mereka dari Wings Group; rubric baru bisa.

**OSM adalah panen sekali jalan, bukan pipeline harian.** Setelah 10 kota
tersapu, menjalankan ulang menghasilkan ~0 lead baru karena data OSM
bertambah sangat lambat dari kontribusi sukarelawan.

## Catatan data

`data/leads.db` sengaja dilacak versinya supaya hasil kerja terekam.
File backup (`leads_backup_*.db`) tidak — lihat `.gitignore`.

Karena git tidak bisa menampilkan perbedaan file binary, isi database juga
diekspor ke CSV agar perubahannya bisa dibaca lewat riwayat commit.
Jalankan `python src/ekspor_csv.py` setiap kali database berubah — dulu
langkah ini manual, sekarang ada skripnya supaya tidak terlupa.

Stempel waktu sengaja tidak ikut diekspor. Kalau ikut, tiap kali skrip
dijalankan seluruh baris terlihat berubah padahal datanya sama.
