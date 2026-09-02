"""
gazetteer.py
============
Daftar nama tempat Indonesia, dipakai untuk MENGHITUNG SEBARAN dari
halaman yang cuma MENDAFTAR lokasinya tanpa pernah menyebut jumlahnya.

KENAPA MODUL INI ADA:
    Aturan pola di saring_bukti.py hanya bisa melihat skala kalau
    halamannya menulis ANGKA: "34 provinsi", "500 outlet", "seluruh
    Indonesia". Padahal halaman jangkauan hampir selalu melakukan yang
    sebaliknya - ia MENDAFTAR.

    Dua contoh nyata yang sudah dibaca manusia:

      Nippon Paint  dropdown "Pilih Area Depot" berisi 53 nama kota,
                    dari Aceh sampai Ternate dan Kupang. Tidak ada satu
                    pun angka. Pola scale mendapat 0; manusia membacanya
                    'nasional' (20).

      PT United Dico Citas
                    "BRANCH OFFICES" lalu enam alamat: Jakarta 1, 2, 3,
                    Surabaya, Medan, Bandung. Tidak ada angka. Pola
                    scale mendapat 0; manusia membacanya 'lintas_pulau'.

    Sebuah daftar 53 kota adalah bukti skala yang JAUH lebih kuat
    daripada kalimat "kami hadir di banyak kota" - tapi justru daftar
    itulah yang tidak terlihat oleh regex frasa. Modul ini menutup
    lubang itu dengan cara paling murah: mencocokkan nama tempat, lalu
    menghitung yang BERBEDA.

INI PENGHITUNG SEBARAN, BUKAN PENGURAI ALAMAT:
    Modul ini tidak tahu apakah "Medan" itu kantor cabang, alamat
    pemasok, atau nama jalan. Ia cuma menjawab "berapa banyak tempat
    berbeda yang disebut halaman ini, dan seberapa jauh terpencar".
    Keputusan tetap di tangan pembaca - persis seperti saring_bukti.py.

KENAPA PULAU IKUT DIHITUNG:
    Pita 'lintas_pulau' menyebut pulau, bukan jumlah. Enam kota yang
    semuanya di Jawa tidak sama artinya dengan enam kota yang tersebar
    di Jawa, Sumatera, dan Sulawesi. Tanpa pemetaan pulau, keduanya
    terlihat identik.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Provinsi (38, setelah pemekaran Papua 2022)
# ---------------------------------------------------------------------------
# Disebutnya provinsi berbeda bobotnya dengan disebutnya kota: "29 provinsi"
# adalah klaim cakupan, "29 kota" belum tentu.

PROVINSI = {
    "aceh": "sumatera",
    "sumatera utara": "sumatera", "sumatra utara": "sumatera",
    "sumatera barat": "sumatera", "sumatra barat": "sumatera",
    "riau": "sumatera",
    "kepulauan riau": "sumatera",
    "jambi": "sumatera",
    "sumatera selatan": "sumatera", "sumatra selatan": "sumatera",
    "bangka belitung": "sumatera",
    "bengkulu": "sumatera",
    "lampung": "sumatera",
    "banten": "jawa",
    "dki jakarta": "jawa", "jakarta raya": "jawa",
    "jawa barat": "jawa",
    "jawa tengah": "jawa",
    "yogyakarta": "jawa", "di yogyakarta": "jawa",
    "jawa timur": "jawa",
    "bali": "balinusa",
    "nusa tenggara barat": "balinusa",
    "nusa tenggara timur": "balinusa",
    "kalimantan barat": "kalimantan",
    "kalimantan tengah": "kalimantan",
    "kalimantan selatan": "kalimantan",
    "kalimantan timur": "kalimantan",
    "kalimantan utara": "kalimantan",
    "sulawesi utara": "sulawesi",
    "gorontalo": "sulawesi",
    "sulawesi tengah": "sulawesi",
    "sulawesi barat": "sulawesi",
    "sulawesi selatan": "sulawesi",
    "sulawesi tenggara": "sulawesi",
    "maluku": "maluku",
    "maluku utara": "maluku",
    "papua": "papua",
    "papua barat": "papua",
    "papua selatan": "papua",
    "papua tengah": "papua",
    "papua pegunungan": "papua",
    "papua barat daya": "papua",
}

# ---------------------------------------------------------------------------
# Kota / kabupaten
# ---------------------------------------------------------------------------
# Bukan daftar lengkap 514 kabupaten/kota - sengaja. Yang dikumpulkan adalah
# nama yang BENAR-BENAR muncul di halaman jaringan: kota tempat orang menaruh
# depo, cabang, dan kantor penjualan. Menambah 400 nama kecamatan hanya
# menambah salah-cocok tanpa menambah sinyal.

KOTA = {
    # Sumatera
    "banda aceh": "sumatera", "lhokseumawe": "sumatera", "langsa": "sumatera",
    "sabang": "sumatera", "meulaboh": "sumatera",
    "medan": "sumatera", "binjai": "sumatera", "pematang siantar": "sumatera",
    "pematangsiantar": "sumatera", "tebing tinggi": "sumatera",
    "tanjung balai": "sumatera", "sibolga": "sumatera", "kisaran": "sumatera",
    "rantau prapat": "sumatera", "rantauprapat": "sumatera",
    "padang sidempuan": "sumatera", "padangsidimpuan": "sumatera",
    "padang": "sumatera", "bukit tinggi": "sumatera", "bukittinggi": "sumatera",
    "payakumbuh": "sumatera", "pariaman": "sumatera", "solok": "sumatera",
    "pekanbaru": "sumatera", "dumai": "sumatera", "duri": "sumatera",
    "batam": "sumatera", "tanjung pinang": "sumatera",
    "tanjungpinang": "sumatera",
    "muara bungo": "sumatera",
    "palembang": "sumatera", "lubuk linggau": "sumatera",
    "lubuklinggau": "sumatera", "prabumulih": "sumatera",
    "baturaja": "sumatera", "lahat": "sumatera",
    "pangkal pinang": "sumatera", "pangkalpinang": "sumatera",
    "tanjung pandan": "sumatera",
    "curup": "sumatera",
    "bandar lampung": "sumatera", "bandarlampung": "sumatera",
    "metro": "sumatera", "kotabumi": "sumatera", "bandar jaya": "sumatera",
    # Jawa
    "jakarta": "jawa", "jakarta pusat": "jawa", "jakarta barat": "jawa",
    "jakarta timur": "jawa", "jakarta selatan": "jawa", "jakarta utara": "jawa",
    "cakung": "jawa", "menteng": "jawa", "kelapa gading": "jawa",
    "bogor": "jawa", "depok": "jawa", "tangerang": "jawa",
    "tangerang selatan": "jawa", "serpong": "jawa", "gading serpong": "jawa",
    "bekasi": "jawa", "jatiasih": "jawa", "cikarang": "jawa",
    "karawang": "jawa", "cikampek": "jawa", "purwakarta": "jawa",
    "serang": "jawa", "cilegon": "jawa", "malimping": "jawa",
    "bandung": "jawa", "cimahi": "jawa", "kopo": "jawa", "sumedang": "jawa",
    "garut": "jawa", "tasikmalaya": "jawa", "banjar": "jawa",
    "sukabumi": "jawa", "cianjur": "jawa", "subang": "jawa",
    "cirebon": "jawa", "indramayu": "jawa", "kuningan": "jawa",
    "semarang": "jawa", "salatiga": "jawa", "ungaran": "jawa",
    "kendal": "jawa", "pekalongan": "jawa", "tegal": "jawa",
    "pemalang": "jawa", "brebes": "jawa", "purwokerto": "jawa",
    "cilacap": "jawa", "kebumen": "jawa", "purworejo": "jawa",
    "magelang": "jawa", "temanggung": "jawa", "wonosobo": "jawa",
    "klaten": "jawa", "sukoharjo": "jawa", "surakarta": "jawa",
    "boyolali": "jawa", "sragen": "jawa", "karanganyar": "jawa",
    "kudus": "jawa", "jepara": "jawa", "rembang": "jawa",
    "blora": "jawa", "grobogan": "jawa", "purwodadi": "jawa", "pati": "jawa",
    "jogja": "jawa", "jogjakarta": "jawa", "sleman": "jawa",
    "bantul": "jawa",
    "surabaya": "jawa", "sidoarjo": "jawa", "gresik": "jawa",
    "mojokerto": "jawa", "pasuruan": "jawa", "probolinggo": "jawa",
    "malang": "jawa", "batu": "jawa", "blitar": "jawa", "kediri": "jawa",
    "tulungagung": "jawa", "trenggalek": "jawa", "nganjuk": "jawa",
    "madiun": "jawa", "ngawi": "jawa", "ponorogo": "jawa",
    "bojonegoro": "jawa", "tuban": "jawa", "lamongan": "jawa",
    "jember": "jawa", "banyuwangi": "jawa", "situbondo": "jawa",
    "bondowoso": "jawa", "lumajang": "jawa", "pamekasan": "jawa",
    "sumenep": "jawa", "bangkalan": "jawa",
    # Bali & Nusa Tenggara
    "denpasar": "balinusa", "singaraja": "balinusa", "gianyar": "balinusa",
    "tabanan": "balinusa", "negara": "balinusa",
    "mataram": "balinusa", "bima": "balinusa", "sumbawa": "balinusa",
    "praya": "balinusa", "selong": "balinusa",
    "kupang": "balinusa", "ende": "balinusa", "maumere": "balinusa",
    "waingapu": "balinusa", "ruteng": "balinusa", "atambua": "balinusa",
    "labuan bajo": "balinusa",
    # Kalimantan
    "pontianak": "kalimantan", "singkawang": "kalimantan",
    "ketapang": "kalimantan", "sintang": "kalimantan",
    "palangka raya": "kalimantan", "palangkaraya": "kalimantan",
    "sampit": "kalimantan", "pangkalan bun": "kalimantan",
    "banjarmasin": "kalimantan", "banjarbaru": "kalimantan",
    "martapura": "kalimantan", "batulicin": "kalimantan",
    "balikpapan": "kalimantan", "samarinda": "kalimantan",
    "bontang": "kalimantan", "sangatta": "kalimantan", "berau": "kalimantan",
    "tarakan": "kalimantan", "tanjung selor": "kalimantan",
    "nunukan": "kalimantan",
    # Sulawesi
    "manado": "sulawesi", "bitung": "sulawesi", "tomohon": "sulawesi",
    "kotamobagu": "sulawesi",
    "limboto": "sulawesi",
    "palu": "sulawesi", "poso": "sulawesi", "luwuk": "sulawesi",
    "toli-toli": "sulawesi", "tolitoli": "sulawesi", "donggala": "sulawesi",
    "mamuju": "sulawesi", "majene": "sulawesi", "polewali": "sulawesi",
    "makassar": "sulawesi", "ujung pandang": "sulawesi",
    "parepare": "sulawesi", "pare-pare": "sulawesi", "palopo": "sulawesi",
    "bulukumba": "sulawesi", "bone": "sulawesi", "watampone": "sulawesi",
    "sengkang": "sulawesi", "pinrang": "sulawesi", "sidrap": "sulawesi",
    "kendari": "sulawesi", "bau-bau": "sulawesi", "baubau": "sulawesi",
    "kolaka": "sulawesi", "unaaha": "sulawesi",
    # Maluku & Papua
    "ambon": "maluku", "tual": "maluku", "masohi": "maluku",
    "ternate": "maluku", "tidore": "maluku", "sofifi": "maluku",
    "sorong": "papua", "manokwari": "papua", "fakfak": "papua",
    "jayapura": "papua", "timika": "papua", "merauke": "papua",
    "biak": "papua", "nabire": "papua", "wamena": "papua",
    "serui": "papua",
}

# ---------------------------------------------------------------------------
# Nama yang juga kata biasa
# ---------------------------------------------------------------------------
# Ini yang membuat gazetteer naif jadi berbahaya. "Bone" kabupaten di
# Sulawesi Selatan DAN kata Inggris untuk tulang. "Batu" kota di Jawa Timur
# DAN kata Indonesia untuk batuan. "Negara" kota di Bali DAN kata yang muncul
# di hampir tiap halaman perusahaan Indonesia. "Duri" kota di Riau DAN kata
# untuk duri. "Metro" kota di Lampung DAN kata umum.
#
# Untuk nama-nama ini huruf besar di awal DIWAJIBKAN. Itu tidak sempurna
# (judul berhuruf kapital semua tetap lolos), tapi membuang sebagian besar
# salah-cocok tanpa membuang cocokan yang benar, karena nama tempat memang
# hampir selalu ditulis berhuruf besar.

AMBIGU = {
    "bone", "batu", "metro", "negara", "duri", "banjar", "solok",
    "sabang", "ende", "berau", "riau", "jambi", "bengkulu", "maluku",
    "papua", "bali", "aceh", "lahat", "tual", "serui", "pati",
    "praya", "bima", "kuningan", "selong", "poso", "sintang",
}

# Kata yang mendahului nama tempat dan menandai ia MEMANG lokasi jaringan,
# bukan sekadar disebut lewat. Tidak dipakai untuk menyaring - dipakai untuk
# melaporkan seberapa yakin sebarannya.
PETUNJUK_JARINGAN = re.compile(
    r"(cabang|kantor|depo|depot|gudang|warehouse|branch|office|area"
    r"|wilayah|region|distributor|perwakilan|outlet|gerai|pabrik|plant)",
    re.I,
)


def _bersih(teks: str) -> str:
    """Samakan bentuk supaya pencocokan tidak gagal karena aksen atau tanda."""
    teks = unicodedata.normalize("NFKD", teks)
    return re.sub(r"[‐-―]", "-", teks)


_CACHE_POLA: dict[str, re.Pattern] = {}


def _pola_untuk(nama: str) -> re.Pattern:
    """Regex satu nama tempat: spasi longgar, batas kata di kedua ujung."""
    if nama not in _CACHE_POLA:
        n = nama.title() if nama in AMBIGU else nama
        bagian = r"[\s\-]+".join(re.escape(w) for w in n.split())
        _CACHE_POLA[nama] = re.compile(
            rf"(?<!\w){bagian}(?!\w)", 0 if nama in AMBIGU else re.I)
    return _CACHE_POLA[nama]


def formulir_alamat(teks_halaman: str) -> bool:
    """
    Deteksi halaman yang berisi DROPDOWN ALAMAT GENERIK — bukan jaringan.

    Kasus nyata yang memaksa fungsi ini ada: formulir lamaran kerja
    frisianflag.com/karir/tim-kami. Dropdown "Pilih Provinsi" dan "Pilih
    Kota"-nya mendaftar SEMUA provinsi Indonesia plus ratusan "Kabupaten
    X" — alamat rumah pelamar, bukan sebaran perusahaan. Tanpa deteksi
    ini gazetteer membacanya "35 provinsi / 159 kota" dan menyimpulkan
    'nasional'.

    Pembedanya dari daftar jaringan sungguhan:
      - Kata "Kabupaten" berulang banyak. Formulir alamat memakai nama
        administratif resmi ("Kabupaten Gianyar"); halaman depo/cabang
        menulis nama kotanya saja. Halaman rekrutmen Sinar Sosro yang
        mendaftar lokasi penempatan SUNGGUHAN cuma memuat 5; formulir
        Frisian Flag memuat ratusan.
      - Pasangan frasa "Pilih Provinsi" + "Pilih Kota" tanpa kata
        jaringan. (Dropdown depo Nippon Paint berbunyi "Pilih Area
        Depot" — kata depot-nya yang membedakan.)
    """
    if len(re.findall(r"\bKabupaten\b", teks_halaman)) >= 8:
        return True
    return bool(re.search(r"pilih\s+provinsi", teks_halaman, re.I)
                and re.search(r"pilih\s+(?:kota|kabupaten)", teks_halaman, re.I)
                and not PETUNJUK_JARINGAN.search(teks_halaman))


def sebaran(teks: str | list[str]) -> dict:
    """
    Hitung tempat berbeda yang disebut sebuah halaman.

    `teks` boleh satu string, atau LIST teks per halaman. Kalau list,
    halaman yang terdeteksi formulir alamat (lihat formulir_alamat())
    dibuang dulu — satu string gabungan tidak bisa dibedah lagi, jadi
    pemanggil yang masih memegang halaman terpisah sebaiknya mengirim
    yang terpisah.

    Return:
      provinsi     set nama provinsi yang disebut
      kota         set nama kota yang disebut
      pulau        set gugus pulau yang tersentuh (sumatera, jawa,
                   balinusa, kalimantan, sulawesi, maluku, papua)
      berpetunjuk  True kalau ada kata jaringan (cabang/depo/kantor/...)
                   di dekat salah satu nama tempat. Tanpa ini, deretan
                   nama kota bisa saja cuma daftar alamat pemasok.
      contoh       beberapa nama, untuk dikutip di antrian
    """
    if isinstance(teks, list):
        teks = " ".join(h for h in teks if not formulir_alamat(h))
    t = _bersih(teks)
    prov, kota, pulau = set(), set(), set()

    for nama, p in PROVINSI.items():
        if _pola_untuk(nama).search(t):
            prov.add(nama)
            pulau.add(p)

    for nama, p in KOTA.items():
        if _pola_untuk(nama).search(t):
            kota.add(nama)
            pulau.add(p)

    # Nama provinsi yang juga nama kotanya (Gorontalo, Yogyakarta) jangan
    # dihitung dua kali sebagai bukti terpisah.
    kota -= set(PROVINSI)

    berpetunjuk = False
    for nama in sorted(prov | kota)[:40]:
        m = _pola_untuk(nama).search(t)
        if m and PETUNJUK_JARINGAN.search(t[max(0, m.start() - 120):m.end() + 60]):
            berpetunjuk = True
            break

    return {
        "provinsi": prov,
        "kota": kota,
        "pulau": pulau,
        "berpetunjuk": berpetunjuk,
        "contoh": sorted(x.title() for x in
                         sorted(prov)[:3] + sorted(kota)[:5]),
    }


def pita_scale(s: dict) -> tuple[int, str, str] | None:
    """
    Terjemahkan sebaran jadi pita `scale`. None kalau terlalu tipis untuk
    dijadikan bukti apa pun.

    Ambangnya sengaja lebih tinggi daripada bunyi rubrik. Rubrik menilai
    KENYATAAN perusahaan; di sini yang ada cuma nama tempat yang kebetulan
    tercetak di satu halaman. Satu-dua nama kota bukan bukti sebaran - itu
    alamat kantor.
    """
    np_, nk, npl = len(s["provinsi"]), len(s["kota"]), len(s["pulau"])

    if np_ >= 25 or nk >= 40:
        return 20, "nasional", f"{np_} provinsi / {nk} kota disebut"
    if np_ >= 10 or nk >= 15 or (npl >= 4 and nk >= 6):
        return 15, "lintas_pulau", f"{np_} provinsi / {nk} kota, {npl} gugus pulau"
    if nk >= 3 or np_ >= 3:
        return 10, "multi_kota", f"{np_ + nk} tempat berbeda, {npl} gugus pulau"
    return None


def ringkas(s: dict) -> str:
    """Satu baris untuk dicetak sebagai kutipan."""
    bagian = []
    if s["provinsi"]:
        bagian.append(f"{len(s['provinsi'])} provinsi")
    if s["kota"]:
        bagian.append(f"{len(s['kota'])} kota")
    if s["pulau"]:
        bagian.append(f"{len(s['pulau'])} gugus pulau")
    inti = ", ".join(bagian) or "tidak ada nama tempat"
    tanda = "" if s["berpetunjuk"] else " (tanpa kata jaringan di dekatnya)"
    return f"[sebaran: {inti}{tanda} - {', '.join(s['contoh'][:5])}]"
