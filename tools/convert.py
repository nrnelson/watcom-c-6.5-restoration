"""convert.py - turn a big-code Watcom C 6.5 library module into its
small-code twin: medium (CLIBM) -> small (CLIBS), large (CLIBL) -> compact
(CLIBC).

convert(recs) takes the decoded records of the big-code module
(omfrec.decode_module) and returns (records, notes): the converted records
and a list of notes about anything the mechanical rules could not handle
(each note names a reason; a module with notes is not expected to match).

The rules, learned from the surviving pairs and from 6.5 probe compiles
(medium = wcc /mm /s /g=CLIBM, small = wcc /ms /s, large = wcc /ml /s,
compact = wcc /mc /s):

records
  LNAMES   drop the code group name CLIBM; the code segment (CLIBM_TEXT,
           <MODULE>_TEXT) becomes _TEXT; indexes renumbered
  SEGDEF   name/class indexes renumbered, code length recomputed
  GRPDEF   the code group (CLIBM) is dropped, the others renumbered
  EXTDEF   _big_code_ -> _small_code_
  PUBDEF   base group of the code group -> 0
  FIXUPP   far calls/jumps (loc pointer) -> self-relative offsets; a frame
           of the code group -> frame of the target (F5); group indexes
           renumbered; positions and code displacements relocated
code
  CALL FAR ptr (9A) -> CALL near (E8); JMP FAR ptr (EA) -> JMP near (E9)
  RETF -> RET, RETF n -> RET n
  [bp+d] at or above the return address: d - 2 (near return address)
  relative branches recomputed; JMP near that now fits rel8 -> JMP short
  LEDATA   C modules: 189-byte chunks; a fixup is never split
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import omfrec  # noqa: E402
import x86  # noqa: E402

CHUNK = 189          # LEDATA size the 6.5 compiler writes
ASM_CHUNK = 1020     # LEDATA size of the assembler-written modules
ITERATE_JUMPS = False
FIXBODY = 195        # largest FIXUPP body the 6.5 compiler writes
# externals that stay far procedures in small code (see METHOD.md, decision 3: the
# compact SPAWNVE page span needs at least one far call; EXECADDR, which
# returns the far exec hook, is taken as a model-independent far routine)
KEEP_FAR = set(os.getenv('WCR_KEEP_FAR', '_execaddr_').split())
CROSS_JUMP = True    # merge exit sequences that small code makes identical
CJ_MIN = 5           # least bytes a merged tail must have
CJ_MAX = 65535       # farthest back (bytes) the compiler looks for a tail


class Unsupported(Exception):
    pass


def fixup_bytes(f):
    """Encoded size of one FIXUPP subrecord."""
    g = {k: v for k, v in f.items() if k not in ('seg', 'pos') and
         not k.startswith('_') and k != 'seg_is_code'}
    g.setdefault('at', 0)
    g['kind'] = 'fixup'
    return len(omfrec.encode({'type': 0x9C, 'subs': [g]}))


def fixup_size(f):
    return {0: 1, 1: 2, 2: 2, 3: 4, 4: 1}[f['loc']]


# ---------------------------------------------------------------- images

def segment_images(recs, seglens):
    """{seg: bytearray}, [fixup dict + 'seg', 'pos' (absolute)], and
    the set of segments that hold LIDATA."""
    img = {s: bytearray(n) for s, n in seglens.items()}
    fix = []
    lidata = set()
    last = None
    for r in recs:
        if r['type'] == 0xA0:
            s = r['seg']
            img[s][r['off']:r['off'] + len(r['data'])] = r['data']
            last = r
        elif r['type'] == 0xA2:
            lidata.add(r['seg'])
            last = r
        elif r['type'] == 0x9C:
            if last is not None and last['type'] == 0xA2:
                continue        # kept as it is, see conv_rec
            if last is None:
                raise Unsupported('fixup-before-data')
            for d in r['subs']:
                if d['kind'] != 'fixup':
                    raise Unsupported('fixup-thread')
                f = dict(d)
                f['seg'] = last['seg']
                f['pos'] = last['off'] + d['at']
                fix.append(f)
    return img, fix, lidata


# ---------------------------------------------------------------- code

STOPS = {x86.JMP_NEAR, x86.JMP_SHORT, x86.JMP_FAR, x86.RET, x86.RETF,
         x86.RETN, x86.RETFN, x86.JMP_IND}


def is_exit(code, prev, x):
    """INT 21h function 4Ch: the program ends, nothing falls through."""
    if x.op != 0xCD or code[x.off + 1] != 0x21 or prev is None:
        return False
    return (prev.op == 0xB4 and code[prev.off + 1] == 0x4C) or \
        (prev.op == 0xB8 and code[prev.off + 2] == 0x4C)


def explore(code, entries, fixat, notes):
    """Recursive-descent disassembly from the entry points ->
    {start: Insn}.  Bytes never reached are data."""
    insns = {}
    work = sorted(set(entries), reverse=True)
    while work:
        i = work.pop()
        prev = None
        entry = True
        while 0 <= i < len(code) and i not in insns:
            try:
                x = x86.decode(code, i)
            except (ValueError, IndexError) as e:
                if entry:
                    raise Unsupported('decode: %s' % e)
                notes.append('fall-through-stopped@%04X' % i)
                break
            if i in fixat:
                if entry:
                    raise Unsupported('fixup-on-opcode@%04X' % i)
                notes.append('fall-through-stopped@%04X' % i)
                break
            insns[i] = x
            if x.rel is not None and x.rel not in fixat and \
                    x.kind != x86.CALL_FAR:
                work.append(x.target(code))
            if x.kind in STOPS or x.op in (0xCF, 0xF4) or \
                    is_exit(code, prev, x):
                break
            prev = x
            entry = False
            i += x.len
    return insns


PUSHES = set(range(0x50, 0x58)) | {0x06, 0x0E, 0x16, 0x1E}


def returns_near(code, start, insns):
    """True when every return reached from start (following jumps, not
    calls) is a near RET: the function is near in the big-code model too."""
    seen = set()
    work = [start]
    kinds = set()
    while work:
        o = work.pop()
        while o in insns and o not in seen:
            seen.add(o)
            x = insns[o]
            if x.kind in (x86.RET, x86.RETN):
                kinds.add('near')
                break
            if x.kind in (x86.RETF, x86.RETFN):
                kinds.add('far')
                break
            if x.rel is not None and x.kind in (x86.JMP_NEAR, x86.JMP_SHORT,
                                                x86.JCC, x86.LOOP):
                work.append(x.target(code))
                if x.kind in (x86.JMP_NEAR, x86.JMP_SHORT):
                    break
            if x.kind in (x86.JMP_FAR, x86.JMP_IND):
                break
            o += x.len
    return kinds == {'near'}


def interrupt_stubs(code, order, insns):
    """{call offset: (callee, retf offset)} for every INT emulated in
    inline assembly: pushf; push cs; call near L, where L pushes the vector
    and jumps to it with the first RETF at or after L (which stays)."""
    out = {}
    for x in order:
        if x.op == 0x0E and code[x.off - 1:x.off] == b'\x9c' and \
                x.off + 1 in insns and insns[x.off + 1].op == 0xE8:
            callee = insns[x.off + 1].target(code)
            for y in order:
                if y.off >= callee and y.kind == x86.RETF:
                    out[x.off + 1] = (callee, y.off)
                    break
    return out


POPS = set(range(0x58, 0x60)) | {0x07, 0x17, 0x1F, 0x9D}


def imm_value(code, x):
    """The immediate of x, an 8-bit one sign-extended."""
    n = code[x.imm] if x.immsz == 1 else code[x.imm] | code[x.imm + 1] << 8
    if x.immsz == 1 and n > 127:
        n -= 256
    return n


def writes_bp(x):
    """True when x writes BP other than by pop bp (mov, xchg, lea, lds/les,
    inc/dec, arithmetic with BP as destination)."""
    op = x.op
    return (op == 0x8B and x.reg == 5) or \
        (op == 0x89 and x.mod == 3 and x.rm == 5) or \
        (op == 0x87 and (x.reg == 5 or (x.mod == 3 and x.rm == 5))) or \
        op in (0x95, 0xBD, 0x45, 0x4D) or \
        (op in (0x8D, 0xC4, 0xC5) and x.reg == 5) or \
        (op in (0x81, 0x83) and x.mod == 3 and x.rm == 5 and x.reg != 7)


def frame_thresholds(code, order, starts, asm_entries=None, insns=None,
                     stubs=None):
    """{insn start: bp displacement of the return address} for every
    instruction inside a bp frame (None outside).  With asm_entries
    (assembler modules, where bp is often a plain register) only a
    'push bp; mov bp,sp' that opens one of those entry points counts.

    In compiled C (METHOD.md 7.3) BP is followed through the function in
    address order: the stub of an emulated INT (stubs, from
    interrupt_stubs) is inline code of the same function, and pushf; push
    cs; call with the stub is stack-neutral.  The stack depth below the
    frame is counted through pushes, pops, add/sub sp,n and mov sp,bp; a
    push bp while BP is the frame pointer records where the frame BP was
    saved; any other write to BP repurposes it (its [bp+d] are left alone)
    until a pop bp at the saved depth restores the frame.  A pop bp with no
    frame BP saved is the epilogue."""
    th = {}
    cur = None
    if asm_entries is not None:
        for x in order:
            if x.off in starts:
                cur = None
            if x.off in asm_entries and x.op == 0x55 and \
                    code[x.off + 1:x.off + 3] in (b'\x89\xe5', b'\x8b\xec'):
                cur = 2
            elif x.off in asm_entries and \
                    code[x.off:x.off + 2] in (b'\x89\xe5', b'\x8b\xec'):
                cur = 0         # mov bp,sp at the entry: bp+0 is the return
            th[x.off] = cur
        return th
    if stubs is None:
        stubs = interrupt_stubs(code, order, insns)
    callees = {c for c, r in stubs.values()}
    inert = set()           # pushf; push cs; call; and the stub itself
    for call, (callee, retf) in stubs.items():
        inert.update((call - 2, call - 1, call))
        inert.update(x.off for x in order if callee <= x.off <= retf)
    bp_frame, depth, saved, frame_mov = False, 0, None, None
    for n, x in enumerate(order):
        if x.off in starts and x.off not in callees:
            cur, bp_frame, depth, saved = None, False, 0, None
        if x.op == 0x55 and \
                code[x.off + 1:x.off + 3] in (b'\x89\xe5', b'\x8b\xec'):
            bp_frame, depth, saved = True, 0, None
            frame_mov = x.off + 1
            if returns_near(code, x.off, insns):
                # a near (static) function: same return address in both
                # code models, nothing to adjust
                cur = None
                th[x.off] = cur
                continue
            k = 0
            m = n - 1
            while m >= 0 and order[m].op in PUSHES and \
                    not order[m].prefixes and \
                    order[m].off + order[m].len == order[m + 1].off:
                k += 1
                if order[m].off in starts:
                    break
                m -= 1
            cur = 2 + 2 * k
            th[x.off] = cur
            continue
        if cur is None:
            th[x.off] = None
            continue
        th[x.off] = cur if bp_frame else None
        if x.off in inert or x.off == frame_mov:
            continue
        op = x.op
        if op in PUSHES or op == 0x9C or (op == 0xFF and x.reg == 6):
            depth += 1
            if op == 0x55 and bp_frame:
                saved = depth
        elif op == 0x5D:
            if saved is not None:
                bp_frame = depth == saved
                if bp_frame:
                    saved = None
            depth -= 1
        elif op in POPS or (op == 0x8F and x.reg == 0):
            depth -= 1
        elif op in (0x81, 0x83) and x.mod == 3 and x.rm == 4 and \
                x.reg in (0, 5):
            v = imm_value(code, x)
            depth += (-v if x.reg == 0 else v) // 2
        elif code[x.off:x.off + 2] in (b'\x89\xec', b'\x8b\xe5'):
            depth = 0
        elif writes_bp(x):
            bp_frame = False
    return th


def code_entries(code, fixups, pubs, start):
    """Sure entry points of the code segment: publics, the start address
    and the targets of self-relative fixups (calls and jumps)."""
    out = set(pubs)
    if start is not None:
        out.add(start)
    for f in fixups:
        if f.get('_tcode') and f['M'] == 0 and not f['P']:
            out.add(f['disp'])
    return out


def fixup_target(code, f):
    """Code offset a fixup of the code segment refers to, or None."""
    if not f.get('_tcode'):
        return None
    if not f['P']:
        return f['disp']
    if f['seg_is_code'] and f['loc'] == 1:
        p = f['pos']
        return code[p] | code[p + 1] << 8
    return None


def try_explore(code, start, insns, fixat):
    """Explore from start as a guess: the new instructions, or None when
    the path fails to decode, runs into a fixup at an opcode, or overlaps
    known instructions out of step."""
    scratch = []
    try:
        got = explore(code, [start], fixat, scratch)
    except Unsupported:
        return None
    if any(n.startswith('fall-through-stopped') for n in scratch):
        return None
    known = set()
    for x in insns.values():
        known.update(range(x.off + 1, x.off + x.len))
    for x in got.values():
        if x.off in known and x.off not in insns:
            return None
    return got


def is_text(code, a, b):
    """A run of 8 or more printable characters in code[a:b]."""
    run = 0
    for c in code[a:b]:
        run = run + 1 if 32 <= c < 127 else 0
        if run >= 8:
            return True
    return False


def explore_all(code, entries, fixups, fixat, notes, is_c=True):
    """explore() from the sure entries; then from the targets of offset
    fixups lying in data (jump tables in the code segment); then, in
    compiled C, from code offsets taken by instructions (function
    pointers) where a function may start (after an unconditional
    transfer); and last from gaps that directly follow an unconditional
    transfer and decode cleanly (dead code), until no new code is
    found."""
    insns = explore(code, entries, fixat, notes)
    while True:
        covered = set()
        for x in insns.values():
            covered.update(range(x.off, x.off + x.len))
        ends = {x.off + x.len for x in insns.values()
                if x.kind in STOPS or x.op in (0xCF, 0xF4)}
        more = set()
        guess = set()
        for f in fixups:
            if not f['seg_is_code']:
                continue
            t = fixup_target(code, f)
            if t is None or t in insns or not 0 <= t < len(code):
                continue
            if f['pos'] not in covered:
                more.add(t)
            elif is_c and t in ends:
                guess.add(t)
        if more:
            insns.update(explore(code, more, fixat, notes))
            continue
        for t in sorted(guess | {e for e in ends if e < len(code) and
                                 e not in covered}):
            if t in insns:
                continue
            nxt = min([k for k in insns if k > t] + [len(code)])
            if not is_c and is_text(code, t, nxt):
                continue
            got = try_explore(code, t, insns, fixat)
            if got:
                notes.append('guessed-code@%04X' % t)
                insns.update(got)
                break
        else:
            return insns


def convert_insn(code, x, th, fixat, notes, compiled=True):
    """The unit for one instruction: dict(start, b=[(old, byte)], rel,
    kind)."""
    b = [(x.off + j, code[x.off + j]) for j in range(x.len)]
    e = {'start': x.off, 'insn': x, 'b': b, 'rel': None, 'kind': x.kind}
    if x.kind in (x86.CALL_FAR, x86.JMP_FAR) and \
            fixat.get(x.off + 1, {}).get('_keepfar'):
        notes.append('kept-far-call@%04X' % x.off)
    elif x.kind in (x86.CALL_FAR, x86.JMP_FAR):
        f = fixat.get(x.off + 1)
        if f is None or f['loc'] != 3:
            raise Unsupported('far-branch-without-fixup@%04X' % x.off)
        f['_conv'] = 'near'
        op = 0xE8 if x.kind == x86.CALL_FAR else 0xE9
        e['b'] = [(x.off, op), (x.off + 1, code[x.off + 1]),
                  (x.off + 2, code[x.off + 2])]
        e['kind'] = 'fixed'
    elif x.kind == x86.RETF:
        e['b'] = [(x.off, 0xC3)]
    elif x.kind == x86.RETFN:
        e['b'] = [(x.off, 0xC2)] + b[1:]
    elif compiled and x.kind == x86.CALL_IND and x.reg == 3 and \
            x.mod == 0 and x.rm == 6 and x.disp in fixat:
        # call dword ptr [var]: a global code pointer, which small code
        # keeps in a word: call word ptr [var]
        e['b'] = [(o, (v & 0xC7) | 0x10) if o == x.modrm else (o, v)
                  for o, v in b]
        notes.append('near-code-pointer-call@%04X' % x.off)
    elif x.kind == x86.CALL_IND and x.reg == 3:
        notes.append('call-far-indirect@%04X' % x.off)
    elif x.kind == x86.JMP_IND and x.reg == 5:
        notes.append('jmp-far-indirect@%04X' % x.off)
    if x.rel is not None and x.rel in fixat:
        e['kind'] = 'fixed'     # near call/jump to an external
    elif x.rel is not None and x.kind != x86.CALL_FAR:
        e['rel'] = x.target(code)
    ret = th.get(x.off)
    if x.disp is not None and x.bp_based() and ret is not None:
        d = code[x.disp] if x.dispsz == 1 else \
            code[x.disp] | code[x.disp + 1] << 8
        if x.dispsz == 1 and d > 127:
            d -= 256
        elif x.dispsz == 2 and d > 32767:
            d -= 65536
        if ret <= d < ret + 4:
            notes.append('return-address-access@%04X' % x.off)
        elif d >= ret + 4:
            d -= 2
            short = x.dispsz == 2 and -128 <= d <= 127
            if short:
                notes.append('disp16-to-disp8@%04X' % x.off)
            nb = []
            for (o, v) in e['b']:
                if o == x.modrm and short:
                    nb.append((o, (v & 0x3F) | 0x40))
                elif o == x.disp:
                    nb.append((o, d & 0xFF))
                    if x.dispsz == 2 and not short:
                        nb.append((o + 1, d >> 8 & 0xFF))
                elif x.dispsz == 2 and o == x.disp + 1:
                    continue
                else:
                    nb.append((o, v))
            e['b'] = nb
    for p in range(x.off, x.off + x.len):
        if p in fixat:
            e['fix'] = True
            if not any(o == p for o, v in e['b']):
                raise Unsupported('fixup-in-dropped-bytes@%04X' % p)
    return e


RETS = (0xC3, 0xC2)


def plain(e):
    """A unit that can be part of a mergeable tail: an ordinary
    instruction with no branch and no fixup."""
    return e['kind'] not in ('data', 'dropped', 'fixed', 'jccpair') and \
        e.get('rel') is None and not e.get('fix') and e['b']


def cross_jump(units, targets, notes):
    """The 6.5 compiler replaces a function's exit sequence by a jump to
    the earliest identical one already emitted (cross-jumping).  Exits that
    differ in big code (RETF in public functions, RET in near static ones)
    can become identical in small code: merge them as the compiler would.

    Exits are taken in address order: a run of plain instructions ending in
    RET, or in a jump to an exit (an earlier merge; it counts as the
    instructions it jumps to).  Each is matched against the exits before
    it: the longest common tail wins, the earliest of equals."""
    pos = 0
    addr = []
    for e in units:
        addr.append(pos)
        pos += len(e['b'])
    index = {e['start']: n for n, e in enumerate(units)}

    def body(i):
        return [v for o, v in units[i]['b']]

    def run_before(n):
        t = []
        m = n - 1
        while m >= 0 and plain(units[m]) and \
                (not t or units[t[0]]['start'] not in targets):
            t.insert(0, m)
            m -= 1
        return t

    def is_ret(e):
        return e['b'] and e['b'][0][1] in RETS and plain(e)

    def is_jump(e):
        return e['kind'] in (x86.JMP_NEAR, x86.JMP_SHORT) and \
            e.get('rel') is not None

    # logical tail starting at each unit of a RET exit (for jumps into it)
    suffix = {}
    for n, e in enumerate(units):
        if is_ret(e):
            t = [(i, body(i)) for i in run_before(n) + [n]]
            for j in range(len(t)):
                suffix.setdefault(t[j][0], t[j:])

    tails = []
    for n, e in enumerate(units):
        if is_ret(e):
            new = [(i, body(i)) for i in run_before(n) + [n]]
            current = None
        elif is_jump(e) and index.get(e['rel']) in suffix:
            run = [(i, body(i)) for i in run_before(n)]
            tail = suffix[index[e['rel']]]
            new = run + [(None, b) for i, b in tail]
            current = index[e['rel']]
        else:
            continue
        best = None
        for old in tails:
            k = 0
            while k < len(old) and k < len(new) and \
                    old[-1 - k][1] == new[-1 - k][1]:
                k += 1
            if k == 0 or old[-k][0] is None:
                continue
            size = sum(len(b) for i, b in new[-k:])
            if size >= CJ_MIN and addr[n] - addr[old[-k][0]] <= CJ_MAX and \
                    (best is None or k > best[0] or
                     (k == best[0] and old[-k][0] < best[1][-k][0])):
                best = (k, old)
        if current is not None:
            # an existing jump: keep it unless an earlier exit matches at
            # least as much of it
            keep = len(new) - len(run)
            if best is None or best[0] < keep or \
                    (best[0] == keep and best[1][-keep][0] >= current):
                tails.append(new)
                continue
        if best is None:
            tails.append(new)
            continue
        k, old = best
        if new[-k][0] is None:
            # the match lies within the exit jumped to: retarget the jump
            # (written near, made short again if it fits)
            target = units[old[-k][0]]['start']
            jmp = x86.Insn(e['start'])
            jmp.op, jmp.kind, jmp.len, jmp.relsz = 0xE9, x86.JMP_NEAR, 3, 2
            units[n] = e = {'start': e['start'], 'kind': x86.JMP_NEAR,
                            'rel': target, 'cand': True, 'insn': jmp,
                            'b': [(e['start'], 0xE9), (None, 0), (None, 0)]}
            targets.add(target)
            notes.append('cross-jump@%04X' % e['start'])
            tails.append(new)
            continue
        first = new[-k][0]
        target = units[old[-k][0]]['start']
        jmp = x86.Insn(units[first]['start'])
        jmp.op, jmp.kind, jmp.len, jmp.relsz = 0xE9, x86.JMP_NEAR, 3, 2
        units[first] = {'start': units[first]['start'], 'kind':
                        x86.JMP_NEAR, 'rel': target, 'cand': True,
                        'insn': jmp, 'b': [(units[first]['start'], 0xE9),
                                           (None, 0), (None, 0)]}
        for i, b in new[-k + 1:]:
            if i is not None:
                units[i] = {'start': units[i]['start'], 'b': [],
                            'rel': None, 'kind': 'dropped'}
        if current is not None and first != n:
            units[n] = {'start': units[n]['start'], 'b': [], 'rel': None,
                        'kind': 'dropped'}
        targets.add(target)
        notes.append('cross-jump@%04X' % units[first]['start'])
        merged = new[:-k] + [(None, b) for i, b in old[-k:]]
        if len(merged) > k:
            tails.append(merged)


def convert_code(code, fixups, entries, notes, frames=True,
                 code_target=lambda f: False, ext_name=lambda f: None):
    """Convert the code segment.  fixups: those of the code segment
    (dicts with 'pos').  Returns (new code, new fixups, offset map)."""
    fixat = {f['pos']: f for f in fixups}
    insns = explore_all(code, entries, fixups, fixat, notes, frames)
    order = [insns[k] for k in sorted(insns)]
    starts = set(entries)
    for x in order:
        if x.kind == x86.CALL_NEAR and x.rel not in fixat:
            starts.add(x.target(code))
    stubs = interrupt_stubs(code, order, insns)
    th = frame_thresholds(code, order, starts,
                          None if frames else set(entries), insns, stubs)
    targets = set(entries)
    for x in order:
        if x.rel is not None and x.rel not in fixat and \
                x.kind != x86.CALL_FAR:
            targets.add(x.target(code))

    # pushf; push cs; call near L: an INT emulated in inline assembly; L
    # pushes the vector and jumps to it with RETF, which stays
    bounds = sorted(targets | starts)
    keep_retf = set()
    for call in sorted(stubs):
        keep_retf.add(stubs[call][1])
        notes.append('interrupt-call-kept@%04X' % (call - 1))
    # RETF used as a far jump: the block before it pushed a segment and an
    # offset (or switched stacks) that it consumes; it stays RETF
    for n, x in enumerate(order):
        if x.kind != x86.RETF:
            continue
        depth = 0
        m = n - 1
        while m >= 0 and order[m].off + order[m].len == order[m + 1].off \
                and order[m + 1].off not in targets:
            y = order[m]
            if y.kind in STOPS or y.kind in (x86.JCC, x86.CALL_NEAR,
                                             x86.CALL_FAR, x86.CALL_IND):
                break
            if y.op in PUSHES or (y.op == 0xFF and y.reg == 6) or \
                    y.op in (0x68, 0x6A, 0x9C):
                depth += 1
            elif y.op in range(0x58, 0x60) or y.op in (0x07, 0x17, 0x1F,
                                                      0x9D, 0x8F):
                depth -= 1
            elif code[y.off:y.off + 2] in (b'\x89\xec', b'\x8b\xe5'):
                break           # mov sp,bp: an ordinary epilogue
            elif y.op in (0x81, 0x83) and y.mod == 3 and y.rm == 4 and \
                    y.reg in (0, 5):
                # add/sub sp,n: words released or reserved
                n = code[y.imm] if y.immsz == 1 else \
                    code[y.imm] | code[y.imm + 1] << 8
                if y.immsz == 1 and n > 127:
                    n -= 256
                depth += (-n if y.reg == 0 else n) // 2
            elif (y.op == 0x8B and y.reg == 4) or \
                    (y.op == 0x89 and y.mod == 3 and y.rm == 4) or \
                    (y.op == 0x8E and y.reg == 2):
                depth = 2       # a stack switch: what follows is a jump
                break
            m -= 1
        if depth >= 2 and x.off not in keep_retf:
            keep_retf.add(x.off)
            notes.append('retf-jump-kept@%04X' % x.off)
    units = []
    pos = 0
    while pos < len(code):
        x = insns.get(pos)
        if x is None:
            units.append({'start': pos, 'b': [(pos, code[pos])],
                          'rel': None, 'kind': 'data'})
            pos += 1
            continue
        end = pos + x.len
        inner = [k for k in range(pos + 1, end) if k in insns]
        if inner:
            # overlapping instructions (a jump into the middle of one):
            # kept byte for byte
            for k in [pos] + inner:
                y = insns[k]
                end = max(end, k + y.len)
                if y.rel is not None or y.kind in (x86.CALL_FAR, x86.JMP_FAR,
                                                   x86.RETF, x86.RETFN) or \
                        (y.disp is not None and y.bp_based()):
                    raise Unsupported('overlap-needs-change@%04X' % k)
            notes.append('overlapping-insns@%04X' % pos)
            units.append({'start': pos,
                          'b': [(k, code[k]) for k in range(pos, end)],
                          'rel': None, 'kind': 'data'})
            pos = end
            continue
        nxt = insns.get(end)
        if frames and x.op == 0xE8 and x.rel not in fixat and \
                pos in entries and end < len(code) and code[end] == 0xCB \
                and end not in targets:
            # F: call near body; retf -- the far entry medium gives a
            # function also called near; small code has only the body
            units.append({'start': pos, 'b': [], 'rel': None,
                          'kind': 'dropped', 'alias': x.target(code)})
            notes.append('far-entry-thunk@%04X' % pos)
            pos = end + 1
            continue
        if x.op == 0xC7 and x.imm is not None and \
                fixat.get(x.imm, {}).get('loc') == 2 and \
                code_target(fixat[x.imm]):
            # mov word ptr [p+2], seg F: the segment half of a far code
            # pointer, which small code does not have
            units.append({'start': pos, 'b': [], 'rel': None,
                          'kind': 'dropped'})
            for q in range(pos, end):
                if q in fixat:
                    fixat[q]['_drop'] = True
            notes.append('code-segment-store@%04X' % pos)
            pos = end
            continue
        if x.op == 0x0E and nxt is not None and nxt.op == 0xE8 and \
                end not in targets and code[pos - 1:pos] != b'\x9c':
            # push cs; call near = a far call within the segment: in small
            # code a plain near call
            units.append({'start': pos, 'b': [], 'rel': None,
                          'kind': 'dropped'})
            pos = end
            continue
        if x.kind == x86.JCC and code[x.off + 1] == 3 and nxt is not None \
                and nxt.op == 0xE9 and nxt.rel not in fixat and \
                end not in targets:
            # jcc' +3; jmp near: a conditional jump out of rel8 range
            t = nxt.target(code)
            units.append({'start': pos, 'insn': nxt, 'kind': 'jccpair',
                          'cond': x.op ^ 1, 'rel': t,
                          'cand': not -128 <= t - (pos + 2) <= 127,
                          'b': [(pos + j, code[pos + j]) for j in range(5)]})
            pos = end + nxt.len
            continue
        e = convert_insn(code, x, th, fixat, notes, frames)
        if frames and x.op == 0xB8 and nxt is not None and \
                nxt.kind in (x86.CALL_NEAR, x86.CALL_FAR) and \
                ext_name(fixat.get(nxt.off + 1)) == '__STK':
            # mov ax,N; call __STK: N counts the return address, two
            # bytes less in a far function made near
            entry = max([o for o in starts if o <= pos] or [0])
            if not returns_near(code, entry, insns):
                n = (code[x.off + 1] | code[x.off + 2] << 8) - 2
                e['b'] = [e['b'][0], (x.off + 1, n & 0xFF),
                          (x.off + 2, n >> 8)]
                notes.append('stack-check-size@%04X' % pos)
        if pos in keep_retf:
            e['b'] = [(pos, 0xCB)]
        if e['kind'] == x86.JMP_NEAR:
            # medium kept some near jumps that already fit rel8: those stay
            e['cand'] = not -128 <= e['rel'] - (pos + 2) <= 127
        units.append(e)
        pos = end

    if frames and CROSS_JUMP:
        cross_jump(units, targets, notes)

    # Lay out: jumps that medium made long only for distance are made
    # short where they now fit, in one pass in address order (later jumps
    # still long), as the 6.5 code generator appears to do.
    short = set()

    def layout():
        newoff = []
        o = 0
        for n, e in enumerate(units):
            newoff.append(o)
            o += 2 if n in short else len(e['b'])
        where = {}
        for n, e in enumerate(units):
            if e['kind'] in ('data', 'dropped'):
                if e['kind'] == 'dropped':
                    where[e['start']] = newoff[n]
                for j, (old, v) in enumerate(e['b']):
                    where[old] = newoff[n] + j
            else:
                where[e['start']] = newoff[n]
        where[len(code)] = o
        for n, e in enumerate(units):
            if 'alias' in e:
                where[e['start']] = where[e['alias']]
        return newoff, where, o

    while True:
        changed = False
        for n, e in enumerate(units):
            if e.get('cand') and n not in short:
                newoff, where, total = layout()
                t = where.get(e['rel'])
                if t is None:
                    raise Unsupported('branch-target-lost@%04X'
                                      % e['start'])
                if -128 <= t - (newoff[n] + 2) <= 127:
                    short.add(n)
                    changed = True
        if not changed or not ITERATE_JUMPS:
            break
    newoff, where, total = layout()

    def mapoff(old):
        if old in where:
            return where[old]
        raise Unsupported('offset-not-mapped %04X' % old)

    new = bytearray()
    bytemap = {}
    relfields = []      # (position, size, forward?) of branch fields
    for n, e in enumerate(units):
        base = newoff[n]
        bs = e['b']
        if e['rel'] is not None:
            x = e['insn']
            t = mapoff(e['rel'])
            if n in short:
                op = e['cond'] if e['kind'] == 'jccpair' else 0xEB
                bs = [(e['start'], op), (None, (t - base - 2) & 0xFF)]
            elif e['kind'] == 'jccpair':
                d = t - (base + 5)
                bs = bs[:3] + [(None, d & 0xFF), (None, d >> 8 & 0xFF)]
            elif x.relsz == 1:
                pre = bs[:-1]
                d = t - (base + len(pre) + 1)
                if not -128 <= d <= 127:
                    raise Unsupported('rel8-out-of-range@%04X' % x.off)
                bs = pre + [(None, d & 0xFF)]
            else:
                pre = bs[:-2]
                d = t - (base + len(pre) + 2)
                bs = pre + [(None, d & 0xFF), (None, d >> 8 & 0xFF)]
            size = 1 if n in short or (x.relsz == 1 and
                                       e['kind'] != 'jccpair') else 2
            relfields.append((base + len(bs) - size, size, t > base))
        for j, (o, v) in enumerate(bs):
            if o is not None:
                bytemap[o] = base + j
            new.append(v)
    newfix = []
    for f in fixups:
        if f.get('_drop'):
            continue
        g = dict(f)
        if f['pos'] not in bytemap:
            raise Unsupported('fixup-lost@%04X' % f['pos'])
        g['pos'] = bytemap[f['pos']]
        newfix.append(g)
    return bytes(new), newfix, mapoff, relfields


# ---------------------------------------------------------------- records

def convert(recs, big='CLIBM'):
    notes = []
    names = None
    segs = []
    grps = []
    for r in recs:
        if r['type'] == 0x96:
            if names is not None:
                raise Unsupported('two-lnames')
            names = r['names']
        elif r['type'] == 0x98:
            segs.append(r)
        elif r['type'] == 0x9A:
            grps.append(r)
    names = names or []

    def lname(i):
        return names[i - 1] if i else None

    # code segment: class CODE
    code_seg = None
    for n, s in enumerate(segs, 1):
        if lname(s['cls']) == 'CODE' and code_seg is None:
            code_seg = n
    # code group: a group over the code segment only
    code_grp = None
    for n, g in enumerate(grps, 1):
        if g['segs'] == [code_seg] and lname(g['name']) == big:
            code_grp = n
    # new LNAMES
    drop = set()
    if code_grp:
        drop.add(grps[code_grp - 1]['name'])
    newnames = []
    lmap = {0: 0}
    for i, s in enumerate(names, 1):
        if i in drop:
            continue
        if code_seg and segs[code_seg - 1]['name'] == i and \
                s.endswith('_TEXT'):
            s = '_TEXT'
        newnames.append(s)
        lmap[i] = len(newnames)
    gmap = {0: 0}
    k = 0
    for n, g in enumerate(grps, 1):
        if n == code_grp:
            gmap[n] = None
        else:
            k += 1
            gmap[n] = k

    # compiled C carries a COMENT naming its source; assembler modules not
    is_c = any(r['type'] == 0x88 and r['raw'][:2] == b'\xff\x80'
               for r in recs)
    seglens = {n: s['length'] for n, s in enumerate(segs, 1)}
    img, fix, lidata = segment_images(recs, seglens)
    pubs = []
    for r in recs:
        if r['type'] == 0x90 and r['seg'] == code_seg:
            pubs.extend(o for s, o, t in r['pubs'])
    if code_seg in lidata:
        raise Unsupported('lidata-in-code')
    ext_all = [n for r in recs if r['type'] == 0x8C for n, ti in r['ext']]
    for f in fix:
        if not f['T'] and f['targt'] == 2 and \
                ext_all[f['tdatum'] - 1] in KEEP_FAR:
            f['_keepfar'] = True
        f['seg_is_code'] = f['seg'] == code_seg
        f['_tcode'] = not f['T'] and f['targt'] == 0 and \
            f['tdatum'] == code_seg
    codefix = [f for f in fix if f['seg'] == code_seg]
    start = None
    for r in recs:
        if r['type'] == 0x8A and 'start' in r:
            d = r['start']
            if not d['T'] and d['targt'] == 0 and d['tdatum'] == code_seg:
                start = d.get('disp', 0)
    extnames = [n for r in recs if r['type'] == 0x8C for n, ti in r['ext']]
    if code_seg is None:
        newcode, mapoff, relfields = b'', None, []
    else:
        code = bytes(img[code_seg])
        def code_target(f):
            # Watcom C names functions name_ and variables _name
            if f['T'] or f['targt'] not in (0, 2):
                return False
            if f['targt'] == 0:
                return f['tdatum'] == code_seg
            return extnames[f['tdatum'] - 1].endswith('_')

        def ext_name(f):
            if f is None or f['T'] or f['targt'] != 2:
                return None
            return extnames[f['tdatum'] - 1]

        newcode, codefix, mapoff, relfields = convert_code(
            code, codefix, code_entries(code, fix, pubs, start), notes,
            frames=is_c, code_target=code_target, ext_name=ext_name)

    def conv_fix(f):
        g = dict(f)
        in_code = f['seg'] == code_seg
        if f.get('_conv') == 'near':
            g['M'] = 0
            g['loc'] = 1
        elif f['loc'] == 3 and f['T'] == 0 and \
                (f['targt'] == 0 and f['tdatum'] == code_seg):
            notes.append('far-code-pointer@%d:%04X' % (f['seg'], f['pos']))
        if not f['F'] and f['frame'] == 1:
            ng = gmap[f['fdatum']]
            if ng is None:
                g['frame'] = 5
                del g['fdatum']
                g.pop('fl', None)
            else:
                g['fdatum'] = ng
        if not f['T'] and f['targt'] == 1:
            ng = gmap[f['tdatum']]
            if ng is None:
                raise Unsupported('target-code-group')
            g['tdatum'] = ng
        if not f['T'] and f['targt'] == 0 and f['tdatum'] == code_seg:
            if not f['P']:
                g['disp'] = mapoff(f['disp'])
            elif not in_code:
                notes.append('code-offset-in-field@%d:%04X' % (f['seg'],
                                                               f['pos']))
        for k in ('_conv', '_tcode', 'seg_is_code', '_keepfar'):
            g.pop(k, None)
        if in_code:
            g['pos'] = f['pos']
        return g

    for f in fix:
        if f['loc'] in (2, 3) and not f.get('_drop') and \
                f.get('_conv') != 'near' and code_seg and \
                ((not f['T'] and f['targt'] == 0 and
                  f['tdatum'] == code_seg) or
                 (not f['T'] and f['targt'] == 2 and
                  extnames[f['tdatum'] - 1].endswith('_'))):
            notes.append('code-segment-ref@%d:%04X' % (f['seg'], f['pos']))
    if not is_c:
        notes.append('assembler')
    codefix = [conv_fix(f) for f in codefix]
    otherfix = [conv_fix(f) for f in fix if f['seg'] != code_seg]
    # fields holding code offsets (P=1, target the code segment): remap
    # the stored value
    for f in codefix:
        if f['T'] == 0 and f['targt'] == 0 and f['tdatum'] == code_seg and \
                f['P'] and f['loc'] == 1:
            p = f['pos']
            v = newcode[p] | newcode[p + 1] << 8
            v = mapoff(v)
            newcode = newcode[:p] + bytes((v & 0xFF, v >> 8)) + \
                newcode[p + 2:]

    chunk = CHUNK if is_c else ASM_CHUNK
    coderecs = emit_ledata(code_seg, newcode, codefix, chunk,
                           relfields if is_c else None) \
        if code_seg else []

    def conv_rec(r, prev):
        """The converted form of one record other than code data."""
        t = r['type']
        if t == 0x96:
            return {'type': t, 'names': newnames}
        if t == 0x98:
            x = dict(r)
            x['name'] = lmap[r['name']]
            x['cls'] = lmap[r['cls']]
            x['ovl'] = lmap[r['ovl']]
            if code_seg and r is segs[code_seg - 1]:
                x['length'] = len(newcode)
            return x
        if t == 0x9A:
            if grps.index(r) + 1 == code_grp:
                return None
            return {'type': t, 'name': lmap[r['name']], 'segs': r['segs']}
        if t == 0x8C:
            return {'type': t, 'ext': [
                ('_small_code_' if x == '_big_code_' else x, ti)
                for x, ti in r['ext']]}
        if t == 0x90:
            x = dict(r)
            ng = gmap[r['grp']]
            x['grp'] = 0 if ng is None else ng
            if r['seg'] == code_seg:
                x['pubs'] = [(n, mapoff(o), ti) for n, o, ti in r['pubs']]
            return x
        if t == 0x88 and r['raw'][:2] != b'\xff\x80':
            # a default library request (SCNF asks for the math library):
            # the small-code model's library
            small = {'CLIBM': b'S', 'CLIBL': b'C'}[big]
            raw = r['raw']
            for lib in (b'MATH', b'CLIB'):
                raw = raw.replace(lib + big[-1:].encode(), lib + small)
            return {'type': t, 'raw': raw}
        if t == 0x8A and 'start' in r and start is not None:
            m = dict(r)
            m['start'] = dict(r['start'])
            m['start']['disp'] = mapoff(start)
            return m
        if t == 0x9C and prev is not None and prev['type'] == 0xA2:
            if prev['seg'] == code_seg or any(
                    (not d['F'] and d['frame'] == 1 and
                     gmap[d['fdatum']] is None) for d in r['subs']):
                raise Unsupported('lidata-fixup-on-code')
            subs = []
            for d in r['subs']:
                g = dict(d)
                if not d['F'] and d['frame'] == 1:
                    g['fdatum'] = gmap[d['fdatum']]
                if not d['T'] and d['targt'] == 1:
                    g['tdatum'] = gmap[d['tdatum']]
                subs.append(g)
            return {'type': t, 'subs': subs}
        if t == 0x9C:
            subs = []
            for d in r['subs']:
                f = [g for g in otherfix if g['seg'] == prev['seg'] and
                     g['pos'] == prev['off'] + d['at']][0]
                g = {k: v for k, v in f.items() if k not in ('seg', 'pos')}
                g['at'] = d['at']
                subs.append(g)
            return {'type': t, 'subs': subs}
        return r

    def is_code(r):
        return r['type'] in (0xA0, 0xA2) and r['seg'] == code_seg

    if is_c and code_seg and any(is_code(r) for r in recs):
        return order_c(recs, conv_rec, is_code, coderecs, codefix,
                       code_seg, mapoff), notes

    out = []
    done_code = False
    prev = None
    for r in recs:
        if is_code(r):
            if not done_code:
                out.extend(coderecs)
                done_code = True
        elif r['type'] == 0x9C and prev is not None and \
                prev['seg'] == code_seg:
            pass
        else:
            x = conv_rec(r, prev)
            if x is not None:
                out.append(x)
        if r['type'] in (0xA0, 0xA2):
            prev = r
    return out, notes


def order_c(recs, conv_rec, is_code, coderecs, codefix, code_seg, mapoff):
    """Records of a compiled C module in the order the 6.5 compiler
    writes them: the header; then per code LEDATA chunk the EXTDEF of the
    externals first referenced while the chunk was open,
    the LEDATA, its FIXUPP and the PUBDEF of the publics in the chunk; then
    the rest (data, data publics, the model marker, MODEND) as in the
    source module."""
    n = 0
    while recs[n]['type'] in (0x80, 0x88, 0x96, 0x98, 0x9A):
        n += 1
    last = max(i for i, r in enumerate(recs) if is_code(r))
    if last + 1 < len(recs) and recs[last + 1]['type'] == 0x9C:
        last += 1
    out = [x for x in (conv_rec(r, None) for r in recs[:n]) if x]
    exts = []       # (name, type index) of the externals before the tail
    pubs = []       # (grp, seg, (name, offset, type))
    floats = []     # [anchor code offset, [records]]: data flushed early
    prev = None
    body = recs[n:last + 1]
    for j, r in enumerate(body):
        if r['type'] == 0x8C:
            exts.extend(conv_rec(r, None)['ext'])
        elif r['type'] == 0x90 and r['seg'] == code_seg:
            x = conv_rec(r, None)
            pubs.extend((x['grp'], x['seg'], p) for p in x['pubs'])
        elif is_code(r) or (r['type'] == 0x9C and prev is not None and
                            is_code(prev)):
            pass
        else:
            # data written before the code ended (a full data buffer):
            # anchored to the code offset medium had reached
            nxt = [q for q in body[j:] if is_code(q)]
            at = mapoff(nxt[0]['off']) if nxt else None
            x = conv_rec(r, prev)
            if x is not None:
                if floats and floats[-1][0] == at and floats[-1][2] == j - 1:
                    floats[-1][1].append(x)
                    floats[-1][2] = j
                else:
                    floats.append([at, [x], j])
        if r['type'] in (0xA0, 0xA2):
            prev = r
    first = {}
    for f in codefix:
        if not f['T'] and f['targt'] == 2:
            i = f['tdatum']
            first[i] = min(first.get(i, f['pos']), f['pos'])
    # an EXTDEF is written when the reference is generated, so before the
    # chunk then open: the chunk holding the reference, or the one before
    # when that chunk was cut exactly at the reference
    chunks = [(r['off'], len(r['data'])) for r in coderecs
              if r['type'] == 0xA0]

    def opened(p):
        for j, (o, n) in enumerate(chunks):
            if o <= p < o + n:
                return j - 1 if p == o and j > 0 else j
        return len(chunks) - 1
    anchor = []
    for i in range(1, len(exts) + 1):
        j = opened(first[i]) if i in first else (anchor[-1] if anchor
                                                  else 0)
        anchor.append(max(j, anchor[-1]) if anchor else j)
    k = 0
    ci = -1
    for r in coderecs:
        if r['type'] == 0xA0:
            ci += 1
            b = r['off']
            for fl in [f for f in floats if f[0] is not None and
                       f[0] < b + len(r['data'])]:
                out.extend(fl[1])
                floats.remove(fl)
            group = []
            while k < len(exts) and anchor[k] <= ci:
                group.append(exts[k])
                k += 1
            if group:
                out.append({'type': 0x8C, 'ext': group})
            out.append(r)
            end = b + len(r['data'])
            pend = [p for p in pubs if b <= p[2][1] < end or
                    (p[2][1] == end and r is coderecs[-1] or
                     coderecs[-1]['type'] == 0x9C and r is coderecs[-2])]
        else:
            out.append(r)
        nxt = coderecs.index(r) + 1
        if nxt == len(coderecs) or coderecs[nxt]['type'] == 0xA0:
            if pend:
                g, sg = pend[0][0], pend[0][1]
                out.append({'type': 0x90, 'grp': g, 'seg': sg,
                            'pubs': [p[2] for p in pend]})
                for p in pend:
                    pubs.remove(p)
    for fl in floats:
        out.extend(fl[1])
    if k < len(exts):
        out.append({'type': 0x8C, 'ext': exts[k:]})
    if pubs:
        raise Unsupported('public-outside-code')
    prev = None
    for r in recs[last + 1:]:
        x = conv_rec(r, prev)
        if x is not None:
            out.append(x)
        if r['type'] in (0xA0, 0xA2):
            prev = r
    return out


def emit_ledata(seg, code, fixups, chunk, relfields=None):
    """LEDATA (+ FIXUPP) records for a segment image.

    With relfields (compiled C), the 6.5 compiler's rule: a chunk holds up
    to 189 bytes, but before a fixup field at p the chunk ends if p + 4 >
    189 (a fixup reserves 4 bytes whatever its size), and before the field
    of a forward branch (a label not yet placed) or of a backward rel16
    branch if p + 2 > 189; and before a fixup that would make the chunk's
    FIXUPP body longer than 195 bytes.  Without (assembler), a fixup is just never
    split."""
    out = []
    if relfields is not None:
        items = sorted([(f['pos'], 4) for f in fixups] +
                       [(p, 2) for p, n, fwd in relfields if fwd or n == 2])
    spans = sorted((f['pos'], f['pos'] + fixup_size(f)) for f in fixups)
    o = 0
    while o < len(code):
        end = min(o + chunk, len(code))
        if relfields is not None:
            for p, r in items:
                if o <= p < end and p + r > o + chunk:
                    end = p
                    break
            # and the chunk's FIXUPP body stays within FIXBODY bytes
            used = 0
            for f in sorted(fixups, key=lambda f: f['pos']):
                if o <= f['pos'] < end:
                    used += fixup_bytes(f)
                    if used > FIXBODY:
                        end = f['pos']
                        break
        else:
            for a, b in spans:
                if a < end < b:
                    end = a
        out.append({'type': 0xA0, 'seg': seg, 'off': o,
                    'data': code[o:end]})
        subs = []
        for f in fixups:
            if o <= f['pos'] < end:
                g = {k: v for k, v in f.items() if k not in ('seg', 'pos')}
                g['at'] = f['pos'] - o
                g['kind'] = 'fixup'
                subs.append(g)
        if subs:
            out.append({'type': 0x9C, 'subs': subs})
        if end == o:
            break
        o = end
    return out
