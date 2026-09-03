"""
buat_antrian.py
===============
Hasilkan docs/index.html - dashboard untuk ORANG SALES, bukan untuk yang
membangun pipeline.

KENAPA INI YANG JADI index.html:
    Halaman ini terbit publik lewat GitHub Pages, dan yang membukanya
    orang sales. Merekalah yang harus mendarat di URL polos; telemetri
    pipeline bukan halaman depan.

    docs/antrian.html tetap dibuat, tapi isinya cuma pengalih ke ./ —
    tautan itu terlanjur dibagikan sebelum penukaran ini, dan tautan
    yang sudah beredar tidak boleh mati.

BEDANYA DENGAN buat_dashboard.py:
    docs/teknis.html menjawab "pipeline-nya sehat tidak?" - sebaran kota,
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

import argparse
import csv
import json
import re
import sqlite3
from datetime import date, datetime, timezone
import time
from html import escape as esc
from pathlib import Path

import pembuka
import agen_status as ag
import rubrik

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "leads.db"
CSV_SKOR = BASE / "data" / "companies_scored.csv"
OUT = BASE / "docs" / "index.html"
# Pengalih untuk tautan lama yang sudah beredar. Lihat docstring.
OUT_ALIAS = BASE / "docs" / "antrian.html"

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
    # Kelompok tersendiri, BUKAN "arsip". Arsip artinya "tidak layak
    # biayanya"; ini artinya "jangan, meski skornya menggoda". Dibedakan
    # supaya tidak tenggelam di antara 54 baris arsip biasa dan supaya
    # orang sales bisa membuka daftarnya untuk tahu kenapa.
    "jangan_hubungi":          ["tolak", "JANGAN telepon"],
}

POLA_CALL_CENTER = re.compile(r"^(1500|0804|0800|62804|62800)")


def kualitas(kelas, telepon):
    """Terjemahkan kelas kontak ke istilah yang dipakai rubrik.py."""
    if kelas == "langsung":
        return "langsung_resmi"
    # Nomor cabang dari daftar cabang: sah, tapi bukan kantor yang mau
    # dituju. Diperlakukan sama dengan nomor HP -- "cek dulu, baru
    # telepon" -- supaya tidak naik ke prioritas tertinggi diam-diam.
    if kelas in ("seluler", "cabang"):
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

    # DIKUNCI PADA nama_normal, BUKAN nama.
    #
    # Dulu kuncinya nama tampilan, dan itu putus begitu ejaannya beda
    # sedikit saja. PT. Kimia Farma tersimpan sebagai "PT. Kimia Farma
    # Tbk." di kontak_web tapi "PT. Kimia Farma, Tbk." di kebutuhan --
    # beda satu koma. Nomornya ADA di database, tapi antrian menampilkan
    # "cari nomor" dan orang sales tidak pernah melihatnya.
    #
    # Kedua tabel sama-sama ber-PRIMARY KEY nama_normal; tidak ada alasan
    # menyambung lewat kolom yang bebas ditulis manusia.
    kontak = {}
    if tabel_ada(con, "kontak_web"):
        kontak = {r[0]: {"telepon": r[1], "kelas": r[2]}
                  for r in con.execute(
                      "SELECT nama_normal, telepon, kelas_kontak "
                      "FROM kontak_web")}

    # Telepon lead OSM ikut dipakai - sebagian sudah punya nomor dari OSM
    # sendiri, jadi sayang kalau tidak dimanfaatkan.
    osm = {}
    for n, p in con.execute(
            "SELECT name, phone FROM leads WHERE phone IS NOT NULL AND phone != ''"):
        osm.setdefault(n.strip(), p)

    # Nomor dari riset manual (companies_prioritas.csv). Dipakai sebagai
    # cadangan TERAKHIR untuk baris yang sudah pindah ke tabel kebutuhan.
    #
    # KENAPA PERLU: begitu sebuah perusahaan dinilai dari bukti situs,
    # namanya masuk `dinilai` dan cabang riset manual di bawah
    # melewatinya — termasuk melewati nomor teleponnya. TIKI (1500 125)
    # dan Alfamart (1500 959) kehilangan nomornya persis begitu, di
    # detik mereka naik dari tebakan manual jadi penilaian berbukti.
    # Naik mutu penilaian tidak boleh berarti turun mutu data kontak.
    manual_tel = {}
    if CSV_SKOR.exists():
        for r in csv.DictReader(open(CSV_SKOR, encoding="utf-8")):
            t = (r.get("phone") or "").strip()
            if t and t != "NOT_FOUND":
                manual_tel[r["company_name"].strip()] = t

    lead = []
    dinilai = set()
    if tabel_ada(con, "kebutuhan"):
        for r in con.execute(
                "SELECT nama, dist_model, field_sales, scale, industry_fit, "
                "need_score, rincian, catatan, bukti_kuat, status_nilai, "
                "penanda, nama_normal FROM kebutuhan"):
            nama = r[0]
            dinilai.add(nama)
            rincian = json.loads(r[6])
            # Kolom `penanda` baru ada sejak 3 Sep 2026. NULL berarti baris
            # ini dinilai sebelum field booleannya ada, dan rubrik jatuh ke
            # jalur prosa warisan — lihat rubrik.tandai_penolakan().
            penanda = json.loads(r[10]) if r[10] else None
            tolak = rubrik.tandai_penolakan(r[5], r[4], r[7] or "", penanda)
            k = kontak.get(r[11], {})
            telepon = k.get("telepon") or osm.get(nama) or manual_tel.get(nama)
            aksi, saran = rubrik.tentukan_aksi(
                r[5], kualitas(k.get("kelas"), telepon),
                industry_fit=r[4], catatan=r[7] or "", penanda=penanda)
            lead.append({
                "nama": nama, "sumber": "bukti situs", "need": r[5],
                "dist": r[1], "field": r[2], "scale": r[3], "fit": r[4],
                "telepon": telepon, "kelas": k.get("kelas"),
                "aksi": aksi, "saran": saran, "catatan": r[7],
                "tolak": tolak,
                "buka": pembuka.susun(
                    nama, rincian, r[5], r[8], r[9] == "nilai_tegak", tolak),
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
            fit = int(r["industry_fit"])
            catatan = r.get("need_notes", "")
            aksi, saran = rubrik.tentukan_aksi(need, q, industry_fit=fit,
                                               catatan=catatan)
            lead.append({
                "nama": nama, "sumber": "riset manual", "need": need,
                "dist": int(r["dist_model"]), "field": int(r["field_sales"]),
                "scale": int(r["scale"]), "fit": fit,
                "tolak": rubrik.tandai_penolakan(need, fit, catatan),
                # Riset manual tidak menyimpan kutipan per komponen —
                # cuma angka. pembuka.dari_skor() membalik angka itu jadi
                # label lewat rubrik.label_pita(), supaya lead sekelas
                # Wings Group dan Kalbe (keduanya 100, keduanya siap
                # ditelepon) tetap dapat bahan. Semua titik bicaranya
                # otomatis bertanda "perlu dipastikan".
                "buka": pembuka.susun(
                    nama,
                    pembuka.dari_skor({
                        "dist_model": int(r["dist_model"]),
                        "field_sales": int(r["field_sales"]),
                        "scale": int(r["scale"]),
                        "industry_fit": fit,
                    }),
                    need, 4, True,
                    rubrik.tandai_penolakan(need, fit, catatan)),
                "telepon": telepon,
                "kelas": "langsung" if q == "langsung_resmi" else
                         ("layanan" if q == "call_center" else None),
                "aksi": aksi, "saran": saran, "catatan": r.get("need_notes", ""),
                "tegak": True, "bukti_kuat": 4, "bukti": [],
            })

    lead.sort(key=lambda x: -x["need"])
    return lead


HEAD = '<title>Antrian Lead Salesmart</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">\n<style>\n/* Palet TERMINAL GELAP. Satu palet saja, bukan pasangan terang-gelap:\n   halaman ini alat pantau, dan alat pantau tidak berganti wajah\n   menurut setelan sistem. Warna latar dicat eksplisit supaya tidak\n   meminjam warna peramban. */\n:root{\n  --kertas:#070B0D; --permukaan:#0C1215; --permukaan2:#111A1E;\n  --garis:#1A262B; --garis2:#2B3B42;\n  /* Kontras teks sengaja tinggi: orang sales membaca kutipan panjang\n     sambil menelepon. Abu-abu redup yang terlihat elegan di tangkapan\n     layar justru melambatkan orang yang sedang bekerja. */\n  --tinta:#DCE8E5; --tinta2:#9DB2AD; --tinta3:#6B837E;\n  --merek:#2DD4BF; --merek-lembut:#0B2B28;\n  --siap:#34D399; --siap-lembut:#0A2620;\n  --perlu:#F0B429; --perlu-lembut:#2A2110;\n  --arsip:#6B837E; --arsip-lembut:#131C1F;\n  --tolak:#FB7185; --tolak-lembut:#2B1419;\n  --k1:#0E7C6E; --k2:#17A697; --k3:#2DD4BF; --k4:#7FE9DC;\n  --logo-ink:#04090A;\n  --kisi:rgba(45,212,191,.045);\n  --bayang:0 1px 0 rgba(255,255,255,.02), 0 18px 44px -28px rgba(0,0,0,.9);\n}\n*{box-sizing:border-box}\nbody{background:var(--kertas);color:var(--tinta);\n  font-family:"Plus Jakarta Sans",ui-sans-serif,system-ui,-apple-system,sans-serif;\n  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;\n  background-image:linear-gradient(var(--kisi) 1px,transparent 1px),\n    linear-gradient(90deg,var(--kisi) 1px,transparent 1px);\n  background-size:46px 46px;background-position:-1px -1px;\n  background-attachment:fixed}\n.app{max-width:1280px;margin:0 auto;padding:0 20px 80px}\n\n/* HUD: satu baris melintang berisi angka yang paling sering dilirik.\n   Sengaja lengket di atas -- orang sales menggulung daftar panjang dan\n   tetap perlu tahu berapa yang siap ditelepon tanpa naik lagi. */\n.hud{position:sticky;top:0;z-index:30;display:flex;align-items:center;\n  gap:18px;flex-wrap:wrap;padding:9px 20px;margin:0 -20px 2px;\n  background:rgba(7,11,13,.94);backdrop-filter:blur(10px);\n  border-bottom:1px solid var(--garis)}\n.hud-merek{display:flex;align-items:center;gap:9px;flex:none}\n.hud-merek b{font-family:\'IBM Plex Mono\',monospace;font-size:13px;\n  letter-spacing:.16em;font-weight:600}\n.hud-sub{font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;\n  color:var(--tinta3);letter-spacing:.1em}\n.hud-tautan{margin-left:auto;display:flex;gap:6px;flex:none}\n.hud-tautan a{font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;\n  letter-spacing:.12em;color:var(--tinta3);text-decoration:none;\n  border:1px solid var(--garis2);border-radius:5px;padding:4px 9px}\n.hud-tautan a:hover{color:var(--merek);border-color:var(--merek)}\n\n.judul{padding:26px 0 4px}\n\n/* Dua kolom: rel kiri untuk keadaan mesin, kanan untuk pekerjaan.\n   Saringan pindah ke rel supaya tidak lagi memakan satu baris penuh\n   di atas daftar -- dan supaya tetap terlihat sambil menggulung. */\n.konsol{display:grid;grid-template-columns:326px minmax(0,1fr);\n  gap:18px;align-items:start;margin-top:20px}\n/* Rel lengket WAJIB punya batas tinggi dan gulirnya sendiri.\n   Tanpa itu, isi yang lebih tinggi dari layar jadi TIDAK BISA\n   DICAPAI sama sekali: ia menempel di atas dan sisanya menggantung\n   di luar viewport tanpa satu pun cara menggulungnya. Terjadi\n   3 Sep 2026, satu menit setelah layout dua kolom dipasang. */\n.sisi{position:sticky;top:64px;display:flex;flex-direction:column;gap:14px;\n  max-height:calc(100vh - 80px);overflow-y:auto;overscroll-behavior:contain;\n  padding-right:4px;scrollbar-width:thin;\n  scrollbar-color:var(--garis2) transparent}\n.sisi::-webkit-scrollbar{width:7px}\n.sisi::-webkit-scrollbar-thumb{background:var(--garis2);border-radius:4px}\n.sisi::-webkit-scrollbar-track{background:transparent}\n.utama{min-width:0}\n.blok{background:var(--permukaan);border:1px solid var(--garis);\n  border-radius:12px;overflow:hidden}\n.blok-judul{font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;\n  letter-spacing:.14em;text-transform:uppercase;color:var(--tinta3);\n  padding:12px 16px 0}\n@media (max-width:900px){\n  .konsol{grid-template-columns:1fr}\n  .sisi{position:static;max-height:none;overflow:visible;padding-right:0}\n}\n\n.logo{width:26px;height:26px;border-radius:7px;background:var(--merek);\n  display:grid;place-items:center;color:var(--logo-ink);font-weight:700;font-size:13px;flex:none}\n.merek b,.merek span{font-family:\'IBM Plex Mono\',monospace;\n  letter-spacing:.04em}\nh1{font-size:clamp(1.6rem,4vw,2.05rem);font-weight:700;letter-spacing:-.025em;\n  margin:0 0 6px;line-height:1.15;text-wrap:balance}\n.sub{color:var(--tinta2);margin:0;max-width:54ch;font-size:.95rem}\n\n.ringkas{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--garis);\n  border-radius:8px;overflow:hidden;margin:0}\n.rk{background:var(--permukaan);padding:6px 14px;position:relative;\n  border-right:1px solid var(--garis);display:flex;align-items:baseline;\n  gap:8px}\n.rk:last-child{border-right:0}\n.rk:after{content:\'\';position:absolute;left:0;top:0;bottom:0;width:2px;\n  background:var(--merek);opacity:.55}\n.rk.rk-tolak:after{background:var(--tolak)}\n.rk .k{font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:600;font-family:\'IBM Plex Mono\',monospace;\n  order:2}\n.rk .v{font-family:"IBM Plex Mono",monospace;font-size:1.15rem;font-weight:600;\n  line-height:1;font-variant-numeric:tabular-nums;order:1}\n/* Keterangan panjang tiap kartu tidak muat di HUD. Ia tidak dibuang,\n   cuma dipindah ke tooltip -- membuang penjelasan angka berarti\n   membuat angka lebih sulit dipercaya, bukan lebih ringkas. */\n.rk .n{display:none}\n\n.saring{display:flex;flex-direction:column;gap:5px;padding:10px 12px 12px}\n.chip{font:inherit;font-size:.83rem;font-weight:600;padding:8px 12px;border-radius:7px;\n  border:1px solid var(--garis);background:var(--permukaan2);color:var(--tinta2);\n  cursor:pointer;display:flex;align-items:center;justify-content:space-between;\n  gap:7px;width:100%;text-align:left;transition:border-color .12s,color .12s}\n.chip:hover{border-color:var(--tinta3)}\n.chip:focus-visible{outline:2px solid var(--merek);outline-offset:2px}\n.chip[aria-pressed="true"]{background:var(--merek);border-color:var(--merek);color:var(--logo-ink)}\n.chip .jml{font-family:"IBM Plex Mono",monospace;font-size:.76rem;opacity:.75}\n\n.daftar{margin-top:0;display:flex;flex-direction:column;gap:9px;\n  counter-reset:lead}\n.lead{counter-increment:lead}\n/* Nomor urut antrian. Bukan hiasan: orang sales menyebut "nomor 7"\n   waktu bicara dengan rekannya, dan tanpa nomor mereka menyebut\n   nama panjang perusahaan. */\n.nama:before{content:counter(lead,decimal-leading-zero);\n  font-family:\'IBM Plex Mono\',monospace;font-size:.68rem;font-weight:600;\n  color:var(--tinta3);background:var(--permukaan2);border:1px solid var(--garis);\n  border-radius:4px;padding:2px 6px;flex:none}\n.lead{background:var(--permukaan);border:1px solid var(--garis);border-radius:12px;\n  overflow:hidden;box-shadow:var(--bayang);position:relative;\n  transition:border-color .12s}\n.lead:hover{border-color:var(--garis2)}\n.lead:before,.lead:after{content:\'\';position:absolute;width:9px;height:9px;\n  border-color:var(--merek);opacity:0;transition:opacity .12s;pointer-events:none}\n.lead:before{top:5px;right:5px;border-top:1px solid;border-right:1px solid}\n.lead:after{bottom:5px;right:5px;border-bottom:1px solid;border-right:1px solid}\n.lead:hover:before,.lead:hover:after,\n.lead.buka:before,.lead.buka:after{opacity:.7}\n.lead.siap{border-left:3px solid var(--siap)}\n.lead.perlu{border-left:3px solid var(--perlu)}\n.lead.arsip{border-left:3px solid var(--arsip)}\n.lead.tolak{border-left:3px solid var(--tolak)}\n.pil.tolak{background:var(--tolak-lembut);color:var(--tolak);font-weight:700}\n.alasan-tolak{font-size:.84rem;color:var(--tolak);background:var(--tolak-lembut);border-radius:8px;padding:9px 12px;margin-top:7px;line-height:1.5}\n.rk.rk-tolak .v{color:var(--tolak)}\n.baris{width:100%;background:none;border:0;font:inherit;color:inherit;\n  text-align:left;cursor:pointer;padding:15px 18px;display:grid;\n  grid-template-columns:1fr auto;gap:10px 18px;align-items:start}\n.baris:hover{background:var(--permukaan2)}\n.baris:focus-visible{outline:2px solid var(--merek);outline-offset:-2px}\n.kiri{min-width:0}\n.nama{font-weight:600;font-size:1rem;letter-spacing:-.01em;display:flex;\n  align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}\n.pil{font-family:"IBM Plex Mono",monospace;font-size:.7rem;font-weight:500;\n  padding:2px 8px;border-radius:5px;letter-spacing:.02em;white-space:nowrap}\n.pil.siap{background:var(--siap-lembut);color:var(--siap)}\n.pil.perlu{background:var(--perlu-lembut);color:var(--perlu)}\n.pil.arsip{background:var(--arsip-lembut);color:var(--arsip)}\n.pil.lantai{background:var(--perlu-lembut);color:var(--perlu);border:1px dashed var(--perlu)}\n.aksi-teks{font-size:.86rem;color:var(--tinta2);margin-bottom:6px}\n.kutip{font-size:.83rem;color:var(--tinta2);line-height:1.5;font-style:italic;\n  overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}\n.kanan{display:flex;align-items:center;gap:16px;flex:none}\n.skor{text-align:right}\n.skor .angka{font-family:"IBM Plex Mono",monospace;font-size:1.5rem;font-weight:600;\n  line-height:1;font-variant-numeric:tabular-nums}\n.skor .lbl{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:600;margin-top:3px}\n.komp{display:flex;gap:2px;height:7px;width:96px;border-radius:4px;margin-top:7px}\n.komp i{display:block;border-radius:2px}\n.komp i.k1{background:var(--k1)}\n.komp i.k2{background:var(--k2)}\n.komp i.k3{background:var(--k3)}\n.komp i.k4{background:var(--k4)}\n.panah{color:var(--tinta3);font-size:.8rem;transition:transform .15s;flex:none}\n.lead.buka .panah{transform:rotate(90deg)}\n\n.rinci{display:none;padding:0 18px 18px;border-top:1px solid var(--garis)}\n.lead.buka .rinci{display:block}\n.rinci h4{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;\n  color:var(--tinta3);font-weight:700;margin:18px 0 9px}\n.kontak{display:flex;flex-wrap:wrap;gap:9px;align-items:center}\n.tel{font-family:"IBM Plex Mono",monospace;font-size:1rem;font-weight:600;\n  color:var(--merek);text-decoration:none;padding:7px 13px;border-radius:8px;\n  background:var(--merek-lembut);display:inline-flex;align-items:center;gap:8px}\n.tel:hover{text-decoration:underline}\n.tel.mati{color:var(--tinta3);background:var(--permukaan2)}\n.bukti-item{border-left:2px solid var(--garis2);padding:2px 0 2px 13px;margin-bottom:11px}\n.bukti-komp{font-family:"IBM Plex Mono",monospace;font-size:.73rem;\n  color:var(--tinta3);margin-bottom:3px}\n.bukti-komp b{color:var(--tinta2);font-weight:600}\n.bukti-teks{font-size:.88rem;color:var(--tinta);line-height:1.6}\n.nanti{background:var(--permukaan2);border:1px dashed var(--garis2);border-radius:9px;\n  padding:13px 15px;font-size:.85rem;color:var(--tinta3);line-height:1.5}\n.nanti b{color:var(--tinta2)}\n.buka{background:var(--merek-lembut);border-radius:9px;padding:13px 15px}\n.buka > p{margin:0 0 9px;font-size:.86rem;color:var(--tinta2);font-weight:600}\n.buka ul{margin:0;padding-left:17px;list-style:none}\n.buka li{margin-bottom:10px;font-size:.88rem;color:var(--tinta);position:relative}\n.buka li:before{content:'';position:absolute;left:-13px;top:.55em;width:5px;height:5px;\n  border-radius:50%;background:var(--merek)}\n.buka .kutip-kecil{display:block;margin-top:3px;font-size:.82rem;color:var(--tinta2);\n  font-style:italic;line-height:1.45}\n.buka .cek{font-style:normal;font-size:.75rem;color:var(--perlu);\n  background:var(--perlu-lembut);border-radius:4px;padding:1px 6px;margin-left:5px}\n.buka .kait{margin:11px 0 0;padding-top:10px;border-top:1px solid var(--garis2);\n  font-size:.86rem;color:var(--tinta)}\n.buka .pastikan{margin:9px 0 0;font-size:.81rem;color:var(--tinta3);line-height:1.5}\n.agen{margin:22px 0 0;background:var(--permukaan);border:1px solid var(--garis);border-radius:12px;overflow:hidden;box-shadow:var(--bayang);position:relative}\n/* Garis pemindai murni hiasan, jadi ia HANYA menyapu waktu agennya\n   benar-benar bekerja. Hiasan yang bergerak terus akan terbaca\n   sebagai tanda kegiatan, dan itu kebohongan yang sama dengan\n   titik hijau yang menyala terus. */\n.agen.jalan:before{content:\'\';position:absolute;inset:0;pointer-events:none;\n  background:linear-gradient(180deg,transparent,rgba(45,212,191,.10),transparent);\n  height:38%;animation:sapu 4.5s linear infinite}\n@keyframes sapu{0%{transform:translateY(-40%)}100%{transform:translateY(280%)}}\n.agen-kepala{display:flex;align-items:center;gap:11px;padding:14px 18px;border-bottom:1px solid var(--garis)}\n.nadi{width:9px;height:9px;border-radius:50%;flex:none;background:var(--tinta3)}\n.agen.jalan .nadi{background:var(--siap);animation:denyut 1.6s ease-in-out infinite}\n@keyframes denyut{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.72)}}\n.agen-judul{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700;color:var(--tinta3);font-family:\'IBM Plex Mono\',monospace}\n.agen-kini{font-size:.92rem;font-weight:600;color:var(--tinta)}\n.agen.diam .agen-kini{color:var(--tinta2);font-weight:500}\n.agen-catatan{font-size:.74rem;color:var(--tinta3);margin-top:2px}\n.agen-catatan:empty{display:none}\n.agen-sejak{margin-left:auto;font-family:\'IBM Plex Mono\',monospace;font-size:.74rem;color:var(--tinta3);white-space:nowrap}\n.agen-maju{padding:12px 18px;border-bottom:1px solid var(--garis)}\n.agen-maju .lbl{display:flex;justify-content:space-between;font-size:.76rem;color:var(--tinta3);margin-bottom:6px}\n.agen-maju .lbl b{color:var(--tinta2);font-family:\'IBM Plex Mono\',monospace}\n.rel{height:6px;background:var(--permukaan2);border-radius:3px;overflow:hidden}\n.rel i{display:block;height:100%;background:var(--merek);border-radius:3px}\n/* Batas tinggi dilepas. Dulu daftar ini punya gulir sendiri di dalam\n   panel; setelah rel jadi area gulir, dua area bersarang membuat roda\n   tetikus berhenti di daftar ini dan relnya tidak ikut jalan. Satu\n   area gulir saja. */\n.denyut{list-style:none;margin:0;padding:8px 18px 14px}\n.denyut li{display:flex;gap:10px;align-items:baseline;padding:4px 0;font-size:.83rem;color:var(--tinta2)}\n.denyut .jam{font-family:\'IBM Plex Mono\',monospace;font-size:.72rem;color:var(--tinta3);flex:none;white-space:nowrap}\n.denyut .tag{font-family:\'IBM Plex Mono\',monospace;font-size:.66rem;padding:1px 6px;border-radius:4px;flex:none;font-weight:600}\n.tag.panen{background:var(--merek-lembut);color:var(--merek)}\n.tag.kontak{background:var(--perlu-lembut);color:var(--perlu)}\n.tag.nilai{background:var(--siap-lembut);color:var(--siap)}\n.tag.periksa{background:var(--tolak-lembut);color:var(--tolak)}\n.agen-kaki{padding:10px 18px 14px;font-size:.78rem;color:var(--tinta3);line-height:1.5;border-top:1px solid var(--garis)}\n.kosong{text-align:center;padding:56px 20px;color:var(--tinta3)}\n\n.kaki{margin-top:38px;padding:18px 20px;background:var(--permukaan2);\n  border:1px solid var(--garis);border-radius:12px;font-size:.84rem;\n  color:var(--tinta2);line-height:1.6}\n.kaki b{color:var(--tinta)}\n.kaki code{font-family:"IBM Plex Mono",monospace;font-size:.9em}\n@media (max-width:640px){\n  .baris{grid-template-columns:1fr}\n  .kanan{justify-content:space-between;width:100%}\n  .komp{width:120px}\n}\n@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}\n</style>\n'

BODY = '<div class="app">\n  <header class="hud">\n    <div class="hud-merek">\n      <span class="logo">S</span>\n      <b>SALESMART</b><span class="hud-sub">// PENCARI LEAD</span>\n    </div>\n    <div class="ringkas" id="ringkas"></div>\n    <nav class="hud-tautan">\n      <a href="agen.html">AGEN</a><a href="teknis.html">TEKNIS</a>\n    </nav>\n  </header>\n\n  <div class="judul">\n    <h1>Antrian lead hari ini</h1>\n    <p class="sub">Perusahaan yang bukti di situsnya sendiri menunjukkan mereka punya\n    tim sales lapangan dan jaringan distribusi &mdash; diurutkan dari yang paling butuh.</p>\n  </div>\n\n  <div class="konsol">\n    <aside class="sisi">\n      <section class="blok">\n        <div class="blok-judul">Saring antrian</div>\n        <div class="saring" id="saring" role="group" aria-label="Saring berdasarkan tindakan"></div>\n      </section>\n__AGEN__\n    </aside>\n\n    <main class="utama">\n      <div class="daftar" id="daftar"></div>\n    </main>\n  </div>\n\n  <div class="kaki">\n    Semua angka, nomor, dan kutipan di halaman ini data nyata dari pipeline\n    per __TANGGAL__ &mdash; tidak ada yang dikarang. __JML__ perusahaan, dinilai dari\n    bukti yang mereka tulis sendiri di situsnya.\n    Rekomendasi tindakan dihitung <code>rubrik.py</code>, memadukan seberapa butuh\n    perusahaan itu dengan apakah nomornya bisa dipakai menghubungi pengambil keputusan.\n  </div>\n</div>\n\n'

SCRIPT = '\n(function(){\n  "use strict";\n  var LEADS = __DATA__;\n  var AKSI = __AKSI__;\n  var KOMP = [["dist","Model distribusi"],["field","Tim sales lapangan"],\n              ["scale","Skala operasi"],["fit","Kecocokan industri"]];\n  var saringAktif = "aktif";\n\n  function grup(l){ return AKSI[l.aksi][0]; }\n\n  function hitung(){\n    var n = {semua:LEADS.length, aktif:0, siap:0, perlu:0, arsip:0, tolak:0};\n    LEADS.forEach(function(l){\n      var g = grup(l);\n      n[g]++;\n      if (g !== "arsip" && g !== "tolak") { n.aktif++; }\n    });\n    return n;\n  }\n\n  function ringkas(){\n    var n = hitung();\n    var siapTel = LEADS.filter(function(l){ return grup(l) === "siap" && l.telepon; }).length;\n    var tegak = LEADS.filter(function(l){ return l.tegak; }).length;\n    var kartu = [\n      ["Siap ditelepon", siapTel, "punya nomor jalur kantor"],\n      ["Perlu dilengkapi", n.perlu, "butuh nomor atau verifikasi"],\n      ["Nilai tegak", tegak, "bukti cukup untuk dipercaya"],\n      ["Total lead", n.semua, "dari pipeline sejauh ini"]\n    ];\n    if (n.tolak) { kartu.splice(3, 0, ["Jangan telepon", n.tolak, "pesaing atau salah sasaran"]); }\n    document.getElementById("ringkas").innerHTML = kartu.map(function(k){\n      var kls = (k[0] === "Jangan telepon") ? " rk-tolak" : "";\n      // Keterangan tiap angka tidak muat di HUD, tapi TIDAK dibuang: ia\n      // pindah ke tooltip. Angka tanpa penjelasan lebih sulit dipercaya,\n      // bukan lebih ringkas.\n      return \'<div class="rk\' + kls + \'" title="\' + k[0] + \' — \' + k[2] + \'">\' +\n             \'<div class="k">\' + k[0] + \'</div><div class="v">\' +\n             k[1] + \'</div><div class="n">\' + k[2] + \'</div></div>\';\n    }).join("");\n  }\n\n  function chips(){\n    var n = hitung();\n    var d = [["aktif","Perlu ditindak",n.aktif],["siap","Siap ditelepon",n.siap],\n             ["perlu","Perlu dilengkapi",n.perlu],["arsip","Arsip",n.arsip],\n             ["tolak","Jangan telepon",n.tolak],\n             ["semua","Semua",n.semua]];\n    document.getElementById("saring").innerHTML = d.map(function(x){\n      return \'<button class="chip" type="button" data-f="\' + x[0] + \'" aria-pressed="\' +\n             (x[0] === saringAktif) + \'">\' + x[1] +\n             \' <span class="jml">\' + x[2] + \'</span></button>\';\n    }).join("");\n  }\n\n  function labelKelas(k){\n    if (k === "langsung") { return "jalur kantor"; }\n    if (k === "layanan")  { return "call center"; }\n    if (k === "seluler")  { return "nomor HP"; }\n    if (k === "cabang")   { return "nomor cabang"; }\n    return "belum jelas";\n  }\n\n  function render(){\n    var wadah = document.getElementById("daftar");\n    var tampil = LEADS.filter(function(l){\n      var g = grup(l);\n      if (saringAktif === "semua") { return true; }\n      if (saringAktif === "aktif") { return g !== "arsip" && g !== "tolak"; }\n      return g === saringAktif;\n    });\n\n    if (!tampil.length){\n      wadah.innerHTML = \'<div class="kosong">Tidak ada lead di saringan ini.</div>\';\n      return;\n    }\n\n    wadah.innerHTML = tampil.map(function(l){\n      var g = grup(l);\n      var seg = KOMP.map(function(k, j){\n        return l[k[0]] > 0 ? \'<i class="k\' + (j+1) + \'" style="flex:\' + l[k[0]] + \' 1 0"></i>\' : \'\';\n      }).join("");\n      var kutip = l.bukti.length\n        ? \'<div class="kutip">\\u201C\' + l.bukti[0].kutipan + \'\\u201D</div>\'\n        : \'<div class="kutip">\' + (l.catatan || "") + \'</div>\';\n      var pilLantai = l.tegak ? \'\'\n        : \'<span class="pil lantai">bukti \' + l.bukti_kuat + \'/4</span>\';\n      var pilTolak = l.tolak ? \'<span class="pil tolak">JANGAN TELEPON</span>\' : \'\';\n      var kotakTolak = l.tolak\n        ? \'<div class="alasan-tolak"><b>Jangan hubungi.</b> \' + l.tolak + \'</div>\'\n        : \'\';\n\n      var rinciBukti = l.bukti.length\n        ? l.bukti.map(function(b){\n            var judul = b.komponen;\n            KOMP.forEach(function(k){\n              if (b.komponen.indexOf(k[0]) === 0) { judul = k[1]; }\n            });\n            return \'<div class="bukti-item"><div class="bukti-komp"><b>\' + judul +\n              \'</b> &middot; \' + b.label + \' &middot; keyakinan \' + b.yakin +\n              \'</div><div class="bukti-teks">\\u201C\' + b.kutipan + \'\\u201D</div></div>\';\n          }).join("")\n        : \'<div class="bukti-teks">\' + (l.catatan || "Belum ada kutipan.") + \'</div>\';\n\n      var b = l.buka || {};\n      var blokBuka;\n      if (b.tolak){\n        blokBuka = \'<div class="alasan-tolak"><b>Tidak ada pembuka.</b> \' +\n          \'Lead ini ditandai jangan-telepon, jadi bahannya sengaja tidak disusun. \' +\n          b.tolak + \'</div>\';\n      } else if (!(b.titik || []).length){\n        blokBuka = \'<div class="nanti"><b>Belum bisa disusun.</b> \' +\n          \'Belum ada satu pun komponen yang punya kutipan dari situs mereka sendiri. \' +\n          \'Panen bukti dan nilai dulu.\' +\n          ((b.pastikan || []).length ? \'<div class="pastikan">Pastikan dulu: \' +\n            b.pastikan.join(\'; \') + \'</div>\' : \'\') + \'</div>\';\n      } else {\n        blokBuka = \'<div class="buka"><p>Buka dengan yang sudah Anda ketahui \' +\n          \'tentang mereka &mdash; jangan dibacakan, sebut saja:</p><ul>\' +\n          b.titik.map(function(t){\n            return \'<li>\' + t.teks +\n              (t.lemah ? \' <span class="cek">perlu dipastikan</span>\' : \'\') +\n              (t.sorot ? \'<span class="kutip-kecil">kata mereka sendiri: \\u201C\' +\n                t.sorot + \'\\u201D</span>\' : \'\') + \'</li>\';\n          }).join(\'\') + \'</ul>\' +\n          (b.kait ? \'<p class="kait"><b>Lalu kaitkan:</b> \' + b.kait + \'.</p>\' : \'\') +\n          ((b.pastikan || []).length ? \'<p class="pastikan"><b>Pastikan dulu:</b> \' +\n            b.pastikan.join(\'; \') + \'</p>\' : \'\') + \'</div>\';\n      }\n      var tel = l.telepon\n        ? \'<a class="tel" href="tel:\' + l.telepon.replace(/[^0-9+]/g, "") + \'">\' +\n          l.telepon + \'</a><span class="pil \' +\n          (l.kelas === "langsung" ? "siap" : "perlu") + \'">\' + labelKelas(l.kelas) + \'</span>\'\n        : \'<span class="tel mati">Nomor belum ada</span>\';\n\n      return \'<article class="lead \' + g + \'">\' +\n        \'<button class="baris" type="button" aria-expanded="false">\' +\n          \'<div class="kiri">\' +\n            \'<div class="nama">\' + l.nama + pilTolak + pilLantai + \'</div>\' +\n            \'<div class="aksi-teks">\' + l.saran + \'</div>\' + kotakTolak + kutip +\n          \'</div>\' +\n          \'<div class="kanan">\' +\n            \'<div class="skor"><div class="angka">\' + l.need + \'</div>\' +\n              \'<div class="lbl">butuh</div><div class="komp">\' + seg + \'</div></div>\' +\n            \'<span class="panah" aria-hidden="true">&#9654;</span>\' +\n          \'</div>\' +\n        \'</button>\' +\n        \'<div class="rinci">\' +\n          \'<h4>Hubungi</h4><div class="kontak">\' + tel + \'</div>\' +\n          \'<h4>Kenapa perusahaan ini butuh Salesmart</h4>\' + rinciBukti +\n          \'<h4>Pembuka percakapan</h4>\' + blokBuka +\n          \'<h4>Sumber</h4><div class="bukti-teks">\' + l.sumber + \' &middot; skor \' +\n            l.need + \'/100 &middot; \' +\n            (l.tegak ? \'bukti cukup\' : \'bukti \' + l.bukti_kuat + \'/4, angka ini lantai\') +\n          \'</div>\' +\n        \'</div>\' +\n      \'</article>\';\n    }).join("");\n  }\n\n  document.addEventListener("click", function(e){\n    var chip = e.target.closest(".chip");\n    if (chip){ saringAktif = chip.dataset.f; chips(); render(); return; }\n    var b = e.target.closest(".baris");\n    if (b){\n      var buka = b.parentNode.classList.toggle("buka");\n      b.setAttribute("aria-expanded", buka ? "true" : "false");\n    }\n  });\n\n  // --- status agen: dihitung di PERAMBAN, bukan saat halaman dibuat ---\n  // Halaman ini statis dan bisa dibuka berjam-jam kemudian, atau dibuka\n  // dari GitHub Pages yang dibangun dari commit lama. Umur peristiwa\n  // terakhir karena itu dihitung terhadap jam pembaca.\n  function usia(d){\n    // Jam pembaca bisa lebih lambat dari jam server; tanpa ini\n    // panelnya menulis "-8 detik lalu".\n    if (d < 0) { d = 0; }\n    if (d < 60) { return Math.round(d) + \' detik lalu\'; }\n    if (d < 3600) { return Math.round(d/60) + \' menit lalu\'; }\n    if (d < 86400) { return Math.round(d/3600) + \' jam lalu\'; }\n    return Math.round(d/86400) + \' hari lalu\';\n  }\n  function statusAgen(){\n    var el = document.getElementById(\'agen\');\n    if (!el || !el.dataset.pada) { return; }\n    var t = Date.parse(el.dataset.pada);\n    if (isNaN(t)) { return; }\n    var ambang = Number(el.dataset.ambang || 180);\n    var d = (Date.now() - t) / 1000;\n    // Umur HALAMAN, bukan umur peristiwa. Halaman hanya tahu apa yang\n    // benar saat ia dibangkitkan; kalau ia sendiri sudah basi, ia\n    // tidak berhak mengklaim apa pun tentang sekarang.\n    var h = Date.parse(el.dataset.dibuat || \'\');\n    var uh = isNaN(h) ? Infinity : (Date.now() - h) / 1000;\n    var tahu = uh <= ambang;\n    var jalan = tahu && d >= 0 && d <= ambang;\n    el.classList.toggle(\'jalan\', jalan);\n    el.classList.toggle(\'diam\', !jalan);\n    document.getElementById(\'agen-judul\').textContent =\n      jalan ? \'sedang bekerja\'\n            : (tahu ? \'menganggur\' : \'status tidak diketahui\');\n    document.getElementById(\'agen-sejak\').textContent = usia(d);\n    document.getElementById(\'agen-catatan\').textContent = tahu ? \'\'\n      : \'Halaman ini dibuat \' + usia(uh) + \'; apa pun yang agen \'\n        + \'kerjakan sesudah itu tidak terekam di sini.\';\n  }\n  // Jam denyut ditulis server dalam UTC lalu diganti ke jam setempat\n  // pembaca. Tanpa ini, pembaca di WIB melihat 05:57 untuk peristiwa\n  // yang menurut jamnya terjadi pukul 12:57 -- selisih tujuh jam yang\n  // membuat denyutnya terbaca seperti kejadian subuh.\n  function jamSetempat(){\n    var n = document.querySelectorAll(\'time.jam[datetime]\');\n    for (var i = 0; i < n.length; i++){\n      var t = Date.parse(n[i].getAttribute(\'datetime\'));\n      if (isNaN(t)) { continue; }\n      var d = new Date(t);\n      n[i].textContent =\n        String(d.getHours()).padStart(2, \'0\') + \':\' +\n        String(d.getMinutes()).padStart(2, \'0\');\n      n[i].title = d.toLocaleString();\n    }\n  }\n  // --- angka menghitung naik saat halaman dibuka ---------------------\n  // Hanya angka bulat polos yang dianimasikan. Yang berbentuk \'68/72\'\n  // atau berisi teks dibiarkan apa adanya: separuh angka yang bergerak\n  // dan separuh diam terbaca seperti halaman rusak, bukan gaya.\n  //\n  // Nilai akhirnya sudah ada di DOM sebelum animasi jalan, jadi kalau\n  // skripnya gagal di tengah, yang tertinggal angka yang BENAR.\n  function hidupkanAngka(){\n    if (window.matchMedia &&\n        window.matchMedia(\'(prefers-reduced-motion: reduce)\').matches){\n      return;\n    }\n    var n = document.querySelectorAll(\'.rk .v, .skor .angka\');\n    for (var i = 0; i < n.length; i++){\n      (function(el){\n        var teks = el.textContent.trim();\n        if (!/^\\d+$/.test(teks)) { return; }\n        var akhir = parseInt(teks, 10);\n        if (akhir < 2) { return; }\n        var mulai = performance.now();\n        var lama = 620;\n        function langkah(t){\n          var k = Math.min(1, (t - mulai) / lama);\n          var e = 1 - Math.pow(1 - k, 3);\n          el.textContent = String(Math.round(akhir * e));\n          if (k < 1) { requestAnimationFrame(langkah); }\n          else { el.textContent = teks; }\n        }\n        requestAnimationFrame(langkah);\n      })(n[i]);\n    }\n  }\n  jamSetempat();\n  statusAgen(); setInterval(statusAgen, 20000);\n\n  ringkas(); chips(); render(); hidupkanAngka();\n})();\n'


def blok_agen():
    """Panel 'agennya sedang apa' — dibangun dari jejak nyata di database.

    ATURAN YANG TIDAK BOLEH DILONGGARKAN: titik hijau berdenyut hanya
    menyala kalau ada jejak pekerjaan yang benar-benar baru. Agen ini
    tidak jalan terus-menerus; tanpa API berbayar ia hidup hanya selama
    sesi dibuka. Panel yang selalu tampak sibuk adalah rekaman palsu, dan
    seluruh dasbor ini berdiri di atas janji bahwa tidak ada angka yang
    dikarang. Menganggur ditulis apa adanya, lengkap dengan kapan
    terakhir ia bekerja.
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        st = ag.status(con)
        ev = ag.denyut(con, batas=8)
    finally:
        con.close()

    # HALAMAN INI STATIS. "Sedang bekerja" karena itu TIDAK BOLEH dicetak
    # di sini — kalimat itu benar saat halaman dibangkitkan lalu membeku
    # selamanya. Halaman yang dibangkitkan waktu panen berjalan akan terus
    # menyala hijau dan menulis "5 detik lalu" berjam-jam setelah agennya
    # berhenti. Itu persis kebohongan yang panel ini berjanji hindari, dan
    # itu benar-benar terjadi 3 Sep 2026.
    #
    # Jadi yang dicetak ke HTML hanyalah STEMPEL WAKTU peristiwa terakhir.
    # Umurnya dihitung di peramban, saat halaman dibuka, lalu diperbarui
    # tiap 20 detik. Server hanya melaporkan "kapan", tidak pernah "sedang".
    #
    # Nilai bawaannya sengaja "menganggur": kalau JavaScript mati, yang
    # terbaca adalah klaim yang paling hati-hati, bukan yang paling ramai.
    iso = st["terakhir"].isoformat() if st["terakhir"] else ""
    ambang = ag.AMBANG_AKTIF_DETIK
    dibuat = datetime.now(timezone.utc).isoformat()

    # WAKTU HALAMAN INI DIBUAT ikut ditanam, dan itu bukan hiasan.
    #
    # Perbaikan sebelumnya memindahkan perhitungan umur ke peramban,
    # sehingga "5 detik lalu" berhenti membeku. Tapi PERISTIWA TERAKHIRNYA
    # tetap beku: halaman hanya tahu apa yang benar saat ia dibangkitkan.
    # Halaman yang dibuat pukul 05:57 tidak akan pernah tahu agennya mulai
    # bekerja lagi pukul 06:14 -- dan dengan tenang menulis "menganggur"
    # padahal agennya sedang jalan. Itu terjadi 3 Sep 2026, satu jam
    # setelah cacat kebalikannya ditambal.
    #
    # Halaman statis memang tidak bisa tahu apa yang terjadi sesudah ia
    # dibuat. Yang bisa ia lakukan: MENGAKUINYA. Kalau halamannya sendiri
    # sudah lebih tua dari ambang, ia berhenti mengklaim "sedang bekerja"
    # MAUPUN "menganggur", dan menulis status tidak diketahui beserta
    # umurnya sendiri.
    h = [f'<div class="agen diam" id="agen" data-pada="{iso}" '
         f'data-dibuat="{dibuat}" data-ambang="{ambang}">']
    h.append('<div class="agen-kepala"><span class="nadi"></span>'
             '<div><div class="agen-judul">Agen &middot; '
             '<span id="agen-judul">status tidak diketahui</span></div>'
             f'<div class="agen-kini">{esc(st["kegiatan"])}</div>'
             '<div class="agen-catatan" id="agen-catatan"></div></div>'
             '<div class="agen-sejak" id="agen-sejak">&mdash;</div></div>')

    selesai, total = st["panen_selesai"], st["panen_total"]
    if total:
        pct = min(100, round(selesai * 100 / total))
        h.append('<div class="agen-maju"><div class="lbl">'
                 '<span>Sapuan OpenStreetMap</span>'
                 f'<b>{selesai}/{total} kombinasi wilayah &times; tag</b></div>'
                 f'<div class="rel"><i style="width:{pct}%"></i></div></div>')

    if ev:
        h.append('<ul class="denyut">')
        for waktu, jenis, teks in ev:
            # Jamnya dicetak dalam UTC dan DIBERI LABEL "UTC" -- itu yang
            # terbaca kalau JavaScript mati. Peramban menggantinya dengan
            # jam setempat pembaca lewat atribut datetime di bawah.
            #
            # KENAPA TIDAK LANGSUNG DIKONVERSI DI SINI: jam yang dipakai
            # adalah jam MESIN YANG MEMBANGKITKAN halaman, bukan jam
            # pembacanya. Halaman ini terbit lewat GitHub Pages dan bisa
            # dibuka dari zona waktu mana pun; mencetak "12:57" tanpa
            # keterangan hanya memindahkan kesalahannya, tidak
            # memperbaikinya.
            h.append(f'<li><time class="jam" datetime="{waktu.isoformat()}">'
                     f'{waktu.strftime("%H:%M")} UTC</time>'
                     f'<span class="tag {jenis}">{jenis}</span>'
                     f'<span>{esc(teks)}</span></li>')
        h.append('</ul>')

    h.append('<div class="agen-kaki">Denyut ini jejak pekerjaan yang '
             'sungguh terjadi, bukan animasi: tiap barisnya punya stempel '
             'waktu di database. Agen ini tidak berjalan sepanjang hari '
             '&mdash; ia bekerja waktu sesi dibuka. Status di atas dihitung '
             'saat Anda membuka halaman ini, bukan saat halamannya dibuat, '
             'jadi halaman lama akan jujur bilang &ldquo;menganggur&rdquo; '
             'meski dulu dibangkitkan waktu agennya sibuk.</div>')
    h.append('</div>')
    return "\n".join(h)


