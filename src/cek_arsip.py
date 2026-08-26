"""
cek_arsip.py — audit isi leads_arsip: apa saja yang dibuang dan kenapa.
Penting dijalankan setelah bersihkan_db.py, untuk memastikan filter
tidak salah buang perusahaan asli.
"""
import sqlite3
from pathlib import Path

# Script ada di src/, database ada di data/ — naik satu level lalu masuk data.
# Tetap dikunci ke lokasi file .py, BUKAN ke folder kerja terminal.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.db"
conn = sqlite3.connect(DB_PATH)

print("=== JUMLAH PER ALASAN ===")
for alasan, n in conn.execute(
    "SELECT alasan, COUNT(*) FROM leads_arsip GROUP BY alasan ORDER BY COUNT(*) DESC"
):
    print(f"  {n:>5}  {alasan}")

print("\n=== PERIKSA INI: yang dibuang TAPI punya telepon ===")
print("(kalau ada perusahaan asli di sini, berarti filter salah buang)")
for nama, alasan, tel in conn.execute("""
    SELECT name, alasan, phone FROM leads_arsip
    WHERE phone IS NOT NULL AND alasan NOT LIKE 'kategori mall%'
    ORDER BY alasan
"""):
    print(f"  {nama[:42]:<44} | {tel[:20]:<20} | {alasan[:35]}")

conn.close()