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
17. Corroboration from the shipped programs


## 1. Principles

- Bytes that survived are never changed, except three that are provably
  corrupted (section 11, decision 1).
- Every rebuilt module must fill exactly the space the original module
  occupied, and must contain exactly the public names the intact library
  dictionary lists for it.
- Every converter rule applied to a lost module is first tested on
  modules that did survive.  A rule that makes any surviving module come
  out wrong is not kept.  A recompiled module's test is that its source
  gives the intact medium and large modules exactly, with two
  exceptions: SIGNAL differs in one register choice there (section 9,
  decision 2), and SETJMP's small and compact code is an edit of the far
  code that those matches cannot test, checked for small against a
  shipped program, and for compact by no shipped program (only the test
  programs exercise it) (section 9, decision 4).
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
  and record sequentially instead of trusting the dictionary, then checks
  the end record and the dictionary against what it found
  (`tools/selfcheck.py` shows it rejects one-byte damage).

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
  the true checksum is 0).  `tools/checklib.py` enforces this: every module
  record's bytes must sum to 0 mod 256, zero checksum bytes included, and
  the intact CLIBM, CLIBL and CLIBH and both restored libraries pass.
- The end record runs exactly up to the dictionary (CLIBS: F1h at 86128,
  length 397, dictionary at 86528; CLIBC: 91488, 157, 91648), and its
  payload is all zeros; the dictionary ends the file.
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
- A sector that matches no file whole but splits in two is foreign (a
  "split" sector): for some file A, the sector's offset o satisfies o <
  len(A) < o + 512 and the sector's bytes up to len(A) equal A's at the
  same offsets, and for some file B the rest of the sector equals B's bytes
  at the same offsets.  The end of one file and the start of the next
  file's run, at the same offsets, as the copy went from one file to the
  next.  CLIBS has three, one between each pair of its foreign runs:

  | sector | end of A, same offsets | then B, same offsets |
  |---|---|---|
  | 19968-20480 | 19968-20080 DISK3/WDISASM.EXE (20080 bytes long) | 20080-20480 DISK3/WMAKE.EXE |
  | 28672-29184 | 28672-28978 DISK3/WMAKE.EXE (28978 bytes long) | 28978-29184 DISK3/WLINK.EXE |
  | 38400-38912 | 38400-38528 DISK3/WLINK.EXE (38528 bytes long) | 38528-38912 DISK3/WVIDEO.HLP |

  So all 96 foreign CLIBS sectors match other files' bytes.

**Result.**

| | CLIBS.LIB | CLIBC.LIB |
|---|---|---|
| size | 96256 | 101376 |
| foreign | 96 sectors, 49152 bytes | 101 sectors, 51712 bytes |
| dictionary | at 86528, 19 blocks, genuine | at 91648, 19 blocks, genuine |

CLIBS foreign runs (all at the same offsets in the named files, each run
ending at its file's length): 14336-20080 DISK3/WDISASM.EXE; 20080-28978
DISK3/WMAKE.EXE; 28978-38528 DISK3/WLINK.EXE; 38528-63488
DISK3/WVIDEO.HLP.  All 49152 foreign bytes match.

CLIBC foreign runs: 11776-22016 DISK4/MATHM.LIB (same offset); 22016-37376
the last 15360 bytes of DISK4/CLIBM.LIB (its last modules and its
dictionary, sector-aligned there); 37376-63488 DISK4/CLIBM.LIB (same
offset).

That is the observation.  How the damage arose is a hypothesis: the
pattern (whole sectors of other files, mostly at their own offsets) looks
like a copy made from a hard disk with unreadable sectors, where the
copying tool left whatever its buffer last held.  Nothing in this method
depends on that explanation.

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
  index is renumbered.  Near code has one code segment, so every
  CODE-class segment becomes `_TEXT`, whatever its name.  One module's is
  not named `*_TEXT`: the assembler module DOINTR's segment is named
  `CODE` (LNAMES `['', 'CODE']`, SEGDEF name 2, class 2), the only such
  module in CLIBM and CLIBL.  Its name is also its class name, so it is
  kept and `_TEXT` is appended (LNAMES `['', 'CODE', '_TEXT']`), as
  Watcom's own assembler modules do for a `_TEXT` segment (CHAININT in
  CLIBM has exactly these LNAMES).
