/* machoload/loader.c
 *
 * A minimal arm64 Mach-O executable loader for Linux on aarch64.
 * It maps an lld-linked iOS executable at its preferred virtual addresses,
 * fills the dyld bind slots by symbol name against its own Linux symbol
 * table (direct syscalls and libc string helpers), and calls the program
 * entry. Segments are mapped at their link-time vmaddr, so no rebasing or
 * relocation processing is needed; only dyld bind opcodes are interpreted.
 *
 * Freestanding: direct Linux syscalls only, no libc. Runs natively on
 * aarch64 Linux and under qemu-aarch64-static anywhere.
 *
 *   qemu-aarch64-static ./loader ./Hello
 *
 * Build: machoload/build.sh
 */

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef unsigned long long u64;
typedef int            i32;
typedef long long      i64;

/* ------------------------------------------------------------------ */
/* Direct Linux aarch64 syscalls                                      */
/* ------------------------------------------------------------------ */

#define SYS_OPENAT     56
#define SYS_LSEEK      62
#define SYS_READ       63
#define SYS_WRITE      64
#define SYS_EXIT       93
#define SYS_EXIT_GROUP 94
#define SYS_GETPID     172
#define SYS_MMAP       222
#define SYS_MPROTECT   226
#define AT_FDCWD       (-100)

static long sys1(long n, long a) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8) : "memory", "cc");
    return x0;
}
static long sys3(long n, long a, long b, long c) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory", "cc");
    return x0;
}
static long sys4(long n, long a, long b, long c, long d) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory", "cc");
    return x0;
}

static u64 xstrlen(const char *s) { u64 n = 0; while (s[n]) n++; return n; }
static void xputs_fd(int fd, const char *s) { sys3(SYS_WRITE, fd, (long)s, xstrlen(s)); }

static void die(const char *msg) {
    xputs_fd(2, "machoload: ");
    xputs_fd(2, msg);
    xputs_fd(2, "\n");
    sys1(SYS_EXIT_GROUP, 1);
}

static void *memset(void *d, int c, u64 n) {
    u8 *p = d; while (n--) *p++ = (u8)c; return d;
}
static void *memcpy(void *d, const void *s, u64 n) {
    u8 *dp = d; const u8 *sp = s; while (n--) *dp++ = *sp++; return d;
}

/* ------------------------------------------------------------------ */
/* Mach-O format (64-bit)                                             */
/* ------------------------------------------------------------------ */

#define MH_MAGIC_64    0xfeedfacfu
#define CPU_TYPE_ARM64 0x0100000cu
#define MH_EXECUTE     2u

#define LC_SEGMENT_64       0x19u
#define LC_DYLD_INFO        0x22u
#define LC_DYLD_INFO_ONLY   0x80000022u
#define LC_MAIN             0x80000028u

struct mach_header_64 {
    u32 magic, cputype, cpusubtype, filetype;
    u32 ncmds, sizeofcmds, flags, reserved;
};
struct segment_command_64 {
    u32 cmd, cmdsize;
    char segname[16];
    u64 vmaddr, vmsize, fileoff, filesize;
    i32 maxprot, initprot, nsects, flags;
};
struct dyld_info_command {
    u32 cmd, cmdsize;
    u32 reinterpret_off, reinterpret_size;
    u32 bind_off, bind_size, weak_bind_off, weak_bind_size;
    u32 lazy_bind_off, lazy_bind_size, export_off, export_size;
};
struct entry_point_command {
    u32 cmd, cmdsize;
    u64 entryoff, stacksize;
};

/* dyld bind opcodes (classic LC_DYLD_INFO streams, llvm BinaryFormat/MachO.h) */
#define BIND_TYPE_POINTER 1
#define BIND_TYPE_TEXT_ABSOLUTE32 2

/* ------------------------------------------------------------------ */
/* Linux symbol providers (stand-ins for libSystem on iOS)            */
/* ------------------------------------------------------------------ */

