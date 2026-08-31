"""
buat_antrian.py
===============
Hasilkan docs/antrian.html - dashboard untuk ORANG SALES, bukan untuk yang
membangun pipeline.

BEDANYA DENGAN buat_dashboard.py:
    docs/index.html menjawab "pipeline-nya sehat tidak?" - sebaran kota,
    cakupan telepon per kategori, berapa duplikat terbuang. Itu telemetri,
    berguna buat yang mengerjakan.

    File ini menjawab pertanyaan yang berbeda sama sekali:
    "siapa yang saya telepon sekarang, dan apa kalimat pembuka saya?"

    Jadi tidak ada satu pun angka telemetri di sini.

YANG JADI JANTUNGNYA BUKAN SKOR, TAPI KUTIPAN:
    Daftar lead biasa cuma memberi nama dan nomor. Halaman ini menunjukkan
    kalimat yang perusahaan itu tulis sendiri di situsnya - misalnya
    "jaringan distribusi berskala nasional... melalui SNS ke seluruh pelosok
    Indonesia". Orang sales yang menelepon dengan kalimat itu di tangan
    tidak sedang menelepon dingin.

    Karena itu kutipan ditaruh di baris utama, bukan disembunyikan di detail.

REKOMENDASI TINDAKAN DIAMBIL DARI rubrik.py:
    tentukan_aksi() sudah menghasilkan "hubungi_sekarang",
    "cari_nomor_kantor", "arsipkan" - itu persis bahasa yang dibutuhkan orang
    sales. Jadi itulah tulang punggung tampilan ini, bukan angka skornya.

Jalankan ulang setiap data berubah:
    python src/buat_antrian.py
"""

import csv
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import rubrik

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "leads.db"
CSV_SKOR = BASE / "data" / "companies_scored.csv"
OUT = BASE / "docs" / "antrian.html"

BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]

# Tiap tindakan dari rubrik.py dipetakan ke kelompok warna + label pendek.
AKSI = {
    "hubungi_sekarang":        ["siap",  "Telepon sekarang"],
    "hubungi_nanti":           ["siap",  "Antrian kedua"],
    "verifikasi_lalu_hubungi": ["perlu", "Cek nomor dulu"],
    "cari_nomor_kantor":       ["perlu", "Cari jalur kantor"],
    "cari_nomor":              ["perlu", "Cari nomor"],
    "arsipkan":                ["arsip", "Arsipkan"],
}

POLA_CALL_CENTER = re.compile(r"^(1500|0804|0800|62804|62800)")


def kualitas(kelas, telepon):
    """Terjemahkan kelas kontak ke istilah yang dipakai rubrik.py."""
    if kelas == "langsung":
        return "langsung_resmi"
    if kelas == "seluler":
        return "langsung_lain"
    if kelas == "layanan":
        return "call_center"
    if telepon:
        digit = re.sub(r"\D", "", telepon)
        return "call_center" if POLA_CALL_CENTER.match(digit) else "langsung_lain"
    return "tidak_ada"


def tabel_ada(con, nama):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nama,)).fetchone())


