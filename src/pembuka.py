"""
pembuka.py
==========
Susun bahan pembuka percakapan untuk tiap lead, dari bukti yang sudah
dikumpulkan.

KENAPA MODUL INI ADA:
    Halaman antrian sejak awal memuat janji yang belum ditepati:
    "Pembuka percakapan — Belum aktif. Nanti disusun otomatis oleh
    penilai AI dari kutipan di atas." Bahannya sebenarnya sudah lengkap
    di kolom `rincian`; yang belum ada cuma yang menyusunnya.

INI BRIEFING, BUKAN NASKAH:
    Godaan pertamanya adalah membangkitkan kalimat siap-baca. Itu
    ditolak, karena dua alasan yang keduanya berasal dari data nyata:

    1. KUTIPANNYA TIDAK SERAGAM. Bacaan awal menulis parafrase
       berkutipan — "Halaman Distribusi memuat peta distributor rekanan
       per provinsi: PT. SAPTA SARI TAMA, PT. PENTA VALENT, ..." —
       sementara bacaan 2 Sep menulis kalimat verbatim murni.
       Membacakan yang pertama di telepon akan terdengar janggal.
    2. ORANG SALES TIDAK MEMBACAKAN NASKAH. Yang mereka butuhkan
       sebelum menekan tombol adalah: apa yang saya sudah tahu tentang
       mereka, dan kenapa itu relevan. Kalimatnya mereka susun sendiri,
       dan hasilnya selalu lebih hidup daripada naskah.

    Jadi yang dibangkitkan adalah TITIK BICARA, bukan kalimat.

SUMBER KEBENARANNYA LABEL PITA, BUKAN KUTIPAN:
    Titik bicara disusun dari label pita (`jaringan_sendiri`,
    `sales_kanvas`, ...) yang bentuknya seragam dan terkontrol, bukan
    dari teks kutipan yang bentuknya bebas. Kutipannya tetap
    ditampilkan di bagian lain halaman sebagai bahan yang dibaca
    sendiri oleh orang sales.

    FRASA di bawah wajib memuat SETIAP label yang ada di rubrik.PITA.
    Kalau ada pita baru ditambahkan di rubrik.py tanpa frasanya di
    sini, impor modul ini GAGAL — bukan diam-diam menghasilkan
    pembuka yang bolong.

YANG SENGAJA TIDAK DILAKUKAN:
    - Tidak memanggil LLM. Halaman ini dibangkitkan ulang tiap kali
      data berubah; memanggil model tiap kali berarti biaya berulang
      untuk keluaran yang isinya sama.
    - Tidak mengarang fakta. Semua yang muncul berasal dari pita yang
      sudah punya kutipan; komponen tanpa kutipan tidak dijadikan
      titik bicara, ia masuk daftar "pastikan dulu".
    - Tidak menyusun pembuka untuk lead yang ditandai JANGAN TELEPON.
      Itu bukan kelalaian — lihat susun() untuk alasannya.
"""

import re

import rubrik

# ---------------------------------------------------------------------------
# Mengangkat detail yang membedakan
# ---------------------------------------------------------------------------
# Versi pertama modul ini hanya memakai label pita, dan hasilnya cacat yang
# baru kelihatan setelah dijalankan: pembuka untuk Danone, Erela, Garudafood,
# dan Sinar Sosro KELUAR IDENTIK. Wajar — keempatnya duduk di pita teratas
# yang sama. Padahal yang membuat telepon ke Erela hangat justru yang
# spesifik: "29 provinsi", "lowongan Medical Representative".
#
# Percobaan kedua mengekstrak angka dan jabatan dengan regex. Diukur ke data
# nyata: dari 6 lead teratas, hanya 2 yang menghasilkan sesuatu. Cakupannya
# terlalu timpang untuk jadi tulang punggung.
#
# Yang SELALU ada dan selalu berbeda antar perusahaan adalah kutipannya
# sendiri. Jadi itu yang dipakai — dipotong pendek, dengan angka dan jabatan
# didahulukan kalau kebetulan ada.

_ANGKA = re.compile(
    r"\b\d{1,3}(?:[.,]\d{3})*\+?\s*"
    r"(?:provinsi|kota|kabupaten|outlet|gerai|cabang|toko|titik|depo|depot"
    r"|apotek|negara|produk|karyawan|armada|unit|pabrik|gudang|dealer"
    r"|distributor|mitra|warung)\b", re.I)

_JABATAN = re.compile(
    r"\b(?:Medical|Sales|Area|Key Account|Regional|Brand|Product|Field"
    r"|Territory|Branch)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")

# Batas potongan. Cukup untuk satu klausa yang bisa disebut di telepon,
# pendek supaya tidak berubah jadi paragraf yang dibacakan.
_MAKS_SOROT = 120


