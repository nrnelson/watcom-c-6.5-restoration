"""install.py - install Watcom C 6.5 from the original zip into build/watcom.

usage: python3 -I tools/install.py [ZIP] [--restored]

Checks that ZIP (default: the zip in the repository folder) is the known
Watcom C 6.5 archive, then copies its files into build/watcom/ the way the
distribution's own installer would, following DISK1/INSTALL.SCR (BIN, H,
LIB, SRC, README.1ST).  The zip is only read.

With --restored, also makes build/watcom-restored/: the same tree with the
restored out/CLIBS.LIB and out/CLIBC.LIB in place of the damaged ones (what
the test programs link against, and what you would install in DOS).
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402


def script_copies(files):
    """[(source name in the zip, destination path)] from INSTALL.SCR."""
    scr = files['DISK1/INSTALL.SCR'].decode('latin1').replace('\r', '')
    disk = 1
    out = []
    for line in scr.split('\n'):
        w = line.split()
        if not w or w[0].startswith('#'):
            continue
        if w[0] == 'enter' and len(w) > 2 and w[1] == 'disk':
            disk = int(w[2].rstrip(','))
        elif w[0] == 'copy' and len(w) == 3 and w[1].startswith('%1') and \
                w[2].startswith('%2'):
            src = w[1][2:].replace('\\', '/').lstrip('/').upper()
            dst = w[2][2:].replace('\\', '/').lstrip('/').upper()
            if '..' in src or '..' in dst:
                raise SystemExit('bad path in INSTALL.SCR: %s' % line)
            out.append(('DISK%d/%s' % (disk, src), dst))
    return out


def install(zpath, dest):
    files = paths.zip_files(zpath)
    copies = script_copies(files)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    for src, dst in copies:
        if src not in files:
            raise SystemExit('INSTALL.SCR names %s, not in the zip' % src)
        p = os.path.join(dest, *dst.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(files[src])
    for need in ('BIN/WCC.EXE', 'BIN/WCG.EXE', 'BIN/WLINK.EXE', 'H/STDIO.H',
                 'LIB/CLIBM.LIB'):
        if not os.path.isfile(os.path.join(dest, *need.split('/'))):
            raise SystemExit('%s was not installed' % need)
    return len(copies)


def install_restored(dest_restored):
    if os.path.isdir(dest_restored):
        shutil.rmtree(dest_restored)
    shutil.copytree(paths.WATCOM, dest_restored)
    for k in 'SC':
        src = os.path.join(paths.OUT, 'CLIB%s.LIB' % k)
        if not os.path.isfile(src):
            raise SystemExit('%s missing: run restore.py first' % src)
        shutil.copy(src, os.path.join(dest_restored, 'LIB',
                                      'CLIB%s.LIB' % k))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    zpath = paths.check_zip(args[0] if args else None)
    n = install(zpath, paths.WATCOM)
    print('installed %d files of Watcom C 6.5 into %s' % (n, paths.WATCOM))
    if '--restored' in argv:
        dest = os.path.join(paths.BUILD, 'watcom-restored')
        install_restored(dest)
        print('restored libraries installed in %s' % dest)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
