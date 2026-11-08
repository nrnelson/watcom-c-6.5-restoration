"""rebuild.py - rebuild CLIBS.LIB and CLIBC.LIB.

usage: python3 -I tools/rebuild.py [ZIP] [OUTDIR] [-v]

ZIP defaults to the zip in the repository folder, OUTDIR to out/.

For each of the 250 modules of each damaged library:
  original  the module survives whole (TELL in CLIBS after its one-bit
            repair, see REPAIRS)
  rebuilt   otherwise, from the routes below, checked against the page span
            the intact dictionary gives and against every genuine byte left
            in that span:
              cross    the other damaged library's surviving module, where
                       the medium and large modules are identical (code and
                       data) so the module does not depend on the data model
              convert  tools/convert.py on the medium (for S) or large (for
                       C) module
              recompile  an object compiled by 6.5 from reconstructed source
                       (build/objects/<MODULE>.S.OBJ / .C.OBJ, made by
                       tools/recompile.py), used only when
                       build/objects/<MODULE>.status says exact or accepted
                       and gives the object's SHA-256; any other object
                       there is ignored with a warning
              unchanged  CLIBM's module as it is, for the model-
                       independent routines of MODEL_INDEPENDENT
Every route that applies is tried; the first that passes the checks in the
order recompile, unchanged, cross, convert is used and the others are
recorded.

Writes OUTDIR/CLIBS.LIB, OUTDIR/CLIBC.LIB and OUTDIR/PROVENANCE.csv, and
prints a summary.  The libraries keep the original header, module pages,
end record and dictionary; the dictionary is checked against the publics of
the rebuilt modules (after the route is chosen: a mismatch fails the
module).  Exit status 1 when any module FAILED; the libraries are still
written, for diagnosis, but are incomplete.
"""

import csv
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert  # noqa: E402
import damage  # noqa: E402
import omf  # noqa: E402
import omfrec  # noqa: E402
import paths  # noqa: E402
import recompile  # noqa: E402
import survey  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
DISKS = {'S': 'DISK4/CLIBS.LIB', 'C': 'DISK4/CLIBC.LIB'}
SOURCE = {'S': 'M', 'C': 'L'}
OTHER = {'S': 'C', 'C': 'S'}
# Bytes of genuine sectors known to be wrong, with the evidence.
REPAIRS = {
    'S': {14012: (0x4C, 0x6C, 'TELL PUBDEF: checksum fails with 4C; the '
                  'dictionary names the public tell_; 6C fixes both')},
    'C': {11580: (0xD0, 0xD1, 'AMODF code: D0 81 breaks the instruction '
                  'stream (shl di,1; rcl cx,1; rcl bx,1 ...); S, M, L and H '
                  'all have D1 D1 here'),
          11581: (0x81, 0xD1, 'AMODF code: see byte 11580')},
}


def repair_note(k, start, end):
    """The REPAIRS of library k inside [start, end), as a note ('' if
    none)."""
    return '; '.join('byte %d %02X->%02X: %s' % (o, a, b, w)
                     for o, (a, b, w) in sorted(REPAIRS.get(k, {}).items())
                     if start <= o < end)


def set_theadr(data, name):
    """Module bytes with THEADR (and the source name in the first COMENT,
    when it ends in the same base name) set to name, case and all."""
    out = bytearray()
    i = 0
    while i < len(data):
        t = data[i]
        n = data[i + 1] | data[i + 2] << 8
        body = bytes(data[i + 3:i + 2 + n])
        if t == 0x80:
            body = bytes((len(name),)) + name.encode('latin1')
        elif t == 0x88 and body[:2] == b'\xff\x80':
            src = body[2:].decode('latin1')
            base = src.rsplit('\\', 1)[-1]
            stem, dot, ext = base.partition('.')
            if stem.upper() == name.upper() and stem != name:
                body = body[:2] + (src[:len(src) - len(base)] + name + dot +
                                   ext).encode('latin1')
        rec = bytes((t,)) + omfrec.w16(len(body) + 1) + body
        out += rec + bytes(((-sum(rec)) & 0xFF,))
        i += 3 + n
        if t in (0x8A, 0x8B):
            break
    return bytes(out)


