"""
rubrik.py
=========
Aturan penilaian lead yang DITULIS EKSPLISIT.

KENAPA FILE INI ADA:
Sebelumnya aturannya "80+ auto_include, 50-79 flag_review". Tapi waktu
14 keputusan lama diperiksa, TIDAK SATU PUN yang mencapai 80 — dan
keputusan auto_include/flag_review ternyata sama sekali tidak mengikuti
angka itu.

Yang SEBENARNYA menentukan keputusan adalah KUALITAS NOMOR TELEPON:
  auto_include -> semua punya nomor jalur langsung dari sumber tepercaya
  flag_review  -> semua bermasalah: call-center 1500-xxx, tidak ada nomor,
                  atau nomor dari sumber tidak resmi (job board)

Angka 76 vs 73 hanya AKIBAT, bukan sebab. Keputusan diambil dulu secara
naluriah, angkanya menyusul supaya terlihat konsisten.

File ini mengubah naluri itu jadi aturan yang bisa dijalankan kode.
"""

import re

# ===========================================================================
# BAGIAN 1: GERBANG KUALITAS KONTAK  (aturan yang dulu tersembunyi)
# ===========================================================================

# Nomor call-center / layanan pelanggan — BUKAN jalur ke pengambil keputusan.
# Pola ini ditemukan berulang di data nyata: TIKI (1500 125),
# Alfamart (1500 959), Traveloka (0804-1500-308), Blibli (0804-1-871-871),
# LG (14010), Zurich (1 500 456).
POLA_CALL_CENTER = re.compile(
    r"^\+?62?[\s\-]?0?8?0?4"      # 0804-xxx (premium/toll)
    r"|1[\s\-]?500"                # 1500-xxx
    r"|^\+?62?[\s\-]?0?800"        # 0800-xxx (bebas pulsa)
    r"|^1[34]\d{3}$",              # 14010, 13xxx (nomor pendek)
    re.IGNORECASE,
)


def klasifikasi_telepon(phone, sumber_resmi=False, jml_sumber=1,
                        ditandai_contact_center=False):
    """
    Kembalikan salah satu:
      'langsung_resmi'   - jalur langsung, sumber kuat (resmi ATAU 2+ sumber)
      'langsung_lain'    - jalur langsung, sumber tunggal & tidak resmi
      'call_center'      - nomor layanan pelanggan, bukan kantor
      'tidak_ada'        - belum ketemu

    Parameter:
      sumber_resmi            website resmi perusahaan (contact/about/IR)
      jml_sumber              berapa sumber independen yang menyebut nomor
                              SAMA. 2+ sumber yang cocok dianggap sekuat
                              sumber resmi — ini aturan yang dipakai untuk
                              J&T dan SiCepat ("multiple directory listings").
      ditandai_contact_center penanda MANUAL. Sebagian nomor contact center
                              formatnya sama persis dengan telepon kantor
                              biasa, jadi tidak bisa dideteksi otomatis.
                              Contoh: JNE +62 21 2927 8888 ada di halaman
                              resmi dan formatnya normal, tapi itu contact
                              center. Hanya manusia yang bisa tahu dari
                              konteks halamannya.
    """
    if not phone or phone.strip().upper() == "NOT_FOUND":
        return "tidak_ada"

    if ditandai_contact_center:
        return "call_center"

    digit = re.sub(r"[^\d+]", "", phone.split(";")[0])
    if POLA_CALL_CENTER.search(phone) or POLA_CALL_CENTER.search(digit):
        return "call_center"

    # Sumber kuat = dari halaman resmi, ATAU dikuatkan 2+ sumber independen
    sumber_kuat = sumber_resmi or jml_sumber >= 2
    return "langsung_resmi" if sumber_kuat else "langsung_lain"


# ===========================================================================
# BAGIAN 2: NEED SCORE  (seberapa BUTUH perusahaan terhadap Salesmart)
# ===========================================================================
MAKS_KOMPONEN = {
    "dist_model": 35,     # punya jaringan distributor/agen/reseller
    "field_sales": 30,    # ada tim sales lapangan / canvassing
    "scale": 20,          # jumlah titik operasi
    "industry_fit": 15,   # cocok dengan vertikal Salesmart
}

AMBANG_NEED_TINGGI = 75
AMBANG_NEED_SEDANG = 50


def hitung_need(komponen):
    total = 0
    for nama, maks in MAKS_KOMPONEN.items():
        nilai = int(komponen[nama])
        if nilai > maks:
            raise ValueError(f"{nama}={nilai} melebihi maksimum {maks}")
        total += nilai
    return total


