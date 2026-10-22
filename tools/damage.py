"""damage.py - map the foreign 512-byte sectors of the damaged libraries.

usage: python3 -I tools/damage.py [ZIP] [LIB ...]

Reads every file of the Watcom C 6.5 zip and, for each 512-byte sector of
each named library (default DISK4/CLIBS.LIB DISK4/CLIBC.LIB), looks for the
same 512 bytes in every other file of the distribution: first at the same
offset, then at any offset.  Prints the runs of sectors that are "own" (no
match elsewhere), "same" (match at the same offset in another file) or
"moved" (match elsewhere at another offset), and marks those taken to be
foreign (see foreign()).  Sectors of a single repeated
byte are reported as "fill" since they match too much to say anything.

A match does not by itself prove damage: CLIBS and CLIBC legitimately share
near-code modules, so a "moved" match between them may be genuine.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402

SECTOR = 512
DEFAULT = ('DISK4/CLIBS.LIB', 'DISK4/CLIBC.LIB')


def load(zpath):
    return paths.zip_files(zpath)


def index_all(files):
    """hash of every 512-byte window -> [(file, offset)]."""
    idx = {}
    for name, d in files.items():
        for o in range(0, len(d) - SECTOR + 1):
            idx.setdefault(hash(d[o:o + SECTOR]), []).append((name, o))
    return idx


def classify(name, files, idx):
    d = files[name]
    out = []
    for o in range(0, len(d), SECTOR):
        s = d[o:o + SECTOR]
        if len(set(s)) == 1:
            out.append((o, 'fill', []))
            continue
        hits = [(f, p) for f, p in idx.get(hash(s), ())
                if f != name and files[f][p:p + SECTOR] == s]
        same = [f for f, p in hits if p == o]
        if same:
            out.append((o, 'same', sorted(same)))
        elif hits:
            out.append((o, 'moved', sorted(hits)))
        else:
            out.append((o, 'own', []))
    return out


def foreign(cls):
    """Offsets of the sectors taken to be foreign: those matching another
    file at the same offset, or at a sector-aligned offset elsewhere (a
    whole sector of another file).  A match at an unaligned offset is a
    run of bytes shared by two genuine files (CLIBS and CLIBC hold some
    identical near-code modules) and is not counted."""
    out = set()
    for o, kind, src in cls:
        if kind == 'same' or (kind == 'moved' and
                              any(p % SECTOR == 0 for f, p in src)):
            out.add(o)
    # A lone "own" sector between foreign ones is foreign too, from a file
    # that is not in the distribution (in CLIBS: machine code, a ctype
    # table with "Unable to open '%s'", README-style text).
    for o, kind, src in cls:
        if kind == 'own' and o - SECTOR in out and o + SECTOR in out:
            out.add(o)
    return out


def damage_map(zpath, names=DEFAULT):
    """{library name: (bytes, set of foreign sector offsets)}"""
    files = load(zpath)
    idx = index_all(files)
    return {n: (files[n], foreign(classify(n, files, idx))) for n in names}


def runs(cls):
    """Merge consecutive sectors with the same kind and source file(s)."""
    out = []
    for o, kind, src in cls:
        if kind == 'same':
            key = tuple(src)
        elif kind == 'moved':
            key = tuple(sorted({f for f, p in src}))
        else:
            key = ()
        delta = None
        if kind == 'moved' and len(src) == 1:
            delta = src[0][1] - o
        if out and out[-1][2] == kind and out[-1][3] == key and \
                out[-1][4] == delta:
            out[-1][1] = o + SECTOR
            continue
        out.append([o, o + SECTOR, kind, key, delta])
    return out


def main(argv):
    args = argv[1:]
    zpath = args.pop(0) if args and args[0].lower().endswith('.zip') \
        else None
    files = load(paths.check_zip(zpath))
    targets = args or DEFAULT
    idx = index_all(files)
    for name in targets:
        cls = classify(name, files, idx)
        bad = foreign(cls)
        print('%s (%d bytes, %d in %d foreign sectors)'
              % (name, len(files[name]), len(bad) * SECTOR, len(bad)))
        for a, b, kind, key, delta in runs(cls):
            src = ' '.join(key)
            if delta is not None:
                src += ' (%+d)' % delta
            mark = 'FOREIGN' if a in bad else ''
            print('  %6d-%6d %-5s %-7s %s' % (a, b, kind, mark, src))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
