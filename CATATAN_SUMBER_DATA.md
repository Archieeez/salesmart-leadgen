# Catatan sumber data — apa yang boleh dan tidak

Dokumen ini mencatat hasil pemeriksaan kelayakan tiap sumber data, supaya
keputusannya tidak perlu diulang tiap kali dan tidak berubah-ubah karena
lupa. Setiap entri menyebut **apa yang diverifikasi langsung** dan **apa
yang belum**, karena keduanya berbeda nilainya.

---

## BPS (Badan Pusat Statistik) — diperiksa 1 September 2026

**Sasaran:** Direktori Perusahaan Industri Manufaktur, sekitar 31.795
perusahaan. Selama ini tercatat di antrian sebagai kandidat sumber data
baru dengan keterangan "ada catatan hukum" — catatan itu tidak pernah
benar-benar ditulis. Ini isinya.

### Kesimpulan

**Panen otomatis dari bps.go.id: TERTUTUP.** Bukan karena tafsir, tapi
karena robots.txt mereka menyebut ClaudeBot secara harfiah.

**Mengolah PDF yang diunduh manusia: BELUM JELAS**, dan bagian yang belum
jelas justru bagian yang menentukan untuk proyek ini.

### Yang diverifikasi langsung

**1. robots.txt memblokir ClaudeBot dan seluruh crawler AI besar.**

```
User-agent: ClaudeBot
Disallow: /
```

Sederet dengan GPTBot, CCBot, Google-Extended, Bytespider,
meta-externalagent, Amazonbot, dan Applebot-Extended — semuanya
`Disallow: /`.

Aturan proyek ini berbunyi "WAJIB patuh robots.txt, tidak ada
pengecualian". Tidak ada yang perlu ditimbang: jalur ini tertutup.

