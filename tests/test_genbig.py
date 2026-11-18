"""scripts/genbig.py: generador de árboles de texto voluminoso (relleno real) para el World."""

import subprocess
import sys
from pathlib import Path

GENBIG = Path(__file__).resolve().parents[1] / "scripts" / "genbig.py"


def test_genbig_generates_tree_with_custom_subdirs(tmp_path):
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(
        "This is a paragraph long enough to exceed the eighty-character threshold and "
        "serve as realistic filler material for the unit tests.\n\n"
        "A second paragraph, also long, so the generator has a variety of blocks to "
        "choose from when mixing the content of the files produced by the process.\n\n",
        encoding="utf-8",
    )
    out = tmp_path / "data"
    r = subprocess.run(
        [
            sys.executable, str(GENBIG), str(out),
            "--files", "4", "--size", "64K",
            "--subdirs", "2", "--subdir-prefix", "", "--subdir-width", "2", "--subdir-start", "23",
            "--corpus", str(corpus), "--seed", "1",
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "23").is_dir() and (out / "24").is_dir()  # naming de subdirs personalizado
    files = sorted(out.rglob("*.txt"))
    assert len(files) == 4
    for f in files:
        assert f.stat().st_size == 64 * 1024  # tamaño exacto por fichero
    assert "paragraph" in files[0].read_text(encoding="utf-8", errors="ignore")  # texto real del corpus