/* write(2) over a direct syscall */
static long host_write(int fd, const void *buf, u64 n) {
    return sys3(SYS_WRITE, fd, (long)buf, (long)n);
}

/* _puts over write(2): the string, then a newline, like puts */
static long host_puts(const char *s) {
    long r = host_write(1, s, xstrlen(s));
    host_write(1, "\n", 1);
    return r;
}

static void host_exit(long code) { sys1(SYS_EXIT_GROUP, code); }
static long host_getpid(void) { return sys1(SYS_GETPID, 0); }
static void *host_memmove(void *d, const void *s, u64 n) {
    u8 *dp = d; const u8 *sp = s;
    if (dp < sp) { while (n--) *dp++ = *sp++; }
    else { dp += n; sp += n; while (n--) *--dp = *--sp; }
    return d;
}
static long host_abort(void) { die("guest called abort"); return 0; }

struct timespec64 { i64 sec; i64 nsec; };
static long host_clock_gettime(int clk, struct timespec64 *ts) {
    return sys3(113 /* clock_gettime */, clk, (long)ts, 0);
}

/* Mach-O symbols are C names prefixed with '_'; names that already start
 * with '_' (like "___stack_chk_guard") keep their extra underscores. */
static void host_dyld_stub_binder(void) { die("guest reached dyld_stub_binder"); }
static u64 host_stack_chk_guard = 0xdeadbeefcafe0001ULL;

static const struct { const char *name; void *addr; } providers[] = {
    { "puts",         (void *)host_puts },
    { "write",        (void *)host_write },
    { "exit",         (void *)host_exit },
    { "getpid",       (void *)host_getpid },
    { "clock_gettime",(void *)host_clock_gettime },
    { "memcpy",       (void *)memcpy },
    { "memmove",      (void *)host_memmove },
    { "memset",       (void *)memset },
    { "abort",        (void *)host_abort },
    { "dyld_stub_binder", (void *)host_dyld_stub_binder },
    { "__stack_chk_guard",(void *)&host_stack_chk_guard },
    { "__stack_chk_fail", (void *)host_abort },
    { 0, 0 },
};

static void *resolve(const char *sym) {
    const char *n = (*sym == '_') ? sym + 1 : sym;
    for (int i = 0; providers[i].name; i++)
        if (xstrlen(providers[i].name) == xstrlen(n)) {
            const char *a = providers[i].name, *b = n;
            while (*a && *a == *b) { a++; b++; }
            if (!*a) return providers[i].addr;
        }
    return 0;
}

/* ------------------------------------------------------------------ */
/* dyld bind opcode machine                                           */
/* ------------------------------------------------------------------ */

static u64 read_uleb(const u8 **p) {
    u64 r = 0; int shift = 0; u8 b;
    do { b = *(*p)++; r |= (u64)(b & 0x7f) << shift; shift += 7; } while (b & 0x80);
    return r;
}
static i64 read_sleb(const u8 **p) {
    i64 r = 0; int shift = 0; u8 b;
    do { b = *(*p)++; r |= (i64)(b & 0x7f) << shift; shift += 7; } while (b & 0x80);
    if (shift < 64 && (b & 0x40)) r |= -(1LL << shift);
    return r;
}

struct seg { u64 vmaddr, vmsize; };

static struct seg segs[16];
static int nsegs;

static void do_bind(int segi, u64 off, void *addr, int type, const char *name) {
    if (!addr) {
        xputs_fd(2, "machoload: unresolved symbol: ");
        xputs_fd(2, name);
        xputs_fd(2, "\n");
        sys1(SYS_EXIT_GROUP, 1);
    }
    if (segi < 0 || segi >= nsegs) die("bind: bad segment index");
    u64 a = segs[segi].vmaddr + off;
    if (off + 8 > segs[segi].vmsize) die("bind: offset outside segment");
    switch (type) {
    case BIND_TYPE_POINTER:      *(u64 *)a = (u64)addr; break;
    case BIND_TYPE_TEXT_ABSOLUTE32: *(u32 *)a = (u32)(u64)addr; break;
    default: die("bind: unsupported type");
    }
    (void)name;
}

