# Jawaban untuk PST BPS — ID Transaksi #50964

**Status: DRAF. Periksa sebelum dikirim — ada satu hal yang HARUS
dipastikan Bryan sendiri, lihat bagian "Yang wajib dicek dulu".**

Kanal: `pst.bps.go.id` -> **Transaksi Saya** -> transaksi #50964 ->
balas di kolom percakapan.

**TENGGAT: Selasa, 8 September 2026.** Surel pemberitahuan (3 Sep 2026,
08.57 WIB) menyatakan konsultasi ditutup otomatis kalau tidak dibalas
dalam 3 hari kerja.

---

## Pertanyaan yang masuk

Balasan BPS lewat SILASTIK, 3 September 2026:

> Nama dan alamat perusahaan dipakai untuk **menyusun daftar calon
> pelanggan produk software**.
>
> Mohon bisa dikirimkan seperti apa susunan **daftar calon pelanggan
> produk software yang ingin dikomersialkan**?

## Cara membaca pertanyaannya

Ini **bukan penolakan** dan bukan pengalihan ketiga. BPS meminta
kejelasan bentuk penggunaannya sebelum memutuskan — artinya pertanyaan
izinnya sudah sampai ke orang yang menanganinya.

Tapi frasa *"daftar calon pelanggan yang ingin dikomersialkan"*
menyiratkan bahwa **daftarnya** yang dijual. Itu tidak benar, dan
kesalahpahaman itu justru yang paling menentukan hasilnya: menjual
daftar berisi nama-alamat dari direktori BPS = menjual kembali isi
publikasi. Memakai daftar itu untuk menelepon calon pelanggan produk
sendiri = penggunaan internal.

**Luruskan dulu duduk perkaranya di kalimat pertama, baru tunjukkan
susunannya.**

---

## Yang wajib dicek dulu — jangan kirim sebelum ini pasti

**1. Daftarnya betul-betul tidak dijual, kan?** Seluruh jawaban ini
berdiri di atas satu klaim: daftar dipakai sendiri untuk mencari
pelanggan Salesmart, tidak dijual, tidak diserahkan ke pihak lain,
tidak jadi bagian produk. Kalau ada rencana menjual daftarnya, atau
menampilkannya di dalam produk yang dijual, **jawabannya harus
berubah** — dan itu penggunaan yang jauh lebih berat izinnya.

**2. Repo ini PUBLIK, dan daftarnya ikut terbit di dalamnya.**
`data/kebutuhan_export.csv` dan `data/leads_export.csv` dilacak git,
dan dasbornya tayang di https://archieeez.github.io/salesmart-leadgen/
Artinya: kalau nama dan alamat dari direktori BPS masuk pipeline hari
ini, ia **otomatis ikut terbit ke internet**. Itu penerbitan ulang, dan
menulis "tidak menerbitkan ulang" tanpa menutup jalur ini akan jadi
pernyataan yang tidak benar.

Jalan keluarnya dipilih sekarang, bukan nanti:

- (a) **Sebutkan apa adanya ke BPS** (dipakai di draf di bawah), disertai
  komitmen bahwa baris berasal-BPS tidak akan masuk berkas publik
  kecuali diizinkan; atau
- (b) tutup dulu jalurnya di kode (kolom `sumber` + penyaring di
  `ekspor_csv.py`), baru menjawab.

Draf di bawah memakai (a) **plus** janji (b). Kalau izinnya nanti
turun, penyaringnya harus benar-benar dipasang — aturan yang tidak
dijalankan mesin cepat atau lambat dilanggar tanpa ada yang sengaja
melanggarnya.

---

## Versi untuk ditempel ke kolom balasan SILASTIK

