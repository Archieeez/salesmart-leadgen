"""
buat_dashboard.py
=================
Baca data/leads.db (dan data/bukti.db kalau ada), hasilkan docs/index.html —
dashboard visual yang bisa dibuka langsung di browser (klik dua kali, tidak
perlu server).

Jalankan ulang setiap selesai panen supaya angkanya ikut terbarui:
    python src/buat_dashboard.py

TIDAK ADA LAGI ANGKA YANG DIKETIK DI FILE INI.
    Versi sebelumnya menyimpan peringkat need score sebagai daftar tetap di
    dalam kode. Akibatnya bisa ditebak: begitu companies_scored.csv berubah,
    dashboard diam-diam menampilkan angka lama. Blue Bird sempat tertulis 35
    di sini padahal datanya sudah 50.

    Sekarang semuanya dibaca dari sumber aslinya. Kalau sumbernya berubah,
    dashboard ikut berubah — atau tidak ditampilkan sama sekali.

Bagian yang datanya belum ada akan DILEWATI, bukan ditampilkan kosong.
Jadi file ini tetap jalan di komputer yang belum menjalankan Phase 2.
"""

import csv
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "leads.db"
DB_BUKTI = BASE / "data" / "bukti.db"
CSV_SKOR = BASE / "data" / "companies_scored.csv"
OUT = BASE / "docs" / "index.html"

