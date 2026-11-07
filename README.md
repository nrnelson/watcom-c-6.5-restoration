# Watcom C 6.5 run-time library restoration

Watcom C 6.5, released in 1988, is, as far as I have been able to find,
the earliest version of the Watcom C compiler that still survives.  The
only copy of it I could find is damaged: its small-model and compact-model
run-time libraries, `CLIBS.LIB` and `CLIBC.LIB`, have each lost more than
half of their contents.  Without them the compiler can only build medium,
large and huge model programs.  The compiler itself (its programs, headers
and other libraries) survived intact; what this project rebuilds is those
two run-time libraries, so its outputs are reconstructed substitutes for
two damaged files.  Another copy may well exist somewhere (see
[below](#looking-for-another-copy)); until one turns up, this restoration
is the way to make the compiler whole again.

This repository rebuilds the two libraries from what survives, documents
every step, and lets anyone repeat the restoration from the original
archive with one command, on Linux or Windows.

**The restored libraries are reconstructions, not the originals.**
Without an undamaged copy of the files, or a checksum of them, the result
cannot be proven identical to what Watcom shipped.  Everything that survived is kept
byte for byte; everything rebuilt is labelled, module by module, with how
it was made and how confident the reconstruction is.


## Why this matters

Watcom grew out of the University of Waterloo, and its C compiler became one of the most
respected optimising compilers of the DOS era.  Its code generator shaped
a generation of PC software, its descendants were used to build classics
such as *DOOM*, and its source was eventually released as Open Watcom,
which is still maintained today.  Version 6.5 is, as far as I can tell,
where the surviving record of that line begins: I have not been able to
find a copy of 6.0 or anything earlier, though that does not mean none
exists.

Software from this period disappears quietly.  Floppy disks fail, hard
disks are thrown away, companies change hands, and the people who wrote
the code retire.  When the last copy of a program is damaged, the damage
becomes the history unless someone repairs it.  A compiler is a
particularly important thing to keep working: it is the key to the
software written with it, to the documentation and articles that describe
it, and to understanding how programmers of the time actually worked.

The surviving copy of Watcom C 6.5 sits in the public
[Watcom C/C++ Compilers collection](https://archive.org/details/watcom-c-cpp-compilers-collection)
on the Internet Archive, the only copy I could find.  Anyone who
downloads it today gets a compiler
that cannot build small or compact model programs (the small model was
the one most DOS programs of the time used), and that fails in confusing
ways if they try.
This project exists so that the compiler can be used again as it was
meant to be, and so that the method, the evidence and its limits are on
record for anyone who comes later.


## What was wrong with the surviving copy

The archive holds the eight distribution disks of Watcom C 6.5 as plain
files (DISK1-DISK8), dated 31 May 1988.  Every file checks out except two:

| library | model | state in the archive |
|---|---|---|
| `CLIBS.LIB` | small (near code, near data) | 96 of 188 sectors foreign, 141 of 250 modules lost |
| `CLIBC.LIB` | compact (near code, far data) | 101 of 198 sectors foreign, 146 of 250 modules lost |
| `CLIBM.LIB`, `CLIBL.LIB`, `CLIBH.LIB` | medium, large, huge | intact |

What can be observed: whole 512-byte sectors of the two files hold other
files' data instead: pieces of `WDISASM.EXE`, `WMAKE.EXE`, `WLINK.EXE`,
`WVIDEO.HLP`, `MATHM.LIB` and `CLIBM.LIB`, mostly at the same offsets those
files have themselves.  Of the 96 foreign sectors of `CLIBS.LIB`, 93 match
other files' bytes; the other 3 are lone sectors between foreign runs that
match nothing and were classified as foreign by inspection (METHOD.md,
section 4).  How it happened is a hypothesis, not evidence: it looks as if
the copy was made from a hard disk with unreadable sectors, where the
copying tool left whatever it had read before.  The sector pattern is the
evidence.  The true bytes of those sectors are gone; a checksum can show a
record is bad, but cannot bring back its content.  Three further bytes in
otherwise good sectors are corrupted by bit errors.

What did survive is still a great deal: each library's dictionary is
intact (so the name, position and size of every lost module is known),
106 and 102 modules survive whole, and the medium, large and huge
libraries, built from the same sources, are complete.

### Looking for another copy

Before starting, I looked for another copy, without success:

- The Internet Archive collection above holds only this one copy of 6.5;
  its "7.0" is WATCOM C 386 7.0, the 32-bit protected-mode edition, which
  has no 16-bit libraries at all.
- Later versions (8.x to 11.0) have a different code generator and
  run-time library, so they cannot supply 6.5's bytes.
- The WATCOM Express C library shipped with 6.5 (`WCEXPL.LIB`) has 591
  modules.  241 of the 250 medium-library modules appear in it byte for
  byte; 7 medium modules are absent by name (WRITE, READ, QREAD, MIN, MAX,
  SIGNAL, FTOSX) and 2 same-named ones differ (GETCTIME, D2TTIME).  No
  Express module carries the compiler's `_small_code_` marker, and of the
  35 modules whose code segment is named `_TEXT`, 28 are byte-identical to
  CLIBM's assembler modules of the same name and the other 7 are 8087 math
  modules (ATAN87, EXP87, LOG87, SIN87, SQRT87, TAN87, I64TOS).  The search
  found no small-model donor in Express.
- I could not find any copy of 6.0 or earlier either.

That is the limit of my search, not proof that nothing else survives.
Copies of software like this turn up in attics, old office storage and
private collections, and there may well be another 6.5, or a 6.0,
somewhere.  If you have original Watcom C disks, or a copy of `CLIBS.LIB`
or `CLIBC.LIB` from them, please get in touch: a genuine copy would let
every reconstructed module here be checked, and would itself be worth
preserving.


## How the libraries were rebuilt

In short (the full account, with the evidence for every rule, the
decisions taken and the hypotheses that failed, is in
[METHOD.md](METHOD.md)):

1. **Map the damage** sector by sector, and find which modules survive
   whole, in part, or not at all.
2. **Learn exactly how the libraries were built**, by compiling small test
   programs with Watcom C 6.5 itself (it is intact) in every memory model.
3. **Convert**: a small-model module differs from its medium-model twin
   only in how code is addressed (near instead of far), and a compact one
   from its large twin the same way.  A converter turns medium and large
   modules into small and compact ones: calls, returns, stack frames,
   jumps, relocations, and the exact way the compiler splits and orders
   its object records, all recovered from the surviving modules.
4. **Recompile** where conversion is not enough (modules that handle
   pointers to functions): C source was reconstructed by reading the
   machine code, until Watcom C 6.5 compiled it to exactly the bytes of the
   intact medium and large libraries; the same source is then compiled for
   small and compact.
5. **Assemble** both libraries with every module at its original position,
   filling exactly its original space, matching every surviving byte, and
   naming exactly the symbols the original dictionary lists.
6. **Test** real programs built in all four models and compare their
   output.

Every rule was tested on the modules that survived before it was used on
the ones that were lost.


## Results

| | CLIBS.LIB (small) | CLIBC.LIB (compact) |
|---|---|---|
| original modules, kept byte for byte | 106 (+1 repaired) | 102 |
| rebuilt and matching every surviving byte of a partly damaged module | 2 | 2 |
| rebuilt with nothing left to check against | 141 | 146 |

- **Measured on the survivors**: the converter reproduces 97 of 106 small
  and 93 of 102 compact modules byte for byte, every record; the cross
  route (taking the other damaged library's module where the medium and
  large modules are identical) is exact in 30 of 30 surviving pairs (the
  same 30 pairs in both directions); the recompile route reproduces the
  one module it was tested on (PRINTF) in all five libraries, including
  the surviving small and compact ones.  These rules were developed on
  those same modules, so the scores are optimistic for the lost ones.
- **Preserved**: 106 small modules (and TELL, after a one-bit repair) and
  102 compact modules are kept byte for byte, and every surviving byte of
  the four partly damaged modules is matched.
- **The strongest constraint**: the partly surviving compact `SCNF`
  module, 3088 of its 3424 bytes intact, is matched exactly by the rebuilt
  one (three converter rules were found on it, so it is a constraint, not
  an independent prediction).
- **Tests**: both restored libraries pass a strict check of every module
  and record, link with Watcom's own linker, and six test programs
  (strings, stdio, floating point, files, directories, time, setjmp,
  signals, three kinds of heap, environment, spawn and exec, and the DOS
  interrupt wrappers) build in all four memory models, exit with the
  expected status and give the same output.
- How many of the lost modules are byte-identical to the originals cannot
  be measured; METHOD.md, section 14, gives my estimate and its
  arithmetic, which is a judgment, not a measurement.

`PROVENANCE.csv` lists every module of both libraries: whether it is
original or rebuilt, how, with what confidence, and anything unusual the
tools noted about it.


## Restoring the libraries yourself

The repository contains no Watcom files.  You need the original archive,
Python and DOSBox-X; the script does the rest.  Nothing outside the
repository folder is written.

### 1. Get the original archive

Download **`Watcom C.ver.6.5.English.zip`** from the Internet Archive:

- collection page: <https://archive.org/details/watcom-c-cpp-compilers-collection>
- direct download:
  <https://archive.org/download/watcom-c-cpp-compilers-collection/watcom-6.5/Watcom%20C.ver.6.5.English.zip>

and put it in the repository folder (or give its path to the script).  It
must be exactly this file; the script checks it:

| | |
|---|---|
| size | 1,286,189 bytes |
| SHA-256 | `76b2ebc8ec730ee1151b1c1f9193460b8cfc03dacec5d567573296f3a537eca6` |
| SHA-1 | `dc1547755776922145461010f99077fdcc35f770` |
| MD5 | `0ee269bc6e38a1ca2a3aab7ec9b9bf0d` |

### 2. Install the requirements

- **Python 3.8 or later.**
- **DOSBox-X** (any recent version).  It runs Watcom C 6.5's own compiler
  and linker, which are DOS programs.

Tested on Linux (Python 3.13, DOSBox-X 2025.02.01) and Windows (Python
3.12, DOSBox-X 2026.10.01): the same result, byte for byte, on both.

**Linux** (Debian/Ubuntu shown; use your distribution's packages or the
DOSBox-X Flatpak):

```
sudo apt install python3 dosbox-x
```

**Windows**: install Python from <https://www.python.org/downloads/>
(tick "Add python.exe to PATH"), and DOSBox-X from
<https://dosbox-x.com/> (the installer, or the portable zip).  The script
finds DOSBox-X on the PATH or in `C:\DOSBox-X` and `C:\Program Files\DOSBox-X`;
anywhere else, tell it where (Command Prompt, then PowerShell):

```
set WCR_DOSBOX=D:\Tools\DOSBox-X\dosbox-x.exe
```

```
$env:WCR_DOSBOX = 'D:\Tools\DOSBox-X\dosbox-x.exe'
```

**macOS**: Python from python.org or Homebrew, DOSBox-X from
<https://dosbox-x.com/>; set `WCR_DOSBOX` to the `dosbox-x` binary inside
the app bundle if it is not on the PATH.

### 3. Run the restoration

Linux and macOS:

```
git clone https://github.com/nrnelson/watcom-c-6.5-restoration.git
cd watcom-c-6.5-restoration
cp ~/Downloads/"Watcom C.ver.6.5.English.zip" .
python3 restore.py
```

Windows, Command Prompt:

```
git clone https://github.com/nrnelson/watcom-c-6.5-restoration.git
cd watcom-c-6.5-restoration
copy "%USERPROFILE%\Downloads\Watcom C.ver.6.5.English.zip" .
py restore.py
```

Windows, PowerShell:

```
git clone https://github.com/nrnelson/watcom-c-6.5-restoration.git
cd watcom-c-6.5-restoration
Copy-Item -LiteralPath "$env:USERPROFILE\Downloads\Watcom C.ver.6.5.English.zip" -Destination .
py restore.py
```

(Without git, download the repository as a zip from GitHub's green
**Code** button and unpack it.)

It takes about a minute.  It checks the archive, installs Watcom C 6.5 into
`build/watcom` the way its own installer would, compiles the four
reconstructed modules with Watcom C 6.5 in DOSBox-X (no window opens),
rebuilds both libraries into `out/`, checks every module and record, and
compares the result with the published restoration.  It ends with:

```
out/CLIBS.LIB: 250 modules ok
  SHA-256 95100563d6885e7f0eba7c1a96aa0587bdf2fbe9ef8bfbaf73a367f85216b8c0: identical to the published restoration
out/CLIBC.LIB: 250 modules ok
  SHA-256 69e6fe1e9b4e0f2b50e047c24c2678fe564c773ead325356376ddce794d9d58b: identical to the published restoration
```

The process is deterministic: the same archive gives the same bytes on
every machine.  Add `--test` to also build and run the test programs in
all four memory models (a few more minutes).  Any failed check makes the
script end with "with problems" and exit status 1.

Two more environment variables: `WCR_ZIP` gives the archive's path, and
`WCR_BUILD` moves the `build/` work folder elsewhere.  The tools delete
and recreate their own subfolders of `build/` (`build/watcom`,
`build/objects`, `build/recompile`, `build/difftest`,
`build/watcom-restored`) on each run, so do not keep anything of your own
there.

### 4. Use them

`out/CLIBS.LIB` and `out/CLIBC.LIB` replace the damaged files in the `LIB`
directory of a Watcom C 6.5 installation (in DOS, an emulator, or a
virtual machine).  The script can do it:

```
python3 restore.py --install /path/to/WATCOM/LIB
```

It installs only when every check of the run passed (with `--test`, the
tests too), and only into a directory that already holds `CLIBS.LIB` and
`CLIBC.LIB`.  The libraries found there are first copied to `CLIBS.BAD`
and `CLIBC.BAD`, unless those files already exist: an existing `.BAD` is
kept as it is, and is not checked, so after a second install it still
holds the libraries from before the first.  Both new libraries are written
beside the old ones and then moved into place; if moving the second
fails, the first is put back, so the directory does not end up with one
new and one old library.  (That covers an error reported during the
install, not a crash or power loss between the two moves.)

`build/watcom` is Watcom C 6.5 as the archive's `INSTALL.SCR` copies it
(BIN, H, LIB, SRC, README.1ST), **with the damaged libraries still in
place**; the installer does not generate the files `INSTALL.SCR` would
also write (NEWCONF.SYS, NEWAUTO.BAT, DEMO.BAT, GRDEMO.BAT, DEMOEXP.BAT).
`build/watcom-restored`, made by `--test` or by
`python3 -I tools/install.py --restored`, is the same tree with the
restored libraries in place, ready to use if you have no installation of
your own.


## What is in this repository

| | |
|---|---|
| `restore.py` | the whole restoration in one command |
| `tools/` | the tools it uses, each runnable alone (listed in METHOD.md) |
| `recompile/` | the reconstructed C sources and their compiler switches |
| `tests/` | the test programs |
| `METHOD.md` | the complete method: every rule, its evidence, every decision |
| `PROVENANCE.csv` | the result for every module of both libraries |

Made when you run it, and not committed: `build/` (the installed compiler
and work files) and `out/` (the restored libraries).

`PROVENANCE.csv` fields:

| field | meaning |
|---|---|
| `lib` | CLIBS or CLIBC |
| `index` | the module's position in the library, 0-249 |
| `module` | the module name as the library's dictionary spells it |
| `offset` | file offset of the module's first page |
| `span` | the page span allocated to the module, in bytes; the original object's length is known only to within 16 bytes |
| `genuine_bytes` | bytes of the span outside foreign sectors, padding included; repaired bytes count as genuine |
| `status` | `original` (survives whole), `original-repaired` (whole after a repair), `anchored` (rebuilt, matching surviving bytes in its span), `inferred` (rebuilt, nothing in its span survives), `FAILED` (no route fitted) |
| `route` | how a rebuilt module was made: `recompile`, `unchanged`, `cross` or `convert` (METHOD.md, section 10) |
| `confidence` | `original`, `high`, `medium` or `low` (METHOD.md, section 10) |
| `agrees` | other routes that gave the same bytes |
| `disagrees` | other routes that gave other bytes or failed the checks |
| `notes` | the converter's note classes (the `@offset` suffixes the tools print are dropped), repairs, and other remarks |


## Independent audit (November 2026)

An independent audit of the published restoration found one real defect:
in the compact library, `int86` and `int86x` reloaded their output pointer
from the wrong stack offset after the interrupt, so a failing DOS call
(carry set) was reported with carry clear and a wrong return value.  The
converter had stopped following the stack frame at the inline code that
emulates an `INT`; the rule is now general (METHOD.md, section 7.3) and
changes exactly two displacement bytes (and two record checksums) in
`CLIBC.LIB`.  The audit also found that the installer, the library checker,
the test runner and the recompile route checked less than they claimed;
all of them now enforce what this document and METHOD.md say.  The small
library is unchanged.

| | `CLIBC.LIB` SHA-256 |
|---|---|
| before the audit (pre-fix) | `b53e05b77252a952e0896abc3612846bae2a10f4c584d1fa682e752b6e24bcae` |
| now | `69e6fe1e9b4e0f2b50e047c24c2678fe564c773ead325356376ddce794d9d58b` |

`CLIBS.LIB` remains
`95100563d6885e7f0eba7c1a96aa0587bdf2fbe9ef8bfbaf73a367f85216b8c0`.  If you
installed the earlier `CLIBC.LIB`, run the restoration again and reinstall
it.


## Limits

- For 141 small and 146 compact modules nothing survives to check the
  reconstruction against.  On surviving modules the methods are about 91%
  exact (conversion) and exact in every tested case (recompilation and the
  small/compact cross check); the kinds of module where they are weakest
  are known and marked low in `PROVENANCE.csv`.
- A few decisions had to be made where the evidence ran out; each is
  explained in METHOD.md, section 11, with its alternative.
- Some original sources contained small-model-only code that no other
  library can reveal; for lost modules such differences cannot be seen.


## Rights

Watcom C is a product of Watcom Systems Inc.; its rights passed to Sybase
and then SAP.  This repository contains none of Watcom's files or code:
the tools read your own copy of the archive, and the restored libraries
are produced on your machine.  The restored libraries are derived from
Watcom's and remain subject to Watcom's (now SAP's) rights; they are not
distributed here.  The tools, tests, documentation and reconstructed
sources are © 2026 Nathan Nelson, released under the MIT licence
(`LICENSE`); the licence covers only that work, not Watcom's.

Open Watcom (<https://github.com/open-watcom/open-watcom-v2>) is the open
source descendant of Watcom C/C++ and is unrelated to this work.
