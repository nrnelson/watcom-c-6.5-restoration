# recompile/

C sources reconstructed for the Watcom C 6.5 library restoration, compiled
by Watcom C 6.5 itself through `tools/recompile.py` (METHOD.md, section 9).
They were written by reading the CLIBM and CLIBL machine code; they are not
Watcom's sources.

| file | role |
|---|---|
| `PRINTF.c` | validation case: reproduces CLIBM, CLIBL and CLIBH and the surviving CLIBS and CLIBC modules byte for byte.  The surviving small and compact modules are kept, so its objects are not used in the libraries. |
| `SPRINTF.c` | supplies the rebuilt small and compact SPRINTF. |
| `SETJMP.py` | supplies the rebuilt small and compact SETJMP.  It generates the C source at build time: the far-model bodies are read from your own CLIBM and CLIBL modules, the near-code variants are explicit edits of them (inferred; METHOD.md, decision 4). |
| `SIGNAL.c` | supplies the rebuilt small and compact SIGNAL, accepted near-exact (METHOD.md, decision 2). |
| `SIGNAL.accept` | why SIGNAL is accepted, its confidence (first line), and the SHA-256 of all five objects the source must give for the acceptance to hold. |
| `FMALLOC.c`, `SPAWNVE.c` | attempts that came close but were not reproduced; not used. |

Each `NAME.opt` holds the compiler switches (besides the memory model)
that make 6.5 reproduce the module.  They record what works, not the
build line Watcom used, which is unknown.
