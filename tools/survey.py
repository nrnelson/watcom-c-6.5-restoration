"""survey.py - which modules of the damaged libraries survive.

usage: python3 -I tools/survey.py [ZIP] [-v]

For each module of CLIBS.LIB and CLIBC.LIB (positions from the intact
dictionary) reports:
  whole    - no byte of its page span lies in a foreign sector, and its
             records parse and checksum from THEADR to MODEND
  partial  - some genuine bytes remain in its span, some are foreign
  lost     - every byte of its span is foreign
  suspect  - no foreign sector touches it but it fails to parse (would mean
             damage the sector map does not show)
and the counts per library and across both.  -v lists every module.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import damage  # noqa: E402
import omf  # noqa: E402
import paths  # noqa: E402

LIBS = (('S', 'DISK4/CLIBS.LIB'), ('C', 'DISK4/CLIBC.LIB'))


def lib_from_bytes(data):
    return omf.Lib.from_bytes(data)


def genuine_bytes(start, end, bad):
    """Number of bytes of [start, end) outside the foreign sectors."""
    n = 0
    for o in range(start, end):
        if o - o % damage.SECTOR not in bad:
            n += 1
    return n


def survey(lib, bad):
    """[(start, end, first public name, status, genuine bytes)]"""
    out = []
    for s in lib.starts:
        a, b = lib.span(s)
        g = genuine_bytes(a, b, bad)
        recs = lib.module(a)
        if g == b - a:
            status = 'whole' if recs else 'suspect'
        elif g == 0:
            status = 'lost'
        else:
            status = 'partial'
        out.append((a, b, sorted(lib.names[s])[0], status, g))
    return out


def main(argv):
    args = [a for a in argv[1:] if a != '-v']
    verbose = '-v' in argv[1:]
    zpath = paths.check_zip(args[0] if args else None)
    dm = damage.damage_map(zpath, [n for k, n in LIBS])
    res = {}
    for key, name in LIBS:
        data, bad = dm[name]
        lib = lib_from_bytes(data)
        res[key] = survey(lib, bad)
        counts = {}
        for m in res[key]:
            counts[m[3]] = counts.get(m[3], 0) + 1
        print('%s: %d modules, %s' % (name, len(res[key]), ', '.join(
            '%s %d' % kv for kv in sorted(counts.items()))))
        if verbose:
            for a, b, nm, st, g in res[key]:
                print('  %6d-%6d %-8s %4d/%4d %s' % (a, b, st, g, b - a, nm))
    s = [m[3] for m in res['S']]
    c = [m[3] for m in res['C']]
    print('not whole in both: %d; S only: %d; C only: %d; whole in both: %d'
          % (sum(x != 'whole' and y != 'whole' for x, y in zip(s, c)),
             sum(x != 'whole' and y == 'whole' for x, y in zip(s, c)),
             sum(x == 'whole' and y != 'whole' for x, y in zip(s, c)),
             sum(x == 'whole' and y == 'whole' for x, y in zip(s, c))))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
