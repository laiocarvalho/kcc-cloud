"""
Entry point used instead of kcc/kcc-c2e.py (same CLI, same behaviour) with one fix
applied at runtime, so the upstream KCC submodule stays untouched.

Fix: with --customwidth/--customheight KCC renames the profile to "Custom", and
comic2ebook.buildOPF() then skips the Kindle fixed-layout metadata
(original-resolution, book-type=comic, ...) because of
``if options.iskindle and options.profile != 'Custom'``. KindleGen rejects such
books with "E34002: Please specify the Original-resolution metadata value" and
KCC leaves only the EPUB behind. The wrapper makes buildOPF treat a Kindle
"Custom" profile like a normal Kindle profile; original-resolution is then the
custom width x height (options.profileData[1]).
"""

import os
import sys

KCC_DIR = os.environ.get(
    "KCC_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kcc")
)
if KCC_DIR not in sys.path:
    sys.path.insert(0, KCC_DIR)


def _patch_custom_kindle_profile():
    from functools import wraps

    from kindlecomicconverter import comic2ebook

    original = comic2ebook.buildOPF
    if getattr(original, "_kcc_cloud_patched", False):
        return

    @wraps(original)
    def build_opf(*args, **kwargs):
        opts = comic2ebook.options
        if getattr(opts, "iskindle", False) and getattr(opts, "profile", None) == "Custom":
            opts.profile = "CustomKindle"  # anything but "Custom" passes the check
            try:
                return original(*args, **kwargs)
            finally:
                opts.profile = "Custom"
        return original(*args, **kwargs)

    build_opf._kcc_cloud_patched = True
    comic2ebook.buildOPF = build_opf


if __name__ == "__main__":
    if sys.version_info < (3, 8, 0):
        print("ERROR: This is a Python 3.8+ script!")
        sys.exit(1)

    from multiprocessing import freeze_support, set_start_method

    from kcc import modify_path
    from kindlecomicconverter.startup import startC2E

    modify_path()
    set_start_method("spawn")
    freeze_support()
    _patch_custom_kindle_profile()
    startC2E()
