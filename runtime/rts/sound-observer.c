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
// PSG/noise setup writes TMR directly rather than calling the timer setter.
// All three entries supply the SDK period, not the hardware reload value.
static void observePeriod(uint32_t ch,uint32_t period)
{
    if(ch>=16){gRtsSoundShadow.unsupported=1;return;}
    RtsObserveSoundWrite(&gRtsSoundShadow,0x04000408+ch*16,2,(0x10000-period)&65535);
}
void rtsSoundObserveTimer(const uint32_t* regs)
{
    observePeriod(regs[0],regs[1]);
}
// Called with the register state at the common PSG/noise TMR store.
// The SDK has already disabled this channel through CNT. The assembly stub
// masks IRQ/FIQ across shadow publication AND the displaced halfword store.
void rtsSoundObserveReload(const uint32_t* regs)
{
    uint32_t a=regs[0];
    if(a<0x04000400 || a>=0x04000500 || (a&15)){gRtsSoundShadow.unsupported=1;return;}
    RtsObserveSoundWrite(&gRtsSoundShadow,a+8,2,regs[1]&65535);
}
