"""
cek_db.py (v2) — periksa isi leads.db dengan sampel yang JUJUR.

Perbaikan dari v1:
- Cakupan telepon/website dipecah PER KATEGORI (bukan cuma total).
  Total 20% bisa menyesatkan kalau ternyata semuanya datang dari mall.
- Sampel diambil ACAK (ORDER BY RANDOM()), bukan LIMIT 20 tanpa urutan
  yang cuma mengembalikan baris pertama sesuai osm_id.
- Fokus khusus ke kategori 'company' — itu 65% database tapi isinya
  belum pernah kita lihat sama sekali.
"""
import sqlite3
from pathlib import Path

# Script ada di src/, database ada di data/ — naik satu level lalu masuk data.
# Tetap dikunci ke lokasi file .py, BUKAN ke folder kerja terminal.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"

if not DB_PATH.exists():
    print(f"Database belum ada di: {DB_PATH}")
    raise SystemExit

conn = sqlite3.connect(DB_PATH)
print(f"Membaca: {DB_PATH}\n")

print("=== CAKUPAN KONTAK PER KATEGORI ===")
print(f"{'kategori':<22}{'total':>7}{'telepon':>10}{'%':>7}{'website':>10}{'%':>7}")
for kat, tot, tel, web in conn.execute("""
    SELECT category, COUNT(*), COUNT(phone), COUNT(website)
    FROM leads GROUP BY category ORDER BY COUNT(*) DESC
"""):
    print(f"{kat or '(kosong)':<22}{tot:>7}{tel:>10}{tel/tot*100:>6.0f}%{web:>10}{web/tot*100:>6.0f}%")

# Angka paling penting: lead yang BUKAN mall DAN punya telepon.
layak = conn.execute("""
    SELECT COUNT(*) FROM leads
    WHERE category != 'mall' AND phone IS NOT NULL
""").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

print(f"\n=== ANGKA YANG SEBENARNYA PENTING ===")
print(f"Bukan mall + punya telepon : {layak} dari {total} entri "
      f"({layak/total*100:.1f}%)")

print("\n=== 25 SAMPEL ACAK KATEGORI 'company' ===")
print("(inilah 65% database yang belum pernah kita lihat isinya)")
for nama, tel, web in conn.execute("""
    SELECT name, phone, website FROM leads
    WHERE category = 'company' ORDER BY RANDOM() LIMIT 25
"""):
    tanda = "TEL" if tel else "   "
    print(f"  [{tanda}] {nama[:55]}")

print("\n=== SEMUA 'company' YANG PUNYA TELEPON ===")
rows = conn.execute("""
    SELECT name, phone FROM leads
    WHERE category = 'company' AND phone IS NOT NULL
""").fetchall()
print(f"(jumlah: {len(rows)})")
for nama, tel in rows[:40]:
    print(f"  {nama[:45]:<47} | {tel}")

conn.close()