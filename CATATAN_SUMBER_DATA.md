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

### PEMBARUAN 2 Sep 2026 — respon pertama BPS: tenggat mundur ke ~15 Sep

Bryan menerima balasan dari BPS (disalin apa adanya):

> "Terima kasih telah melakukan permohonan informasi. Pemberitahuan
> Tertulis akan kami berikan maksimal 10 hari kerja."

Artinya:

- Ini **penerimaan permohonan**, bukan jawaban. Permohonannya masuk dan
  diproses — bukan ditolak, bukan diabaikan.
- BPS memakai tenggat **UU 14/2008 (10 hari kerja)**, bukan janji "3 hari
  kerja" dari formulirnya. Dihitung dari 1 September:
  **jatuh tempo sekitar 15 September 2026** (2–4, 7–11, 14–15 Sep;
  tidak ada hari libur nasional di rentang itu).
- Frasa "Pemberitahuan Tertulis" adalah istilah UU KIP — bentuknya
  dokumen resmi, persis yang diminta (izin tertulis yang bisa disimpan).
- UU yang sama membolehkan perpanjangan 7 hari kerja lagi; kalau dipakai,
  paling lambat ~24 September 2026.

Konsekuensi untuk rencana kerja: **jangan menunggu-nunggu 4 September.**
Pekerjaan yang tidak butuh BPS (penyaringan, pembacaan antrian,
pelengkapan kontak) jalan terus. Kalau **15 September** lewat tanpa
Pemberitahuan Tertulis, barulah ajukan keberatan.

**Sampai jawaban itu ada, `data/direktori-industri-manufaktur-2025.pdf`
TIDAK DISENTUH.** Tidak ada pengekstrak yang dibangun, tidak ada isinya
yang dipindahkan ke database.

### JAWABAN BPS SUDAH DATANG — 2 September 2026

Pemberitahuan Tertulis No. **202609007**, ditandatangani PPID BPS RI,
tertanggal 2 September 2026. Datang **1 hari kerja** setelah permohonan,
jauh lebih cepat dari perkiraan 10 hari kerja.

**Berkas aslinya TIDAK dimasukkan ke repo ini.** Formulirnya memuat
alamat rumah, nomor telepon pribadi, dan surel pribadi Bryan; repo ini
publik. Yang disalin di bawah hanya substansinya.

#### Isi jawabannya

**Bagian A — "Informasi Dapat Diberikan"** (terisi):

| Butir | Isi |
|---|---|
| Penguasaan informasi | **Kami** (BPS), bukan badan publik lain |
| Bentuk fisik tersedia | Softcopy |
| Biaya | Rp 0 |
| Waktu penyediaan | 1 hari kerja |
| Penghitaman informasi | tidak ada |

Kolom keterangan butir pertama seluruhnya berupa **pengalihan**:

> "Untuk permohonan informasi terkait data statistik, silakan untuk
> menghubungi: Pelayanan Statistik Terpadu BPS (pst.bps.go.id) atau
> nomor telepon 021-3507057."

disusul petunjuk pemakaian `pst.bps.go.id` dan empat standar layanannya:
perpustakaan (cari data mandiri), konsultasi, **produk berbayar** (beli
data mikro dan peta digital), dan rekomendasi kegiatan statistik.

**Bagian B — "Informasi tidak dapat diberikan karena"**: ketiga kotaknya
**KOSONG**. Tidak dicentang "belum dikuasai", tidak dicentang "belum
didokumentasikan", tidak dicentang "alasan lainnya".

#### Pembacaan yang jujur: BUKAN DITOLAK, TAPI JUGA BUKAN IZIN

Ini yang harus dipegang, dan jangan dibaca lebih longgar dari
seharusnya.

**Permohonannya menanyakan tiga hal** (lihat `surat/permohonan-izin-bps.md`,
angka 5):

1. izin tertulis mereproduksi nama + alamat perusahaan untuk tujuan
   komersial;
2. kalau tidak bisa, adakah mekanisme sah lain — misalnya pembelian data
   atau perjanjian penggunaan data;
3. ketentuan mana yang berlaku saat T&C laman BPS dan larangan di dalam
   terbitan saling bertentangan.

**Tidak satu pun dijawab secara substansi.** Kata "izin", "komersial",
"reproduksi", dan "hak cipta" tidak muncul sama sekali di seluruh
dokumen. Permohonan sengaja diajukan di kategori "Informasi Publik"
justru supaya tidak dibaca sebagai permintaan data — tapi PPID tetap
menanganinya sebagai permintaan data statistik dan mengalihkannya ke
meja layanan data.

Artinya, secara formal permohonan **dilayani dan tidak ditolak**, tapi
**larangan di halaman keterangan terbitan masih berdiri utuh**:

> "Dilarang mereproduksi ... untuk tujuan komersial tanpa izin tertulis
> dari Badan Pusat Statistik"

Surat ini bukan izin tertulis itu. Ia tidak memberi hak apa pun atas isi
publikasi.

**Maka aturannya TIDAK berubah: `data/direktori-industri-manufaktur-2025.pdf`
tetap tidak disentuh, dan pengekstrak tetap tidak dibangun.**

