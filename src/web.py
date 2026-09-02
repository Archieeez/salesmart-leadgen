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


def boleh_ambil(url: str) -> bool:
    """
    Cek robots.txt. Kalau robots.txt tidak bisa dibaca sama sekali,
    ANGGAP BOLEH — itu perilaku standar — tapi tetap dicatat di log.
    """
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    if root not in _cache_robots:
        rp = RobotFileParser()
        rp.set_url(urljoin(root, "/robots.txt"))
        try:
            rp.read()
            _cache_robots[root] = rp
        except Exception:
            _cache_robots[root] = None

    rp = _cache_robots[root]
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url)


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
