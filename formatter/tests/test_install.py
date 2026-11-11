"""The formatter must work when installed as a wheel, outside the source checkout."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

setuptools = pytest.importorskip("setuptools")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(int(setuptools.__version__.split(".")[0]) < 61, reason="needs setuptools>=61 (pip install -r requirements.txt)")
def test_installed_package_finds_its_vocabulary(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns("tests", "build", "*.egg-info", "__pycache__", ".pytest_cache"))
    target = tmp_path / "site"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--no-build-isolation",
                    "--target", str(target), str(src)], check=True)
    shutil.rmtree(src)  # nothing may be read from the source tree
    code = "from banglish_formatter import format_note as f; r = f('alu 50 tk, dim 30 tk'); print(r['result'])"
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env={"PYTHONPATH": str(target)},
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "alu - 50\ndim - 30\ntotal - 80"
