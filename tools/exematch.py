"""exematch.py - find rebuilt library code in the archive's own programs.

usage: python3 -I tools/exematch.py [ZIP] [OUTDIR]
       python3 -I tools/exematch.py --programs PATH [OUTDIR]

The programs shipped with Watcom C 6.5 (the .EXE and .COM files in the zip)
were linked with its libraries, mostly the small-model one.  For every
`inferred` module of OUTDIR/CLIBS.LIB and OUTDIR/CLIBC.LIB (default out/,
rows from OUTDIR/PROVENANCE.csv) whose code is one CODE segment (LEDATA
only) with at least MIN_LITERAL bytes outside fixup fields, the code is
searched for in each program's load image (after the MZ header): every
byte that is not a fixup field must match at one contiguous location.
Fixup fields are masked because the linker fills them; so are bytes no
record defines (DOSPAWN's scratch word), which the linker leaves as they
were.

Prints CSV: library, module, code bytes, literal bytes (those compared:
outside fixup fields and defined), whether the whole code, fixup fields
included, occurs as it is in some program, and the matches as FILE@hex
file offset.  A match corroborates the module's instruction bytes only:
not its fixup fields (a masked call operand may name another routine),
its data, its records, or where its relocations point.  The modules stay
classified `inferred` (METHOD.md, section 17).

With --programs PATH (a directory tree or a zip), every .EXE and .COM
under PATH is searched instead of the 6.5 zip's programs, with no hash
check (nothing is taken from them), and matches are named by their path
relative to PATH: used for the later distributions' programs.
"""

import csv
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import omf  # noqa: E402
import omfrec  # noqa: E402
import paths  # noqa: E402

MIN_LITERAL = 20
FIXUP_SIZE = {0: 1, 1: 2, 2: 2, 3: 4, 4: 1}


def code_and_mask(recs):
    """(code bytes, mask) of the module's single CODE segment, mask[i] true
    where a fixup field lies or no record defines the byte; None when the
    module has no single LEDATA code segment."""
    names = [n for r in recs if r['type'] == 0x96 for n in r['names']]
    segs = [r for r in recs if r['type'] == 0x98]
    code_segs = [i for i, r in enumerate(segs, 1)
                 if r['cls'] and names[r['cls'] - 1] == 'CODE']
    if len(code_segs) != 1:
        return None
    seg = code_segs[0]
    n = segs[seg - 1]['length']
    code = bytearray(n)
    have = bytearray(n)
    mask = bytearray(n)
    last = None
    for r in recs:
        if r['type'] in (0xA0, 0xA2):
            last = r
            if r['seg'] != seg:
                continue
            if r['type'] == 0xA2:
                return None
            code[r['off']:r['off'] + len(r['data'])] = r['data']
            have[r['off']:r['off'] + len(r['data'])] = b'\1' * len(r['data'])
        elif r['type'] == 0x9C and last is not None and last['seg'] == seg:
            for f in r['subs']:
                if f['kind'] != 'fixup':
                    return None
                p = last['off'] + f['at']
                k = FIXUP_SIZE[f['loc']]
                mask[p:p + k] = b'\1' * k
    for i, h in enumerate(have):
        if not h:
            mask[i] = 1         # undefined in the object: the linker's too
    return bytes(code), bytes(mask)


def runs(code, mask):
    """[(offset, bytes)] of the runs of unmasked bytes."""
    out = []
    i = 0
    while i < len(code):
        if mask[i]:
            i += 1
            continue
        j = i
        while j < len(code) and not mask[j]:
            j += 1
        out.append((i, code[i:j]))
        i = j
    return out


def load_images(files):
    """{file name: (first byte of the load image, bytes up to its end)} of
    every .EXE and .COM in files ({name: bytes})."""
    out = {}
    for name, data in sorted(files.items()):
        if not name.upper().endswith(('.EXE', '.COM')):
            continue
        first = 0
        if data[:2] == b'MZ':
            last_page = data[2] | data[3] << 8
            pages = data[4] | data[5] << 8
            end = (pages - 1) * 512 + (last_page or 512)
            first = (data[8] | data[9] << 8) * 16
            data = data[:end]
        out[name] = (first, data)
    return out


def images(zpath):
    """Load images of every .EXE and .COM in the 6.5 zip."""
    return load_images(paths.zip_files(zpath))


def program_files(path):
    """{relative name with / separators: bytes} of every .EXE and .COM
    under path, a directory tree or a zip."""
    files = {}
    if os.path.isdir(path):
        for root, dirs, names in os.walk(path):
            dirs.sort()
            for n in names:
                if not n.upper().endswith(('.EXE', '.COM')):
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, path).replace(os.sep, '/')
                with open(full, 'rb') as f:
                    files[rel] = f.read()
    else:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir() and \
                        info.filename.upper().endswith(('.EXE', '.COM')):
                    files[info.filename] = z.read(info)
    return files


def find(code, lits, imgs):
    """Matches of the literal runs at one contiguous place: [name@hex]."""
    at, anchor = max(lits, key=lambda x: len(x[1]))
    hits = []
    for name, (first, data) in imgs.items():
        h = data.find(anchor, first)
        while h >= 0:
            s = h - at
            if s >= first and s + len(code) <= len(data) and \
                    all(data[s + o:s + o + len(b)] == b for o, b in lits):
                hits.append('%s@%x' % (name, s))
            h = data.find(anchor, h + 1)
    return hits


def main(argv):
    args = argv[1:]
    programs = None
    if '--programs' in args:
        i = args.index('--programs')
        if i + 1 >= len(args):
            raise SystemExit('--programs needs a directory or zip')
        programs = args[i + 1]
        del args[i:i + 2]
    zpath = args.pop(0) if args and args[0].lower().endswith('.zip') \
        else None
    outdir = args[0] if args else paths.OUT
    if programs is not None:
        if not os.path.exists(programs):
            raise SystemExit('not found: %s' % programs)
        imgs = load_images(program_files(programs))
    else:
        imgs = images(paths.check_zip(zpath))
    with open(os.path.join(outdir, 'PROVENANCE.csv'), newline='') as f:
        rows = list(csv.DictReader(f))
    w = csv.writer(sys.stdout, lineterminator='\n')
    w.writerow(['library', 'module', 'code_bytes', 'literal_bytes',
                'whole', 'matches'])
    count = {}
    for k in 'SC':
        lib = omf.Lib(os.path.join(outdir, 'CLIB%s.LIB' % k))
        for row in rows:
            if row['lib'] != 'CLIB' + k or row['status'] != 'inferred':
                continue
            got = code_and_mask(omfrec.decode_module(
                lib.module(int(row['offset']))))
            if got is None:
                continue
            code, mask = got
            lits = runs(code, mask)
            nlit = sum(len(b) for o, b in lits)
            if nlit < MIN_LITERAL:
                continue
            hits = find(code, lits, imgs)
            if hits:
                count[k] = count.get(k, 0) + 1
                whole = any(data.find(code, first) >= 0
                            for first, data in imgs.values())
                w.writerow([row['lib'], row['module'], len(code), nlit,
                            'yes' if whole else 'no', ' '.join(hits)])
    sys.stderr.write('modules found in shipped programs: CLIBS %d, CLIBC %d\n'
                     % (count.get('S', 0), count.get('C', 0)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