def kumpulkan():
    """Gabungkan penilaian bukti, hasil enrichment kontak, dan riset manual."""
    con = sqlite3.connect(DB)

    kontak = {}
    if tabel_ada(con, "kontak_web"):
        kontak = {r[0]: {"telepon": r[1], "kelas": r[2]}
                  for r in con.execute(
                      "SELECT nama, telepon, kelas_kontak FROM kontak_web")}

    # Telepon lead OSM ikut dipakai - sebagian sudah punya nomor dari OSM
    # sendiri, jadi sayang kalau tidak dimanfaatkan.
    osm = {}
    for n, p in con.execute(
            "SELECT name, phone FROM leads WHERE phone IS NOT NULL AND phone != ''"):
        osm.setdefault(n.strip(), p)

    lead = []
    dinilai = set()
    if tabel_ada(con, "kebutuhan"):
        for r in con.execute(
                "SELECT nama, dist_model, field_sales, scale, industry_fit, "
                "need_score, rincian, catatan, bukti_kuat, status_nilai "
                "FROM kebutuhan"):
            nama = r[0]
            dinilai.add(nama)
            rincian = json.loads(r[6])
            k = kontak.get(nama, {})
            telepon = k.get("telepon") or osm.get(nama)
            aksi, saran = rubrik.tentukan_aksi(
                r[5], kualitas(k.get("kelas"), telepon))
            lead.append({
                "nama": nama, "sumber": "bukti situs", "need": r[5],
                "dist": r[1], "field": r[2], "scale": r[3], "fit": r[4],
                "telepon": telepon, "kelas": k.get("kelas"),
                "aksi": aksi, "saran": saran, "catatan": r[7],
                "tegak": r[9] == "nilai_tegak", "bukti_kuat": r[8],
                "bukti": [{"komponen": kk, "label": v["label"],
                           "kutipan": v["kutipan"], "yakin": v["keyakinan"]}
                          for kk, v in rincian.items() if v["kutipan"]],
            })
    con.close()

    # Riset manual, untuk yang belum pernah dinilai dari bukti.
    if CSV_SKOR.exists():
        for r in csv.DictReader(open(CSV_SKOR, encoding="utf-8")):
            nama = r["company_name"]
            if nama in dinilai:
                continue
            need = sum(int(r[x]) for x in
                       ["dist_model", "field_sales", "scale", "industry_fit"])
            telepon = r["phone"] if r["phone"] not in ("NOT_FOUND", "") else None
            # legitimacy_score adalah penilaian Anda sendiri soal seberapa
            # terverifikasi datanya. hitung_prioritas.py sudah memakai 60
            # sebagai gerbang, jadi ambang yang sama dipakai di sini:
            # di atasnya dianggap jalur resmi, di bawahnya perlu dicek dulu.
            q = kualitas(None, telepon)
            if q == "langsung_lain" and int(r.get("legitimacy_score", 0)) >= 60:
                q = "langsung_resmi"
            aksi, saran = rubrik.tentukan_aksi(need, q)
            lead.append({
                "nama": nama, "sumber": "riset manual", "need": need,
                "dist": int(r["dist_model"]), "field": int(r["field_sales"]),
                "scale": int(r["scale"]), "fit": int(r["industry_fit"]),
                "telepon": telepon,
                "kelas": "langsung" if q == "langsung_resmi" else
                         ("layanan" if q == "call_center" else None),
                "aksi": aksi, "saran": saran, "catatan": r.get("need_notes", ""),
                "tegak": True, "bukti_kuat": 4, "bukti": [],
            })

    lead.sort(key=lambda x: -x["need"])
    return lead


