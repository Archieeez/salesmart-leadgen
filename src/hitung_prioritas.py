"""
hitung_prioritas.py
===================
Hitung Need Score dan prioritas lead berdasarkan seberapa BUTUH sebuah
perusahaan terhadap Salesmart — bukan sekadar seberapa besar perusahaannya.

DASAR PEMIKIRAN:
Salesmart adalah platform untuk manajemen TIM SALES LAPANGAN dan RANTAI
DISTRIBUSI (produk: Smart Team, Distribusi, Point Reward). Jadi sinyal yang
diukur adalah hal-hal yang menandakan perusahaan punya operasi lapangan,
bukan sekadar punya "divisi marketing".

Konsekuensi penting: perusahaan digital besar (Traveloka, Tokopedia) yang
di rubric lama skornya tinggi, di sini justru rendah — karena mereka tidak
punya tim canvassing untuk dilacak GPS-nya.

PERUBAHAN STRUKTUR SKOR:
  Lama : legitimacy x 0.4 + division x 0.6
  Baru : need x 0.7 + division x 0.3, legitimacy jadi GERBANG

Alasan: legitimacy mengukur "apakah datanya bisa dipakai" — itu SYARAT,
bukan nilai. Lead dengan data belum terverifikasi bukan "agak kurang bagus",
tapi belum siap dihubungi sama sekali.

Jalankan:  python hitung_prioritas.py
"""

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"
INPUT_CSV = DATA / "companies_scored.csv"
OUTPUT_CSV = DATA / "companies_prioritas.csv"

# --- Ambang batas -----------------------------------------------------------
GERBANG_LEGITIMACY = 60   # di bawah ini: data belum layak dipakai
AMBANG_PRIORITAS_1 = 75   # target utama
AMBANG_PRIORITAS_2 = 50   # target sekunder

# --- Bobot komponen (0-100 total) -------------------------------------------
# Ini TEBAKAN berdasarkan materi pemasaran Salesmart, BUKAN data konversi
# nyata. Kalau nanti tahu klien mana yang benar-benar closing, ubah di sini.
MAKS = {
    "dist_model": 35,    # model distribusi - sinyal terkuat
    "field_sales": 30,   # keberadaan tim sales lapangan
    "scale": 20,         # skala operasi (jumlah titik)
    "industry_fit": 15,  # kecocokan dengan vertikal Salesmart
}


def hitung_need(row):
    """Jumlahkan 4 komponen jadi Need Score 0-100."""
    total = 0
    for komponen, maks in MAKS.items():
        nilai = int(row[komponen])
        if nilai > maks:
            raise ValueError(
                f"{row['company_name']}: {komponen}={nilai} melebihi maks {maks}"
            )
        total += nilai
    return total


def tentukan_status(need, legitimacy):
    """
    Legitimacy adalah GERBANG, bukan bobot. Data belum terverifikasi =
    belum siap dihubungi, berapa pun kebutuhannya.
    """
    if legitimacy < GERBANG_LEGITIMACY:
        return "perlu_verifikasi"
    if need >= AMBANG_PRIORITAS_1:
        return "prioritas_1"
    if need >= AMBANG_PRIORITAS_2:
        return "prioritas_2"
    return "prioritas_rendah"


def main():
    if not INPUT_CSV.exists():
        print(f"File tidak ditemukan: {INPUT_CSV}")
        raise SystemExit(1)

    rows = list(csv.DictReader(open(INPUT_CSV, encoding="utf-8")))

    # Deteksi baris rusak lebih awal. Penyebab tersering: ada koma di dalam
    # need_notes tanpa tanda kutip, sehingga terbaca sebagai kolom tambahan.
    for row in rows:
        if None in row:
            print(f"BARIS RUSAK: {row['company_name']}")
            print(f"  Kolom berlebih: {row[None]}")
            print("  Perbaiki: bungkus kolom need_notes dengan tanda kutip \"...\"")
            raise SystemExit(1)

    for row in rows:
        need = hitung_need(row)
        legit = int(row["legitimacy_score"])
        div = int(row["division_score"])

        row["need_score"] = need
        row["final_score"] = round(need * 0.7 + div * 0.3, 1)
        row["status"] = tentukan_status(need, legit)
        row["punya_telepon"] = "tidak" if row["phone"] == "NOT_FOUND" else "ya"

    rows.sort(key=lambda r: (-r["need_score"], -float(r["final_score"])))

    # --- Tampilkan -----------------------------------------------------------
    print(f"\n{'='*88}")
    print("PRIORITAS LEAD BERDASARKAN KEBUTUHAN TERHADAP SALESMART")
    print(f"{'='*88}")
    print(f"{'#':<3}{'Perusahaan':<34}{'Need':>5}{'Final':>7}{'Tel':>5}  {'Status':<18}")
    print("-" * 88)

    for i, row in enumerate(rows, 1):
        tel = "ya" if row["punya_telepon"] == "ya" else "--"
        print(f"{i:<3}{row['company_name'][:32]:<34}"
              f"{row['need_score']:>5}{row['final_score']:>7}{tel:>5}  {row['status']:<18}")

    # --- Ringkasan per status -------------------------------------------------
    print(f"\n{'='*88}")
    print("RINGKASAN")
    print("-" * 88)
    for status in ("prioritas_1", "prioritas_2", "prioritas_rendah", "perlu_verifikasi"):
        cocok = [r for r in rows if r["status"] == status]
        if not cocok:
            continue
        dgn_tel = sum(1 for r in cocok if r["punya_telepon"] == "ya")
        print(f"  {status:<20} {len(cocok):>3} perusahaan  "
              f"({dgn_tel} punya telepon, siap dihubungi)")

    # --- Daftar aksi -----------------------------------------------------------
    siap = [r for r in rows
            if r["status"] == "prioritas_1" and r["punya_telepon"] == "ya"]
    print(f"\n{'='*88}")
    print(f"SIAP DIHUBUNGI SEKARANG ({len(siap)} perusahaan)")
    print("-" * 88)
    for row in siap:
        print(f"  {row['company_name'][:30]:<32} {row['phone']:<22} need={row['need_score']}")

    macet = [r for r in rows
             if r["status"] == "prioritas_1" and r["punya_telepon"] == "tidak"]
    if macet:
        print(f"\nPRIORITAS TINGGI TAPI TELEPON BELUM ADA ({len(macet)}):")
        print("(ini yang paling layak dicari duluan saat Places API aktif)")
        for row in macet:
            print(f"  {row['company_name'][:30]:<32} need={row['need_score']}")

    # --- Simpan ---------------------------------------------------------------
    kolom = list(rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kolom)
        w.writeheader()
        w.writerows(rows)
    print(f"\nHasil lengkap disimpan ke: {OUTPUT_CSV.name}")


if __name__ == "__main__":
    main()
