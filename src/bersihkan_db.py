"""
bersihkan_db.py
===============
Bersihkan leads.db secara retroaktif:
1. Backup otomatis dulu (leads_backup_<waktu>.db) — tidak ada yang hilang.
2. Buang kategori 'mall' (properti, bukan perusahaan).
3. Terapkan filter noise ke SEMUA data lama (yang masuk sebelum filter ada).
4. Buang pola kantor cabang/gerai yang jelas (GraPARI, Plasa Telkom,
   "cabang", card center, dll) — konservatif, hanya pola yang pasti.
5. Dedup TINGKAT ENTITAS: dua entri dengan telepon sama, atau nama sama
   setelah dinormalisasi (PT/CV/tanda baca dibuang), dianggap satu
   perusahaan. Yang datanya paling lengkap dipertahankan. Contoh nyata
   dari data yang lolos dedup lama:
       PT. Bakti Mandiri Perkasa  | +62318296878
       PT BAKTI MANDIRI PERKASA   | +62318296878

Entri yang dibuang TIDAK dihapus permanen — dipindah ke tabel `leads_arsip`
lengkap dengan alasannya, supaya bisa diaudit dan dikembalikan kalau
ternyata filternya salah buang.

Jalankan:  python bersihkan_db.py
"""

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Script ada di src/, database ada di data/ — naik satu level lalu masuk data.
# Tetap dikunci ke lokasi file .py, BUKAN ke folder kerja terminal.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"

# --- Pola nama noise (sama dengan discover_osm.py v3) ----------------------
POLA_NOISE = re.compile(
    r"(service\s*cent(er|re)|customer\s*service|care\s*cent(er|re)"
    r"|service,?\s*parts|authorized\s*service|pusat\s*servis"
    r"|kelurahan|kecamatan|kantor\s*pos|puskesmas|polsek|polres"
    r"|\bkpu\b|\bdprd\b|\bbpjs\b|\bsamsat\b"
    r"|office\s*park|business\s*park|wisma\b|graha\b|menara\b|\bplaza\b)",
    re.IGNORECASE,
)

# --- Pola kantor cabang / gerai ritel yang JELAS ----------------------------
# Sengaja konservatif: hanya pola yang hampir mustahil salah tangkap.
# "BNI" atau "Telkom Indonesia" polos TIDAK difilter otomatis — terlalu
# berisiko salah buang; itu urusan review manual / rubric scoring nanti.
POLA_CABANG = re.compile(
    r"(\bcabang\b|kantor\s*cabang|\bbranch\b|\bkcp\b|\bkcu\b"
    r"|grapari|plasa\s*telkom|xl\s*center|gerai\s|galeri\s*indosat"
    r"|card\s*cent(er|re)|sales\s*office|service\s*point"
    r"|kantor\s*perwakilan|representative\s*office)",
    re.IGNORECASE,
)


def normalisasi_nama(nama):
    """
    'PT. Bakti Mandiri Perkasa' dan 'PT BAKTI MANDIRI PERKASA'
    harus menghasilkan string yang sama: 'bakti mandiri perkasa'.
    """
    n = nama.lower()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\b(pt|cv|ud|pd|tbk|persero|tb)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalisasi_telepon(telepon):
    """
    '+62 31 829-6878' dan '+62318296878' harus sama: '62318296878'.
    Kalau ada beberapa nomor (dipisah ;), pakai yang pertama.
    Nomor terlalu pendek (<7 digit, mis. call center '14010') diabaikan
    sebagai kunci dedup karena bukan nomor unik satu perusahaan.
    """
    if not telepon:
        return None
    pertama = telepon.split(";")[0]
    digit = re.sub(r"\D", "", pertama)
    if digit.startswith("0"):
        digit = "62" + digit[1:]
    return digit if len(digit) >= 7 else None


def kelengkapan(row):
    """Skor kelengkapan: dipakai memilih entri mana yang dipertahankan."""
    _, _, _, address, phone, website = row[:6]
    return sum(1 for v in (address, phone, website) if v)