# ===========================================================================
# BAGIAN 2B: PITA BUKTI  (aturan yang SEBELUMNYA masih tersembunyi)
# ===========================================================================
# KENAPA BAGIAN INI ADA:
# Sama persis dengan alasan file ini dibuat. MAKS_KOMPONEN di atas hanya
# menyebut angka maksimum tiap komponen — tapi tidak ada satu baris pun yang
# menjelaskan KENAPA Erajaya dapat dist_model=25 sementara Gojek dapat 15.
# Kedua puluh baris di companies_scored.csv diisi dengan naluri, lalu
# angkanya menyusul. Persis pola yang sudah kita bongkar sekali di skor lama.
#
# Selama aturannya belum tertulis, dua hal tidak mungkin:
#   1. Orang lain (atau LLM) tidak bisa mengisi kolom ini konsisten.
#   2. Tidak ada cara tahu apakah sebuah penilaian SALAH.
#
# Pita di bawah ini dibalik-rekayasa dari 20 keputusan yang sudah diambil,
# lalu diperluas ke bawah supaya bisa menilai perusahaan KECIL — sesuatu
# yang sampel kalibrasi sekarang tidak punya sama sekali.
#
# Tiap pita menyebut BUKTI yang harus terlihat, bukan kesan. Kolom "sumber"
# menandai di mana bukti itu biasanya ditemukan.

PITA = {
    # -------------------------------------------------------------------
    "dist_model": [
        (35, "jaringan_sendiri",
         "Punya jaringan distributor/agen/depo sendiri, ATAU memasok ritel "
         "pihak ketiga secara masif (warung, toko, apotek, modern/general "
         "trade), ATAU mengoperasikan jaringan gerai/kurir nasional sendiri.",
         "situs: halaman distribusi/jaringan; laporan tahunan"),
        (25, "jaringan_terbatas",
         "Punya jaringan titik fisik tapi lebih sempit — satu kategori "
         "produk atau segmen ritel tertentu saja.",
         "situs: daftar toko/cabang"),
        (15, "lapangan_bukan_barang",
         "Punya armada atau gerai lapangan yang dikelola, tapi tidak "
         "mendistribusikan barang bermerek sendiri.",
         "situs: halaman layanan/lokasi"),
        (0, "tanpa_distribusi_fisik",
         "Produk atau jasa digital. Tidak ada barang fisik yang berpindah "
         "lewat jaringan yang perlu dikelola.",
         "situs: halaman produk"),
    ],
    # -------------------------------------------------------------------
    "field_sales": [
        (30, "sales_kanvas",
         "Ada tim yang MENJUAL di lapangan: salesman, motoris, canvasser, "
         "medical representative, beauty advisor, area sales manager. "
         "Inilah orang-orang yang dilacak Salesmart.",
         "lowongan kerja (paling kuat); situs: halaman karier"),
        (20, "lapangan_operasional",
         "Ada tim lapangan besar tapi tugasnya operasional, bukan menjual: "
         "kurir, staf gerai, kepala cabang.",
         "lowongan kerja; situs: halaman karier"),
        (10, "lapangan_minimal",
         "Ada sebagian staf di luar kantor, tapi bukan struktur lapangan "
         "yang jelas.",
         "lowongan kerja"),
        (0, "tanpa_lapangan",
         "Seluruh operasi di kantor atau daring.",
         "lowongan kerja: hanya posisi kantor/teknologi"),
    ],
    # -------------------------------------------------------------------
    # CATATAN PENTING: pita 10, 5, dan 0 BELUM PERNAH TERPAKAI. Kedua puluh
    # perusahaan di sampel kalibrasi semuanya berskala nasional, jadi
    # komponen ini belum teruji. Ia baru akan bekerja saat menilai
    # perusahaan menengah dari BPS atau OSM.
    "scale": [
        (20, "nasional",
         "Hadir di seluruh Indonesia, atau >100 titik operasi, atau "
         "menyebut 30+ provinsi.",
         "situs: halaman jaringan; daftar cabang"),
        (15, "lintas_pulau",
         "Hadir di banyak provinsi tapi belum menyeluruh (kira-kira 10-33 "
         "provinsi), atau 20-100 titik.",
         "situs: daftar cabang; sebaran lowongan"),
        (10, "multi_kota",
         "3-9 kota, umumnya masih dalam satu atau dua provinsi.",
         "situs: daftar cabang; sebaran lowongan"),
        (5, "dua_kota",
         "Dua lokasi operasi.",
         "situs; direktori"),
        (0, "satu_lokasi",
         "Satu lokasi saja. Tim lapangannya terlalu kecil untuk butuh "
         "platform pelacakan.",
         "direktori BPS/OSM: satu alamat"),
    ],
    # -------------------------------------------------------------------
    # CATATAN: pita 0 juga BELUM PERNAH TERPAKAI, karena kedua puluh
    # perusahaan sampel semuanya menghadap konsumen.
    "industry_fit": [
        (15, "produsen_barang_konsumsi",
         "Produsen barang konsumsi bermerek: FMCG, makanan-minuman, "
         "farmasi, kosmetik. Vertikal inti Salesmart.",
         "KBLI; situs: halaman produk"),
        (10, "ritel_distribusi_logistik",
         "Peritel, distributor, atau logistik. Butuh manajemen lapangan, "
         "tapi bukan pemilik merek yang mendorong produk ke pasar.",
         "KBLI; situs"),
        (5, "platform_jasa",
         "Platform digital atau jasa. Kecocokannya lemah.",
         "situs"),
        (0, "tidak_relevan",
         "B2B berat, jasa profesional, pemerintah, pendidikan. Tidak ada "
         "produk konsumsi yang didorong lewat jaringan lapangan.",
         "KBLI; direktori"),
    ],
}