**2. Sinyal konten untuk semua agen lain.**

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /
```

`Allow: /` memang mengizinkan perayapan umum. Tapi `ai-train=no` dan
`use=reference` adalah pernyataan tegas bahwa isinya tidak untuk dicerna
sistem AI di luar rujukan. Memakai User-Agent proyek sendiri untuk
mengambil apa yang mereka tutup bagi AI adalah pengelakan, bukan
kepatuhan — persis semangat yang dilarang aturan proyek.

**3. Seluruh domain BPS menjawab 403 untuk permintaan dari sini.**

Dicoba `www.bps.go.id/id/term-of-use`, `kalsel.bps.go.id/id/term-of-use`,
dan satu halaman publikasi direktori. Ketiganya HTTP 403. Ini bukan
kebetulan teknis; ia sejalan dengan robots.txt di atas.

**4. Syarat API BPS MELARANG penggunaan komersial.**

Dari `webapi.bps.go.id/developer/terms`:

> "Anda tidak boleh... Menjual, menyewakan, atau melakukan sublisensi API
> BPS... untuk keuntungan dagang atau ekonomi"

dan komitmen "free and open access... **for non-commercial purposes**".
Penjualan ulang dan sublisensi dilarang tegas.

**5. Bentuk datanya bukan satu berkas.**

Direktori itu terbit **per provinsi dan per kota**, bukan satu PDF
nasional 31.795 baris. Contoh terbitan yang ada: DKI Jakarta 2024,
Kalimantan Selatan 2025, Sumatera Utara 2023 (1.273 perusahaan), Kota
Bekasi 2024 (470 perusahaan), Kota Banjarmasin 2023, Kota Semarang 2024,
Banten. Angka 31.795 adalah agregat — mengumpulkannya berarti mengurus
puluhan berkas terpisah, bukan satu unduhan.

### Yang BELUM terverifikasi, dan kenapa itu penting

Syarat penggunaan di situs web BPS (bukan API) tampaknya memberi lisensi
yang jauh lebih longgar — mencakup "penggunaan data, baik untuk
kepentingan komersial maupun nonkomersial", penyalinan, pendistribusian,
dan pemanfaatan kepada pihak ketiga.

**Itu bertentangan dengan syarat API di poin 4**, dan saya **tidak bisa
memverifikasinya sendiri** karena halamannya 403. Yang saya punya hanya
cuplikan hasil pencarian, dan cuplikan bukan sumber.

Perbedaan ini menentukan. Salesmart adalah produk komersial; daftar lead
dipakai untuk menjual. Kalau yang berlaku syarat non-komersial, seluruh
rencana ini gugur. Kalau yang berlaku syarat situs, ia justru sangat
terbuka.

### PEMBARUAN 1 Sep 2026 (sore) — larangan ada DI DALAM PDF-nya

Bryan membuka sendiri halaman syarat penggunaan di peramban, dan
mengutipnya: konten situs BPS diberikan gratis "untuk tujuan (i)
penggunaan data, baik untuk kepentingan komersial maupun nonkomersial;
(ii) penyalinan, pendistribusian... (iii) pemanfaatan konten... kepada
pihak ketiga dengan cara apa pun." Terbaca sangat terbuka.

PDF direktorinya lalu diunduh (`direktori-industri-manufaktur-2025.pdf`,
22,5 MB, 1.379 halaman, Volume 14). **Di halaman keterangan terbitannya
tertulis larangan yang berlawanan:**

> "Dilarang mereproduksi dan/atau menggandakan sebagian atau seluruh isi
> buku ini **untuk tujuan komersial** tanpa izin tertulis dari Badan
> Pusat Statistik"
>
> "It is prohibited to reproduce and/or duplicate part or all of this book
> for **commercial purpose** without permission from BPS-Statistics
> Indonesia"

Ini bukan syarat umum situs, melainkan syarat yang dicetak DI DALAM
terbitan yang mau dipakai. Yang khusus lebih menentukan daripada yang
umum, dan sekarang dua dari tiga sumber (syarat API + terbitan itu
sendiri) sama-sama menutup penggunaan komersial.

**Kesimpulan: mengekstrak isi direktori ini untuk Salesmart memerlukan
IZIN TERTULIS dari BPS lebih dulu.** Bukan jalan buntu — kalimatnya
sendiri menyebut "tanpa izin tertulis", jadi izinnya memang bisa diminta.
Kanalnya PPID BPS (ppid.bps.go.id).

**Sampai izin itu ada, jangan bangun pengekstraknya.**

Tindakan pengamanan yang sudah diambil: `*.pdf` dan `data/*.pdf`
dimasukkan ke .gitignore. Repo ini PUBLIK — meng-commit PDF-nya sama
dengan menerbitkan ulang terbitan berhak cipta itu ke internet.

### STATUS: PERMOHONAN SUDAH DIKIRIM — 1 September 2026

Permohonan izin diajukan lewat e-PPID BPS (`ppid.bps.go.id`), kategori
**Informasi Publik** (bukan "Data Statistik" — yang diminta izin, bukan
file; publikasinya sudah diunduh).

Isian yang dipakai ada di `surat/permohonan-izin-bps.md`. Cara memperoleh
informasi dipilih "Mendapatkan salinan (softcopy)" lewat **email**, supaya
izinnya berbentuk dokumen tertulis yang bisa disimpan sebagai bukti.

Balasan formulir: **"pengajuan informasi akan direspon maksimal 3 hari
kerja"**. Tenggat menurut UU 14/2008 lebih longgar (10 hari kerja, dapat
diperpanjang 7 hari kerja), jadi 3 hari kerja itu janji layanan BPS
sendiri.

**Perkiraan jawaban: sekitar 4 September 2026.**

Kalau lewat tenggat dan belum ada kabar, ajukan keberatan lewat kanal
yang sama. Begitu jawabannya datang, SALIN ISINYA KE BERKAS INI — apa pun
jawabannya — supaya keputusan ini tidak perlu diperdebatkan lagi.

**Sampai jawaban itu ada, `data/direktori-industri-manufaktur-2025.pdf`
TIDAK DISENTUH.** Tidak ada pengekstrak yang dibangun, tidak ada isinya
yang dipindahkan ke database.

### Bentuk datanya (untuk menimbang layak-tidaknya mengejar izin)

- 1.379 halaman, PDF teks (bukan pindaian), bisa dibaca `pdftotext`
- Tata letak TIGA KOLOM per halaman
- Per perusahaan: NAMA (berikut bentuk badan usaha: PT, CV, UD) dan
  ALAMAT lengkap sampai kecamatan, kabupaten, provinsi, kode pos
- Di halaman contoh TIDAK terlihat kode KBLI maupun jumlah tenaga kerja
  per baris — kemungkinan KBLI dipakai sebagai pengelompokan bab, bukan
  kolom. Perlu diperiksa lagi kalau izin sudah keluar.
- Ada watermark "https://www.bps.go.id" yang ikut terbaca sebagai teks
  dan menyisip ke tengah data — harus dibersihkan
- Isinya nyata dan relevan: di satu halaman contoh saja sudah muncul
  CALBEE WINGS FOOD PT dan CAMPINA ICE CREAM INDUSTRY PT
- TIDAK ADA alamat situs web. Jadi dist_model dan field_sales tetap harus
  dicari dari situs perusahaan, seperti sekarang.

### Yang perlu dilakukan manusia (tidak bisa saya kerjakan)

1. **Buka sendiri di peramban** `https://www.bps.go.id/id/term-of-use`.
   Halaman itu terbuka normal untuk orang; yang diblokir agen otomatis.
   Baca bagian lisensinya, dan perhatikan apakah kata "komersial" benar
   ada di sana.
2. **Tanyakan resmi lewat PPID BPS** (`ppid.bps.go.id`) — kanal permintaan
   informasi publik. Pertanyaannya cukup satu kalimat: bolehkah isi
   Direktori Perusahaan Industri Manufaktur dipakai untuk keperluan
   komersial. Jawaban tertulis dari PPID menutup ambiguitas ini
   sepenuhnya, dan sekaligus jalur yang sah untuk meminta datanya.
3. Kalau jawabannya boleh: **unduh PDF-nya sendiri lewat peramban**.
   robots.txt mengatur perayapan robot, bukan apa yang dilakukan manusia
   terhadap berkas yang ia unduh secara sah. Mengolah berkas yang sudah
   ada di cakram lokal tidak menyentuh larangan itu sama sekali.

### Catatan tambahan

Pembelian **mikrodata** (bukan direktori) mensyaratkan Surat Perjanjian
Penggunaan Data (SPPD). Direktori dan mikrodata dua hal berbeda — SPPD
tidak otomatis berlaku untuk direktori terbitan, tapi kalau nanti
mikrodata yang diincar, syarat itu ikut.

---

## Places API (Google) — ditutup 31 Agustus 2026

Ditolak Bryan atas dasar biaya, bukan hukum. Jangan diusulkan lagi
sebagai jalan keluar. Lihat memori `no-paid-api-hybrid`.

---

## Papan lowongan pihak ketiga — ditutup 31 Agustus 2026

JobStreet dan Glints memblokir lewat robots.txt. ToS Kalibrr, Indeed, dan
Karir.com tidak bisa diverifikasi. Sumber lowongan yang sah hanya halaman
karier di situs perusahaan itu sendiri.

## LinkedIn — ditutup

Dilarang ToS. Tidak ada pengecualian.

## Database telepon bulk — ditutup

Risiko UU PDP. Hanya data kontak level perusahaan yang boleh.