static void run_binds(const u8 *p, u64 size) {
    const u8 *end = p + size;
    int segi = 0, type = BIND_TYPE_POINTER;
    u64 off = 0;
    const char *name = "";

    while (p < end) {
        u8 op = *p++;
        u8 imm = op & 0x0f;
        switch (op & 0xf0) {
        case 0x00: /* DONE: ends each lazy-bind entry; keep walking */
            break;
        case 0x10: /* set dylib ordinal immediate: no operand */
            break; /* bound by name here; ordinal unused */
        case 0x20: /* set dylib ordinal uleb */
            read_uleb(&p);
            break;
        case 0x30: /* set dylib special ordinal: no operand */
            break;
        case 0x40: /* symbol name follows, null-terminated */
            name = (const char *)p;
            p += xstrlen(name) + 1;
            break;
        case 0x50: type = imm; break;
        case 0x60: read_sleb(&p); break; /* addend; unused */
        case 0x70: segi = imm; off = read_uleb(&p); break;
        case 0x80: off += read_uleb(&p); break;
        case 0x90: /* do bind */
            do_bind(segi, off, resolve(name), type, name);
            off += 8;
            break;
        case 0xa0: /* do bind, then add uleb to the offset */
            do_bind(segi, off, resolve(name), type, name);
            off += read_uleb(&p);
            break;
        case 0xb0: /* do bind, then skip imm more slots */
            do_bind(segi, off, resolve(name), type, name);
            off += 8 + (u64)imm * 8;
            break;
        case 0xc0: { /* do bind uleb times, skipping uleb slots */
            u64 times = read_uleb(&p), skip = read_uleb(&p);
            for (u64 i = 0; i < times; i++) {
                do_bind(segi, off, resolve(name), type, name);
                off += skip + 8;
            }
            break;
        }
        default:
            die("bind: unsupported opcode");
        }
    }
}

/* ------------------------------------------------------------------ */
/* Loader                                                             */
/* ------------------------------------------------------------------ */

static void *sys_mmap(void *addr, u64 len, int prot, int flags, int fd, u64 off) {
    register long x8 __asm__("x8") = 222; /* mmap */
    register long x0 __asm__("x0") = (long)addr;
    register long x1 __asm__("x1") = (long)len;
    register long x2 __asm__("x2") = prot;
    register long x3 __asm__("x3") = flags;
    register long x4 __asm__("x4") = fd;
    register long x5 __asm__("x5") = (long)off;
    __asm__ volatile("svc 0"
                     : "+r"(x0)
                     : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
                     : "memory", "cc");
    return (void *)x0;
}

#define PROT_R 1
#define PROT_W 2
#define PROT_X 4
#define MAP_PRIVATE   0x02
#define MAP_ANONYMOUS 0x20
#define MAP_FIXED     0x10

static u64 round_up(u64 v, u64 a) { return (v + a - 1) & ~(a - 1); }
static int segname_is(const char *sn, const char *name) {
    for (int i = 0; i < 16; i++) {
        if (sn[i] != name[i]) return 0;
        if (!name[i]) return 1;
    }
    return 1;
}

/* ELF entry: hand the initial stack pointer to the C loader. */
__attribute__((naked)) void _start(void) {
    __asm__ volatile("mov x0, sp\n b machoload_start\n");
}