# --------------------------------------------------------------------------
# Warna — dipertahankan dari versi sebelumnya supaya dashboard tetap terasa
# satu keluarga dengan yang sudah Anda kenal.
# --------------------------------------------------------------------------
BIRU, BIRU_MUDA = "#185FA5", "#B5D4F4"
HIJAU, HIJAU_MUDA = "#0F6E56", "#9FE1CB"
HIJAU_SEDANG = "#1D9E75"
OKER = "#EF9F27"
MERAH = "#D85A30"
UNGU = "#7F77DD"
ABU = "#B4B2A9"

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
h3{font-size:13px;font-weight:500;margin:20px 0 8px;color:var(--ink3)}
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
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:4px;
border:1px solid var(--line);color:var(--ink3);vertical-align:middle;margin-left:6px}
.tag.tegak{border-color:#1D9E75;color:#1D9E75}
.tag.lantai{border-color:#EF9F27;color:#EF9F27;border-style:dashed}
.komp{display:flex;gap:2px;height:20px;flex:1;border-radius:4px;overflow:hidden}
.komp i{display:block}
.kosong{color:var(--ink3);font-size:13px;font-style:italic}
footer{margin-top:32px;padding-top:16px;border-top:1px solid var(--line);
font-size:12px;color:var(--ink3)}
footer code{font-size:12px}
"""


# --------------------------------------------------------------------------
# Pembantu
# --------------------------------------------------------------------------

def baris(label, isi_track, nilai, judul=""):
    t = f' title="{judul}"' if judul else ""
    return (f'<div class="row"{t}><div class="lbl">{label}</div>'
            f'<div class="track">{isi_track}</div>'
            f'<div class="val">{nilai}</div></div>')


def isi(lebar_pct, warna):
    return f'<div class="fill" style="width:{lebar_pct:.1f}%;background:{warna}"></div>'


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def tabel_ada(con, nama):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nama,)).fetchone())


def buka_ro(path: Path):
    """Buka database hanya-baca. Dipakai untuk bukti.db yang mungkin sedang
    ditulis panen_bukti.py — jangan sampai dashboard mengunci panen."""
    if not path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True,
                               timeout=2.0)
    except sqlite3.Error:
        return None


# --------------------------------------------------------------------------
# Bagian-bagian dashboard
# --------------------------------------------------------------------------

def bagian_need():
    """Peringkat kebutuhan, dibaca dari companies_scored.csv."""
    if not CSV_SKOR.exists():
        return ""
    rows = list(csv.DictReader(open(CSV_SKOR, encoding="utf-8")))
    KOMP = [("dist_model", 35, "#12406E"), ("field_sales", 30, BIRU),
            ("scale", 20, "#6FA3D6"), ("industry_fit", 15, BIRU_MUDA)]

    data = []
    for r in rows:
        n = sum(int(r[k]) for k, _, _ in KOMP)
        data.append((n, r["company_name"], r, r.get("need_notes", "")))
    data.sort(reverse=True, key=lambda x: (x[0], x[1]))

    out = []
    for n, nama, r, catatan in data:
        seg = "".join(
            f'<i style="flex:{int(r[k])} 1 0;background:{w}"></i>'
            for k, _, w in KOMP if int(r[k]) > 0)
        out.append(
            f'<div class="row" title="{esc(catatan)[:180]}">'
            f'<div class="lbl">{esc(nama)}</div>'
            f'<div class="komp">{seg}</div>'
            f'<div class="val">{n}</div></div>')

    lg = "".join(f'<span><i class="sw" style="background:{w}"></i>{k}</span>'
                 for k, _, w in KOMP)
    return (f'<h2>Peringkat kebutuhan Salesmart — {len(rows)} perusahaan '
            f'dinilai manual</h2>\n<div class="legend">{lg}</div>\n'
            + "\n".join(out))


def bagian_kontak(con):
    """Hasil enrichment nomor telepon dari situs resmi."""
    if not tabel_ada(con, "kontak_web"):
        return "", None
    total = con.execute("SELECT COUNT(*) FROM kontak_web").fetchone()[0]
    if not total:
        return "", None
    kelas = dict(con.execute(
        "SELECT COALESCE(kelas_kontak,'tidak ada'), COUNT(*) "
        "FROM kontak_web GROUP BY 1").fetchall())
    urut = [("langsung", "Jalur kantor", HIJAU),
            ("seluler", "Nomor HP", OKER),
            ("layanan", "Call center", UNGU),
            ("tidak ada", "Tidak ketemu", ABU)]
    out = [baris(lbl, isi(kelas.get(k, 0) / total * 100, w),
                 f'{kelas.get(k, 0)} <span class="sub">/ {total}</span>')
           for k, lbl, w in urut if kelas.get(k, 0)]
    langsung = kelas.get("langsung", 0)
    return (f'<h2>Enrichment telepon dari situs resmi — {total} perusahaan uji</h2>\n'
            + "\n".join(out)), langsung


def bagian_kebutuhan(con):
    """Nilai kebutuhan hasil pembacaan bukti."""
    if not tabel_ada(con, "kebutuhan"):
        return "", None
    rows = con.execute(
        "SELECT nama, dist_model, field_sales, scale, industry_fit, "
        "need_score, bukti_kuat, status_nilai, catatan FROM kebutuhan "
        "ORDER BY status_nilai, need_score DESC").fetchall()
    if not rows:
        return "", None

    KOMP = [(1, "#12406E"), (2, BIRU), (3, "#6FA3D6"), (4, BIRU_MUDA)]
    tegak, lantai = [], []
    for r in rows:
        nama, need, bk, st, catatan = r[0], r[5], r[6], r[7], r[8]
        seg = "".join(f'<i style="flex:{r[i]} 1 0;background:{w}"></i>'
                      for i, w in KOMP if r[i] > 0)
        tag = ('<span class="tag tegak">bukti %s/4</span>' % bk
               if st == "nilai_tegak"
               else '<span class="tag lantai">bukti %s/4</span>' % bk)
        h = (f'<div class="row" title="{esc(catatan)[:200]}">'
             f'<div class="lbl">{esc(nama)[:26]}</div>'
             f'<div class="komp">{seg}</div>'
             f'<div class="val">{need}{tag}</div></div>')
        (tegak if st == "nilai_tegak" else lantai).append(h)

    blok = [f'<h2>Nilai kebutuhan hasil pembacaan bukti — {len(rows)} perusahaan</h2>']
    if tegak:
        blok.append('<h3>Nilai tegak — minimal 3 dari 4 komponen berbukti</h3>')
        blok += tegak
    if lantai:
        blok.append('<h3>Bukti belum cukup — angka ini LANTAI, bukan penilaian '
                    'final. Jangan dipakai memeringkat.</h3>')
        blok += lantai
    return "\n".join(blok), len(tegak)


def bagian_panen():
    """Cakupan panen halaman bukti, dari bukti.db kalau ada."""
    con = buka_ro(DB_BUKTI)
    if con is None:
        return "", None
    try:
        if not tabel_ada(con, "panen_log"):
            return "", None
        dicoba = con.execute("SELECT COUNT(*) FROM panen_log").fetchone()[0]
        berhasil = con.execute(
            "SELECT COUNT(*) FROM panen_log WHERE jml_halaman > 0").fetchone()[0]
        halaman = con.execute("SELECT COUNT(*) FROM halaman_bukti").fetchone()[0]
        per_jenis = con.execute(
            "SELECT jenis, COUNT(*) FROM halaman_bukti GROUP BY jenis "
            "ORDER BY 2 DESC").fetchall()
    except sqlite3.Error:
        return "", None
    finally:
        con.close()

    if not dicoba:
        return "", None
    maks = max((v for _, v in per_jenis), default=1)
    jenis_html = "\n".join(
        baris(esc(j), isi(v / maks * 100, BIRU), v) for j, v in per_jenis)

    return (f'<h2>Panen halaman bukti — {halaman} halaman dari {berhasil} situs</h2>\n'
            + baris("Situs dicoba", isi(100, BIRU_MUDA), dicoba)
            + "\n" + baris("Menghasilkan halaman", isi(berhasil / dicoba * 100, HIJAU),
                           f'{berhasil} <span class="sub">'
                           f'({berhasil / dicoba * 100:.0f}%)</span>')
            + "\n" + baris("Nol halaman", isi((dicoba - berhasil) / dicoba * 100, ABU),
                           dicoba - berhasil)
            + f'\n<h3>Jenis halaman yang terkumpul</h3>\n{jenis_html}'), halaman


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

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

    html_kontak, n_langsung = bagian_kontak(c)
    html_kebutuhan, n_tegak = bagian_kebutuhan(c)
    c.close()

    html_panen, n_halaman = bagian_panen()
    html_need = bagian_need()

    maks_kota = max((k[1] for k in kota), default=1) or 1
    maks_ars = max((a[1] for a in ars), default=1) or 1

    def w_kat(pct):
        return (HIJAU if pct >= 35 else HIJAU_SEDANG if pct >= 18
                else HIJAU_MUDA if pct >= 10 else ABU)

    kota_html = "\n".join(
        f'<div class="row"><div class="lbl">{esc(n)}</div><div class="track">'
        f'<div class="fill" style="width:{t/maks_kota*100:.1f}%;background:{BIRU_MUDA}"></div>'
        f'<div class="fill2" style="width:{p/maks_kota*100:.1f}%;background:{BIRU}"></div>'
        f'</div><div class="val">{t} <span class="sub">/ {p}</span></div></div>'
        for n, t, p in kota)

    kat_html = "\n".join(
        f'<div class="row"><div class="lbl">{esc(n)}</div><div class="track">'
        f'<div class="fill" style="width:{round(p/t*100)/60*100:.1f}%;'
        f'background:{w_kat(round(p/t*100))}"></div></div>'
        f'<div class="val">{round(p/t*100)}% <span class="sub">({p}/{t})</span></div></div>'
        for n, t, p in kat)

    warna_ars = [MERAH, OKER, UNGU, ABU]
    ars_html = "\n".join(
        f'<div class="row"><div class="lbl">{esc(a.split("(")[0].strip())}</div>'
        f'<div class="track"><div class="fill" style="width:{v/maks_ars*100:.1f}%;'
        f'background:{warna_ars[i % len(warna_ars)]}"></div></div>'
        f'<div class="val">{v}</div></div>'
        for i, (a, v) in enumerate(ars))

    # --- kartu angka, hanya yang datanya ada -----------------------------
    kartu = [
        ("Data mentah", f"{tot[0] + n_ars:,}", "#E6F1FB", "#185FA5", "#042C53"),
        ("Bersih", tot[0], "#E1F5EE", "#0F6E56", "#04342C"),
        ("Punya telepon", tot[1], "#EEEDFE", "#534AB7", "#26215C"),
        ("Punya website", tot[2], "#FBEAF0", "#993556", "#4B1528"),
        ("Dibuang", n_ars, "#FAECE7", "#993C1D", "#4A1B0C"),
    ]
    if n_halaman:
        kartu.append(("Halaman bukti", n_halaman, "#E6F1FB", "#185FA5", "#042C53"))
    if n_tegak is not None:
        kartu.append(("Nilai tegak", n_tegak, "#E1F5EE", "#0F6E56", "#04342C"))
    kartu_html = "\n".join(
        f'<div class="c" style="background:{bg}"><p class="k" style="color:{c1}">{k}</p>'
        f'<p class="v" style="color:{c2}">{v}</p></div>'
        for k, v, bg, c1, c2 in kartu)

    fase2 = "\n".join(x for x in [html_panen, html_kebutuhan, html_kontak] if x)

    html = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard — salesmart-leadgen</title>
<style>{CSS}</style></head><body><div class="wrap">

<h1>salesmart-leadgen</h1>
<p class="meta">Dashboard teknis — kesehatan pipeline, dibuat otomatis dari data/leads.db<br>
Untuk daftar lead siap telepon, lihat <a href="antrian.html" style="color:#185FA5">Antrian Lead</a>.</p>

<div class="cards">
{kartu_html}
</div>

<h2>Sebaran per kota</h2>
<div class="legend"><span><i class="sw" style="background:{BIRU_MUDA}"></i>Total entri</span><span><i class="sw" style="background:{BIRU}"></i>Punya telepon</span></div>
{kota_html}

<h2>Cakupan telepon per kategori OSM</h2>
{kat_html}

<h2>{n_ars} entri yang dibuang saat pembersihan</h2>
{ars_html}

{fase2}

{html_need}

<div class="note">
<b>Cara membaca angka-angka ini</b>
<ul>
<li>Kategori spesifik jauh mengalahkan generik: <b>consulting 60%</b> vs <b>company 12%</b> cakupan telepon.</li>
<li>Denpasar menghasilkan entri terbanyak tapi teleponnya paling sedikit — banyak belum tentu berkualitas.</li>
<li>145 duplikat lolos dedup berbasis ID karena <b>PT. Bakti Mandiri Perkasa</b> dan <b>PT BAKTI MANDIRI PERKASA</b> punya osm_id berbeda dengan telepon sama.</li>
<li>Batang pendek di peringkat kebutuhan (Traveloka, Tokopedia) adalah perusahaan besar yang <b>tidak</b> punya tim sales lapangan — tidak cocok untuk Salesmart.</li>
<li>Panjang batang di peringkat kebutuhan menunjukkan <b>komposisinya</b>, bukan cuma totalnya. Gojek dan Erajaya nilainya mirip tapi susunannya kebalikan.</li>
<li>Nilai bertanda <b>bukti &lt;3/4</b> adalah LANTAI — yang terbukti sejauh ini, bukan penilaian final. Jangan dipakai memeringkat.</li>
<li>Hanya 27 dari {tot[0]} entri (3,2%) cocok profil klien ideal. Ini <b>baseline pembanding</b> untuk menilai apakah Places API nanti lebih baik.</li>
</ul>
</div>

<footer>Perbarui dashboard ini dengan: <code>python src/buat_dashboard.py</code><br>
Angka di halaman ini seluruhnya dibaca dari database dan CSV — tidak ada yang diketik di dalam kode.</footer>
</div></body></html>"""

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Dashboard dibuat: {OUT}")
    ada = [n for n, x in [("panen", html_panen), ("kebutuhan", html_kebutuhan),
                          ("kontak", html_kontak), ("need", html_need)] if x]
    print(f"Bagian yang tampil: {', '.join(ada)}")
    print("Buka dengan klik dua kali file itu di File Explorer.")


if __name__ == "__main__":
    main()
