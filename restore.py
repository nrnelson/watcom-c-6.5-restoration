"""restore.py - restore Watcom C 6.5's damaged CLIBS.LIB and CLIBC.LIB.

usage: python3 restore.py [ZIP] [--test] [--install DIR]

ZIP is the original archive "Watcom C.ver.6.5.English.zip" (default: that
file in this folder).  See README.md for where to get it and what it is.

Steps:
  1. check the zip is the known Watcom C 6.5 archive (SHA-256);
  2. install Watcom C 6.5 from it into build/watcom (as its INSTALL.SCR
     does);
  3. recompile the four modules rebuilt from reconstructed C, with
     Watcom C 6.5 itself running in DOSBox-X;
  4. rebuild both libraries into out/ (out/CLIBS.LIB, out/CLIBC.LIB,
     out/PROVENANCE.csv);
  5. check them: every module walked and checksummed, and the SHA-256 of
     each compared with the published result;
  6. with --test, build and run the test programs in all four models;
  7. with --install DIR, copy the restored libraries into DIR, the LIB
     directory of a Watcom C 6.5 installation (the damaged ones are kept
     there as CLIBS.BAD and CLIBC.BAD).

Needs Python 3.8 or later and DOSBox-X (README.md).  Nothing outside this
folder is written, except with --install.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))

import checklib  # noqa: E402
import difftest  # noqa: E402
import install  # noqa: E402
import paths  # noqa: E402
import rebuild  # noqa: E402
import recompile  # noqa: E402

EXPECTED = {
    'CLIBS.LIB':
        '95100563d6885e7f0eba7c1a96aa0587bdf2fbe9ef8bfbaf73a367f85216b8c0',
    'CLIBC.LIB':
        'b53e05b77252a952e0896abc3612846bae2a10f4c584d1fa682e752b6e24bcae',
}


def step(n, text):
    print('\n[%d] %s' % (n, text))


def main(argv):
    args = argv[1:]
    test = '--test' in args
    target = None
    if '--install' in args:
        i = args.index('--install')
        if i + 1 >= len(args):
            print('--install needs a directory')
            return 2
        target = args[i + 1]
        del args[i:i + 2]
    args = [a for a in args if not a.startswith('--')]
    if len(args) > 1:
        sys.stderr.write(__doc__)
        return 2

    step(1, 'checking the archive')
    zpath = paths.check_zip(args[0] if args else None)
    print('ok: %s' % zpath)

    step(2, 'installing Watcom C 6.5 into %s' % paths.WATCOM)
    print('%d files' % install.install(zpath, paths.WATCOM))

    step(3, 'recompiling %s with Watcom C 6.5 in DOSBox-X' %
         ', '.join(recompile.MODULES))
    for name, (res, ok, kept) in recompile.recompile(
            list(recompile.MODULES), zpath).items():
        print('%-8s %s' % (name, 'reproduces CLIBM and CLIBL exactly' if ok
                           else 'kept as accepted (see recompile/%s.accept)'
                           % name if kept else 'FAILED'))
        if not kept:
            print('the recompile of %s failed; see build/recompile/RUN.LOG'
                  % name)
            return 1

    step(4, 'rebuilding the libraries into %s' % paths.OUT)
    if rebuild.main(['rebuild.py', zpath, paths.OUT]) != 0:
        return 1

    step(5, 'checking the result')
    status = 0
    for name, want in EXPECTED.items():
        p = os.path.join(paths.OUT, name)
        print(p + ': ' + checklib.check(p))
        got = paths.sha256_file(p)
        if got == want:
            print('  SHA-256 %s: identical to the published restoration' %
                  got)
        else:
            print('  SHA-256 %s: DIFFERS from the published %s' % (got, want))
            status = 1

    if test:
        step(6, 'running the test programs in all four models')
        status |= difftest.main(['difftest.py'])

    if target:
        step(7, 'installing the restored libraries into %s' % target)
        for k in 'SC':
            dst = os.path.join(target, 'CLIB%s.LIB' % k)
            bad = os.path.join(target, 'CLIB%s.BAD' % k)
            if os.path.isfile(dst) and not os.path.exists(bad):
                shutil.copy(dst, bad)
            shutil.copy(os.path.join(paths.OUT, 'CLIB%s.LIB' % k), dst)
            print('  %s' % dst)

    print('\ndone: %s' % ('the restored libraries are in ' + paths.OUT
                          if status == 0 else 'with problems, see above'))
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
