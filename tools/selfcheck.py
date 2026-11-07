"""selfcheck.py - show that tools/checklib.py rejects damaged libraries.

usage: python3 -I tools/selfcheck.py [LIB]

LIB (default out/CLIBS.LIB) must pass checklib.  Then, in memory, one
byte at a time:
  a. the checksum byte of the first module's THEADR is set to 0
     (offset 26 in the restored CLIBS.LIB, FBh)
  b. the first character of a public name in the dictionary is set to '?'
     (_full_io_exit_, offset 86793 in the restored CLIBS.LIB)
  c. the first payload byte of the end record (F1h) is set to 1
     (offset 86131 in the restored CLIBS.LIB)
  d. the end record's declared length is decreased by one
and checklib must reject each for that reason.  Exit status 0 when it
does, 1 on any surprise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checklib  # noqa: E402
import omf  # noqa: E402
import paths  # noqa: E402


def end_record(lib):
    """Offset of the end record (F1h): walk the modules record by record."""
    d = lib.data
    o = (3 + (d[1] | d[2] << 8) + lib.page - 1) // lib.page * lib.page
    while d[o] != 0xF1:
        while True:
            t = d[o]
            o += 3 + (d[o + 1] | d[o + 2] << 8)
            if t == 0x8A:
                break
        o = (o + lib.page - 1) // lib.page * lib.page
    return o


def public_in_dictionary(lib):
    """(offset of the first character, name) of a public (not a module
    name) in the dictionary; _full_io_exit_ when present."""
    d = lib.data
    found = []
    for b in range(lib.dict_blocks):
        base = lib.dict_at + b * 512
        for k in range(37):
            o = d[base + k] * 2
            if not o:
                continue
            n = d[base + o]
            name = d[base + o + 1:base + o + 1 + n].decode('latin1')
            if not name.endswith('!'):
                found.append((base + o + 1, name))
    for at, name in found:
        if name == '_full_io_exit_':
            return at, name
    return min(found)


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(paths.OUT,
                                                       'CLIBS.LIB')
    with open(path, 'rb') as f:
        data = f.read()
    ok, msg = checklib.check(path, data)
    print('unmodified: %s' % msg)
    if not ok:
        print('SURPRISE: the unmodified library fails')
        return 1
    lib = omf.Lib(path, data)
    first = lib.starts[0]
    theadr_sum = first + 3 + (data[first + 1] | data[first + 2] << 8) - 1
    name_at, name = public_in_dictionary(lib)
    f1 = end_record(lib)
    f1_len = data[f1 + 1] | data[f1 + 2] << 8
    shorter = f1_len - 1
    cases = [
        ('a. THEADR checksum byte %d (%02Xh) set to 0' % (
            theadr_sum, data[theadr_sum]), {theadr_sum: 0}, 'bad checksum'),
        ('b. dictionary name %s (offset %d) spelt ?%s' % (
            name, name_at, name[1:]), {name_at: ord('?')},
         'dictionary names'),
        ('c. end record payload byte %d set to 1' % (f1 + 3), {f1 + 3: 1},
         'non-zero bytes'),
        ('d. end record length %d -> %d' % (f1_len, shorter),
         {f1 + 1: shorter & 0xFF, f1 + 2: shorter >> 8}, 'declares its end'),
    ]
    status = 0
    for label, change, why in cases:
        bad = bytearray(data)
        for o, v in change.items():
            bad[o] = v
        ok, msg = checklib.check(path, bytes(bad))
        good = not ok and why in msg
        print('%s: %s -> %s' % (label, 'rejected' if not ok else 'ACCEPTED',
                                msg))
        if not good:
            print('  SURPRISE: expected a rejection mentioning "%s"' % why)
            status = 1
    print('selfcheck %s' % ('passed' if status == 0 else 'FAILED'))
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
