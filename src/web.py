"""
web.py
======
Lapisan pengambil halaman yang dipakai bersama.

KENAPA MODUL INI ADA:
    enrich_kontak.py sudah punya kode ambil-halaman yang matang: patuh
    robots.txt, cache ke disk, dan turun ke http kalau sertifikat https
    situsnya rusak. panen_bukti.py butuh persis semua itu.

    Kalau disalin, dua salinan itu pasti berbeda pelan-pelan — dan yang
    paling berbahaya, aturan robots.txt bisa ikut berbeda. Aturan kepatuhan
    hanya boleh ditulis di SATU tempat.

Prinsip yang dijaga di sini:
    - WAJIB patuh robots.txt. Tidak ada jalan pintas, tidak ada parameter
      untuk mematikannya.
    - Rate limit sopan. Jeda tidak boleh dikecilkan.
    - Tidak pernah memakai verify=False. Kalau sertifikat tidak bisa
      diverifikasi, yang dicoba adalah http biasa — bukan menerima
      sertifikat palsu.
"""

import hashlib
import json
import os
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Konfigurasi
# --------------------------------------------------------------------------

# Menunjuk ke repo, bukan alamat email pribadi.
#
# Crawler yang sopan HARUS bisa dihubungi — pemilik situs berhak tahu siapa
# yang mengetuk pintunya. Tapi alamat pribadi di repo publik dipanen bot
# spam dalam hitungan hari, dan alamat karangan lebih buruk lagi: pemilik
# situs yang mau protes menulis ke kotak surat yang tidak ada.
#
# URL repo menyelesaikan keduanya: identitasnya jelas, dan siapa pun bisa
# membuka issue di sana. Ini praktik yang sama dipakai crawler arus utama.
USER_AGENT = (
    "salesmart-leadgen/0.1 "
    "(riset lead B2B; +https://github.com/Archieeez/salesmart-leadgen)"
)
TIMEOUT = 15
JEDA_ANTAR_SITUS = 2.0      # detik, antar domain
JEDA_ANTAR_HALAMAN = 1.0    # detik, antar halaman di domain yang sama

# Diisi pemanggil lewat setel().
VERBOSE = False
CACHE_DIR = None


def setel(verbose: bool = False, cache_dir: str | None = None):
    """Dipanggil sekali dari main() tiap skrip."""
    global VERBOSE, CACHE_DIR
    VERBOSE = verbose
    CACHE_DIR = cache_dir or None


def log(pesan: str):
    if VERBOSE:
        print(f"      {pesan}")


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------

_cache_robots: dict[str, RobotFileParser | None] = {}
# root -> True kalau host itu BENAR-BENAR menerbitkan robots.txt yang bisa
# dibaca (HTTP 200). False kalau ia menolak menerbitkannya (401/403).
_robots_terbit: dict[str, bool] = {}


