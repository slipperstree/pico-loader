"""Compile the actual allocator, testing failure without a fatal loop or mutation."""
from pathlib import Path
import os, shutil, subprocess, sys

root = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
work = root / 'build/rts-heap-test'
work.mkdir(parents=True,exist_ok=True)
for name in ('PatchHeap.cpp','PatchHeap.h'):
    shutil.copyfile(root/'arm9/source/patches'/name, work/name)
(work/'common.h').write_text('''#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
using u8 = uint8_t;
using u32 = uint32_t;
#define LOG_DEBUG(...) ((void)0)
#define LOG_FATAL(...) std::abort()
''')
(work/'main.cpp').write_text('''#include "common.h"
#include "PatchHeap.h"
#include <cassert>
int main() {
    alignas(4) u8 a[64], b[124];
    PatchHeap heap;
    heap.AddFreeSpace(a, sizeof(a));
    heap.AddFreeSpace(b, sizeof(b));
    assert(heap.TryAlloc(140) == nullptr); // Neither block fits; do not consume.
    assert(heap.TryAlloc(48) == a); // Best fit, leave 16 bytes.
    assert(heap.TryAlloc(128) == nullptr); // Failure must not lose the 124 block.
    assert(heap.Alloc(124) == b); // Required allocation still works.
    assert(heap.TryAlloc(16) == a+48);
    assert(heap.TryAlloc(4) == nullptr); // Empty heap must return, not hang.
    alignas(4) u8 c[32];
    PatchHeap merged;
    merged.AddFreeSpace(c,16);
    merged.AddFreeSpace(c+16,16);
    assert(merged.TryAlloc(32) == c); // Adjacent block merging still works.
    std::puts("PASS actual PatchHeap: exhaustion, no mutation on failure, best fit, required allocation, adjacent merging");
}
''')
cxx = os.environ.get('CXX', r'C:/msys64/mingw64/bin/g++.exe' if os.name=='nt' else 'g++')
exe = work/('test.exe' if os.name=='nt' else 'test')
subprocess.run([cxx,'-std=c++23','-static','-I'+str(work),str(work/'main.cpp'),str(work/'PatchHeap.cpp'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,timeout=10)
