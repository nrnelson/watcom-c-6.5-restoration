/* T_SPAWN - process: spawn a child, system-like behaviour, exit codes.
   The process exit status is expected to be 3: the program ends by
   exec-ing itself with argument 3, and that child returns 3
   (tools/difftest.py, EXPECT_EXIT). */
#include <stdio.h>
#include <stdlib.h>
#include <process.h>

int main( int argc, char **argv )
{
    int         rc;

    if( argc > 1 ) {
        printf( "child: argc=%d arg1=%s\n", argc, argv[1] );
        return( atoi( argv[1] ) );
    }
    rc = spawnl( P_WAIT, argv[0], argv[0], "7", NULL );
    printf( "1 spawnl rc=%d\n", rc );
    rc = spawnlp( P_WAIT, argv[0], argv[0], "9", NULL );
    printf( "2 spawnlp rc=%d\n", rc );
    rc = spawnl( P_WAIT, "NOSUCH.EXE", "NOSUCH.EXE", NULL );
    printf( "3 missing rc=%d\n", rc );
    printf( "4 exec next\n" );
    fflush( stdout );
    execl( argv[0], argv[0], "3", NULL );
    printf( "exec failed\n" );
    return( 99 );
}
