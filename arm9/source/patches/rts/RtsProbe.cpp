// Altered research version, not an upstream LNH-team release.
// Wait-wrapper detours are adapted from VideoGameMore/pico-loader PR #228.
// The reversible rendezvous protocol is new; no nds-bootstrap code is copied.
#include "common.h"
#ifdef PICO_RTS_PROBE
#include <cstring>
#include <stddef.h>
#include "sections.h"
#include "gameCode.h"
#include "thumbInstructions.h"
#include "RtsProbe.h"
#ifdef PICO_RTS_SNAPSHOT
#ifndef PICO_LOADER_TARGET_DSPICO
#error M2 snapshot is DSPico only
#endif
#include "RtsSnapshotInfo.h"
#include "RtsM2Image.h"
extern RtsSnapshotInfo gRtsSnapshotInfo;
extern "C" u32 rts9_m2_entry;
extern "C" u32 rts7_diagnostic_address;
static u32* sM2EntryAtTarget;
#endif

DEFINE_SECTION_SYMBOLS(patch_rts9_gate);
DEFINE_SECTION_SYMBOLS(patch_rts9_guard);
DEFINE_SECTION_SYMBOLS(patch_rts9_park);
DEFINE_SECTION_SYMBOLS(patch_rts9_dim);
DEFINE_SECTION_SYMBOLS(patch_rts9_resume);
DEFINE_SECTION_SYMBOLS(patch_rts7);
extern "C" {
void rts9_gate(), rts9_guard(), rts9_park(), rts9_dim(), rts9_resume(), rts9_return();
extern u32 rts9_enabled, rts9_guard_address, rts9_guard_return, rts9_park_address;
extern u32 rts9_park_return, rts9_dim_address, rts9_resume_address, rts9_dim_resume, rts9_resume_return;
void rts7_arm();
}

static u32* sEnabledAtTarget;
static unsigned sWaitHooks;

static u8* reserve(PatchHeap& heap, u32 size)
{
    // This optional installation runs AFTER all required patches. Failed partial
    // reservations need not be recycled: this heap is discarded on return.
    auto raw = (u8*)heap.TryAlloc(((size + 3) & ~3u) + 4);
    return raw ? (u8*)(((u32)raw + 3) & ~3u) : nullptr;
}

static u32 relocated(const void* symbol, const void* original, const void* target)
{
    return (u32)target + (u32)symbol - (u32)original;
}

