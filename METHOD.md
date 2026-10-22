# How CLIBS.LIB and CLIBC.LIB were reconstructed: full method

This document records, in detail, everything that was done to rebuild the
damaged small-model (CLIBS.LIB) and compact-model (CLIBC.LIB) run-time
libraries of Watcom C 6.5 (1988): what was examined, every rule used, how
each rule was found and checked, what was tried and failed, every decision
taken, and how to repeat or check the work.  `README.md` is the overview;
`PROVENANCE.csv` gives the result module by module; the tools in `tools/`
and the sources in `recompile/` are the executable form of this document.

The result is a **reconstruction**.  Without an undamaged copy of the
files, or a checksum of them, no rebuilt module can be proven identical to
Watcom's.
Where this document says "exact", it means byte-identical to bytes that
actually survived.

Contents

1. Principles
2. Materials and environment
3. The library file format as 6.5 writes it
4. Finding the damage
5. Which modules survive
6. How the libraries were compiled (probe compiles)
7. The converter: rules and how each was found
8. Scoring the converter on the surviving modules
9. The recompile route
10. Assembling the rebuilt libraries
11. Decisions, with the evidence for each
12. Testing in real use
13. Hypotheses that failed, and dead ends
14. Confidence
15. Reproducing and checking the work
16. Open questions


## 1. Principles

- Bytes that survived are never changed, except three that are provably
  corrupted (section 11, decision 1).
- Every rebuilt module must fill exactly the space the original module
  occupied, and must contain exactly the public names the intact library
  dictionary lists for it.
- Every rule applied to a lost module is first tested on modules that did
  survive.  A rule that makes any surviving module come out wrong is not
  kept.
- Nothing is "fixed" to make a check pass.  Where the evidence ran out, the
  choice made is written down as a decision, with the alternative.
- Inferred bytes are never presented as original: every module carries its
  status, route and confidence in `PROVENANCE.csv`.


## 2. Materials and environment

### The source archive

`Watcom C.ver.6.5.English.zip`, SHA-256
`76b2ebc8ec730ee1151b1c1f9193460b8cfc03dacec5d567573296f3a537eca6`, holding
directories DISK1-DISK8 of plain files dated 1988-05-31.  It is the only
copy of Watcom C 6.5 I could find (README.md says where to get it, and
what else was looked at).  Every tool
reads it directly; nothing is unpacked by hand.

The five C run-time libraries:

| file | model | code / data pointers | state |
|---|---|---|---|
| CLIBS.LIB | small | near / near | damaged |
| CLIBC.LIB | compact | near / far | damaged |
| CLIBM.LIB | medium | far / near | intact, 250 modules |
| CLIBL.LIB | large | far / far | intact, 250 modules |
| CLIBH.LIB | huge | far / far (huge arrays) | intact, 250 modules |

The four-model matrix is the basis of the whole method: small differs from
medium only in code pointers (so medium is the template for small), compact
differs from large only in code pointers (so large is the template for
compact), and small differs from compact only in data pointers.

### Programs used

- Python 3.13.5 (all tools; any Python 3.8 or later should do).
- DOSBox-X 2025.02.01, headless (`SDL_VIDEODRIVER=dummy`, `-nogui -nomenu
  -exit`), configured as MS-DOS 3.10, 16 MB, `cycles=max`
  (`tools/dosrun.py` writes the configuration).  It runs Watcom C 6.5's
  own `WCC.EXE` (compiler), `WCG.EXE` (code generator) and `WLINK.EXE`
  (WLINK 4.1), installed from the zip into `build/watcom` by
  `tools/install.py`, which follows the distribution's own `INSTALL.SCR`.
- Open Watcom v2 `wdis` (beta, 2026) only to display disassembly while
  investigating; no reconstructed byte depends on it.
- `tools/checklib.py`, a strict library checker that walks every module
  and record sequentially instead of trusting the dictionary.

No assembler was used to produce any byte.  Watcom C 6.5 ships no
assembler; every rebuilt byte comes from the converter, from Watcom C 6.5
itself compiling reconstructed C, or from the intact libraries.


## 3. The library file format as 6.5 writes it

Learned from the five libraries (`tools/omf.py`, `tools/omfrec.py`):

- A header record (type F0h) of 16 bytes: page size 16 (stored as 13 =
  16 - 3), the dictionary's file offset, and its size in 512-byte blocks
  (19 in all five libraries).
- Modules start on 16-byte page boundaries, in the same order in all five
  libraries.  After each module's MODEND record, zero bytes pad to the next
  page.
- After the last module, an end record (F1h) on a page boundary, padded
  with zeros up to the dictionary, which starts on a 512-byte boundary.
