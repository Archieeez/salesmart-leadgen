"""
nilai_kebutuhan.py
==================
Isi keempat komponen Need Score secara otomatis, dari halaman yang sudah
dipanen panen_bukti.py. Ini Phase 2 — ekstraksi sinyal via LLM.

MASALAH YANG DISELESAIKAN:
    dist_model, field_sales, scale, dan industry_fit selama ini DIKETIK
    TANGAN di companies_scored.csv. Dua puluh perusahaan bisa. 991 lead OSM
    tidak bisa. 31.795 perusahaan BPS jelas tidak bisa.

KENAPA LLM, BUKAN COCOK-COCOKAN KATA:
    Sudah dicoba. Cocok-cocokan kata kunci hanya menemukan sinyal di 10 dari
    27 perusahaan — padahal ke-27-nya anggota GAPMMI, yang menurut definisi
    semuanya produsen makanan dengan jaringan distribusi. Jawaban benarnya
    ~27/27.

    Sebabnya: kalimat "melayani lebih dari 500 outlet di 34 provinsi" adalah
    bukti kuat untuk dist_model DAN scale sekaligus, tapi tidak mengandung
    satu pun kata kunci. Yang bisa membaca kalimat itu dan paham artinya
    cuma model bahasa.

ATURAN PROMPT DIBANGKITKAN DARI rubrik.py:
    Deskripsi pita TIDAK ditulis ulang di file ini. Ia dibangkitkan dari
    rubrik.PITA. Jadi begitu pita di rubrik.py diubah, prompt ikut berubah —
    tidak mungkin melenceng diam-diam.

WAJIB ADA BUKTI:
    Model diminta mengutip kalimat aslinya untuk tiap penilaian. Penilaian
    tanpa kutipan diturunkan ke pita terendah yang bisa dipertahankan.
    Ini yang membedakan penilaian dari tebakan.

Pakai:
    python nilai_kebutuhan.py --dry-run            # lihat prompt + perkiraan biaya
    python nilai_kebutuhan.py --limit 5            # nilai 5 perusahaan
    python nilai_kebutuhan.py                      # semuanya
"""

import argparse
import json
import sqlite3
import sys
from typing import Literal

import rubrik

MODEL = "claude-opus-5"

# Harga per 1 juta token (Claude Opus 5). Dipakai untuk perkiraan biaya
# di --dry-run, supaya tidak ada kejutan di tagihan.
HARGA_INPUT = 5.00
HARGA_OUTPUT = 25.00
HARGA_INPUT_CACHE_BACA = 0.50    # pembacaan cache jauh lebih murah

# Batas teks per perusahaan. Halaman dipotong per halaman, bukan digabung
# lalu dipotong, supaya tiap jenis halaman tetap kebagian.
MAKS_CHAR_PER_HALAMAN = 6000
MAKS_CHAR_PER_PERUSAHAAN = 40000


# --------------------------------------------------------------------------
# Prompt dibangkitkan dari rubrik.py
# --------------------------------------------------------------------------

def bangun_aturan() -> str:
    """Terjemahkan rubrik.PITA jadi teks aturan untuk model."""
    bagian = []
    for komponen, maks in rubrik.MAKS_KOMPONEN.items():
        baris = [f"### {komponen}  (maksimum {maks} poin)"]
        for nilai, label, penjelasan, sumber in rubrik.PITA[komponen]:
            baris.append(f'- label "{label}" = {nilai} poin')
            baris.append(f"    {penjelasan}")
            baris.append(f"    biasanya terlihat di: {sumber}")
        bagian.append("\n".join(baris))
    return "\n\n".join(bagian)


SISTEM = """Kamu menilai apakah sebuah perusahaan Indonesia MEMBUTUHKAN Salesmart.

Salesmart adalah platform untuk mengelola TIM SALES LAPANGAN dan RANTAI
DISTRIBUSI FISIK. Jadi yang dinilai adalah apakah perusahaan itu punya orang
yang bekerja di lapangan dan barang yang berpindah lewat jaringan — BUKAN
seberapa besar atau seberapa terkenal perusahaannya.

Konsekuensi yang harus kamu pegang: perusahaan digital besar seperti
marketplace atau agen perjalanan daring skornya RENDAH, karena mereka tidak
punya tim kanvas yang perlu dilacak. Perusahaan manufaktur menengah yang
tidak terkenal bisa skornya TINGGI.

Kamu diberi teks halaman-halaman dari situs resmi perusahaan. Untuk setiap
komponen, pilih SATU label dari daftar di bawah.

ATURAN BUKTI — ini yang paling penting:
- Kutip kalimat ASLI dari teks yang diberikan sebagai alasan penilaianmu.
  Kutipan harus verbatim, disalin persis.
- Kalau tidak ada kalimat yang mendukung, kosongkan kutipan dan pilih pita
  TERENDAH yang masih bisa dipertahankan. Jangan menebak dari nama
  perusahaan atau dari yang kamu tahu di luar teks ini.
- Tidak adanya bukti BUKAN bukti ketiadaan. Kalau halaman yang tersedia
  memang tidak membahas suatu topik, katakan begitu lewat keyakinan
  "rendah" — jangan mengarang.

PITA PENILAIAN:

{aturan}
"""


