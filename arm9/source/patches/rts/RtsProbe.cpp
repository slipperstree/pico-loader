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
#include "patches/platform/dspico/DSPicoReadSdSectorsPatchCode.h"
#include "patches/platform/dspico/DSPicoWriteSdSectorsPatchCode.h"
#include "RtsM2Image.h"
extern RtsSnapshotInfo gRtsSnapshotInfo;
extern "C" u32 rts9_m2_entry;
extern "C" u32 rts7_diagnostic_address, rts7_read_busy_address, rts7_write_busy_address, rts7_clock_address;
#ifdef PICO_RTS_ARM7_CAPTURE
extern "C" u32 rts7_mailbox_address, rts7_capture_address, rts7_service_address;
#endif
static u32* sM2EntryAtTarget;
#ifdef PICO_RTS_RESTORE_PROBE
#include "RtsP4.h"
#include "RtsP4Profile.h"
extern RtsP4Identity gRtsP4LoaderIdentity;
extern "C" u32 rts7_operation_address,rts7_begin_address,rts7_loop_address;
DEFINE_SECTION_SYMBOLS(patch_rtsSoundPcm);
DEFINE_SECTION_SYMBOLS(patch_rtsSoundTimer);
DEFINE_SECTION_SYMBOLS(patch_rtsSoundExit);
extern "C" {
void rtsSoundPcmHook(),rtsSoundTimerHook(),rtsSoundExitHook();
extern u32 rtsSoundPcmBusy,rtsSoundPcmObserve,rtsSoundPcmResume;
extern u32 rtsSoundTimerBusy,rtsSoundTimerObserve,rtsSoundTimerResume,rtsSoundExitBusy;
}
static u8* sP4Tail;
#endif
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
#ifdef PICO_RTS_RESTORE_PROBE
    sP4Tail=nullptr;
#endif
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
#ifdef PICO_RTS_RESTORE_PROBE
    if(sWaitHooks!=5)return;
    sP4Tail=reserve(heap,RTS_P4_TAIL_BYTES);
    if(!sP4Tail)return;
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
#ifdef PICO_RTS_RESTORE_PROBE
        rtsProbeMessage("P4 checkpoint unavailable.\nCheck ROM and .rts file,\nfree TF space/fragmentation.");
#else
        rtsProbeMessage("M2 snapshot unavailable.\nCheck free TF space and\nRTS-A2GJ-M2.bin format.\nNo memory capture active.");
#endif
        return;
    }
    u32 readBusy=DSPicoReadSdSectorsPatchCode::busyAddress;
    u32 writeBusy=DSPicoWriteSdSectorsPatchCode::busyAddress;
    if(readBusy<0x03800000 || readBusy>=0x03810000 || writeBusy<0x03800000 || writeBusy>=0x03810000)
    {
        rtsProbeMessage("M2 disabled: SD guards\nwere not installed.");return;
    }
#ifdef PICO_RTS_RESTORE_PROBE
    if(!sP4Tail || memcmp(gRtsP4LoaderIdentity.code,RTS_P4_EXPECTED_CODE,32))
    {rtsProbeMessage("P4 disabled: code identity\nor secure tail unavailable.");return;}
#endif
    memset(workspace,0,workspaceBytes);
    memcpy(workspace,RTS_M2_IMAGE,sizeof(RTS_M2_IMAGE));
    u32 delta=(u32)workspace-RTS_M2_LINK_BASE;
    for (u32 offset:RTS_M2_RELOCS) *(u32*)((u8*)workspace+offset)+=delta;
    auto config=(u8*)workspace+RTS_M2_CONFIG_OFFSET;
    memcpy(config,&gRtsSnapshotInfo,sizeof(gRtsSnapshotInfo));
    ((RtsSnapshotInfo*)config)->reserved=0;
    auto header=(RtsM2Header*)(config+sizeof(gRtsSnapshotInfo)+8);
    header->flags=
#ifdef PICO_RTS_RESTORE_PROBE
        RTS_P4_EXPERIMENT_FLAG |
#else
        RTS_M2_FLAG_DIAGNOSTIC |
#endif
        ((gRtsSnapshotInfo.reserved&RTS_M2_CONFIG_FULL_VERIFY) ? 0 : RTS_M2_FLAG_NO_READBACK);
    ((u32*)(config+sizeof(gRtsSnapshotInfo)))[0]=(u32)workspace;
    ((u32*)(config+sizeof(gRtsSnapshotInfo)))[1]=workspaceBytes;
    *sM2EntryAtTarget=(u32)workspace+RTS_M2_ENTRY_OFFSET;
#ifdef PICO_RTS_RESTORE_PROBE
    auto ptr=(const u32*)((u8*)workspace+RTS_P4_POINTERS_OFFSET);
    memcpy(sP4Tail,(void*)ptr[8],RTS_P4_TAIL_BYTES);
    *(u32*)ptr[9]=(u32)sP4Tail;
    auto identity=(RtsP4Identity*)ptr[7];
    memcpy(identity,&gRtsP4LoaderIdentity,sizeof(*identity));
    memcpy(identity->build,RTS_P4_BUILD_SHA256,32);
    auto shadow=(RtsSoundShadow*)ptr[5];shadow->magic=RTS_SOUND_SHADOW_MAGIC;shadow->version=1;
#endif
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
    *(u32*)relocated(&rts7_read_busy_address,SECTION_START(patch_rts7),target)=readBusy;
    *(u32*)relocated(&rts7_write_busy_address,SECTION_START(patch_rts7),target)=writeBusy;
    *(u32*)relocated(&rts7_clock_address,SECTION_START(patch_rts7),target)=(u32)workspace+RTS_M2_CLOCK_OFFSET;
