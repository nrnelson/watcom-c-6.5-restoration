/* T_FLT - floating point formatting and scanning (MATH libraries). */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main( void )
{
    double      x, y;
    float       f;
    int         n;
    char        buf[80];

    x = 3.14159265358979;
    printf( "1 %f %e %g %.2f %10.3f|%-10.1f|\n", x, x * 1e10, x / 1000, x, x, x );
    printf( "2 %f %f %f\n", sqrt( 2.0 ), sin( 0.5 ), log( 10.0 ) );
    n = sscanf( "1.5 -2.25e3 7", "%lf %lf %f", &x, &y, &f );
    printf( "3 %d %f %f %f\n", n, x, y, f );
    printf( "4 %f %f\n", atof( "123.456" ), strtod( "-0.001e2xyz", NULL ) );
    sprintf( buf, "%.10g", 1.0 / 3.0 );
    printf( "5 %s %d\n", buf, (int)floor( -2.5 ) );
    return( 0 );
}
