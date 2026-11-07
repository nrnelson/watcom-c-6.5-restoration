/* T_INT - the interrupt wrappers int86, int86x, intdos and intdosx.

   For each: a DOS call that fails (INT 21h function 3Eh, close handle
   FFFFh: AX=6, carry set, return value 6 -- what the intact medium and
   large libraries give), a call that succeeds (close a real handle: carry
   clear, return value equal to AX), and INT 21h function 30h (DOS
   version).  The x variants also report whether the segment registers in
   the SREGS came back as segread() gave them.  Every register is printed;
   the exit status is 1 when a promised value is wrong. */
#include <stdio.h>
#include <string.h>
#include <dos.h>
#include <io.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>

static char *api_name[4] = { "int86", "int86x", "intdos", "intdosx" };
static int fails;

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
    union REGS  in, out, both;
    int         api, rc, segok, h;

    for( api = 0; api < 4; api++ ) {
        /* a failing call, distinct in and out */
        init( &in, 0x3E00, 0xFFFF );
        init( &out, 0x5555, 0x5555 );
        rc = call( api, &in, &out, &segok );
        dump( "bad-handle", api, rc, &out, segok );
        check( "bad-handle", api,
               rc == 6 && out.x.ax == 6 && out.x.cflag != 0 );

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
        check( "close", api, both.x.cflag == 0 && rc == both.x.ax );
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