def bangun(pantau: bool = False) -> int:
    """Tulis docs/index.html sekali. Return jumlah lead."""
    lead = kumpulkan()
    if not lead:
        print("Belum ada lead yang bisa ditampilkan.")
        print("Jalankan panen_bukti.py lalu nilai_kebutuhan.py dulu.")
        raise SystemExit(1)

    hari = date.today()
    tanggal = str(hari.day) + " " + BULAN[hari.month] + " " + str(hari.year)

    isi = (BODY.replace("__JML__", str(len(lead)))
               .replace("__TANGGAL__", tanggal)
               .replace("__AGEN__", blok_agen()))
    js = (SCRIPT.replace("__DATA__", json.dumps(lead, ensure_ascii=False))
                .replace("__AKSI__", json.dumps(AKSI, ensure_ascii=False)))

    # Penyegaran otomatis HANYA di mode pantau. Halaman biasa tidak boleh
    # menyegarkan diri: orang sales yang sedang membaca bukti sebuah lead
    # akan kehilangan posisinya di tengah membaca.
    segar = ('<meta http-equiv="refresh" content="4">\n' if pantau else "")

    html = ('<!DOCTYPE html>\n<html lang="id"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            + segar + HEAD + "</head><body>\n" + isi
            + "<script>\n" + js + "\n</script>\n</body></html>")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    # Pengalih di alamat lama. Ditulis ulang tiap kali supaya tidak ada
    # file yatim yang harus diurus tangan.
    OUT_ALIAS.write_text(
        '<!DOCTYPE html><html lang="id"><head><meta charset="utf-8">'
        '<title>Antrian Lead Salesmart</title>'
        '<link rel="canonical" href="./">'
        '<meta http-equiv="refresh" content="0; url=./"></head>'
        '<body><p>Antrian lead pindah ke <a href="./">halaman depan</a>.</p>'
        '</body></html>\n',
        encoding="utf-8")

    import collections
    n = collections.Counter(AKSI[x["aksi"]][0] for x in lead)
    if not pantau:
        print("Antrian lead dibuat: " + str(OUT))
        print("  %d lead  |  siap %d   perlu %d   arsip %d"
              % (len(lead), n["siap"], n["perlu"], n["arsip"]))
        print("Buka dengan klik dua kali file itu di File Explorer.")
    return len(lead)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pantau", action="store_true",
                    help="bangkitkan ulang terus-menerus selama agen bekerja, "
                         "dan halamannya menyegarkan diri sendiri")
    ap.add_argument("--jeda", type=float, default=4.0)
    args = ap.parse_args()

    if not DB.exists():
        print("Database tidak ada: " + str(DB))
        raise SystemExit(1)

    if not args.pantau:
        bangun(False)
        return

    print("Mode pantau. Ctrl+C untuk berhenti. -> " + str(OUT))
    try:
        while True:
            bangun(True)
            print("  disegarkan " + time.strftime("%H:%M:%S"), flush=True)
            time.sleep(args.jeda)
    except KeyboardInterrupt:
        # Bangkitkan sekali lagi TANPA penyegaran otomatis, supaya halaman
        # yang ditinggalkan tidak terus berkedip setelah agennya berhenti.
        bangun(False)
        print("\nBerhenti memantau; halaman dibangkitkan sekali lagi tanpa "
              "penyegaran otomatis.")


if __name__ == "__main__":
    main()
