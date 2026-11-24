#include "RtsP4.h"
#include "RtsArm7Restore.h"
#include "worker-state.h"
typedef uint32_t u32;typedef uint16_t u16;
#define R32(a) (*(volatile u32*)(a))
#define R16(a) (*(volatile u16*)(a))
extern volatile RtsArm7Mailbox gRtsArm7Mailbox;
extern void rtsArm7CaptureService(volatile RtsArm7Mailbox*);
RtsP4Shared gRtsP4 __attribute__((aligned(32)));
RtsP4Scratch gRtsP4Scratch __attribute__((aligned(32)));
RtsP4Identity gRtsP4Identity __attribute__((aligned(32)));
u32 gRtsP4TailAddress;
u32 gRtsP4SavedSequence __attribute__((aligned(32)));
u32 gRtsP4FreshSlot;
u32 gRtsP4Arm7Stack[96] __attribute__((aligned(8)));
static u32 send(const RtsP4Queue* q)
{
    u32 n=q->count;if(n>16)return 1;
    for(u32 i=0;i<n;++i){if(R16(0x04000184)&2)return 2;R32(0x04000188)=q->data[i];}
    return 0;
}
static void mmio(void* user,u32 a,u32 bytes,u32 value)
{
    (void)user;if(bytes==2)R16(a)=value;else R32(a)=value;
}
void rtsP4Arm7Begin(u32 originalIpc)
{
    gRtsP4.error=0;gRtsP4.ready=0;gRtsP4.release=0;gRtsP4.to7.count=0;
    if(gRtsSoundBusy || gRtsM2.info.reserved){gRtsP4.error=gRtsSoundBusy ? 4096 : 0;return;}
    u32* p=gRtsSoundShadow.reserved;
    for(u32 i=0;i<16;++i)p[i]=R32(0x04000400+i*16);
    p[16]=R16(0x04000500)|((u32)R16(0x04000504)<<16);
    p[17]=R32(0x04000210);p[18]=R32(0x04000214);p[19]=originalIpc;
    p[20]=R16(0x04000184)|((u32)R16(0x04000304)<<16);
    p[21]=R16(0x04000102)|((u32)R16(0x04000106)<<16);
    p[22]=R16(0x0400010a)|((u32)R16(0x0400010e)<<16);
    p[23]=R16(0x04000100)|((u32)R16(0x04000104)<<16);
    p[24]=R16(0x04000108)|((u32)R16(0x0400010c)<<16);
    p[25]=1;p[26]=R16(0x04000508);p[27]=0;
    if(p[20]&0x4000){gRtsP4.error=4096;return;}
    while(!(R16(0x04000184)&0x100))
    {
        u32 n=gRtsP4.to7.count;
        if(n==16){gRtsP4.error=4096;return;}
        gRtsP4.to7.data[n]=R32(0x04100000);gRtsP4.to7.count=n+1;
    }
}
static void restoreDevice7(void)
{
    const u32* p=gRtsSoundShadow.reserved;
    R16(0x04000180)=p[19]&0x4f00;
    R16(0x04000184)=(p[20]&0x8404)|0x4000; // No FIFO clear after target replay.
    R16(0x04000304)=p[20]>>16;
    R32(0x04000214)=~p[18];R32(0x04000210)=p[17];
}
__attribute__((noreturn)) static void stop(void){for(;;)__asm__ volatile("nop");}
void rtsP4Arm7Loop(u32 originalIpc)
{
    rtsP4Arm7Begin(originalIpc);
    gRtsP4.ready=1; // Publish sampled audio/FIFO state before ARM9 uses it.
    volatile RtsArm7Mailbox* m=&gRtsArm7Mailbox;
    u32 previous=R16(0x04000006),lastPeer=10,budget=0x04000000,destructive=0;
    for(;;)
    {
        u32 line=R16(0x04000006);
        if(line<previous)++gRtsM2Frames[0];previous=line;
        u32 peer=R16(0x04000180)&15;
        if(peer==14)stop();
        if(peer==13){if(destructive)stop();return;}
        if(peer!=9 && peer!=10)stop();
        if(peer!=lastPeer){lastPeer=peer;budget=0x04000000;}
        if(!budget--)stop();
        u32 request=m->request,command=m->command;
        if(!command || request==m->completed)continue;
        if(command==1){rtsArm7CaptureService(m);continue;}
        u32 error=0;
        if(command==2)
        {destructive=1;if(!rtsArm7RestoreSector(m->block,(const u32*)m->data))error=1;}
        else if(command==3)error=send(&gRtsP4.to9);
        else if(command==4)RtsPrepareSoundRestart(&gRtsP4Scratch.plan,mmio,0);
        else if(command==5)
        {
            if(!destructive)stop();
            restoreDevice7();gRtsP4.ready=1;m->status=0;m->completed=request;
            while(!gRtsP4.release)
            {
                line=R16(0x04000006);if(line<previous)++gRtsM2Frames[0];previous=line;
                if((R16(0x04000180)&15)==14)stop();
            }
            RtsReleaseSoundRestart(&gRtsP4Scratch.plan,mmio,0);
            rtsEnterArm7Continuation((const RtsArm7Context*)&m->context);stop();
        }
        else error=3;
        m->status=error;m->completed=request;
    }
}
