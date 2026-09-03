---
name: nilai-lead
description: Nilai satu atau beberapa perusahaan dari bukti situsnya memakai alur tiga lapis (pembaca, pemeriksa adversarial, verifikasi kutipan mesin), lalu tulis ke database dan bangkitkan ulang dasbor. Pakai kapan pun diminta menilai, membaca, atau menskor perusahaan di proyek salesmart-leadgen — termasuk waktu diminta "baca kandidat antrian" atau "nilai ulang X".
---

# Menilai lead dengan alur tiga lapis

Perusahaan dinilai dari kutipan situsnya sendiri, bukan dari yang kamu
tahu tentang mereka. Tiga lapis memeriksa hal yang **berbeda**, dan
ketiganya wajib. Jangan memotong satu pun.

| lapis | siapa | ketat pada |
|---|---|---|
| 1 | agen PEMBACA | memilih pita yang bisa dipertahankan kutipannya |
| 2 | agen PEMERIKSA | membantah pembaca — bukan meninjau |
| 3 | `terapkan.py` | kutipannya benar-benar ADA di dokumen |

Kutipan Ajinomoto pernah LOLOS lapis 3 (regex `\s+` mencocokkan U+2028)
tapi GUGUR di `grep -F` lapis 2. Yang literal ternyata lebih benar.
**Jangan buang salah satu lapisan.**

## Jalankan

### 1. Rakit bahan

```
python src/baca/siapkan.py --nama "Nama A" "Nama B" --keluar kerja/<label>
```

Pakai `<label>` yang menyebut isinya dan tanggalnya, misal `antrian-3sep`.
Nama perusahaan harus **persis** seperti di database. Kalau `siapkan.py`
bilang "LEWAT (belum dipanen)", situsnya belum dipanen — jalankan
`panen_bukti.py` dulu, jangan mengarang penilaian tanpa bukti.

Perintah ini menghasilkan, per perusahaan:
`<slug>.md` (bahan bacanya), `prompt-pembaca-<slug>.md`,
`prompt-pemeriksa-<slug>.md`, plus `aturan.md` dan `daftar.json` bersama.

### 2. Jalankan agen PEMBACA — satu per perusahaan

Untuk tiap perusahaan, jalankan satu subagen dengan isi
`prompt-pembaca-<slug>.md` sebagai promptnya.

**Pakai isi berkas itu apa adanya. JANGAN mengarang prompt sendiri.**
Prompt itu dibangkitkan dari `rubrik.PITA` dan `rubrik.PENANDA_TOLAK`,
jadi label sah, bentuk field `penolakan`, dan daftar jebakan selalu ikut
berubah begitu rubriknya berubah. Prompt yang diketik ulang dari ingatan
akan melenceng, dan melencengnya tidak akan terlihat.

Perusahaan yang berbeda saling bebas — jalankan agennya bersamaan.

### 3. Jalankan agen PEMERIKSA — setelah pembacanya selesai

Sama caranya, dengan `prompt-pemeriksa-<slug>.md`.

Pemeriksa diberi SATU tugas: **membantah**. Kalau kamu tergoda
menyuruhnya "meninjau" atau "menyempurnakan", jangan — bedanya besar di
hasil. Selama 2-3 Sep 2026 pemeriksa menjatuhkan Nutrifood 80→70,
Alfamart 85→70, TransTRACK 90→15, dan menurunkan dua keyakinan pada
Arta Boga.

Pemeriksa yang GAGAL JALAN bukan alasan melanjutkan: setel
`"pemeriksa_gagal": true` di hasilnya, dan `terapkan.py` akan menahan
statusnya di `bukti_belum_cukup` berapa pun jumlah kutipannya.

### 4. Verifikasi, tulis, bangkitkan ulang

```
python src/baca/selesaikan.py --dir kerja/<label>            # periksa dulu
python src/baca/selesaikan.py --dir kerja/<label> --tulis    # baru tulis
```

Backup database dulu sebelum `--tulis`:
`cp data/leads.db data/leads_backup_<label>_<tanggal>.db`

`selesaikan.py` menggabungkan `hasil-*.json`, memanggil `terapkan.py`,
lalu membangkitkan ulang antrian + dasbor + CSV. Jangan menjalankan
keempatnya satu-satu lagi.

## Larangan

**Kalau `terapkan.py` menolak karena kutipan gagal verifikasi, JANGAN
mengedit `hasil.json` supaya lolos.** Kutipan yang tidak bisa ditemukan
berarti agennya mengarang atau menyalin dari bagian terlarang. Cari tahu
yang mana, lalu kosongkan komponennya — penilaian yang kutipannya tidak
bisa ditunjukkan tidak bisa dipertanggungjawabkan waktu orang sales
ditanya "dari mana Anda tahu?".

**Jangan menulis skor ke tabel `kebutuhan` dengan tangan.** Satu-satunya
jalan tulis adalah `terapkan.py`, dan itu disengaja: ia yang menegakkan
verifikasi kutipan dan penahanan status.

**Jangan menaikkan pita karena kamu tahu perusahaan itu besar.** Yang
dinilai bukti di dokumen, bukan reputasi. Perusahaan terkenal dengan
halaman terpanen yang tipis memang layak dapat skor rendah — bedakan
lewat `status_nilai`, bukan dengan mengarang.

## Setelah selesai

Laporkan per perusahaan: skor lama → skor baru, bukti n/4, status, dan
**apa yang dikoreksi pemeriksa**. Koreksi pemeriksa itu bagian paling
berguna dari seluruh alur; jangan diringkas jadi "sudah diperiksa".

Kalau ada lead yang naik ke `hubungi_sekarang`, sebutkan — itu yang
sebenarnya dicari orang sales.
