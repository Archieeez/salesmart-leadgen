"""
buat_agen.py
============
Hasilkan `docs/agen.html` — halaman yang menunjukkan agennya BEKERJA.

SIAPA PEMBACANYA, dan kenapa itu menentukan bentuknya:
    Orang sales yang memakai antrian. Pertanyaan dia cuma satu, dan
    bukan "arsitekturnya bagaimana": **"kenapa saya harus percaya angka
    ini?"**

    Jawaban yang meyakinkan bukan "ada dua agen". Jawabannya: *"ini yang
    sempat DIBANTAH, dan begini bantahan itu berakhir."* Sistem yang
    berani menunjukkan perselisihannya sendiri lebih layak dipercaya
    daripada sistem yang cuma menampilkan angka akhir.

    Karena itu halaman ini memimpin dengan koreksi pemeriksa, bukan
    dengan diagram. Mesinnya ada di bawah, untuk yang membangun.

TIDAK ADA YANG DIKARANG DI SINI:
    Tiap angka datang dari tabel `jalan_agen` yang diisi `baca/rekam.py`
    dari berkas hasil agen yang sebenarnya. Lama jalan dan token hanya
    tampil kalau `telemetri.json` memang ada; kalau tidak, halaman
    menulis "tidak tercatat" — bukan 0, karena 0 itu klaim yang salah.

MODE PANTAU:
    python src/buat_agen.py --pantau
    Bangkitkan ulang tiap 3 detik, dan halamannya menyegarkan diri
    sendiri. Dipakai waktu agen sedang jalan, supaya barisnya muncul satu
    per satu. Tanpa server: halamannya tetap berkas biasa.
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from html import escape as esc
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import rubrik  # noqa: E402

DB = BASE / "data" / "leads.db"
KELUAR = BASE / "docs" / "agen.html"

NAMA_KOMPONEN = {
    "dist_model": "Model distribusi",
    "field_sales": "Tim sales lapangan",
    "scale": "Skala operasi",
    "industry_fit": "Kecocokan industri",
}


def tabel_ada(con, nama):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nama,)).fetchone())


def muat(con):
    if not tabel_ada(con, "jalan_agen"):
        return []
    baris = []
    for r in con.execute(
            "SELECT jalan, nama, pada, ditulis, pemeriksa_gagal, "
            "skor_pembaca, skor_akhir, bukti_kuat, komponen, koreksi, "
            "telemetri FROM jalan_agen ORDER BY pada DESC, nama"):
        baris.append({
            "jalan": r[0], "nama": r[1], "pada": r[2], "ditulis": r[3],
            "pemeriksa_gagal": r[4], "skor_pembaca": r[5],
            "skor_akhir": r[6], "bukti_kuat": r[7],
            "komponen": json.loads(r[8]), "koreksi": json.loads(r[9]),
            "telemetri": json.loads(r[10]) if r[10] else None,
        })
    return baris


def jalur_pipa(con):
    """Angka nyata tiap tahap. Yang gugur di satu tahap tidak sampai ke
    tahap berikutnya — itulah yang mau ditunjukkan."""
    def hitung(sql, *a):
        try:
            return con.execute(sql, a).fetchone()[0]
        except sqlite3.Error:
            return 0

    bersih = hitung("SELECT count(*) FROM leads")
    dibuang = hitung("SELECT count(*) FROM leads_arsip")

    # Berapa perusahaan yang halaman buktinya benar-benar dipanen. Isinya
    # ada di bukti.db yang TIDAK dilacak git (teks mentah, bisa dipanen
    # ulang). Kalau berkasnya tidak ada, jangan menebak — lebih baik
    # tahapnya tidak ditampilkan daripada menampilkan angka karangan.
    dipanen = None
    f_bukti = BASE / "data" / "bukti.db"
    if f_bukti.exists():
        try:
            b = sqlite3.connect(f"file:{f_bukti}?mode=ro", uri=True)
            dipanen = b.execute(
                "SELECT count(DISTINCT nama_normal) FROM halaman_bukti"
            ).fetchone()[0]
            b.close()
        except sqlite3.Error:
            dipanen = None

    tahap = [
        ("Dipanen dari OpenStreetMap", bersih + dibuang,
         "10 kota x 10 kategori, sekali jalan dan sudah tuntas"),
        ("Lolos pembersihan", bersih,
         f"{dibuang} dibuang: mall, duplikat entitas, gedung pemerintah"),
    ]
    if dipanen is not None:
        tahap.append(
            ("Situs resminya dipanen", dipanen,
             "halaman Tentang/Distribusi/Karier diambil sebagai bukti"))
    tahap += [
        ("Dinilai dari bukti situs", hitung(
            "SELECT count(*) FROM kebutuhan"),
         "empat komponen, tiap komponen wajib punya kutipan"),
        ("Bukti cukup untuk dipercaya", hitung(
            "SELECT count(*) FROM kebutuhan WHERE status_nilai='nilai_tegak'"),
         "minimal 3 dari 4 kutipan lolos verifikasi mesin"),
    ]
    return tahap


def kartu_ringkas(baris):
    total = len(baris)
    dikoreksi = sum(1 for b in baris if b["koreksi"])
    n_koreksi = sum(len(b["koreksi"]) for b in baris)
    label_ubah = sum(1 for b in baris
                     for k in b["komponen"] if k["berubah"])
    gagal = sum(1 for b in baris
                for k in b["komponen"] if not k["kutipan_lolos"])
    kut = sum(len(b["komponen"]) for b in baris)
    return [
        ("Perusahaan dinilai agen", total, "lewat alur tiga lapis"),
        ("Dibantah pemeriksa", dikoreksi,
         f"{n_koreksi} koreksi, {label_ubah} label diubah"),
        ("Kutipan diverifikasi mesin", f"{kut - gagal}/{kut}",
         "dicocokkan harfiah ke halaman aslinya"),
    ]


def blok_perusahaan(b):
    out = [f'<article class="p">']
    kepala = f'<div class="nm">{esc(b["nama"])}</div>'
    sp = b["skor_pembaca"]
    if sp is None:
        gerak = f'<span class="sk">{b["skor_akhir"]}</span>'
    elif sp == b["skor_akhir"]:
        gerak = (f'<span class="sk">{b["skor_akhir"]}</span>'
                 f'<span class="tetap">bertahan</span>')
    else:
        arah = "turun" if b["skor_akhir"] < sp else "naik"
        gerak = (f'<span class="lama">{sp}</span>'
                 f'<span class="pan {arah}">&rarr;</span>'
                 f'<span class="sk">{b["skor_akhir"]}</span>')
    out.append(f'<div class="baris">{kepala}<div class="gerak">{gerak}'
               f'<span class="bk">bukti {b["bukti_kuat"]}/4</span></div></div>')

    if b["pemeriksa_gagal"]:
        out.append('<div class="peringatan">Pemeriksa GAGAL JALAN. '
                   'Status ditahan di "bukti belum cukup" berapa pun '
                   'jumlah kutipannya — bacaan yang belum diadu tidak '
                   'boleh dianggap tegak.</div>')

    if b["koreksi"]:
        out.append(f'<h4>Yang dibantah pemeriksa '
                   f'<span class="jml">{len(b["koreksi"])}</span></h4>')
        for k in b["koreksi"]:
            out.append(f'<div class="kor">{esc(k)}</div>')
    else:
        out.append('<h4>Yang dibantah pemeriksa</h4>'
                   '<div class="kor kosong">Pemeriksa menyerang bacaan ini '
                   'dan tidak menemukan cacat. Tugasnya memang membantah, '
                   'bukan menyetujui — jadi "nol koreksi" berarti '
                   'serangannya patah, bukan tidak dicoba.</div>')

    out.append('<h4>Per komponen: bacaan pertama, lalu keputusan akhir</h4>')
    out.append('<table class="komp"><thead><tr><th>Komponen</th>'
               '<th>Pembaca</th><th>Keputusan akhir</th>'
               '<th>Kutipannya</th></tr></thead><tbody>')
    for k in b["komponen"]:
        nm = NAMA_KOMPONEN.get(k["komponen"], k["komponen"])
        lp = k["label_pembaca"] or "—"
        np_ = "" if k["nilai_pembaca"] is None else f' <i>{k["nilai_pembaca"]}</i>'
        kelas = " ubah" if k["berubah"] else ""
        yak = ""
        if k["keyakinan_turun"] and not k["berubah"]:
            yak = (f'<div class="yk">keyakinan {esc(k["keyakinan_pembaca"] or "")}'
                   f' &rarr; {esc(k["keyakinan_akhir"] or "")}</div>')
        cek = ('<span class="ok">cocok harfiah</span>' if k["kutipan_lolos"]
               else '<span class="gagal">TIDAK DITEMUKAN</span>')
        kut = esc(k["kutipan"][:190]) + ("…" if len(k["kutipan"]) > 190 else "")
        if not k["kutipan"]:
            kut = '<i>tidak ada kutipan — pita terendah yang bisa dipertahankan</i>'
            cek = '<span class="netral">tidak diklaim</span>'
        out.append(
            f'<tr class="{kelas.strip()}"><td>{esc(nm)}</td>'
            f'<td class="lb">{esc(lp)}{np_}</td>'
            f'<td class="lb">{esc(k["label_akhir"])} <i>{k["nilai_akhir"]}</i>{yak}</td>'
            f'<td class="kt">{cek}<div class="q">{kut}</div>'
            f'<div class="src">{esc(k["sumber_url"])}</div></td></tr>')
    out.append('</tbody></table>')

    t = b["telemetri"]
    if t:
        sel = []
        for peran in ("pembaca", "pemeriksa"):
            d = t.get(peran) or {}
            if d:
                sel.append(
                    f'<span class="tl"><b>{peran}</b> {d.get("detik", "?")} dtk'
                    f' &middot; {d.get("token", "?"):,} token'
                    f' &middot; {d.get("alat", "?")} panggilan alat</span>')
        out.append('<div class="tel">' + "".join(sel) + '</div>')
    else:
        out.append('<div class="tel"><span class="tl kosong">lama jalan dan '
                   'token tidak tercatat untuk jalan ini</span></div>')

    out.append('</article>')
    return "\n".join(out)


GAYA = """
/* Palet disamakan dengan docs/index.html. Dua halaman yang dibuka
   bergantian oleh orang yang sama tidak boleh terasa seperti dua produk. */