def _muat_robots(root: str):
    """Ambil robots.txt satu host, catat apakah ia benar-benar terbit.

    Dipisah dari boleh_ambil() supaya STATUS-nya bisa diketahui, bukan
    cuma hasil boleh/tidaknya. Bedanya menentukan — lihat
    host_alternatif().
    """
    if root in _cache_robots:
        return
    rp = RobotFileParser()
    rp.set_url(urljoin(root, "/robots.txt"))
    try:
        r = requests.get(urljoin(root, "/robots.txt"),
                         headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
            _cache_robots[root] = rp
            _robots_terbit[root] = True
            # Content-Signal tidak dikenali RobotFileParser, jadi dipungut
            # sendiri. Diambil dari SELURUH berkas, bukan cuma grup "*":
            # sinyal ini pernyataan tentang KONTEN situsnya, bukan tentang
            # satu agen tertentu.
            sinyal = " ".join(
                b.split(":", 1)[1].strip().lower()
                for b in r.text.splitlines()
                if b.strip().lower().startswith("content-signal:"))
            if sinyal:
                _cache_sinyal[root] = sinyal
            return
        if r.status_code in (401, 403):
            # Server MENOLAK menyerahkan robots.txt. Ini bukan kebijakan
            # perayapan — ia tidak menyatakan apa pun. Perilaku standar
            # (dan yang dipakai di sini) tetap menganggapnya larangan.
            rp.disallow_all = True
            _cache_robots[root] = rp
            _robots_terbit[root] = False
            return
        # 404 dan sisanya: tidak ada robots.txt = tidak ada larangan.
        _cache_robots[root] = None
        _robots_terbit[root] = False
    except requests.RequestException:
        _cache_robots[root] = None
        _robots_terbit[root] = False


# --------------------------------------------------------------------------
# Content-Signal: sinyal yang robots.txt sendiri tidak bisa nyatakan
# --------------------------------------------------------------------------
# robots.txt cuma bisa bilang "boleh diambil / tidak" PER NAMA AGEN. Ia tidak
# bisa bilang "boleh diambil, tapi jangan dimasukkan ke model AI". Untuk itu
# ada Content-Signal, dan sejumlah situs sudah memakainya.
#
# KENAPA INI HARUS ADA DI KODE, BUKAN CUMA DI CATATAN:
#     robots.txt bps.go.id berbunyi:
#         User-agent: *
#         Content-Signal: search=yes,ai-train=no,use=reference
#         Allow: /
#     lalu Disallow: / untuk ClaudeBot, GPTBot, CCBot, Google-Extended, dst.
#
#     Agen kita bernama "salesmart-leadgen", jadi ia jatuh ke grup "*" dan
#     SECARA HARFIAH DIIZINKAN. Proyek ini sudah memutuskan sejak 1 Sep
#     bahwa memakai nama sendiri untuk mengambil apa yang mereka tutup bagi
#     AI adalah PENGELAKAN, bukan kepatuhan — tapi keputusan itu selama ini
#     hanya tertulis di CATATAN_SUMBER_DATA.md. Kodenya tetap akan memanen
#     bps.go.id kalau ada yang menaruhnya di seed.
#
#     Aturan yang tidak dijalankan mesin cepat atau lambat dilanggar tanpa
#     ada yang sengaja melanggarnya. Jadi sekarang dijalankan mesin.
#
# Pipeline ini memasukkan teks yang dipanen ke model bahasa untuk dinilai.
# Itu persis "ai-input". Jadi situs yang menyatakan ai-train=no atau
# ai-input=no dihormati, berapa pun bunyi Allow-nya.

_SINYAL_MENOLAK = ("ai-train=no", "ai-input=no")
_cache_sinyal: dict[str, str] = {}


def _sinyal_menolak(root: str) -> str:
    """Kembalikan sinyal yang menolak, atau string kosong."""
    s = _cache_sinyal.get(root, "")
    for tolak in _SINYAL_MENOLAK:
        if tolak in s.replace(" ", ""):
            return tolak
    return ""


def boleh_ambil(url: str) -> bool:
    """
    Cek robots.txt. Kalau robots.txt tidak bisa dibaca sama sekali,
    ANGGAP BOLEH — itu perilaku standar — tapi tetap dicatat di log.

    Content-Signal ikut dihormati: situs yang menyatakan ai-train=no atau
    ai-input=no TIDAK dipanen, walau baris Allow-nya mengizinkan agen
    kita. Lihat catatan di atas.
    """
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    _muat_robots(root)

    tolak = _sinyal_menolak(root)
    if tolak:
        log(f"DITOLAK Content-Signal ({tolak}): {root}")
        return False

    rp = _cache_robots[root]
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url)


