/* T_IO - files: stdio streams, low-level io, directories. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <io.h>
#include <fcntl.h>
#include <direct.h>
#include <sys/types.h>
#include <sys/stat.h>

int main( void )
{
    FILE        *fp;
    char        buf[128];
    int         h, n, i, a1, a2;
    long        pos;
    struct stat st;

    fp = fopen( "TIO.TXT", "w" );
    if( fp == NULL ) { printf( "fopen w failed\n" ); return( 1 ); }
    for( i = 0; i < 50; i++ ) fprintf( fp, "line %d %s\n", i, "abcdefghij" );
    fputs( "last\n", fp ); fputc( 'X', fp ); fclose( fp );
    fp = fopen( "TIO.TXT", "r" );
    n = 0; while( fgets( buf, sizeof( buf ), fp ) != NULL ) n++;
    printf( "1 lines=%d last=%s\n", n, buf );
    rewind( fp ); fgets( buf, sizeof( buf ), fp ); printf( "2 %s", buf );
    fseek( fp, -7L, SEEK_END ); pos = ftell( fp ); n = fgetc( fp );
    printf( "3 pos=%ld c=%c\n", pos, n );
    ungetc( 'Q', fp ); printf( "4 %c\n", fgetc( fp ) );
    printf( "5 eof=%d err=%d\n", feof( fp ) != 0, ferror( fp ) != 0 );
    fclose( fp );
    fp = fopen( "TIO.BIN", "wb" );
    for( i = 0; i < 300; i++ ) buf[i % 128] = (char)i, fwrite( &i, sizeof( i ), 1, fp );
    fclose( fp );
    fp = fopen( "TIO.BIN", "rb" ); fseek( fp, 200L * sizeof( int ), SEEK_SET );
    fread( &n, sizeof( n ), 1, fp ); printf( "6 %d\n", n ); fclose( fp );
    h = open( "TIO.BIN", O_RDONLY | O_BINARY );
    printf( "7 len=%ld ", filelength( h ) ); lseek( h, 10L, SEEK_SET );
    n = read( h, buf, 8 ); printf( "read=%d tell=%ld eof=%d\n", n, tell( h ), eof( h ) );
    i = dup( h ); printf( "8 dup ok=%d\n", i >= 0 ); close( i ); close( h );
    h = creat( "TIO2.BIN", S_IREAD | S_IWRITE );
    n = write( h, "0123456789", 10 ); close( h );
    stat( "TIO2.BIN", &st ); printf( "9 write=%d size=%ld\n", n, st.st_size );
    a1 = access( "TIO2.BIN", 0 );
    a2 = access( "NOSUCH.ZZZ", 0 );
    printf( "10 access=%d %d\n", a1, a2 );
    rename( "TIO2.BIN", "TIO3.BIN" );
    a1 = access( "TIO3.BIN", 0 );
    a2 = remove( "TIO3.BIN" );
    printf( "11 %d %d\n", a1, a2 );
    mkdir( "TDIR" ); chdir( "TDIR" ); getcwd( buf, sizeof( buf ) );
    printf( "12 %s\n", strrchr( buf, '\\' ) ); chdir( ".." ); printf( "13 %d\n", rmdir( "TDIR" ) );
    remove( "TIO.TXT" ); remove( "TIO.BIN" );
    printf( "14 isatty=%d\n", isatty( fileno( stdout ) ) );
    tmpnam( buf ); printf( "15 tmpnam len=%d\n", strlen( buf ) > 0 );
    return( 0 );
}