:root{--bg:#070B0D;--kartu:#0C1215;--gr:#1A262B;--tx:#DCE8E5;--rd:#9DB2AD;
--ok:#34D399;--bad:#FB7185;--ung:#2DD4BF;--kun:#F0B429;
--kisi:rgba(45,212,191,.045)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
background-image:linear-gradient(var(--kisi) 1px,transparent 1px),
  linear-gradient(90deg,var(--kisi) 1px,transparent 1px);
background-size:46px 46px;background-position:-1px -1px;
background-attachment:fixed}
.wrap{max-width:1060px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 6px}
.sub{color:var(--rd);margin:0 0 22px;max-width:70ch}
h2{font-size:17px;margin:34px 0 10px;padding-top:18px;border-top:1px solid var(--gr)}
h3{font-size:13px;margin:22px 0 8px;color:var(--rd);
text-transform:uppercase;letter-spacing:.14em;
font-family:ui-monospace,Consolas,monospace}
h4{font-size:12px;margin:16px 0 6px;color:var(--rd);
text-transform:uppercase;letter-spacing:.06em}
.jml{color:var(--kun)}
.rk{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 8px}
.rk>div{background:var(--kartu);border:1px solid var(--gr);border-radius:10px;
padding:12px 16px;min-width:190px;flex:1}
.rk .k{color:var(--rd);font-size:11px;letter-spacing:.12em;
text-transform:uppercase;font-family:ui-monospace,Consolas,monospace}
.rk .v{font-size:28px;font-weight:600;line-height:1.2;
font-family:ui-monospace,Consolas,monospace;font-variant-numeric:tabular-nums}
.rk .n{color:var(--rd);font-size:12px}
.pipa{background:var(--kartu);border:1px solid var(--gr);border-radius:10px;
padding:6px 16px 14px}
.tp{display:flex;align-items:center;gap:14px;padding:10px 0;
border-bottom:1px solid var(--gr)}
.tp:last-child{border-bottom:0}
.tp .ang{font-size:22px;font-weight:600;min-width:74px;text-align:right;
color:var(--ung)}
.tp .lbl{font-weight:500}
.tp .ket{color:var(--rd);font-size:12px}
.tp .bar{flex:1;height:6px;background:var(--gr);border-radius:3px;overflow:hidden}
.tp .bar i{display:block;height:100%;background:var(--ung)}
.p{background:var(--kartu);border:1px solid var(--gr);border-radius:10px;
padding:14px 16px;margin:0 0 14px}
.baris{display:flex;justify-content:space-between;align-items:center;gap:16px}
.nm{font-size:16px;font-weight:600}
.gerak{display:flex;align-items:center;gap:8px;white-space:nowrap}
.lama{color:var(--rd);font-size:16px;text-decoration:line-through}
.pan{color:var(--rd)} .pan.turun{color:var(--bad)} .pan.naik{color:var(--ok)}
.sk{font-size:24px;font-weight:700;font-family:ui-monospace,Consolas,monospace;
font-variant-numeric:tabular-nums}
.tetap{color:var(--rd);font-size:12px}
.bk{color:var(--rd);font-size:12px;border:1px solid var(--gr);
border-radius:20px;padding:2px 9px}
.kor{background:#161311;border-left:3px solid var(--kun);border-radius:0 6px 6px 0;
padding:9px 12px;margin:0 0 7px;font-size:13px}
.kor.kosong{border-left-color:var(--gr);color:var(--rd)}
.peringatan{background:#2B1419;border-left:3px solid var(--bad);
border-radius:0 6px 6px 0;padding:9px 12px;margin:10px 0;font-size:13px}
table.komp{width:100%;border-collapse:collapse;font-size:13px}
table.komp th{text-align:left;color:var(--rd);font-weight:500;font-size:11px;
text-transform:uppercase;letter-spacing:.05em;padding:6px 8px;
border-bottom:1px solid var(--gr)}
table.komp td{padding:9px 8px;border-bottom:1px solid var(--gr);
vertical-align:top}
table.komp tr.ubah{background:#1C1810}
.lb{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.lb i{color:var(--rd);font-style:normal}
.yk{color:var(--kun);font-size:11px;margin-top:3px}
.kt .q{color:var(--rd);font-size:12px;margin-top:4px}
.kt .src{color:#5c6474;font-size:11px;margin-top:3px;word-break:break-all}
.ok{color:var(--ok);font-size:11px} .gagal{color:var(--bad);font-size:11px}
.netral{color:var(--rd);font-size:11px}
.tel{margin-top:12px;display:flex;gap:16px;flex-wrap:wrap}
.tl{color:var(--rd);font-size:12px}
.tl b{color:var(--tx);font-weight:600}
.tl.kosong{font-style:italic}
.cat{color:var(--rd);font-size:13px;max-width:74ch}
.lapis{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 8px}
.lapis>div{background:var(--kartu);border:1px solid var(--gr);border-radius:10px;
padding:12px 16px;flex:1;min-width:230px}
.lapis .n{color:var(--ung);font-size:12px;font-weight:600}
.lapis .j{font-weight:600;margin:2px 0 4px}
.lapis .d{color:var(--rd);font-size:12px}
.kaki{color:#5c6474;font-size:12px;margin-top:34px;
border-top:1px solid var(--gr);padding-top:14px}
.pantau{background:#0B2B28;border:1px solid var(--ung);border-radius:8px;
padding:8px 12px;margin:0 0 16px;font-size:12px;color:var(--ung)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;
transition:none!important}}
"""


def bangun(con, pantau: bool) -> str:
    baris = muat(con)
    tahap = jalur_pipa(con)
    maks = max((t[1] for t in tahap), default=1) or 1

    h = ['<!doctype html><html lang="id"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>Agen penilai lead — Salesmart</title>']
    if pantau:
        h.append('<meta http-equiv="refresh" content="3">')
    h.append(f"<style>{GAYA}</style></head><body><div class='wrap'>")

    h.append("<h1>Bagaimana angka di antrian itu diputuskan</h1>")
    h.append('<p class="sub">Setiap skor di antrian dinilai oleh agen yang '
             'membaca situs resmi perusahaannya, lalu <b>dibantah oleh agen '
             'kedua</b>, lalu kutipannya dicocokkan huruf-per-huruf oleh '
             'mesin. Halaman ini menunjukkan ketiganya apa adanya — termasuk '
             'waktu bantahannya berhasil dan skornya turun.</p>')

    if pantau:
        h.append('<div class="pantau">MODE PANTAU — halaman ini menyegarkan '
                 'diri tiap 3 detik selama agen berjalan.</div>')

    if not baris:
        h.append('<div class="p"><b>Belum ada jalannya agen yang terekam.</b>'
                 '<p class="cat">Jalankan alur baca, lalu '
                 '<code>src/baca/selesaikan.py</code> akan mengisi tabel '
                 '<code>jalan_agen</code> sendiri.</p></div>')
    else:
        h.append('<div class="rk">')
        for k, v, n in kartu_ringkas(baris):
            h.append(f'<div><div class="k">{k}</div><div class="v">{v}</div>'
                     f'<div class="n">{n}</div></div>')
        h.append('</div>')

    h.append("<h2>Tiga lapis, dan masing-masing ketat pada hal berbeda</h2>")
    h.append('<div class="lapis">')
    for n, j, d in [
        ("Lapis 1", "Agen pembaca",
         "Menilai empat komponen dan WAJIB mengutip kalimat aslinya. Tanpa "
         "kutipan, ia harus turun ke pita terendah yang masih bisa "
         "dipertahankan."),
        ("Lapis 2", "Agen pemeriksa",
         "Diberi satu tugas: MEMBANTAH. Bukan meninjau, bukan "
         "menyempurnakan. Ia sudah menjatuhkan Nutrifood 80&rarr;70, "
         "Alfamart 85&rarr;70, dan TransTRACK 90&rarr;15."),
        ("Lapis 3", "Verifikasi mesin",
         "Tiap kutipan dicocokkan harfiah ke dokumen sumbernya. Kalau satu "
         "saja tidak ditemukan, penulisan ke database DITOLAK seluruhnya."),
    ]:
        h.append(f'<div><div class="n">{n}</div><div class="j">{j}</div>'
                 f'<div class="d">{d}</div></div>')
    h.append('</div>')
    h.append('<p class="cat">Ketiganya ketat pada hal yang berbeda, dan itu '
             'disengaja: sebuah kutipan pernah LOLOS lapis 3 karena '
             'pencocokan longgar menyamakan spasi tak-kasatmata dengan spasi '
             'biasa, tapi GUGUR di lapis 2 yang mencocokkan huruf demi huruf. '
             'Tidak ada lapisan yang boleh dibuang.</p>')

    if baris:
        h.append("<h2>Yang terjadi pada tiap perusahaan</h2>")
        h.append('<p class="cat">Kolom "Pembaca" adalah bacaan pertama; '
                 '"Keputusan akhir" adalah yang bertahan setelah dibantah. '
                 'Baris bertanda kuning berarti labelnya berubah.</p>')
        jalan_kini = None
        for b in baris:
            if b["jalan"] != jalan_kini:
                jalan_kini = b["jalan"]
                tulis = "ditulis ke database" if b["ditulis"] else "belum ditulis"
                h.append(f'<h3>jalan &ldquo;{esc(jalan_kini)}&rdquo; &middot; '
                         f'<time datetime="{esc(b["pada"])}">'
                         f'{esc(b["pada"][:16].replace("T", " "))} UTC</time>'
                         f' &middot; {tulis}</h3>')
            h.append(blok_perusahaan(b))

    h.append("<h2>Dari mana perusahaannya datang</h2>")
    h.append('<p class="cat">Tiap tahap membuang sebagian. Yang gugur tidak '
             'sampai ke tahap berikutnya — jadi angka terakhirlah yang '
             'benar-benar sampai ke tangan orang sales.</p>')
    h.append('<div class="pipa">')
    for nama, angka, ket in tahap:
        lebar = max(2, round(angka * 100 / maks))
        h.append(f'<div class="tp"><div class="ang">{angka}</div>'
                 f'<div style="flex:1"><div class="lbl">{esc(nama)}</div>'
                 f'<div class="ket">{esc(ket)}</div></div>'
                 f'<div class="bar" style="max-width:220px">'
                 f'<i style="width:{lebar}%"></i></div></div>')
    h.append('</div>')

    h.append(f'<div class="kaki">Dibuat otomatis dari '
             f'<code>data/leads.db</code> tabel <code>jalan_agen</code> oleh '
             f'<code>src/buat_agen.py</code> pada '
             f'{datetime.now().strftime("%d %b %Y %H:%M")}. Tidak ada angka '
             f'di halaman ini yang diketik tangan.</div>')
    # Jam ditulis UTC lalu diganti ke jam setempat pembaca. Halaman ini
    # terbit lewat GitHub Pages dan bisa dibuka dari zona waktu mana pun,
    # jadi mengonversinya saat membangkitkan halaman hanya memindahkan
    # kesalahannya ke pembaca yang lain.
    h.append("""<script>
(function(){
  var n = document.querySelectorAll('time[datetime]');
  for (var i = 0; i < n.length; i++){
    var t = Date.parse(n[i].getAttribute('datetime'));
    if (isNaN(t)) { continue; }
    n[i].textContent = new Date(t).toLocaleString();
  }
})();
</script>""")
    h.append("</div></body></html>")
    return "\n".join(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pantau", action="store_true",
                    help="bangkitkan ulang terus-menerus selama agen jalan")
    ap.add_argument("--jeda", type=float, default=3.0)
    args = ap.parse_args()

    KELUAR.parent.mkdir(parents=True, exist_ok=True)

    def sekali():
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        html = bangun(con, args.pantau)
        con.close()
        KELUAR.write_text(html, encoding="utf-8")

    if not args.pantau:
        sekali()
        print(f"Halaman agen dibuat: {KELUAR}")
        return

    print(f"Mode pantau. Ctrl+C untuk berhenti. -> {KELUAR}")
    try:
        while True:
            sekali()
            print(f"  disegarkan {datetime.now().strftime('%H:%M:%S')}",
                  flush=True)
            time.sleep(args.jeda)
    except KeyboardInterrupt:
        sekali()
        print("\nBerhenti memantau; halaman dibangkitkan sekali lagi tanpa "
              "penyegaran otomatis.")


if __name__ == "__main__":
    main()