def host_alternatif(website: str) -> tuple[str, str] | None:
    """Kalau host seed tidak menerbitkan kebijakan, coba pasangan www-nya.

    Kembalikan (url_baru, alasan) atau None.

    ATURANNYA SEMPIT, DAN KESEMPITANNYA YANG PENTING:

        Varian hanya dicoba kalau host asal **menolak menerbitkan
        robots.txt** (HTTP 401/403). Host yang begitu tidak menyatakan
        kebijakan perayapan apa pun — 403-nya setelan server, dan yang
        membacanya sebagai "larang semua" adalah pustaka kita sendiri,
        secara konservatif.

        Kalau host asal MENERBITKAN robots.txt yang melarang, varian
        TIDAK pernah dicoba. Itu kebijakan sungguhan dan harus dipatuhi,
        titik. Termasuk kalau larangannya menyebut agen kita secara
        harfiah — kasus bps.go.id yang menyebut ClaudeBot.

        Varian pun tetap harus MENERBITKAN robots.txt sendiri yang
        mengizinkan. Kalau ia juga menolak menerbitkan, berhenti.

    KENAPA ADA:
        indomaret.co.id/robots.txt menjawab 403 — tidak ada kebijakan.
        www.indomaret.co.id/robots.txt menjawab 200 dengan berkas KOSONG,
        yang artinya izinkan semua. Situsnya hidup di host www; host apex
        cuma memantul. Tanpa aturan ini, Indomaret (need 85) terus
        tercatat "0 halaman" padahal situsnya terbuka.

    SEBERAPA SERING MENOLONG: sedikit sekali, dan itu sudah diukur.
        Dari 29 situs bertanda robots_larang (2 Sep 2026), 23 MENERBITKAN
        robots.txt sungguhan yang melarang — tertutup, tidak disentuh.
        Hanya 2 yang menolak menerbitkan, dan keduanya bukan profil
        sasaran. Jadi jangan pakai aturan ini sebagai alasan menyisir
        ulang tumpukan robots_larang; sudah dicoba, hasilnya nihil.
    """
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    p = urlparse(website)
    root = f"{p.scheme}://{p.netloc}"
    _muat_robots(root)
    if _robots_terbit.get(root, False):
        return None                      # ia menerbitkan kebijakan: hormati
    if boleh_ambil(website):
        return None                      # tidak diblokir, tidak perlu varian

    lain = _host_lain(p.netloc)
    root_lain = f"{p.scheme}://{lain}"
    _muat_robots(root_lain)
    if not _robots_terbit.get(root_lain, False):
        return None                      # varian juga tidak menerbitkan
    sisa = p.path + (("?" + p.query) if p.query else "")
    url_lain = f"{root_lain}{sisa}"
    if not boleh_ambil(url_lain):
        return None                      # varian menerbitkan, dan melarang
    return url_lain, (f"host {p.netloc} tidak menerbitkan robots.txt "
                      f"(401/403); {lain} menerbitkan dan mengizinkan")


# --------------------------------------------------------------------------
# Cache HTML di disk
# --------------------------------------------------------------------------

def _jalur_cache(url: str) -> str | None:
    if not CACHE_DIR:
        return None
    kunci = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, kunci + ".json")


def dari_cache(url: str) -> bool:
    jalur = _jalur_cache(url)
    return bool(jalur and os.path.exists(jalur))


def _host_lain(host: str) -> str:
    """Pasangan www dari sebuah host: www.x <-> x."""
    return host[4:] if host.startswith("www.") else "www." + host


def _varian_http(url: str) -> list[str]:
    """URL http yang layak dicoba saat https gagal karena sertifikat."""
    p = urlparse(url)
    sisa = p.path + (("?" + p.query) if p.query else "")
    return [f"http://{p.netloc}{sisa}",
            f"http://{_host_lain(p.netloc)}{sisa}"]