- **SEGDEF**: name, class and overlay indexes renumbered; the code
  segment's length is the new code length.  A code segment renamed from a
  name not ending in `_TEXT` points at the appended `_TEXT` (DOINTR: name
  3, class 2, ACBP unchanged).
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
  the surviving pairs, which showed one consistent mapping.  In a module
  whose code segment was renamed from a name not ending in `_TEXT`, a frame
  given explicitly as the code segment (F0) is also written as F5, with no
  frame datum: the same meaning for the linker.  DOINTR's 15 cs-relative
  scratch fixups are the case; the modules that keep explicit F0 frames
  on a `_TEXT` segment (CSTART, STK, IFS, I4D, FSMATH, FSI, FDMATH, FDC,
  AMODF) are survivors reproduced exactly and are not touched.  The
  encoding is forced by the dictionary: DOINTR's page span is 352 bytes in
  both libraries; a verbatim rename (LNAMES 6 bytes longer, F0 frames
  kept) makes the module 354 bytes, which does not fit, and the F5 form
  makes it 339 (from 348).  So the original small and compact DOINTR was
  not simply the donor source assembled with `_TEXT`; its real record
  encoding is unknown, and the module stays `low`.  Before this rule
  DOINTR's segment kept the name `CODE` (section 13).
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
  `add/sub sp`) or switch stacks, it stays RETF.  DOEXEC's stubs that start
  a loaded program, and the INT emulation below, are the cases.  A `mov
  sp,bp` in the block is an ordinary epilogue unless the instructions
  between it and the RETF plant the two words the RETF pops: after `mov
  sp,bp`, and until an instruction writes BP (or `pop bp`), `[bp+d]` is
  the stack slot at sp+d, so with k pops (`58-5F`, `07`, `17`, `1F`, `9D`,
  `8F`) before the RETF it pops `[bp+2k]` and `[bp+2k+2]`; if both were
  written in that window (`87` xchg, `89` mov r to m, `8F` pop m, `C7` mov
  imm to m, `8C` mov sreg to m, with ModR/M mod 1 or 2, rm 6), the RETF is
  a far jump and stays (note `retf-jump-kept`).  Writes before the `mov
  sp,bp` do not count (INT86 and INT86X write `[bp+0..10]` there through a
  repurposed BP).  CHAININT (`_chain_intr`) is the case: `mov sp,bp` to
  the interrupt handler's frame, `xchg [bp+10h],cx` and `xchg [bp+12h],ax`
  into the saved CX and AX slots, eight pops, RETF to the previous
  handler.  Over every CLIBM and CLIBL module the rule fires on CHAININT
  only.  The evidence that this RETF is what small code had: DISK2/WCPP.EXE
  holds the small-model SIGNAL code (section 17), whose near call at file
  offset 0x6776 reaches 0x6870, where the 21 bytes equal CLIBM's CHAININT
  byte for byte, ending in `CB` at 0x6884; the same 21 bytes are in
  DISK1/WCC.EXE at 0x3038 and DISK7/WCEXP.EXE at 0x5DA8.  Before this
  rule `mov sp,bp` always ended the scan and the RETF became RET
  (section 13).
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

  In compiled C, BP is followed through the function: within a frame
  opened by `push bp; mov bp,sp`, BP is followed through the function's
  straight-line code.  The stub reached by an interrupt-emulation call
  (`pushf; push cs; call L`, whose RETF is kept, above) is inline code of
  the same function, not a function entry: it does not end the frame, and
  the sequence `pushf; push cs; call` together with the stub is
  stack-neutral (the handler's IRET consumes it).  The stack depth below
  the frame is counted through pushes, pops, `add/sub sp,n` and `mov
  sp,bp` (depth 0).  A `push bp` while BP is the frame pointer records the
  depth at which the frame BP was saved.  Any other write to BP (`mov
  bp,...`, `xchg`, `lea`, `lds/les bp`, `inc/dec`, arithmetic, `pop bp` at
  a different depth) means BP is repurposed: `[bp+d]` is then not a frame
  access and is left alone, until a `pop bp` at the saved depth restores
  the frame.  A `pop bp` when no frame BP is saved on the stack is the
  function epilogue and leaves the state unchanged.

  This rule changes two modules, both compact: INT86 (`lds bx,[bp+10h]`
  after the interrupt becomes `[bp+0Eh]`) and INT86X (`[bp+0Eh]` becomes
  `[bp+0Ch]`; its `[bp+6]` and `[bp+4]`, read through a temporary BP, are
  left alone).  Before it, the converter forgot the frame at the stub and
  left the reload unadjusted (section 13).  It only re-labels INTDOSX in
  both libraries: its bytes are unchanged, but its accesses through a
  temporary BP are no longer reported as touching the return address, so
  its confidence is `medium`, resting on this corrected frame
  interpretation; both INTDOSX rows stay `inferred` with no genuine bytes.
  The analysis follows instructions in address order, ignoring branches;
  that is exact for the straight-line inline code it exists for, and it is
  validated on this corpus (the survivor score of section 8 is unchanged,
  and the three inline-assembly modules INT86, INT86X and INTDOSX come out
  as traced by hand), not proven for arbitrary control flow.
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
  was kept because it fitted the jump study better.  The rule is known to
  be wrong in two places.  Compact FWRITE (section 8) keeps a jump long
  that the compiler shortened.  And the REALLOC in the shipped
  `WMAKE.EXE`, reached by following the near call in its PUTENV (which
  matches the rebuilt small PUTENV byte for byte), has its two jumps to
  the shared exit long then short (`E9 77 00` at 11h, `EB 6C` at 1Dh)
  where the rule gives short then long; medium has both long.  Small
  REALLOC is therefore graded low (section 17).  No simple alternative
  fits better: in the five libraries the compiler left 26 forward jumps
  long that fit in a byte, at distances from 99 to 122, and made others
  short at 120 to 122; neither another pass order nor counting the
  not-yet-sized later branches at their long size separates the two
  groups.
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
  threshold was measured: 3 breaks two surviving modules, 4 and 5 are
  equal on the survivors and on the math libraries (section 8), 6 loses
  one.  The shipped `INSTALL.EXE` and `WMAKE.EXE` both hold small STAT
  with its four-byte exit (`pop si; pop cx; pop bx; ret`) shared by a
  jump (section 17), so the threshold is 4; on this corpus that changes
  small STAT and nothing else.
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

Alignment bytes.  A data segment's string literals are word-aligned with
`/ot` or `/ox`, and the alignment byte between two strings is whatever
the compiler's buffer held (section 6).  The converter copies each data
segment from the medium or large donor unchanged, so a rebuilt module's
alignment bytes are the donor's.  The survivors show that such a byte
does not carry over: small TZSET's is `54` where medium has `CE`, small
ASCTIME's `02` where medium has `4A` (section 8), while every other byte
of the 259 small and 250 compact surviving data segments equals the
donor's.  So the converter has no evidence of its own for these bytes,
and five of them, in three small modules, are written from the shipped
6.5 programs that hold the module's code (section 17; section 11,
decision 6).  In each program the code's DGROUP-relative operands were
resolved through the startup's `mov ax,DGROUP` word, which carries an MZ
relocation, to the string block, and every other byte of the block
equals the rebuilt segment:

| module | segment, offset | donor | program | program@file offset |
|---|---|---|---|---|
| SPAWNVE | 2, +5 | `B2` | `00` | DISK1/WCL.EXE@2b91, DISK3/WMAKE.EXE@6d4d |
| SYSTEM | 2, +3 | `08` | `89` | DISK3/WMAKE.EXE@6d57 |
| STRERROR | 2, +0x2F | `A1` | `00` | DISK2/WCPP.EXE@8a4b |
| STRERROR | 2, +0x43 | `0A` | `00` | DISK2/WCPP.EXE@8a5f |
| STRERROR | 2, +0x95 | `59` | `84` | DISK2/WCPP.EXE@8ab1 |

SPAWNVE's block is `.exe`, pad, `.com`; SYSTEM's `/c`, pad, `COMMAND`,
`COMSPEC`; STRERROR's is the 306-byte message segment that its pointer
table (segment 3) points into.  The medium forms of the same blocks
occur in DISK7/WCEXP.EXE (SPAWNVE at 0x38000, SYSTEM at 0x38162,
STRERROR at 0x37caa) and, for STRERROR, DISK1/WCC.EXE at 0x17ad0, all
programs whose code for the module is the medium one.  SYSTEM and
STRERROR rest on one program each.  The rebuilt module is noted
`pad-witnessed:FILE@hex` for each byte.  The other alignment bytes keep
the donor's value, since nothing witnesses them: small EXECVE (1 pad)
and STRFTIME (19); compact EXECVE (1), SPAWNVE (1), STRERROR (3),
STRFTIME (19), SYSTEM (1) and TZSET (1).  No compact-model 6.5 program
exists to check them, and the 7.0 programs hold different string
blocks.  Small TZSET survives.  Nothing reads an alignment byte.

