/* PRINTF - reconstructed for the Watcom C 6.5 library restoration.
   Written to reproduce the CLIBM/CLIBL module PRINTF exactly; not
   Watcom's source. */
#include <stdio.h>
#include <stdarg.h>

struct specs {
    FILE        *fp;
    int         pad1, pad2, pad3;
    int         output_count;
};

extern int _prtf( FILE *fp, const char *format, va_list args,
                  void (*out_putc)( struct specs *, int ) );
extern void _ioalloc( FILE *fp );

#if defined(M_I86SM)
 #define _vfprintf vfprintf
#else
 static int near _vfprintf( FILE *fp, const char *format, va_list args );
#endif

int printf( const char *format, ... )
{
    va_list     args;

    va_start( args, format );
    return( _vfprintf( stdout, format, args ) );
}

int fprintf( FILE *fp, const char *format, ... )
{
    va_list     args;

    va_start( args, format );
    return( _vfprintf( fp, format, args ) );
}

int vprintf( const char *format, va_list args )
{
    return( _vfprintf( stdout, format, args ) );
}

#if !defined(M_I86SM)
int vfprintf( FILE *fp, const char *format, va_list args )
{
    return( _vfprintf( fp, format, args ) );
}
#endif

static void file_putc( struct specs *specs, int op_char )
{
    fputc( op_char, specs->fp );
    specs->output_count++;
}

#if !defined(M_I86SM)
static int near _vfprintf( FILE *fp, const char *format, va_list args )
#else
int vfprintf( FILE *fp, const char *format, va_list args )
#endif
{
    int         not_buffered;
    int         len;

    if( fp->_base == NULL ) {
        _ioalloc( fp );
    }
    not_buffered = 0;
    if( fp->_flag & _IONBF ) {
        not_buffered = 1;
        fp->_flag &= ~_IONBF;
        fp->_flag |= _IOFBF;
    }
    len = _prtf( fp, format, args, file_putc );
    if( not_buffered ) {
        fp->_flag &= ~_IOFBF;
        fp->_flag |= _IONBF;
        fflush( fp );
    }
    return( len );
}
