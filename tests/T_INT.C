/* T_INT - the interrupt wrappers int86, int86x, intdos, intdosx and intr.

   For each: a DOS call that fails (INT 21h function 3Eh, close handle
   FFFFh: AX=6, carry set, return value 6 -- what the intact medium and
   large libraries give), a call that succeeds (close a real handle: carry
   clear, return value equal to AX), and INT 21h function 30h (DOS
   version).  The x variants and intr also report whether the segment
   registers came back as segread() gave them; intr returns nothing, so its
   rc is printed as 0 and its carry is the low bit of the returned flags.
   Every register is printed; the exit status is 1 when a promised value is
   wrong.

   intr calls _DoINTR_ (module DOINTR), which keeps 12 bytes of scratch at
   offsets 00A6h-00B1h of its own code and addresses them CS-relative.  If
   DOINTR is not in the caller's code segment in small code, CS is the
   caller's and those stores land at CS:00A6h-00B1h of the caller: code of
   this test (its object is the first file WLINK places in _TEXT, so
   DOINTR is never at offset 0), or the PSP command tail in a tiny-model
   .COM.  So the 12 bytes there are saved and filled with 90h around the
   failing intr call, the count of bytes that are no longer 90h is
   printed (it must be 0), and the saved bytes are put back.  t_int_pad,
   the first function in this file, is 192 bytes of NOPs that never run:
   in small and compact it holds CS:00A6h-00B1h, so stray stores there do
   not hit code that is still to run. */
#include <stdio.h>
#include <string.h>
#include <dos.h>
#include <io.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>

/* first in the file, never called: _TEXT:0000h-00BFh in small and
   compact */
extern void nop16( void );
#pragma aux nop16 = 0x90 0x90 0x90 0x90 0x90 0x90 0x90 0x90 \
                    0x90 0x90 0x90 0x90 0x90 0x90 0x90 0x90;

void t_int_pad( void )
{
    nop16(); nop16(); nop16(); nop16(); nop16(); nop16();
    nop16(); nop16(); nop16(); nop16(); nop16(); nop16();
}

#define APIS 5
static char *api_name[APIS] = { "int86", "int86x", "intdos", "intdosx",
                                "intr" };
static int fails;

extern unsigned get_cs( void );
#pragma aux get_cs = 0x8C 0xC8 value [ax];

/* intr with the registers of a union REGS: the result copied back the
   same way the other wrappers give it */
static int call_intr( union REGS *in, union REGS *out, int *segok )
{
    union REGPACK   r;
    struct SREGS    sr;

    memset( &r, 0, sizeof( r ) );
    segread( &sr );
    r.x.ax = in->x.ax;
    r.x.bx = in->x.bx;
    r.x.cx = in->x.cx;
    r.x.dx = in->x.dx;
    r.x.si = in->x.si;
    r.x.di = in->x.di;
    r.x.ds = sr.ds;
    r.x.es = sr.es;
    intr( 0x21, &r );
    *segok = ( r.x.ds == sr.ds && r.x.es == sr.es );
    out->x.ax = r.x.ax;
    out->x.bx = r.x.bx;
    out->x.cx = r.x.cx;
    out->x.dx = r.x.dx;
    out->x.si = r.x.si;
    out->x.di = r.x.di;
    out->x.cflag = r.x.flags & 1;
    return( 0 );
}

static void init( union REGS *r, unsigned ax, unsigned bx )
{
    memset( r, 0, sizeof( *r ) );
    r->x.ax = ax;
    r->x.bx = bx;
    r->x.cx = 0;
    r->x.dx = 0;
    r->x.si = 0;
    r->x.di = 0;
    r->x.cflag = 0;
}

static int call( int api, union REGS *in, union REGS *out, int *segok )
{
    struct SREGS sr, before;
    int rc;

    *segok = -1;
    switch( api ) {
    case 0:
        return( int86( 0x21, in, out ) );
    case 1:
        segread( &sr );
        before = sr;
        rc = int86x( 0x21, in, out, &sr );
        *segok = ( sr.ds == before.ds && sr.es == before.es );
        return( rc );
    case 2:
        return( intdos( in, out ) );
    case 4:
        return( call_intr( in, out, segok ) );
    default:
        segread( &sr );
        before = sr;
        rc = intdosx( in, out, &sr );
        *segok = ( sr.ds == before.ds && sr.es == before.es );
        return( rc );
    }
}

static void dump( char *what, int api, int rc, union REGS *o, int segok )
{
    printf( "%s %s: rc=%d cflag=%u ax=%u bx=%u cx=%u dx=%u si=%u di=%u",
            api_name[api], what, rc, o->x.cflag, o->x.ax, o->x.bx, o->x.cx,
            o->x.dx, o->x.si, o->x.di );
    if( segok >= 0 ) {
        printf( " sregs-unchanged=%d", segok );
    }
    printf( "\n" );
}

static void check( char *what, int api, int ok )
{
    if( !ok ) {
        printf( "WRONG: %s %s\n", api_name[api], what );
        fails = 1;
    }
}

int main( void )
{
    union REGS          in, out, both;
    int                 api, rc, segok, h, i, changed;
    unsigned char far   *scratch;
    unsigned char       saved[12];

    scratch = MK_FP( get_cs(), 0xA6 );
    for( api = 0; api < APIS; api++ ) {
        /* a failing call, distinct in and out */
        init( &in, 0x3E00, 0xFFFF );
        init( &out, 0x5555, 0x5555 );
        if( api == 4 ) {
            for( i = 0; i < 12; i++ ) {
                saved[i] = scratch[i];
                scratch[i] = 0x90;
            }
        }
        rc = call( api, &in, &out, &segok );
        if( api == 4 ) {
            changed = 0;
            for( i = 0; i < 12; i++ ) {
                if( scratch[i] != 0x90 ) {
                    changed++;
                }
                scratch[i] = saved[i];
            }
        }
        dump( "bad-handle", api, rc, &out, segok );
        check( "bad-handle", api, ( api == 4 || rc == 6 ) &&
               out.x.ax == 6 && out.x.cflag != 0 );
        if( api == 4 ) {
            printf( "intr CS:00A6h-00B1h bytes changed: %d\n", changed );
            check( "scratch stores outside DOINTR", api, changed == 0 );
        }

        /* a succeeding call, the same union in and out */
        h = open( "TINT.TMP", O_RDWR | O_CREAT | O_TRUNC | O_BINARY,
                  S_IREAD | S_IWRITE );
        if( h < 0 ) {
            printf( "WRONG: cannot create TINT.TMP\n" );
            fails = 1;
        }
        init( &both, 0x3E00, h );
        rc = call( api, &both, &both, &segok );
        dump( "close", api, rc, &both, segok );
        check( "close", api, both.x.cflag == 0 &&
               ( api == 4 || rc == both.x.ax ) );
        remove( "TINT.TMP" );

        /* DOS version, distinct in and out */
        init( &in, 0x3000, 0 );
        init( &out, 0x5555, 0x5555 );
        rc = call( api, &in, &out, &segok );
        dump( "version", api, rc, &out, segok );
        printf( "%s version: %u.%u\n", api_name[api], out.h.al, out.h.ah );
    }
    printf( "%s\n", fails ? "SOME VALUES WRONG" : "all promised values right" );
    return( fails );
}
