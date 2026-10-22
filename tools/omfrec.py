"""omfrec.py - decode and re-encode the OMF-86 records Watcom C 6.5 writes.

decode(t, body) turns a record body (no checksum) into a dict; encode(rec)
turns it back into the body, byte for byte (roundtrip() checks this on every
record of a library).  Records carry 'type' and, where the encoding has
choices, enough to reproduce them (index forms, thread use).

Record types handled: THEADR 80, COMENT 88, MODEND 8A, EXTDEF 8C, PUBDEF 90,
LNAMES 96, SEGDEF 98, GRPDEF 9A, FIXUPP 9C, LEDATA A0, LIDATA A2.  Anything
else is kept raw.
"""

import omf


def rd_index(b, i):
    """(value, next offset, long form?)"""
    if b[i] & 0x80:
        return (b[i] & 0x7F) << 8 | b[i + 1], i + 2, True
    return b[i], i + 1, False


def wr_index(v, long_form=False):
    if long_form or v > 0x7F:
        return bytes((0x80 | v >> 8, v & 0xFF))
    return bytes((v,))


def rd_name(b, i):
    n = b[i]
    return b[i + 1:i + 1 + n].decode('latin1'), i + 1 + n


def wr_name(s):
    e = s.encode('latin1')
    return bytes((len(e),)) + e


def w16(v):
    return bytes((v & 0xFF, v >> 8 & 0xFF))


def r16(b, i):
    return b[i] | b[i + 1] << 8


# FIXUP location field names (bits 5..2 of the first byte)
LOC = {0: 'lobyte', 1: 'offset', 2: 'base', 3: 'pointer', 4: 'hibyte'}


def _fixdat(b, i, d):
    """Decode a FIXDAT byte and its datums into d; return next offset."""
    f = b[i]
    i += 1
    d['F'] = f >> 7 & 1
    d['frame'] = f >> 4 & 7
    d['T'] = f >> 3 & 1
    d['P'] = f >> 2 & 1
    d['targt'] = f & 3
    if not d['F'] and d['frame'] < 3:
        d['fdatum'], i, d['fl'] = rd_index(b, i)
    if not d['T']:
        d['tdatum'], i, d['tl'] = rd_index(b, i)
    if not d['P']:
        d['disp'] = r16(b, i)
        i += 2
    return i


def _wr_fixdat(d):
    out = bytes((d['F'] << 7 | d['frame'] << 4 | d['T'] << 3 | d['P'] << 2 |
                 d['targt'],))
    if not d['F'] and d['frame'] < 3:
        out += wr_index(d['fdatum'], d.get('fl'))
    if not d['T']:
        out += wr_index(d['tdatum'], d.get('tl'))
    if not d['P']:
        out += w16(d['disp'])
    return out


def decode(t, b):
    r = {'type': t}
    if t == 0x80:
        r['name'] = rd_name(b, 0)[0]
    elif t == 0x96:
        r['names'] = []
        i = 0
        while i < len(b):
            s, i = rd_name(b, i)
            r['names'].append(s)
    elif t == 0x8C:
        r['ext'] = []
        i = 0
        while i < len(b):
            s, i = rd_name(b, i)
            ti, i, _ = rd_index(b, i)
            r['ext'].append((s, ti))
    elif t == 0x98:
        acbp = b[0]
        r['acbp'] = acbp
        i = 1
        if acbp >> 5 == 0:
            r['absframe'] = r16(b, 1)
            r['absoff'] = b[3]
            i = 4
        r['length'] = r16(b, i)
        i += 2
        r['name'], i, _ = rd_index(b, i)
        r['cls'], i, _ = rd_index(b, i)
        r['ovl'], i, _ = rd_index(b, i)
        assert i == len(b)
    elif t == 0x9A:
        r['name'], i, _ = rd_index(b, 0)
        r['segs'] = []
        while i < len(b):
            assert b[i] == 0xFF
            s, i, _ = rd_index(b, i + 1)
            r['segs'].append(s)
    elif t == 0x90:
        r['grp'], i, _ = rd_index(b, 0)
        r['seg'], i, _ = rd_index(b, i)
        if r['grp'] == 0 and r['seg'] == 0:
            r['frame'] = r16(b, i)
            i += 2
        r['pubs'] = []
        while i < len(b):
            s, i = rd_name(b, i)
            off = r16(b, i)
            ti, i, _ = rd_index(b, i + 2)
            r['pubs'].append((s, off, ti))
    elif t == 0xA0 or t == 0xA2:
        r['seg'], i, _ = rd_index(b, 0)
        r['off'] = r16(b, i)
        r['data'] = bytes(b[i + 2:])
    elif t == 0x9C:
        r['subs'] = []
        i = 0
        while i < len(b):
            x = b[i]
            if x & 0x80:
                d = {'kind': 'fixup', 'M': x >> 6 & 1, 'loc': x >> 2 & 0xF,
                     'at': (x & 3) << 8 | b[i + 1]}
                i = _fixdat(b, i + 2, d)
            else:
                d = {'kind': 'thread', 'D': x >> 6 & 1, 'method': x >> 2 & 7,
                     'thred': x & 3, 'z': x >> 5 & 1}
                i += 1
                # frame threads F0-F2 and target threads T0-T2 (T4-T6
                # alias them) carry an index
                if (d['method'] if d['D'] else d['method'] & 3) < 3:
                    d['datum'], i, d['l'] = rd_index(b, i)
            r['subs'].append(d)
    elif t == 0x8A:
        r['mtype'] = b[0]
        if b[0] & 0x40:
            d = {}
            i = _fixdat(b, 1, d)
            r['start'] = d
            assert i == len(b)
        else:
            r['tail'] = bytes(b[1:])
    else:
        r['raw'] = bytes(b)
    return r


