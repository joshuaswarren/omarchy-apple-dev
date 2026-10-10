/* machoload/hello.c
 *
 * C hello compiled as an iOS arm64 Mach-O with the sdk-free toolchain and
 * run on Linux by machoload/loader. Every call below stays an undefined
 * symbol in the binary (compiled with -fno-builtin and linked with
 * -undefined dynamic_lookup); the Linux loader binds each by name against
 * its own implementations over direct syscalls.
 */

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

int main(void) {
    /* keep every call: results feed checks the compiler cannot fold */
    struct timespec ts;
    long pid = getpid();
    int have_time = clock_gettime(CLOCK_REALTIME, &ts) == 0;

    char buf[16];
    memset(buf, 0, sizeof(buf));
    memcpy(buf, "Hello from", 10);
    volatile int ok = buf[0] == 'H' && pid > 0 && have_time;
    if (!ok)
        return 1;
    puts("Hello from an iOS Mach-O on Linux");
    return 0;
}
