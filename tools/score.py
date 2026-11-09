"""score.py - score the converter on the surviving small-code modules.

usage: python3 -I tools/score.py [ZIP] [ROUTE ...] [-v] [--check | --math]

ROUTE is M>S (medium -> small, default), L>C (large -> compact), or the
cross-model routes C>S and S>C.  For every module of the target library that
survives whole (tools/survey.py), the source library's module is converted
(tools/convert.py) and compared with the surviving one byte for byte, every
record from THEADR to MODEND.  The cross-model routes take the other damaged
library's module unchanged, and only where the medium and large modules have
the same code and data bytes (a module that does not depend on the data
model); the others count as "not applicable".
Prints per route: exact, differing (with the converter's notes or the first
differing record), and unsupported (the converter refused, with why).
-v lists every module.

--check (routes M>S and L>C) is the regression test to run after any change
to the converter: each route must score exactly the population of
SURVIVORS, none unsupported, and differ on exactly the modules of
EXPECTED_DIFFER, so every other survivor is exact.  Exit status 1 on any
deviation; otherwise it prints "score unchanged".

--math scores the converter outside its development set: every module of
the intact MATHS, MATHC, MATH87S and MATH87C libraries is predicted from
its MATHM/MATHL (MATH87M/MATH87L) twin, with the donor group name passed,
and compared byte for byte.  No rule was tuned on these; they test the
same compiler's output on other code.  Informative only (not frozen).
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert  # noqa: E402
import damage  # noqa: E402
import omf  # noqa: E402
import omfrec  # noqa: E402
import paths  # noqa: E402
import survey  # noqa: E402

DISKS = {'S': 'DISK4/CLIBS.LIB', 'C': 'DISK4/CLIBC.LIB',
         'M': 'DISK4/CLIBM.LIB', 'L': 'DISK5/CLIBL.LIB',
         'H': 'DISK5/CLIBH.LIB'}
BIG = {'M': 'CLIBM', 'L': 'CLIBL', 'H': 'CLIBH'}
# the measured score (METHOD.md section 8), frozen for --check
SURVIVORS = {'M>S': 106, 'L>C': 102}
EXPECTED_DIFFER = {
    'M>S': {'exit', 'atexit', 'OVLLDR', 'TZSET', 'QSORT', 'PRTF', 'PRINTF',
            'BSEARCH', 'ASCTIME'},
    'L>C': {'exit', 'atexit', 'OVLLDR', 'QSORT', 'PRTF', 'PRINTF',
            'IOALLOC', 'FWRITE', 'BSEARCH'},
}


def module_bytes(lib, start):
    raw = lib.module(start)
    t, b, o = raw[-1]
    return lib.data[start:o + 3 + len(b) + 1]


def first_diff(a, b):
    """Describe where two record lists first differ."""
    for n, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return '%s#%d' % (omf.NAMES.get(x['type'] & 0xFE,
                                            '%02X' % x['type']), n)
    return 'record-count %d/%d' % (len(a), len(b))


def classify_diff(got, want):
    """Rough reason for a mismatch."""
    gt = [r['type'] for r in got]
    wt = [r['type'] for r in want]
    if gt != wt:
        return 'record-layout'
    for x, y in zip(got, want):
        if x == y:
            continue
        t = x['type']
        if t == 0x98:
            if x['length'] != y['length']:
                return 'code-length'
            return 'segdef'
        if t == 0xA0:
            if len(x['data']) != len(y['data']):
                return 'ledata-length'
            return 'code-bytes'
        if t == 0x9C:
            return 'fixupp'
        return omf.NAMES.get(t & 0xFE, '%02X' % t)
    return 'same-records?'


def code_bytes(lib, start):
    """Every LEDATA/LIDATA's bytes, in order (code and data)."""
    return b''.join(r['data'] for r in omfrec.decode_module(lib.module(start))
                    if r['type'] in (0xA0, 0xA2))


def score_cross(dm, src, dst, verbose, zpath=None):
    mlib = paths.library('M', zpath)
    llib = paths.library('L', zpath)
    libs = {}
    for k in (src, dst):
        data, bad = dm[DISKS[k]]
        libs[k] = (survey.lib_from_bytes(data), bad)

    def whole(k, i):
        lib, bad = libs[k]
        a, b = lib.span(lib.starts[i])
        return survey.genuine_bytes(a, b, bad) == b - a and \
            lib.module(lib.starts[i])
    res = Counter()
    rows = []
    for i in range(len(mlib.starts)):
        if not whole(dst, i):
            continue
        tl, sl = libs[dst][0], libs[src][0]
        name = omf.theadr(tl.module(tl.starts[i]))
        if not whole(src, i):
            res['source lost'] += 1
            continue
        if code_bytes(mlib, mlib.starts[i]) != \
                code_bytes(llib, llib.starts[i]):
            res['not applicable'] += 1
            continue
        same = module_bytes(tl, tl.starts[i]) == module_bytes(sl,
                                                              sl.starts[i])
        res['exact' if same else 'differ'] += 1
        rows.append((i, name, 'exact' if same else 'differ', ''))
    print('%s>%s: %s' % (src, dst, ', '.join('%s %d' % kv
                                             for kv in sorted(res.items()))))
    if verbose:
        for row in rows:
            print('  %3d %-10s %-11s %s' % row)
    return rows