HEAD = '<title>Antrian Lead Salesmart</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">\n<style>\n:root{\n  --kertas:#FAFAF7; --permukaan:#FFFFFF; --permukaan2:#F2F2EC; --garis:#E6E5DD;\n  --garis2:#CFCEC3; --tinta:#16201B; --tinta2:#4E5A53; --tinta3:#8B958D;\n  --merek:#14584E; --merek-lembut:#E2EFEA;\n  --siap:#1B7F4F; --siap-lembut:#E4F2E9;\n  --perlu:#A8620A; --perlu-lembut:#F7EEE1;\n  --arsip:#8B958D; --arsip-lembut:#EFEFEA;\n  --k1:#0F4A42; --k2:#1C7A6B; --k3:#5BA99A; --k4:#A9CFC6;\n  --logo-ink:#FAFAF7;\n  --bayang:0 1px 2px rgba(22,32,27,.05), 0 10px 28px -16px rgba(22,32,27,.22);\n}\n@media (prefers-color-scheme: dark){\n  :root:not([data-theme="light"]){\n    --kertas:#0E1311; --permukaan:#161C19; --permukaan2:#1E2521; --garis:#293029;\n    --garis2:#3D463E; --tinta:#E7ECE8; --tinta2:#AFB9B2; --tinta3:#7F8A83;\n    --merek:#5CC0A8; --merek-lembut:#122B26;\n    --siap:#4FBF8B; --siap-lembut:#12271C;\n    --perlu:#D9A24E; --perlu-lembut:#2A2114;\n    --arsip:#7F8A83; --arsip-lembut:#1D231F;\n    --k1:#CFEAE2; --k2:#8FCBBC; --k3:#4E9C8B; --k4:#2C5F55;\n    --logo-ink:#0E1311;\n    --bayang:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -16px rgba(0,0,0,.7);\n  }\n}\n:root[data-theme="dark"]{\n  --kertas:#0E1311; --permukaan:#161C19; --permukaan2:#1E2521; --garis:#293029;\n  --garis2:#3D463E; --tinta:#E7ECE8; --tinta2:#AFB9B2; --tinta3:#7F8A83;\n  --merek:#5CC0A8; --merek-lembut:#122B26;\n  --siap:#4FBF8B; --siap-lembut:#12271C;\n  --perlu:#D9A24E; --perlu-lembut:#2A2114;\n  --arsip:#7F8A83; --arsip-lembut:#1D231F;\n  --k1:#CFEAE2; --k2:#8FCBBC; --k3:#4E9C8B; --k4:#2C5F55;\n  --logo-ink:#0E1311;\n  --bayang:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -16px rgba(0,0,0,.7);\n}\n*{box-sizing:border-box}\nbody{background:var(--kertas);color:var(--tinta);\n  font-family:"Plus Jakarta Sans",ui-sans-serif,system-ui,-apple-system,sans-serif;\n  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}\n.app{max-width:1060px;margin:0 auto;padding:0 20px 80px}\n\n.kepala{padding:34px 0 22px}\n.merek{display:flex;align-items:center;gap:10px;margin-bottom:20px}\n.logo{width:26px;height:26px;border-radius:7px;background:var(--merek);\n  display:grid;place-items:center;color:var(--logo-ink);font-weight:700;font-size:13px;flex:none}\n.merek b{font-size:15px;font-weight:700;letter-spacing:-.01em}\n.merek span{color:var(--tinta3);font-size:13px}\nh1{font-size:clamp(1.6rem,4vw,2.05rem);font-weight:700;letter-spacing:-.025em;\n  margin:0 0 6px;line-height:1.15;text-wrap:balance}\n.sub{color:var(--tinta2);margin:0;max-width:54ch;font-size:.95rem}\n\n.ringkas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));\n  gap:1px;background:var(--garis);border:1px solid var(--garis);\n  border-radius:12px;overflow:hidden;margin:26px 0 0}\n.rk{background:var(--permukaan);padding:16px 18px}\n.rk .k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:600;margin-bottom:5px}\n.rk .v{font-family:"IBM Plex Mono",monospace;font-size:1.75rem;font-weight:600;\n  line-height:1;font-variant-numeric:tabular-nums}\n.rk .n{font-size:.78rem;color:var(--tinta3);margin-top:4px}\n\n.saring{position:sticky;top:0;z-index:5;background:var(--kertas);\n  padding:18px 0 14px;margin-top:26px;border-bottom:1px solid var(--garis);\n  display:flex;flex-wrap:wrap;gap:8px;align-items:center}\n.chip{font:inherit;font-size:.83rem;font-weight:600;padding:7px 14px;border-radius:999px;\n  border:1px solid var(--garis2);background:var(--permukaan);color:var(--tinta2);\n  cursor:pointer;display:inline-flex;align-items:center;gap:7px;transition:border-color .12s}\n.chip:hover{border-color:var(--tinta3)}\n.chip:focus-visible{outline:2px solid var(--merek);outline-offset:2px}\n.chip[aria-pressed="true"]{background:var(--merek);border-color:var(--merek);color:var(--logo-ink)}\n.chip .jml{font-family:"IBM Plex Mono",monospace;font-size:.76rem;opacity:.75}\n\n.daftar{margin-top:18px;display:flex;flex-direction:column;gap:9px}\n.lead{background:var(--permukaan);border:1px solid var(--garis);border-radius:12px;\n  overflow:hidden;box-shadow:var(--bayang)}\n.lead.siap{border-left:3px solid var(--siap)}\n.lead.perlu{border-left:3px solid var(--perlu)}\n.lead.arsip{border-left:3px solid var(--arsip)}\n.baris{width:100%;background:none;border:0;font:inherit;color:inherit;\n  text-align:left;cursor:pointer;padding:15px 18px;display:grid;\n  grid-template-columns:1fr auto;gap:10px 18px;align-items:start}\n.baris:hover{background:var(--permukaan2)}\n.baris:focus-visible{outline:2px solid var(--merek);outline-offset:-2px}\n.kiri{min-width:0}\n.nama{font-weight:600;font-size:1rem;letter-spacing:-.01em;display:flex;\n  align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}\n.pil{font-family:"IBM Plex Mono",monospace;font-size:.7rem;font-weight:500;\n  padding:2px 8px;border-radius:5px;letter-spacing:.02em;white-space:nowrap}\n.pil.siap{background:var(--siap-lembut);color:var(--siap)}\n.pil.perlu{background:var(--perlu-lembut);color:var(--perlu)}\n.pil.arsip{background:var(--arsip-lembut);color:var(--arsip)}\n.pil.lantai{background:var(--perlu-lembut);color:var(--perlu);border:1px dashed var(--perlu)}\n.aksi-teks{font-size:.86rem;color:var(--tinta2);margin-bottom:6px}\n.kutip{font-size:.83rem;color:var(--tinta3);line-height:1.5;font-style:italic;\n  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}\n.kanan{display:flex;align-items:center;gap:16px;flex:none}\n.skor{text-align:right}\n.skor .angka{font-family:"IBM Plex Mono",monospace;font-size:1.5rem;font-weight:600;\n  line-height:1;font-variant-numeric:tabular-nums}\n.skor .lbl{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:600;margin-top:3px}\n.komp{display:flex;gap:2px;height:7px;width:96px;border-radius:4px;margin-top:7px}\n.komp i{display:block;border-radius:2px}\n.komp i.k1{background:var(--k1)}\n.komp i.k2{background:var(--k2)}\n.komp i.k3{background:var(--k3)}\n.komp i.k4{background:var(--k4)}\n.panah{color:var(--tinta3);font-size:.8rem;transition:transform .15s;flex:none}\n.lead.buka .panah{transform:rotate(90deg)}\n\n.rinci{display:none;padding:0 18px 18px;border-top:1px solid var(--garis)}\n.lead.buka .rinci{display:block}\n.rinci h4{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:700;margin:18px 0 9px}\n.kontak{display:flex;flex-wrap:wrap;gap:9px;align-items:center}\n.tel{font-family:"IBM Plex Mono",monospace;font-size:1rem;font-weight:600;\n  color:var(--merek);text-decoration:none;padding:7px 13px;border-radius:8px;\n  background:var(--merek-lembut);display:inline-flex;align-items:center;gap:8px}\n.tel:hover{text-decoration:underline}\n.tel.mati{color:var(--tinta3);background:var(--permukaan2)}\n.bukti-item{border-left:2px solid var(--garis2);padding:2px 0 2px 13px;margin-bottom:11px}\n.bukti-komp{font-family:"IBM Plex Mono",monospace;font-size:.73rem;\n  color:var(--tinta3);margin-bottom:3px}\n.bukti-komp b{color:var(--tinta2);font-weight:600}\n.bukti-teks{font-size:.86rem;color:var(--tinta2);line-height:1.55}\n.nanti{background:var(--permukaan2);border:1px dashed var(--garis2);border-radius:9px;\n  padding:13px 15px;font-size:.85rem;color:var(--tinta3);line-height:1.5}\n.nanti b{color:var(--tinta2)}\n.kosong{text-align:center;padding:56px 20px;color:var(--tinta3)}\n\n.kaki{margin-top:38px;padding:18px 20px;background:var(--permukaan2);\n  border:1px solid var(--garis);border-radius:12px;font-size:.84rem;\n  color:var(--tinta2);line-height:1.6}\n.kaki b{color:var(--tinta)}\n.tautan{margin-left:auto;font-size:.82rem;font-weight:600;color:var(--merek);text-decoration:none}\n.tautan:hover{text-decoration:underline}\n.kaki code{font-family:"IBM Plex Mono",monospace;font-size:.9em}\n@media (max-width:640px){\n  .baris{grid-template-columns:1fr}\n  .kanan{justify-content:space-between;width:100%}\n  .komp{width:120px}\n}\n@media (prefers-reduced-motion:reduce){*{transition:none!important}}\n</style>\n'

