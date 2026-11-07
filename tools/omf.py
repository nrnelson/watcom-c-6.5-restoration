"""omf.py - read Watcom C 6.5 OMF libraries (Intel OMF-86, 16-bit records).

A library is a header record (F0h, page size - 3 in its length field, the
dictionary offset and block count), modules each starting on a page
boundary, an end record (F1h) and the hashed dictionary.  Only reads.
"""

MODSTART = (0x80, 0x82)
MODEND = (0x8A, 0x8B)

NAMES = {0x80: 'THEADR', 0x82: 'LHEADR', 0x88: 'COMENT', 0x8A: 'MODEND',
         0x8C: 'EXTDEF', 0x90: 'PUBDEF', 0x94: 'LINNUM', 0x96: 'LNAMES',
         0x98: 'SEGDEF', 0x9A: 'GRPDEF', 0x9C: 'FIXUPP', 0xA0: 'LEDATA',
         0xA2: 'LIDATA', 0xB0: 'COMDEF', 0xB4: 'LEXTDEF', 0xB6: 'LPUBDEF',
         0xB8: 'LCOMDEF'}


class Lib(object):
    def __init__(self, path, data=None):
        if data is None:
            with open(path, 'rb') as f:
                data = f.read()
        self.data = d = bytes(data)
        if d[0] != 0xF0:
            raise ValueError('%s: not an OMF library' % path)
        self.page = (d[1] | d[2] << 8) + 3
        self.dict_at = d[3] | d[4] << 8 | d[5] << 16 | d[6] << 24
        self.dict_blocks = d[7] | d[8] << 8
        self.names = self._dictionary()      # page offset -> [public names]
        self.starts = sorted(self.names)

    @classmethod
    def from_bytes(cls, data, name='<bytes>'):
        return cls(name, data)

    def _dictionary(self):
        d = self.data
        out = {}
        for b in range(self.dict_blocks):
            blk = d[self.dict_at + b * 512:self.dict_at + b * 512 + 512]
            for k in range(37):
                o = blk[k] * 2
                if not o:
                    continue
                n = blk[o]
                name = blk[o + 1:o + 1 + n].decode('latin1')
                page = blk[o + 1 + n] | blk[o + 2 + n] << 8
                out.setdefault(page * self.page, []).append(name)
        return out

    def end_of_modules(self):
        """Offset of the library end record (F1h), which follows the last
        module's page span."""
        d = self.data
        o = self.starts[-1]
        raw = self.module(o)
        if raw:
            t, b, p = raw[-1]
            o = p + 3 + len(b) + 1
        while d[o] != 0xF1:
            o += 1
        return o

    def span(self, start):
        """(start, end) of the page span the dictionary gives a module; the
        last module's ends at the end record."""
        i = self.starts.index(start)
        end = self.starts[i + 1] if i + 1 < len(self.starts) else \
            self.end_of_modules()
        return start, end

    def module(self, start):
        """Records [(type, body without checksum, offset)] of the module at
        start, or None when a record is cut off or fails its checksum."""
        d = self.data
        i = start
        recs = []
        while True:
            if i + 3 > len(d):
                return None
            t = d[i]
            n = d[i + 1] | d[i + 2] << 8
            end = i + 3 + n
            if n == 0 or end > self.dict_at:
                return None
            if d[end - 1] != 0 and sum(d[i:end]) & 0xFF:
                return None
            recs.append((t, d[i + 3:end - 1], i))
            i = end
            if t in MODEND:
                return recs
            if not recs[0][0] in MODSTART:
                return None


def theadr(recs):
    b = recs[0][1]
    return b[1:1 + b[0]].decode('latin1')


def index(b, i):
    """OMF index field at b[i]: (value, next offset)."""
    if b[i] & 0x80:
        return (b[i] & 0x7F) << 8 | b[i + 1], i + 2
    return b[i], i + 1


def names(b):
    """Length-prefixed names of an LNAMES/EXTDEF-style body (EXTDEF has a
    type index after each name)."""
    out = []
    i = 0
    while i < len(b):
        n = b[i]
        out.append(b[i + 1:i + 1 + n].decode('latin1'))
        i += 1 + n
    return out


def describe(t, b):
    """One-line human-readable view of a record body."""
    nm = NAMES.get(t & 0xFE, '%02X' % t)
    if t == 0x96:
        return '%s %s' % (nm, names(b))
    if t == 0xA0:
        seg, i = index(b, 0)
        off = b[i] | b[i + 1] << 8
        return '%s seg%d @%04X %s' % (nm, seg, off, b[i + 2:].hex())
    return '%s %s' % (nm, b.hex())