def score(zpath, src, dst, verbose, dm=None):
    dm = dm or damage.damage_map(zpath, [DISKS['S'], DISKS['C']])
    if src in 'SC':
        return score_cross(dm, src, dst, verbose, zpath)
    data, bad = dm[DISKS[dst]]
    tlib = survey.lib_from_bytes(data)
    slib = paths.library(src, zpath)
    res = Counter()
    why = Counter()
    rows = []
    for n, (ts, ss) in enumerate(zip(tlib.starts, slib.starts)):
        a, b = tlib.span(ts)
        if survey.genuine_bytes(a, b, bad) != b - a or not tlib.module(ts):
            continue
        name = omf.theadr(tlib.module(ts))
        want = omfrec.decode_module(tlib.module(ts))
        srec = omfrec.decode_module(slib.module(ss))
        try:
            got, notes = convert.convert(srec, BIG[src])
        except convert.Unsupported as e:
            res['unsupported'] += 1
            r = str(e).split('@')[0].split(':')[0]
            why['unsupported: ' + r] += 1
            rows.append((n, name, 'unsupported', str(e)))
            continue
        gb = omfrec.module_bytes(got)
        wb = module_bytes(tlib, ts)
        if gb == wb:
            res['exact'] += 1
            rows.append((n, name, 'exact', ' '.join(notes)))
        else:
            res['differ'] += 1
            c = classify_diff(got, want)
            tag = ('noted ' + ','.join(sorted({x.split('@')[0]
                                               for x in notes}))) \
                if notes else c
            why['differ: ' + tag] += 1
            rows.append((n, name, 'differ', '%s %s' % (c, ' '.join(notes))))
    total = sum(res.values())
    print('%s>%s: %d surviving modules: exact %d, differ %d, unsupported %d'
          % (src, dst, total, res['exact'], res['differ'],
             res['unsupported']))
    for k, v in sorted(why.items(), key=lambda kv: -kv[1]):
        print('  %3d %s' % (v, k))
    if verbose:
        for row in rows:
            print('  %3d %-10s %-11s %s' % row)
    return rows


def score_math(zpath, verbose):
    """Out-of-sample: the math libraries, intact in all five models."""
    files = paths.zip_files(zpath)

    def lib(name):
        return omf.Lib.from_bytes(next(b for n, b in files.items()
                                       if n.endswith('/%s.LIB' % name)))
    for family in ('MATH', 'MATH87'):
        for src, dst in (('M', 'S'), ('L', 'C')):
            slib = lib(family + src)
            donors = {omf.theadr(slib.module(s)): s for s in slib.starts}
            tlib = lib(family + dst)
            exact = []
            differ = []
            for ts in tlib.starts:
                name = omf.theadr(tlib.module(ts))
                try:
                    got, notes = convert.convert(
                        omfrec.decode_module(slib.module(donors[name])),
                        family + src)
                    same = omfrec.module_bytes(got) == module_bytes(tlib, ts)
                except convert.Unsupported as e:
                    same, notes = False, [str(e)]
                (exact if same else differ).append((name, notes))
            print('%s %s>%s: %d modules: exact %d, differ %d%s' % (
                family, src, dst, len(exact) + len(differ), len(exact),
                len(differ),
                ' (%s)' % ', '.join(n for n, w in differ) if differ else ''))
            if verbose:
                for name, notes in exact + differ:
                    print('  %-10s %-7s %s' % (
                        name, 'exact' if (name, notes) in exact else 'differ',
                        ' '.join(notes)))


def main(argv):
    args = argv[1:]
    zpath = args.pop(0) if args and args[0].lower().endswith('.zip') \
        else None
    zpath = paths.check_zip(zpath)
    verbose = '-v' in args
    check = '--check' in args
    if '--math' in args:
        score_math(zpath, verbose)
        return 0
    routes = [a for a in args if '>' in a] or ['M>S']
    dm = damage.damage_map(zpath, [DISKS['S'], DISKS['C']])
    bad = []
    for r in routes:
        src, dst = r.split('>')
        rows = score(zpath, src, dst, verbose, dm)
        if not check:
            continue
        if r not in EXPECTED_DIFFER:
            bad.append('%s: no frozen score to check against' % r)
            continue
        if len(rows) != SURVIVORS[r]:
            bad.append('%s: %d surviving modules scored, expected %d' % (
                r, len(rows), SURVIVORS[r]))
        uns = sorted(row[1] for row in rows if row[2] == 'unsupported')
        if uns:
            bad.append('%s: unsupported %s' % (r, ' '.join(uns)))
        differ = {row[1] for row in rows if row[2] == 'differ'}
        if differ != EXPECTED_DIFFER[r]:
            bad.append('%s: now differ %s; no longer differ %s' % (
                r, sorted(differ - EXPECTED_DIFFER[r]),
                sorted(EXPECTED_DIFFER[r] - differ)))
    if check:
        for b in bad:
            print('CHECK FAILED: ' + b)
        print('score unchanged' if not bad else 'score CHANGED')
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
