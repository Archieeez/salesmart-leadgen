"""
buat_dashboard.py
=================
Baca data/leads.db (dan data/bukti.db kalau ada), hasilkan docs/teknis.html —
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rubrik  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "leads.db"
DB_BUKTI = BASE / "data" / "bukti.db"
CSV_SKOR = BASE / "data" / "companies_scored.csv"
OUT = BASE / "docs" / "teknis.html"

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
.tag.tolak{border-color:#B3261E;color:#B3261E;font-weight:600}
.note.blokir{border-left:3px solid #EF9F27}
.note.blokir b{color:#A8620A}
@media(prefers-color-scheme:dark){.note.blokir b{color:#D9A24E}}
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


def bagian_penyaring(con):
    """Corong penyaring pola: berapa yang ditemukan, berapa yang derau.

    KENAPA BAGIAN INI ADA:
        Penyaring pola (saring_bukti.py) adalah satu-satunya bagian
        pipeline yang selama ini tidak punya angka di mana pun. Padahal
        ia yang memutuskan SIAPA YANG DIBACA — kalau ia bocor, lead
        bagus hilang tanpa jejak dan tidak ada yang tahu.

        Yang ditampilkan sengaja BUKAN "berapa persen tepat". Penyaring
        memang tidak dirancang untuk tepat; ia dirancang untuk tidak
        melewatkan. Jadi yang diukur dua hal berbeda:

        1. Corong: dari sekian situs terpanen, berapa yang lolos ambang.
        2. Adu ke bacaan manusia: perusahaan yang skor polanya jauh dari
           bacaan manusia. Selisih BESAR ke bawah = penyaring nyaris
           melewatkan lead bagus (bahaya). Selisih besar ke atas =
           derau, yang memang boleh dan sudah diduga.
    """
    try:
        import saring_bukti
    except ImportError:
        return "", None
    if not DB_BUKTI.exists() or not tabel_ada(con, "kebutuhan"):
        return "", None
    try:
        per = saring_bukti.muat_teks(DB_BUKTI)
    except sqlite3.Error:
        return "", None
    if not per:
        return "", None

    manusia = {n: (need, st) for n, need, st in con.execute(
        "SELECT nama, need_score, status_nilai FROM kebutuhan")}
    kategori = saring_bukti.muat_kategori()

    AMBANG = 50
    lolos = tersaring = 0
    beda = []
    for p in per.values():
        h = saring_bukti.saring(p["teks"], kategori.get(p["nama"], ""),
                                halaman=p["halaman"])
        skor = sum(h[k]["nilai"] for k in rubrik.MAKS_KOMPONEN)
        if skor >= AMBANG:
            lolos += 1
        else:
            tersaring += 1
        m = manusia.get(p["nama"])
        if m and m[1] == "nilai_tegak":
            beda.append((skor - m[0], p["nama"], skor, m[0]))

    total = lolos + tersaring
    out = [f'<h2>Penyaring pola — {total} situs disaring, {lolos} masuk '
           f'antrian baca</h2>']
    out.append(baris("Lolos ambang %d" % AMBANG,
                     isi(lolos / total * 100, HIJAU),
                     f'{lolos} <span class="sub">({lolos / total * 100:.0f}%)</span>'))
    out.append(baris("Tersaring keluar", isi(tersaring / total * 100, ABU),
                     tersaring))

    # Yang berbahaya: penyaring memberi skor JAUH DI BAWAH bacaan manusia.
    bahaya = sorted([b for b in beda if b[0] <= -25])[:6]
    derau = sorted([b for b in beda if b[0] >= 25], reverse=True)[:6]
    if bahaya:
        out.append('<h3>Nyaris terlewat — pola menilai jauh di bawah bacaan '
                   'manusia. Ini yang berbahaya.</h3>')
        for d, nama, sp, sm in bahaya:
            out.append(baris(esc(nama)[:26], isi(abs(d), MERAH),
                             f'pola {sp} <span class="sub">vs baca {sm}</span>'))
    if derau:
        out.append('<h3>Derau — pola menilai jauh di atas bacaan manusia. '
                   'Ini boleh, dan memang sudah diduga.</h3>')
        for d, nama, sp, sm in derau:
            out.append(baris(esc(nama)[:26], isi(min(abs(d), 100), OKER),
                             f'pola {sp} <span class="sub">vs baca {sm}</span>'))
    return "\n".join(out), lolos


def bagian_penolakan(con):
    """Skor tinggi yang justru TIDAK boleh ditelepon.

    Lihat Aturan 3 di rubrik.py. Ditampilkan terpisah karena inilah
    satu-satunya bagian dashboard yang kerugiannya jatuh ke orang:
    antrian diurutkan dari skor tertinggi, dan orang sales menelepon
    dari atas.
    """
    if not tabel_ada(con, "kebutuhan"):
        return "", None
    tolak = []
    for nama, need, fit, catatan in con.execute(
            "SELECT nama, need_score, industry_fit, COALESCE(catatan,'') "
            "FROM kebutuhan ORDER BY need_score DESC"):
        alasan = rubrik.tandai_penolakan(need, fit, catatan)
        if alasan:
            tolak.append((need, nama, alasan))
    if not tolak:
        return "", None
    out = [f'<h2>{len(tolak)} perusahaan bernilai tinggi yang JANGAN '
           f'ditelepon</h2>',
           '<p class="sub">Skornya tidak salah — rubrik memang mengukur '
           '"punya operasi lapangan tersebar", dan mereka punya. Yang salah '
           'adalah menyimpulkan skor tinggi berarti boleh ditelepon.</p>']
    for need, nama, alasan in tolak:
        out.append(
            f'<div class="row" title="{esc(alasan)}">'
            f'<div class="lbl">{esc(nama)[:26]}</div>'
            f'<div class="track"><div class="fill" style="width:{need}%;'
            f'background:{MERAH}"></div></div>'
            f'<div class="val">{need}'
            f'<span class="tag tolak">tolak</span></div></div>')
    return "\n".join(out), len(tolak)


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
    html_saring, n_lolos = bagian_penyaring(c)
    html_tolak, n_tolak = bagian_penolakan(c)
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
    if n_tolak:
        kartu.append(("Jangan telepon", n_tolak, "#FBE9E7", "#B3261E", "#5C1410"))
    kartu_html = "\n".join(
        f'<div class="c" style="background:{bg}"><p class="k" style="color:{c1}">{k}</p>'
        f'<p class="v" style="color:{c2}">{v}</p></div>'
        for k, v, bg, c1, c2 in kartu)

    fase2 = "\n".join(x for x in [html_panen, html_saring, html_kebutuhan,
                                  html_tolak, html_kontak] if x)

    html = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard — salesmart-leadgen</title>
<style>{CSS}</style></head><body><div class="wrap">

<h1>salesmart-leadgen</h1>
<p class="meta">Dashboard teknis — kesehatan pipeline, dibuat otomatis dari data/leads.db<br>
Untuk daftar lead siap telepon, lihat <a href="./" style="color:#185FA5">Antrian Lead</a>.</p>

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

<div class="note blokir">
<b>Yang sedang menghambat pipeline: izin BPS</b>
<ul>
<li>Direktori Industri Manufaktur BPS (~31.795 perusahaan) adalah sumber data berikutnya, tapi terbitannya melarang reproduksi <b>untuk tujuan komersial</b> tanpa izin tertulis.</li>
<li>Permohonan izin dikirim lewat e-PPID BPS <b>1 September 2026</b>. <b>Pemberitahuan Tertulis No. 202609007 sudah datang 2 September</b> &mdash; dalam 1 hari kerja, bukan 10.</li>
<li><b>Jawabannya bukan penolakan, tapi juga bukan izin.</b> Bagian "informasi tidak dapat diberikan" kosong seluruhnya, tapi tiga hal yang ditanyakan surat &mdash; izin komersial, mekanisme pembelian data, dan ketentuan mana yang berlaku saat T&amp;C laman bertentangan dengan larangan di dalam terbitan &mdash; tak satu pun dijawab. Kata "izin", "komersial", dan "reproduksi" tidak muncul sama sekali; isinya pengalihan ke Pelayanan Statistik Terpadu (pst.bps.go.id).</li>
<li>Pertanyaan izin dikirim ulang ke <b>PST</b> &mdash; kanal yang BPS tunjuk sendiri &mdash; 2 September 15:47 WIB, <b>ID Transaksi #50964</b>.</li>
<li><b>PST menjawab 3 September 08:57 WIB, dan jawabannya pertanyaan balik:</b> "seperti apa susunan daftar calon pelanggan produk software yang ingin dikomersialkan?" Bukan penolakan &mdash; yang mereka timbang adalah bentuk penggunaannya. Frasanya menyiratkan <i>daftarnya</i> yang dijual; itu salah baca yang harus diluruskan lebih dulu, karena menjual daftar nama-alamat = menjual kembali isi publikasi, sedangkan memakainya untuk menelepon calon pelanggan produk sendiri = penggunaan internal. Draf jawaban di <code>surat/jawaban-pst-50964.md</code>, <b>tenggat balas 8 September 2026</b> (ditutup otomatis setelah 3 hari kerja).</li>
<li>Larangan di halaman keterangan terbitan <b>masih berdiri utuh</b>. Cadangan kalau PST tetap buntu: keberatan ke PPID atas dasar UU 14/2008 Pasal 35 ayat (1) huruf e, tenggat ~15 Oktober 2026.</li>
<li>Sampai izin itu ada, PDF-nya <b>tidak disentuh</b> dan tidak ada pengekstrak yang dibangun. Lihat <code>CATATAN_SUMBER_DATA.md</code>.</li>
<li>Panen otomatis dari bps.go.id tetap tertutup permanen &mdash; robots.txt mereka menyebut ClaudeBot secara harfiah.</li>
</ul>
</div>

<div class="note">
<b>Cara membaca angka-angka ini</b>
<ul>
<li>Kategori spesifik jauh mengalahkan generik: <b>consulting 60%</b> vs <b>company 12%</b> cakupan telepon.</li>
<li>Denpasar menghasilkan entri terbanyak tapi teleponnya paling sedikit — banyak belum tentu berkualitas.</li>
<li>145 duplikat lolos dedup berbasis ID karena <b>PT. Bakti Mandiri Perkasa</b> dan <b>PT BAKTI MANDIRI PERKASA</b> punya osm_id berbeda dengan telepon sama.</li>
<li>Batang pendek di peringkat kebutuhan (Traveloka, Tokopedia) adalah perusahaan besar yang <b>tidak</b> punya tim sales lapangan — tidak cocok untuk Salesmart.</li>
<li>Panjang batang di peringkat kebutuhan menunjukkan <b>komposisinya</b>, bukan cuma totalnya. Gojek dan Erajaya nilainya mirip tapi susunannya kebalikan.</li>
<li><b>Nomor dari OSM tidak bisa dipercaya untuk menelepon.</b> Dari 6 lead tegak yang nomornya diverifikasi ke situs resmi 2 Sep, <b>4 berbeda</b> &mdash; PT. Erela (lead nomor 1) tercatat 024-7477557 di OSM tapi 024-8310650 di situsnya; BERCA tercatat kode area Semarang tapi kantornya menjawab di Jakarta; Multi Guna Maritim tercatat Jakarta tapi situsnya Banjarmasin. Nomor OSM layak jadi petunjuk, bukan jadi nomor yang ditelepon.</li>
<li><b>Skor tinggi bukan izin menelepon.</b> Smart GPS Bandung (55) pesaing langsung, AirNav (55) punya 299 kantor tapi isinya petugas ATC. Keduanya kini ditandai otomatis &mdash; lihat bagian "JANGAN ditelepon" di atas.</li>
<li><b>Penyaring pola sengaja longgar.</b> Balon Tepuk sempat dapat skor pola 95 (ternyata "Depo" adalah potongan kata "DEPOK" di halaman SEO kota) dan gugur jadi 0 waktu dibaca. Derau seperti itu diterima; yang tidak diterima adalah lead bagus yang tersaring keluar.</li>
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
    ada = [n for n, x in [("panen", html_panen), ("penyaring", html_saring),
                          ("kebutuhan", html_kebutuhan), ("penolakan", html_tolak),
                          ("kontak", html_kontak), ("need", html_need)] if x]
    print(f"Bagian yang tampil: {', '.join(ada)}")
    print("Buka dengan klik dua kali file itu di File Explorer.")


if __name__ == "__main__":
    main()