def nilai_pita(komponen: str, label: str) -> int:
    """Ubah label pita jadi angka. Salah label = error, bukan diam-diam 0."""
    for nilai, nama, _, _ in PITA[komponen]:
        if nama == label:
            return nilai
    sah = ", ".join(n for _, n, _, _ in PITA[komponen])
    raise ValueError(f"label '{label}' tidak dikenal untuk {komponen}. Pilih: {sah}")


def label_pita(komponen: str, nilai: int) -> str:
    """Kebalikannya: angka -> label. Dipakai untuk memeriksa data lama."""
    for n, nama, _, _ in PITA[komponen]:
        if n == int(nilai):
            return nama
    return None


# ===========================================================================
# BAGIAN 2C: ATURAN TAFSIR  (aturan yang SEBELUMNYA cuma ada di kepala)
# ===========================================================================
# Dua aturan di bawah ini sudah dipakai diam-diam waktu menilai, tapi tidak
# pernah ditulis. Akibatnya keduanya diperdebatkan ulang tiap kali ketemu
# kasus yang sama. Ditulis di sini supaya berhenti jadi perdebatan.


# --- Aturan 1: SATU FAKTA, SATU KOMPONEN -----------------------------------
#
# Sebuah fakta hanya boleh menaikkan SATU komponen. Kalau fakta yang sama
# dipakai di dua tempat, need score-nya kelihatan besar padahal buktinya
# cuma satu.
#
# Kasus yang memaksa aturan ini ditulis — MS Glow:
#   Program agen/reseller-nya sudah dinilai di dist_model = 35, karena pita
#   itu memang berbunyi "punya jaringan distributor/agen/reseller sendiri".
#   Muncul usulan menaikkan field_sales dari 20 ke 30 (sales_kanvas) dengan
#   alasan "seller-nya kan menjual". Tapi itu fakta yang PERSIS SAMA,
#   dihitung dua kali. Kalau diterima, MS Glow jadi 95 hanya karena satu
#   program reseller disebut dua kali.
#
#   field_sales-nya berdiri di atas bukti LAIN, dan cuma itu yang boleh
#   dihitung: sub-brand Aesthetic Clinic — gerai fisik dengan stafnya
#   sendiri. Itu lapangan_operasional = 20. Jadi 20, bukan 30.
#
# Praktisnya: sebelum memberi nilai, tanya "apakah kutipan ini sudah saya
# pakai untuk komponen lain?" Kalau ya, komponen kedua harus punya
# kutipannya sendiri atau turun pita.


def periksa_dobel_hitung(rincian: dict) -> list:
    """Cari satu fakta yang dinilai di dua komponen sekaligus.

    Membandingkan kutipan antar komponen: kalau dua komponen memakai
    kutipan yang sama — atau salah satu memuat yang lain — nilainya
    berdiri di atas fakta yang sama dan salah satu harus turun.

    INI PENYARING, BUKAN HAKIM. Ia hanya menangkap dobel hitung yang
    kutipannya kebetulan sama persis. Dobel hitung yang diparafrase
    berbeda tetap lolos, dan itu memang tidak bisa ditangkap mesin.
    """
    peringatan = []
    isi = {}
    for komp, nilai in rincian.items():
        if isinstance(nilai, dict):
            isi[komp] = (nilai.get("kutipan") or "").strip().lower()

    # Kutipan pendek diabaikan: terlalu mudah kebetulan sama.
    komp = [k for k, v in isi.items() if len(v) >= 40]
    for i, a in enumerate(komp):
        for b in komp[i + 1:]:
            ta, tb = isi[a], isi[b]
            if ta == tb or ta in tb or tb in ta:
                peringatan.append(
                    f"{a} dan {b} berdiri di atas kutipan yang sama")
    return peringatan


