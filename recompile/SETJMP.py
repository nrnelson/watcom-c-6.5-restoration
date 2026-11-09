"""SETJMP.py - writes the reconstructed SETJMP.c at build time.

SETJMP is a C module whose two functions, _setjmp and longjmp, are made of
#pragma aux inline code.  Rather than carry Watcom's instruction bytes in
this repository, the source is generated from the user's own copy: the
far-code forms are taken from the CLIBM (near data) and CLIBL (far data)
modules, and the small-code forms (CLIBS, CLIBC) are edits of them:

  _setjmp:  the far form saves the return address as two words, popping
            the offset to [si+14h] and the segment to [si+12h] and pushing
            them back; the near form pops the offset to [si+14h], stores
            CS in [si+12h] (mov [si+12h],cs where the far form pops) and
            pushes the offset back (push [si+12h] dropped), so the jmp_buf
            layout is the same in every model.
  longjmp:  the far form discards the 4-byte return address (add sp,4) and
            pushes segment and offset before its final RETF; the near form
            discards 2 bytes with pop di (DI is reloaded from the buffer
            afterwards), pushes the offset only and ends in RET.

The exact medium and large objects do not test these edits, since they
are not compiled from the same instruction list, and no small- or
compact-model SETJMP survives in the libraries.  The small list is the
code DISK3/WLIB.EXE, a small-model program, calls: its near call at file
offset 0xd01 reaches _setjmp at 0x2852 and its tail jump at 0xf4f reaches
longjmp, and all 84 code bytes there, which hold no fixup fields, equal
the small object's.  The compact list applies the same edits to the large
form (which addresses the buffer through DS, so the same instruction
bytes apply); no shipped program checks it.  NOTE gives the provenance
note of each: near-code-witnessed:FILE@hex for the small object,
near-code-inferred for the compact one.  The compiler adds RETF or RET
after _setjmp itself.

generate(lib) returns the C source; lib(key) gives the omf.Lib of CLIB<key>.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'tools'))

import omfrec  # noqa: E402
import x86  # noqa: E402

POP_SEG = b'\x8f\x44\x12'       # pop  word ptr [si+12h]
MOV_CS_SEG = b'\x8c\x4c\x12'    # mov  [si+12h],cs
PUSH_SEG = b'\xff\x74\x12'      # push word ptr [si+12h]
ADD_SP4 = b'\x83\xc4\x04'       # add  sp,4
POP_DI = b'\x5f'                 # pop  di
# the provenance note of the small (S) and compact (C) objects, by model
# (tools/recompile.py writes it to the status file, tools/rebuild.py
# grades a near-code- note medium)
NOTE = {'S': 'near-code-witnessed:DISK3/WLIB.EXE@2852',
        'C': 'near-code-inferred'}


def functions(lib):
    """(_setjmp bytes without its final RETF, longjmp bytes) of a library's
    SETJMP module."""
    for s in lib.starts:
        raw = lib.module(s)
        if raw and raw[0][0] == 0x80 and raw[0][1][1:].startswith(b'SETJMP'):
            recs = omfrec.decode_module(raw)
            code = b''.join(r['data'] for r in recs
                            if r['type'] == 0xA0 and r['seg'] == 1)
            pubs = {n: o for r in recs if r['type'] == 0x90
                    for n, o, t in r['pubs']}
            lj = pubs['longjmp_']
            sj = code[pubs['_setjmp_']:lj]
            if sj[-1:] != b'\xcb':
                raise SystemExit('SETJMP: unexpected _setjmp ending')
            return sj[:-1], code[lj:]
    raise SystemExit('SETJMP module not found')


def insns(code):
    out = []
    i = 0
    while i < len(code):
        n = x86.decode(code, i).len
        out.append(code[i:i + n])
        i += n
    return out


def near_setjmp(code):
    parts = insns(code)
    if POP_SEG not in parts or PUSH_SEG not in parts:
        raise SystemExit('SETJMP: return-address handling not found')
    parts[parts.index(POP_SEG)] = MOV_CS_SEG
    parts.remove(PUSH_SEG)
    return b''.join(parts)


def near_longjmp(code):
    parts = insns(code)
    if ADD_SP4 not in parts or PUSH_SEG not in parts or parts[-1] != b'\xcb':
        raise SystemExit('SETJMP: return-address handling not found')
    parts[parts.index(ADD_SP4)] = POP_DI
    parts.remove(PUSH_SEG)
    parts[-1] = b'\xc3'
    return b''.join(parts)


def pragma(name, code, tail):
    lines = []
    for p in insns(code):
        lines.append('        ' + ' '.join('0x%02x' % b for b in p))
    return '#pragma aux %s = \\\n%s \\\n        %s;\n' % (
        name, ' \\\n'.join(lines), tail)


def variant(sj, lj, far_data):
    if far_data:
        return (pragma('__setjmp', sj, 'parm [ax dx] value [ax] '
                       'modify [ax dx]') +
                pragma('__longjmp', lj, 'parm [ax dx] [bx] aborts'))
    return (pragma('__setjmp', sj, 'parm [ax] value [ax] modify [ax]') +
            pragma('__longjmp', lj, 'parm [ax] [dx] aborts'))


def generate(lib):
    m_sj, m_lj = functions(lib('M'))
    l_sj, l_lj = functions(lib('L'))
    small = variant(near_setjmp(m_sj), near_longjmp(m_lj), False)
    medium = variant(m_sj, m_lj, False)
    compact = variant(near_setjmp(l_sj), near_longjmp(l_lj), True)
    large = variant(l_sj, l_lj, True)
    return ('/* SETJMP - generated by recompile/SETJMP.py from the CLIBM and '
            'CLIBL\n   modules of the original Watcom C 6.5 libraries.  Not '
            'Watcom\'s source.\n   6.5 has no #elif, so the model tests '
            'nest. */\n'
            '#include <setjmp.h>\n\n'
            'extern int __setjmp( jmp_buf env );\n'
            'extern void __longjmp( jmp_buf env, int val );\n\n'
            '#if defined(M_I86SM)\n' + small +
            '#else\n#if defined(M_I86MM)\n' + medium +
            '#else\n#if defined(M_I86CM)\n' + compact +
            '#else\n' + large +
            '#endif\n#endif\n#endif\n\n'
            'int _setjmp( jmp_buf env )\n{\n'
            '    return( __setjmp( env ) );\n}\n\n'
            'void longjmp( jmp_buf env, int val )\n{\n'
            '    __longjmp( env, val );\n}\n')
