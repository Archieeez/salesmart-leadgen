"""
query_plan.py (v2 — SUDAH DIVALIDASI)
======================================
Daftar query Places API, disusun dari profil klien ideal Salesmart.

VERSI INI SUDAH DIUJI lewat pencarian web sebelum menghabiskan kuota API.
Hasil pengujian mengubah daftarnya cukup banyak:

DIBUANG (terbukti buruk):
  "grosir sembako"        -> hasilnya toko/warung (Toko Nur Makkah, UD
                             Piramida). Skala terlalu kecil. Pola sama
                             dengan kesalahan shop=mall di OSM.
  "perusahaan manufaktur" -> hasilnya IKLAN LOWONGAN dari Jobstreet/Indeed,
                             bukan perusahaan. Ini istilah pencari kerja,
                             bukan cara perusahaan menamai diri.
  "supplier bahan makanan"-> tumpang tindih dengan toko bahan kue/katering.

TEMUAN UTAMA:
  Perusahaan Indonesia menamai diri dengan PRODUK + JENIS USAHA,
  bukan kategori abstrak.
      GAGAL  : "perusahaan manufaktur"  -> iklan lowongan
      BERHASIL: "pabrik plastik"        -> pabrik asli + nomor telepon
  Karena itu semua query manufaktur di bawah memakai pola
  "pabrik <produk spesifik>", bukan kategori umum.

CATATAN TENTANG "distributor ...":
  Terbukti campur (~40-50% layak). Muncul PT besar yang bagus
  (PT Central Pacific Prima, PT Sele Ingredients) TAPI juga banyak UD/CV
  kecil pemasok warung yang terlalu kecil untuk butuh Salesmart.
  Solusi: JANGAN buang query-nya, tapi siapkan filter ukuran saat
  memproses hasilnya (lihat catatan FILTER di bawah).
"""

# ---------------------------------------------------------------------------
# TIER 1 — Distribusi (dist_model = 35, sinyal terkuat)
# Sudah dipangkas: hanya sektor yang jaringan distributornya jelas berskala
# perusahaan, bukan toko.
# ---------------------------------------------------------------------------
TIER_1_DISTRIBUSI = [
    "distributor makanan dan minuman",   # diuji: ~40-50% layak, perlu filter
    "distributor kosmetik",
    "distributor farmasi",
    "distributor bahan bangunan",
    "distributor alat kesehatan",
    "distributor sparepart otomotif",
    "distributor bahan kimia industri",  # baru: muncul PT asli saat diuji
    "distributor pupuk",
]

# ---------------------------------------------------------------------------
# TIER 2 — Manufaktur (field_sales 30 + industry_fit 15)
# SEMUA memakai pola "pabrik <produk>" karena "perusahaan manufaktur"
# terbukti hanya menghasilkan iklan lowongan.
# ---------------------------------------------------------------------------
TIER_2_MANUFAKTUR = [
    "pabrik makanan ringan",
    "pabrik minuman kemasan",
    "pabrik kosmetik",
    "pabrik obat farmasi",
    "pabrik plastik kemasan",   # diuji: muncul pabrik asli + nomor telepon
    "pabrik tekstil",
    "pabrik cat",
    "pabrik keramik sanitasi",
]

# ---------------------------------------------------------------------------
# TIER 3 — Logistik dengan jaringan agen (terbukti need score 85 di kalibrasi)
# ---------------------------------------------------------------------------
TIER_3_LOGISTIK = [
    "ekspedisi pengiriman barang",
    "jasa cargo",
    "perusahaan logistik",
    "gudang distribusi",   # baru: menyasar operasi distribusi, bukan agen kecil
]

# ---------------------------------------------------------------------------
# TIER 4 — Eksperimen, hasil belum diketahui. Jalankan PALING AKHIR.
# ---------------------------------------------------------------------------
TIER_4_EKSPERIMEN = [
    "PT distributor resmi",
    "kantor pemasaran produk",
]

# ---------------------------------------------------------------------------
# KOTA — urut berdasarkan kepadatan industri
# Tangerang & Bekasi didahulukan sebelum Surabaya/Bandung karena kawasan
# industrinya jauh lebih padat (terkonfirmasi saat pengujian: Jatake,
# Cikupa, Jatiuwung penuh pabrik).
# ---------------------------------------------------------------------------
KOTA = [
    "Jakarta",
    "Tangerang",
    "Bekasi",
    "Surabaya",
    "Bandung",
    "Semarang",
    "Medan",
    "Makassar",
]

# ---------------------------------------------------------------------------
# FILTER — terapkan ke HASIL query, bukan ke query-nya
# ---------------------------------------------------------------------------
# Nama yang menandakan skala terlalu kecil (toko/warung, bukan perusahaan
# dengan tim sales lapangan). Ditemukan saat pengujian "grosir sembako"
# dan "distributor makanan".
POLA_TERLALU_KECIL = (
    r"^(toko|warung|kios|ud\.?\s|cv\.?\s)"
    r"|\b(eceran|retail kecil|rumahan|online shop|olshop)\b"
)

# Nama yang menandakan hasil dari situs lowongan kerja, bukan perusahaan.
POLA_JEBAKAN_LOKER = r"\b(loker|lowongan|karir|career|recruitment|jobstreet|indeed)\b"


def semua_query(tier_aktif=(1, 2, 3)):
    """Hasilkan daftar (tier, query, kota) siap pakai."""
    tiers = {
        1: TIER_1_DISTRIBUSI,
        2: TIER_2_MANUFAKTUR,
        3: TIER_3_LOGISTIK,
        4: TIER_4_EKSPERIMEN,
    }
    hasil = []
    for t in tier_aktif:
        for q in tiers[t]:
            for kota in KOTA:
                hasil.append({"tier": t, "query": f"{q} {kota}", "kota": kota})
    return hasil


if __name__ == "__main__":
    nama = {1: "Distribusi", 2: "Manufaktur", 3: "Logistik", 4: "Eksperimen"}
    for tier in (1, 2, 3, 4):
        q = semua_query((tier,))
        print(f"Tier {tier} ({nama[tier]:<11}): {len(q):>3} query "
              f"({len(q)//len(KOTA)} kata kunci x {len(KOTA)} kota)")

    inti = len(semua_query((1, 2, 3)))
    print(f"\nTotal tier 1-3        : {inti} query")
    print(f"Total termasuk tier 4 : {len(semua_query((1,2,3,4)))} query")
    print(f"\nSEBELUM validasi      : 176 query (tier 1-3)")
    print(f"SESUDAH validasi      : {inti} query")
    print(f"Dihemat               : {176-inti} query yang terbukti buruk,")
    print("                        dibuang SEBELUM menghabiskan kuota API.")
    print("\nURUTAN JALANKAN: Tier 1 dulu SAJA. Ukur hasilnya dengan cek_db.py.")
    print("Baru lanjut Tier 2 kalau hit rate profil ideal jauh di atas")
    print("baseline OSM (3.2%). Kalau tidak, perbaiki query dulu.")