Assembler modules (no source-name COMENT) keep the source module's record
order, with LEDATA up to 1020 bytes.  Bytes that no record of the source
module defines stay undefined: DOSPAWN's assembler source left one word
of its scratch area (code offsets 6-7) as `DW ?`, so its LEDATA stops at
6 and resumes at 8, in every intact library; the rebuilt small and
compact DOSPAWN do the same.  The linker leaves such bytes as they were,
and the two shipped programs holding small DOSPAWN have different words
there (section 17).

### 7.5 Notes

The converter records every non-trivial thing it did or could not do as a
note in the provenance (e.g. `call-far-indirect`, `cross-jump`,
`stack-check-size`, `overlapping-insns`, `guessed-code`,
`code-segment-ref`, `code-segment-renamed`, `retf-jump-kept`).  Section 8 measures how often modules with each note
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

These numbers are development-set measurements: the rules were tuned on
these same modules, so they are optimistic for the lost modules.  The
strongest further constraint is CLIBC SCNF (section 10), and it is not
independent either.  `python3 -I tools/score.py 'M>S' 'L>C' --check`
freezes the scores as a regression test: it fails unless both routes score
exactly these populations, with no module unsupported and exactly the
differing modules listed above.

**Outside the development set.**  The math libraries are intact in all
five models, so their small and compact modules are answers the converter
never saw.  `python3 -I tools/score.py --math` converts every module of
MATHM to small and MATHL to compact (and MATH87M, MATH87L), passing the
donor's group name, and compares with MATHS, MATHC, MATH87S and MATH87C:

| route | targets | exact |
|---|---|---|
| MATHM to MATHS | 42 | 38 |
| MATHL to MATHC | 42 | 39 |
| MATH87M to MATH87S | 34 | 34 |
| MATH87L to MATH87C | 34 | 34 |

The differing modules are `_MATHERR`, SINCOS, ATAN2 (both routes) and POW
(medium to small).  Five of these seven (`_MATHERR`, POW and ATAN2 from medium
to small; `_MATHERR` and SINCOS from large to compact) fill their page span in
the intact library with fewer than 16 bytes of padding and carry the
dictionary's names, so the page-fit and name checks of section 10 would have
accepted them: a measured example of what those checks cannot tell apart.  No
rule was tuned on these libraries, but they are not a sample of the lost CLIB
modules either: they are mostly floating-point routines with few calls and no
code pointers.  The result supports the conversion technique; it gives no
percentage for the lost modules.


## 9. The recompile route

Tool: `tools/recompile.py`; sources in `recompile/` (described in
`recompile/README.md`).  By role:

| source | role |
|---|---|
| `PRINTF.c` | validation case: reproduces all five libraries; the surviving S and C modules are kept, so its objects are not needed |
| `SPRINTF.c` | supplies the rebuilt small and compact modules |
| `SETJMP.py` | supplies them; generates the C source, whose far bodies are read from the user's CLIBM and CLIBL and whose near variants are explicit edits |
| `SIGNAL.c` | supplies them, accepted near-exact (decision 2) |
| `FMALLOC.c`, `SPAWNVE.c` | attempts, not reproduced, not used |

Each `.opt` file holds the switches that make 6.5 reproduce the module,
not Watcom's own build line, which is unknown.

For modules the converter cannot do (code pointers), C source was written
by reading the CLIBM and CLIBL machine code, and compiled by Watcom C 6.5
itself in all five models (with the source placed so it is named
`..\c\NAME.c`).  A source counts as reproducing a module when the medium
and large objects are byte-identical to CLIBM's and CLIBL's modules: medium
pins down everything that depends on the code model, large everything that
depends on the data model, so small and compact compiled from the same
source are very likely right.  That reasoning holds for compiled C.
SETJMP's functions are `#pragma aux` instruction lists written out per
model, so its medium and large matches verify the far lists only, and
nothing about the small-code lists, which are edits of them.  The small
list is checked against the code a shipped small-model program, WLIB.EXE,
calls; the compact list is checked by no shipped program; only the test
programs exercise it.  The provenance notes this
(`near-code-witnessed:DISK3/WLIB.EXE@2852` for small, `near-code-inferred`
for compact) and grades both objects medium.  The sources are
reconstructions written for this project, not Watcom's.

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
  source variant changed it.  Two shipped small-model programs contradict
  the small object (79 code bytes).  The `sprintf` in DISK1/INSTALL.EXE
  at file offset 0x2b1e and in DISK2/WCPP.EXE at 0x68ac is 82 code bytes:
  it keeps the destination in SI across the `_prtf` call (`push si; mov
  si,[bp+0Ch]; ... mov ax,si; ... mov bx,si`) where the rebuilt one
  reloads it from the stack.  `vsprintf` and the output callback are
  identical, and all four fixup fields resolve in both programs: both
  calls reach the surviving small PRTF code (at 0x2155 and 0x4b85) and
  both callback pointers reach the local output routine.  No shipped
  program holds the 79-byte form.  The same source compiled with `/ot /s`
  or `/ox /s` gives exactly the 82 witnessed bytes in small (a 303-byte
  object, which fits the 304-byte span), but those switches break the
  medium and large matches.  So the switches or the source differed for
  the small build, and nothing shows which.  The bytes stay, since the
  `/os` source has evidence of its own (the medium and large matches);
  the rebuilt small SPRINTF is noted
  `witness-differs:DISK1/INSTALL.EXE@2b1e` and graded low, as REALLOC is
  (section 17).  Compact SPRINTF has no witness and is unchanged.
- **SETJMP**: written as two C functions whose bodies are `#pragma aux`
  inline code, one variant per model (nested `#if`, since 6.5 has no
  `#elif`).  Medium, large and huge exact.  So that this repository holds
  none of Watcom's code, the source is generated at build time by
  `recompile/SETJMP.py` from the user's own CLIBM and CLIBL modules.
  The small-code variants are two edits of the far ones.  `_setjmp` pops
  the return offset to 14h of the jmp_buf as the far form does, then
  stores CS at 12h (`mov [si+12h],cs`) where the far form pops the return
  segment, and pushes the offset back alone; so the jmp_buf layout is the
  same in every model.  `longjmp` discards the near return address with
  `pop di` (DI is reloaded from the buffer afterwards) where the far form
  has `add sp,4`, pushes the offset alone and ends in RET.  The small list
  equals the `_setjmp` and `longjmp` that DISK3/WLIB.EXE, a small-model
  program, calls: 84 of 84 code bytes at file offset 0x2852, with no fixup
  fields among them; WLIB's near call at 0xd01 and its tail jump at 0xf4f
  reach them, both passing the buffer at DS:0F74h.  The compact list
  applies the same edits to the large form, and no shipped program checks
  it.  A probe that reads the jmp_buf after `setjmp` sees the caller's CS
  in slot 9 (offset 12h); the previous form left that slot untouched.  (A
  variant keeping the offset at 12h instead of 14h also matched medium,
  large and huge, fitted both spans and passed T_MISC; WLIB settles it at
  14h.)
