/* SPRINTF - reconstructed for the Watcom C 6.5 library restoration.
   Written to reproduce the CLIBM/CLIBL/CLIBH module SPRINTF exactly;
   not Watcom's source. */
#include <stdio.h>
#include <stdarg.h>

struct specs {
    char        *ptr;
    int         pad1, pad2, pad3;
    int         output_count;
};

extern int _prtf( char *dest, const char *format, va_list args,
                  void (*out_putc)( struct specs *, char ) );

static void mem_putc( struct specs *specs, char op_char );

int sprintf( char *dest, const char *format, ... )
{
    va_list     args;
    int         len;

    va_start( args, format );
    len = _prtf( dest, format, args, mem_putc );
    dest[len] = '\0';
    return( len );
}

int vsprintf( char *dest, const char *format, va_list args )
{
    int         len;

    len = _prtf( dest, format, args, mem_putc );
    dest[len] = '\0';
    return( len );
}

static void mem_putc( struct specs *specs, char op_char )
{
    *( specs->ptr++ ) = op_char;
    specs->output_count++;
}
