/* SIGNAL - reconstructed for the Watcom C 6.5 library restoration.
   Written to reproduce the CLIBM/CLIBL module SIGNAL; not Watcom's
   source. */
#include <stdio.h>
#include <signal.h>
#include <errno.h>
#include <dos.h>

typedef void (*sig_fn)( int );
typedef void (interrupt far *int_fn)();

extern int      _child;
extern void     (*_int23_exit)( void );
extern void     _null_int23_exit( void );
extern void     _exit_with_msg( char far *msg, int rc );

extern int_fn   _getvect23( void );
#pragma aux _getvect23 = 0xb0 0x23      /* mov al,23h */\
                         0xb4 0x35      /* mov ah,35h */\
                         0xcd 0x21      /* int 21h */\
                         value [es bx];
extern void     _setvect23( int_fn handler );
#pragma aux _setvect23 = 0xb0 0x23      /* mov al,23h */\
                         0x1e           /* push ds */\
                         0x8e 0xd9      /* mov ds,cx */\
                         0xb4 0x25      /* mov ah,25h */\
                         0xcd 0x21      /* int 21h */\
                         0x1f           /* pop ds */\
                         parm [cx dx] modify [ax];

sig_fn SignalTable[7] = {
    SIG_IGN, SIG_DFL, SIG_IGN, SIG_IGN, SIG_IGN, SIG_IGN, SIG_IGN
};
int_fn _old_int23;

int __raise( int sig );
#pragma aux __raise "*";

void interrupt far _int23_handler( void )
{
    if( _child == 0 ) {
        _enable();
        __raise( SIGINT );
    } else {
        _chain_intr( _old_int23 );
    }
}

void _int23_exit_rtn( void )
{
    _setvect23( _old_int23 );
    _old_int23 = 0;
    _int23_exit = _null_int23_exit;
}

sig_fn signal( int sig, sig_fn func )
{
    sig_fn      prev;

    if( sig > SIGTERM ) {
        errno = EINVAL;
        return( SIG_ERR );
    }
    if( sig == SIGINT && _old_int23 == 0 ) {
        _old_int23 = _getvect23();
        _setvect23( _int23_handler );
        _int23_exit = _int23_exit_rtn;
    }
    prev = SignalTable[ sig ];
    SignalTable[ sig ] = func;
    return( prev );
}

int __raise( int sig )
{
    return( raise( sig ) );
}

int raise( int sig )
{
    sig_fn      func;

    func = SignalTable[ sig ];
    switch( sig ) {
    case SIGABRT:
        if( func == SIG_DFL ) {
            _exit_with_msg( "ABNORMAL TERMINATION\r\n", 3 );
        }
    case SIGFPE:
    case SIGILL:
    case SIGINT:
    case SIGSEGV:
    case SIGTERM:
        if( func != SIG_IGN && func != SIG_DFL && func != SIG_ERR ) {
            SignalTable[ sig ] = SIG_DFL;
            (*func)( sig );
        }
        break;
    default:
        return( -1 );
    }
    return( 0 );
}