# Converter notes and how the routes scored on the surviving modules
# (tools/score.py): with no note, or only these, conversion was exact for
# 96% of surviving modules; with any RISKY note it was mostly wrong.
RISKY = {'call-far-indirect', 'jmp-far-indirect', 'far-code-pointer',
         'code-offset-in-field', 'code-segment-ref', 'code-segment-store',
         'return-address-access', 'interrupt-call-kept',
         'code-segment-renamed'}


# Assembler modules taken unchanged from CLIBM (far routines in every
# model): a decision, see METHOD.md section 11.
MODEL_INDEPENDENT = set(os.getenv('WCR_MODEL_INDEPENDENT',
                                  'EXECADDR').split())


def confidence(row):
    """high / medium / low for a rebuilt module, from its route and notes
    (see METHOD.md, section 10)."""
    if row['status'].startswith('original'):
        return 'original'
    if row['status'] == 'FAILED':
        return ''
    notes = set(row.get('notes', '').split())
    accepted = [n for n in notes if n.startswith('recompile-accepted:')]
    if accepted:
        level = accepted[0].split(':', 1)[1]
    elif row['route'] == 'unchanged':
        level = 'low'
    elif row['route'] in ('cross', 'recompile'):
        level = 'high'
    elif notes & RISKY:
        level = 'low'
    else:
        level = 'medium'
    if 'name-case-from-dictionary' in notes and level == 'high':
        level = 'medium'
    return level


def end_of_modules(lib):
    """Offset of the library end record (F1), which follows the last
    module's page span (omf.Lib.end_of_modules)."""
    return lib.end_of_modules()


def recompiled(name, k):
    """(object bytes, note) of build/objects/NAME.k.OBJ when
    tools/recompile.py made it (NAME.status: first word exact or accepted,
    and a 'sha256 k <hex>' line matching the object), else None, with a
    warning when an object is there but not vouched for."""
    obj = os.path.join(paths.OBJECTS, '%s.%s.OBJ' % (name, k))
    if not os.path.exists(obj):
        return None
    with open(obj, 'rb') as f:
        data = f.read()
    stat = os.path.join(paths.OBJECTS, name + '.status')
    lines = open(stat).read().splitlines() if os.path.exists(stat) else []
    level = lines[0].split()[0] if lines and lines[0].split() else ''
    digest = {w[1]: w[2] for w in (line.split() for line in lines[1:])
              if len(w) == 3 and w[0] == 'sha256'}
    if level not in ('exact', 'accepted'):
        print('warning: %s ignored: %s does not say exact or accepted' %
              (obj, stat))
        return None
    if k not in digest:
        print('warning: %s ignored: %s gives no SHA-256 for it' % (obj, stat))
        return None
    if digest[k] != hashlib.sha256(data).hexdigest():
        print('warning: %s ignored: its SHA-256 is not the one %s gives' %
              (obj, stat))
        return None
    note = ''
    if level == 'accepted':
        acc = open(os.path.join(ROOT, 'recompile',
                                name + '.accept')).readline()
        note = 'recompile-accepted:%s' % acc.split()[0]
    return data, note


def module_raw(lib, start):
    raw = lib.module(start)
    t, b, o = raw[-1]
    return lib.data[start:o + 3 + len(b) + 1]


def publics(data):
    """Public names of a module's bytes (PUBDEF), and its THEADR name."""
    out = []
    i = 0
    name = None
    while i < len(data):
        t = data[i]
        n = data[i + 1] | data[i + 2] << 8
        body = data[i + 3:i + 2 + n]
        if t == 0x80:
            name = body[1:1 + body[0]].decode('latin1')
        if t == 0x90:
            r = omfrec.decode(t, body)
            out.extend(p[0] for p in r['pubs'])
        i += 3 + n
        if t in (0x8A, 0x8B):
            break
    return name, out


