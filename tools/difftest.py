"""difftest.py - run test programs against the restored libraries.

usage: python3 -I tools/difftest.py [--no-run] [TEST ...]

Each tests/<TEST>.C (default: all) is compiled by Watcom C 6.5 in the small,
compact, medium and large models and linked by WLINK 4.1: small and compact
against the restored out/CLIBS.LIB and out/CLIBC.LIB, medium and large
against the intact original libraries.  Every program runs in DOSBox-X
(MS-DOS 3.10) with its output captured, each in its own DOSBox-X instance
(four at a time), so a program that hangs only loses its own output.  The
outputs of all four models must be the same; differences are printed.
--no-run only reports on the last run.

Work files go to build/difftest.  Needs build/watcom (tools/install.py) and
the restored libraries in out/ (tools/rebuild.py).  Exit status 0 when every
test builds, runs and agrees in all four models.
"""

import difflib
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dosrun  # noqa: E402
import install  # noqa: E402
import paths  # noqa: E402

WORK = os.path.join(paths.BUILD, 'difftest')
TOOL = os.path.join(paths.BUILD, 'watcom-restored')
MODELS = 'scml'
TIMEOUT = 120    # seconds per program


def report(tests):
    status = 0
    for t in tests:
        outs = {}
        for m in MODELS:
            d = os.path.join(WORK, '%s%s' % (t[:7], m.upper()))
            for log in ('CC.LOG', 'LINK.LOG'):
                p = os.path.join(d, log)
                text = open(p, errors='replace').read() if \
                    os.path.exists(p) else ''
                if 'Error!' in text or 'undefined' in text or \
                        '*** Error' in text:
                    print('%s /m%s %s:\n%s' % (t, m, log, text.strip()))
                    status = 1
            p = os.path.join(d, 'RUN.OUT')
            outs[m] = open(p, errors='replace').read().splitlines() \
                if os.path.exists(p) else ['<no output>']
        ref = outs['m']
        same = all(outs[m] == ref for m in MODELS) and ref != ['<no output>']
        print('%-8s %s (%d lines)' % (t, 'all models agree' if same else
                                      'DIFFER', len(ref)))
        if not same:
            status = 1
            for m in 'scl':
                if outs[m] != ref:
                    for line in difflib.unified_diff(
                            ref, outs[m], 'medium', m, lineterm='', n=0):
                        print('   ' + line)
    return status


def main(argv):
    norun = '--no-run' in argv
    names = [a.upper() for a in argv[1:] if not a.startswith('--')]
    tests = names or sorted(
        f[:-2].upper() for f in os.listdir(os.path.join(paths.ROOT, 'tests'))
        if f.upper().endswith('.C'))
    if norun:
        return report(tests)
    install.install_restored(TOOL)
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    jobs = []
    for t in tests:
        for m in MODELS:
            d = os.path.join(WORK, '%s%s' % (t[:7], m.upper()))
            os.makedirs(d)
            shutil.copy(os.path.join(paths.ROOT, 'tests', t + '.C'),
                        os.path.join(d, t + '.C'))
            bat = ['@echo off',
                   'WCC %s.C /m%s /zq > CC.LOG' % (t, m),
                   'WLINK FILE %s NAME %s > LINK.LOG' % (t, t),
                   'IF EXIST %s.EXE %s.EXE > RUN.OUT' % (t, t)]
            with open(os.path.join(d, 'GO.BAT'), 'w', newline='\r\n') as f:
                f.write('\n'.join(bat) + '\n')
            jobs.append(d)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda d: dosrun.run(d, 'GO.BAT', TIMEOUT, TOOL), jobs))
    return report(tests)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
