"""
buat_dashboard.py
=================
Baca data/leads.db, hasilkan docs/index.html — dashboard visual yang bisa
dibuka langsung di browser (klik dua kali, tidak perlu server).

Jalankan ulang setiap selesai panen supaya angkanya ikut terbarui:
    python src/buat_dashboard.py

Peringkat need score di bagian bawah masih ditulis manual di DAFTAR_NEED
karena datanya berasal dari riset manual (companies_scored.csv), bukan dari
leads.db. Kalau menambah perusahaan tervalidasi, tambahkan juga di sini.
"""

import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "leads.db"
OUT = BASE / "docs" / "index.html"

# Hasil riset manual — lihat data/companies_scored.csv
DAFTAR_NEED = [
    ("Wings Group", 100), ("Mayora", 100), ("Kalbe Farma", 100),
    ("Paragon", 100), ("Sido Muncul", 100), ("MS Glow", 85),
    ("Indomaret", 85), ("Alfamart", 85), ("J&T Express", 85),
    ("SiCepat", 85), ("JNE", 85), ("TIKI", 85), ("Wahana", 80),
    ("Erajaya", 75), ("Gojek", 70), ("Kopi Kenangan", 55),
    ("Blibli", 40), ("Blue Bird", 35), ("Tokopedia", 35), ("Traveloka", 25),
]

CSS = """
:root{--bg:#fcfcfb;--card:#fff;--ink:#0b0b0b;--ink2:#52514e;--ink3:#898781;--line:#e1e0d9}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#898781;--line:#2c2c2a}}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.6}
.wrap{max-width:820px;margin:0 auto}
h1{font-size:24px;font-weight:500;margin:0 0 4px}
.meta{color:var(--ink3);font-size:13px;margin:0 0 28px}
h2{font-size:15px;font-weight:500;margin:32px 0 12px;color:var(--ink2)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:8px}
.c{border-radius:8px;padding:14px 16px}
.c p{margin:0}
.c .k{font-size:12px;margin-bottom:4px}
.c .v{font-size:24px;font-weight:500}
.row{display:flex;align-items:center;gap:12px;margin-bottom:7px;font-size:13px}
.lbl{width:150px;flex-shrink:0;color:var(--ink2);text-align:right}
.track{flex:1;height:20px;background:var(--line);border-radius:4px;position:relative;overflow:hidden}
.fill,.fill2{position:absolute;left:0;top:0;height:100%;border-radius:4px}
.val{width:92px;flex-shrink:0;color:var(--ink);font-variant-numeric:tabular-nums}
.sub{color:var(--ink3);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink3);margin-bottom:10px}
.legend span{display:flex;align-items:center;gap:5px}
.sw{width:10px;height:10px;border-radius:2px}
.note{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:14px 16px;font-size:13px;color:var(--ink2);margin-top:28px}
.note b{color:var(--ink);font-weight:500}
.note ul{margin:8px 0 0;padding-left:18px}
.note li{margin-bottom:6px}
footer{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);
font-size:12px;color:var(--ink3)}
"""


def main():
    if not DB.exists():
        print(f"Database tidak ada: {DB}")
        print("Jalankan src/discover_osm.py dulu.")
        raise SystemExit(1)

    c = sqlite3.connect(DB)
    q = lambda s: c.execute(s).fetchall()

    kota = q("SELECT city,COUNT(*),COUNT(phone) FROM leads WHERE city IS NOT NULL "
             "GROUP BY city ORDER BY COUNT(*) DESC")
    kat = q("SELECT category,COUNT(*),COUNT(phone) FROM leads GROUP BY category "
            "ORDER BY COUNT(phone)*1.0/COUNT(*) DESC")
    ars = q("SELECT alasan,COUNT(*) FROM leads_arsip GROUP BY alasan "
            "ORDER BY COUNT(*) DESC")
    tot = q("SELECT COUNT(*),COUNT(phone),COUNT(website) FROM leads")[0]
    n_ars = c.execute("SELECT COUNT(*) FROM leads_arsip").fetchone()[0]
    c.close()

    maks_kota = max(k[1] for k in kota) or 1
    maks_ars = max(a[1] for a in ars) or 1

    def w_kat(pct):
        return ("#0F6E56" if pct >= 35 else "#1D9E75" if pct >= 18
                else "#9FE1CB" if pct >= 10 else "#B4B2A9")

    def w_need(v):
        return "#1D9E75" if v >= 75 else "#EF9F27" if v >= 50 else "#B4B2A9"

    kota_html = "\n".join(
        f'<div class="row"><div class="lbl">{n}</div><div class="track">'
        f'<div class="fill" style="width:{t/maks_kota*100:.1f}%;background:#B5D4F4"></div>'
        f'<div class="fill2" style="width:{p/maks_kota*100:.1f}%;background:#185FA5"></div>'
        f'</div><div class="val">{t} <span class="sub">/ {p}</span></div></div>'
        for n, t, p in kota)

    kat_html = "\n".join(
        f'<div class="row"><div class="lbl">{n}</div><div class="track">'
        f'<div class="fill" style="width:{round(p/t*100)/60*100:.1f}%;'
        f'background:{w_kat(round(p/t*100))}"></div></div>'
        f'<div class="val">{round(p/t*100)}% <span class="sub">({p}/{t})</span></div></div>'
        for n, t, p in kat)

    warna_ars = ["#D85A30", "#EF9F27", "#7F77DD", "#B4B2A9"]
    ars_html = "\n".join(
        f'<div class="row"><div class="lbl">{a.split("(")[0].strip()}</div>'
        f'<div class="track"><div class="fill" style="width:{v/maks_ars*100:.1f}%;'
        f'background:{warna_ars[i % len(warna_ars)]}"></div></div>'
        f'<div class="val">{v}</div></div>'
        for i, (a, v) in enumerate(ars))

    need_html = "\n".join(
        f'<div class="row"><div class="lbl">{n}</div><div class="track">'
        f'<div class="fill" style="width:{v}%;background:{w_need(v)}"></div></div>'
        f'<div class="val">{v}</div></div>'
        for n, v in DAFTAR_NEED)

    mentah = tot[0] + n_ars
    html = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard — salesmart-leadgen</title>
