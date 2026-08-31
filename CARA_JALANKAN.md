# Cara menjalankan — urut dari nol

**Sebelum mulai:** buka folder ini di VS Code lewat `File > Open Folder`.
Kalau tidak, terminal mulai dari folder instalasi VS Code dan file bisa
nyasar ke sana. Cek dengan mengetik `cd` — harus muncul `D:\lead-agent`.

Semua perintah dijalankan dari folder utama (`lead-agent`), bukan dari
dalam `src/`.

---

## Persiapan (sekali saja)

```
pip install requests beautifulsoup4
```

Untuk Phase 2 (penilaian kebutuhan via LLM), tambahan:
```
pip install anthropic
```
Perlu kunci API: `setx ANTHROPIC_API_KEY "sk-ant-..."` lalu buka terminal baru.

---

## Kelompok A — tanpa internet, cek dulu semua file utuh (2 menit)

### 1. Uji aturan penilaian
```
python src/rubrik.py
```
Harus keluar `Cocok: 14/14 (100%)`. Kalau tidak, ada file rusak — berhenti.

### 2. Lihat rencana query Places API
```
python src/query_plan.py
```
Menampilkan 160 query tervalidasi. Belum memanggil API apa pun.

### 3. Hitung prioritas 20 perusahaan
```
python src/hitung_prioritas.py
```
Membaca `data/companies_scored.csv` → menghasilkan
`data/companies_prioritas.csv`.

---

## Kelompok B — periksa data yang sudah ada

### 4. Periksa kualitas database
```
python src/cek_db.py
```

### 5. Audit entri yang dibuang
```
python src/cek_arsip.py
```
Bagian "dibuang TAPI punya telepon" wajib dibaca — kalau ada perusahaan
asli di situ, filternya salah buang.

### 6. Buat dashboard visual
```
python src/buat_dashboard.py
```
Menghasilkan `docs/index.html`. Klik dua kali untuk membukanya di browser.

---

## Kelompok C — panen ulang (butuh internet, 30–60 menit)

Hanya perlu kalau mau menambah data baru. `data/leads.db` yang sudah ada
berisi hasil panen sebelumnya (991 entri bersih).

### 7. Panen dari OpenStreetMap
```
python src/discover_osm.py
```
10 kota x 10 kategori. Aman ditinggal — kalau mati di tengah jalan,
jalankan lagi dan dia lanjut dari yang belum selesai.

Catatan: OSM adalah panen sekali jalan. Karena 100 kombinasi sudah selesai
semua (tercatat di tabel `harvest_log`), menjalankan ini sekarang akan
melewati semuanya dan menghasilkan 0 lead baru. Itu perilaku yang benar.

### 8. Bersihkan dan hapus duplikat
```
python src/bersihkan_db.py
```
Otomatis backup dulu. Yang dibuang dipindah ke tabel `leads_arsip`, tidak
dihapus permanen.

### 9. Ulangi langkah 4–6 untuk melihat hasil barunya

---

---

## Kelompok D — menilai KEBUTUHAN perusahaan (Phase 2)

Ini jalur yang penting sekarang: bukan "punya nomor telepon?" tapi
"perusahaan ini butuh Salesmart atau tidak?".

### 10. Panen halaman bukti
```
python src/panen_bukti.py --input data/seed_gapmmi.csv --cache data/.cache_html
```
Mengambil halaman Tentang Kami, Bisnis, Distribusi, Produk, dan Karier —
bukan halaman kontak. Hasilnya masuk tabel `halaman_bukti`.

Halaman karier dipanen dari situs perusahaan sendiri, BUKAN dari papan
lowongan. JobStreet dan Glints melarang lewat robots.txt; ToS Kalibrr,
Indeed, dan Karir.com belum bisa diverifikasi. Jangan pakai ketiganya
sampai ToS-nya dibaca.

### 10b. Panen bukti untuk lead OSM yang punya website

Dari 991 lead OSM, hanya 180 yang punya alamat website — dan setelah
domain duplikat dibuang, tersisa 170 situs unik. Itulah batas atas berapa
banyak lead OSM yang bisa dinilai dengan cara ini.

Bikin daftarnya dulu:
```
python -c "import sqlite3,csv;from urllib.parse import urlparse;c=sqlite3.connect('data/leads.db');rows=c.execute(\"select osm_id,name,category,city,website from leads where website is not null and website!='' order by name\").fetchall();seen={};[seen.setdefault(urlparse(w if w.startswith('http') else 'https://'+w).netloc.lower().replace('www.',''),dict(nama=n.strip(),website=w if w.startswith('http') else 'https://'+w,sumber='osm',kategori=k,kota=ci or '',osm_id=o)) for o,n,k,ci,w in rows];out=list(seen.values());f=open('data/seed_osm_website.csv','w',newline='',encoding='utf-8');wr=csv.DictWriter(f,fieldnames=['nama','website','sumber','kategori','kota','osm_id']);wr.writeheader();wr.writerows(out);print(len(out))"
```

Lalu panen:
```
python src/panen_bukti.py --input data/seed_osm_website.csv --cache data/.cache_html
```
Butuh 1–3 jam. Aman ditinggal: halaman yang sudah diambil masuk cache,
jadi kalau mati di tengah jalan, jalankan lagi dan yang sudah selesai
tidak diunduh ulang.

### 11. Lihat biaya sebelum keluar duit
```
python src/nilai_kebutuhan.py --dry-run
```
Menampilkan prompt lengkap dan perkiraan biaya. Belum memanggil API.

### 12. Nilai kebutuhannya
```
python src/nilai_kebutuhan.py --limit 5     # coba 5 dulu
python src/nilai_kebutuhan.py               # semuanya
```
Hasil masuk tabel `kebutuhan` di `leads.db`, lengkap dengan kutipan bukti
tiap penilaian. Bahan mentahnya dibaca dari `bukti.db`.

### 13. Ekspor ke CSV sebelum commit
```
python src/ekspor_csv.py
```
WAJIB dijalankan tiap kali database berubah. Tanpa ini, riwayat commit
cuma menampilkan "file binary berubah" dan isinya tidak bisa diperiksa.

Cara memeriksa hasilnya: ke-27 perusahaan di `seed_gapmmi.csv` adalah
anggota GAPMMI — semuanya produsen makanan-minuman. Jadi `industry_fit`
seharusnya hampir semuanya `produsen_barang_konsumsi`. Kalau tidak,
promptnya yang salah, bukan perusahaannya.

---

## Kalau mau benar-benar mulai dari nol

```
del data\leads.db
python src/discover_osm.py
python src/bersihkan_db.py
```

Jangan hapus `leads_backup_*.db` sampai yakin hasil barunya benar.
