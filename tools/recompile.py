"""recompile.py - the recompile route: build modules from reconstructed C.

usage: python3 -I tools/recompile.py [ZIP] NAME [NAME ...]

recompile/NAME.c (or, for SETJMP, the source recompile/NAME.py generates
from the user's own libraries) is C written to reproduce library module
NAME.  Watcom C 6.5 compiles it in DOSBox-X (tools/dosrun.py) in every
model:

  S  wcc ..\\c\\NAME.c /ms OPT       C  /mc OPT
  M  /mm /g=CLIBM OPT               L  /ml OPT      H  /mh OPT

from a directory beside c\\, so that the object names its source as
..\\c\\NAME.c as the library modules do.  OPT is recompile/NAME.opt (one
line: the switches besides the model; default /s).

The M, L and H objects are compared byte for byte with the intact
libraries' modules, the S and C objects with the surviving CLIBS/CLIBC
modules where they survive (all read from the zip).  A source reproduces
the module when M and L both match: they fix the code-model and the
data-model halves of S and C.  When they do not match, the S and C
objects are kept only when recompile/NAME.accept exists and pins exactly
the objects just compiled.  Its format: first line the confidence; then
why the difference is accepted; then one line 'sha256 K <hex>' for each of
the five objects (K = S, C, M, L, H).  All five must match: an accept file
cannot vouch for a changed source, even one whose change shows only in
the S and C objects.

Kept objects go to build/objects/NAME.S.OBJ and NAME.C.OBJ, with
build/objects/NAME.status for tools/rebuild.py: first line exact or
accepted, then the per-model results, then 'sha256 S <hex>' and
'sha256 C <hex>' of the kept objects (rebuild.py ignores an object that
does not match), then 'note <word>' when a generator declares a
provenance note (SETJMP.py: near-code-inferred, its small-code bodies
being edits the medium and large matches do not test).  Needs
build/watcom (tools/install.py).
"""

import hashlib

import importlib.util
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dosrun  # noqa: E402
import omf  # noqa: E402
import paths  # noqa: E402

SRC = os.path.join(paths.ROOT, 'recompile')
WORK = os.path.join(paths.BUILD, 'recompile')
SWITCHES = {'S': '/ms', 'M': '/mm /g=CLIBM', 'C': '/mc', 'L': '/ml',
            'H': '/mh'}
DEFAULT_OPT = '/s'
# the modules restore.py recompiles
MODULES = ('PRINTF', 'SPRINTF', 'SETJMP', 'SIGNAL')


def lib_module(lib, name):
    for s in lib.starts:
        raw = lib.module(s)
        if raw and omf.theadr(raw) == name:
            t, b, o = raw[-1]
            return lib.data[s:o + 3 + len(b) + 1]
    return None


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def source(name, zpath):
    """(C source, provenance note) of module name: recompile/NAME.c, or
    what recompile/NAME.py generates, with the generator's NOTE ('' when
    it has none)."""
    gen = os.path.join(SRC, name + '.py')
    if os.path.exists(gen):
        spec = importlib.util.spec_from_file_location('gen_' + name, gen)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return (mod.generate(lambda k: paths.library(k, zpath)),
                getattr(mod, 'NOTE', ''))
    with open(os.path.join(SRC, name + '.c')) as f:
        return f.read(), ''


def accept_digests(path):
    """{model: SHA-256} pinned by an accept file."""
    out = {}
    with open(path) as f:
        for line in f:
            w = line.split()
            if len(w) == 3 and w[0] == 'sha256':
                out[w[1]] = w[2].lower()
    return out


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def recompile(names, zpath):
    """Compile and compare; returns {name: (results, exact?, kept?)}."""
    libs = {k: paths.library(k, zpath) for k in 'SCMLH'}
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(os.path.join(WORK, 'c'))
    os.makedirs(os.path.join(WORK, 'o'))
    os.makedirs(paths.OBJECTS, exist_ok=True)
    bat = []
    note = {}
    for name in names:
        text, note[name] = source(name, zpath)
        with open(os.path.join(WORK, 'c', name + '.C'), 'w',
                  newline='\r\n') as f:
            f.write(text)
        opt = DEFAULT_OPT
        optf = os.path.join(SRC, name + '.opt')
        if os.path.exists(optf):
            opt = open(optf).read().strip()
        for k in 'SMCLH':
            bat.append('wcc ..\\c\\%s.c %s %s /zq' % (name, SWITCHES[k], opt))
            bat.append('copy %s.OBJ %s.%s' % (name[:8], name[:8], k))
            bat.append('del %s.OBJ' % name[:8])
    with open(os.path.join(WORK, 'GO.BAT'), 'w', newline='\r\n') as f:
        f.write('@echo off\ncd \\o\n' + '\n'.join(bat) + '\n')
    if not dosrun.run(WORK, 'GO.BAT', 900):
        raise SystemExit('DOSBox-X did not finish the compiles')
    results = {}
    for name in names:
        res = {}
        objs = {}
        for k in 'SMCLH':
            p = os.path.join(WORK, 'o', '%s.%s' % (name[:8], k))
            if not os.path.exists(p):
                res[k] = 'no object'
                continue
            obj = open(p, 'rb').read()
            objs[k] = obj
            want = lib_module(libs[k], name)
            if want is None:
                res[k] = 'no surviving module'
            elif obj == want:
                res[k] = 'exact'
            else:
                res[k] = 'differs at %d (%d vs %d bytes)' % (
                    first_diff(obj, want), len(obj), len(want))
        ok = all(res.get(k) == 'exact' for k in 'ML')
        accept = os.path.join(SRC, name + '.accept')
        sc_ok = all(res.get(k) in ('exact', 'no surviving module')
                    for k in 'SC')
        accepted = False
        if not ok and os.path.exists(accept):
            pins = accept_digests(accept)
            accepted = all(k in objs and pins.get(k) == sha256(objs[k])
                           for k in 'SCMLH')
            if not accepted:
                res['accept'] = 'does not pin these objects'
        kept = sc_ok and (ok or accepted)
        statf = os.path.join(paths.OBJECTS, name + '.status')
        for k in 'SC':
            p = os.path.join(paths.OBJECTS, '%s.%s.OBJ' % (name, k))
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(statf):
            os.remove(statf)
        if kept:
            for k in 'SC':
                with open(os.path.join(paths.OBJECTS, '%s.%s.OBJ' % (name, k)),
                          'wb') as f:
                    f.write(objs[k])
            with open(statf, 'w') as f:
                f.write('%s\n' % ('exact' if ok else 'accepted'))
                f.write('  '.join('%s %s' % (k, res[k]) for k in 'MLHSC') +
                        '\n')
                for k in 'SC':
                    f.write('sha256 %s %s\n' % (k, sha256(objs[k])))
                if note[name]:
                    f.write('note %s\n' % note[name])
        results[name] = (res, ok, kept)
    return results


def main(argv):
    args = argv[1:]
    zpath = None
    if args and args[0].lower().endswith('.zip'):
        zpath = args.pop(0)
    if not args:
        sys.stderr.write(__doc__)
        return 2
    zpath = paths.check_zip(zpath)
    status = 0
    for name, (res, ok, kept) in recompile(args, zpath).items():
        line = '  '.join('%s %s' % (k, res[k]) for k in 'MLHSC')
        if 'accept' in res:
            line += '  (%s.accept %s)' % (name, res['accept'])
        print('%s: %s%s' % (name, line, '' if ok else '  -- not reproduced'))
        if kept and not ok:
            print('  kept as accepted: %s' % open(os.path.join(
                SRC, name + '.accept')).readline().strip())
        if not kept:
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