#endif
#ifdef PICO_RTS_ARM7_CAPTURE
    *(u32*)relocated(&rts7_mailbox_address,SECTION_START(patch_rts7),target)=(u32)workspace+RTS_M3_MAILBOX_OFFSET;
    *(u32*)relocated(&rts7_capture_address,SECTION_START(patch_rts7),target)=(u32)workspace+RTS_M3_ARM7_CAPTURE_OFFSET;
    *(u32*)relocated(&rts7_service_address,SECTION_START(patch_rts7),target)=(u32)workspace+RTS_M3_ARM7_SERVICE_OFFSET;
#endif
#ifdef PICO_RTS_RESTORE_PROBE
    // Exact-code identity above gates these known SDK runtime continuations.
    const u32 pcmPattern[]={0xe1a07002,0xe1a06003,0xe59d1020,0xe59d502c};
    const u32 timerPattern[]={0xe2611801,0xe1a00200,0xe2800301,0xe2800b01};
    auto pcm=context.FindPattern32(pcmPattern,sizeof(pcmPattern));
    if(pcm)pcm-=2;
    auto timer=context.FindPattern32(timerPattern,sizeof(timerPattern));
    if(!pcm || !timer || pcm[0xb8/4]!=0xe12fff1e || timer[0x14/4]!=0xe12fff1e)
    {rtsProbeMessage("P4 disabled: sound SDK\nentry not recognized.");return;}
    void* soundOriginal[]={SECTION_START(patch_rtsSoundPcm),SECTION_START(patch_rtsSoundTimer),SECTION_START(patch_rtsSoundExit)};
    const u32 soundSize[]={SECTION_SIZE(patch_rtsSoundPcm),SECTION_SIZE(patch_rtsSoundTimer),SECTION_SIZE(patch_rtsSoundExit)};
    u8* soundTarget[3];
    for(u32 i=0;i<3;++i){soundTarget[i]=reserve(context.GetPatchHeap(),soundSize[i]);if(!soundTarget[i]){rtsProbeMessage("P4 disabled: sound patch\nspace unavailable.");return;}memcpy(soundTarget[i],soundOriginal[i],soundSize[i]);}
    auto soundLink=[&](u32& literal,u32 i,u32 value){*(u32*)relocated(&literal,soundOriginal[i],soundTarget[i])=value;};
    soundLink(rtsSoundPcmBusy,0,ptr[4]);soundLink(rtsSoundPcmObserve,0,ptr[2]);soundLink(rtsSoundPcmResume,0,0x037ff2a0);
    soundLink(rtsSoundTimerBusy,1,ptr[4]);soundLink(rtsSoundTimerObserve,1,ptr[3]);soundLink(rtsSoundTimerResume,1,0x037ff070);
    soundLink(rtsSoundExitBusy,2,ptr[4]);
    const u32 exit=relocated((void*)rtsSoundExitHook,soundOriginal[2],soundTarget[2]);
    pcm[0]=timer[0]=0xe51ff004;
    pcm[1]=relocated((void*)rtsSoundPcmHook,soundOriginal[0],soundTarget[0]);
    timer[1]=relocated((void*)rtsSoundTimerHook,soundOriginal[1],soundTarget[1]);
    pcm[0xb8/4]=0xea000000|(((exit-0x037ff350-8)>>2)&0xffffff);
    timer[0x14/4]=0xea000000|(((exit-0x037ff07c-8)>>2)&0xffffff);
    *(u32*)relocated(&rts7_operation_address,SECTION_START(patch_rts7),target)=ptr[6]+offsetof(RtsP4Shared,operation);
    *(u32*)relocated(&rts7_begin_address,SECTION_START(patch_rts7),target)=ptr[1];
    *(u32*)relocated(&rts7_loop_address,SECTION_START(patch_rts7),target)=ptr[0];
#endif
    // No target becomes active until all mandatory blocks have been copied.
    epilogue[1] = relocated((void*)rts7_arm, SECTION_START(patch_rts7), target);
    epilogue[0] = 0xe51ff004;
    *sEnabledAtTarget = 1;
#ifdef PICO_RTS_SNAPSHOT
#ifdef PICO_RTS_ARM7_CAPTURE
#ifdef PICO_RTS_VIDEO_CAPTURE
#ifdef PICO_RTS_RESTORE_PROBE
    rtsProbeMessage("RTS research: restore P4.0\nPersistent checkpoint test.\nSave: L+R+Down+A\nLoad: L+R+Down+B\nAudio restarts. 3D incomplete.");
#else
    rtsProbeMessage("RTS research: capture M3.2\nARM7 + VRAM/palette/OAM.\nCapture only, NO load yet.\nHold L+R+Down+A.");
#endif
#else
    rtsProbeMessage("RTS research: capture M3.1\nARM7 context + WRAM added.\nCapture only, NO load yet.\nHold L+R+Down+A.\nS8 8192: WRAM/mode guard.");
#endif
#else
    rtsProbeMessage((header->flags&RTS_M2_FLAG_NO_READBACK)
        ? "RTS research: snapshot M2.6\nFAST: no full readback.\nCapture only, NO load yet.\nHold L+R+Down+A.\nOn S8, read code, press B."
        : "RTS research: snapshot M2.6\nFULL: write + readback.\nCapture only, NO load yet.\nHold L+R+Down+A.\nOn S8, read code, press B.");
#endif
#else
    rtsProbeMessage("RTS research: CPU probe M1\nNOT save/load states yet.\nHold L+R+Down+A.\nDim/pause about 3 seconds,\nthen continue automatically.");
#endif
}
#endif