def main():
    if not DB_PATH.exists():
        print(f"Database tidak ditemukan: {DB_PATH}")
        raise SystemExit(1)

    # ---- 1. BACKUP DULU ----------------------------------------------------
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_name(f"leads_backup_{stempel}.db")
    shutil.copy2(DB_PATH, backup)
    print(f"Backup dibuat: {backup.name}")

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads_arsip (
            osm_id INTEGER PRIMARY KEY, name TEXT, category TEXT,
            address TEXT, phone TEXT, website TEXT, latitude REAL,
            longitude REAL, source TEXT, discovered_at TEXT, city TEXT,
            alasan TEXT, diarsip_pada TEXT
        )
    """)

    def arsipkan(osm_ids, alasan):
        if not osm_ids:
            return 0
        sekarang = datetime.now(timezone.utc).isoformat()
        for oid in osm_ids:
            conn.execute("""
                INSERT OR IGNORE INTO leads_arsip
                SELECT osm_id, name, category, address, phone, website,
                       latitude, longitude, source, discovered_at, city,
                       ?, ? FROM leads WHERE osm_id = ?
            """, (alasan, sekarang, oid))
            conn.execute("DELETE FROM leads WHERE osm_id = ?", (oid,))
        conn.commit()
        return len(osm_ids)

    awal = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    print(f"Jumlah awal: {awal} entri\n")

    # ---- 2. Buang mall -----------------------------------------------------
    ids = [r[0] for r in conn.execute(
        "SELECT osm_id FROM leads WHERE category = 'mall'")]
    n = arsipkan(ids, "kategori mall (properti, bukan perusahaan)")
    print(f"[1] Mall dibuang                 : {n}")

    # ---- 3. Filter noise retroaktif ------------------------------------------
    ids = [r[0] for r in conn.execute("SELECT osm_id, name FROM leads")
           if r[1] and POLA_NOISE.search(r[1])]
    n = arsipkan(ids, "nama cocok pola noise (gedung/pemerintah/service center)")
    print(f"[2] Noise retroaktif dibuang     : {n}")

    # ---- 4. Kantor cabang / gerai --------------------------------------------
    ids = [r[0] for r in conn.execute("SELECT osm_id, name FROM leads")
           if r[1] and POLA_CABANG.search(r[1])]
    n = arsipkan(ids, "pola kantor cabang/gerai (bukan pengambil keputusan)")
    print(f"[3] Cabang/gerai dibuang         : {n}")

    # ---- 5. Dedup tingkat entitas --------------------------------------------
    rows = conn.execute("""
        SELECT osm_id, name, category, address, phone, website
        FROM leads WHERE name IS NOT NULL ORDER BY osm_id
    """).fetchall()

    terlihat = {}
    buang_dedup = []

    for row in rows:
        osm_id, nama, _, _, telepon, _ = row
        kunci_kandidat = [("nama", normalisasi_nama(nama))]
        tel_norm = normalisasi_telepon(telepon)
        if tel_norm:
            kunci_kandidat.insert(0, ("tel", tel_norm))

        duplikat_dari = None
        for kunci in kunci_kandidat:
            if kunci in terlihat:
                duplikat_dari = kunci
                break

        if duplikat_dari is None:
            for kunci in kunci_kandidat:
                terlihat[kunci] = row
            continue

        lama = terlihat[duplikat_dari]
        if kelengkapan(row) > kelengkapan(lama):
            buang_dedup.append(lama[0])
            for kunci in kunci_kandidat:
                terlihat[kunci] = row
        else:
            buang_dedup.append(osm_id)

    n = arsipkan(buang_dedup, "duplikat entitas (nama/telepon sama)")
    print(f"[4] Duplikat entitas dibuang     : {n}")

    # ---- Ringkasan -------------------------------------------------------------
    akhir = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    layak = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE phone IS NOT NULL").fetchone()[0]
    print(f"\n{'='*50}")
    print(f"Sebelum : {awal} entri")
    print(f"Sesudah : {akhir} entri bersih")
    print(f"Punya telepon (siap tindak lanjut): {layak}")
    print(f"\nSemua yang dibuang ada di tabel 'leads_arsip' beserta alasannya.")
    print(f"Untuk melihatnya, jalankan: python cek_arsip.py")

    conn.close()


if __name__ == "__main__":
    main()