- The dictionary is the standard hashed OMF library dictionary: 37 buckets
  per block; each entry is a name and the page number of its module.  It
  lists every public symbol and, for every module, the module name followed
  by `!` (from the module's THEADR record).
- Records used in modules: THEADR 80h, COMENT 88h, MODEND 8Ah, EXTDEF 8Ch,
  PUBDEF 90h, LNAMES 96h, SEGDEF 98h, GRPDEF 9Ah, FIXUPP 9Ch, LEDATA A0h,
  LIDATA A2h.  No LINNUM, no FIXUPP threads (every fixup is explicit).  Every
  record carries a valid checksum (a checksum byte of 0 occurs only where
  the true checksum is 0).
- COMENT records: class `FF 80` + the source file name as the compiler was
  given it (e.g. `..\c\UNLINK.c`) in every compiled-C module; class `FE 80`
  + `L5MATHM` (a default-library request) only in SCNF.  Assembler modules
  have no source-name COMENT, which is how the tools tell compiled C from
  assembler.

`tools/omfrec.py` decodes every record into fields and re-encodes it.  It
was checked to reproduce every record of all five libraries (and of the
MATH and GRAPH libraries) byte for byte before anything was built on it.


## 4. Finding the damage

Tool: `tools/damage.py`.

**Method.**  Every 512-byte sector of each damaged library was looked up in
every other file of the distribution: first at the same file offset, then
at any offset (a hash of every 512-byte window of every file, confirmed by
direct comparison).  Sectors of one repeated byte were set aside as
uninformative.

**Classification.**
- A sector equal to another file's bytes at the same offset is foreign.
- A sector equal to another file's bytes at a 512-aligned offset is
  foreign (a whole sector of another file).
- A sector equal to the other damaged library at an *unaligned* offset is
  genuine: CLIBS and CLIBC share many identical near-code modules, shifted
  by earlier size differences.  These modules parse and checksum.
- A lone unmatched sector between two foreign runs is foreign too.  The
  three such sectors in CLIBS were inspected: one holds 8086 code, one a
  ctype table followed by "Unable to open '%s'", one README-style text
  about a mouse driver.  None is library content.

**Result.**

| | CLIBS.LIB | CLIBC.LIB |
|---|---|---|
| size | 96256 | 101376 |
| foreign | 96 sectors, 49152 bytes | 101 sectors, 51712 bytes |
| dictionary | at 86528, 19 blocks, genuine | at 91648, 19 blocks, genuine |

CLIBS foreign runs (all at the same offsets in the named files):
14336-19968 DISK3/WDISASM.EXE; 19968-20480 unknown; 20480-28672
DISK3/WMAKE.EXE; 28672-29184 unknown; 29184-38400 DISK3/WLINK.EXE;
38400-38912 unknown; 38912-63488 DISK3/WVIDEO.HLP.

CLIBC foreign runs: 11776-22016 DISK4/MATHM.LIB (same offset); 22016-37376
the last 15360 bytes of DISK4/CLIBM.LIB (its last modules and its
dictionary, sector-aligned there); 37376-63488 DISK4/CLIBM.LIB (same
offset).

**Bit errors inside genuine sectors.**  Two places were found where bytes
in a sector that is otherwise genuine are wrong:

1. CLIBS offset 14012 (module TELL, a PUBDEF record): the record's checksum
   fails.  The byte is `4C` ('L'), making the public name `telL_`; the
   dictionary lists `tell_`.  With `6C` the checksum is right and the name
   matches.  A one-bit error (bit 5).
2. CLIBC offsets 11580-11581 (module AMODF): the bytes `D0 81` sit in a
   repeated instruction pattern (`shl di,1; rcl cx,1; rcl bx,1; ...`) where
   they make no sense as code; CLIBS, CLIBM, CLIBL and CLIBH all have
   `D1 D1` there.  The record cannot be checksummed (it runs into a foreign
   sector).

So "genuine" sectors are not perfect.  In whole modules every record
checksum is valid, so no other single-byte error can hide there; in the
surviving parts of partly damaged modules one cannot rule it out.


## 5. Which modules survive

Tool: `tools/survey.py`.  The intact dictionary gives every module's page,
and so its exact position and its size to within 16 bytes (the distance to
the next module).  A module is **whole** when no byte of its page span is
foreign and its records parse with valid checksums, **partial** when some
bytes are genuine, **lost** when none are.

| | CLIBS | CLIBC |
|---|---|---|
| whole | 106 (107 with the TELL repair) | 102 |
| partial | 2: SYSTEM, REMOVE | 2: AMODF, SCNF |
| lost | 141 | 146 |

141 module positions are not whole in either library.

Six modules of CLIBC parse cleanly but lie entirely in foreign sectors:
they are CLIBM's (and one MATHM-area) modules sitting at the same offsets
(SEGREAD, MAX, MALLOC, D_SETVECT, BDOS, STRLEN), recognisable by their
medium-model segment names.  They are not counted as surviving.

Six CLIBS modules have lower-case names in the original dictionary
(`d_setvect!`, `d_keep!`, `d_getvect!`, `strspn!`, `strpbrk!`, `strcspn!`),
where the other four libraries have upper case.  The module name comes from
the source file name given to the compiler, so these six were compiled
separately from the rest of CLIBS.  All six are lost.


## 6. How the libraries were compiled (probe compiles)

Watcom C 6.5's compiler is intact, so small C files were compiled with it
in every model to learn exactly what it produces (`tools/dosrun.py`,
`tools/recompile.py`).

- **Segment and group names** match the libraries only with: small
  `wcc /ms`; medium `wcc /mm /g=CLIBM` (the `/g` switch gives the group
  `CLIBM` and segment `CLIBM_TEXT`); compact `/mc`, large `/ml`, huge `/mh`
  (segment `<MODULE>_TEXT`).
- **The source name.**  The modules name their source `..\c\NAME.c`, so
  each was compiled from a directory beside a `c` directory; the recompile
  tool does the same so that those records match.
- **Optimisation switches** were found by recompiling reconstructed modules
  with each combination (section 9).  SPRINTF reproduces only with `/os`;
  PRINTF and SETJMP with `/os` or `/ox`; SPAWNVE comes closest with `/oilt`
  (it has a stack check, so it was not built with `/s`).  The library was
  evidently not built with one switch set for all modules.
- **Stack checks.**  6.5 emits `mov ax,N; call __STK` only for functions
  with large frames, so most modules show no stack check whatever switch
  was used.  N is the stack the function needs, including its return
  address and stack arguments (section 7.3).
- **Inline functions.**  Many modules contain inlined `strlen`, `strcpy`,
  `strchr` loops (`repne scasb`, `lodsw/stosw` loops): built with `/oi`.
  DOS.H confirms `/oi` turns `_enable()` into inline code.
- **String literals** are emitted in reverse order of first use; with `/ot`
  or `/ox` they are word-aligned, and the alignment byte is whatever the
  compiler's buffer held (this is the source of the unpredictable padding
  bytes, section 8).
