"""
agen_status.py
==============
Apa yang agen ini SEDANG kerjakan, dan apa yang baru saja ia kerjakan —
dibaca dari jejak nyata di database, bukan dari status yang dikarang.

KENAPA MODUL INI HATI-HATI SOAL KATA "SEDANG BEKERJA":
    Agen ini tidak jalan terus-menerus. Tanpa API berbayar, ia jalan
    hanya waktu sesi dibuka. Dasbor yang menampilkan agen selalu sibuk
    adalah rekaman palsu — dan halaman-halaman proyek ini dijual atas
    dasar "tidak ada angka yang dikarang".

    Jadi aturannya keras: **"sedang bekerja" hanya boleh muncul kalau
    ada jejak yang benar-benar baru.** Kalau tidak ada, halaman menulis
    "menganggur" beserta kapan terakhir ia bekerja. Menganggur bukan aib;
    berpura-pura sibuk baru aib.

DARI MANA JEJAKNYA DIBACA — semuanya kolom waktu yang memang sudah ada:
    harvest_log.done_at   satu baris per kombinasi wilayah x tag OSM
    kontak_web.diambil_pada   satu baris per perusahaan yang dicari nomornya
    kebutuhan.dinilai_pada    satu baris per penilaian yang ditulis
    jalan_agen.pada           satu baris per jalannya agen pembaca+pemeriksa

    Tidak ada tabel status tersendiri, dan itu disengaja: status yang
    ditulis terpisah bisa basi tanpa ada yang tahu. Jejak pekerjaan tidak
    bisa basi — ia ADALAH pekerjaannya.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

# Ambang "masih hangat". Panen OSM menulis satu baris tiap ~20 detik, jadi
# 3 menit cukup longgar untuk menahan status tetap hidup di sela-sela
# permintaan yang lambat, tapi terlalu pendek untuk membuat pekerjaan
# kemarin terlihat seperti pekerjaan sekarang.
AMBANG_AKTIF_DETIK = 180


def _waktu(s):
    """Terima ISO dengan atau tanpa zona; kembalikan datetime beraware UTC."""
    if not s:
        return None
    t = str(s).strip().replace(" ", "T")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    # Kolom lama ditulis CURRENT_TIMESTAMP SQLite: UTC tanpa penanda zona.
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _tabel_ada(con, nama):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nama,)).fetchone())


def _aman(con, sql, *a):
    try:
        return list(con.execute(sql, a))
    except sqlite3.Error:
        return []


def denyut(con, batas=14):
    """Peristiwa nyata terakhir, terbaru dulu.

    Tiap peristiwa: (waktu UTC, jenis, teks). Jenis dipakai untuk warna.
    """
    ev = []

    for kota, tag, pada in _aman(
            con, "SELECT city, tag_key||'='||tag_value, done_at "
                 "FROM harvest_log ORDER BY done_at DESC LIMIT ?", batas):
        ev.append((_waktu(pada), "panen",
                   f"menyisir {kota} untuk {tag}"))

    for nama, kelas, pada in _aman(
            con, "SELECT nama, COALESCE(kelas_kontak,'?'), diambil_pada "
                 "FROM kontak_web ORDER BY diambil_pada DESC LIMIT ?", batas):
        ev.append((_waktu(pada), "kontak",
                   f"menemukan nomor {kelas} untuk {nama}"))

    for nama, skor, pada in _aman(
            con, "SELECT nama, need_score, dinilai_pada FROM kebutuhan "
                 "ORDER BY dinilai_pada DESC LIMIT ?", batas):
        ev.append((_waktu(pada), "nilai",
                   f"menilai {nama} — skor {skor}"))

    if _tabel_ada(con, "jalan_agen"):
        for nama, sp, sa, pada in _aman(
                con, "SELECT nama, skor_pembaca, skor_akhir, pada "
                     "FROM jalan_agen ORDER BY pada DESC LIMIT ?", batas):
            if sp is not None and sp != sa:
                t = f"pemeriksa mengubah {nama}: {sp} → {sa}"
            else:
                t = f"pemeriksa membantah {nama} dan gagal — {sa} bertahan"
            ev.append((_waktu(pada), "periksa", t))

    ev = [e for e in ev if e[0]]
    ev.sort(key=lambda x: x[0], reverse=True)
    return ev[:batas]


def kemajuan_panen(con):
    """(selesai, total) sapuan OSM. Total dihitung dari daftar yang
    sebenarnya dipakai skripnya, bukan angka yang diketik di sini."""
    selesai = _aman(con, "SELECT count(*) FROM harvest_log")
    selesai = selesai[0][0] if selesai else 0
    try:
        import discover_osm as d
        total = len(d.AREAS) * len(d.CATEGORIES)
    except Exception:
        total = None
    return selesai, total


def status(con):
    """Ringkasan keadaan agen sekarang. Tidak pernah mengarang aktivitas."""
    ev = denyut(con, batas=1)
    sekarang = datetime.now(timezone.utc)
    terakhir = ev[0][0] if ev else None
    umur = (sekarang - terakhir).total_seconds() if terakhir else None

    aktif = umur is not None and umur <= AMBANG_AKTIF_DETIK
    selesai, total = kemajuan_panen(con)

    if aktif:
        kegiatan = ev[0][2]
    elif umur is None:
        kegiatan = "belum ada jejak pekerjaan sama sekali"
    else:
        kegiatan = ev[0][2]

    return {
        "aktif": aktif,
        "kegiatan": kegiatan,
        "detik_sejak": umur,
        "terakhir": terakhir,
        "panen_selesai": selesai,
        "panen_total": total,
    }


def usia_manusia(detik):
    if detik is None:
        return "—"
    detik = int(detik)
    if detik < 60:
        return f"{detik} detik lalu"
    if detik < 3600:
        return f"{detik // 60} menit lalu"
    if detik < 86400:
        return f"{detik // 3600} jam lalu"
    return f"{detik // 86400} hari lalu"