BODY = '<div class="app">\n  <header class="kepala">\n    <div class="merek">\n      <span class="logo">S</span>\n      <b>Salesmart</b><span>&middot;</span><span>Pencari Lead</span><a class="tautan" href="index.html">Dashboard teknis &rarr;</a>\n    </div>\n    <h1>Antrian lead hari ini</h1>\n    <p class="sub">Perusahaan yang bukti di situsnya sendiri menunjukkan mereka punya\n    tim sales lapangan dan jaringan distribusi &mdash; diurutkan dari yang paling butuh.</p>\n    <div class="ringkas" id="ringkas"></div>\n  </header>\n\n  <div class="saring" id="saring" role="group" aria-label="Saring berdasarkan tindakan"></div>\n  <div class="daftar" id="daftar"></div>\n\n  <div class="kaki">\n    <b>Pratinjau tampilan.</b> Semua angka, nomor, dan kutipan di halaman ini data nyata\n    dari pipeline per __TANGGAL__ &mdash; tidak ada yang dikarang. Jumlahnya masih __JML__\n    perusahaan karena penilai AI belum dijalankan; tata letaknya dirancang untuk ratusan.\n    Rekomendasi tindakan dihitung <code>rubrik.py</code>, memadukan seberapa butuh\n    perusahaan itu dengan apakah nomornya bisa dipakai menghubungi pengambil keputusan.\n  </div>\n</div>\n\n'

