"""
discover_osm.py (v3)
====================
Panen lead perusahaan dari OpenStreetMap via Overpass API.

PERUBAHAN DARI v2 (berdasarkan hasil evaluasi data nyata):
1. shop=mall DIBUANG — mall itu properti/gedung, bukan perusahaan dengan
   divisi marketing. Di v2 dia menyumbang 209 entri noise (32% database).
2. office=marketing DIBUANG — menghasilkan 0 entri, tag ini tidak dipakai
   di OSM Indonesia.
3. Ditambah tag office spesifik (it, engineering, logistics, dll). Alasan:
   di v2, office=consulting punya cakupan telepon 100% sedangkan
   office=company cuma 12%. Tag spesifik = data lebih bersih.
4. Multi-kota, bukan Jakarta saja.
5. Filter nama untuk membuang service center / call center konsumen.
6. BISA DILANJUT (resumable) — kalau script mati di tengah jalan,
   jalankan lagi dan dia lewati kombinasi kota+kategori yang sudah selesai.

CATATAN PENTING TENTANG SIFAT SUMBER INI:
OSM adalah PANEN SEKALI JALAN, bukan pipeline harian. Setelah semua kota
di bawah tersapu, menjalankan ulang script ini akan menghasilkan ~0 lead
baru, karena data OSM bertambah sangat lambat (kontribusi sukarelawan).
Jangan berharap ini memenuhi target "50 lead/hari" — gunakan hasilnya
sebagai dataset kalibrasi Phase 0.
"""

import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Script ada di src/, database ada di data/ — naik satu level lalu masuk data.
# Tetap dikunci ke lokasi file .py, BUKAN ke folder kerja terminal.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "User-Agent": "lead-agent-personal-project/0.3 (belajar AI engineering, non-komersial)"
}

# ---------------------------------------------------------------------------
# AREA PENCARIAN
# ---------------------------------------------------------------------------
# Bounding box: (south, west, north, east).
# CATATAN: kotak-kotak ini PERKIRAAN kasar, bukan batas administratif resmi.
# Kalau hasil suatu kota terasa aneh (kebanyakan/kesedikitan), cek kotaknya
# di https://boundingbox.klokantech.com/ lalu ganti angkanya di sini.
AREAS = {
    "Jakarta":    (-6.370, 106.689, -6.089, 106.971),
    "Tangerang":  (-6.320, 106.550, -6.150, 106.720),
    "Bekasi":     (-6.330, 106.950, -6.170, 107.060),
    "Depok":      (-6.460, 106.750, -6.350, 106.860),
    "Bandung":    (-6.980, 107.550, -6.850, 107.720),
    "Surabaya":   (-7.350, 112.600, -7.180, 112.850),
    "Semarang":   (-7.060, 110.340, -6.930, 110.500),
    "Medan":      ( 3.500,  98.600,  3.690,  98.750),
    "Makassar":   (-5.210, 119.370, -5.080, 119.510),
    "Denpasar":   (-8.730, 115.170, -8.590, 115.290),

    # --- KABUPATEN INDUSTRI, ditambah 3 Sep 2026 -------------------------
    # Sepuluh kota di atas semuanya PUSAT KANTOR. Pabriknya tidak di sana.
    # Bukti yang memaksa penambahan ini: 991 baris dari sepuluh kota itu
    # menghasilkan TIGA lead bernilai >= 75. Sekitar 30 seed manual dari
    # asosiasi menghasilkan SEMBILAN. Yang salah bukan rubriknya, melainkan
    # tempat memancingnya.
    #
    # Hitungan pra-panen (Overpass `out count`, hanya yang ber-nama):
    #   Karawang  landuse=industrial 163, man_made=works  8
    #   Cikarang  landuse=industrial  56, man_made=works 24
    #   Sidoarjo  landuse=industrial  38, man_made=works 14
    "Karawang":   (-6.450, 107.200, -6.200, 107.450),
    "Cikarang":   (-6.400, 107.050, -6.200, 107.250),
    "Sidoarjo":   (-7.550, 112.600, -7.350, 112.800),
    "Gresik":     (-7.250, 112.550, -7.100, 112.700),
    "Purwakarta": (-6.620, 107.400, -6.450, 107.560),
    "Serang":     (-6.200, 106.030, -6.000, 106.230),
    "Kudus":      (-6.860, 110.780, -6.740, 110.900),
    "Mojokerto":  (-7.550, 112.400, -7.400, 112.560),
}

