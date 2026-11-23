#include "RtsSoundRestart.h"
RtsSoundShadow gRtsSoundShadow;
volatile uint32_t gRtsSoundBusy;
// Original SDK arguments, before its first prologue. Only write-only fields
// are shadowed; actual current CNT is sampled on ARM7 when saving.
void rtsSoundObservePcm(const uint32_t* regs,const uint32_t* stack)
{
    uint32_t ch=regs[0];if(ch>=16){gRtsSoundShadow.unsupported=1;return;}
    uint32_t a=0x04000400+ch*16;
    RtsObserveSoundWrite(&gRtsSoundShadow,a+4,4,regs[1]);
    RtsObserveSoundWrite(&gRtsSoundShadow,a+8,2,(0x10000-stack[4])&65535);
    RtsObserveSoundWrite(&gRtsSoundShadow,a+10,2,stack[0]&65535);
    RtsObserveSoundWrite(&gRtsSoundShadow,a+12,4,stack[1]);
}
void rtsSoundObserveTimer(const uint32_t* regs)
{
    if(regs[0]>=16){gRtsSoundShadow.unsupported=1;return;}
    RtsObserveSoundWrite(&gRtsSoundShadow,0x04000408+regs[0]*16,2,(0x10000-regs[1])&65535);
}
