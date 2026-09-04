"""
lembar_telepon.py
=================
Satu halaman untuk orang yang benar-benar MENELEPON. Lokal, tidak terbit.

KENAPA MODUL INI ADA:
    4 Sep 2026, `data/leads.db` dikeluarkan dari git dan `publik.klausa()`
    mulai menahan lead berasal-BPS dari `docs/index.html`. Itu benar --
    halaman itu tayang di GitHub Pages, dan menerbitkan baris berasal-BPS
    di sana adalah penerbitan kembali yang BPS larang.

    Tapi akibatnya: 16 lead yang dinilai hari itu TIDAK TERLIHAT SIAPA PUN,
    termasuk orang yang harus meneleponnya. Lead terbaik yang pernah
    dipunya proyek ini -- 95 dari 100, dengan jalur kantor langsung --
    ada di database dan tidak ada di layar siapa-siapa.

    `buat_antrian.py --lengkap` menutup separuh masalah: ia memuat semua
    lead. Tapi ia halaman PANTAU -- 109 baris, termasuk arsip dan yang
    ditolak, disusun untuk menilai keadaan pipeline.

    Berkas ini menutup separuhnya lagi. Isinya HANYA yang bisa ditelepon,
    disusun untuk dipakai sambil menempelkan telepon di kuping: nomor
    yang bisa diklik, kalimat pembuka yang sudah ada kutipannya, dan apa
    yang harus dipastikan saat menelepon.

KENAPA INI TIDAK MELANGGAR GARIS BPS:
    BPS menjawab 3 Sep 2026 bahwa nama dan alamat perusahaan BOLEH
    dimanfaatkan; yang dilarang adalah reproduksi/penerbitan kembali
    publikasinya. Memakai daftar untuk menelepon calon pelanggan produk
    sendiri adalah penggunaan internal -- persis yang Bryan sampaikan ke
    PST, dan persis yang dibedakan surat itu dari "menjual daftarnya".

    Karena itu berkas ini ditulis ke `kerja/` yang di-gitignore, dan
    fungsi tulisnya MENOLAK menulis ke `docs/`. Penjaga itu sama dengan
    yang dipasang di `buat_antrian.bangun()`, dan alasannya sama: aturan
    yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa ada
    yang sengaja melanggarnya.

Pakai:
    python src/lembar_telepon.py
    python src/lembar_telepon.py --keluar kerja/lembar-telepon.html
"""

import argparse
import sys
from datetime import date
from html import escape as esc
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import buat_antrian as ba  # noqa: E402

KELUAR = BASE / "kerja" / "lembar-telepon.html"

# Hanya tindakan yang berarti "angkat telepon". `cari_nomor*` sengaja
# TIDAK masuk: orang yang sedang menelepon tidak bisa berbuat apa-apa
# dengan lead yang belum punya nomor, dan mencampurnya membuat lembar
# ini berhenti bisa dipercaya sebagai daftar-yang-bisa-ditelepon.
AKSI_TELEPON = ("hubungi_sekarang", "hubungi_nanti", "verifikasi_lalu_hubungi")

# Kelas nomor -> peringatan yang perlu dibaca SEBELUM memencet.
PERINGATAN_KELAS = {
    "seluler": "Nomor SELULER, bukan jalur kantor resmi — biasanya WA "
               "sekretariat. Perkenalkan diri lebih dulu.",
    "layanan": "Nomor LAYANAN KONSUMEN, bukan jalur kantor. Minta "
               "disambungkan ke bagian penjualan atau kantor pusat.",
    "cabang":  "Nomor CABANG, bukan kantor pusat. Minta nomor atau "
               "sambungan ke kantor pusat sebelum menawarkan apa pun.",
}


def rapikan_telepon(digit: str) -> str:
    """62216122040 -> (021) 6122040. Bentuk yang dibaca orang."""
    d = (digit or "").strip()
    if not d.startswith("62"):
        return d
    sisa = d[2:]
    for panjang in (3, 2):                      # kode area 3 lalu 2 digit
        if len(sisa) > panjang + 5:
            return f"(0{sisa[:panjang]}) {sisa[panjang:]}"
    return "0" + sisa


HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lembar Telepon Salesmart</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
:root{
  --kertas:#FBFAF7; --panel:#FFFFFF; --tinta:#1A1D22; --tinta2:#565C66;
  --tinta3:#878E99; --garis:#E4E2DC; --garis2:#CFCCC4;
  --aksen:#1F5F4B; --aksen-lembut:#E4EFEA;
  --hati:#8A5A12; --hati-lembut:#F6EEDD;
  --bps:#4A4468; --bps-lembut:#ECE9F4;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --kertas:#14161A; --panel:#1B1E24; --tinta:#EBEDF0; --tinta2:#A8AEB8;
  --tinta3:#787F8A; --garis:#2A2E36; --garis2:#3C424D;
  --aksen:#63C39F; --aksen-lembut:#12291F;
  --hati:#D9A63F; --hati-lembut:#2A2313;
  --bps:#A9A0D6; --bps-lembut:#221F30;
}}
:root[data-theme="dark"]{
  --kertas:#14161A; --panel:#1B1E24; --tinta:#EBEDF0; --tinta2:#A8AEB8;
  --tinta3:#787F8A; --garis:#2A2E36; --garis2:#3C424D;
  --aksen:#63C39F; --aksen-lembut:#12291F;
  --hati:#D9A63F; --hati-lembut:#2A2313;
  --bps:#A9A0D6; --bps-lembut:#221F30;
}
*{box-sizing:border-box}
body{background:var(--kertas);color:var(--tinta);margin:0;
  font-family:"IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;
  font-size:15.5px;line-height:1.6;-webkit-font-smoothing:antialiased}
.bingkai{max-width:900px;margin:0 auto;padding:34px 20px 80px}
.kop{border-bottom:2px solid var(--tinta);padding-bottom:14px;
  display:flex;justify-content:space-between;align-items:baseline;
  gap:16px;flex-wrap:wrap}
h1{font-size:1.6rem;font-weight:600;margin:0;letter-spacing:-.015em}
.mono{font-family:"IBM Plex Mono",monospace}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--tinta3)}
.catatan-atas{margin:14px 0 0;color:var(--tinta2);font-size:.93rem;max-width:70ch}
.catatan-atas b{color:var(--tinta)}

.grup{margin-top:34px}
.grup-judul{display:flex;align-items:baseline;gap:10px;
  border-bottom:1px solid var(--garis2);padding-bottom:7px}
.grup-judul h2{font-size:1.06rem;font-weight:600;margin:0}
.grup-judul .n{font-family:"IBM Plex Mono",monospace;font-size:.85rem;
  color:var(--tinta3)}

.lead{background:var(--panel);border:1px solid var(--garis);
  margin-top:12px;padding:16px 18px 18px}
.lead.utama{border-left:3px solid var(--aksen)}
.lead.hati{border-left:3px solid var(--hati)}
.atas{display:flex;justify-content:space-between;align-items:flex-start;
  gap:16px;flex-wrap:wrap}
.nama{font-size:1.08rem;font-weight:600;letter-spacing:-.01em;
  display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.pil{font-family:"IBM Plex Mono",monospace;font-size:10px;font-weight:600;
  letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;
  border-radius:3px;background:var(--bps-lembut);color:var(--bps)}
.skor{font-family:"IBM Plex Mono",monospace;font-size:1.45rem;font-weight:600;
  line-height:1;font-variant-numeric:tabular-nums;color:var(--aksen)}
.skor small{display:block;font-size:9.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--tinta3);font-weight:600;
  margin-top:3px;text-align:right;font-family:"IBM Plex Sans",sans-serif}
.tel{display:inline-flex;align-items:center;gap:9px;margin-top:12px;
  font-family:"IBM Plex Mono",monospace;font-size:1.24rem;font-weight:600;
  color:var(--aksen);text-decoration:none;background:var(--aksen-lembut);
  padding:8px 14px;border-radius:4px;letter-spacing:.01em}
.tel:hover{text-decoration:underline}
.tel:focus-visible{outline:2px solid var(--aksen);outline-offset:2px}
.awas{margin-top:10px;background:var(--hati-lembut);color:var(--hati);
  border-radius:4px;padding:9px 12px;font-size:.89rem;line-height:1.5}
.saran{margin-top:10px;font-size:.93rem;color:var(--tinta2)}
h3{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--tinta3);font-weight:600;margin:18px 0 8px;
  font-family:"IBM Plex Mono",monospace}
.titik{list-style:none;margin:0;padding:0;display:flex;
  flex-direction:column;gap:11px}
