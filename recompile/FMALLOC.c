/* FMALLOC - reconstructed for the Watcom C 6.5 library restoration.
   Written to reproduce the CLIBM/CLIBL module FMALLOC exactly; not
   Watcom's source. */
#include <stddef.h>
#include <stdlib.h>
#include <malloc.h>
#include <errno.h>
#include <dos.h>

#define FRL_SIZE        10

struct freelist {
    unsigned                    len;
    struct freelist far         *prev;
    struct freelist far         *next;
};

extern void _fcoalesce( struct freelist far *p );

int _dos_setblock( unsigned seg, unsigned paras );
#pragma aux _dos_setblock = 0xb4 0x4a   /* mov ah,4ah */\
                            0xcd 0x21   /* int 21h */\
                            0x19 0xc0   /* sbb ax,ax */\
                        parm caller [es] [bx] value [ax];

struct freelist _fdynfree = { 0, &_fdynfree, &_fdynfree };
static unsigned heap_paras = 0x1001;
static unsigned heap_seg;

static int near add_mem( unsigned size, unsigned minsize )
{
    union REGS          r;
    unsigned            paras;
    unsigned            minparas;
    unsigned            len;
    unsigned char far   *p;

    paras = size >> 4;
    if( size & 0x0f ) ++paras;
    if( heap_paras + paras <= 0x1000 &&
        _dos_setblock( heap_seg, heap_paras + paras ) == 0 ) {
        p = MK_FP( heap_seg, ( ( heap_paras - 1 ) << 4 ) + 14 );
        len = paras << 4;
        *(unsigned far *)p = len | 1;
        *(unsigned far *)( p + len ) = 0xffff;
        heap_paras += paras;
        _ffree( p + 2 );
        return( 1 );
    }
    r.h.ah = 0x48;
    r.x.bx = paras;
    intdos( &r, &r );
    if( r.x.cflag ) {
        minparas = minsize >> 4;
        if( minsize & 0x0f ) ++minparas;
        paras = r.x.bx;
        if( minparas > paras ) return( 0 );
        r.h.ah = 0x48;
        intdos( &r, &r );
        if( r.x.cflag ) return( 0 );
    }
    heap_seg = r.x.ax;
    heap_paras = paras;
    p = MK_FP( r.x.ax, 0 );
    len = ( paras << 4 ) - 2;
    *(unsigned far *)p = len | 1;
    *(unsigned far *)( p + len ) = 0xffff;
    _ffree( p + 2 );
    return( 1 );
}

static int near grow_heap( unsigned size )
{
    unsigned            mask;
    unsigned            n;

    mask = 0x7fff;
    while( mask > _amblksiz ) {
        mask >>= 1;
        if( mask == 0 ) break;
    }
    for( ;; ) {
        n = size + mask;
        if( n >= size ) {
            return( add_mem( n & ~mask, size ) );
        }
        mask >>= 1;
        if( mask == 0 ) return( 0 );
    }
}

void far *_fmalloc( size_t amt )
{
    unsigned            size;
    int                 expanded;
    struct freelist far *p;
    struct freelist far *next;
    struct freelist far *prev;
    void near           *np;

    if( amt == 0 ) return( NULL );
    size = ( amt + 3 ) & ~1;
    if( size < FRL_SIZE ) size = FRL_SIZE;
    expanded = 0;
    for( ;; ) {
        for( p = _fdynfree.next; p != &_fdynfree; p = p->next ) {
            _fcoalesce( p );
            if( size <= p->len ) {
                if( p->len - size > FRL_SIZE ) {
                    p->len -= size;
                    p = (struct freelist far *)( (char far *)p + p->len );
                    p->len = size;
                } else {
                    next = p->next;
                    prev = p->prev;
                    prev->next = next;
                    next->prev = prev;
                }
                p->len |= 1;
                return( (char far *)p + 2 );
            }
        }
        if( expanded ) break;
        if( grow_heap( size + 2 ) == 0 ) break;
        expanded = 1;
    }
    np = _nmalloc( amt );
    if( np == NULL ) {
        errno = ENOMEM;
        return( NULL );
    }
    return( (void far *)np );
}

void _fcoalesce( struct freelist far *p )
{
    struct freelist far *q;
    struct freelist far *next;
    struct freelist far *prev;

    for( ;; ) {
        q = (struct freelist far *)( (char far *)p + p->len );
        if( q->len & 1 ) return;
        p->len += q->len;
        next = q->next;
        prev = q->prev;
        prev->next = next;
        next->prev = prev;
    }
}