#### Yang justru berguna dari jawaban ini

Pengalihannya bukan jalan buntu — ia menunjuk kanal yang sebelumnya tidak
diketahui. Standar layanan (c) berbunyi **"Layanan produk berbayar, jika
sudah paham dan akan membeli data mikro dan peta digital"**. Keberadaan
kanal jual-beli data resmi adalah jawaban parsial untuk pertanyaan nomor
2 di atas: mekanisme komersial memang ADA di BPS, hanya belum jelas
apakah direktori ini termasuk di dalamnya.

#### Langkah berikutnya — dua jalur, tidak saling meniadakan

**Jalur 1 (disarankan lebih dulu): tanya PST.** Ini kanal yang ditunjuk
BPS sendiri, jadi tidak bisa dibilang salah alamat. Pertanyaannya harus
dipersempit ke satu hal supaya tidak dialihkan lagi: *apakah izin
penggunaan komersial atas isi Direktori Industri Manufaktur 2025 bisa
diperoleh, dan lewat layanan yang mana.* Draf ada di
`surat/pertanyaan-lisensi-pst.md`.
Kontak: pst.bps.go.id atau 021-3507057.

#### STATUS JALUR 1: SUDAH DIKIRIM — 2 September 2026, 15:47 WIB

**ID Transaksi PST: #50964**, jenis "Konsultasi Data", media Layanan
Online, cakupan Nasional. Status saat dicatat: **Menunggu**.
Balasan dijanjikan lewat **email**.

Yang dikirim: pertanyaan tunggal soal cara memperoleh izin tertulis
penggunaan komersial, dibuka dengan pernyataan tegas bahwa datanya
SUDAH dimiliki dan ini bukan permintaan data. Dilampiri PDF
Pemberitahuan Tertulis 202609007 sebagai bukti bahwa PST-lah yang
ditunjuk PPID, bukan alamat yang dipilih sendiri.

Catatan pengisian yang berpengaruh, kalau nanti perlu diulang:
- **Kategori institusi: Swasta.** Bukan "Lembaga Penelitian &
  Pendidikan" walau itu terlihat lebih mudah aksesnya — mendaftar
  sebagai lembaga penelitian lalu meminta izin KOMERSIAL saling
  bertabrakan, dan bisa membatalkan izin yang sudah keluar karena
  dasarnya keliru.
- **Tag: Industri**, bukan "Komunikasi" (sempat salah pilih). Tag
  menentukan meja mana yang menangani; salah tag berarti dioper lagi.

**Sampai ada jawaban tertulis, tidak ada yang berubah: PDF tidak
disentuh, pengekstrak tidak dibangun.** Jawaban lisan lewat telepon
tidak dihitung — kalau positif, minta dikirim lewat surel.

**Jalur 2 (cadangan): keberatan ke PPID.** UU 14/2008 Pasal 35 ayat (1)
huruf e memberi dasar keberatan untuk *"permintaan informasi ditanggapi
tidak sebagaimana yang diminta"* — dan itu persis yang terjadi. Tenggat
pengajuan keberatan 30 hari kerja sejak Pemberitahuan Tertulis diterima,
jadi **paling lambat sekitar 15 Oktober 2026**.

Jalur 2 sebaiknya ditahan dulu sampai PST menjawab. Mengajukan keberatan
atas surat yang secara formal "tidak menolak" lebih lemah posisinya
daripada menunjukkan bahwa kanal yang mereka tunjuk sendiri pun tidak
menyelesaikan pertanyaannya.

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

---

## Panen ulang situs gagal — diuji 2 September 2026, HASIL NOL

Dari 81 percobaan panen yang gagal, 39 berkategori `situs_mati` (33) dan
`http_error` (6) — sisanya `robots_larang` (29, tertutup permanen) dan
`js_render` (13, sudah diputuskan tidak sepadan).

**Ke-39 itu dicoba ulang. Hasilnya nol halaman, tanpa kecuali.**

### Cara pengujiannya

1. **Saring lewat DNS dulu**, supaya tidak membebani server yang jelas
   mati. Dari 39, **21 masih menjawab DNS** dan 18 benar-benar hilang.
2. **21 itu dipanen ulang** dengan `web.py` yang sudah ditambal
   (fallback varian www kini menyala juga pada ConnectionError, bukan
   cuma pada SSLError).
3. Hasil: **21 dari 21 tetap 0 halaman.** Alasan gagalnya identik
   persis dengan yang tercatat 31 Agustus: ConnectTimeout 5,
   ConnectionError 4, SSLError 3, http 403 3, http 404 3, ReadTimeout 2.

### Kenapa hasilnya nol, padahal DNS menjawab

DNS menjawab ≠ situs hidup. Yang menjawab kebanyakan parkir domain,
Cloudflare tanpa origin, atau server yang menolak sambungan. Contoh
paling jelas: `www.carsworld.co.id` menjawab DNS, tapi robots.txt-nya
melarang DAN origin-nya balas HTTP 530.

