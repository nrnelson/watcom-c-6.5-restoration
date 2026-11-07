"""checklib.py - an independent integrity check of OMF libraries.

usage: python3 -I tools/checklib.py LIB [LIB ...]

Walks each library from the start, not through its dictionary: the header,
then module after module (each from THEADR to MODEND, every record's length
checked and every record's bytes summing to 0 mod 256, a zero checksum byte
included: METHOD.md section 3), the next module on the next page after the
previous one's zero padding; then the end record (F1h), which must start on
a page boundary, run exactly up to the dictionary and hold only zero bytes;
then the dictionary, which must fill the rest of the file.  Checks that
every module the dictionary names starts where the dictionary says, that
every module found is in the dictionary, and that the dictionary names at
each module's page are exactly the module's THEADR name + '!' and its
PUBDEF names.  This is how a strict reader sees a library: a module that
leaves an extra empty page, or a damaged record, stops it.

check(path) returns (ok, message).  Exit status 0 when every library is
sound, 1 otherwise.  tools/selfcheck.py shows that the checks bite.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import omf  # noqa: E402
import omfrec  # noqa: E402

TYPES = {0x80, 0x88, 0x8A, 0x8C, 0x90, 0x96, 0x98, 0x9A, 0x9C, 0xA0, 0xA2}


def check_lib(lib):
    """(ok, message) for an omf.Lib."""
    d = lib.data
    page = lib.page
    if lib.dict_at + lib.dict_blocks * 512 != len(d):
        return False, 'dictionary (%d + %d blocks) does not end the file ' \
            '(%d bytes)' % (lib.dict_at, lib.dict_blocks, len(d))
    # the first module starts on the first page after the header record
    o = (3 + (d[1] | d[2] << 8) + page - 1) // page * page
    found = []
    names = {}
    while True:
        if o >= lib.dict_at:
            return False, 'no end record before the dictionary'
        if d[o] == 0xF1:
            break
        if d[o] != 0x80:
            return False, 'module %d at offset %d does not start with ' \
                'THEADR' % (len(found) + 1, o)
        start = o
        want = set()
        while True:
            t = d[o]
            n = d[o + 1] | d[o + 2] << 8
            end = o + 3 + n
            if t not in TYPES or n == 0 or end > lib.dict_at:
                return False, 'bad record %02Xh at offset %d' % (t, o)
            if sum(d[o:end]) & 0xFF:
                return False, 'record %02Xh at offset %d: bad checksum' % (
                    t, o)
            body = d[o + 3:end - 1]
            if t == 0x80:
                want.add(body[1:1 + body[0]].decode('latin1') + '!')
            elif t == 0x90:
                want.update(p[0] for p in omfrec.decode(t, body)['pubs'])
            o = end
            if t == 0x8A:
                break
        found.append(start)
        names[start] = want
        if any(d[o:(o + page - 1) // page * page]):
            return False, 'non-zero padding after the module at %d' % start
        o = (o + page - 1) // page * page
    # the end record: padding up to the dictionary
    if o % page:
        return False, 'end record at %d is not on a page boundary' % o
    n = d[o + 1] | d[o + 2] << 8
    if o + 3 + n != lib.dict_at:
        return False, 'end record at %d declares its end at %d, the ' \
            'dictionary is at %d' % (o, o + 3 + n, lib.dict_at)
    if any(d[o + 3:o + 3 + n]):
        return False, 'end record at %d holds non-zero bytes' % o
    if found != lib.starts:
        missing = sorted(set(lib.starts) - set(found))
        extra = sorted(set(found) - set(lib.starts))
        return False, 'modules and dictionary disagree (missing %s, ' \
            'extra %s)' % (missing[:3], extra[:3])
    for start in found:
        have = set(lib.names[start])
        if have != names[start]:
            return False, 'dictionary names at the module at %d differ ' \
                'from its records (dictionary only %s, records only %s)' % (
                    start, sorted(have - names[start])[:3],
                    sorted(names[start] - have)[:3])
    return True, '%d modules ok' % len(found)


def check(path, data=None):
    """(ok, message) for the library at path (or its bytes, data)."""
    try:
        lib = omf.Lib(path, data)
    except (ValueError, IndexError) as e:
        return False, 'unreadable: %s' % e
    try:
        return check_lib(lib)
    except IndexError:
        return False, 'a record runs past the end of the file'


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    status = 0
    for p in argv[1:]:
        ok, res = check(p)
        print('%s: %s' % (p, res))
        if not ok:
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
