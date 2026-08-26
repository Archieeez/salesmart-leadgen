# Cara menjalankan — urut dari nol

**Sebelum mulai:** buka folder ini di VS Code lewat `File > Open Folder`.
Kalau tidak, terminal mulai dari folder instalasi VS Code dan file bisa
nyasar ke sana. Cek dengan mengetik `cd` — harus muncul `D:\lead-agent`.

Semua perintah dijalankan dari folder utama (`lead-agent`), bukan dari
dalam `src/`.

---

## Persiapan (sekali saja)

```
pip install requests
```

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

## Kalau mau benar-benar mulai dari nol

```
del data\leads.db
python src/discover_osm.py
python src/bersihkan_db.py
```

Jangan hapus `leads_backup_*.db` sampai yakin hasil barunya benar.