- **SIGNAL**: an INT 23h handler (`interrupt` function), `signal`, `raise`
  with a switch on the signal number.  The library has two public names at
  one address, `raise_` and `__raise`: reproduced by a function `__raise`
  whose body is `return raise(sig);` placed just before `raise`, which
  6.5 compiles to a jump to the next instruction and then removes.  Medium
  and large differ from the library in one register choice in `signal`
  (the table index in BX instead of SI); dozens of source variants and the
  other code generator did not change it.  Accepted, see decision 2.
  `recompile/SIGNAL.accept` pins the SHA-256 of all five objects this
  source gives, so a changed source, even one whose change shows only in
  the small and compact objects, is not accepted; and `rebuild.py` uses an
  object only when `recompile.py`'s status file vouches for its SHA-256.
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
   accepted sources), **unchanged** (CLIBM's module as it is, for the one
   model-independent routine), **cross** (the other damaged library's
   surviving module, when CLIBM and CLIBL are identical), **convert**.  The
   order matters where more than one fits: EXECADDR fits both unchanged
   and convert, and decision 3 is to take it unchanged.
3. A candidate is accepted only if, placed at the dictionary's page and
   padded with zeros, it (a) fills the page span exactly (fewer than 16
   bytes of padding) and (b) equals every surviving genuine byte in the
   span.  The first that passes is chosen.
4. The chosen module is written; the others are recorded as agreeing or
   disagreeing.  Then (c) the chosen module's THEADR name and public names
   must be exactly the names the dictionary lists for that page; a
   mismatch fails the module (it is not a reason to try another
   candidate; none has occurred).  Any failed module makes `rebuild.py`
   exit with status 1.

Then the library is checked as a whole: every genuine byte of the damaged
file is unchanged (apart from the repairs), and the original header, end
record and dictionary are kept.  Both libraries pass `tools/checklib.py`,
which walks the modules sequentially, checks every record checksum, the
end record and the dictionary names (a stricter check than the
dictionary alone, see section 13).

Results: CLIBS 106 original + TELL repaired, 2 anchored, 141 inferred
(convert 138, recompile 3, cross 1, unchanged 1).  CLIBC 102 original, 2
anchored, 146 inferred (convert 142, recompile 3, cross 2, unchanged 1).

**The strongest constraint: CLIBC SCNF.**  SCNF is CLIBC's largest partly
surviving module: 3088 of its 3424 bytes are genuine (only the header and
the first code bytes are lost).  It was the test that found three rules
(cross-jumping between far and near exits, near static functions keeping
their frames, the stack-check size), none of which changes any surviving
module's result; with them, the converted module matches all 3088
surviving bytes.  Because those rules were found on it, it constrains the
converter strongly but is not an independent prediction.

**Confidence levels** in the provenance: `high` = recompiled with CLIBM and
CLIBL exact, or the cross route; `medium` = converted with no risky note,
a near-exact recompile, or a recompile whose near-code instruction lists
are edits of the far ones (SETJMP, section 9: `near-code-inferred`, or
`near-code-witnessed:` when a shipped program holds the code); a byte
written from a shipped program (`near-code-witnessed:`, or
`pad-witnessed:` for an alignment byte, section 7.4) never raises the
level; `low` =
converted through code-pointer constructs (notes such as `call-far-indirect`,
`code-segment-ref`), a renamed code segment whose record encoding cannot
be the original's (`code-segment-renamed`, section 7.1), depending on a
decision, or contradicted by a shipped program (`witness-differs`,
section 17).  Low in both libraries: SPAWNVE, EXECADDR, DOINTR, DOEXEC,
INT86, INT86X, SETVBUF; in CLIBS also REALLOC and SPRINTF.  A module that
one shipped program contradicts while another holds the rebuilt code is
noted `witness-mixed:FILE@hex` and keeps its level: the programs were
linked from different builds, and the disagreement is not evidence
against the rebuilt bytes (section 17; ISATTY in both libraries, GETCTIME
in CLIBS, all `medium`).  `witness-differs` is for a module no program
holds as rebuilt while one holds another form.


## 11. Decisions, with the evidence for each

1. **Three genuine bytes repaired** (section 4): CLIBS 14012 `4C`→`6C`;
   CLIBC 11580-11581 `D0 81`→`D1 D1`.  The two repairs rest on different
   evidence.  TELL's on a failing record checksum and the dictionary's
   spelling of the public name, both of which the repair satisfies.
   AMODF's on the sibling libraries (CLIBS, CLIBM, CLIBL and CLIBH all
   have `D1 D1` there) and the instruction stream, in a record that runs
   into a foreign sector and so cannot be checksummed.  Both are recorded
   in the provenance notes of every row whose span holds them, and the
   compact TELL, which is taken from the repaired small one, is marked
   `cross-from-repaired`.
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
   Small SPAWNVE fits either way.  The shipped programs support it: the
   far call in small SPAWNVE has counterparts in DISK1/WCL.EXE at file
   offset 0x1DCB and DISK3/WMAKE.EXE at 0x4D7E (where small SPAWNVE is
   found, section 17), both with DOS loader relocations on the segment
   word, and their targets (0x2084 and 0x5037) load two adjacent words
   into AX and DX and end in RETF, as inferred for EXECADDR.  This
   supports the decision; it does not verify P_OVERLAY's success path
   (section 16).
4. **SETJMP's near-code edits** (section 9) follow the `_setjmp` and
   `longjmp` that WLIB.EXE calls; the compact form applies the same edits
   to the large one and is inferred from it.
5. **The six lower-case CLIBS modules** are rebuilt from CLIBM with the
   dictionary's names; a separate compile may have used other sources,
   which nothing can show.
6. **Five alignment bytes follow the shipped programs** (small SPAWNVE,
   SYSTEM and STRERROR; section 7.4).  The converter has no evidence of
   its own for these bytes: it copies the donor's, and the survivors
   (TZSET, ASCTIME) refute that copy.  So the shipped code decides, as
   for SETJMP's near-code list (decision 4): WCL.EXE and WMAKE.EXE for
   SPAWNVE, WMAKE.EXE alone for SYSTEM, WCPP.EXE alone for STRERROR.  No
   behaviour depends on them: nothing reads an alignment byte.


## 12. Testing in real use

### Programs in every model

