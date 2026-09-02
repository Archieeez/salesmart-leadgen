"""
saring_bukti.py
===============
Saring halaman bukti dengan aturan pola, untuk memilih siapa yang layak
dibaca manusia.

KENAPA MODUL INI ADA:
    Menilai 170 situs dengan LLM keluar biaya. Membaca semuanya sendiri
    butuh 700 ribu karakter. Modul ini mempersempit: aturan pola menyaring
    ratusan jadi puluhan kandidat, lalu manusia (atau LLM) hanya membaca
    yang lolos saringan.

    Pembagian tugasnya sengaja timpang:
      aturan pola  -> kuat MENEMUKAN, lemah MEMUTUSKAN
      manusia/LLM  -> lemah menemukan (mahal), kuat memutuskan
    Dipasangkan, keduanya menutupi kelemahan masing-masing.

KENAPA CARA INI SEKARANG LAYAK DICOBA, PADAHAL DULU GAGAL:
    Percobaan pertama cuma menemukan sinyal di 10 dari 27 perusahaan.
    Tapi yang salah waktu itu BUKAN aturannya — melainkan halaman yang
    dibaca. Yang tersedia baru halaman "Hubungi Kami", yang memang tidak
    pernah membahas jaringan distribusi.

    Sekarang panen_bukti.py sudah mengambil halaman Tentang, Bisnis,
    Distribusi, dan Karier. Di sana buktinya sering sangat harfiah:
    "jaringan distribusi berskala nasional", "Peta Distribusi Nasional",
    "Kantor Penjualan Cakung".

INI PENYARING, BUKAN PENILAI:
    Aturan pola pasti melewatkan kalimat yang tidak memakai kata kunci.
    "Melayani lebih dari 500 outlet di 34 provinsi" adalah bukti kuat
    tanpa satu pun kata "distribusi". Karena itu hasil modul ini TIDAK
    ditulis ke tabel `kebutuhan` — ia hanya menyusun antrian baca.

    Konsekuensinya polanya sengaja dibuat longgar: lebih baik salah
    memasukkan kandidat (nanti gugur waktu dibaca) daripada melewatkan
    lead bagus yang tidak akan pernah dilihat lagi.

Pakai:
    python saring_bukti.py --uji            # adu ke 17 nilai bacaan manusia
    python saring_bukti.py                  # saring semuanya, tampilkan antrian
    python saring_bukti.py --keluar antrian.csv
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

import gazetteer
import rubrik

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data"

# --------------------------------------------------------------------------
# Pola per pita
# --------------------------------------------------------------------------
# Tiap entri: (label pita, regex). Urutan penting — yang pertama cocok
# dipakai, jadi pita tertinggi harus di atas.
#
# Semua pola diambil dari kalimat yang BENAR-BENAR muncul waktu 17 halaman
# GAPMMI dibaca manual, bukan dikarang.
#
# LAPIS INGGRIS (ditambahkan 2 Sep 2026)
# -------------------------------------
# Aturan di atas hampir seluruhnya berbahasa Indonesia, dengan beberapa
# kata Inggris yang kebetulan ikut ("distributor", "fleet", "merchandiser").
# Itu bukan pilihan sadar — cuma akibat dari sumbernya: 17 halaman GAPMMI
# yang memang berbahasa Indonesia.
#
# Waktu 108 situs terpanen dihitung, 41 di antaranya DOMINAN INGGRIS.
# Termasuk Indofood, Mayora, Frisian Flag, Musim Mas, Mondelez — persis
# profil yang dicari, karena perusahaan yang memegang principal asing
# memang menulis situsnya dalam bahasa Inggris.
#
# PT United Dico Citas adalah buktinya: distributor farmasi sungguhan
# dengan enam kantor cabang, dibaca manusia 80, tapi hanya dapat skor pola
# 25 — karena kalimatnya berbunyi "distribute for our principals ... to
# local vendors, convenience stores, pharmacies" dan "an armada of UDC
# truck and motorcycle drivers", yang tidak satu pun punya padanan aturan.
#
# Tiap tambahan di bawah ini adalah padanan Inggris dari pita yang SUDAH
# ada — bukan pita baru dan bukan pelonggaran ambang.

POLA = {
    "dist_model": [
        ("jaringan_sendiri", re.compile(
            r"(jaringan\s+distribusi|peta\s+distribusi|distribusi\s+nasional"
            r"|distribusi\s+ke\s+seluruh|jaringan\s+pemasaran"
            r"|\bdepo\b|\bdepot\b|keagenan|agen\s+resmi"
            r"|modern\s+trade|general\s+trade"
            r"|(?:consumer\s+goods?|produk)\s+distributor"
            r"|distributor\s+(?:resmi\s+)?(?:tunggal|utama|nasional)"
            r"|anak\s+(?:usaha|perusahaan)[^.]{0,60}distribu"
            r"|distribution\s+(?:network|business|group)"
            r"|melayani[^.]{0,40}(?:outlet|toko|warung|gerai|apotek)"
            r"|food\s*service|\bhoreka\b"
            r"|(?:hotel|restoran|restaurant)[^.]{0,30}(?:katering|catering)"
            r"|produk\s+retail"
            # -- lapis Inggris --
            r"|distribution\s+(?:channel|coverage|infrastructure|service"
            r"|centers?|centres?|points?|arm)"
            r"|nationwide\s+distribution|integrated\s+distribution"
            r"|our\s+principals?\b|the\s+principals?\s+we"
            r"|(?:sole|exclusive|appointed|authoriz|authoris)\w*\s+distributor"
            r"|distribut\w+[^.]{0,60}(?:convenience\s+stores?|traditional\s+trade"
            r"|retail\s+outlets?|pharmac(?:y|ies)|kiosks?|wholesalers?)"
            r"|(?:convenience\s+stores?|traditional\s+trade)[^.]{0,60}distribut"
            r"|point\s+of\s+sale\s+network)", re.I)),
        ("jaringan_terbatas", re.compile(
            r"(\bdistributor\b|\bdealer\b|authorized\s+dealer|\breseller\b"
            r"|mitra\s+penjualan|jaringan\s+mitra"
            # -- lapis Inggris --
            r"|dealer\s+network|agent\s+network|channel\s+partners?"
            r"|sales\s+partners?|distribution\s+partners?)", re.I)),
        ("lapangan_bukan_barang", re.compile(
            r"(\barmada\b|\bfleet\b|gerai\s+kami|outlet\s+kami"
            r"|\d+\s*(?:outlet|gerai|cabang)\b|cabang\s+kami"
            # -- lapis Inggris --
            r"|our\s+(?:outlets?|stores?|branches|vehicles)"
            r"|\d+\s*(?:branches|stores|outlets)\b)", re.I)),
    ],
    "field_sales": [
        ("sales_kanvas", re.compile(
            r"(sales\s+representative|medical\s+representative|\bmedrep\b"
            r"|area\s+sales|sales\s+area|\bsalesman\b|\bmotoris\b"
            r"|canvass?er|kanvas(?:ing)?|sales\s+promotion|\bSPG\b"
            r"|beauty\s+advisor|merchandiser|sales\s+force|tenaga\s+penjual"
            r"|sales\s+executive|account\s+executive"
            # -- lapis Inggris --
            r"|field\s+sales|sales\s+officers?|territory\s+(?:manager|sales)"
            r"|sales\s+supervisors?|\bdetailers?\b)", re.I)),
        ("lapangan_operasional", re.compile(
            r"(kantor\s+penjualan|kepala\s+cabang|branch\s+manager"
            r"|\bkurir\b|\bcourier\b|teknisi\s+lapangan|field\s+(?:engineer|technician)"
            r"|petugas\s+lapangan|tim\s+lapangan|driver\s+(?:mitra|kami)"
            # -- lapis Inggris --
            r"|(?:truck|motorcycle|van|delivery|our)\s+(?:and\s+\w+\s+)?drivers?"
            r"|delivery\s+(?:team|crew|personnel|staff)"
            r"|field\s+(?:staff|team|force|personnel)"
            r"|branch\s+offices?|sales\s+offices?)", re.I)),
        ("lapangan_minimal", re.compile(
            r"(divisi\s+penjualan|departemen\s+penjualan|tim\s+sales"
            r"|sales\s+(?:&|dan)\s+marketing"
            # -- lapis Inggris --
            r"|sales\s+(?:&|and)\s+marketing\s+(?:team|division|department)"
            r"|sales\s+department)", re.I)),
    ],
    "scale": [
        ("nasional", re.compile(
            r"(seluruh\s+indonesia|ke\s+seluruh\s+pelosok|nationwide"
            r"|3[0-9]\s+provinsi|seluruh\s+provinsi"
            r"|\b[1-9]\d{2,}\s*(?:outlet|gerai|cabang|titik|kota)\b"
            r"|skala\s+nasional|berskala\s+nasional"
            # -- lapis Inggris --
            r"|(?:throughout|across|all\s+over|all\s+around)\s+"
            r"(?:indonesia|the\s+country|the\s+archipelago)"
            r"|3[0-9]\s+provinces|all\s+provinces"
            r"|\b[1-9]\d{2,}\s*(?:outlets|stores|branches|points|cities)\b)",
            re.I)),
        ("lintas_pulau", re.compile(
            r"(\b[1-9]\d\s*(?:outlet|gerai|cabang|titik|kota)\b"
            r"|\b(?:1[0-9]|2[0-9])\s+provinsi\b"
            r"|sumatera[^.]{0,60}(?:jawa|kalimantan|sulawesi)"
            r"|jawa[^.]{0,60}(?:sumatera|kalimantan|sulawesi|papua)"
            # -- lapis Inggris --
            r"|\b[1-9]\d\s*(?:outlets|stores|branches|points|cities"
            r"|distribution\s+centers?|warehouses?)\b"
            r"|\b(?:1[0-9]|2[0-9])\s+provinces\b)", re.I)),
        ("multi_kota", re.compile(
            r"(\b[3-9]\s*(?:cabang|kantor\s+cabang|kota)\b"
            r"|beberapa\s+kota|beberapa\s+cabang"
            # -- lapis Inggris --
            r"|\b[3-9]\s*(?:branches|branch\s+offices|cities)\b"
            r"|several\s+(?:cities|branches))", re.I)),
    ],
    "industry_fit": [
        ("produsen_barang_konsumsi", re.compile(
            r"(\bFMCG\b|barang\s+konsumsi|consumer\s+goods"
            r"|makanan\s+dan\s+minuman|food\s+(?:and|&)\s+beverage"
            r"|\bfarmasi\b|pharmaceutical|\bkosmetik\b|cosmetic"
            r"|produsen[^.]{0,40}(?:makanan|minuman|obat|kosmetik)"
            r"|memproduksi[^.]{0,40}(?:makanan|minuman|obat|kosmetik|snack)"
            r"|manufactur[^.]{0,30}(?:food|beverage|consumer)"
            # -- lapis Inggris --
            r"|\bdairy\b|confectionery|personal\s+care\s+products?"
            r"|household\s+products?|packaged\s+(?:food|goods)"
            r"|nutrition\s+(?:company|products?)|\bbeverages\b)", re.I)),
        ("ritel_distribusi_logistik", re.compile(
            r"(\britel\b|\bretail\b|\bekspedisi\b|\blogistik\b|logistics"
            r"|pengiriman\s+barang|jasa\s+kurir|supply\s+chain"
            r"|rantai\s+pasok|pergudangan|warehouse"
            # -- lapis Inggris --
            r"|freight\s+forward|courier\s+service|\b3PL\b"
            r"|distribution\s+company|wholesale)", re.I)),
        ("platform_jasa", re.compile(
            r"(platform\s+digital|aplikasi\s+kami|marketplace"
            r"|software|perangkat\s+lunak|\bSaaS\b|layanan\s+digital)", re.I)),
    ],
}

# Kategori OSM yang hampir pasti di luar sasaran. Dipakai HANYA kalau teks
# tidak memberi sinyal apa pun — bukan untuk menimpa bukti.
KATEGORI_TIDAK_RELEVAN = {
    "insurance", "financial", "research", "consulting",
    "advertising_agency", "government", "lawyer", "educational_institution",
}
KATEGORI_PLATFORM = {"it", "telecommunication"}


def kalimat_sekitar(teks: str, m: re.Match, lebar: int = 130) -> str:
    """Ambil potongan kalimat di sekitar kecocokan, sebagai kutipan."""
    a = max(0, m.start() - lebar // 2)
    b = min(len(teks), m.end() + lebar)
    potong = teks[a:b].strip()
    if a > 0:
        potong = "..." + potong
    if b < len(teks):
        potong = potong + "..."
    return re.sub(r"\s+", " ", potong)


def saring(teks: str, kategori: str = "", halaman: list[str] | None = None) -> dict:
    """Return {komponen: {'label','nilai','kutipan','pola'}}.

    `halaman` (opsional): teks per halaman terpisah. Dipakai gazetteer
    untuk membuang halaman formulir alamat sebelum menghitung sebaran —
    lihat gazetteer.formulir_alamat(). Pola frasa tetap membaca `teks`
    gabungan.
    """
    hasil = {}
    for komponen, aturan in POLA.items():
        pilih = None
        for label, pola in aturan:
            m = pola.search(teks)
            if m:
                pilih = {"label": label,
                         "nilai": rubrik.nilai_pita(komponen, label),
                         "kutipan": kalimat_sekitar(teks, m),
                         "pola": m.group()[:40]}
                break
        if pilih is None:
            # Pita terendah — tidak ada bukti, bukan bukti ketiadaan.
            terendah = POLA and rubrik.PITA[komponen][-1]
            pilih = {"label": terendah[1], "nilai": terendah[0],
                     "kutipan": "", "pola": ""}
        hasil[komponen] = pilih

    # Sebaran nama tempat, untuk halaman yang MENDAFTAR lokasinya tanpa
    # pernah menyebut jumlahnya. Lihat gazetteer.py.
    #
    # HANYA MENAIKKAN, tidak pernah menurunkan. Kalau pola frasa sudah
    # menemukan pita yang lebih tinggi, itu yang dipakai — daftar nama
    # tempat bukti yang lebih lemah daripada kalimat yang menyatakannya.
    #
    # Ini tidak melanggar "satu fakta satu komponen": sebaran hanya
    # menyentuh `scale`, tidak pernah dist_model atau field_sales.
    sb = gazetteer.sebaran(halaman if halaman is not None else teks)
    pita = gazetteer.pita_scale(sb)
    if pita and pita[0] > hasil["scale"]["nilai"]:
        nilai, label, alasan = pita
        hasil["scale"] = {"label": label, "nilai": nilai,
                          "kutipan": gazetteer.ringkas(sb),
                          "pola": "sebaran:" + alasan}

    # Kategori OSM hanya dipakai kalau teks bungkam soal industri.
    if kategori and not hasil["industry_fit"]["kutipan"]:
        if kategori in KATEGORI_TIDAK_RELEVAN:
            hasil["industry_fit"] = {"label": "tidak_relevan", "nilai": 0,
                                     "kutipan": f"[kategori OSM: {kategori}]",
                                     "pola": "kategori"}
        elif kategori in KATEGORI_PLATFORM:
            hasil["industry_fit"] = {"label": "platform_jasa", "nilai": 5,
                                     "kutipan": f"[kategori OSM: {kategori}]",
                                     "pola": "kategori"}
    return hasil


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def muat_teks(db_bukti: Path) -> dict:
    con = sqlite3.connect(db_bukti)
    con.row_factory = sqlite3.Row
    per = {}
    for r in con.execute("SELECT nama_normal, nama, jenis, teks FROM halaman_bukti"):
        p = per.setdefault(r["nama_normal"], {"nama": r["nama"], "teks": [],
                                              "halaman": [], "hal": 0})
        p["halaman"].append(r["teks"] or "")
        p["hal"] += 1
    con.close()
    for p in per.values():
        # `teks` gabungan untuk pola frasa; `halaman` terpisah untuk
        # gazetteer, yang perlu membuang halaman formulir alamat utuh.
        p["teks"] = " ".join(p["halaman"])
    return per


def muat_kategori() -> dict:
    """nama -> kategori OSM, dari seed CSV kalau ada."""
    f = DATA / "seed_osm_website.csv"
    if not f.exists():
        return {}
    return {r["nama"].strip(): r.get("kategori", "")
            for r in csv.DictReader(open(f, encoding="utf-8"))}


# --------------------------------------------------------------------------
# Uji: adu ke nilai bacaan manusia
# --------------------------------------------------------------------------

def uji(per: dict):
    con = sqlite3.connect(DATA / "leads.db")
    emas = {}
    for nama, rin, need, st in con.execute(
            "SELECT nama, rincian, need_score, status_nilai FROM kebutuhan"):
        emas[nama] = {"rincian": json.loads(rin), "need": need, "status": st}
    con.close()
    if not emas:
        print("Tabel kebutuhan kosong — tidak ada acuan untuk diadu.")
        return

    print("UJI: apakah aturan pola sepakat dengan bacaan manusia?\n")
    print(f"{'perusahaan':<34}{'komponen sepakat':>18}{'need pola':>11}{'need baca':>11}")
    print("-" * 76)

    total_komp = sepakat_komp = 0
    tegak_benar = tegak_total = 0
    baris = []

    for nama, g in sorted(emas.items()):
        cocok_nama = next((k for k, v in per.items() if v["nama"] == nama), None)
        if not cocok_nama:
            continue
        h = saring(per[cocok_nama]["teks"], halaman=per[cocok_nama]["halaman"])
        n_sepakat = 0
        for komponen in rubrik.MAKS_KOMPONEN:
            total_komp += 1
            if h[komponen]["label"] == g["rincian"][komponen]["label"]:
                n_sepakat += 1
                sepakat_komp += 1
        need_pola = sum(h[k]["nilai"] for k in rubrik.MAKS_KOMPONEN)
        baris.append((nama, n_sepakat, need_pola, g["need"], g["status"], h, g))
        # Hanya lead tegak yang memang BAGUS (need >= 50) yang wajib lolos.
        # Lead tegak bernilai rendah memang seharusnya tersaring keluar.
        if g["status"] == "nilai_tegak" and g["need"] >= 50:
            tegak_total += 1
            if need_pola >= 50:
                tegak_benar += 1

    for nama, n, np_, ng, st, _, _ in sorted(baris, key=lambda x: -x[3]):
        tanda = " *" if st == "nilai_tegak" else "  "
        print(f"{nama[:32]:<34}{n:>13}/4{np_:>11}{ng:>11}{tanda}")

    print("\n  * = nilai bacaan manusia sudah tegak (bukti >= 3/4)")
    print(f"\n  komponen sepakat        {sepakat_komp}/{total_komp} "
          f"({sepakat_komp / total_komp * 100:.0f}%)")
    print(f"  lead tegak & BAGUS terjaring  {tegak_benar}/{tegak_total}"
          "   <- ini yang paling penting")
    print("\n  Yang dinilai di sini BUKAN ketepatan nilainya, tapi apakah")
    print("  penyaring ini melewatkan lead bagus. Lead bagus yang lolos")
    print("  saringan masih bisa diperbaiki nilainya saat dibaca; lead bagus")
    print("  yang tersaring keluar tidak akan pernah dilihat lagi.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    # Konsol Windows default-nya cp1252 dan akan meledak begitu ketemu emoji
    # atau aksara non-Latin yang ikut terpanen dari situs orang. Halaman web
    # memang penuh karakter begitu, jadi ini bukan kasus langka.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--db-bukti", default=str(DATA / "bukti.db"))
    ap.add_argument("--uji", action="store_true",
                    help="adu ke nilai bacaan manusia di tabel kebutuhan")
    ap.add_argument("--ambang", type=int, default=50,
                    help="skor pola minimum untuk masuk antrian baca")
    ap.add_argument("--keluar", default="",
                    help="tulis antrian ke CSV")
    args = ap.parse_args()

    per = muat_teks(Path(args.db_bukti))
    if not per:
        print("Tabel halaman_bukti kosong. Jalankan panen_bukti.py dulu.")
        raise SystemExit(1)

    if args.uji:
        uji(per)
        return

    kategori = muat_kategori()

    # Yang SUDAH dinilai tegak tidak perlu dibaca ulang — antrian ini
    # antrian BACA, bukan papan skor. Yang statusnya bukti_belum_cukup
    # tetap masuk (bertanda ~), karena sinyal baru justru alasan untuk
    # membacanya lagi.
    con = sqlite3.connect(DATA / "leads.db")
    status_nilai = dict(con.execute("SELECT nama, status_nilai FROM kebutuhan"))
    need_manusia = dict(con.execute("SELECT nama, need_score FROM kebutuhan"))
    con.close()
    # 20 perusahaan sampel pra-pipeline (companies_prioritas.csv) juga
    # sudah dinilai manusia lengkap dengan catatan — Blue Bird dan MS Glow
    # ada di sana, bukan di tabel kebutuhan.
    f_prio = DATA / "companies_prioritas.csv"
    if f_prio.exists():
        for r in csv.DictReader(open(f_prio, encoding="utf-8")):
            status_nilai.setdefault(r["company_name"].strip(), "nilai_tegak")

    antrian = []
    for nn, p in per.items():
        h = saring(p["teks"], kategori.get(p["nama"], ""), halaman=p["halaman"])
        skor = sum(h[k]["nilai"] for k in rubrik.MAKS_KOMPONEN)
        bukti = sum(1 for k in h if h[k]["kutipan"])
        antrian.append((skor, bukti, p["nama"], p["hal"], h))

    antrian.sort(reverse=True, key=lambda x: (x[0], x[1]))
    tegak = [a for a in antrian if status_nilai.get(a[2]) == "nilai_tegak"]
    belum = [a for a in antrian if status_nilai.get(a[2]) != "nilai_tegak"]
    lolos = [a for a in belum if a[0] >= args.ambang]

    # Sebaran menonjol di bawah ambang: perusahaan yang MENDAFTAR
    # lokasinya secara masif (>= lintas_pulau, dengan kata jaringan di
    # dekatnya) tapi komponen lain bungkam. Daftar lokasi sepanjang itu
    # hampir selalu berarti ada halaman jaringan yang belum terbaca pola.
    menonjol = [a for a in belum
                if a[0] < args.ambang
                and a[4]["scale"]["pola"].startswith("sebaran:")
                and a[4]["scale"]["nilai"] >= 15]

    print(f"{'perusahaan':<40}{'hal':>4}{'skor':>6}{'bukti':>7}  bukti terkuat")
    print("-" * 112)
    for skor, bukti, nama, hal, h in lolos:
        kut = ""
        for k in ["dist_model", "field_sales", "scale", "industry_fit"]:
            if h[k]["kutipan"] and not h[k]["kutipan"].startswith("["):
                kut = h[k]["kutipan"][:56]
                break
        if status_nilai.get(nama) == "bukti_belum_cukup":
            # need bacaan manusia yang lama ikut dicetak, supaya baris
            # seperti toko balon (pola 95, manusia 0) langsung ketahuan.
            tanda = f"~{need_manusia.get(nama, ''):>3}"
        else:
            tanda = "    "
        print(f"{tanda}{nama[:37]:<38}{hal:>4}{skor:>6}{bukti:>5}/4  {kut}")

    if menonjol:
        print(f"\n  SEBARAN MENONJOL di bawah ambang (daftar lokasi masif, "
              f"komponen lain bungkam):")
        for skor, bukti, nama, hal, h in menonjol:
            print(f"   {nama[:38]:<39}{skor:>5}  {h['scale']['kutipan'][:60]}")

    print(f"\n  disaring       {len(antrian)} perusahaan")
    print(f"  sudah tegak    {len(tegak)}  (tidak ditampilkan — sudah dibaca manusia)")
    print(f"  lolos          {len(lolos)}  (skor pola >= {args.ambang}; "
          f"~ = pernah dibaca, bukti belum cukup)")
    print(f"  tersaring      {len(belum) - len(lolos)}")

    if args.keluar:
        with open(args.keluar, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["nama", "halaman", "skor_pola", "komponen_berbukti",
                        "dist_model", "field_sales", "scale", "industry_fit",
                        "kutipan_dist", "kutipan_field"])
            for skor, bukti, nama, hal, h in lolos:
                w.writerow([nama, hal, skor, bukti,
                            h["dist_model"]["nilai"], h["field_sales"]["nilai"],
                            h["scale"]["nilai"], h["industry_fit"]["nilai"],
                            h["dist_model"]["kutipan"], h["field_sales"]["kutipan"]])
        print(f"  antrian ditulis ke {args.keluar}")


if __name__ == "__main__":
    sys.exit(main())
