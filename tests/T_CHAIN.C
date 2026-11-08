/* T_CHAIN - _chain_intr, _dos_getvect and _dos_setvect.

   Two interrupt handlers on INT 60h (the vector is saved and restored
   around the test).  second counts its calls and returns.  first counts
   its calls and chains with _chain_intr to second, read back with
   _dos_getvect after second was installed.  _chain_intr must leave the
   stack as the interrupt left it and jump far to the previous handler;
   if it instead returned near, it would land on second's offset in the
   current code segment with one extra word on the stack, and second's
   IRET would pop garbage.

   The check calibrates itself: sp0 is SP just before INT 60h is raised.
   second is first installed directly and records how far below sp0 its
   own SP is (delta_direct); then first is installed and second, reached
   through _chain_intr, measures the same (delta_chain).  The two must be
   equal; when they are not, second does not return (the stack is wrong)
   but restores the vector and ends the program with exit status 7.  No
   addresses or deltas are printed, only counts and the comparisons.

   There is no tiny-model build: a 6.5 interrupt function loads DS with
   the segment of DGROUP, a relocation EXE2COM refuses. */
#include <stdio.h>
#include <stdlib.h>
#include <dos.h>

typedef void (interrupt far *isr)( void );

extern unsigned get_sp( void );
#pragma aux get_sp = 0x8B 0xC4 value [ax];
extern void trigger( void );
#pragma aux trigger = 0xCD 0x60;

static isr          saved, previous;
static unsigned     sp0, delta_direct, delta_chain;
static volatile int count_first, count_second, chained;

static void interrupt far second( void )
{
    ++count_second;
    if( !chained ) {
        delta_direct = sp0 - get_sp();
    } else {
        delta_chain = sp0 - get_sp();
        if( delta_chain != delta_direct ) {
            _dos_setvect( 0x60, saved );
            _exit( 7 );
        }
    }
}

static void interrupt far first( void )
{
    ++count_first;
    _chain_intr( previous );
}

int main( void )
{
    saved = _dos_getvect( 0x60 );

    _dos_setvect( 0x60, second );
    previous = _dos_getvect( 0x60 );
    printf( "getvect gives the handler set: %d\n", previous == second );
    sp0 = get_sp();
    trigger();
    printf( "direct: first=%d second=%d\n", count_first, count_second );

    _dos_setvect( 0x60, first );
    chained = 1;
    sp0 = get_sp();
    trigger();
    printf( "chained: first=%d second=%d\n", count_first, count_second );

    _dos_setvect( 0x60, saved );
    printf( "vector restored: %d\n", _dos_getvect( 0x60 ) == saved );
    if( count_first == 1 && count_second == 2 &&
        delta_chain == delta_direct ) {
        printf( "chain ok\n" );
        return( 0 );
    }
    printf( "chain WRONG\n" );
    return( 1 );
}