Tool: `tools/difftest.py`; programs in `tests/`.  Each program is compiled
by 6.5 in the small, compact, medium and large models and linked by
WLINK 4.1: small and compact against the rebuilt libraries, medium and
large against the intact originals.  T_INT is also built as a tiny-model
.COM: compiled `/ms`, linked after the shipped startup object
`LIB/CSTART_T.OBJ` against the rebuilt CLIBS.LIB, converted by `EXE2COM`.
T_CHAIN cannot be: a 6.5 interrupt function loads DS with the segment of
DGROUP, a relocation EXE2COM refuses.  Each runs in its own DOSBox-X
instance.  Each run must finish in the emulator, the batch file records
the program's exit status and a completion marker, and the status must be
the expected one (3 for T_SPAWN, 0 for the others); then every output
must be identical to the medium one.  All seven agree:

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
- T_INT: int86, int86x, intdos, intdosx and intr with a failing DOS call
  (close handle FFFFh: AX=6, carry set, return value 6, as the intact
  medium and large libraries give), a succeeding one (close a real handle)
  and the DOS version call, every register printed; it exits 1 if a
  promised value is wrong.  Around the failing `intr` call it fills
  CS:00A6h-00B1h with 90h and counts the bytes that change, which must be
  none: DOINTR's CS-relative scratch lands there when DOINTR is not in the
  caller's code segment.  The first function in the file is a 192-byte NOP
  pad that never runs, so in small and compact those offsets are dead code
  (the test's object is the first in `_TEXT`, so the pad starts at offset
  0, and DOINTR is never at offset 0); in the tiny .COM they are the PSP
  command tail.
- T_CHAIN: `_chain_intr`, `_dos_getvect` and `_dos_setvect`.  Two
  interrupt handlers on INT 60h; the first chains to the second through
  `_chain_intr`.  The check calibrates itself: the second handler records
  how far its SP is below the SP taken just before `int 60h`, once when
  installed directly and once when reached through the chain; the two
  must be equal, and when they are not the handler ends the program with
  exit status 7 rather than return through a wrong stack.  Only counts and
  comparisons are printed.

Faults these tests found in earlier versions of the rebuild, all fixed:
SCNF's default-library request (small programs linked MATHM.LIB);
EXECVE's far call through the near `_int23_exit` (exec crashed); the
DOSPAWN hypothesis (spawn crashed, section 13).  Tests were also added for
three faults the earlier programs did not catch: the compact `int86`/`int86x`
frame offsets (the `int86` and `int86x` part of T_INT); `intr`'s scratch stores
in the caller's code segment (the `intr` part of T_INT and its tiny build); and
`_chain_intr` returning near (T_CHAIN); all three in section 13.  On the
earlier outputs that still have the last two faults (section 15), T_INT fails
in small, compact and tiny (12 bytes changed, exit 1) and T_CHAIN in small and
compact (exit 7).

### Every module through the 1988 librarian and linker

Tool: `tools/periodcheck.py`, run by `restore.py --test` after the
programs.  The test programs pull in 156 of the 250 small and 155 of
the 250 compact modules (by their link maps); the others had been read
only by `tools/checklib.py`.  This tool hands every module of each restored
library to Watcom's own 1988 tools in DOSBox-X:

- **WLIB 1.1** extracts every module (a command file of `*NAME` lines,
  `WLIB CLIBS @EXT`).  Each object written, identified by its THEADR
  name, is byte-identical to the module's bytes in the library (THEADR
  to MODEND): 250 of 250 in both libraries.  WLIB rewrites nothing, and
  leaves the library unchanged.
- **WLINK 4.1** links a generated program that takes the address of
  every one of the library's 371 publics, against the library under test
  and the intact MATH library, with a map.  WLINK 4.1 has no `REFERENCE`
  directive, so the references are C (`extern void NAME(void); #pragma
  aux NAME "*";`).  Every one of the 250 modules appears in the map's
  memory map, in both libraries.  OVLLDR refers to `_OVLTAB`, which WLINK
  builds only for an overlaid program, so the link has one overlay
  section, with `OPTION SMALL` in near code (without it WLINK asks for
  the far loader `_LOVLLDR`).  The link prints one message, `redefinition
  of _FtoS_ ignored` for MATH's FTOS: FTOSX and FTOS both define
  `_FtoS_`, and SCNF's reference to `_fltused_` pulls in FTOS.  The intact
  CLIBM, CLIBL and CLIBH give the same message, and it is the only one the
  tool accepts.