# --------------------------------------------------------------------------
# Skema keluaran
# --------------------------------------------------------------------------

def bangun_skema():
    """Skema JSON hasil penilaian, labelnya diambil dari rubrik.PITA."""
    prop = {}
    for komponen in rubrik.MAKS_KOMPONEN:
        label_sah = [lab for _, lab, _, _ in rubrik.PITA[komponen]]
        prop[komponen] = {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": label_sah},
                "kutipan": {
                    "type": "string",
                    "description": "kalimat verbatim dari teks; kosongkan kalau tidak ada",
                },
                "sumber_url": {"type": "string"},
                "keyakinan": {
                    "type": "string",
                    "enum": ["tinggi", "sedang", "rendah"],
                },
            },
            "required": ["label", "kutipan", "sumber_url", "keyakinan"],
            "additionalProperties": False,
        }
    prop["catatan"] = {
        "type": "string",
        "description": "satu kalimat: kenapa perusahaan ini butuh / tidak butuh Salesmart",
    }
    return {
        "type": "object",
        "properties": prop,
        "required": list(rubrik.MAKS_KOMPONEN) + ["catatan"],
        "additionalProperties": False,
    }


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS kebutuhan (
    nama_normal    TEXT PRIMARY KEY,
    nama           TEXT NOT NULL,
    website        TEXT,
    dist_model     INTEGER,
    field_sales    INTEGER,
    scale          INTEGER,
    industry_fit   INTEGER,
    need_score     INTEGER,
    rincian        TEXT,      -- JSON: label, kutipan, sumber, keyakinan
    catatan        TEXT,
    model          TEXT,
    dinilai_pada   TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def muat_perusahaan(db_path: str) -> list[dict]:
    """Kelompokkan halaman_bukti per perusahaan."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    baris = con.execute(
        "SELECT nama_normal, nama, website, jenis, url, teks "
        "FROM halaman_bukti ORDER BY nama_normal, jenis"
    ).fetchall()
    con.close()

    per: dict[str, dict] = {}
    for r in baris:
        p = per.setdefault(r["nama_normal"], {
            "nama_normal": r["nama_normal"], "nama": r["nama"],
            "website": r["website"], "halaman": [],
        })
        p["halaman"].append({"jenis": r["jenis"], "url": r["url"],
                             "teks": r["teks"]})
    return list(per.values())


def rakit_dokumen(p: dict) -> str:
    """Gabungkan halaman jadi satu dokumen, dengan batas ukuran."""
    bagian, total = [], 0
    for h in p["halaman"]:
        teks = (h["teks"] or "")[:MAKS_CHAR_PER_HALAMAN]
        if total + len(teks) > MAKS_CHAR_PER_PERUSAHAAN:
            break
        bagian.append(f"--- halaman [{h['jenis']}] {h['url']}\n{teks}")
        total += len(teks)
    return "\n\n".join(bagian)


def simpan(db_path: str, p: dict, hasil: dict):
    skor = {k: rubrik.nilai_pita(k, hasil[k]["label"])
            for k in rubrik.MAKS_KOMPONEN}
    need = sum(skor.values())

    con = sqlite3.connect(db_path)
    con.execute(DDL)
    con.execute(
        """INSERT OR REPLACE INTO kebutuhan
           (nama_normal, nama, website, dist_model, field_sales, scale,
            industry_fit, need_score, rincian, catatan, model)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (p["nama_normal"], p["nama"], p["website"],
         skor["dist_model"], skor["field_sales"], skor["scale"],
         skor["industry_fit"], need,
         json.dumps({k: hasil[k] for k in rubrik.MAKS_KOMPONEN},
                    ensure_ascii=False),
         hasil.get("catatan", ""), MODEL),
    )
    con.commit()
    con.close()
    return skor, need


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="../data/leads.db",
                    help="tempat HASIL penilaian ditulis (tabel kebutuhan)")
    ap.add_argument("--db-bukti", default="../data/bukti.db",
                    help="tempat teks halaman DIBACA (tabel halaman_bukti)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="tampilkan prompt dan perkiraan biaya, JANGAN panggil API")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    sistem = SISTEM.format(aturan=bangun_aturan())
    perusahaan = muat_perusahaan(args.db_bukti)
    if not perusahaan:
        print(f"Tabel halaman_bukti kosong di {args.db_bukti}.")
        print("Jalankan panen_bukti.py dulu.")
        raise SystemExit(1)
    if args.limit:
        perusahaan = perusahaan[: args.limit]

    # ---------------- dry-run: tunjukkan biaya sebelum keluar duit --------
    if args.dry_run:
        print("=" * 74)
        print("PROMPT SISTEM (sama untuk semua perusahaan — inilah yang di-cache)")
        print("=" * 74)
        print(sistem)
        print("=" * 74)
        print(f"PERKIRAAN — {len(perusahaan)} perusahaan, model {args.model}")
        print("=" * 74)
        # ~4 karakter per token untuk campuran Indonesia/Inggris. Kasar,
        # tapi cukup untuk tahu ini receh atau mahal.
        tok_sistem = len(sistem) // 4
        tok_dok = sum(len(rakit_dokumen(p)) for p in perusahaan) // 4
        tok_out = len(perusahaan) * 400
        print(f"  token sistem (per panggilan)  {tok_sistem:>9,}")
        print(f"  token dokumen (total)         {tok_dok:>9,}")
        print(f"  token keluaran (perkiraan)    {tok_out:>9,}")
        tanpa_cache = ((tok_sistem * len(perusahaan) + tok_dok) / 1e6 * HARGA_INPUT
                       + tok_out / 1e6 * HARGA_OUTPUT)
        dengan_cache = ((tok_sistem / 1e6 * HARGA_INPUT)
                        + (tok_sistem * (len(perusahaan) - 1) / 1e6 * HARGA_INPUT_CACHE_BACA)
                        + tok_dok / 1e6 * HARGA_INPUT
                        + tok_out / 1e6 * HARGA_OUTPUT)
        print(f"\n  tanpa prompt caching          ${tanpa_cache:>8.3f}")
        print(f"  dengan prompt caching         ${dengan_cache:>8.3f}")
        print("\n  Untuk ribuan perusahaan, pakai Message Batches API —")
        print("  harganya separuh dan pekerjaan ini tidak butuh jawaban cepat.")
        print("\nBelum ada API yang dipanggil. Hapus --dry-run untuk menilai.")
        for p in perusahaan[:1]:
            print("\n" + "=" * 74)
            print(f"CONTOH DOKUMEN — {p['nama']} ({len(p['halaman'])} halaman)")
            print("=" * 74)
            print(rakit_dokumen(p)[:1500] + "\n[...dipotong...]")
        return

    # ---------------- penilaian sungguhan ---------------------------------
    try:
        import anthropic
    except ImportError:
        print("Paket 'anthropic' belum terpasang.  pip install anthropic")
        raise SystemExit(1)

    client = anthropic.Anthropic()
    skema = bangun_skema()

    print(f"{'perusahaan':<34}{'dist':>5}{'field':>6}{'scale':>6}{'fit':>5}{'NEED':>6}")
    print("-" * 62)

    for p in perusahaan:
        dokumen = rakit_dokumen(p)
        resp = client.messages.create(
            model=args.model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            # Blok sistem ditandai cache: isinya sama persis tiap panggilan,
            # jadi hanya dibayar penuh sekali.
            system=[{"type": "text", "text": sistem,
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": skema}},
            messages=[{"role": "user", "content":
                       f"Perusahaan: {p['nama']}\nSitus: {p['website']}\n\n{dokumen}"}],
        )
        teks = "".join(b.text for b in resp.content if b.type == "text")
        hasil = json.loads(teks)
        skor, need = simpan(args.db, p, hasil)
        print(f"{p['nama'][:33]:<34}{skor['dist_model']:>5}{skor['field_sales']:>6}"
              f"{skor['scale']:>6}{skor['industry_fit']:>5}{need:>6}")

    print(f"\nHasil tersimpan di tabel 'kebutuhan' pada {args.db}")


if __name__ == "__main__":
    sys.exit(main())
