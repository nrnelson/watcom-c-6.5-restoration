/* T_MISC - time, setjmp/longjmp, signal/raise, atexit, memory, env. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <setjmp.h>
#include <signal.h>
#include <malloc.h>
#include <dos.h>

static jmp_buf  env;
static int      hits;

static void bye1( void ) { printf( "atexit 1\n" ); }
static void bye2( void ) { printf( "atexit 2\n" ); }
static void onsig( int sig ) { hits += sig; }

static void deep( int n )
{
    if( n == 0 ) longjmp( env, 42 );
    deep( n - 1 );
}

int main( void )
{
    time_t      t;
    struct tm   tm, *ptm;
    char        buf[100];
    int         rc, i;
    char        *np[20];
    char far    *fp[20];
    char huge   *hp;
    union REGS  r;
    char        *p;

    t = 600000000L;
    ptm = gmtime( &t );
    printf( "1 %d-%02d-%02d %02d:%02d:%02d wd=%d yd=%d\n", ptm->tm_year + 1900, ptm->tm_mon + 1,
            ptm->tm_mday, ptm->tm_hour, ptm->tm_min, ptm->tm_sec, ptm->tm_wday, ptm->tm_yday );
    tm = *ptm;
    printf( "2 %s", asctime( &tm ) );
    strftime( buf, sizeof( buf ), "%A %B %d %Y %H:%M:%S %j %a %b", &tm );
    printf( "3 %s\n", buf );
    printf( "4 %.0f\n", difftime( t + 100, t ) );
    rc = setjmp( env );
    if( rc == 0 ) deep( 10 );
    printf( "5 setjmp=%d\n", rc );
    signal( SIGFPE, onsig ); signal( SIGTERM, onsig );
    raise( SIGFPE ); raise( SIGTERM );
    signal( SIGTERM, SIG_IGN ); raise( SIGTERM );
    printf( "6 hits=%d\n", hits );
    for( i = 0; i < 20; i++ ) { np[i] = malloc( 100 + i * 10 ); memset( np[i], i, 100 ); }
    for( i = 0; i < 20; i += 2 ) free( np[i] );
    for( i = 0; i < 20; i += 2 ) np[i] = malloc( 50 );
    rc = 0; for( i = 1; i < 20; i += 2 ) rc += np[i][50];
    printf( "7 near heap sum=%d\n", rc );
    for( i = 0; i < 20; i++ ) { fp[i] = _fmalloc( 1000 ); for( rc = 0; rc < 1000; rc++ ) fp[i][rc] = (char)i; }
    for( i = 0; i < 20; i += 3 ) _ffree( fp[i] );
    rc = 0; for( i = 1; i < 20; i += 3 ) rc += fp[i][999];
    printf( "8 far heap sum=%d\n", rc );
    hp = halloc( 3L, 30000 );
    if( hp != NULL ) { hp[70000L] = 7; printf( "9 huge=%d\n", hp[70000L] ); hfree( hp ); }
    else printf( "9 huge=none\n" );
    p = realloc( np[1], 400 );
    printf( "10 realloc=%d\n", p != NULL && p[50] == 1 );
    printf( "11 calloc zero=%d\n", ((char *)calloc( 10, 10 ))[55] == 0 );
    putenv( "WCRTEST=yes" ); printf( "12 env=%s\n", getenv( "WCRTEST" ) );
    r.h.ah = 0x30; intdos( &r, &r ); printf( "13 dos=%d\n", r.h.al >= 2 );
    atexit( bye1 ); atexit( bye2 );
    printf( "14 stackavail=%d\n", stackavail() > 512 );
    return( 0 );
}
