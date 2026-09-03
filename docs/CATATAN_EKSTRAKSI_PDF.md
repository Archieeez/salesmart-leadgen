# Mengekstrak Direktori Industri Manufaktur BPS — apa yang sudah diuji

Ditulis 3 Sep 2026, setelah BPS menyatakan nama dan alamat boleh dipakai
tanpa izin tertulis. Ini catatan **temuan**, bukan rencana: supaya sesi
berikutnya tidak mengulang tiga percobaan yang sama.

## Alat yang ada di mesin ini

| | |
|---|---|
| `pdftotext` | **Xpdf 4.00**, bukan Poppler |
| `pypdf` / `pdfplumber` / `PyMuPDF` | tidak terpasang |

**Ini menentukan segalanya.** `pdftotext` versi Xpdf **tidak mendukung
pemotongan area** (`-x -y -W -H`). Padahal memotong per kolom adalah cara
paling bersih untuk halaman tiga kolom: tiap kolom jadi aliran teks satu
kolom, dan record terpisah dengan sendirinya. Itu jalan yang tertutup di
sini, bukan jalan yang belum dicoba.

## Bentuk halamannya

- 1.379 halaman, PDF teks (bukan pindaian)
- **Tiga kolom** per halaman
- Per perusahaan: NAMA (huruf besar, sering membungkus ke baris kedua,
  mis. `CAHAYA LESTARI SAWITA,` lalu `PT`) diikuti alamat lengkap sampai
  kecamatan, kabupaten, provinsi, kode pos
- Urutannya **alfabetis** — berguna sebagai uji kewarasan nanti
- **Watermark `https://www.bps.go.id` dirender vertikal di margin kiri**,
  satu potongan per baris: `.id`, `o`, `.g`, `s`, `p`, `.b`, `w`,
  `s://w`, `tt`, `h`

## Tiga mode ekstraksi, diuji ke halaman yang sama

### `-layout`
Kolom terjaga, tapi batas kolomnya bergeser tiap halaman dan baris yang
kepanjangan menyeberang. Menghasilkan nama tercampur bleed kolom sebelah,
mis. `CAHAYA TIDAR` + `SOKA, SALAKAN` (dua record berbeda).

### `-table`
Kolom paling rapi dan **baris kosong antar-record ada di ketiga kolom** —
sempat terlihat seperti jawabannya. Tapi di pita tempat watermark berada,
watermark **menyuntikkan baris kosong ke SEMUA kolom**, bukan cuma kolom
kiri. Jadi memotong per baris kosong pecah di situ: satu record terbelah
jadi empat.

### `-fixed 6` — paling menjanjikan, dan paling menipu
Di bagian atas halaman hasilnya sempurna: satu record per paragraf, sudah
tergabung, tanpa watermark, tanpa bleed.

    CAHAYA KENCANA, CV JLN. MOJOPAHIT NO 29 Gedangrowo Kec. Prambon
    Kab. Sidoarjo Jawa Timur 61264

Tapi begitu masuk pita watermark, ia hancur total — potongan URL menyatu
ke dalam teks (`28382s://w CAKRA PILAR WISESA, PT`) dan record dari tiga
kolom saling menempel jadi satu paragraf raksasa.

## Angka yang diukur, bukan ditebak

41 halaman (40–80) dengan `-fixed 6`:

| | |
|---|---|
| record utuh | 430 |
| paragraf lain | 528 |
| **rasio utuh** | **44%** |

Dan 44% itu masih terlalu optimis: dari yang "utuh" pun, batas nama
sering salah. `BALI EKSTRAK UTAMA` terpotong jadi nama `BALI EKSTRAK`
dengan alamat diawali `UTAMA`.

**Kesimpulannya: cara teks-polos ini belum layak dipakai.** Memakainya
berarti kehilangan lebih dari separuh direktori DAN menyimpan nama yang
salah potong pada sisanya — persis jenis kesalahan yang menyusup tanpa
suara, karena keluarannya tetap terlihat masuk akal.

## Jalan yang belum ditutup

**Pasang alat yang memberi KOORDINAT, bukan teks yang sudah dirata.**
`pdfplumber` atau Poppler `pdftotext` memberi posisi tiap kata, sehingga
kolom dipisah berdasarkan koordinat x — bukan ditebak dari pola spasi —
dan watermark dibuang berdasarkan posisinya di margin, bukan dari
mencocokkan potongan string.

Keduanya gratis dan sumber terbuka, jadi tidak menabrak keputusan
"tanpa API berbayar" ([[no-paid-api-hybrid]]): itu soal langganan, bukan
soal pustaka.

Dengan koordinat, ketiga cacat di atas hilang sekaligus — bukan ditambal
satu per satu. Menambalnya dengan heuristik teks bisa saja dikerjakan,
tapi hasilnya akan selalu berupa tebakan yang tidak bisa diverifikasi
tanpa membaca ulang PDF-nya dengan mata.

## Yang TIDAK boleh terlupa saat ekstraksi jalan nanti

Hasilnya masuk `data/bps.db` (sudah di `.gitignore`), **bukan**
`leads.db` yang dilacak git. Penegaknya `src/publik.py`, dan
`ekspor_csv.py` menolak jalan kalau ada baris berasal-BPS bocor ke berkas
publik. Lihat `CATATAN_SUMBER_DATA.md`: yang BPS izinkan adalah memakai
nama dan alamat; yang tetap dilarang adalah menerbitkannya kembali.