# --- Aturan 2: VERTIKAL YANG SENGAJA DITUTUP -------------------------------
#
# Beberapa industri punya tim penjual lapangan yang besar dan nyata, tapi
# TETAP dinilai industry_fit = 0. Ini keputusan, bukan kelalaian rubrik.
#
# Kalau tidak ditulis, tiap sesi penilaian akan mengulang perdebatan yang
# sama: "AIA punya ribuan Life Planner, masa 0?"

VERTIKAL_DITUTUP = {
    "asuransi_keuangan": (
        "Asuransi, penjaminan, sekuritas, multifinance.",
        # Kenapa ditutup:
        "Tim lapangannya nyata — AIA punya halaman Jalur Distribusi dan "
        "merekrut Life Planner, Asuransi Bintang memisahkan jalur karier "
        "Agen dari Karyawan dan punya kantor pemasaran sampai Samarinda, "
        "Makassar, dan Batam. Tapi yang mereka bawa ke lapangan adalah "
        "polis, bukan barang: tidak ada stok, tidak ada outlet yang "
        "dikunjungi, tidak ada rute ke toko. Agen asuransi mendatangi "
        "ORANG, salesman FMCG mendatangi TOKO — alur kerjanya beda, dan "
        "produk yang dibangun untuk kanvasing toko tidak otomatis cocok. "
        "Rubrik sudah menahannya lewat dist_model = 0 (komponen terbesar, "
        "35 poin), jadi asuransi tidak akan pernah menembus ambang tanpa "
        "aturan khusus. industry_fit = 0 membuat penolakan itu disengaja, "
        "bukan kebetulan.",
        # Kapan keputusan ini layak ditinjau ulang:
        "Kalau Salesmart nanti punya modul manajemen keagenan — bukan "
        "kunjungan outlet — vertikal ini dibuka lagi. Sampai saat itu, "
        "jangan dinilai ulang satu per satu.",
    ),
}


def vertikal_ditutup(catatan: str = "") -> str:
    """Nama vertikal tertutup yang cocok, atau string kosong.

    Sengaja TIDAK otomatis: penilai yang memutuskan sebuah perusahaan
    masuk vertikal tertutup, fungsi ini hanya menyediakan alasannya
    supaya kalimatnya seragam di semua catatan.
    """
    for nama, (_, alasan, _) in VERTIKAL_DITUTUP.items():
        if nama in catatan:
            return alasan
    return ""


# ===========================================================================
# BAGIAN 3: KEPUTUSAN AKHIR
# ===========================================================================
# Dua sumbu terpisah, sengaja TIDAK dijadikan satu angka:
#   sumbu 1 = seberapa butuh   (need score)
#   sumbu 2 = bisa dihubungi?  (kualitas kontak)
#
# Alasan dipisah: perusahaan dengan kebutuhan 100 tapi tanpa nomor telepon
# BUKAN "lead sedang". Dia lead bagus yang datanya belum lengkap — dan
# tindakannya beda: cari nomornya, bukan turunkan prioritasnya.

def tentukan_aksi(need, kualitas_telepon):
    """Kembalikan (status, aksi_berikutnya)."""
    butuh = (need >= AMBANG_NEED_TINGGI)
    sedang = (AMBANG_NEED_SEDANG <= need < AMBANG_NEED_TINGGI)

    if kualitas_telepon == "langsung_resmi":
        if butuh:
            return "hubungi_sekarang", "Telepon langsung. Prioritas tertinggi."
        if sedang:
            return "hubungi_nanti", "Data siap, kebutuhan sedang. Antrian kedua."
        return "arsipkan", "Data bagus tapi kemungkinan tidak butuh produk ini."

    if kualitas_telepon == "langsung_lain":
        if butuh:
            return "verifikasi_lalu_hubungi", \
                   "Cek nomor di website resmi dulu, baru telepon."
        return "arsipkan", "Kebutuhan rendah, tidak layak biaya verifikasi."

    if kualitas_telepon == "call_center":
        if butuh:
            return "cari_nomor_kantor", \
                   "Nomor yang ada hanya call-center. Cari jalur kantor/marketing."
        return "arsipkan", "Call-center + kebutuhan rendah."

    # tidak ada nomor
    if butuh:
        return "cari_nomor", \
               "Kebutuhan tinggi tapi nomor belum ada. TARGET UTAMA Places API."
    return "arsipkan", "Tidak ada nomor dan kebutuhan rendah."