def sorot(kutipan: str) -> str:
    """Ambil potongan kutipan yang paling layak disebut di telepon.

    Urutan pilihan:
      1. Klausa yang memuat ANGKA + satuan ("29 provinsi") — ini yang
         paling berbunyi spesifik dan paling sulit dikarang.
      2. Klausa yang memuat JABATAN lapangan ("Medical Representative").
      3. Klausa pertama, dipotong di batas kata.

    Selalu mengembalikan potongan yang BENAR-BENAR ada di kutipan —
    tidak pernah merangkai ulang kata. Kalau potongannya dipotong,
    diberi elipsis supaya jelas ia sepenggal.
    """
    t = re.sub(r"\s+", " ", (kutipan or "").strip())
    if not t:
        return ""

    for pola in (_ANGKA, _JABATAN):
        m = pola.search(t)
        if not m:
            continue
        # Ambil jendela di sekitar kecocokan, lalu rapikan ke batas kata.
        a = max(0, m.start() - 45)
        b = min(len(t), m.end() + 45)
        potong = t[a:b]
        if a > 0:
            potong = potong.split(" ", 1)[-1]
        if b < len(t):
            potong = potong.rsplit(" ", 1)[0]
        hasil = ("..." if a > 0 else "") + potong + ("..." if b < len(t) else "")
        return _rapikan(hasil)

    if len(t) <= _MAKS_SOROT:
        return _rapikan(t)
    return _rapikan(t[:_MAKS_SOROT].rsplit(" ", 1)[0] + "...")