void InstallRtsProbeArm9(PatchContext& context, const nds_header_ntr_t* header, u32 imageBytes)
{
    sEnabledAtTarget = nullptr;
#ifdef PICO_RTS_SNAPSHOT
    sM2EntryAtTarget = nullptr;
#endif
    sWaitHooks = 0;
    // First hardware target only: the user's AA2 Japanese/CJK ROM (A2GJ).
    if (header->gameCode != GAMECODE("A2GJ") || header->unitCode != 0 ||
        context.GetSdkVersion() != SdkVersion(0x03017532) || imageBytes < 0x800)
        return;
    void* originals[] = { SECTION_START(patch_rts9_gate), SECTION_START(patch_rts9_guard),
        SECTION_START(patch_rts9_park), SECTION_START(patch_rts9_dim), SECTION_START(patch_rts9_resume) };
    const u32 sizes[] = { SECTION_SIZE(patch_rts9_gate), SECTION_SIZE(patch_rts9_guard),
        SECTION_SIZE(patch_rts9_park), SECTION_SIZE(patch_rts9_dim), SECTION_SIZE(patch_rts9_resume) };
    u8* targets[5];
    auto& heap = context.GetPatchHeap();
    for (unsigned i = 0; i < 5; ++i)
    {
        targets[i] = reserve(heap, sizes[i]);
        if (!targets[i]) return;
        memcpy(targets[i], originals[i], sizes[i]);
    }
    auto link = [&](u32& literal, unsigned block, u32 value) {
        *(u32*)relocated(&literal, originals[block], targets[block]) = value;
    };
    const u32 entry = relocated((void*)rts9_gate, originals[0], targets[0]);
    const u32 ret = relocated((void*)rts9_return, originals[0], targets[0]);
    const u32 resume = relocated((void*)rts9_resume, originals[4], targets[4]);
    link(rts9_guard_address, 0, relocated((void*)rts9_guard, originals[1], targets[1]));
    link(rts9_guard_return, 1, ret);
    link(rts9_park_address, 1, relocated((void*)rts9_park, originals[2], targets[2]));
    link(rts9_park_return, 2, ret);
    link(rts9_dim_address, 2, relocated((void*)rts9_dim, originals[3], targets[3]));
    link(rts9_resume_address, 2, resume);
    link(rts9_dim_resume, 3, resume);
    link(rts9_resume_return, 4, ret);

    // Secure-area Thumb BIOS wait wrappers: preserve arguments and caller LR.
    auto secure = (u16*)header->arm9LoadAddress;
    for (unsigned i = 0; i + 1 < 0x800/2; ++i)
    {
        const u16 svc = secure[i];
        if (secure[i+1] != 0x4770 ||
            (svc != 0xdf03 && svc != 0xdf04 && svc != 0xdf05 && svc != 0xdf06)) continue;
        if ((svc == 0xdf04 || svc == 0xdf05) && (!i || secure[i-1] != 0x2200)) continue;
        auto stub = (u16*)reserve(heap, 16);
        if (!stub) continue;
        int delta = (int)stub - (int)&secure[i] - 4;
        if ((delta & 1) || delta < -2048 || delta > 2046) continue;
        stub[0] = 0xb50f; // push {r0-r3,lr}
        stub[1] = 0x4b02; // ldr r3,[pc,#8] -> stub+12
        stub[2] = 0x4798; // blx r3 (ARM9)
        stub[3] = 0xbc0f; // pop {r0-r3}
        stub[4] = svc;
        stub[5] = 0xbd00; // pop {pc}
        *(u32*)&stub[6] = entry;
        secure[i] = 0xe000 | ((delta >> 1) & 0x7ff);
        ++sWaitHooks;
    }
    // SDK OS_Halt may use inline CP15 WFI instead of any BIOS wrapper.
    auto words = (u32*)header->arm9LoadAddress;
    const auto adjuster = context.GetAutoloadAdjuster();
    for (unsigned i = 0x800/4; i + 1 < imageBytes/4; ++i)
    {
        const u32 instruction = words[i];
        if ((instruction & 0xffff0fff) != 0xee070f90 || (instruction & 0xf000) == 0xf000) continue;
        const u32 initial = (u32)&words[i];
        const u32 runtime = adjuster ? adjuster->AdjustInitialToFinal(initial) : initial;
        if ((runtime & 3) || (adjuster && adjuster->AdjustInitialToFinal(initial+4) != runtime+4)) continue;
        if (!((runtime >= 0x01ff8000 && runtime+4 < 0x02000000) ||
              (runtime >= 0x02000800 && runtime+4 < 0x02400000))) continue;
        auto stub = (u32*)reserve(heap, 32);
        if (!stub) continue;
        const int delta = (int)stub - (int)runtime - 8;
        if ((delta & 3) || delta < -33554432 || delta > 33554428) continue;
        stub[0] = 0xe92d500f; // stmdb sp!,{r0-r3,r12,lr}
        stub[1] = 0xe59fc00c; // ldr r12,[pc,#12] -> stub+24
        stub[2] = 0xe12fff3c; // blx r12
        stub[3] = 0xe8bd500f; // restore arguments and original LR
        stub[4] = instruction;
        stub[5] = 0xe59ff000; // ldr pc,[pc] -> stub+28
        stub[6] = entry;
        stub[7] = runtime+4;
        words[i] = 0xea000000 | ((delta >> 2) & 0xffffff);
        ++sWaitHooks;
    }
#ifdef PICO_RTS_SNAPSHOT
    sM2EntryAtTarget=(u32*)relocated(&rts9_m2_entry,originals[3],targets[3]);
#endif
    if (sWaitHooks)
        sEnabledAtTarget = (u32*)relocated(&rts9_enabled, originals[0], targets[0]);
}

