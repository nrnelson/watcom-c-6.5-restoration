"""dosrun.py - run a DOS batch file with Watcom C 6.5 in headless DOSBox-X.

    import dosrun
    dosrun.run(workdir, 'GO.BAT', timeout=300)

WORKDIR is mounted as drive C: and the batch file C:\\GO.BAT runs there,
its output going to WORKDIR/RUN.LOG.  The Watcom C 6.5 tree (build/watcom,
made by tools/install.py; another with tooldir=) is mounted as D:, with
PATH, INCLUDE and LIB set to its BIN, H and LIB.  Works on Linux, Windows
and macOS.

DOSBox-X is found as WCR_DOSBOX if set, else dosbox-x on the PATH, else in
its usual Windows install folders.
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402

CONF = """[sdl]
output=surface
autolock=false
[log]
logfile=
[dosbox]
machine=svga_s3
memsize=16
quit warning=false
[cpu]
core=dynamic
cputype=auto
cycles=max
[dos]
ver=3.10
lfn=false
[mixer]
nosound=true
[sblaster]
sbtype=none
[gus]
gus=false
[speaker]
pcspeaker=false
tandy=off
disney=false
[midi]
mpu401=none
mididevice=none
[serial]
serial1=disabled
serial2=disabled
[parallel]
parallel1=disabled
[autoexec]
mount c "{work}" -nocachedir
mount d "{tool}" -nocachedir
c:
SET PATH=Z:\\;D:\\BIN
SET INCLUDE=D:\\H
SET LIB=D:\\LIB
COMMAND /C {bat} > RUN.LOG
exit
"""

WINDOWS_PLACES = [
    r'C:\DOSBox-X\dosbox-x.exe',
    r'C:\Program Files\DOSBox-X\dosbox-x.exe',
    r'C:\Program Files (x86)\DOSBox-X\dosbox-x.exe',
]


def find_dosbox():
    exe = os.getenv('WCR_DOSBOX') or shutil.which('dosbox-x')
    if not exe and os.name == 'nt':
        exe = next((p for p in WINDOWS_PLACES if os.path.isfile(p)), None)
    if not exe:
        raise SystemExit('DOSBox-X not found: install it (README.md), or set '
                         'WCR_DOSBOX to the full path of dosbox-x')
    return exe


def run(work, bat, timeout=300, tooldir=None):
    """Run BAT in WORK; returns True if DOSBox-X ended before the timeout
    with exit status 0, False otherwise (its output is in
    WORK/DOSBOX.OUT)."""
    work = os.path.abspath(work)
    tool = os.path.abspath(tooldir or paths.WATCOM)
    if not os.path.isfile(os.path.join(tool, 'BIN', 'WCC.EXE')):
        raise SystemExit('%s has no BIN/WCC.EXE: run tools/install.py '
                         'first' % tool)
    for p in (work, tool):
        if '"' in p:
            raise SystemExit('path contains a quote: %s' % p)
    conf = os.path.join(work, 'DOSBOX.CNF')
    with open(conf, 'w') as f:
        f.write(CONF.format(work=work, tool=tool, bat=bat))
    env = dict(os.environ)
    env['SDL_VIDEODRIVER'] = 'dummy'
    env['SDL_AUDIODRIVER'] = 'dummy'
    with open(os.path.join(work, 'DOSBOX.OUT'), 'w') as out:
        try:
            res = subprocess.run([find_dosbox(), '-conf', conf, '-nogui',
                                  '-nomenu', '-exit'], stdout=out,
                                 stderr=subprocess.STDOUT, env=env,
                                 timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
    return res.returncode == 0


def log(work):
    p = os.path.join(work, 'RUN.LOG')
    return open(p, errors='replace').read() if os.path.exists(p) else ''


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write('usage: python3 -I tools/dosrun.py WORKDIR BAT '
                         '[TIMEOUT]\n')
        sys.exit(2)
    ok = run(sys.argv[1], sys.argv[2],
             int(sys.argv[3]) if len(sys.argv) > 3 else 300)
    sys.stdout.write(log(sys.argv[1]))
    sys.exit(0 if ok else 1)
