"""Output format handling: -f flag, custom resolution vs MOBI, output selection."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from utils.command_generator import generate_kcc_command
from utils.kcc_formats import (
    ConversionOptionsError,
    effective_format,
    expected_extensions,
    kcc_error_lines,
    normalize_output_format,
    pick_outputs,
    sanitize_custom_resolution,
)


def _cmd(profile, options):
    return generate_kcc_command("/in/book.cbz", "/out", device_profile=profile, options=options)


@pytest.mark.parametrize(
    "value,flag",
    [("MOBI", "MOBI"), ("mobi", "MOBI"), ("EPUB", "EPUB"), ("CBZ", "CBZ"), ("PDF", "PDF"),
     ("KFX", "KFX"), ("MOBI+EPUB", "MOBI+EPUB"), ("mobi+epub", "MOBI+EPUB")],
)
def test_output_format_reaches_command(value, flag):
    cmd = _cmd("KPW5", {"manga_style": True, "output_format": value})
    assert cmd[cmd.index("-f") + 1] == flag


@pytest.mark.parametrize("value", ["Auto", "auto", "", None])
def test_auto_or_empty_format_is_not_sent(value):
    assert "-f" not in _cmd("KPW5", {"output_format": value})


def test_unknown_format_is_rejected():
    with pytest.raises(ConversionOptionsError):
        _cmd("KPW5", {"output_format": "AZW9"})


def test_native_custom_resolution_is_dropped():
    # Exactly the failing job from the logs
    cmd = _cmd("KPW5", {"manga_style": True, "hq": True, "custom_width": 1236,
                        "custom_height": 1648, "output_format": "MOBI"})
    assert "--customwidth" not in cmd and "--customheight" not in cmd
    assert cmd[cmd.index("-p") + 1] == "KPW5"
    assert cmd[cmd.index("-f") + 1] == "MOBI"


def test_native_resolution_dropped_with_auto_format_too():
    cmd = _cmd("KPW5", {"custom_width": 1236, "custom_height": 1648})
    assert "--customwidth" not in cmd


def test_real_custom_resolution_is_kept_for_mobi():
    cmd = _cmd("KPW5", {"custom_width": 1000, "custom_height": 1400, "output_format": "MOBI"})
    assert cmd[cmd.index("--customwidth") + 1] == "1000"
    assert cmd[cmd.index("--customheight") + 1] == "1400"
    assert cmd[cmd.index("-f") + 1] == "MOBI"


def test_real_custom_resolution_kept_for_non_mobi():
    cmd = _cmd("OTHER", {"custom_width": 1000, "custom_height": 1400, "output_format": "EPUB"})
    assert cmd[cmd.index("--customwidth") + 1] == "1000"
    assert cmd[cmd.index("-p") + 1] == "KV"
    cmd = _cmd("KoC", {"custom_width": 1000, "custom_height": 1400})
    assert "--customwidth" in cmd


def test_command_uses_wrapper_by_default():
    assert _cmd("KPW5", {})[1].endswith("kcc_c2e_wrapper.py")


def test_sanitize_does_not_mutate_input():
    opts = {"custom_width": 1236, "custom_height": 1648}
    sanitize_custom_resolution("KPW5", opts)
    assert opts == {"custom_width": 1236, "custom_height": 1648}


def test_effective_format_and_extensions():
    assert normalize_output_format("Auto") is None
    assert effective_format(None, "KPW5") == "MOBI"
    assert effective_format(None, "KoC") == "EPUB"
    assert effective_format(None, "Rmk2") == "PDF"
    assert effective_format(None, "KDX") == "CBZ"
    assert effective_format("epub", "KPW5") == "EPUB"
    assert expected_extensions("MOBI", "KPW5") == [".mobi"]
    assert expected_extensions("MOBI+EPUB", "KPW5") == [".mobi", ".epub"]
    assert expected_extensions("EPUB", "KoC") == [".kepub.epub"]
    assert expected_extensions("EPUB", "KoC", no_kepub=True) == [".epub"]
    assert expected_extensions("KFX", "KPW5") == [".epub"]


def test_pick_outputs_ignores_leftover_epub(tmp_path):
    (tmp_path / "book.epub").write_text("x")
    assert pick_outputs(tmp_path.iterdir(), [".mobi"]) == []
    (tmp_path / "book.mobi").write_text("x")
    assert [p.name for p in pick_outputs(tmp_path.iterdir(), [".mobi"])] == ["book.mobi"]
    assert [p.name for p in pick_outputs(tmp_path.iterdir(), [".mobi", ".epub"])] == [
        "book.mobi", "book.epub"]


def test_kcc_error_lines():
    lines = [
        "Creating MOBI files...",
        "Error: KindleGen failed to create MOBI!",
        "[1, 'Error(opfparser):E34002: Please specify the Original-resolution ...', 'x.epub']",
        "makeBook: 2.0 seconds",
    ]
    assert len(kcc_error_lines(lines)) == 2


# --- End-to-end with the real KCC + KindleGen (skipped when kindlegen is missing) ---

KCC_SCRIPT = Path(__file__).resolve().parents[1] / "app" / "kcc" / "kcc-c2e.py"


def _make_cbz(path: Path):
    from PIL import Image, ImageDraw

    with zipfile.ZipFile(path, "w") as zf:
        for i in range(1, 9):
            size = (3400, 2400) if i % 4 == 0 else (1700, 2400)  # include double-page spreads
            img = Image.new("L", size, 255)
            draw = ImageDraw.Draw(img)
            for k in range(20):
                x, y = (k * 151) % (size[0] - 300), (k * 97) % (size[1] - 300)
                draw.rectangle([x, y, x + 250, y + 250], outline=0, width=8)
            tmp = path.parent / f"p{i:02d}.jpg"
            img.save(tmp, quality=85)
            zf.write(tmp, arcname=tmp.name)
            tmp.unlink()


WRAPPER = Path(__file__).resolve().parents[1] / "app" / "kcc_c2e_wrapper.py"


@pytest.mark.skipif(shutil.which("kindlegen") is None or not KCC_SCRIPT.exists(),
                    reason="needs kindlegen in PATH and the KCC submodule")
@pytest.mark.parametrize("profile,width,height", [
    ("KPW5", 1236, 1648),   # the job from the logs (native size)
    ("KPW5", 1000, 1400),   # a real custom size
    ("OTHER", 1236, 1648),  # 'Other' profile -> KV + custom size
])
def test_mobi_is_produced_with_custom_size(tmp_path, profile, width, height):
    src = tmp_path / "book.cbz"
    _make_cbz(src)
    out = tmp_path / "out"
    out.mkdir()
    cmd = generate_kcc_command(str(src), str(out), device_profile=profile, options={
        "manga_style": True, "hq": True, "custom_width": width, "custom_height": height,
        "output_format": "MOBI"})
    cmd[0] = sys.executable
    cmd[1] = str(WRAPPER)
    env = dict(os.environ, TMPDIR=str(out), TMP=str(out), TEMP=str(out))
    res = subprocess.run(cmd, cwd=out, env=env, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stdout + res.stderr
    produced = pick_outputs(out.iterdir(), expected_extensions("MOBI", profile))
    assert [p.suffix for p in produced] == [".mobi"], res.stdout
    assert not kcc_error_lines(res.stdout.splitlines())
