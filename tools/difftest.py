"""difftest.py - run test programs against the restored libraries.

usage: python3 -I tools/difftest.py [--no-run] [TEST ...]

Each tests/<TEST>.C (default: all) is compiled by Watcom C 6.5 in the small,
compact, medium and large models and linked by WLINK 4.1: small and compact
against the restored out/CLIBS.LIB and out/CLIBC.LIB, medium and large
against the intact original libraries.  The tests named in TINY are also
built as a tiny-model .COM (model t): compiled /ms, linked after the shipped
startup object LIB/CSTART_T.OBJ against CLIBS.LIB, converted by EXE2COM.
Every program runs in DOSBox-X (MS-DOS 3.10) with its output captured, each
in its own DOSBox-X instance (four at a time), so a program that hangs only
loses its own output.  The batch file appends the program's exit status
(EXIT=n, from an IF ERRORLEVEL ladder; EXIT=10+ for 10 and above) and DONE
to the output, or NO-EXE when nothing was linked (no .COM for model t).  For
each model the run must have finished (DOSBox-X ended in time, exit status
0), the output must end with DONE, hold exactly one EXIT= line, giving the
expected status (EXPECT_EXIT, default 0), and print something besides, and
the compiler's, linker's and (model t) EXE2COM's logs must show no error;
then the outputs of all its models must equal the medium model's;
differences are printed.  --no-run only reports on the last run (without the
emulator check).  A program whose last line has no newline gets the EXIT=
marker appended to that line; the runner splits it off again when it is the
only place the marker is found.

Work files go to build/difftest.  Needs build/watcom (tools/install.py) and
the restored libraries in out/ (tools/rebuild.py).  Exit status 0 when every
test builds, runs and agrees in all its models.
"""

import difflib
import os
import re
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
# tests also built as a tiny-model .COM (model t); T_CHAIN cannot be: its
# interrupt functions load DS from DGROUP, a relocation EXE2COM refuses
TINY = ('T_INT',)
TIMEOUT = 120    # seconds per program
# process exit status each test must end with (default 0)
EXPECT_EXIT = {'T_SPAWN': 3}
LADDER = 10      # IF ERRORLEVEL 10 .. 1


def models(t):
    """The models test t is built in."""
    return MODELS + ('t' if t in TINY else '')


def batch(t, m):
    """GO.BAT for test t in model m (t: tiny, a .COM)."""
    if m == 't':
        bat = ['@echo off',
               'WCC %s.C /ms /zq > CC.LOG' % t,
               r'WLINK FILE D:\LIB\CSTART_T,%s NAME %s > LINK.LOG' % (t, t),
               'EXE2COM %s > E2C.LOG' % t,
               'IF NOT EXIST %s.COM GOTO NOEXE' % t,
               '%s.COM > RUN.OUT' % t]
    else:
        bat = ['@echo off',
               'WCC %s.C /m%s /zq > CC.LOG' % (t, m),
               'WLINK FILE %s NAME %s > LINK.LOG' % (t, t),
               'IF NOT EXIST %s.EXE GOTO NOEXE' % t,
               '%s.EXE > RUN.OUT' % t]
    # DOS 3.x has no %ERRORLEVEL%; and "IF ... ECHO x > FILE" truncates
    # FILE before testing, so branch instead
    bat += ['IF ERRORLEVEL %d GOTO E%d' % (n, n)
            for n in range(LADDER, 0, -1)]
    bat += ['ECHO EXIT=0>> RUN.OUT', 'GOTO DONE']
    for n in range(LADDER, 0, -1):
        bat += [':E%d' % n, 'ECHO EXIT=%d%s>> RUN.OUT' % (
            n, '+' if n == LADDER else ''), 'GOTO DONE']
    bat += [':NOEXE', 'ECHO NO-EXE>> RUN.OUT', ':DONE', 'ECHO DONE>> RUN.OUT']
    return bat


def expected_exit(t):
    n = EXPECT_EXIT.get(t, 0)
    return 'EXIT=%d%s' % (min(n, LADDER), '+' if n >= LADDER else '')


MARKER = re.compile(r'EXIT=\d+\+?$')


def program_output(t, lines):
    """(output without the EXIT= and DONE lines, None) or (None, why).
    When the program's last line has no newline, the batch file's EXIT=
    marker is appended to it ('last textEXIT=0'): if no line is a marker
    but exactly one ends with one, it is split into the program's line
    and the marker."""
    if not lines or lines[-1] != 'DONE':
        return None, 'incomplete (no DONE)'
    if 'NO-EXE' in lines:
        return None, 'not linked (NO-EXE)'
    if not any(MARKER.match(x) for x in lines):
        ends = [n for n, x in enumerate(lines) if MARKER.search(x)]
        if len(ends) == 1:
            n = ends[0]
            m = MARKER.search(lines[n])
            lines = lines[:n] + [lines[n][:m.start()], m.group()] + \
                lines[n + 1:]
    exits = [x for x in lines if x.startswith('EXIT=')]
    if len(exits) != 1 or lines[-2] != exits[0]:
        return None, 'exit status not recorded once (%s)' % exits
    if exits[0] != expected_exit(t):
        return None, 'exit status %s, expected %s' % (exits[0][5:],
                                                      expected_exit(t)[5:])
    out = lines[:-2]
    if not out:
        return None, 'printed nothing'
    return out, None


def report(tests, finished=None):
    """finished: {work dir: True when DOSBox-X ended normally}."""
    status = 0
    for t in tests:
        outs = {}
        bad = {}
        for m in models(t):
            d = os.path.join(WORK, '%s%s' % (t[:7], m.upper()))
            for log in ('CC.LOG', 'LINK.LOG', 'E2C.LOG'):
                p = os.path.join(d, log)
                text = open(p, errors='replace').read() if \
                    os.path.exists(p) else ''
                # E2C.LOG (model t): EXE2COM's refusal names relocations
                if 'Error!' in text or 'undefined' in text or \
                        '*** Error' in text or 'relocation' in text:
                    print('%s /m%s %s:\n%s' % (t, m, log, text.strip()))
                    status = 1
            if finished is not None and not finished.get(d):
                bad[m] = 'timeout/emulator failure'
                continue
            p = os.path.join(d, 'RUN.OUT')
            lines = [x.rstrip() for x in open(p, errors='replace').read()
                     .splitlines()] if os.path.exists(p) else []
            outs[m], why = program_output(t, lines)
            if why:
                bad[m] = why
        if bad:
            status = 1
            print('%-8s FAILED: %s' % (t, '; '.join(
                '/m%s %s' % (m, bad[m]) for m in models(t) if m in bad)))
            continue
        ref = outs['m']
        same = all(outs[m] == ref for m in models(t))
        print('%-8s %s (%d lines, %s)' % (t, 'all models agree' if same else
                                          'DIFFER', len(ref),
                                          expected_exit(t)))
        if not same:
            status = 1
            for m in models(t):
                if m != 'm' and outs[m] != ref:
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
        for m in models(t):
            d = os.path.join(WORK, '%s%s' % (t[:7], m.upper()))
            os.makedirs(d)
            shutil.copy(os.path.join(paths.ROOT, 'tests', t + '.C'),
                        os.path.join(d, t + '.C'))
            with open(os.path.join(d, 'GO.BAT'), 'w', newline='\r\n') as f:
                f.write('\n'.join(batch(t, m)) + '\n')
            jobs.append(d)
    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(lambda d: dosrun.run(d, 'GO.BAT', TIMEOUT, TOOL),
                           jobs))
    return report(tests, dict(zip(jobs, done)))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