- **The preprocessor has no `#elif`**: a `#elif` branch was silently taken
  as the `#else`, which was found when SETJMP's medium build came out as the
  large one.  Sources must nest `#if`/`#else`.
- **Two code generators** ship, `WCG.EXE` and `WCGL.EXE`.  With WCGL put in
  place of WCG the output changes but matches the libraries no better.


## 7. The converter: rules and how each was found

Tool: `tools/convert.py` (with `tools/x86.py`, an 8086/80186 instruction
decoder).  It turns a medium (large) module into its small (compact) twin.
Each rule below was found by comparing surviving small/medium (and
compact/large) pairs and probe compiles, and was kept only if it made no
surviving module come out wrong.  The scores in section 8 are after all of
them.

### 7.1 Records

- **LNAMES**: the code group name `CLIBM` is removed and the code segment
  (`CLIBM_TEXT`, or `<MODULE>_TEXT` in large) becomes `_TEXT`; every name
  index is renumbered.
- **SEGDEF**: name, class and overlay indexes renumbered; the code
  segment's length is the new code length.
- **GRPDEF**: the `CLIBM` group (over the code segment) is dropped; the
  remaining groups (DGROUP) are renumbered.
- **EXTDEF**: the model marker `_big_code_` becomes `_small_code_`.
- **PUBDEF**: publics in the code segment get base group 0 (no code group);
  others keep their renumbered group.
- **FIXUPP**: a far-pointer fixup (location type 3) on a call or jump
  instruction becomes a self-relative 16-bit fixup (M=0, location 1); a
  frame given by the code group becomes "frame of the target" (F5); group
  indexes are renumbered; fixup positions and code displacements in fixups
  are relocated to the new code.  Found from a count of every fixup kind in
  the surviving pairs, which showed one consistent mapping.
- **COMENT default-library request**: `L5MATHM` becomes `L5MATHS`,
  `L5MATHL` becomes `L5MATHC`.  Found by testing: small programs using
  `scanf` pulled in MATHM.LIB.
- **Module name**: THEADR (and the source name in the COMENT) take the
  dictionary's spelling, for the six lower-case CLIBS modules.

### 7.2 Finding the code