def _rapikan(s: str) -> str:
    """Rapikan elipsis ganda dan tanda baca menggantung.

    Kutipan bacaan awal sering SUDAH memuat elipsis sendiri ("...")
    sebagai penanda potongan. Kalau potongan kita mendarat tepat di
    sebelahnya, hasilnya "......" seperti pada Garudafood. Titiknya
    diseragamkan jadi satu elipsis.
    """
    s = re.sub(r"\.{3,}", "...", s)
    s = re.sub(r"(\.\.\.\s*){2,}", "... ", s)
    s = re.sub(r"^\s*[.,;:]+\s*", "", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Frasa per pita
# ---------------------------------------------------------------------------
# Tiap entri: (titik bicara, kaitan ke Salesmart).
#
# "titik bicara" ditulis sebagai hal yang SUDAH DIKETAHUI penelepon tentang
# perusahaan itu — bukan pertanyaan. Perbedaannya besar di telepon: membuka
# dengan "Saya lihat Anda punya jaringan distributor sendiri" menempatkan
# penelepon sebagai orang yang sudah membaca; membuka dengan "Apakah Anda
# punya jaringan distributor?" menempatkannya sebagai penjual yang menebak.
#
# "kaitan" hanya diisi untuk pita yang memang relevan dengan Salesmart.
# Pita terendah tidak punya kaitan — dan itu memang benar: tidak ada yang
# perlu dikaitkan.

FRASA = {
    "dist_model": {
        "jaringan_sendiri": (
            "punya jaringan distributor, agen, atau depo sendiri",
            "tiap titik itu perlu dikunjungi dan dicatat kunjungannya",
        ),
        "jaringan_terbatas": (
            "menjual lewat distributor atau dealer, bukan langsung",
            "jaringan mitra tetap butuh pelacakan kunjungan",
        ),
        "lapangan_bukan_barang": (
            "mengelola armada atau gerai sendiri",
            "operasi lapangannya sudah ada, tinggal soal pencatatannya",
        ),
        "tanpa_jaringan_distribusi": ("", ""),
    },
    "field_sales": {
        "sales_kanvas": (
            "punya tim yang MENJUAL di lapangan (sales, motoris, "
            "medical representative)",
            "inilah orang-orang yang dilacak Salesmart",
        ),
        "lapangan_operasional": (
            "punya tim lapangan besar walau tugasnya operasional "
            "(kurir, kepala cabang, staf gerai)",
            "rute dan kehadiran tim itu bisa dilacak dengan alat yang sama",
        ),
        "lapangan_minimal": (
            "punya sebagian staf yang bekerja di luar kantor",
            "kalau timnya bertambah, pencatatan manual mulai terasa berat",
        ),
        "tanpa_lapangan": ("", ""),
    },
    "scale": {
        "nasional": (
            "beroperasi di seluruh Indonesia",
            "makin luas sebarannya, makin mahal kalau kunjungan tidak tercatat",
        ),
        "lintas_pulau": (
            "sudah melintasi pulau, bukan cuma satu wilayah",
            "koordinasi lintas pulau yang paling cepat kehilangan jejak",
        ),
        "multi_kota": (
            "beroperasi di beberapa kota",
            "sebaran beberapa kota sudah cukup untuk mulai butuh pencatatan terpusat",
        ),
        "dua_kota": ("beroperasi di dua lokasi", ""),
        "satu_lokasi": ("", ""),
    },
    "industry_fit": {
        "produsen_barang_konsumsi": (
            "produsen barang konsumsi bermerek",
            "ini vertikal inti Salesmart — barangnya memang didorong ke pasar "
            "lewat orang",
        ),
        "ritel_distribusi_logistik": (
            "bergerak di ritel, distribusi, atau logistik",
            "barang berpindah lewat jaringan yang perlu dikelola",
        ),
        "platform_jasa": ("bergerak di platform atau jasa digital", ""),
        "tidak_relevan": ("", ""),
    },
}

# Urutan titik bicara di layar. Bukan urutan bobot rubrik — ini urutan
# yang masuk akal DIUCAPKAN: sebut dulu industrinya (siapa mereka), lalu
# jaringannya (apa yang mereka punya), lalu timnya (siapa yang bergerak),
# baru skalanya (seberapa besar masalahnya).
URUT_BICARA = ["industry_fit", "dist_model", "field_sales", "scale"]

NAMA_KOMPONEN = {
    "dist_model": "Model distribusi",
    "field_sales": "Tim sales lapangan",
    "scale": "Skala operasi",
    "industry_fit": "Kecocokan industri",
}


def _periksa_kelengkapan():
    """Pastikan tiap pita di rubrik.py punya frasa di sini.

    Sengaja dijalankan saat impor. Kalau rubrik.PITA bertambah dan file
    ini tidak ikut diperbarui, lebih baik gagal keras sekarang daripada
    menghasilkan pembuka yang diam-diam kehilangan satu titik bicara.
    """
    kurang = []
    for komponen, pita in rubrik.PITA.items():
        for _, label, _, _ in pita:
            if label not in FRASA.get(komponen, {}):
                kurang.append(f"{komponen}.{label}")
    if kurang:
        raise RuntimeError(
            "pembuka.FRASA belum memuat pita: " + ", ".join(kurang)
            + " — tambahkan frasanya, atau isi ('', '') kalau pita itu "
              "memang tidak layak jadi titik bicara.")


_periksa_kelengkapan()


# ---------------------------------------------------------------------------
# Penyusun
# ---------------------------------------------------------------------------

def dari_skor(skor: dict) -> dict:
    """Bangun `rincian` semu dari skor komponen, untuk lead riset manual.

    KENAPA PERLU:
        20 perusahaan sampel di companies_prioritas.csv dinilai manusia
        SEBELUM pipeline bukti ada, jadi tidak punya kutipan per
        komponen — cuma angka. Tanpa jalan ini mereka tidak dapat
        pembuka sama sekali, padahal tiga di antaranya (Wings Group,
        Kalbe Farma, Sido Muncul) bernilai 100 dan ada di daftar siap
        telepon. Membiarkan lead terbaik tanpa bahan adalah kegagalan
        yang lebih besar daripada bahan tanpa kutipan.

        Angkanya dibalik jadi label lewat rubrik.label_pita(), jadi
        sumber kebenarannya tetap rubrik.py.

    Kutipannya diisi penanda, BUKAN teks karangan. susun() memakai
    keberadaan kutipan sebagai syarat sebuah titik bicara boleh muncul;
    penanda ini membuat titik bicaranya muncul tapi keyakinannya
    dipaksa 'sedang' sehingga semuanya bertanda "perlu dipastikan".
    Itu jujur: penilaiannya nyata, tapi tidak berasal dari kalimat yang
    perusahaan itu tulis sendiri.
    """
    rincian = {}
    for komponen in rubrik.MAKS_KOMPONEN:
        nilai = skor.get(komponen)
        if nilai is None:
            continue
        label = rubrik.label_pita(komponen, nilai)
        if not label:
            continue
        rincian[komponen] = {
            "label": label,
            "kutipan": _TANPA_KUTIPAN,
            "sumber_url": "",
            "keyakinan": "sedang",
        }
    return rincian


# Penanda internal: penilaian nyata, tapi tanpa kalimat dari situs mereka.
# Dikenali susun() supaya tidak pernah ditampilkan sebagai kutipan.
_TANPA_KUTIPAN = "\x00riset-manual"


def susun(nama, rincian, need, bukti_kuat, tegak, alasan_tolak=None):
    """Kembalikan dict bahan pembuka, atau dict bertanda 'tolak'.

    Parameter:
      rincian       dict {komponen: {'label','kutipan','keyakinan',...}}
      alasan_tolak  hasil rubrik.tandai_penolakan(); kalau terisi, TIDAK
                    ada pembuka yang disusun sama sekali.

    Kenapa lead yang ditolak tidak dapat pembuka:
        Menyusun pembuka untuk pesaing berarti menyiapkan kalimat yang
        membuka isi pipeline kita kepada mereka. Untuk penolakan jenis
        lain (industry_fit 0), pembukanya akan terdengar meyakinkan
        justru karena bukti lapangannya nyata — dan itu yang membuat
        orang menelepon sasaran yang salah. Dua-duanya lebih buruk
        daripada tidak ada pembuka.
    """
    if alasan_tolak:
        return {"tolak": alasan_tolak, "titik": [], "kait": "", "pastikan": []}

    titik, kait, pastikan = [], [], []
    for komponen in URUT_BICARA:
        v = rincian.get(komponen) or {}
        label = v.get("label", "")
        frasa, hook = FRASA.get(komponen, {}).get(label, ("", ""))
        punya_kutipan = bool((v.get("kutipan") or "").strip())
        yakin = v.get("keyakinan", "")

        if frasa and punya_kutipan:
            manual = (v.get("kutipan") == _TANPA_KUTIPAN)
            titik.append({
                "komponen": komponen,
                "nama_komponen": NAMA_KOMPONEN[komponen],
                "teks": frasa,
                "sorot": "" if manual else sorot(v.get("kutipan")),
                "lemah": manual or yakin in ("sedang", "rendah"),
            })
            if hook:
                kait.append((rubrik.nilai_pita(komponen, label), hook))
        elif frasa and not punya_kutipan:
            # Pita terisi tapi tanpa kutipan: dinilai dari kategori OSM
            # atau simpulan, bukan dari kalimat perusahaan itu sendiri.
            # Tidak layak diucapkan sebagai "saya lihat di situs Anda".
            pastikan.append(f"{NAMA_KOMPONEN[komponen]} — dinilai "
                            f"'{label}' tapi tanpa kutipan dari situsnya")
        elif not frasa:
            pastikan.append(f"{NAMA_KOMPONEN[komponen]} — belum ada bukti")

    # Kaitan yang dipakai cuma SATU: yang komponennya paling berbobot.
    # Menumpuk empat kaitan sekaligus membuat pembuka jadi presentasi.
    kait.sort(reverse=True)
    kaitan = kait[0][1] if kait else ""

    if not tegak:
        pastikan.insert(0, f"Bukti baru {bukti_kuat}/4 — angka {need} ini "
                           f"LANTAI, bukan penilaian final")

    if any((rincian.get(k) or {}).get("kutipan") == _TANPA_KUTIPAN
           for k in rubrik.MAKS_KOMPONEN):
        pastikan.insert(0, "Penilaian ini dari riset manual, BUKAN dari "
                           "kalimat di situs mereka — tidak ada yang bisa "
                           "dikutip balik kalau ditanya")

    return {"tolak": None, "titik": titik, "kait": kaitan,
            "pastikan": pastikan}


def ringkas_teks(nama, bahan):
    """Versi teks polos, untuk CSV ekspor dan pemeriksaan dari terminal."""
    if bahan["tolak"]:
        return f"JANGAN TELEPON — {bahan['tolak']}"
    if not bahan["titik"]:
        return "Belum cukup bukti untuk menyusun pembuka."
    baris = [f"Buka dengan yang sudah Anda ketahui tentang {nama}:"]
    for t in bahan["titik"]:
        tanda = " (perlu dipastikan)" if t["lemah"] else ""
        baris.append(f"  - {t['teks']}{tanda}")
        if t["sorot"]:
            baris.append(f"      kata mereka sendiri: \"{t['sorot']}\"")
    if bahan["kait"]:
        baris.append(f"Lalu kaitkan: {bahan['kait']}.")
    if bahan["pastikan"]:
        baris.append("Pastikan dulu: " + "; ".join(bahan["pastikan"]))
    return "\n".join(baris)


if __name__ == "__main__":
    import json
    import sqlite3
    import sys
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db = Path(__file__).resolve().parent.parent / "data" / "leads.db"
    con = sqlite3.connect(db)
    n = 0
    for (nama, rin, need, bk, st, fit, cat) in con.execute(
            "SELECT nama, rincian, need_score, bukti_kuat, status_nilai, "
            "industry_fit, COALESCE(catatan,'') FROM kebutuhan "
            "ORDER BY need_score DESC"):
        bahan = susun(nama, json.loads(rin), need, bk,
                      st == "nilai_tegak",
                      rubrik.tandai_penolakan(need, fit, cat))
        print(f"\n=== {nama}  (need {need}, bukti {bk}/4)")
        print(ringkas_teks(nama, bahan))
        n += 1
    con.close()
    print(f"\n{n} lead diproses.")