def check(cand, start, end, genuine, data):
    """(ok, why) for a candidate module's bytes placed at start in a span
    ending at end: same page count, zero padding, every genuine byte
    matched."""
    span = end - start
    if len(cand) > span or (span - len(cand)) >= 16:
        return False, 'size %d does not fill span %d' % (len(cand), span)
    padded = cand + bytes(span - len(cand))
    bad = [o for o in range(start, end)
           if o in genuine and padded[o - start] != data[o]]
    if bad:
        return False, '%d genuine bytes differ (first at %d)' % (
            len(bad), bad[0])
    return True, ''


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('-')]
    if len(args) > 2:
        sys.stderr.write(__doc__)
        return 2
    verbose = '-v' in argv
    zpath = args.pop(0) if args and args[0].lower().endswith('.zip') \
        else None
    zpath = paths.check_zip(zpath)
    outdir = args[0] if args else paths.OUT
    os.makedirs(outdir, exist_ok=True)
    dm = damage.damage_map(zpath, list(DISKS.values()))
    big = {k: paths.library(k, zpath) for k in 'ML'}
    libs = {}
    for k, name in DISKS.items():
        data, bad = dm[name]
        data = bytearray(data)
        for o, (was, now, why) in REPAIRS.get(k, {}).items():
            assert data[o] == was
            data[o] = now
        lib = survey.lib_from_bytes(bytes(data))
        genuine = {o for o in range(len(data))
                   if o - o % damage.SECTOR not in bad}
        libs[k] = (lib, genuine)

    def whole(k, i):
        lib, genuine = libs[k]
        a, b = lib.span(lib.starts[i])
        return all(o in genuine for o in range(a, b)) and \
            lib.module(lib.starts[i]) is not None

    def same_ml(i):
        m, l_ = big['M'], big['L']
        get = (lambda lib: b''.join(
            r['data'] for r in omfrec.decode_module(
                lib.module(lib.starts[i])) if r['type'] in (0xA0, 0xA2)))
        return get(m) == get(l_)

    rows = []
    for k in 'SC':
        lib, genuine = libs[k]
        out = bytearray(lib.data)
        endmods = end_of_modules(lib)
        src = big[SOURCE[k]]
        for i, start in enumerate(lib.starts):
            end = lib.starts[i + 1] if i + 1 < len(lib.starts) else endmods
            ngen = sum(1 for o in range(start, end) if o in genuine)
            # name: the donor's THEADR, for the donor-side lookups; dname:
            # the module name as the dictionary spells it (six CLIBS
            # modules have lower-case names there), for the row and the
            # rebuilt object
            name = omf.theadr(src.module(src.starts[i]))
            dname = [n for n in lib.names[start] if n.endswith('!')][0][:-1]
            row = {'lib': 'CLIB%s' % k, 'index': i, 'module': dname,
                   'offset': start, 'span': end - start,
                   'genuine_bytes': ngen}
            if whole(k, i):
                row['status'] = 'original'
                row['route'] = ''
                row['notes'] = ''
                if repair_note(k, start, end):
                    row['status'] = 'original-repaired'
                    row['notes'] = repair_note(k, start, end)
                rows.append(row)
                continue
            cands = []
            got = recompiled(name, k)
            if got:
                cands.append(('recompile', got[0], got[1]))
            if name in MODEL_INDEPENDENT:
                cands.append(('unchanged', module_raw(big['M'],
                                                      big['M'].starts[i]),
                              'model-independent'))
            ok_lib, ok_gen = libs[OTHER[k]]
            if whole(OTHER[k], i) and same_ml(i):
                cands.append(('cross', module_raw(ok_lib, ok_lib.starts[i]),
                              ''))
            try:
                recs, notes = convert.convert(
                    omfrec.decode_module(src.module(src.starts[i])),
                    'CLIB' + SOURCE[k])
                cands.append(('convert', omfrec.module_bytes(recs),
                              ' '.join(sorted({n.split('@')[0]
                                               for n in notes}))))
            except convert.Unsupported as e:
                row.setdefault('tried', []).append('convert: %s' % e)
            fixed = []
            for route, b, notes in cands:
                if publics(b)[0] != dname:
                    b = set_theadr(b, dname)
                    notes = (notes + ' name-case-from-dictionary').strip()
                fixed.append((route, b, notes))
            cands = fixed
            chosen = None
            results = []
            for route, b, notes in cands:
                ok, why = check(b, start, end, genuine, lib.data)
                results.append((route, b, ok, why, notes))
                if ok and chosen is None:
                    chosen = (route, b, notes)
            agree = [r for r, b, ok, why, n in results
                     if chosen and b == chosen[1] and r != chosen[0]]
            disagree = [r for r, b, ok, why, n in results
                        if chosen and b != chosen[1]]
            if chosen:
                route, b, notes = chosen
                out[start:end] = b + bytes(end - start - len(b))
                row['status'] = 'anchored' if ngen else 'inferred'
                row['route'] = route
                notes = notes.strip()
                if route == 'cross':
                    o_start, o_end = ok_lib.span(ok_lib.starts[i])
                    if repair_note(OTHER[k], o_start, o_end):
                        # the bytes come from the other library's repaired
                        # module
                        notes = (notes + ' cross-from-repaired').strip()
                # repaired bytes of this library inside the span
                repaired = repair_note(k, start, end)
                row['notes'] = '; '.join(x for x in (notes, repaired) if x)
            else:
                row['status'] = 'FAILED'
                row['route'] = ''
                row['notes'] = '; '.join('%s: %s' % (r, why)
                                         for r, b, ok, why, n in results) \
                    or '; '.join(row.get('tried', []))
            row['agrees'] = ' '.join(agree)
            row['disagrees'] = ' '.join(
                '%s(%s)' % (r, 'fails check' if not ok else 'other bytes')
                for r, b, ok, why, n in results
                if chosen and b != chosen[1])
            rows.append(row)
        # the dictionary must name exactly the rebuilt modules' publics
        rebuilt = survey.lib_from_bytes(bytes(out))
        for i, start in enumerate(rebuilt.starts):
            dnames = set(rebuilt.names[start])
            if any(r['lib'] == 'CLIB%s' % k and r['index'] == i and
                   r['status'] == 'FAILED' for r in rows):
                continue
            end = rebuilt.starts[i + 1] if i + 1 < len(rebuilt.starts) \
                else endmods
            theadr, pubs = publics(bytes(out[start:end]))
            want = set(pubs) | {theadr + '!'}
            norm, have = dnames, want
            if norm != have:
                for r in rows:
                    if r['lib'] == 'CLIB%s' % k and r['index'] == i:
                        r['status'] = 'FAILED'
                        r['notes'] += ' dictionary mismatch: %s vs %s' % (
                            sorted(norm - have), sorted(have - norm))
        # every genuine byte kept (the repairs excepted)
        for o in genuine:
            if out[o] != lib.data[o]:
                raise SystemExit('genuine byte %d changed in CLIB%s' % (o, k))
        with open(os.path.join(outdir, 'CLIB%s.LIB' % k), 'wb') as f:
            f.write(out)
    for r in rows:
        r['confidence'] = confidence(r)
    fields = ['lib', 'index', 'module', 'offset', 'span', 'genuine_bytes',
              'status', 'route', 'confidence', 'agrees', 'disagrees',
              'notes']
    with open(os.path.join(outdir, 'PROVENANCE.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    from collections import Counter
    for k in 'SC':
        c = Counter((r['status'], r.get('route', '')) for r in rows
                    if r['lib'] == 'CLIB%s' % k)
        print('CLIB%s: %s' % (k, ', '.join(
            '%s%s %d' % (s, '/' + rt if rt else '', n)
            for (s, rt), n in sorted(c.items()))))
    if verbose:
        for r in rows:
            if r['status'] not in ('original',):
                print('  %(lib)s %(index)3d %(module)-10s %(status)-9s '
                      '%(route)-8s %(notes)s' % dict(r, route=r.get(
                          'route', '')))
    failed = [r for r in rows if r['status'] == 'FAILED']
    if failed:
        print('FAILED: %s' % ', '.join('%s %s' % (r['lib'], r['module'])
                                       for r in failed))
        if {r['module'] for r in failed} <= set(recompile.MODULES):
            print('these are rebuilt from recompiled objects: run '
                  'tools/recompile.py first (restore.py does)')
        print('the libraries in %s are written but INCOMPLETE' % outdir)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
