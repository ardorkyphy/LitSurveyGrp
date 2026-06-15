import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_SRC = ROOT / "apps" / "desktop" / "src"
SPEC_PATH = ROOT / "apps" / "desktop" / "LitSurveyGrp.spec"


def test_desktop_launcher_import_is_lightweight():
    script = (
        "import sys; "
        f"sys.path.insert(0, {str(DESKTOP_SRC)!r}); "
        "import desktop_launcher; "
        "assert 'litsurveygrp.pipeline' not in sys.modules"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_pyinstaller_spec_uses_lightweight_onedir_distribution():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "COLLECT(" in spec
    assert "exclude_binaries=True" in spec
    assert "'PyQt5'" in spec
    assert "'IPython'" in spec
    assert "'pytest'" in spec
    assert "'sphinx'" in spec
    assert "'torch'" in spec
    assert "'sentence_transformers'" in spec
    assert "'apps/web/dist'" in spec