> Terima kasih atas tanggapannya.
>
> Sebelum menjawab, izinkan saya meluruskan satu hal supaya tidak salah
> paham: **daftar calon pelanggan itu sendiri tidak dikomersialkan.**
> Daftar tersebut adalah catatan kerja internal tim penjualan kami —
> tidak dijual, tidak diserahkan kepada pihak lain, dan tidak menjadi
> bagian dari produk. Yang bersifat komersial adalah **produk perangkat
> lunaknya** (Salesmart, aplikasi manajemen tim penjualan lapangan).
> Daftar ini hanya dipakai untuk menentukan perusahaan mana yang kami
> hubungi untuk menawarkan produk tersebut.
>
> Berikut susunan daftarnya. Satu baris = satu perusahaan.
>
> **A. Kolom identitas perusahaan**
> 1. Nama perusahaan
> 2. Alamat / kota
> 3. Situs web resmi
> 4. Nomor telepon kantor
>
> **B. Kolom hasil penilaian kami sendiri** — bukan data statistik, tidak
> berasal dari publikasi BPS, seluruhnya kesimpulan kami dari membaca
> situs resmi perusahaan yang bersangkutan:
>
> 5. Model distribusi (punya jaringan sendiri / lewat distributor / tidak ada)
> 6. Ada-tidaknya tim penjualan lapangan
> 7. Perkiraan skala operasi
> 8. Kecocokan dengan produk kami
> 9. Skor kebutuhan 0-100, hasil penjumlahan nomor 5 sampai 8
> 10. Kutipan kalimat dari situs resmi perusahaan sebagai bukti tiap poin
> 11. Catatan dan status tindak lanjut (sudah dihubungi / belum / tidak sesuai)
>
> Contoh satu baris yang sudah terisi — perusahaan ini kami temukan dari
> sumber lain, bukan dari publikasi BPS:
>
> Nama: Garudafood | Situs: garudafood.com | Telepon: 021-7290110 |
> Model distribusi: jaringan sendiri | Tim lapangan: ada | Skor
> kebutuhan: 90 | Bukti: kutipan dari halaman resmi perusahaan.
>
> **Bagian mana yang akan berasal dari publikasi BPS**
>
> Hanya nomor 1 dan 2 — nama perusahaan dan alamatnya — dan hanya
> sebagai **daftar awal yang tetap kami verifikasi ulang satu per satu**
> ke situs resmi masing-masing perusahaan. Nomor 3 sampai 11 tidak ada
> di publikasi BPS dan tidak mungkin diambil dari sana.
>
> **Yang tidak kami ambil dari publikasi**: nilai produksi, jumlah tenaga
> kerja, kode KBLI, dan seluruh angka statistik lainnya. Kami juga tidak
> memakai data perseorangan — hanya identitas badan usaha.
>
> **Ukurannya**: daftar kami sekarang berisi 991 entri perusahaan yang
> berasal dari sumber lain (OpenStreetMap dan situs resmi perusahaan),
> 72 di antaranya sudah dinilai lengkap. Dari publikasi BPS kami
> memperkirakan menambah beberapa ribu nama sebagai kandidat awal.
>
> **Satu hal yang perlu saya sampaikan terbuka**: pengembangan alat ini
> saya kerjakan di repositori kode yang bersifat publik, sehingga berkas
> kerjanya saat ini dapat dilihat umum. Apabila izin diberikan, saya
> siap menyanggupi bahwa baris yang berasal dari publikasi BPS **tidak
> akan disertakan dalam berkas publik tersebut**, atau mengikuti
> ketentuan lain yang BPS tetapkan. Saya menyampaikannya di awal supaya
> tidak menjadi persoalan di kemudian hari.
>
> **Pertanyaan saya tetap sama**: apabila bentuk penggunaan seperti di
> atas dapat diizinkan, bagaimana cara memperoleh izin tertulisnya —
> lewat layanan berbayar di PST, perjanjian penggunaan data tersendiri,
> pengajuan ke Direktorat Statistik Industri selaku penyusun, atau kanal
> lain? Apabila tidak dapat diizinkan, mohon disampaikan juga, supaya
> saya tidak memakai publikasi tersebut.
>
> Terima kasih banyak atas waktunya.

---

## Kalau ditanya lanjutan

**"Berapa banyak nama yang akan diambil?"** — Jawab dengan angka, jangan
dikecilkan. Direktorinya terbit per provinsi dan per kota (Sumut 2023 =
1.273 perusahaan, Kota Bekasi 2024 = 470); agregat nasionalnya 31.795.
Yang relevan bagi kami hanya perusahaan berjaringan distribusi, jauh
lebih sedikit dari itu.

**"Apakah datanya diolah ulang atau dijual dalam bentuk lain?"** —
Tidak. Tidak ada penerbitan ulang, tidak ada penjualan data, tidak ada
turunan yang dibagikan.

**"Bisa pakai produk data berbayar PST saja?"** — Ini kemungkinan besar
arah yang mereka tuju, dan **itu jawaban yang sah**. Kalau ditawari,
tanyakan: harganya, cakupannya (per provinsi atau nasional), formatnya,
dan apakah lisensinya memang mengizinkan penggunaan komersial seperti
di atas. Catat jawabannya, jangan langsung membeli.

## Yang dicatat setelah dijawab

Salin ke `CATATAN_SUMBER_DATA.md`: nama dan jabatan penjawab, tanggal,
bisa/tidak bisa, mekanismenya, biayanya, bentuk dokumennya.

**Tetap berlaku: PDF direktori tidak disentuh dan pengekstrak tidak
dibangun sampai ada izin TERTULIS.** Jawaban di kolom percakapan
SILASTIK yang berbunyi "boleh" **belum tentu** izin tertulis yang
dimaksud halaman keterangan terbitan — kalau jawabannya positif, minta
bentuk resminya (surat atau surel resmi ber-nomor).

## Jalur cadangan — belum dipakai

Keberatan ke PPID, dasar UU 14/2008 Pasal 35 ayat (1) huruf e, tenggat
sekitar 15 Oktober 2026. Tahan selama PST masih menjawab; percakapan
yang berjalan justru memperkuat posisi kalau nanti tetap buntu.
