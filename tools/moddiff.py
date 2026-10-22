"""moddiff.py - compare one module across two libraries, record by record.

usage: python3 -I tools/moddiff.py LIB_A LIB_B NAME [-d]

LIB_A and LIB_B are library files, or S, C, M, L, H for the original
CLIB<x>.LIB read from the zip.  NAME is the module's dictionary name (e.g.
UNLINK!, case-insensitive) or its position (0-249).  Prints the decoded
records of both side by side, marking those that differ.  -d also
disassembles both with Open Watcom's wdis (optional; found on the PATH or
as WCR_WDIS; objects written to build/moddiff/) and prints a unified diff
of the two.
"""

import difflib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shutil  # noqa: E402

import omf  # noqa: E402
import omfrec  # noqa: E402
import paths  # noqa: E402

WDIS = os.getenv('WCR_WDIS') or shutil.which('wdis')
SCRATCH = os.path.join(paths.BUILD, 'moddiff')


def find(lib, name):
    """Start offset of the module called name (dictionary name or index)."""
    if name.isdigit():
        return lib.starts[int(name)]
    for s in lib.starts:
        if any(n.upper() == name.upper() for n in lib.names[s]):
            return s
    raise KeyError(name)


def module_records(lib, start):
    raw = lib.module(start)
    if raw is None:
        return None
    return omfrec.decode_module(raw)


def raw_module(lib, start):
    """The module's bytes from THEADR to MODEND (no page padding)."""
    raw = lib.module(start)
    t, b, o = raw[-1]
    return lib.data[start:o + 3 + len(b) + 1]


def disasm(data, tag):
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, tag + '.obj')
    with open(path, 'wb') as f:
        f.write(data)
    if not WDIS:
        raise SystemExit('wdis (Open Watcom) not found: install it or set '
                         'WCR_WDIS, or leave out -d')
    out = subprocess.run([WDIS, '-a', path], capture_output=True, text=True)
    return out.stdout.splitlines()


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('-')]
    if len(args) != 3:
        sys.stderr.write(__doc__)
        return 2
    la, lb = [paths.library(a.upper()) if a.upper() in paths.DISK
              else omf.Lib(a) for a in args[:2]]
    sa, sb = find(la, args[2]), find(lb, args[2])
    ra, rb = module_records(la, sa), module_records(lb, sb)
    if ra is None or rb is None:
        print('unreadable:', 'A' if ra is None else '', 'B' if rb is None else '')
        return 1
    da = [omfrec.describe(r) for r in ra]
    db = [omfrec.describe(r) for r in rb]
    for line in difflib.unified_diff(da, db, 'A', 'B', lineterm='', n=99):
        print(line)
    if '-d' in argv:
        xa = disasm(raw_module(la, sa), 'a')
        xb = disasm(raw_module(lb, sb), 'b')
        for line in difflib.unified_diff(xa, xb, 'A', 'B', lineterm='', n=3):
            print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