def _varian_www(url: str) -> list[str]:
    """URL varian www yang layak dicoba saat SAMBUNGANNYA yang gagal.

    KENAPA TERPISAH DARI _varian_http:
        Fallback www selama ini HANYA menyala pada SSLError. Pada
        ConnectionError — yaitu DNS tidak menjawab — tidak ada yang
        dicoba ulang sama sekali. Padahal domain yang hanya mendaftarkan
        salah satu varian adalah salah konfigurasi yang lazim.

        Diukur pada 33 situs mati proyek ini (2 Sep 2026): hanya SATU
        domain yang varian www-nya menjawab DNS (carsworld.co.id gagal,
        www.carsworld.co.id menjawab) — dan yang satu itu pun TIDAK
        terpanen, karena robots.txt-nya melarang (dan origin-nya balas
        HTTP 530).

        Jadi hasil bersih tambalan ini di data yang ada: NOL situs.
        Ia tetap dipasang karena celahnya memang salah — fallback www
        seharusnya tidak bergantung pada JENIS kegagalan sambungan —
        tapi jangan berharap ia menemukan apa-apa. Kalau ada yang
        mengusulkan panen ulang massal dengan alasan "sekarang fallback
        www-nya sudah benar", angka di atas jawabannya.

    Pemeriksaan robots.txt TETAP berlaku di jalur ini. Varian www adalah
    host yang berbeda, jadi izinnya harus ditanyakan lagi — bukan
    diwarisi dari host asal.
    """
    p = urlparse(url)
    sisa = p.path + (("?" + p.query) if p.query else "")
    return [f"{p.scheme}://{_host_lain(p.netloc)}{sisa}"]


def ambil_html(url: str) -> tuple[str | None, str]:
    """
    Return (html, alasan). html None kalau gagal.

    Kalau CACHE_DIR diisi, HTML mentah disimpan ke disk. Ini bukan demi
    kecepatan: tanpa cache, tiap kali aturan ekstraksi diutak-atik situs
    orang kena request ulang. Dengan cache, satu kali ambil cukup.
    """
    jalur = _jalur_cache(url)
    if jalur and os.path.exists(jalur):
        with open(jalur, encoding="utf-8") as f:
            c = json.load(f)
        return c["html"], c["alasan"] + " |cache"

    def _get(u):
        return requests.get(
            u,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )

    imbuhan = ""
    try:
        try:
            r = _get(url)
        except requests.exceptions.SSLError:
            # Sertifikat tidak terverifikasi. Coba http biasa — BUKAN
            # verify=False, karena itu sama saja menerima sertifikat palsu.
            #
            # Varian www perlu ikut dicoba: mayora.com lewat http dialihkan
            # balik ke https://www.mayora.com yang sertifikatnya sama
            # rusaknya, sementara http://www.mayora.com langsung 200.
            r = None
            for kandidat in _varian_http(url):
                try:
                    r = _get(kandidat)
                    imbuhan = " (turun ke http, sertifikat https bermasalah)"
                    break
                except requests.RequestException:
                    continue
            if r is None:
                raise
        except requests.exceptions.ConnectionError:
            # DNS tidak menjawab, atau sambungan ditolak. Coba varian www
            # sekali — lihat _varian_www() untuk kenapa dan seberapa
            # sering ini menolong.
            r = None
            for kandidat in _varian_www(url):
                if not boleh_ambil(kandidat):
                    continue
                try:
                    r = _get(kandidat)
                    imbuhan = " (varian www, host asli tidak menjawab)"
                    break
                except requests.RequestException:
                    continue
            if r is None:
                raise

        ctype = r.headers.get("Content-Type", "")
        if r.status_code != 200:
            html, alasan = None, f"http {r.status_code}{imbuhan}"
        elif "text/html" not in ctype:
            html, alasan = None, "bukan html: " + ctype.split(";")[0]
        else:
            html, alasan = r.text, f"http 200, {len(r.text)} char{imbuhan}"
    except requests.RequestException as e:
        html, alasan = None, "gagal: " + type(e).__name__

    if jalur:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(jalur, "w", encoding="utf-8") as f:
            json.dump({"url": url, "html": html, "alasan": alasan}, f)
    return html, alasan