### Kenapa ini tetap layak dikerjakan

Karena sebelumnya jawabannya "kemungkinan besar tidak berguna" —
sebuah dugaan. Sekarang jawabannya angka. Kalau nanti ada yang
mengusulkan panen ulang lagi dengan alasan "kan crawler-nya sudah
diperbaiki", biayanya sudah diketahui (21 situs, ~9 detik per situs,
~3 menit) dan hasilnya juga.

### Yang TIDAK diuji, dan kenapa

- **29 `robots_larang`** — tertutup permanen, bukan soal teknis.
- **13 `js_render`** — butuh headless browser, sudah diputuskan tidak
  sepadan (bedah 81 kegagalan, 1 Sep: dari 13 hanya 7 aplikasi JS
  sungguhan, dan cuma 1 yang mungkin lead).
- **18 yang DNS-nya mati** — tidak ada yang bisa disambungi.

**Kesimpulan: tumpukan panen gagal sudah habis.** Jangan dicoba ulang
tanpa alasan baru yang konkret, misalnya seed URL-nya terbukti salah
(bukan situsnya yang mati).


---

## robots.txt: 23 situs pernah salah dicap "melarang" — diperbaiki 2 Sep 2026

Selama ini 29 situs tercatat `robots_larang` dan dianggap tertutup
permanen. Setelah diperiksa ulang dengan pengurai yang benar, **hanya 6
yang benar-benar tertutup.**

### Penyebabnya: robots.txt diambil pakai user-agent yang salah

`RobotFileParser.read()` bawaan Python mengambil robots.txt memakai
**user-agent default urllib** (`Python-urllib/3.x`), bukan `USER_AGENT`
yang kita deklarasikan. Situs ber-WAF (Cloudflare dsb.) menolak urllib
dengan HTTP 403. urllib menafsirkan 403 sebagai `disallow_all`, dan
pipeline mencatatnya:

> "robots.txt melarang User-Agent kita"

Pernyataan itu salah dua kali: robots.txt-nya **tidak pernah terbaca**,
dan yang diblokir **bukan agen kita**.

Contoh paling telanjang: `artaboga.com/robots.txt` menjawab HTTP 200
dengan isi `<script>location.href='https://www.artaboga.com/ID/';</script>`
— itu halaman pengalih, bukan robots.txt. Tidak ada satu pun aturan
larangan di sana.

`web._muat_robots()` sekarang mengambilnya lewat `requests` dengan
USER_AGENT kita, lalu menyerahkan isinya ke `RobotFileParser.parse()`.

### Hitungan yang benar

| Kategori | Jumlah |
|---|---|
| Benar-benar melarang robots.txt | **5** — EST Jakarta, facebook.com, most.co.id, powercableindonesia.com, pln.co.id |
| Ditolak Content-Signal (`ai-train=no`) | **1** — acibademinternational.com |
| Tidak pernah diblokir | **23** |

### Yang paling mahal dari kesalahan ini

**PT Arta Boga Cemerlang** — lengan distribusi FMCG Orang Tua Group,
distributor sungguhan dan profil sasaran paling inti — tercatat sejak
31 Agustus sebagai *"diblokir robots.txt, kehilangan nyata, tutup
buku"*. Ia tidak pernah tertutup. Setelah dipanen: skor pola 65.

**TransTRACK.ID** juga pulih dengan skor pola 90 — tapi ia PESAING,
jadi tetap tidak boleh ditelepon.

### Pelajaran yang lebih umum

"Diblokir" adalah kesimpulan, bukan pengamatan. Yang benar-benar
diamati waktu itu cuma "sebuah permintaan HTTP gagal". Menyimpan
kesimpulan sebagai fakta permanen — lalu menandainya "tutup buku" —
membuat kesalahan alat menjadi kesalahan data yang tidak pernah
ditinjau ulang. Catat pengamatannya (status HTTP, agen yang dipakai),
bukan tafsirannya.

## Content-Signal sekarang dijalankan mesin

robots.txt `bps.go.id` memberi `Allow: /` untuk `User-agent: *`, dan
hanya melarang bot ber-nama AI (ClaudeBot, GPTBot, CCBot,
Google-Extended, meta-externalagent, dst). Agen kita bernama
`salesmart-leadgen`, jadi ia jatuh ke grup `*` dan **secara harfiah
diizinkan**.

Keputusan 1 September sudah menyatakan bahwa memakai nama sendiri untuk
mengambil apa yang mereka tutup bagi AI adalah pengelakan — tapi
keputusan itu hanya tertulis di dokumen ini. Kodenya tetap akan memanen
bps.go.id kalau ada yang menaruhnya di seed.

Sekarang `web.boleh_ambil()` memungut `Content-Signal` dari robots.txt
dan menolak situs yang menyatakan `ai-train=no` atau `ai-input=no`,
berapa pun bunyi baris `Allow`-nya. Pipeline ini memasukkan teks
terpanen ke model bahasa untuk dinilai — itu persis "ai-input", jadi
sinyalnya memang mengenai kita.

**Aturan yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa
ada yang sengaja melanggarnya.**
