"""Zip src/carevista (with its sql/ folder) for the Glue jobs (used by deploy.sh)."""

import os
import sys
import zipfile

src, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for base, dirs, files in os.walk(os.path.join(src, "carevista")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".pyc"):
                path = os.path.join(base, f)
                zf.write(path, os.path.relpath(path, src))
print(f"packaged {out}")
