// Diagnostic only. Load expressly into a freshly launched synthetic worker.
// No interposition or runtime binary change. Optional one-time idle trim.
#define _GNU_SOURCE
#include <errno.h>
#include <malloc.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static void *sample(void *unused) {
    (void)unused;
    const char *path = getenv("PROTEUS_DIAG_ARENAS_PATH");
    if (!path || !*path) return NULL;
    FILE *f = fopen(path, "a");
    if (!f) return NULL;
    struct timespec delay = {.tv_sec = 0, .tv_nsec = 500000000};
    const char *marker = getenv("PROTEUS_DIAG_TRIM_MARKER");
    int trimmed = 0;
    for (;;) {
        struct timespec t;
        clock_gettime(CLOCK_MONOTONIC, &t);
        if (marker && !trimmed && access(marker, F_OK) == 0) {
            trimmed = 1;
            int result = malloc_trim(0);
            fprintf(f, "IDLE_TRIM %d\n", result);
        }
        fprintf(f, "SAMPLE %lld %d\n",
                (long long)t.tv_sec * 1000000000 + t.tv_nsec, (int)getpid());
        if (malloc_info(0, f) != 0) fputs("ERROR malloc_info\n", f);
        fflush(f);
        struct timespec rem = delay;
        while (nanosleep(&rem, &rem) == -1 && errno == EINTR) {}
    }
    return NULL;
}

__attribute__((constructor)) static void start(void) {
    pthread_t thread;
    if (getenv("PROTEUS_DIAG_ARENAS_PATH") && pthread_create(&thread, NULL, sample, NULL) == 0)
        pthread_detach(thread);
}