# ===========================================================================
# UJI: apakah aturan ini mereproduksi keputusan lama?
# ===========================================================================
if __name__ == "__main__":
    # 14 keputusan asli.
    #   resmi   = nomor dari halaman resmi perusahaan
    #   sumber  = jumlah sumber independen yang menyebut nomor sama
    #   cc      = ditandai manual sebagai contact center
    UJI = [
        # nama,          telepon,             resmi, sumber, cc,   keputusan lama
        ("Gojek",        "+62 21 5084 9000",  True,  1, False, "auto_include"),
        ("Tokopedia",    "+62 21 5369 1015",  True,  1, False, "auto_include"),
        ("J&T Express",  "+62 21 8066 1888",  False, 3, False, "auto_include"),
        ("SiCepat",      "+62 21 5663 017",   False, 3, False, "auto_include"),
        ("Blue Bird",    "+62 21 7989 000",   True,  1, False, "auto_include"),
        ("Mayora",       "+62 21 806 377 04", True,  1, False, "auto_include"),
        ("Kalbe Farma",  "+62 21 4287 3888",  True,  3, False, "auto_include"),
        ("Sido Muncul",  "+62 24 7692 8811",  True,  2, False, "auto_include"),
        ("JNE",          "+62 21 2927 8888",  True,  1, True,  "flag_review"),
        ("Alfamart",     "1500 959",          True,  1, False, "flag_review"),
        ("Indomaret",    "NOT_FOUND",         False, 0, False, "flag_review"),
        ("Paragon",      "+62 21 584 9070",   False, 1, False, "flag_review"),
        ("TIKI",         "1500 125",          True,  1, False, "flag_review"),
        ("Wahana",       "+62 21 7341 688",   False, 1, False, "flag_review"),
    ]

    print("UJI: apakah gerbang kontak mereproduksi keputusan lama?\n")
    print(f"{'Perusahaan':<15}{'Klasifikasi':<18}{'Dulu':<14}{'Cocok?'}")
    print("-" * 58)

    cocok = tidak = 0
    for nama, tel, resmi, jml, cc, dulu in UJI:
        k = klasifikasi_telepon(tel, resmi, jml, cc)
        prediksi = "auto_include" if k == "langsung_resmi" else "flag_review"
        ok = (prediksi == dulu)
        cocok += ok
        tidak += (not ok)
        print(f"{nama:<15}{k:<18}{dulu:<14}{'ya' if ok else 'TIDAK'}")

    print(f"\nCocok: {cocok}/{len(UJI)}  ({cocok/len(UJI)*100:.0f}%)")
    if tidak == 0:
        print("Aturan tertulis sekarang mereproduksi SEMUA keputusan lama.")

    # -----------------------------------------------------------------
    # UJI PITA BUKTI terhadap penilaian manual di companies_scored.csv
    # -----------------------------------------------------------------
    import csv as _csv
    import collections as _col
    from pathlib import Path as _Path

    csv_skor = _Path(__file__).resolve().parent.parent / "data" / "companies_scored.csv"
    if not csv_skor.exists():
        raise SystemExit(0)

    baris = list(_csv.DictReader(open(csv_skor, encoding="utf-8")))
    print(f"\n{'=' * 66}")
    print("UJI PITA: apakah 20 penilaian manual jatuh di pita yang sah?")
    print("=" * 66)

    haram = 0
    terpakai = _col.defaultdict(set)
    for r in baris:
        for komp in MAKS_KOMPONEN:
            lab = label_pita(komp, r[komp])
            if lab is None:
                print(f"  DI LUAR PITA: {r['company_name']} {komp}={r[komp]}")
                haram += 1
            else:
                terpakai[komp].add(lab)

    if haram == 0:
        print(f"  Semua {len(baris) * 4} nilai jatuh di pita yang sah.")

    print("\nCakupan pita — mana yang BELUM PERNAH teruji:")
    total_kosong = 0
    for komp in MAKS_KOMPONEN:
        for nilai, nama, _, _ in PITA[komp]:
            if nama not in terpakai[komp]:
                print(f"  BELUM TERUJI  {komp:<14} {nilai:>3}  {nama}")
                total_kosong += 1
    if total_kosong == 0:
        print("  Semua pita sudah pernah terpakai.")
    else:
        print(f"\n  {total_kosong} pita belum pernah dipakai — semuanya di ujung")
        print("  bawah. Sebabnya: 20 perusahaan sampel semuanya berskala")
        print("  nasional dan menghadap konsumen. Pita bawah baru teruji")
        print("  setelah perusahaan menengah dari BPS/OSM ikut dinilai.")