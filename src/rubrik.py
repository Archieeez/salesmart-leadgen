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