# ---------------------------------------------------------------------------
# KATEGORI
# ---------------------------------------------------------------------------
# Urutan sengaja: tag spesifik dulu (lebih bersih), generik terakhir.
CATEGORIES = [
    ("office", "it"),                  # perusahaan IT/software
    ("office", "consulting"),          # 100% punya telepon di uji coba v2
    ("office", "advertising_agency"),
    ("office", "engineering"),
    ("office", "logistics"),
    ("office", "insurance"),
    ("office", "telecommunication"),
    ("office", "financial"),
    ("office", "research"),
    ("office", "company"),             # paling generik, paling banyak noise

    # --- TAG INDUSTRI, ditambah 3 Sep 2026 -------------------------------
    # Sepuluh kategori di atas semuanya KANTOR JASA: IT, konsultan, biro
    # iklan, asuransi, keuangan, telekomunikasi, riset. Tidak satu pun
    # manufaktur, pergudangan, atau distribusi -- padahal itulah vertikal
    # Salesmart. `office=insurance` bahkan vertikal yang sudah ditutup
    # sendiri lewat VERTIKAL_DITUTUP.
    #
    # Sampel pra-panen membuktikan isinya nyata: Unilever, HM Sampoerna,
    # Unicharm, Hankook Tire, Borwita Citra Prima, Aloha Food Industry.
    #
    # Diketahui dan sudah diperhitungkan sebelum dipanen:
    #   - `landuse=industrial` kadang bernama KAWASAN industrinya, bukan
    #     perusahaannya. Dibuang POLA_BUANG.
    #   - `man_made=works` sering bernama "Pabrik" saja. Dibuang juga.
    #   - satu perusahaan bisa terpetakan 2-3 kali; bersihkan_db.py yang
    #     menangani dedup entitas.
    #   - `shop=wholesale` diuji dan hasilnya NOL di keempat wilayah uji,
    #     jadi sengaja TIDAK dimasukkan.
    ("man_made", "works"),             # pabrik
    ("landuse", "industrial"),         # kawasan/lahan industri
    ("building", "warehouse"),         # gudang
]

# ---------------------------------------------------------------------------
# FILTER NOISE
# ---------------------------------------------------------------------------
# Pola nama yang hampir pasti BUKAN lead: service center konsumen, kantor
# pemerintah, gedung/properti. Ini ketahuan dari inspeksi manual data v2.
POLA_BUANG = re.compile(
    r"(service\s*cent(er|re)|customer\s*service|care\s*cent(er|re)"
    r"|service,?\s*parts|authorized\s*service|pusat\s*servis"
    r"|kelurahan|kecamatan|kantor\s*pos|puskesmas|polsek|polres"
    r"|\bkpu\b|\bdprd\b|\bbpjs\b|\bsamsat\b"
    r"|office\s*park|business\s*park|wisma\b|graha\b|menara\b|\bplaza\b"

    # Ditambah 3 Sep 2026 bersama tag industri. Ketiganya terlihat di
    # sampel pra-panen, bukan dibayangkan:
    #   "Pabrik" x9 di Cikarang  -> man_made=works tanpa nama sebenarnya
    #   "Karawang International Industrial City" -> KAWASAN, bukan perusahaan
    #   "Tanrise Westgate", "Pergudangan WIRA9" -> properti/kompleks
    r"|^pabrik$|^gudang$|^pergudangan\b|^kawasan\b"
    r"|industrial\s*(city|estate|park)|kawasan\s*industri"
    r"|\bpergudangan\b|\bruko\b|\bsppbe\b)",
    re.IGNORECASE,
)


def is_noise(nama: str) -> bool:
    """True kalau nama cocok pola yang harus dibuang."""
    return bool(POLA_BUANG.search(nama))


def build_query(bbox, tag_key, tag_value):
    south, west, north, east = bbox
    return f"""
    [out:json][timeout:90];
    (
      node["{tag_key}"="{tag_value}"]({south},{west},{north},{east});
      way["{tag_key}"="{tag_value}"]({south},{west},{north},{east});
    );
    out center tags;
    """


# ---------------------------------------------------------------------------
# AMBIL DATA
# ---------------------------------------------------------------------------
def fetch_from_overpass(query, max_retries=5):
    """
    Kirim query ke Overpass. Kalau server sibuk (429/504), tunggu makin lama
    lalu coba lagi. Balikin None kalau gagal total — dibedakan dari [] yang
    artinya "berhasil tapi memang tidak ada hasil". Perbedaan ini penting
    supaya kombinasi yang gagal tidak ditandai selesai di harvest_log.
    """
    wait = 30
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=180
            )
        except requests.exceptions.RequestException as e:
            print(f"    Koneksi bermasalah: {e} — tunggu {wait}s...")
            time.sleep(wait)
            wait *= 2
            continue

        if response.status_code in (429, 504):
            print(f"    Server sibuk ({response.status_code}) — "
                  f"percobaan {attempt}/{max_retries}, tunggu {wait}s...")
            time.sleep(wait)
            wait *= 2
            continue

        try:
            response.raise_for_status()
            return response.json().get("elements", [])
        except Exception as e:
            print(f"    Error tak terduga: {e}")
            return None

    print(f"    MENYERAH setelah {max_retries}x percobaan.")
    return None