The code segment is disassembled by recursive descent, not a linear sweep,
because 6.5's code contains data (switch jump tables, strings in assembler
modules) and overlapping instructions (the compiler's `jne +2; dec di; db
0A9h` trick, where the `A9` (`test ax,imm16`) swallows the next two bytes
so a jump can land in the middle).  Entry points, in order:

1. publics, the module start address, targets of self-relative fixups;
2. targets of offset fixups lying in data (jump-table entries);
3. in compiled C only, code offsets taken by instructions (function
   pointers) where they follow an unconditional transfer;
4. gaps that directly follow an unconditional transfer and decode cleanly
   (dead code), rejected in assembler modules if they contain text.

Anything never reached is copied byte for byte.  Overlapping instructions
are copied byte for byte (and refused if they would need changing).

### 7.3 Code transformations

Each with the evidence that established it:

- **Far call / far jump to near**: `9A off seg` (5 bytes) becomes
  `E8 rel16` (3 bytes); `EA` becomes `E9`.  The basic difference in 45 of
  46 equal-length surviving pairs.
- **RETF to RET, RETF n to RET n** (`CB` to `C3`, `CA` to `C2`, same n).
  Except a RETF used as a far jump: when the instructions before it in the
  same block push a segment and offset (net two or more words, counting
  `add/sub sp` and stopping at `mov sp,bp`) or switch stacks, it stays
  RETF.  DOEXEC's stubs that start a loaded program, and the INT emulation
  below, are the cases.
- **`push cs; call near` to `call near`**: medium calls a far function in
  the same segment this way (LTOA, ITOA).  Except `pushf; push cs; call`:
  inline code in INT86/INT86X that emulates an `INT`, whose callee ends
  with a RETF that jumps to the interrupt vector; both stay.
- **Far entry thunks**: medium sometimes gives a function `F: call near
  body; retf` and a separate near body (FTOSX, PRINTF).  Small has only the
  body, with F on it.  The thunk is removed and F's address mapped to the
  body.
- **Segment half of a far code pointer**: `mov word ptr [p+2], seg F`
  (IOALLOC) is removed; small keeps code pointers in one word.
- **Calls through a global code pointer** in compiled C: `call dword ptr
  [var]` (FF /3) becomes `call word ptr [var]` (FF /2), same length.  Found
  by testing: EXECVE's call through `_int23_exit` crashed exec, because the
  surviving small EXIT module defines that pointer as one word.  Indexed or
  stack-based far calls (code pointers in tables or locals) are not
  converted; they are flagged.
- **Stack frame offsets**: in a far function, `[bp+d]` at or above the
  return address becomes `[bp+d-2]` (the near return address is 2 bytes
  shorter).  The return address position is found by counting the pushes
  between the function entry and `push bp; mov bp,sp`.  Not applied when
  every return reachable from the frame is a near RET: such a function is a
  near static function in medium too, and its frame does not change (found
  on CLIBC SCNF, section 10).  In assembler modules, BP is often a plain
  register, so only a frame opened at a public entry counts
  (`push bp; mov bp,sp`, return at bp+2; or `mov bp,sp`, return at bp+0).
  A 16-bit displacement that now fits in 8 bits is shortened.
- **Stack check size**: `mov ax,N; call __STK` at the start of a far
  function: N-2.  From PRTF (small 72 vs medium 76: -4, because `_prtf` also
  takes a code pointer argument) and the surviving part of CLIBC SCNF
  (0x6E vs 0x70: -2).  Unchanged in near static functions (all PRTF's
  helpers).
- **Jump sizes**: the compiler's choice was studied by re-deriving the
  short/long form of every jump in all libraries.  Backward jumps are always
  the shortest form.  Some forward jumps stay long although they would fit
  (e.g. three `jmp L$57` in PRTF at distances 44-102, long in medium too).
  Rule: a jump that medium kept long although it fitted stays long; a jump
  (or an inverted `jcc`+`jmp near` pair) that medium needed long for
  distance is made short where it now fits, in one pass in address order.
  An iterated version scores the same on the survivors; the one-pass form
  was kept because it fitted the jump study better.
- **Cross-jumping**: 6.5 replaces a function's exit sequence by a jump to an
  identical exit emitted earlier.  In medium a far function's exit ends in
  RETF and a near static function's in RET, so they cannot be shared; in
  small both end in RET and the compiler shares them.  Found on CLIBC FOPEN
  and SCNF.  Rule: exits are taken in address order (a run of plain
  instructions ending in RET, or ending in a jump to an exit); each is
  matched against the earlier ones; the longest common tail of at least 5
  bytes wins, the earliest of equals; existing merges are re-aimed at an
  earlier identical exit when one now exists; chains (an exit ending in a
  jump to another exit) count as the instructions they jump to.  The
  5-byte threshold was measured: 3 breaks two surviving modules, 4 and 5
  are equal, 6 loses one.
- **Relocation**: every branch displacement, fixup position, public offset,
  jump-table entry and the module start address is moved to the new code.

### 7.4 Splitting code into LEDATA records, and record order

The order and size of records affect the module's bytes, so the compiler's
rules were recovered exactly.  Measured on every code chunk boundary of
every compiled-C module in all five libraries (small 81, compact 78, medium
220, large 220, huge 220 modules), all predicted correctly:

- A code chunk (one LEDATA) holds up to 189 bytes.
- Before a fixup field at position p, the chunk ends if p + 4 > start + 189
  (a fixup reserves 4 bytes whatever its size).
- Before the field of a forward branch (a label not yet placed) or of a
  backward 16-bit branch, the chunk ends if p + 2 > start + 189.  Backward
  8-bit branches and the fixed `+3` of an inverted jcc pair are plain bytes.
- Before a fixup that would make the chunk's FIXUPP record body longer than
  195 bytes, the chunk ends (this explains STRFTIME's 78-byte jump-table
  chunks).

Record order:

- An EXTDEF is written before the code chunk that was open when the first
  reference to the symbol was generated: the chunk holding the reference,
  or the previous chunk when that chunk was cut exactly at the reference.
  Checked on every external of every compiled-C module: 149/149 small,
  137/137 compact, 369/369 medium, 371/371 large, 473/473 huge.  (A simpler
  "first reference within the chunk's 189-byte window" rule missed 5.)
- After each chunk's FIXUPP comes a PUBDEF of the publics the chunk holds.
- Data written before the code ended (a full 189-byte data buffer, e.g.
  STRFTIME's strings) is placed where medium flushed it, relative to the
  code.
- Then the data segments, data publics, the model marker EXTDEF and MODEND,
  as in the source module.

Assembler modules (no source-name COMENT) keep the source module's record
order, with LEDATA up to 1020 bytes.

### 7.5 Notes

The converter records every non-trivial thing it did or could not do as a
note in the provenance (e.g. `call-far-indirect`, `cross-jump`,
`stack-check-size`, `overlapping-insns`, `guessed-code`,
`code-segment-ref`).  Section 8 measures how often modules with each note
were exact; section 10 turns that into confidence levels.


## 8. Scoring the converter on the surviving modules

Tool: `tools/score.py`.  For every module that survives whole in CLIBS
(CLIBC), its CLIBM (CLIBL) twin is converted and compared byte for byte
over the whole module, every record from THEADR to MODEND.

| route | targets | exact |
|---|---|---|
| medium to small | 106 | 97 (91.5%) |
| large to compact | 102 | 93 (91.2%) |
| compact to small, unchanged, where medium = large | 30 | 30 |
| small to compact, likewise | 30 | 30 |

The cross route: when the medium and large modules are byte-identical in
code and data (the module does not depend on the data model), the small
and compact modules were identical in all 30 surviving cases.

The modules that differ, and why:

| module | M>S | L>C | cause |
|---|---|---|---|
| exit, atexit | x | x | code-pointer tables shrink from 4-byte to 2-byte entries, with different register allocation |
| QSORT, BSEARCH, PRTF, PRINTF | x | x | code pointers called through tables or passed as arguments; generated differently |
| OVLLDR | x | x | assembler with different code and public names per model (`_SOVLLDR`/`_LOVLLDR`) |
| TZSET, ASCTIME | x | | one string-alignment byte each holds leftover compiler memory (small `54`/`02`, medium `CE`/`4A`) |
| IOALLOC | | x | far-data code differs around the code-pointer store |
| FWRITE | | x | one jump shortened by the compiler that the rules keep long |

Success by note, on survivors: no note 137 of 142 exact; assembler 47/49;
overlapping instructions 2/2; guessed code 8/10; far entry thunk 2/3; code
pointer constructs (indirect far calls through tables, far code pointers in
data, code offsets in data) 0/12.

These numbers are measured on the same modules the rules were developed
on, so they are optimistic for the lost modules.  The one independent check
is CLIBC SCNF (section 10).


## 9. The recompile route

Tool: `tools/recompile.py`; sources in `recompile/`.

For modules the converter cannot do (code pointers), C source was written
by reading the CLIBM and CLIBL machine code, and compiled by Watcom C 6.5
itself in all five models (with the source placed so it is named
`..\c\NAME.c`).  A source counts as reproducing a module when the medium
and large objects are byte-identical to CLIBM's and CLIBL's modules: medium
pins down everything that depends on the code model, large everything that
depends on the data model, so small and compact compiled from the same
source are very likely right.  The sources are reconstructions written for
this project, not Watcom's.

Findings that came out of this work:

- **PRINTF** (the validation case).  The converter cannot do it (it passes
  a function pointer).  The reconstructed source reproduces CLIBM, CLIBL
  and CLIBH, *and* the surviving CLIBS and CLIBC modules, byte for byte.
  Getting there showed that the original source is model-conditional:
  in every model except small, `vfprintf` is a far wrapper around a static
  near helper (`#if !defined(M_I86SM)`).  This proves model-conditional
  sources exist; for a lost module nothing could reveal one.
- **SPRINTF**: medium and large exact with `/os` only (not `/ox`).  Huge
  differs in one register choice after the huge-pointer helper `__PIA`; no
  source variant changed it.
- **SETJMP**: written as two C functions whose bodies are `#pragma aux`
  inline code, one variant per model (nested `#if`, since 6.5 has no
  `#elif`).  Medium, large and huge exact.  So that this repository holds
  none of Watcom's code, the source is generated at build time by
  `recompile/SETJMP.py` from the user's own CLIBM and CLIBL modules.  The small-code variants keep
  one return-address word (offset 14h of the jmp_buf) instead of the two of
  the far models; this part is inferred and cannot be checked.
- **SIGNAL**: an INT 23h handler (`interrupt` function), `signal`, `raise`
  with a switch on the signal number.  The library has two public names at
  one address, `raise_` and `__raise`: reproduced by a function `__raise`
  whose body is `return raise(sig);` placed just before `raise`, which
  6.5 compiles to a jump to the next instruction and then removes.  Medium
  and large differ from the library in one register choice in `signal`
  (the table index in BX instead of SI); dozens of source variants and the
  other code generator did not change it.  Accepted, see decision 2.
- **FMALLOC, SPAWNVE**: attempted; close (FMALLOC about 75% of the disassembly
  equal, SPAWNVE a few register choices off) but not reproduced; not used.  SPAWNVE's attempt showed `__dospawn`
  takes near pointers in every model and `_execaddr` returns a far
  pointer.
- Declaration order of local variables does not affect 6.5's register
  allocation (all 120 orders of one function's locals, and 53 of 720 of another's,
  gave the same code);
  it does decide the stack layout of locals.


## 10. Assembling the rebuilt libraries

Tool: `tools/rebuild.py`.

For each of the 250 modules of each library:

1. A whole module is kept as it is (`original`); TELL gets its one-byte
   repair (`original-repaired`).
2. Otherwise candidates are built, in this order of preference:
   **recompile** (objects written by `recompile.py` for reproduced or
   accepted sources), **cross** (the other damaged library's surviving
   module, when CLIBM and CLIBL are identical), **convert**, **unchanged**
   (CLIBM's module as it is, for the one model-independent routine).
3. A candidate is accepted only if, placed at the dictionary's page and
   padded with zeros, it (a) fills the page span exactly (fewer than 16
   bytes of padding), (b) equals every surviving genuine byte in the span,
   (c) has exactly the public names the dictionary lists for that page.
4. The chosen module is written; the others are recorded as agreeing or
   disagreeing.

Then the library is checked as a whole: every genuine byte of the damaged
file is unchanged (apart from the repairs), and the original header, end
record and dictionary are kept.  Both libraries pass `tools/checklib.py`,
which walks the modules sequentially (a stricter check than the
dictionary, see section 13).

Results: CLIBS 106 original + TELL repaired, 2 anchored, 141 inferred
(convert 138, recompile 3, cross 1, unchanged 1).  CLIBC 102 original, 2
anchored, 146 inferred (convert 142, recompile 3, cross 2, unchanged 1).

**The independent check: CLIBC SCNF.**  SCNF is CLIBC's largest partly
surviving module: 3088 of its 3424 bytes are genuine (only the header and
the first code bytes are lost).  It was the test that found three rules
(cross-jumping between far and near exits, near static functions keeping
their frames, the stack-check size), none of which changes any surviving
module's result; with them, the converted module matches all 3088 surviving bytes.

**Confidence levels** in the provenance: `high` = recompiled with CLIBM and
CLIBL exact, or the cross route; `medium` = converted with no risky note,
or a near-exact recompile; `low` = converted through code-pointer
constructs, or depending on a decision.  Low in both libraries: SPAWNVE,
EXECADDR, DOINTR, DOEXEC, INTDOSX, INT86, INT86X, SETVBUF.


## 11. Decisions, with the evidence for each

1. **Three genuine bytes repaired** (section 4): CLIBS 14012 `4C`→`6C`;
   CLIBC 11580-11581 `D0 81`→`D1 D1`.  Evidence: a failing checksum and
   the dictionary (TELL); the other four libraries and the instruction
   stream (AMODF).
2. **SIGNAL accepted near-exact** (section 9).  The single register
   difference in medium and large, together with SPRINTF's in huge,
   suggests the libraries were built by a slightly different compiler
   revision than the one on the disks; it cannot be reproduced.
3. **EXECADDR kept as a far routine in small and compact** (taken unchanged
   from CLIBM; SPAWNVE keeps its call to `_execaddr_` far).  Evidence: the
   converted compact SPAWNVE is 944 bytes, one byte short of the smallest
   size its page span allows (945-960).  The cause cannot be seen; one
   far call (+2 bytes) is the smallest change that fits, and among
   SPAWNVE's callees it is the only one that stays internally consistent:
   EXECADDR calls nothing and returns the 4-byte exec hook in DX:AX in
   every model.  The first choice, DOSPAWN, was refuted (section 13).
   Small SPAWNVE fits either way.
4. **SETJMP's small-code bytes** (section 9) are inferred.
5. **The six lower-case CLIBS modules** are rebuilt from CLIBM with the
   dictionary's names; a separate compile may have used other sources,
   which nothing can show.


## 12. Testing in real use

### Programs in every model

Tool: `tools/difftest.py`; programs in `tests/`.  Each program is compiled
by 6.5 in the small, compact, medium and large models and linked by
WLINK 4.1: small and compact against the rebuilt libraries, medium and
large against the intact originals.  Each runs in its own DOSBox-X
instance; the four outputs must be identical.  All five agree:

- T_STR: string and memory functions, ctype, atoi/atol/strtol/strtoul,
  itoa/ltoa/ultoa, div/ldiv, rand, qsort, bsearch, many printf/sprintf/
  sscanf formats.
- T_FLT: printf `%f %e %g`, sscanf of floats, atof, strtod, sqrt, sin,
  log, floor (with the intact MATH libraries).
- T_IO: fopen/fgets/fprintf/fputs/fputc/fseek/ftell/rewind/ungetc/feof/
  ferror/fread/fwrite, open/read/lseek/tell/eof/dup/close/creat/write,
  filelength, stat, access, rename, remove, mkdir/chdir/getcwd/rmdir,
  isatty, tmpnam.
- T_MISC: gmtime, asctime, strftime, difftime, setjmp/longjmp, signal/
  raise, malloc/free/realloc/calloc, _fmalloc/_ffree, halloc/hfree,
  putenv/getenv, intdos, stackavail, atexit order.
- T_SPAWN: spawnl and spawnlp (P_WAIT), a missing program, execl.

Faults these tests found in earlier versions of the rebuild, all fixed:
SCNF's default-library request (small programs linked MATHM.LIB);
EXECVE's far call through the near `_int23_exit` (exec crashed); the
DOSPAWN hypothesis (spawn crashed, section 13).

## 13. Hypotheses that failed, and dead ends

- **DOSPAWN as a far, model-independent routine** (the first answer to the
  SPAWNVE size problem): refuted when DOSPAWN, taken unchanged from CLIBM,
  crashed spawn in small and compact.  DOSPAWN itself calls `_dosretax_`
  far, and that C routine is near in small code.  Replaced by decision 3.
- **An undersize module** (SPAWNVE one byte short, leaving an extra page of
  zeros): WLINK would accept it (it finds modules through the dictionary),
  but a strict checker walks modules sequentially and stops at the zero
  page.  Rejected: every module must fill its span.
- **A "RETF used as a jump" rule that counted `mov sp,bp` as a stack
  switch**: it turned normal epilogues into jumps and broke 17 surviving small modules;
  corrected (section 7.3).
- **An asm frame rule for `mov bp,sp`** broke FSMATH until stack releases
  (`add sp,n`) were counted.
- **Watcom C 386 7.0** (the only 7.0 available) is the 32-bit edition with
  32-bit libraries only; no bytes to take.  8.5 and 9.01 likewise; 9.5 and
  later are a different code generator.  7.0 ships a few run-time sources
  (IOB.C, NFILES.C, WILDARGV.C, CMAIN386.C), useful only as reference.
- **WCGL.EXE** in place of WCG.EXE: different output, no closer.
- **Local declaration order** for register allocation: no effect.
- **Iterated jump sizing**: no better than one pass.
- **WCEXPL.LIB** (WATCOM Express): the medium library plus Express's own
  modules; no small-code modules.


## 14. Confidence

An estimate, not a measurement (for lost modules nothing survives to check
against):

| | CLIBS | CLIBC |
|---|---|---|
| modules expected byte-identical | about 92-94% (230-235 of 250) | about 90-93% (225-232 of 250) |
| bytes expected identical | about 98% | about 97-98% |
| whole library byte-identical | close to 0% | close to 0% |

Basis: the original modules (107/102) are certain; the medium-confidence
rebuilt modules (132/136) were put at 88-93% each, from 96.5% on survivors
discounted for having been tuned on them, for hidden small-model source
conditionals like PRINTF's, and for padding bytes; high-confidence modules
at about 80%; low-confidence ones at about 30%.  A wrong module usually
differs in a few bytes, hence the higher byte figure.  Behaviour is better
than byte identity: every test agrees with the original medium and large
libraries.


## 15. Reproducing and checking the work

`README.md` gives the full instructions for Linux and Windows.  In short,
with the zip in the repository folder, Python and DOSBox-X:

```
python3 restore.py             # everything, ending with the hash check
python3 restore.py --test      # and the test programs in all four models
```

The individual steps, each a tool that can be run alone:

```
python3 -I tools/install.py                 # Watcom C 6.5 into build/watcom
python3 -I tools/damage.py                  # section 4
python3 -I tools/survey.py -v               # section 5
python3 -I tools/score.py 'M>S' 'L>C' 'C>S' 'S>C' -v   # section 8
python3 -I tools/recompile.py PRINTF SPRINTF SETJMP SIGNAL  # section 9
python3 -I tools/rebuild.py -v              # section 10
python3 -I tools/checklib.py out/CLIBS.LIB out/CLIBC.LIB
python3 -I tools/difftest.py                # section 12
```

Expected results: `out/CLIBS.LIB` SHA-256
`95100563d6885e7f0eba7c1a96aa0587bdf2fbe9ef8bfbaf73a367f85216b8c0`,
`out/CLIBC.LIB` SHA-256
`b53e05b77252a952e0896abc3612846bae2a10f4c584d1fa682e752b6e24bcae`.
The whole process is deterministic: the same zip gives the same bytes on
any machine.

Ways to check the work independently:

- Compare `out/CLIBS.LIB` and `out/CLIBC.LIB` with the damaged files: every
  byte outside the foreign sectors of section 4 is equal, except the three
  repaired bytes.
- `python3 -I tools/moddiff.py out/CLIBS.LIB M NAME! -d` shows any rebuilt
  small module beside its medium template (read from the zip), record by
  record and, with Open Watcom's `wdis` installed, as disassembly.
- `out/PROVENANCE.csv` (also committed as `PROVENANCE.csv`) gives each
  module's status, route, confidence and the converter's notes; each note
  names the place in the code.
- Any source in `recompile/` can be compiled with Watcom C 6.5 and compared
  with the intact libraries (`recompile.py` does this).

Tools:

| tool | does |
|---|---|
| `restore.py` | runs everything below in order and checks the result |
| `tools/paths.py` | where everything lives; reads the zip |
| `tools/install.py` | installs Watcom C 6.5 from the zip, as its INSTALL.SCR does |
| `tools/dosrun.py` | runs a DOS batch file with 6.5 in headless DOSBox-X |
| `tools/omf.py` | reads a library: header, dictionary, module spans, records with checksums |
| `tools/omfrec.py` | decodes and re-encodes every record type, byte-exact |
| `tools/damage.py` | the sector damage map |
| `tools/survey.py` | which modules survive |
| `tools/x86.py` | 8086/80186 instruction decoder |
| `tools/convert.py` | the medium-to-small / large-to-compact converter |
| `tools/score.py` | scores the converter and the cross route on survivors |
| `tools/moddiff.py` | compares one module across two libraries |
| `tools/recompile.py` | compiles `recompile/NAME.c` in all models and compares |
| `tools/rebuild.py` | builds `out/CLIBS.LIB`, `out/CLIBC.LIB`, `out/PROVENANCE.csv` |
| `tools/checklib.py` | strict sequential check of a library |
| `tools/difftest.py` | builds and runs `tests/` in all four models |


## 16. Open questions

- Why compact SPAWNVE is one byte longer than conversion gives
  (decision 3 is the best available answer, not a proven one).
- The exact compiler revision and per-module switches Watcom used; the
  register differences in SIGNAL (medium, large) and SPRINTF (huge).
- Whether the six lower-case CLIBS modules came from other sources.
- P_OVERLAY spawn (through the far exec hook) is untested.
- More modules could be moved to the recompile route (FMALLOC, SPAWNVE,
  and the code-pointer modules), which would raise their confidence where
  CLIBM and CLIBL can be reproduced exactly.
