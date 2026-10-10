#pragma once
#include <stddef.h>
#include <stdint.h>
typedef long time_t;
typedef unsigned long clock_t;
struct timespec { time_t tv_sec; long tv_nsec; };
struct tm { int tm_sec, tm_min, tm_hour, tm_mday, tm_mon, tm_year, tm_wday, tm_yday, tm_isdst; long tm_gmtoff; char *tm_zone; };
time_t time(time_t *);
clock_t clock(void);
struct tm *localtime(const time_t *);
struct tm *gmtime(const time_t *);
struct tm *localtime_r(const time_t *, struct tm *);
struct tm *gmtime_r(const time_t *, struct tm *);
time_t mktime(struct tm *);
size_t strftime(char *, size_t, const char *, const struct tm *);
int nanosleep(const struct timespec *, struct timespec *);
int clock_gettime(int clock_id, struct timespec *tp);
#define CLOCK_REALTIME 0
#define CLOCK_MONOTONIC 1
#define CLOCKS_PER_SEC 1000000
