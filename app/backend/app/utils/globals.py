import os

UPLOADS_DIRECTORY = "/tmp"  # Volume-mounted directory
# Wrapper around kcc/kcc-c2e.py that fixes MOBI output with custom width/height
# (see kcc_c2e_wrapper.py). Set KCC_PATH=/app/kcc/kcc-c2e.py to run plain upstream KCC.
KCC_PATH = os.environ.get("KCC_PATH", "/app/kcc_c2e_wrapper.py")