<style>{CSS}</style></head><body><div class="wrap">

<h1>salesmart-leadgen</h1>
<p class="meta">Dashboard hasil pipeline — dibuat otomatis dari data/leads.db</p>

<div class="cards">
<div class="c" style="background:#E6F1FB"><p class="k" style="color:#185FA5">Data mentah</p><p class="v" style="color:#042C53">{mentah:,}</p></div>
<div class="c" style="background:#E1F5EE"><p class="k" style="color:#0F6E56">Bersih</p><p class="v" style="color:#04342C">{tot[0]}</p></div>
<div class="c" style="background:#EEEDFE"><p class="k" style="color:#534AB7">Punya telepon</p><p class="v" style="color:#26215C">{tot[1]}</p></div>
<div class="c" style="background:#FBEAF0"><p class="k" style="color:#993556">Punya website</p><p class="v" style="color:#4B1528">{tot[2]}</p></div>
<div class="c" style="background:#FAECE7"><p class="k" style="color:#993C1D">Dibuang</p><p class="v" style="color:#4A1B0C">{n_ars}</p></div>
</div>

<h2>Sebaran per kota</h2>
<div class="legend"><span><i class="sw" style="background:#B5D4F4"></i>Total entri</span><span><i class="sw" style="background:#185FA5"></i>Punya telepon</span></div>
{kota_html}

<h2>Cakupan telepon per kategori OSM</h2>
{kat_html}

<h2>{n_ars} entri yang dibuang saat pembersihan</h2>
{ars_html}

<h2>Peringkat kebutuhan Salesmart — 20 perusahaan tervalidasi manual</h2>
<div class="legend"><span><i class="sw" style="background:#1D9E75"></i>Prioritas 1</span><span><i class="sw" style="background:#EF9F27"></i>Prioritas 2</span><span><i class="sw" style="background:#B4B2A9"></i>Kemungkinan tidak butuh</span></div>
{need_html}

<div class="note">
<b>Cara membaca angka-angka ini</b>
<ul>
<li>Kategori spesifik jauh mengalahkan generik: <b>consulting 60%</b> vs <b>company 12%</b> cakupan telepon.</li>
<li>Denpasar menghasilkan entri terbanyak tapi teleponnya paling sedikit — banyak belum tentu berkualitas.</li>
<li>145 duplikat lolos dedup berbasis ID karena <b>PT. Bakti Mandiri Perkasa</b> dan <b>PT BAKTI MANDIRI PERKASA</b> punya osm_id berbeda dengan telepon sama.</li>
<li>Batang abu-abu di grafik terakhir (Traveloka, Tokopedia, Blibli) adalah perusahaan besar yang <b>tidak</b> punya tim sales lapangan — tidak cocok untuk Salesmart.</li>
<li>Hanya 27 dari {tot[0]} entri (3,2%) cocok profil klien ideal. Ini <b>baseline pembanding</b> untuk menilai apakah Places API nanti lebih baik.</li>
</ul>
</div>

<footer>Perbarui dashboard ini dengan: <code>python src/buat_dashboard.py</code></footer>
</div></body></html>"""

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Dashboard dibuat: {OUT}")
    print(f"Buka dengan klik dua kali file itu di File Explorer.")


if __name__ == "__main__":
    main()
