/* T_STR - strings, ctype, stdlib conversions, sprintf/sscanf.
   Prints deterministic results; outputs of all memory models must match. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

static int cmpint( const void *a, const void *b )
{
    return( *(int *)a - *(int *)b );
}

static char     buf[200], b2[80], *p;
static int      i, n, arr[10] = { 5, 3, 9, 1, 7, 2, 8, 6, 4, 0 }, key, *hit;
static long     l;
static unsigned long ul;
static div_t    d;
static ldiv_t   ld;

static void part1( void )
{

    strcpy( buf, "Hello" );
    strcat( buf, ", World" );
    printf( "1 %s %d\n", buf, strlen( buf ) );
    printf( "2 %d %d %d\n", strcmp( "abc", "abd" ) < 0, strncmp( "abcx", "abcy", 3 ),
            stricmp( "HeLLo", "hello" ) );
    printf( "3 %s %s\n", strchr( buf, 'o' ), strrchr( buf, 'o' ) );
    printf( "4 %s %d %d\n", strstr( buf, "Wor" ), strspn( "aabbc", "ab" ), strcspn( "xyz,abc", ",") );
    printf( "5 %s\n", strpbrk( buf, ",W" ) );
    strcpy( b2, "one two  three" );
    for( p = strtok( b2, " " ); p != NULL; p = strtok( NULL, " " ) ) printf( "6 [%s]\n", p );
    p = strdup( "MiXeD" );
    printf( "7 %s ", strupr( p ) ); printf( "%s ", strlwr( p ) ); printf( "%s\n", strrev( p ) );
    free( p );
    strcpy( b2, "abcdef" ); strset( b2, 'z' ); printf( "8 %s ", b2 );
    strcpy( b2, "abcdef" ); strnset( b2, 'y', 3 ); printf( "%s\n", b2 );
    memset( b2, 'q', 5 ); b2[5] = 0; memmove( b2 + 1, b2, 3 ); memcpy( b2 + 4, "Z", 1 );
    printf( "9 %s %d %d %s\n", b2, memcmp( "ab", "ac", 2 ) < 0, memicmp( "AB", "ab", 2 ),
            (char *)memchr( buf, 'W', 20 ) );
}

static void part2( void )
{
    printf( "10 %d %ld %ld %lu\n", atoi( "-1234" ), atol( "99999" ), strtol( "0x1fZ", &p, 16 ),
            strtoul( "777", NULL, 8 ) );
    printf( "11 %s ", itoa( -255, b2, 16 ) ); printf( "%s ", ltoa( 123456789L, b2, 10 ) );
    printf( "%s\n", ultoa( 0xFFFFFFFFUL, b2, 2 ) );
    d = div( 17, 5 ); ld = ldiv( -17L, 5L );
    printf( "12 %d %d %ld %ld %d %ld\n", d.quot, d.rem, ld.quot, ld.rem, abs( -9 ), labs( -99L ) );
    /* one bit per predicate (the is* functions return bit masks, which
       may overlap), printed for every character, 32 to a row */
    for( i = 0; i < 128; i++ ) {
        n = ( isalpha( i ) != 0 ) | ( isdigit( i ) != 0 ) << 1 |
            ( isspace( i ) != 0 ) << 2 | ( ispunct( i ) != 0 ) << 3 |
            ( isupper( i ) != 0 ) << 4 | ( islower( i ) != 0 ) << 5 |
            ( isxdigit( i ) != 0 ) << 6 | ( iscntrl( i ) != 0 ) << 7;
        sprintf( buf + ( i % 32 ) * 2, "%02X", n );
        if( i % 32 == 31 ) {
            printf( "13 %3d %s\n", i - 31, buf );
        }
    }
    printf( "13 %c %c\n", toupper( 'q' ), tolower( 'Q' ) );
    srand( 1 );
    i = rand();
    n = rand();
    key = rand();
    printf( "14 %d %d %d\n", i, n, key );
    qsort( arr, 10, sizeof( int ), cmpint );
    for( i = 0; i < 10; i++ ) printf( "%d", arr[i] );
    key = 7; hit = bsearch( &key, arr, 10, sizeof( int ), cmpint );
    printf( " 15 %d\n", hit ? *hit : -1 );
}

static void part3( void )
{
    sprintf( buf, "%5d|%-5d|%05d|%x|%X|%o|%c|%s|%10s|%-10s|%ld|%lx|%u|%%|%+d", 42, 42, 42, 255,
             255, 8, 'A', "str", "right", "left", -123456L, 0xabcdefL, 65535U, 7 );
    printf( "16 %s\n", buf );
    n = sscanf( "12 abc 0x1f 3456789", "%d %s %x %ld", &i, b2, &key, &l );
    printf( "17 %d %d %s %d %ld\n", n, i, b2, key, l );
    sprintf( buf, "%.3s|%*d|%-*d|", "truncate", 6, 9, 4, 3 );
    printf( "18 %s\n", buf );
    ul = 0; for( i = 0; i < 20; i++ ) ul = ul * 31 + (unsigned char)buf[i];
    printf( "19 %lu\n", ul );
}

int main( void )
{
    part1();
    part2();
    part3();
    return( 0 );
}
