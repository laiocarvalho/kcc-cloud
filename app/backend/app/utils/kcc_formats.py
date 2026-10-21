"""
Helpers that keep the KCC command and its output consistent with the output
format the user picked.

Background (KCC 9.4.2, app/backend/app/kcc):
- ``-f/--format`` accepts Auto, MOBI, EPUB, CBZ, KFX, MOBI+EPUB, PDF (plus the
  EPUB-200MB / MOBI+EPUB-200MB variants). ``Auto`` resolves to MOBI for Kindle
  profiles, CBZ for KDX, PDF for reMarkable and EPUB for everything else.
- Passing ``--customwidth``/``--customheight`` makes KCC replace the device
  profile with a synthetic profile called ``Custom``. ``buildOPF`` only writes the
  Kindle fixed-layout metadata (including ``original-resolution``) when
  ``options.profile != 'Custom'``, so KindleGen then aborts with
  ``E34002: Please specify the Original-resolution metadata value``. KCC still
  exits with status 0 and leaves the intermediate ``.epub`` behind.
  kcc_c2e_wrapper.py fixes that at runtime; this module additionally avoids the
  "Custom" profile when the custom size equals the device's native size, and lets
  the task detect a missing deliverable instead of shipping the leftover EPUB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Native screen resolution of KCC's Kindle profiles (kindlecomicconverter/image.py,
# ProfileData.ProfilesKindle, KCC 9.4.2).
KINDLE_PROFILE_RESOLUTIONS: Dict[str, Tuple[int, int]] = {
    "K1": (600, 670),
    "K2": (600, 670),
    "KDX": (824, 1000),
    "K34": (600, 800),
    "K57": (600, 800),
    "KPW": (758, 1024),
    "KV": (1072, 1448),
    "KPW34": (1072, 1448),
    "K810": (600, 800),
    "KO": (1264, 1680),
    "K11": (1072, 1448),
    "KPW5": (1236, 1648),
    "KS1860": (1860, 1920),
    "KS1920": (1920, 1920),
    "KS": (1860, 2480),
    "KCS": (1264, 1680),
    "KS3": (1986, 2648),
    "KSCS": (1986, 2648),
}

REMARKABLE_PROFILES = {"Rmk1", "Rmk2", "RmkPP", "RmkPPMove"}

# Canonical KCC values for -f, keyed by upper-case user input.
KCC_FORMATS: Dict[str, str] = {
    "AUTO": "Auto",
    "MOBI": "MOBI",
    "EPUB": "EPUB",
    "CBZ": "CBZ",
    "KFX": "KFX",
    "PDF": "PDF",
    "MOBI+EPUB": "MOBI+EPUB",
    "EPUB-200MB": "EPUB-200MB",
    "MOBI+EPUB-200MB": "MOBI+EPUB-200MB",
}

MOBI_FORMATS = {"MOBI", "MOBI+EPUB", "MOBI+EPUB-200MB"}


class ConversionOptionsError(ValueError):
    """Invalid conversion options (e.g. unknown output format)."""


class ConversionOutputError(RuntimeError):
    """KCC finished but did not produce the requested format."""


def kcc_profile(device_profile: Optional[str]) -> str:
    """Profile id that is actually passed to KCC (mirrors command_generator)."""
    if not device_profile:
        return "KV"  # KCC's own default profile
    if device_profile.upper() == "OTHER":
        return "KV"
    return device_profile


def normalize_output_format(value) -> Optional[str]:
    """Return KCC's canonical -f value, or None for Auto/empty. Raise on unknown values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    canonical = KCC_FORMATS.get(text.upper())
    if canonical is None:
        raise ConversionOptionsError(
            f"Unsupported output format '{text}'. "
            f"Use one of: {', '.join(sorted(set(KCC_FORMATS.values())))}"
        )
    return None if canonical == "Auto" else canonical


def effective_format(output_format: Optional[str], device_profile: Optional[str]) -> str:
    """Format KCC will really build, resolving Auto the same way KCC does."""
    fmt = normalize_output_format(output_format)
    if fmt:
        return fmt
    profile = kcc_profile(device_profile)
    if profile == "KDX":
        return "CBZ"
    if profile in KINDLE_PROFILE_RESOLUTIONS:
        return "MOBI"
    if profile in REMARKABLE_PROFILES:
        return "PDF"
    return "EPUB"


def expected_extensions(fmt: str, device_profile: Optional[str], no_kepub: bool = False) -> List[str]:
    """Extensions of the deliverable files for an effective format, primary first."""
    profile = kcc_profile(device_profile)
    if fmt in MOBI_FORMATS:
        return [".mobi", ".epub"] if "+EPUB" in fmt else [".mobi"]
    if fmt == "CBZ":
        return [".cbz"]
    if fmt == "PDF":
        return [".pdf"]
    # EPUB, EPUB-200MB and KFX (KCC builds a KFX-ready EPUB)
    if "Ko" in profile and fmt != "KFX" and not no_kepub:
        return [".kepub.epub"]
    return [".epub"]


def sanitize_custom_resolution(
    device_profile: Optional[str], options: Optional[Dict]
) -> Tuple[Dict, List[str]]:
    """
    Drop empty custom width/height and values that only repeat the profile's native
    resolution, so KCC keeps the real device profile instead of switching to its
    synthetic "Custom" profile. Real custom sizes are kept: kcc_c2e_wrapper.py makes
    KCC write the Kindle metadata for them, so MOBI works with them as well.

    Returns (options_copy, notes). The input dict is not modified.
    """
    opts = dict(options or {})
    notes: List[str] = []
    profile = kcc_profile(device_profile)
    native = KINDLE_PROFILE_RESOLUTIONS.get(profile)

    def _as_int(v):
        try:
            return int(float(v)) if v not in (None, "") else 0
        except (TypeError, ValueError):
            return 0

    width = _as_int(opts.get("custom_width"))
    height = _as_int(opts.get("custom_height"))
    if width <= 0:
        opts.pop("custom_width", None)
        width = 0
    if height <= 0:
        opts.pop("custom_height", None)
        height = 0

    if native and (width or height) and (width or native[0], height or native[1]) == native:
        opts.pop("custom_width", None)
        opts.pop("custom_height", None)
        notes.append(
            f"Custom resolution {native[0]}x{native[1]} equals the native resolution of "
            f"profile {profile}; not passing --customwidth/--customheight to KCC."
        )
    return opts, notes


def kcc_error_lines(lines: Iterable[str]) -> List[str]:
    """Error lines KCC printed (it often exits 0 even when KindleGen failed)."""
    errors = []
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()
        if "error:" in low or "error(" in low or low.startswith("error"):
            errors.append(stripped)
    return errors


def pick_outputs(files: Iterable[Path], expected_exts: List[str]) -> List[Path]:
    """Files in KCC's output dir matching the expected deliverable extensions, primary first."""
    files = sorted(
        (f for f in files if f.is_file() and not f.name.startswith(".")), key=lambda p: p.name
    )
    picked: List[Path] = []
    for ext in expected_exts:
        for f in files:
            name = f.name.lower()
            if not name.endswith(ext):
                continue
            # '.epub' must not swallow '.kepub.epub' and vice versa
            if ext == ".epub" and name.endswith(".kepub.epub"):
                continue
            if f not in picked:
                picked.append(f)
    return picked