.titik li{display:grid;grid-template-columns:auto 1fr;gap:11px;
  align-items:start}
.titik .tanda{width:6px;height:6px;border-radius:50%;background:var(--aksen);
  margin-top:8px}
.titik .lemah .tanda{background:var(--hati)}
.titik .apa{font-size:.95rem}
.titik .kutip{display:block;color:var(--tinta2);font-size:.87rem;
  font-style:italic;margin-top:3px;line-height:1.5}
.pastikan{margin-top:14px;border-top:1px dashed var(--garis2);padding-top:11px;
  font-size:.9rem;color:var(--tinta2)}
.pastikan b{color:var(--tinta)}
.kaki{margin-top:44px;border-top:1px solid var(--garis);padding-top:16px;
  font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--tinta3);
  line-height:1.8}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
/* CETAK / SIMPAN-JADI-PDF.
   Seluruh palet dipaksa balik ke terang, bukan cuma latar body. Kalau
   hanya body yang dipaksa putih, peramban yang sedang bermode gelap
   tetap memakai --tinta terang -> tulisan putih di atas kertas putih,
   dan PDF-nya kosong. Ini jalur yang dipakai orang untuk mengirim
   lembar ini lewat WhatsApp, jadi ia harus benar. */
@media print{
  :root{
    --kertas:#FFFFFF; --panel:#FFFFFF; --tinta:#111111; --tinta2:#444444;
    --tinta3:#666666; --garis:#CCCCCC; --garis2:#999999;
    --aksen:#14503E; --aksen-lembut:#EDF4F1;
    --hati:#7A4E0C; --hati-lembut:#F7F0E2;
    --bps:#3D3859; --bps-lembut:#EEECF5;
  }
  body{background:#fff}
  .lead{break-inside:avoid; border:1px solid #CCC}
  .grup{break-before:auto}
  /* Nomor tidak bisa diklik di kertas, jadi ia harus terbaca sebagai
     angka biasa, bukan tombol. */
  .tel{background:none;padding:0;font-size:1.15rem}
  .kop{border-bottom:2px solid #111}
}
</style>"""


def blok_lead(l: dict) -> str:
    _, label = ba.AKSI[l["aksi"]]
    kelas = (l.get("kelas") or "").lower()
    awas = PERINGATAN_KELAS.get(kelas)
    h = [f'<article class="lead {"hati" if awas else "utama"}">']

    h.append('<div class="atas"><div>')
    pil = ('<span class="pil">dari direktori BPS &mdash; jangan disalin '
           'ke berkas yang terbit</span>'
           if str(l.get("asal", "")).lower().startswith("bps") else "")
    h.append(f'<div class="nama">{esc(l["nama"])}{pil}</div>')
    h.append(f'<div class="eyebrow" style="margin-top:4px">{esc(label)}</div>')
    h.append('</div>')
    h.append(f'<div class="skor">{l["need"]}<small>skor</small></div>')
    h.append('</div>')

    tel = l.get("telepon") or ""
    h.append(f'<a class="tel" href="tel:+{esc(tel)}">'
             f'{esc(rapikan_telepon(tel))}</a>')
    if awas:
        h.append(f'<div class="awas">{esc(awas)}</div>')
    if l.get("saran"):
        h.append(f'<div class="saran">{esc(l["saran"])}</div>')

    buka = l.get("buka") or {}
    titik = [t for t in (buka.get("titik") or []) if t.get("sorot")]
    if titik:
        h.append("<h3>Kenapa mereka butuh ini</h3><ul class=\"titik\">")
        for t in titik:
            lemah = ' class="lemah"' if t.get("lemah") else ""
            h.append(f'<li{lemah}><span class="tanda"></span><span class="apa">'
                     f'{esc(t.get("teks") or "")}'
                     f'<span class="kutip">&ldquo;{esc(t["sorot"])}&rdquo;</span>'
                     f'</span></li>')
        h.append("</ul>")

    pastikan = buka.get("pastikan") or []
    if pastikan:
        h.append('<div class="pastikan"><b>Pastikan saat menelepon:</b> '
                 + esc("; ".join(str(p) for p in pastikan)) + "</div>")
    elif buka.get("kait"):
        h.append('<div class="pastikan"><b>Kaitnya:</b> '
                 + esc(str(buka["kait"])) + "</div>")

    h.append("</article>")
    return "\n".join(h)


def bangun(keluar: Path = None) -> int:
    keluar = keluar or KELUAR
    # Penjaga yang sama dengan buat_antrian.bangun(): lembar ini memuat
    # lead berasal-BPS, dan docs/ tayang lewat GitHub Pages.
    if "docs" in keluar.parts:
        raise SystemExit(
            "DITOLAK: lembar telepon memuat lead berasal-BPS dan tidak "
            "boleh ditulis ke docs/ — folder itu terbit lewat GitHub Pages.")

    semua = ba.kumpulkan(saring=False)
    lead = [l for l in semua if l["aksi"] in AKSI_TELEPON and l.get("telepon")]

    # Asal usul diambil dari DATABASE, bukan dari dict antrian: `sumber`
    # di sana berarti "dari mana buktinya" (bukti situs / riset manual),
    # bukan dari kolam mana namanya datang. Penanda BPS harus jujur --
    # orang yang memegang lembar ini perlu tahu baris mana yang tidak
    # boleh ia salin ke tempat yang terbit.
    import sqlite3
    con = sqlite3.connect(f"file:{BASE / 'data' / 'leads.db'}?mode=ro", uri=True)
    asal = dict(con.execute("SELECT nama, COALESCE(asal,'') FROM kebutuhan"))
    con.close()
    for l in lead:
        l["asal"] = asal.get(l["nama"], "")
    lead.sort(key=lambda l: (-l["need"], l["nama"]))
    if not lead:
        print("Belum ada lead yang bisa ditelepon.")
        raise SystemExit(1)

    urut = {"hubungi_sekarang": ("Telepon sekarang", 0),
            "hubungi_nanti": ("Antrian kedua", 1),
            "verifikasi_lalu_hubungi": ("Cek nomornya dulu", 2)}
    hari = date.today()
    tgl = f"{hari.day} {ba.BULAN[hari.month]} {hari.year}"

    h = [HEAD, "<div class=\"bingkai\">",
         '<header class="kop"><div>',
         "<h1>Lembar Telepon Salesmart</h1>",
         f'<div class="eyebrow" style="margin-top:5px">{len(lead)} lead siap '
         f'dihubungi &middot; {esc(tgl)}</div></div>',
         '<div class="eyebrow">berkas kerja &mdash; tidak terbit</div>',
         "</header>",
         '<p class="catatan-atas">Urut menurut skor kebutuhan. Tiap kutipan '
         'diambil verbatim dari situs perusahaan itu sendiri dan sudah lewat '
         'pemeriksa adversarial &mdash; <b>boleh dibacakan apa adanya</b> '
         'kalau lawan bicara bertanya dari mana kita tahu.</p>']

    for aksi, (judul, _) in sorted(urut.items(), key=lambda x: x[1][1]):
        kelompok = [l for l in lead if l["aksi"] == aksi]
        if not kelompok:
            continue
        h.append(f'<section class="grup"><div class="grup-judul">'
                 f'<h2>{esc(judul)}</h2>'
                 f'<span class="n">{len(kelompok)} lead</span></div>')
        h += [blok_lead(l) for l in kelompok]
        h.append("</section>")

    h.append('<div class="kaki">'
             'Dibuat src/lembar_telepon.py &middot; sumber data/leads.db<br>'
             'Berkas ini memuat lead berasal-BPS dan SENGAJA tidak terbit: '
             'memakai daftar untuk menelepon calon pelanggan adalah '
             'penggunaan internal, menerbitkannya bukan.<br>'
             'Kalau nomor ternyata salah sambung, catat dan hapus dari '
             'kontak_web &mdash; jangan diperbaiki dengan tebakan.'
             "</div></div>")

    keluar.parent.mkdir(parents=True, exist_ok=True)
    keluar.write_text("\n".join(h), encoding="utf-8")
    print(f"Lembar telepon: {keluar}")
    for aksi, (judul, _) in sorted(urut.items(), key=lambda x: x[1][1]):
        n = sum(1 for l in lead if l["aksi"] == aksi)
        if n:
            print(f"  {judul:<20} {n}")
    print(f"  {'TOTAL':<20} {len(lead)}")
    return len(lead)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keluar", default="", help="jalur keluaran HTML")
    args = ap.parse_args()
    bangun(Path(args.keluar) if args.keluar else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