The intact CLIBM, CLIBL and CLIBH pass both checks the same way
(`python3 -I tools/periodcheck.py M L H`).  What this proves: the 1988
librarian and linker accept every rebuilt module's records and resolve
every public the dictionary names.  What it does not prove: that the code
is right.  Wrong bytes in valid records pass, and the three runtime
defects of sections 7.1 and 7.3 (compact `int86`/`int86x`, DOINTR's
segment, CHAININT's RETF) were exactly that, so this check would not have
caught any of them.  Neither WLIB 1.1 nor WLINK 4.1 checks record
checksums either: a byte changed inside a record passes both, with or
without its checksum corrected.  That is `checklib.py`'s job.  A changed
public name fails the link, and a broken record length fails before the
tools run.

## 13. Hypotheses that failed, and dead ends

- **DOSPAWN as a far, model-independent routine** (the first answer to the
  SPAWNVE size problem): refuted when DOSPAWN, taken unchanged from CLIBM,
  crashed spawn in small and compact.  DOSPAWN itself calls `_dosretax_`
  far, and that C routine is near in small code.  Replaced by decision 3.
- **An undersize module** (SPAWNVE one byte short, leaving an extra page of
  zeros): WLINK would accept it (it finds modules through the dictionary),
  but a strict checker walks modules sequentially and stops at the zero
  page.  Rejected: every module must fill its span.  A fallback that still
  accepted such a module when nothing else fitted remained in
  `rebuild.py` (no published module used it); it has been removed.
- **The frame ended at the inline interrupt stub.**  The frame analysis treated
  every near-call target as a new function and forgot the frame there,
  including the stub that `pushf; push cs; call` reaches in INT86 and INT86X.
  In compact those modules then reloaded their output pointer from the wrong
  offset after the interrupt, so a failing DOS call came back with carry clear
  and a wrong return value.  Small was unaffected (medium keeps that pointer at
  a negative offset).  Corrected by following BP through the stub (section
  7.3).
- **DOINTR's `CODE` segment kept its name.**  The LNAMES rule renamed only
  segments named `*_TEXT`, so DOINTR's code segment stayed `CODE`.  WLINK kept
  it as a separate segment; the converted near call from INTR still reached it,
  but CS stayed the caller's `_TEXT`, so DOINTR's 12 bytes of cs-relative
  scratch (00A6h-00B1h) were written into the caller's code segment at those
  offsets, or into the PSP command tail in a tiny-model .COM.  The registers
  came back right, so nothing else noticed.  Corrected by giving every code
  segment the name `_TEXT` (section 7.1).
- **`mov sp,bp` always an epilogue in the RETF-as-jump rule.**  The backward
  scan stopped at `mov sp,bp`, so CHAININT's final RETF, which consumes two
  words planted after `mov sp,bp`, became RET: `_chain_intr` jumped to the
  previous handler's offset in the current code segment and left its segment
  word on the stack.  The INT 23h handler of the recompiled SIGNAL calls it.
  Corrected by the window rule of section 7.3.
- **A "RETF used as a jump" rule that counted `mov sp,bp` as a stack
  switch**: it turned normal epilogues into jumps and broke 17 surviving small modules;
  corrected (section 7.3).
- **An asm frame rule for `mov bp,sp`** broke FSMATH until stack releases
  (`add sp,n`) were counted.
- **Watcom C 386 7.0** (the only 7.0 available) is the 32-bit edition with
  32-bit libraries only; no library bytes to take.  Its DOS programs are
  16-bit and hold later builds of some of the run-time code, including
  compact-model code; they serve as later witnesses only (section 17).
  8.5 and 9.01 likewise have no library bytes to take; 9.5 and later are
  a different code generator.  7.0 ships a few run-time sources
  (IOB.C, NFILES.C, WILDARGV.C, CMAIN386.C), useful only as reference.
- **WCGL.EXE** in place of WCG.EXE: different output, no closer.
- **Local declaration order** for register allocation: no effect.
- **Iterated jump sizing**: no better than one pass.
- **WCEXPL.LIB** (WATCOM Express): 591 modules; 241 of CLIBM's 250 appear
  in it byte for byte, 7 are absent by name (WRITE, READ, QREAD, MIN, MAX,
  SIGNAL, FTOSX) and 2 same-named ones differ (GETCTIME, D2TTIME).  None
  carries `_small_code_`; of the 35 with a code segment named `_TEXT`, 28
  are byte-identical to CLIBM's assembler modules of the same name and 7
  are 8087 math modules.  The search found no small-model donor there.


## 14. Confidence

This is my estimate, a judgment and not a measurement: for lost modules
nothing survives in the original library span to check against.  The
shipped programs hold the code of 59 small and 6 compact of them (section
17), but only instruction bytes outside the fixup fields are compared,
not records, data or relocation targets, and the programs disagree among
themselves.  It is a weighted count.  The counts
are from `PROVENANCE.csv`; the weights are my own judgment, with no
measured basis behind them: originals certain (1); medium-confidence
rebuilt modules 0.88-0.93 each (from 96.5% exact on survivors, discounted
for having been tuned on them, for hidden small-model source conditionals
like PRINTF's, and for padding bytes); high-confidence modules 0.80;
low-confidence ones 0.30.

| group | weight | CLIBS count | CLIBS expected | CLIBC count | CLIBC expected |
|---|---|---|---|---|---|
| original | 1 | 107 | 107 | 102 | 102 |
| medium | 0.88-0.93 | 133 | 117.0-123.7 | 138 | 121.4-128.3 |
| high | 0.80 | 1 | 0.8 | 3 | 2.4 |
| low | 0.30 | 9 | 2.7 | 7 | 2.1 |
| **modules expected byte-identical** | | 250 | **227.5-234.2 (91-94%)** | 250 | **227.9-234.8 (91-94%)** |

(An earlier version of this table gave 92-94% for CLIBS and 90-93% for CLIBC
without the arithmetic; the same weights applied to the counts of that time
give 91.2-93.8% and 90.9-93.6%.  The frame rule of section 7.3 has since moved
INTDOSX from low to medium in both libraries; SETJMP has moved from high to
medium in both (section 9), small REALLOC from medium to low (section 17) and
small SPRINTF from high to low (section 9).)  For bytes I put the figure at
about 98% (CLIBS) and 97-98% (CLIBC), on the view that a wrong module usually
differs in a few bytes; that too is a judgment.  The chance that either whole
library is byte-identical is close to zero.

Two objections to this estimate stand: the "high" modules (recompiled with
CLIBM and CLIBL exact, or the cross route) are weighted below the "medium"
ones, which is inconsistent with the labels; and a wrong module need not differ
in a few bytes only, since a single changed instruction length shifts
everything after it.  The numbers above should be read with that in mind.
Behaviour is better evidence than these numbers: every test agrees with the
original medium and large libraries.


## 15. Reproducing and checking the work

`README.md` gives the full instructions for Linux and Windows.  In short,
with the zip in the repository folder, Python and DOSBox-X:

```
python3 restore.py             # everything, ending with the hash check
python3 restore.py --test      # and the test programs in all four models (and tiny)
```

The individual steps, each a tool that can be run alone:

```
python3 -I tools/install.py                 # Watcom C 6.5 into build/watcom
python3 -I tools/damage.py                  # section 4
python3 -I tools/survey.py -v               # section 5
python3 -I tools/score.py 'M>S' 'L>C' 'C>S' 'S>C' -v   # section 8
python3 -I tools/score.py --math            # section 8, the math libraries
python3 -I tools/recompile.py PRINTF SPRINTF SETJMP SIGNAL  # section 9
python3 -I tools/rebuild.py -v              # section 10
python3 -I tools/checklib.py out/CLIBS.LIB out/CLIBC.LIB
python3 -I tools/difftest.py                # section 12
python3 -I tools/periodcheck.py             # section 12
python3 -I tools/exematch.py                # section 17
```

The later witnesses of section 17 come from the 7.0 distribution's disk
images, read with mtools into one folder per image, then searched:

```
for n in 1 2 3 4 5 6; do
  mkdir disk$n && mcopy -i disk$n.img -n "::*" disk$n/
done
python3 -I tools/exematch.py --programs DIR   # DIR holds disk1/ .. disk6/
```

Regression checks to run after any change to the tools:

```
python3 -I tools/score.py 'M>S' 'L>C' --check   # converter score unchanged
python3 -I tools/selfcheck.py                   # the checker still bites
```

`score.py --check` must print `score unchanged` after any converter
change.  `selfcheck.py` damages `out/CLIBS.LIB` one byte at a time in
memory (a record checksum, a dictionary name, the end record's payload and
its length) and fails unless `checklib.py` rejects each for that reason.
The test programs include T_INT and T_CHAIN (section 12), which fail on
the earlier outputs below: the `int86` and `int86x` part of T_INT on the
first compact library, and the `intr` part of T_INT and T_CHAIN on every
earlier small and compact library.

Expected results: `out/CLIBS.LIB` SHA-256
`27ba210a1c1bc70960169e82a2cc09e9ce167c6c7b504985b4735cd95606a3ca`,
`out/CLIBC.LIB` SHA-256
`a708a545ecd064717e7ccfb4e3b3e613472ae294d4476c86fafe94e353a81627`.
Earlier outputs: CLIBS
`95100563d6885e7f0eba7c1a96aa0587bdf2fbe9ef8bfbaf73a367f85216b8c0`,
before DOINTR's code segment was named `_TEXT` (section 7.1) and
CHAININT's final RETF was restored (section 7.3), then
`6cd1fee804d12b2e811709f6f2042354c0b80ea444e97257e377fb9e57bf3a81`,
before DOSPAWN's undefined word was left undefined (section 7.4) and
STAT's four-byte exit was shared (section 7.3), then
`9f7c970a5f65ccb40550f1d83e5864a0123c2cd36ae6b2446b61cbfd4186e22b`,
before SETJMP's near-code form followed WLIB.EXE (section 9), then
`74d7dcfc7051e312e395bd67a0d1058fe645f960b0b8988494e13913cfbd0e97`,
before five alignment bytes followed the shipped programs (section 7.4);
CLIBC
`b53e05b77252a952e0896abc3612846bae2a10f4c584d1fa682e752b6e24bcae`,
before the frame rule of section 7.3 corrected the `int86` and `int86x`
offsets, then
`69e6fe1e9b4e0f2b50e047c24c2678fe564c773ead325356376ddce794d9d58b`,
before the same two changes as the first CLIBS, then
`9fea459aaaf22ef2feb5284f39c22244ad49312f2330684871566779c06445ae`,
before the DOSPAWN change, then
`1cd2b834f4848fdf635986f28b17f607ef3bdfb96eca97d71ea71b349f980e6b`,
before the SETJMP change.  The last four changes alter no behaviour.
The whole process is deterministic: the same zip gives the same bytes on
any machine.

DOSBox-X configured as DOS 3.10 is an emulator reporting that version,
not a booted copy of DOS 3.10.  The `int86`/`int86x` probes were also
run under Compaq DOS 3.10 booted in QEMU, with the same results.

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
| `tools/score.py` | scores the converter and the cross route on survivors, and the converter on the math libraries |
| `tools/moddiff.py` | compares one module across two libraries |
| `tools/recompile.py` | compiles `recompile/NAME.c` in all models and compares |
| `tools/rebuild.py` | builds `out/CLIBS.LIB`, `out/CLIBC.LIB`, `out/PROVENANCE.csv` |
| `tools/checklib.py` | strict sequential check of a library |
| `tools/selfcheck.py` | shows `checklib.py` rejects one-byte damage |
| `tools/difftest.py` | builds and runs `tests/` in all four models, and T_INT as a tiny .COM |
| `tools/periodcheck.py` | has the 1988 WLIB extract, and WLINK link, every module of a library |
| `tools/exematch.py` | finds rebuilt code in the archive's own programs, or with `--programs` in other programs (section 17) |


## 16. Open questions

- Why compact SPAWNVE is one byte longer than conversion gives
  (decision 3 is the best available answer, not a proven one).
- The exact compiler revision and per-module switches Watcom used; the
  register differences in SIGNAL (medium, large) and SPRINTF (huge).
  `/ox /s` compiled small reproduces the SPRINTF that INSTALL.EXE and
  WCPP.EXE hold and the SIGNAL that WCPP.EXE holds, and leaves the
  surviving small PRINTF unchanged, but does not reproduce the intact
  medium and large SPRINTF, which `/os` does.
- Whether the six lower-case CLIBS modules came from other sources.
- P_OVERLAY spawn (through the far exec hook) is untested.  A
  P_OVERLAY probe returned -1 with errno 9 in all four models, so it did
  not isolate any difference specific to the reconstruction, and the
  success path of P_OVERLAY remains unverified.
- The record encoding of the original small and compact DOINTR (segment
  naming and fixup frames): the page span excludes a verbatim rename of
  the donor's segment (section 7.1).
- More modules could be moved to the recompile route (FMALLOC, SPAWNVE,
  and the code-pointer modules), which would raise their confidence where
  CLIBM and CLIBL can be reproduced exactly.


## 17. Corroboration from the shipped programs

Tool: `tools/exematch.py`; `--programs DIR` searches other programs
(the later witnesses below).

The programs on the distribution disks (`WCL.EXE`, `WMAKE.EXE`,
`WCPP.EXE` and others) were linked by Watcom with its own libraries,
mostly the small-model one, so lost library code may survive inside them.
For every `inferred` module whose code is one CODE segment with at least
20 bytes outside fixup fields, the tool masks the fixup fields (the linker
fills them) and any byte no record defines (the linker leaves it), and
searches every .EXE and .COM load image in the zip for a single contiguous
place where all the other code bytes match.

Result: for 59 wholly lost small modules and 6 compact ones, every code
byte outside the fixup fields is found in a shipped program (for example
small SPAWNVE in WCL.EXE and WMAKE.EXE, small SIGNAL in WCPP.EXE): 6379
of the 6865 code bytes of those small modules are compared, 365 of 419
compact.  Only 16 small and 4 compact modules occur whole, fixup fields
included (the tool's `whole` column); a masked call or data operand can
name another routine or variable while the comparison succeeds.  An
independent implementation of the search found the same matches without
CHAININT; CHAININT's match, in WCC.EXE, WCPP.EXE and WCEXP.EXE, appeared
once its final RETF was restored (section 7.3).  The 6 compact matches
(MOVEDATA, LSEEK, ISATTY, DOSPAWN, CHAININT, TIMEUTIL) are at the same
places as the small ones: the same bytes, no compact-specific evidence.
The later distribution supplies compact evidence for seven other modules
(below).
DOSPAWN's match covers 188 of its 240 code bytes; the two bytes no record
defines (section 7.4) hold `46 70` in WCL.EXE and `20 6D` in WMAKE.EXE,
whatever the linker's buffer held, which is itself evidence that the
object left them undefined.  For SPAWNVE a further check followed the
linked far call to its target (section 11, decision 3).

Small SETJMP is the one module whose code bytes were written from a
shipped program.  Its near-code instruction list is an edit of the far one, and
the project had no other evidence for that edit: the medium and large
matches do not test it, and no small or compact SETJMP survives.  The list
was made to equal the `_setjmp` and `longjmp` that WLIB.EXE calls (section
9), and the tool finds it there whole, all 84 code bytes
(`DISK3/WLIB.EXE@2852`).  Compact SETJMP passes the buffer in AX:DX, so
its bytes differ from WLIB's and the tool does not list it.  Five
alignment bytes of the data segments of small SPAWNVE, SYSTEM and
STRERROR were likewise written from the programs that hold their code
(section 7.4).

The DOS programs of Watcom C 386 7.0 are later witnesses.  Its archive,
`Watcom C 386.ver.7.0.English.zip` (SHA-256
`cd3972581f513d90aef6dc4c6957f4395e4e7be52f147f23db6e3aaea04df4c0`), from
the same Internet Archive collection as 6.5, holds six 360 KB disk
images, `disk1.img` to `disk6.img`, not plain files; the programs were
read out of them with mtools (`mcopy`, section 15).  Its libraries are
32-bit, but its tools are 16-bit DOS programs linked with a later build
of the 16-bit run-time.  The same search over the 15 .EXE and .COM files
of the six images finds 26 rebuilt small modules and 11 compact ones.
Nine of them are found in no 6.5 program: 2 small and 7 compact.

| library | module | program@file offset | literal/code bytes | whole |
|---|---|---|---|---|
| CLIBC | UNLINK | disk1/WDISASM.EXE@7383 | 22/24 | no |
| CLIBC | DOSRET | disk1/WDISASM.EXE@6e18 | 79/87 | no |
| CLIBC | STRLEN | disk1/WDISASM.EXE@768e | 23/23 | yes |
| CLIBC | STRERROR | disk1/WDISASM.EXE@5e1a | 26/30 | no |
| CLIBC | STRCPY | disk1/WDISASM.EXE@76ed | 43/43 | yes |
| CLIBC | STRCMP | disk1/WDISASM.EXE@76a5 | 44/44 | yes |
| CLIBC | STRCAT | disk1/WDISASM.EXE@7434 | 51/51 | yes |
| CLIBS | MAKEPATH | disk1/WTOUCH.EXE@1538 | 131/131 | yes |
| CLIBS | SETVBUF | disk3/WCPP386.EXE@56b6 | 51/55 | no |

The programs, by SHA-256 of the extracted file: `disk1/WDISASM.EXE`
`e1977f0dec244b9522bc8d5b87e285afa40e81a8cb80e4f572cb586d49310559`,
`disk3/WCPP386.EXE`
`d17aaffafa72839df37e3c042e502bfd1d350c39c7d45146aab22f38dccdcc5b`,
`disk1/WTOUCH.EXE`
`1cd52f528c14830a34b08e21c61603f9fcf00a570f5fde2ae87d3d7364c2f69d`.
The seven compact modules compare 288 of their 302 code bytes, and four
occur whole, fixup fields included.  At each of the nine places the
same-named module of the other four libraries (small or compact, medium,
large, huge) does not match, so each match identifies the model.  The
small STRLEN, STRCPY, STRCMP and STRCAT occur nowhere in WDISASM.EXE:
WDISASM is a compact-model program, and these are the first witnesses
specific to compact code.  Two checks go past the masked bytes.
UNLINK's one call (opcode at WDISASM 0x7392) reaches 0x6e27, DOSRET's
start 0x6e18 plus 0xf, the offset of `_set_errno_` in the rebuilt
compact DOSRET.  Compact STRERROR's two masked operands, at +21 and +26,
load the two words of a far pointer from a table at WDISASM 0x8f7a (its
data segment found through the MZ relocations); all 16 far pointers of
the table have loader relocations, and the 16 messages they reach equal,
by index, the strings of the rebuilt compact STRERROR's data segment.

These programs witness a later build of the run-time, not the 6.5
libraries, so they are weaker evidence than a 6.5 program.  Their counts
are kept apart from the 6.5 results (59 small, 6 compact), and they
change no grade: a matching witness never raises one (below).

The shipped programs are witnesses to the builds they were linked from,
not to the library on the disks, and they disagree among themselves.
Small GETCTIME is found in WMAKE.EXE, INSTALL.EXE and WCPP.EXE, and the
matched small TIME in each calls it there; the GETCTIME that WTOUCH.EXE's
TIME calls (the TIME itself matches) lacks one five-byte store, `C7 47 10
FF FF` (-1 to `tm_isdst`), and is otherwise identical: the module is
noted `witness-mixed:DISK3/WTOUCH.EXE@14b9`.  Small ISATTY, 28 code bytes
with no fixup fields, occurs whole in INSTALL.EXE, WCL.EXE, WCPP.EXE,
EXE2COM.COM, WLIB.EXE and WMAKE.EXE, and the surviving small `cmain`
calls it in five of them; the same `cmain` in WSTRIP.EXE and WTOUCH.EXE
calls a 25-byte routine instead, identical in both, which loads AH and AL
separately, saves no CX and has no `sbb cx,cx`, but tests the same bit
of DX after the same IOCTL 4400h call.  Compact ISATTY has the same 28
bytes, so both ISATTY rows are noted
`witness-mixed:DISK3/WSTRIP.EXE@1309` and
`witness-mixed:DISK3/WTOUCH.EXE@14a0`.  And the REALLOC that WMAKE.EXE's
PUTENV calls has the same instructions as the rebuilt small REALLOC with
the other sizes for its two jumps to the shared exit (section 7.3): the
rebuilt module is noted `witness-differs:DISK3/WMAKE.EXE@5448` in the
provenance and graded low.  The alternative was not adopted: the jump
rule was tested on the surviving modules, so the rebuild has evidence of
its own here (see below), and the two sizes change nothing in what the
code does.  The `sprintf` that INSTALL.EXE and WCPP.EXE link keeps its
destination in SI where the rebuilt small SPRINTF reloads it from the
stack (section 9): that module is noted
`witness-differs:DISK1/INSTALL.EXE@2b1e` and graded low, and its bytes
stay, since the source compiled with `/os` reproduces the intact medium
and large SPRINTF and the switches that give the witnessed bytes do not.
The rule: when the programs disagree about a module and at least one of
them holds the rebuilt code (all literal bytes, as the tool finds it),
the disagreement is between the builds they were linked from, not
evidence against the rebuilt bytes; the grade stands and each differing
routine is recorded as `witness-mixed:FILE@hex` (ISATTY, GETCTIME).  When
no program holds the rebuilt code and one holds another form, the module
is noted `witness-differs:FILE@hex` and graded low (REALLOC, SPRINTF).

This corroborates the instruction bytes of those modules only: not their
fixup fields, their data segments, their record layout and other
object-file metadata, or where their relocations point.  The data
segments that the matched code reaches through DGROUP were compared too,
and differ from the rebuilt ones only in the alignment bytes of section
7.4.  The modules therefore stay classified `inferred`, and their
confidence is not raised (it is lowered where a witness contradicts the
result and no program holds the rebuilt code).  The tool's output is a
ledger, not an input to the rebuild, with two kinds of exception: where
a reconstruction had to choose with no evidence of its own, the shipped
code decides (SETJMP's near-code list, and the alignment bytes of
section 7.4, decision 6).  Where the reconstruction has evidence of its
own, a rule tested on the survivors or switches that reproduce the
intact medium and large objects, a contradicting program lowers the
grade and is recorded when no program holds the rebuilt code, and the
bytes stay (REALLOC and SPRINTF); when another program does hold it, the
module is noted `witness-mixed` and the grade stands (ISATTY, GETCTIME).