void InstallRtsProbeArm7(PatchContext& context, u32 cheatsLength, void* workspace, u32 workspaceBytes)
{
    if (!sEnabledAtTarget || cheatsLength) {
        rtsProbeMessage("RTS probe unavailable.\nTarget: A2GJ / SDK 3.1.\nDisable cheats for testing.\nNo save-state support.");
        return;
    }
#ifdef PICO_RTS_SNAPSHOT
    if (!workspace || workspaceBytes<RTS_M2_MEMORY_BYTES || gRtsSnapshotInfo.magic!=RTS_M2_MAGIC || !sM2EntryAtTarget)
    {
        rtsProbeMessage("M2 snapshot unavailable.\nCheck free TF space and\nRTS-A2GJ-M2.bin format.\nNo memory capture active.");
        return;
    }
    memset(workspace,0,workspaceBytes);
    memcpy(workspace,RTS_M2_IMAGE,sizeof(RTS_M2_IMAGE));
    u32 delta=(u32)workspace-RTS_M2_LINK_BASE;
    for (u32 offset:RTS_M2_RELOCS) *(u32*)((u8*)workspace+offset)+=delta;
    auto config=(u8*)workspace+RTS_M2_CONFIG_OFFSET;
    memcpy(config,&gRtsSnapshotInfo,sizeof(gRtsSnapshotInfo));
    ((u32*)(config+sizeof(gRtsSnapshotInfo)))[0]=(u32)workspace;
    ((u32*)(config+sizeof(gRtsSnapshotInfo)))[1]=workspaceBytes;
    *sM2EntryAtTarget=(u32)workspace+RTS_M2_ENTRY_OFFSET;
#else
    (void)workspace; (void)workspaceBytes;
#endif
    // Known target's VBlank epilogue. Verify the displaced instructions, too.
    const u32 pattern[] = { 0xe92d4000, 0xe24dd004, 0xe59f003c, 0xe5902060 };
    u32* handler = context.FindPattern32(pattern, sizeof(pattern));
    u32* epilogue = handler ? handler + 0x40/4 : nullptr;
    if (!epilogue || epilogue[0] != 0xe28dd004 || epilogue[1] != 0xe8bd4000) {
        rtsProbeMessage("RTS probe disabled:\nARM7 hook not recognized.");
        return;
    }
    auto target = reserve(context.GetPatchHeap(), SECTION_SIZE(patch_rts7));
    if (!target) {
        rtsProbeMessage("RTS probe disabled:\nNo ARM7 patch space.");
        return;
    }
    memcpy(target, SECTION_START(patch_rts7), SECTION_SIZE(patch_rts7));
#ifdef PICO_RTS_SNAPSHOT
    *(u32*)relocated(&rts7_diagnostic_address,SECTION_START(patch_rts7),target)=
        (u32)workspace+RTS_M2_CONFIG_OFFSET+offsetof(RtsSnapshotInfo,reserved);
#endif
    // No target becomes active until both code blocks have been copied.
    epilogue[1] = relocated((void*)rts7_arm, SECTION_START(patch_rts7), target);
    epilogue[0] = 0xe51ff004;
    *sEnabledAtTarget = 1;
#ifdef PICO_RTS_SNAPSHOT
    rtsProbeMessage("RTS research: snapshot M2.3\nCapture only, NO load yet.\nHold L+R+Down+A.\nWrites RTS-A2GJ-M2.bin.\nOn S8, read code, press B.");
#else
    rtsProbeMessage("RTS research: CPU probe M1\nNOT save/load states yet.\nHold L+R+Down+A.\nDim/pause about 3 seconds,\nthen continue automatically.");
#endif
}
#endif
