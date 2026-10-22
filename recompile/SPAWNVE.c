/* SPAWNVE - reconstructed for the Watcom C 6.5 library restoration.
   Written to reproduce the CLIBM/CLIBL module SPAWNVE exactly; not
   Watcom's source. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <process.h>
#include <errno.h>
#include <malloc.h>

typedef int (far *exec_fn)( char *path, char **argv, char **envp );

extern exec_fn _execaddr( void );
extern int _cenvarg( char **argv, char **envp, char **envptr,
                     unsigned *envseg, char *cmdline, int pathsearch );
extern int cdecl _dospawn( int mode, char near *pgm, char near *cmdline,
                           unsigned envseg );
extern char _8087;

extern void _fsave( char *buf );
#pragma aux _fsave = 0x55               /* push bp */\
                     0x89 0xc5          /* mov bp,ax */\
                     0xdd 0x76 0x00     /* fnsave [bp] */\
                     0x9b 0xdd 0x66 0x00 /* frstor [bp] */\
                     0x9b               /* fwait */\
                     0x5d               /* pop bp */\
                     parm [ax];
extern void _frstor( char *buf );
#pragma aux _frstor = 0x55              /* push bp */\
                      0x89 0xc5         /* mov bp,ax */\
                      0xdd 0x66 0x00    /* frstor [bp] */\
                      0x9b              /* fwait */\
                      0x5d              /* pop bp */\
                      parm [ax];

int spawnve( int mode, char *path, char **argv, char **envp )
{
    exec_fn     func;
    char        *envptr;
    unsigned    envseg;
    char near   *name;
    char        cmdline[128];
    char        fpstate[94];
    char near   *p;
    int         rc;

    if( mode == P_OVERLAY ) {
        func = _execaddr();
        if( func != NULL ) {
            return( (*func)( path, argv, envp ) );
        }
        errno = EINVAL;
        return( -1 );
    }
    if( (unsigned)mode >= P_OVERLAY ) {
        errno = EINVAL;
        return( -1 );
    }
    if( _cenvarg( argv, envp, &envptr, &envseg, cmdline, 0 ) == -1 ) {
        return( -1 );
    }
    name = _nmalloc( strlen( path ) + 7 );
    if( name == NULL ) {
        free( envptr );
        return( -1 );
    }
    if( _8087 ) _fsave( fpstate );
    strcpy( name, path );
    p = strrchr( name, '\\' );
    if( p == NULL && name[1] != ':' ) {
        name[0] = '.';
        name[1] = '\\';
        strcpy( name + 2, path );
    }
    if( p == NULL ) p = name;
    if( strchr( p, '.' ) != NULL ) {
        rc = _dospawn( mode, name, cmdline, envseg );
    } else {
        strcat( name, ".com" );
        errno = 0;
        rc = _dospawn( mode, name, cmdline, envseg );
        if( errno == ENOENT ) {
            errno = 0;
            strcpy( strrchr( name, '.' ), ".exe" );
            rc = _dospawn( mode, name, cmdline, envseg );
        }
    }
    _nfree( name );
    free( envptr );
    if( _8087 ) _frstor( fpstate );
    return( rc );
}
