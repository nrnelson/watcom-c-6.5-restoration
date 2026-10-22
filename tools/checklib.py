"""checklib.py - an independent integrity check of OMF libraries.

usage: python3 -I tools/checklib.py LIB [LIB ...]

Walks each library from the start, not through its dictionary: the header,
then module after module (each from THEADR to MODEND, every record's length
and checksum checked, the next module on the next 16-byte page after the
previous one's padding), then the end record and the dictionary.  Checks
that every module the dictionary names starts where the dictionary says,
and that every module found is in the dictionary.  This is how a strict
reader sees a library: a module that leaves an extra empty page, or a
damaged record, stops it.

Exit status 0 when every library is sound, 1 otherwise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import omf  # noqa: E402

TYPES = {0x80, 0x88, 0x8A, 0x8C, 0x90, 0x96, 0x98, 0x9A, 0x9C, 0xA0, 0xA2}


def check(path):
    lib = omf.Lib(path)
    d = lib.data
    page = lib.page
    # the first module starts on the first page after the header record
    o = (3 + (d[1] | d[2] << 8) + page - 1) // page * page
    found = []
    while True:
        if d[o] == 0xF1:
            break
        if d[o] != 0x80:
            return 'module %d at offset %d does not start with THEADR' % (
                len(found) + 1, o)
        start = o
        while True:
            t = d[o]
            n = d[o + 1] | d[o + 2] << 8
            end = o + 3 + n
            if t not in TYPES or n == 0 or end > lib.dict_at:
                return 'bad record %02Xh at offset %d' % (t, o)
            if d[end - 1] != 0 and sum(d[o:end]) & 0xFF:
                return 'record %02Xh at offset %d: bad checksum' % (t, o)
            o = end
            if t == 0x8A:
                break
        found.append(start)
        if any(d[o:(o + page - 1) // page * page]):
            return 'non-zero padding after the module at %d' % start
        o = (o + page - 1) // page * page
    if found != lib.starts:
        missing = sorted(set(lib.starts) - set(found))
        extra = sorted(set(found) - set(lib.starts))
        return 'modules and dictionary disagree (missing %s, extra %s)' % (
            missing[:3], extra[:3])
    return '%d modules ok' % len(found)


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    status = 0
    for p in argv[1:]:
        res = check(p)
        print('%s: %s' % (p, res))
        if not res.endswith('modules ok'):
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