def encode(r):
    t = r['type']
    if 'raw' in r:
        return r['raw']
    if t == 0x80:
        return wr_name(r['name'])
    if t == 0x96:
        return b''.join(wr_name(s) for s in r['names'])
    if t == 0x8C:
        return b''.join(wr_name(s) + wr_index(ti) for s, ti in r['ext'])
    if t == 0x98:
        out = bytes((r['acbp'],))
        if r['acbp'] >> 5 == 0:
            out += w16(r['absframe']) + bytes((r['absoff'],))
        return out + w16(r['length']) + wr_index(r['name']) + \
            wr_index(r['cls']) + wr_index(r['ovl'])
    if t == 0x9A:
        return wr_index(r['name']) + b''.join(
            b'\xff' + wr_index(s) for s in r['segs'])
    if t == 0x90:
        out = wr_index(r['grp']) + wr_index(r['seg'])
        if r['grp'] == 0 and r['seg'] == 0:
            out += w16(r['frame'])
        return out + b''.join(wr_name(s) + w16(o) + wr_index(ti)
                              for s, o, ti in r['pubs'])
    if t == 0xA0 or t == 0xA2:
        return wr_index(r['seg']) + w16(r['off']) + r['data']
    if t == 0x9C:
        out = b''
        for d in r['subs']:
            if d['kind'] == 'fixup':
                out += bytes((0x80 | d['M'] << 6 | d['loc'] << 2 |
                              d['at'] >> 8, d['at'] & 0xFF))
                out += _wr_fixdat(d)
            else:
                out += bytes((d['D'] << 6 | d['z'] << 5 | d['method'] << 2 |
                              d['thred'],))
                if 'datum' in d:
                    out += wr_index(d['datum'], d.get('l'))
        return out
    if t == 0x8A:
        out = bytes((r['mtype'],))
        if 'start' in r:
            return out + _wr_fixdat(r['start'])
        return out + r['tail']
    raise ValueError('cannot encode %02X' % t)


def record(r):
    """Whole record bytes: type, length, body, checksum."""
    body = encode(r)
    rec = bytes((r['type'],)) + w16(len(body) + 1) + body
    return rec + bytes(((-sum(rec)) & 0xFF,))


def module_bytes(recs):
    return b''.join(record(r) for r in recs)


def decode_module(raw):
    """[(type, body, offset)] from omf.Lib.module -> [record dicts]"""
    return [decode(t, b) for t, b, o in raw]


def describe(r):
    """One-line view of a decoded record."""
    t = r['type']
    nm = omf.NAMES.get(t & 0xFE, '%02X' % t)
    x = dict(r)
    del x['type']
    if 'data' in x:
        x['data'] = x['data'].hex()
    return '%s %s' % (nm, x)


def roundtrip(path):
    """(records checked, mismatches) over every readable module."""
    lib = omf.Lib(path)
    n = bad = 0
    for s in lib.starts:
        raw = lib.module(s)
        if not raw:
            continue
        for t, b, o in raw:
            n += 1
            if encode(decode(t, b)) != bytes(b):
                bad += 1
    return n, bad


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        print(p, roundtrip(p))