def parse_element(element, kota):
    tags = element.get("tags", {})

    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")

    alamat = ", ".join(
        p for p in (
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
            tags.get("addr:city"),
        ) if p
    ) or None

    return {
        "osm_id": element["id"],
        "name": tags.get("name"),
        "category": tags.get("office") or tags.get("shop"),
        "address": alamat,
        "city": kota,
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website"),
        "latitude": lat,
        "longitude": lon,
    }


# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            osm_id        INTEGER PRIMARY KEY,
            name          TEXT,
            category      TEXT,
            address       TEXT,
            phone         TEXT,
            website       TEXT,
            latitude      REAL,
            longitude     REAL,
            source        TEXT DEFAULT 'osm',
            discovered_at TEXT
        )
    """)

    # Migrasi: database lama (v2) belum punya kolom 'city'. Tambahkan kalau
    # belum ada, supaya data lama tetap terpakai dan tidak perlu hapus DB.
    kolom = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
    if "city" not in kolom:
        print("Menambah kolom 'city' ke tabel lama...")
        conn.execute("ALTER TABLE leads ADD COLUMN city TEXT")

    # Catatan kombinasi yang sudah selesai, supaya bisa dilanjut kalau mati.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS harvest_log (
            city       TEXT,
            tag_key    TEXT,
            tag_value  TEXT,
            done_at    TEXT,
            PRIMARY KEY (city, tag_key, tag_value)
        )
    """)
    conn.commit()


def sudah_selesai(conn, kota, tag_key, tag_value):
    return conn.execute(
        "SELECT 1 FROM harvest_log WHERE city=? AND tag_key=? AND tag_value=?",
        (kota, tag_key, tag_value),
    ).fetchone() is not None


def tandai_selesai(conn, kota, tag_key, tag_value):
    conn.execute(
        "INSERT OR REPLACE INTO harvest_log VALUES (?,?,?,?)",
        (kota, tag_key, tag_value, datetime.now(timezone.utc).isoformat()),
    )


def save_lead(conn, lead):
    conn.execute(
        """
        INSERT OR IGNORE INTO leads
            (osm_id, name, category, address, city, phone, website,
             latitude, longitude, discovered_at)
        VALUES (:osm_id, :name, :category, :address, :city, :phone, :website,
                :latitude, :longitude, :discovered_at)
        """,
        {**lead, "discovered_at": datetime.now(timezone.utc).isoformat()},
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    total_kombinasi = len(AREAS) * len(CATEGORIES)
    print(f"Rencana: {len(AREAS)} kota x {len(CATEGORIES)} kategori "
          f"= {total_kombinasi} query.")
    print("Perkiraan waktu: 30-60 menit. Aman ditinggal — kalau mati di")
    print("tengah jalan, jalankan lagi dan dia lanjut dari yang belum selesai.\n")

    baru_total = dibuang_total = dilewati_total = 0
    ke = 0

    for kota, bbox in AREAS.items():
        for tag_key, tag_value in CATEGORIES:
            ke += 1
            label = f"[{ke}/{total_kombinasi}] {kota} — {tag_key}={tag_value}"

            if sudah_selesai(conn, kota, tag_key, tag_value):
                print(f"{label}: sudah pernah, dilewati.")
                dilewati_total += 1
                continue

            print(f"{label} ...")
            elements = fetch_from_overpass(build_query(bbox, tag_key, tag_value))

            if elements is None:
                # Gagal — JANGAN tandai selesai, supaya dicoba lagi nanti.
                print("    (tidak ditandai selesai, akan dicoba lagi)")
                continue

            baru = dibuang = 0
            for element in elements:
                lead = parse_element(element, kota)
                if not lead["name"]:
                    continue
                if is_noise(lead["name"]):
                    dibuang += 1
                    continue
                sebelum = conn.total_changes
                save_lead(conn, lead)
                if conn.total_changes > sebelum:
                    baru += 1

            tandai_selesai(conn, kota, tag_key, tag_value)
            conn.commit()

            print(f"    -> {len(elements)} mentah | {baru} baru disimpan "
                  f"| {dibuang} dibuang (noise)")
            baru_total += baru
            dibuang_total += dibuang

            time.sleep(20)  # jeda sopan untuk server gratis

    total_db = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.close()

    print(f"\n{'='*55}")
    print(f"Selesai. {baru_total} lead baru, {dibuang_total} dibuang sebagai noise.")
    print(f"{dilewati_total} kombinasi dilewati (sudah pernah dipanen).")
    print(f"Total isi database sekarang: {total_db} entri.")
    print(f"Jalankan 'python cek_db.py' untuk memeriksa kualitasnya.")


if __name__ == "__main__":
    main()