void machoload_start(u64 *sp) {
    long argc = (long)sp[0];
    char **argv = (char **)(sp + 1);
    if (argc < 2) die("usage: loader <mach-o-executable>");

    /* map the file */
    long fd = sys4(SYS_OPENAT, AT_FDCWD, (long)argv[1], 0 /* O_RDONLY */, 0);
    if (fd < 0) die("cannot open input file");
    long size = sys3(SYS_LSEEK, fd, 0, 2 /* SEEK_END */);
    if (size <= 0) die("empty input file");
    u8 *file = sys_mmap(0, (u64)size, PROT_R, MAP_PRIVATE, (int)fd, 0);
    if ((long)file < 0 && (long)file > -4096) die("cannot map input file");

    struct mach_header_64 *mh = (struct mach_header_64 *)file;
    if (mh->magic != MH_MAGIC_64) die("not a 64-bit Mach-O");
    if (mh->cputype != CPU_TYPE_ARM64) die("not an arm64 Mach-O");
    if (mh->filetype != MH_EXECUTE) die("not a Mach-O executable");

    u64 entry = 0, text_vmaddr = 0;
    struct dyld_info_command *info = 0;
    int have_main = 0;

    u8 *cmd = file + sizeof(*mh);
    u8 *cmdend = cmd + mh->sizeofcmds;
    while (cmd + 8 <= cmdend) {
        u32 c = *(u32 *)cmd;
        u32 cs = ((u32 *)cmd)[1];
        if (cs < 8 || cmd + cs > cmdend) die("bad load command");
        if (c == LC_SEGMENT_64) {
            struct segment_command_64 *sg = (struct segment_command_64 *)cmd;
            if (nsegs < 16) {
                segs[nsegs].vmaddr = sg->vmaddr;
                segs[nsegs].vmsize = sg->vmsize;
                nsegs++;
            }
            if (segname_is(sg->segname, "__TEXT"))
                text_vmaddr = sg->vmaddr;
            if (sg->vmsize == 0 || sg->maxprot == 0) { cmd += cs; continue; }
            int prot = 0;
            if (sg->initprot & 1) prot |= PROT_R;
            if (sg->initprot & 2) prot |= PROT_W;
            if (sg->initprot & 4) prot |= PROT_X;
            void *p = sys_mmap((void *)sg->vmaddr, round_up(sg->vmsize, 4096),
                               prot | PROT_W, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED,
                               -1, 0);
            if ((long)p < 0 && (long)p > -4096) die("cannot map segment");
            memcpy((void *)sg->vmaddr, file + sg->fileoff, sg->filesize);
            /* memory beyond filesize stays zero (anonymous mapping) */
        } else if (c == LC_DYLD_INFO || c == LC_DYLD_INFO_ONLY) {
            info = (struct dyld_info_command *)cmd;
        } else if (c == LC_MAIN) {
            struct entry_point_command *ep = (struct entry_point_command *)cmd;
            entry = ep->entryoff;
            have_main = 1;
        }
        cmd += cs;
    }
    if (!have_main) die("no LC_MAIN entry point");
    if (!info) die("no LC_DYLD_INFO bind information");

    /* Fill bind slots by symbol name. Segments are mapped at their
     * preferred vmaddr, so there is no slide: file pointers already hold
     * their final values and only external binds need writing. */
    if (info->bind_size)
        run_binds(file + info->bind_off, info->bind_size);
    if (info->lazy_bind_size)
        run_binds(file + info->lazy_bind_off, info->lazy_bind_size);

    /* restore segment protections */
    u8 *c2 = file + sizeof(*mh);
    while (c2 + 8 <= cmdend) {
        u32 ccs = ((u32 *)c2)[1];
        if (*(u32 *)c2 == LC_SEGMENT_64) {
            struct segment_command_64 *sg = (struct segment_command_64 *)c2;
            if (sg->vmsize && sg->maxprot) {
                int prot = 0;
                if (sg->initprot & 1) prot |= PROT_R;
                if (sg->initprot & 2) prot |= PROT_W;
                if (sg->initprot & 4) prot |= PROT_X;
                sys3(SYS_MPROTECT, (long)sg->vmaddr, (long)round_up(sg->vmsize, 4096), prot);
            }
        }
        c2 += ccs;
    }

    /* the first mapped segment is __TEXT; entry is an offset into it */
    if (!nsegs) die("no segments");
    int (*guest)(long, char **, char **) =
        (int (*)(long, char **, char **))(text_vmaddr + entry);

    long rc = guest(argc, argv, (char **)sp + 1 + argc + 1);
    host_exit(rc);
}