SCRIPT = '\n(function(){\n  "use strict";\n  var LEADS = __DATA__;\n  var AKSI = __AKSI__;\n  var KOMP = [["dist","Model distribusi"],["field","Tim sales lapangan"],\n              ["scale","Skala operasi"],["fit","Kecocokan industri"]];\n  var saringAktif = "aktif";\n\n  function grup(l){ return AKSI[l.aksi][0]; }\n\n  function hitung(){\n    var n = {semua:LEADS.length, aktif:0, siap:0, perlu:0, arsip:0};\n    LEADS.forEach(function(l){\n      var g = grup(l);\n      n[g]++;\n      if (g !== "arsip") { n.aktif++; }\n    });\n    return n;\n  }\n\n  function ringkas(){\n    var n = hitung();\n    var siapTel = LEADS.filter(function(l){ return grup(l) === "siap" && l.telepon; }).length;\n    var tegak = LEADS.filter(function(l){ return l.tegak; }).length;\n    var kartu = [\n      ["Siap ditelepon", siapTel, "punya nomor jalur kantor"],\n      ["Perlu dilengkapi", n.perlu, "butuh nomor atau verifikasi"],\n      ["Nilai tegak", tegak, "bukti cukup untuk dipercaya"],\n      ["Total lead", n.semua, "dari pipeline sejauh ini"]\n    ];\n    document.getElementById("ringkas").innerHTML = kartu.map(function(k){\n      return \'<div class="rk"><div class="k">\' + k[0] + \'</div><div class="v">\' +\n             k[1] + \'</div><div class="n">\' + k[2] + \'</div></div>\';\n    }).join("");\n  }\n\n  function chips(){\n    var n = hitung();\n    var d = [["aktif","Perlu ditindak",n.aktif],["siap","Siap ditelepon",n.siap],\n             ["perlu","Perlu dilengkapi",n.perlu],["arsip","Arsip",n.arsip],\n             ["semua","Semua",n.semua]];\n    document.getElementById("saring").innerHTML = d.map(function(x){\n      return \'<button class="chip" type="button" data-f="\' + x[0] + \'" aria-pressed="\' +\n             (x[0] === saringAktif) + \'">\' + x[1] +\n             \' <span class="jml">\' + x[2] + \'</span></button>\';\n    }).join("");\n  }\n\n  function labelKelas(k){\n    if (k === "langsung") { return "jalur kantor"; }\n    if (k === "layanan")  { return "call center"; }\n    if (k === "seluler")  { return "nomor HP"; }\n    return "belum jelas";\n  }\n\n  function render(){\n    var wadah = document.getElementById("daftar");\n    var tampil = LEADS.filter(function(l){\n      var g = grup(l);\n      if (saringAktif === "semua") { return true; }\n      if (saringAktif === "aktif") { return g !== "arsip"; }\n      return g === saringAktif;\n    });\n\n    if (!tampil.length){\n      wadah.innerHTML = \'<div class="kosong">Tidak ada lead di saringan ini.</div>\';\n      return;\n    }\n\n    wadah.innerHTML = tampil.map(function(l){\n      var g = grup(l);\n      var seg = KOMP.map(function(k, j){\n        return l[k[0]] > 0 ? \'<i class="k\' + (j+1) + \'" style="flex:\' + l[k[0]] + \' 1 0"></i>\' : \'\';\n      }).join("");\n      var kutip = l.bukti.length\n        ? \'<div class="kutip">\\u201C\' + l.bukti[0].kutipan + \'\\u201D</div>\'\n        : \'<div class="kutip">\' + (l.catatan || "") + \'</div>\';\n      var pilLantai = l.tegak ? \'\'\n        : \'<span class="pil lantai">bukti \' + l.bukti_kuat + \'/4</span>\';\n\n      var rinciBukti = l.bukti.length\n        ? l.bukti.map(function(b){\n            var judul = b.komponen;\n            KOMP.forEach(function(k){\n              if (b.komponen.indexOf(k[0]) === 0) { judul = k[1]; }\n            });\n            return \'<div class="bukti-item"><div class="bukti-komp"><b>\' + judul +\n              \'</b> &middot; \' + b.label + \' &middot; keyakinan \' + b.yakin +\n              \'</div><div class="bukti-teks">\\u201C\' + b.kutipan + \'\\u201D</div></div>\';\n          }).join("")\n        : \'<div class="bukti-teks">\' + (l.catatan || "Belum ada kutipan.") + \'</div>\';\n\n      var tel = l.telepon\n        ? \'<a class="tel" href="tel:\' + l.telepon.replace(/[^0-9+]/g, "") + \'">\' +\n          l.telepon + \'</a><span class="pil \' +\n          (l.kelas === "langsung" ? "siap" : "perlu") + \'">\' + labelKelas(l.kelas) + \'</span>\'\n        : \'<span class="tel mati">Nomor belum ada</span>\';\n\n      return \'<article class="lead \' + g + \'">\' +\n        \'<button class="baris" type="button" aria-expanded="false">\' +\n          \'<div class="kiri">\' +\n            \'<div class="nama">\' + l.nama + pilLantai + \'</div>\' +\n            \'<div class="aksi-teks">\' + l.saran + \'</div>\' + kutip +\n          \'</div>\' +\n          \'<div class="kanan">\' +\n            \'<div class="skor"><div class="angka">\' + l.need + \'</div>\' +\n              \'<div class="lbl">butuh</div><div class="komp">\' + seg + \'</div></div>\' +\n            \'<span class="panah" aria-hidden="true">&#9654;</span>\' +\n          \'</div>\' +\n        \'</button>\' +\n        \'<div class="rinci">\' +\n          \'<h4>Hubungi</h4><div class="kontak">\' + tel + \'</div>\' +\n          \'<h4>Kenapa perusahaan ini butuh Salesmart</h4>\' + rinciBukti +\n          \'<h4>Pembuka percakapan</h4>\' +\n          \'<div class="nanti"><b>Belum aktif.</b> Nanti disusun otomatis oleh penilai AI \' +\n            \'dari kutipan di atas &mdash; supaya telepon pertama tidak terdengar dingin.</div>\' +\n          \'<h4>Sumber</h4><div class="bukti-teks">\' + l.sumber + \' &middot; skor \' +\n            l.need + \'/100 &middot; \' +\n            (l.tegak ? \'bukti cukup\' : \'bukti \' + l.bukti_kuat + \'/4, angka ini lantai\') +\n          \'</div>\' +\n        \'</div>\' +\n      \'</article>\';\n    }).join("");\n  }\n\n  document.addEventListener("click", function(e){\n    var chip = e.target.closest(".chip");\n    if (chip){ saringAktif = chip.dataset.f; chips(); render(); return; }\n    var b = e.target.closest(".baris");\n    if (b){\n      var buka = b.parentNode.classList.toggle("buka");\n      b.setAttribute("aria-expanded", buka ? "true" : "false");\n    }\n  });\n\n  ringkas(); chips(); render();\n})();\n'


