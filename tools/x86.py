"""x86.py - a small 8086/80186 (+8087 escape) instruction decoder.

Only what the converter needs: each instruction's length, its kind (call,
jump, return, ...), the position and size of a relative displacement, and
of a ModR/M memory displacement with its base register.
"""

PREFIX = {0x26, 0x2E, 0x36, 0x3E, 0xF0, 0xF2, 0xF3}

# kinds
CALL_NEAR, CALL_FAR, JMP_NEAR, JMP_SHORT, JMP_FAR, JCC, LOOP = \
    'call', 'callf', 'jmp', 'jmps', 'jmpf', 'jcc', 'loop'
RET, RETF, RETN, RETFN = 'ret', 'retf', 'retn', 'retfn'
CALL_IND, JMP_IND = 'calli', 'jmpi'


class Insn(object):
    __slots__ = ('off', 'len', 'op', 'kind', 'rel', 'relsz', 'modrm',
                 'mod', 'reg', 'rm', 'disp', 'dispsz', 'imm', 'immsz',
                 'prefixes')

    def __init__(self, off):
        self.off = off
        self.len = 0
        self.op = None
        self.kind = None
        self.rel = None      # offset (within code) of rel8/rel16 field
        self.relsz = 0
        self.modrm = None    # offset of ModR/M byte
        self.mod = self.reg = self.rm = None
        self.disp = None     # offset of ModR/M displacement
        self.dispsz = 0
        self.imm = None
        self.immsz = 0
        self.prefixes = []

    def target(self, code):
        """Absolute target of a relative branch."""
        if self.rel is None:
            return None
        if self.relsz == 1:
            d = code[self.rel]
            d -= 256 if d > 127 else 0
        else:
            d = code[self.rel] | code[self.rel + 1] << 8
            d -= 65536 if d > 32767 else 0
        return (self.off + self.len + d) & 0xFFFF

    def bp_based(self):
        """True when the memory operand is [bp+disp] or [bp+si/di+disp]
        (rm 2, 3, 6 with mod != 0)."""
        return self.mod in (1, 2) and self.rm in (2, 3, 6)

    def __repr__(self):
        return '<%04X %s len %d %s>' % (self.off, '%02X' % self.op,
                                        self.len, self.kind)


# opcodes with a ModR/M byte (8086 + 186)
MODRM = set(range(0x00, 0x40)) - {0x04, 0x05, 0x06, 0x07, 0x0C, 0x0D, 0x0E,
                                  0x0F, 0x14, 0x15, 0x16, 0x17, 0x1C, 0x1D,
                                  0x1E, 0x1F, 0x24, 0x25, 0x26, 0x27, 0x2C,
                                  0x2D, 0x2E, 0x2F, 0x34, 0x35, 0x36, 0x37,
                                  0x3C, 0x3D, 0x3E, 0x3F}
MODRM |= {0x62, 0x63, 0x69, 0x6B} | set(range(0x80, 0x90)) | \
    {0xC0, 0xC1, 0xC4, 0xC5, 0xC6, 0xC7} | set(range(0xD0, 0xD4)) | \
    set(range(0xD8, 0xE0)) | {0xF6, 0xF7, 0xFE, 0xFF}

# immediate sizes (beyond ModR/M); 'w' = 2 bytes
IMM1 = {0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C, 0x6A, 0x6B, 0x80,
        0x82, 0x83, 0xA8, 0xC0, 0xC1, 0xC6, 0xCD, 0xD4, 0xD5, 0xE4, 0xE5,
        0xE6, 0xE7} | set(range(0xB0, 0xB8))
IMM2 = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D, 0x68, 0x69, 0x81,
        0xA9, 0xC7, 0xA0, 0xA1, 0xA2, 0xA3} | set(range(0xB8, 0xC0))


def decode(code, i):
    """Decode the instruction at code[i]; returns an Insn (raises
    ValueError on an opcode it does not know)."""
    x = Insn(i)
    p = i
    while code[p] in PREFIX:
        x.prefixes.append(code[p])
        p += 1
    op = code[p]
    x.op = op
    p += 1
    if op in MODRM:
        m = code[p]
        x.modrm = p
        x.mod, x.reg, x.rm = m >> 6, m >> 3 & 7, m & 7
        p += 1
        if x.mod == 0 and x.rm == 6:
            x.disp, x.dispsz = p, 2
        elif x.mod == 1:
            x.disp, x.dispsz = p, 1
        elif x.mod == 2:
            x.disp, x.dispsz = p, 2
        p += x.dispsz
        if op == 0xF6 and x.reg in (0, 1):
            x.imm, x.immsz = p, 1
        elif op == 0xF7 and x.reg in (0, 1):
            x.imm, x.immsz = p, 2
        elif op == 0xFF:
            x.kind = {2: CALL_IND, 3: CALL_IND, 4: JMP_IND,
                      5: JMP_IND}.get(x.reg)
    if op in IMM1:
        x.imm, x.immsz = p, 1
    elif op in IMM2:
        x.imm, x.immsz = p, 2
    p += x.immsz
    if 0x70 <= op <= 0x7F:
        x.kind, x.rel, x.relsz = JCC, p, 1
        p += 1
    elif 0xE0 <= op <= 0xE3:
        x.kind, x.rel, x.relsz = LOOP, p, 1
        p += 1
    elif op == 0xEB:
        x.kind, x.rel, x.relsz = JMP_SHORT, p, 1
        p += 1
    elif op == 0xE8:
        x.kind, x.rel, x.relsz = CALL_NEAR, p, 2
        p += 2
    elif op == 0xE9:
        x.kind, x.rel, x.relsz = JMP_NEAR, p, 2
        p += 2
    elif op == 0x9A:
        x.kind = CALL_FAR
        p += 4
    elif op == 0xEA:
        x.kind = JMP_FAR
        p += 4
    elif op == 0xC3:
        x.kind = RET
    elif op == 0xCB:
        x.kind = RETF
    elif op == 0xC2:
        x.kind = RETN
        x.imm, x.immsz = p, 2
        p += 2
    elif op == 0xCA:
        x.kind = RETFN
        x.imm, x.immsz = p, 2
        p += 2
    elif op == 0xC8:
        p += 3
    elif op in (0x0F, 0x63, 0x64, 0x65, 0x66, 0x67, 0xD6, 0xF1) or \
            (op == 0xFF and x.reg == 7) or (op == 0xFE and x.reg > 1):
        raise ValueError('unknown opcode %02X at %04X' % (op, i))
    x.len = p - i
    if p > len(code):
        raise ValueError('instruction at %04X runs past the end' % i)
    return x