def ambil_teks(url: str) -> str | None:
    """HTML -> teks bersih, plus href tel: dan telepon dari JSON-LD."""
    html, alasan = ambil_html(url)
    log(f"GET {url} -> {alasan}")
    if html is None:
        return None

    sup = BeautifulSoup(html, "html.parser")

    # Panen dulu dari JSON-LD sebelum <script> dibuang.
    jsonld = []
    for tag in sup.find_all("script"):
        isi = tag.string or tag.get_text() or ""
        if '"telephone"' in isi or "'telephone'" in isi:
            for m in re.finditer(r'["\']telephone["\']\s*:\s*["\']([^"\']{6,40})', isi):
                jsonld.append(m.group(1))

    for tag in sup(["script", "style", "noscript"]):
        tag.decompose()

    tel = " ".join(
        a["href"].replace("tel:", " ")
        for a in sup.find_all("a", href=True)
        if a["href"].lower().startswith("tel:")
    )
    return sup.get_text(" ", strip=True) + " " + tel + " " + " ".join(jsonld)


def teks_dari_html(html: str) -> str:
    """HTML -> teks polos.

    Dipisah dari ambil_teks_polos() supaya pemanggil yang SUDAH memegang
    HTML halaman tidak perlu memintanya lagi ke server. Tanpa ini,
    panen_bukti.py harus mengambil halaman seed dua kali: sekali untuk
    teksnya, sekali untuk menggali linknya.
    """
    sup = BeautifulSoup(html, "html.parser")
    for tag in sup(["script", "style", "noscript"]):
        tag.decompose()
    return sup.get_text(" ", strip=True)


def ambil_teks_polos(url: str) -> str | None:
    """Teks halaman apa adanya, tanpa tambahan telepon. Untuk panen bukti."""
    html, alasan = ambil_html(url)
    log(f"GET {url} -> {alasan}")
    if html is None:
        return None
    return teks_dari_html(html)


def jeda_halaman(url: str):
    """Jeda hanya kalau halaman benar-benar diambil dari jaringan."""
    if not dari_cache(url):
        time.sleep(JEDA_ANTAR_HALAMAN)


# --------------------------------------------------------------------------
# Penemuan link
# --------------------------------------------------------------------------

def _domain_sama(a: str, b: str) -> bool:
    """Apakah dua URL berada di situs yang sama, mengabaikan awalan www.

    KENAPA PERLU: perbandingan netloc apa adanya membuat SELURUH link
    internal danone.co.id terbuang. Seed-nya ditulis www.danone.co.id,
    sementara link di halamannya ditulis tanpa www — jadi tiap link
    dianggap keluar domain. Akibatnya homepage terbaca "0 link", tidak
    ada apa pun yang bisa ditelusuri, dan yang tersimpan cuma beranda.

    Ini penyaring yang sengaja sempit: hanya awalan www yang diabaikan.
    Subdomain lain (mis. karir.perusahaan.co.id) tetap dianggap situs
    lain, karena menyamakan semua subdomain bisa menyeret crawler ke
    tempat yang tidak diniatkan.
    """
    def inti(h):
        return urlparse(h).netloc.lower().removeprefix("www.")
    return inti(a) == inti(b)


def cari_link(html: str, root: str, pola: re.Pattern) -> list[str]:
    """
    Ambil link satu domain yang teks ATAU href-nya cocok dengan `pola`.
    Menggantikan tebak-tebakan path.
    """
    sup = BeautifulSoup(html, "html.parser")
    hasil, terlihat = [], set()
    for a in sup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if not (pola.search(a.get_text(" ", strip=True)) or pola.search(href)):
            continue
        url = urljoin(root, href)
        if not _domain_sama(url, root):
            continue
        url = url.split("#")[0]
        if url in terlihat:
            continue
        terlihat.add(url)
        hasil.append(url)
    return hasil


def akar(website: str) -> tuple[str, str]:
    """Kembalikan (root, path_seed) dari URL seed."""
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    p = urlparse(website)
    return f"{p.scheme}://{p.netloc}", (p.path or "/")
