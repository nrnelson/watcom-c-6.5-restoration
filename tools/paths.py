"""paths.py - where everything lives, and access to the original zip.

All locations are inside the repository unless overridden:

  Watcom C.ver.6.5.English.zip   the original archive (WCR_ZIP to override)
  build/                         work files, made by the tools (WCR_BUILD)
  build/watcom/                  Watcom C 6.5 installed from the zip
  build/objects/                 recompiled small/compact modules
  out/                           the restored CLIBS.LIB, CLIBC.LIB and
                                 PROVENANCE.csv

Nothing outside the repository is written.  The zip is only read.
"""

import hashlib
import os
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))
ZIP_NAME = 'Watcom C.ver.6.5.English.zip'
ZIP = os.getenv('WCR_ZIP', os.path.join(ROOT, ZIP_NAME))
BUILD = os.getenv('WCR_BUILD', os.path.join(ROOT, 'build'))
WATCOM = os.path.join(BUILD, 'watcom')
OBJECTS = os.path.join(BUILD, 'objects')
OUT = os.path.join(ROOT, 'out')

# The only copy of Watcom C 6.5 found (see README.md).
ZIP_SHA256 = '76b2ebc8ec730ee1151b1c1f9193460b8cfc03dacec5d567573296f3a537eca6'
ZIP_SIZE = 1286189

# Where each library is in the zip.
DISK = {'S': 'DISK4/CLIBS.LIB', 'C': 'DISK4/CLIBC.LIB',
        'M': 'DISK4/CLIBM.LIB', 'L': 'DISK5/CLIBL.LIB',
        'H': 'DISK5/CLIBH.LIB'}

_cache = {}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 16), b''):
            h.update(block)
    return h.hexdigest()


def check_zip(path=None):
    """Raise SystemExit with an explanation unless path is the known zip."""
    path = path or ZIP
    if not os.path.isfile(path):
        raise SystemExit(
            'zip not found: %s\n(download "%s" as README.md describes, put '
            'it in the repository folder, or give its path)' %
            (path, ZIP_NAME))
    digest = sha256_file(path)
    if digest != ZIP_SHA256:
        raise SystemExit('%s: SHA-256 %s, expected %s: not the known Watcom '
                         'C 6.5 archive' % (path, digest, ZIP_SHA256))
    return path


def zip_files(path=None):
    """{name: bytes} of every file in the zip (read once)."""
    path = path or ZIP
    if path not in _cache:
        files = {}
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir():
                    files[info.filename] = z.read(info)
        _cache[path] = files
    return _cache[path]


def library_bytes(key, path=None):
    """Bytes of CLIB<key>.LIB (key S, C, M, L or H) from the zip."""
    return zip_files(path)[DISK[key]]


def library(key, path=None):
    """omf.Lib of CLIB<key>.LIB, read from the zip."""
    import omf
    return omf.Lib.from_bytes(library_bytes(key, path))