def main():
    if not DB.exists():
        print("Database tidak ada: " + str(DB))
        raise SystemExit(1)

    lead = kumpulkan()
    if not lead:
        print("Belum ada lead yang bisa ditampilkan.")
        print("Jalankan panen_bukti.py lalu nilai_kebutuhan.py dulu.")
        raise SystemExit(1)

    hari = date.today()
    tanggal = str(hari.day) + " " + BULAN[hari.month] + " " + str(hari.year)

    isi = BODY.replace("__JML__", str(len(lead))).replace("__TANGGAL__", tanggal)
    js = (SCRIPT.replace("__DATA__", json.dumps(lead, ensure_ascii=False))
                .replace("__AKSI__", json.dumps(AKSI, ensure_ascii=False)))

    html = ('<!DOCTYPE html>\n<html lang="id"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            + HEAD + "</head><body>\n" + isi
            + "<script>\n" + js + "\n</script>\n</body></html>")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    import collections
    n = collections.Counter(AKSI[x["aksi"]][0] for x in lead)
    print("Antrian lead dibuat: " + str(OUT))
    print("  %d lead  |  siap %d   perlu %d   arsip %d"
          % (len(lead), n["siap"], n["perlu"], n["arsip"]))
    print("Buka dengan klik dua kali file itu di File Explorer.")


if __name__ == "__main__":
    main()
