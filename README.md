# Watcom C 6.5 run-time library restoration

Watcom C 6.5, released in 1988, is, as far as I have been able to find,
the earliest version of the Watcom C compiler that still survives.  The
only copy of it I could find is damaged: its small-model and compact-model
run-time libraries, `CLIBS.LIB` and `CLIBC.LIB`, have each lost more than
half of their contents.  Without them the compiler can only build medium,
large and huge model programs.  Another copy may well exist somewhere (see
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
| `CLIBS.LIB` | small (near code, near data) | 96 of 188 sectors replaced, 141 of 250 modules lost |
| `CLIBC.LIB` | compact (near code, far data) | 101 of 198 sectors replaced, 146 of 250 modules lost |
| `CLIBM.LIB`, `CLIBL.LIB`, `CLIBH.LIB` | medium, large, huge | intact |

Whole 512-byte sectors of the two files hold other files' data instead:
pieces of `WDISASM.EXE`, `WMAKE.EXE`, `WLINK.EXE`, `WVIDEO.HLP`,
`MATHM.LIB` and `CLIBM.LIB`, mostly at the same offsets those files have
themselves.  It looks like the copy was made from a hard disk with
unreadable sectors, where the copying tool left whatever it had read
before.  The true bytes of those sectors are gone; a checksum can show a
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
- The WATCOM Express C library shipped with 6.5 is the medium-model
  library plus Express's own modules: no small-model code.
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

- On the modules that survived, the converter reproduces 97 of 106 small
  and 93 of 102 compact modules byte for byte, every record; the
  recompile route reproduces the one module it was tested on (PRINTF) in
  all five libraries, including the surviving small and compact ones.
- The partly surviving compact `SCNF` module, 3088 of its 3424 bytes
  intact, is matched exactly by the rebuilt one.
- Both restored libraries pass a strict check of every module and record,
  link with Watcom's own linker, and the test programs (strings, stdio,
  floating point, files, directories, time, setjmp, signals, three kinds
  of heap, environment, spawn and exec) give the same output in all four
  memory models.
- **Confidence**: an estimated 90-94% of all modules are byte-identical to
  the lost originals, and 97-98% of all bytes; the chance that either whole
  library is byte-identical is close to zero.  Behaviour is better than
  that: everything tested works as the originals do.

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
anywhere else, tell it where:

```
set WCR_DOSBOX=D:\Tools\DOSBox-X\dosbox-x.exe
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

Windows (Command Prompt or PowerShell):

```
git clone https://github.com/nrnelson/watcom-c-6.5-restoration.git
cd watcom-c-6.5-restoration
copy "%USERPROFILE%\Downloads\Watcom C.ver.6.5.English.zip" .
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
  SHA-256 b53e05b77252a952e0896abc3612846bae2a10f4c584d1fa682e752b6e24bcae: identical to the published restoration
```

The process is deterministic: the same archive gives the same bytes on
every machine.  Add `--test` to also build and run the test programs in
all four memory models (a few more minutes).

### 4. Use them

`out/CLIBS.LIB` and `out/CLIBC.LIB` replace the damaged files in the `LIB`
directory of a Watcom C 6.5 installation (in DOS, an emulator, or a
virtual machine).  The script can do it, keeping the damaged files as
`CLIBS.BAD` and `CLIBC.BAD`:

```
python3 restore.py --install /path/to/WATCOM/LIB
```

`build/watcom` is itself a complete Watcom C 6.5 installation, unpacked
from the archive, if you do not have one.


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
