"""restore.py - restore Watcom C 6.5's damaged CLIBS.LIB and CLIBC.LIB.

usage: python3 restore.py [ZIP] [--test] [--install DIR]

ZIP is the original archive "Watcom C.ver.6.5.English.zip" (default: that
file in this folder).  See README.md for where to get it and what it is.
Any other option is an error.

Steps:
  1. check the zip is the known Watcom C 6.5 archive (SHA-256);
  2. install Watcom C 6.5 from it into build/watcom (as its INSTALL.SCR
     does);
  3. recompile the four modules rebuilt from reconstructed C, with
     Watcom C 6.5 itself running in DOSBox-X (build/objects is emptied
     first, so only objects made by this run are used);
  4. rebuild both libraries into out/ (out/CLIBS.LIB, out/CLIBC.LIB,
     out/PROVENANCE.csv);
  5. check them: every module walked and every record checksummed, the
     end record and the dictionary checked (tools/checklib.py), and the
     SHA-256 of each compared with the published result; any failure
     fails the run;
  6. with --test, build and run the test programs in all four models (and
     T_INT also as a tiny-model .COM), then have the 1988 WLIB extract
     every module of both libraries and WLINK link every one of them
     (tools/periodcheck.py); a failure fails the run;
  7. with --install DIR, and only when every step above passed, install
     the restored libraries into DIR, the LIB directory of a Watcom C 6.5
     installation, which must already hold CLIBS.LIB and CLIBC.LIB.  The
     libraries found there are first copied to CLIBS.BAD and CLIBC.BAD,
     unless those files already exist (an existing .BAD is kept as it is,
     and is not checked).  Each backup is written under a temporary name
     and renamed to .BAD only when the copy is complete, so a backup made
     by the installer is complete or absent: a failed install never
     leaves a partial .BAD.  Both new libraries are written beside the old
     ones as .new files, then each is moved into place; if moving the
     second fails, the first is put back as it was just before, so DIR
     does not hold one new and one old library.  (This covers an error
     reported while installing, not a crash or power loss between the two
     moves.)

Exit status 0 when every step passed.  Needs Python 3.8 or later and
DOSBox-X (README.md).  Nothing outside this folder is written, except
with --install.
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
import periodcheck  # noqa: E402
import rebuild  # noqa: E402
import recompile  # noqa: E402

EXPECTED = {
    'CLIBS.LIB':
        '27ba210a1c1bc70960169e82a2cc09e9ce167c6c7b504985b4735cd95606a3ca',
    'CLIBC.LIB':
        'a708a545ecd064717e7ccfb4e3b3e613472ae294d4476c86fafe94e353a81627',
}
LIBS = ('CLIBS', 'CLIBC')


def step(n, text):
    print('\n[%d] %s' % (n, text))


def usage():
    sys.stderr.write(__doc__.split('\n\n')[1] + '\n')
    return 2


def parse(args):
    """(zip or None, test, install dir or None), or None when the
    arguments are wrong; 'help' for -h/--help."""
    zpath, test, target = None, False, None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('-h', '--help'):
            return 'help'
        if a == '--test':
            test = True
        elif a == '--install':
            if i + 1 >= len(args) or target is not None:
                return None
            target = args[i + 1]
            i += 1
        elif a.startswith('-') or zpath is not None:
            return None
        else:
            zpath = a
        i += 1
    return zpath, test, target


def install_libs(target):
    """Install out/CLIBS.LIB and out/CLIBC.LIB into target (step 7);
    returns 0, or 1 with what happened printed."""
    if not os.path.isdir(target):
        print('not installed: %s is not a directory' % target)
        return 1
    dst = {k: os.path.join(target, k + '.LIB') for k in LIBS}
    for k in LIBS:
        if not os.path.isfile(dst[k]):
            print('not installed: %s does not exist (DIR must be the LIB '
                  'directory of a Watcom C 6.5 installation)' % dst[k])
            return 1
    new = {k: dst[k] + '.new' for k in LIBS}
    # each backup is written to a temporary name and renamed to .BAD only
    # once complete, so a failed copy never leaves a partial .BAD
    bad = {k: os.path.join(target, k + '.BAD') for k in LIBS}
    bad_new = {k: bad[k] + '.new' for k in LIBS}
    prev = {}
    try:
        for k in LIBS:
            shutil.copyfile(os.path.join(paths.OUT, k + '.LIB'), new[k])
        for k in LIBS:
            with open(dst[k], 'rb') as f:
                prev[k] = f.read()
            if os.path.exists(bad[k]):
                print('  %s exists: kept as it is' % bad[k])
            else:
                shutil.copyfile(dst[k], bad_new[k])
                os.replace(bad_new[k], bad[k])
                print('  %s: the library found there' % bad[k])
    except OSError as e:
        print('not installed: %s' % e)
        remove_temporaries(new, bad_new)
        return 1
    done = []
    try:
        for k in LIBS:
            os.replace(new[k], dst[k])
            done.append(k)
            print('  %s' % dst[k])
    except OSError as e:
        print('installing %s failed: %s' % (dst[k], e))
        for j in done:
            back = dst[j] + '.prev'
            try:
                with open(back, 'wb') as f:
                    f.write(prev[j])
                os.replace(back, dst[j])
                print('  %s put back as it was before this install' %
                      dst[j])
            except OSError as e2:
                print('  COULD NOT PUT BACK %s (%s): the library it held is '
                      'in %s if that file exists; DIR now mixes new and old '
                      'libraries' % (dst[j], e2, back))
        remove_temporaries(new, bad_new)
        print('not installed')
        return 1
    return 0


def remove_temporaries(*names):
    """Remove the temporary files of install_libs that exist ({k: path}
    dicts); a complete .BAD has already been renamed and is kept."""
    for d in names:
        for p in d.values():
            if os.path.exists(p):
                os.remove(p)


def main(argv):
    parsed = parse(argv[1:])
    if parsed == 'help':
        sys.stdout.write(__doc__)
        return 0
    if parsed is None:
        return usage()
    zarg, test, target = parsed

    step(1, 'checking the archive')
    zpath = paths.check_zip(zarg)
    print('ok: %s' % zpath)

    step(2, 'installing Watcom C 6.5 into %s' % paths.WATCOM)
    print('%d files' % install.install(zpath, paths.WATCOM))

    step(3, 'recompiling %s with Watcom C 6.5 in DOSBox-X' %
         ', '.join(recompile.MODULES))
    if os.path.isdir(paths.OBJECTS):
        shutil.rmtree(paths.OBJECTS)
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
        ok, msg = checklib.check(p)
        print('%s: %s' % (p, msg))
        if not ok:
            status = 1
        got = paths.sha256_file(p)
        if got == want:
            print('  SHA-256 %s: identical to the published restoration' %
                  got)
        else:
            print('  SHA-256 %s: DIFFERS from the published %s' % (got, want))
            status = 1

    if test:
        step(6, 'running the test programs in all four models and tiny, '
             'then WLIB and WLINK on every module')
        status |= difftest.main(['difftest.py'])
        status |= periodcheck.main(['periodcheck.py'])

    if target:
        step(7, 'installing the restored libraries into %s' % target)
        if status != 0:
            print('not installed: verification failed (see above)')
            return 1
        if install_libs(target) != 0:
            return 1

    print('\ndone: %s' % ('the restored libraries are in ' + paths.OUT
                          if status == 0 else 'with problems, see above'))
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
