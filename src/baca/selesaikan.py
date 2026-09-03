"""
baca/selesaikan.py
==================
Langkah terakhir alur baca, dijadikan SATU perintah: gabungkan hasil
pemeriksa, verifikasi kutipannya, tulis ke database, bangkitkan ulang
seluruh tampilan.

Pakai:
    python src/baca/selesaikan.py --dir kerja/b1            # periksa saja
    python src/baca/selesaikan.py --dir kerja/b1 --tulis    # tulis + bangkitkan

KENAPA ADA:
    Sampai 3 Sep 2026 empat langkah terakhir diketik satu-satu: terapkan
    (periksa), terapkan (tulis), buat_antrian, buat_dashboard, ekspor_csv.
    Lupa satu langkah tidak menimbulkan error — ia cuma membuat dasbor
    menampilkan angka kemarin, dan itu jenis kesalahan yang tidak
    kelihatan sampai seseorang bertanya "kok tidak berubah?".

KENAPA HASILNYA PER PERUSAHAAN, LALU DIGABUNG DI SINI:
    Tiap pemeriksa menulis `hasil-<slug>.json` sendiri. Kalau semuanya
    menulis ke satu `hasil.json`, dua agen yang jalan bersamaan akan
    saling menimpa — dan yang hilang tidak akan terlihat, karena berkas
    yang tersisa tetap JSON yang sah. Penggabungan dikerjakan di sini,
    setelah semua agen selesai.

MODE --tulis TETAP MENOLAK JALAN kalau ada kutipan yang gagal verifikasi.
Itu ditegakkan terapkan.py; modul ini tidak melonggarkannya, cuma
meneruskan kode keluarnya.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Dibangkitkan ulang setiap kali database berubah. Urutannya penting:
# antrian dan dasbor membaca database, ekspor CSV membaca database yang
# sama supaya diff-nya terbaca git.
TAMPILAN = ["buat_antrian.py", "buat_dashboard.py", "ekspor_csv.py"]


def gabung(folder: Path) -> int:
    """Satukan hasil-*.json jadi hasil.json. Return jumlah perusahaan."""
    potongan = sorted(folder.glob("hasil-*.json"))
    if not potongan:
        if (folder / "hasil.json").exists():
            isi = json.loads((folder / "hasil.json").read_text(encoding="utf-8"))
            return len(isi)
        raise SystemExit(
            f"Tidak ada hasil-*.json maupun hasil.json di {folder}.\n"
            "Agen pemeriksa belum jalan, atau menulis ke tempat lain."
        )

    semua, terlihat = [], set()
    for f in potongan:
        isi = json.loads(f.read_text(encoding="utf-8"))
        for h in (isi if isinstance(isi, list) else [isi]):
            kunci = h.get("nama_normal") or h.get("nama")
            if kunci in terlihat:
                print(f"  LEWAT (dobel): {kunci} dari {f.name}", flush=True)
                continue
            terlihat.add(kunci)
            semua.append(h)

    (folder / "hasil.json").write_text(
        json.dumps(semua, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(potongan)} berkas pemeriksa -> hasil.json "
          f"({len(semua)} perusahaan)", flush=True)
    return len(semua)


def jalankan(skrip: str, *argumen: str) -> int:
    perintah = [sys.executable, str(BASE / "src" / skrip), *argumen]
    # flush wajib: keluaran anak proses ditulis langsung ke terminal,
    # sedangkan print induk masuk buffer. Tanpa ini judul langkah muncul
    # SETELAH keluaran langkahnya, dan lognya terbaca terbalik.
    print(f"\n$ {' '.join(perintah[1:])}", flush=True)
    return subprocess.run(perintah, cwd=BASE).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="folder dari siapkan.py")
    ap.add_argument("--tulis", action="store_true",
                    help="tulis ke database dan bangkitkan ulang tampilan")
    ap.add_argument("--model", default="agen pembaca+pemeriksa")
    args = ap.parse_args()

    folder = Path(args.dir)
    if not folder.exists():
        raise SystemExit(f"Folder tidak ada: {folder}")

    gabung(folder)

    kode = jalankan("baca/terapkan.py", "--dir", args.dir,
                    *(["--tulis"] if args.tulis else []),
                    "--model", args.model)
    if kode != 0:
        raise SystemExit(
            "\nterapkan.py menolak. Database TIDAK disentuh dan tampilan "
            "TIDAK dibangkitkan ulang — perbaiki kutipannya dulu.")

    if not args.tulis:
        print("\n(mode periksa. Tambahkan --tulis untuk menulis dan "
              "membangkitkan ulang tampilan.)")
        return

    for skrip in TAMPILAN:
        if jalankan(skrip) != 0:
            raise SystemExit(f"\n{skrip} gagal. Database SUDAH ditulis, "
                             f"tapi tampilan belum lengkap — jalankan "
                             f"sisanya sendiri.")

    print("\nSelesai: database ditulis, antrian + dasbor + CSV dibangkitkan "
          "ulang.")


if __name__ == "__main__":
    main()
