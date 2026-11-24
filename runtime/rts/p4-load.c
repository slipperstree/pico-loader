#include <string.h>
#include "RtsP4.h"
#include "RtsArm7Restore.h"
#include "worker-state.h"
typedef uint32_t u32;typedef uint16_t u16;typedef uint8_t u8;
#define R32(a) (*(volatile u32*)(a))
#define R16(a) (*(volatile u16*)(a))
#define R8(a) (*(volatile u8*)(a))
extern volatile RtsArm7Mailbox gRtsArm7Mailbox;
static struct {u32 replayed,drained9,started7;} own __attribute__((aligned(32)));
#define replayed own.replayed
#define drained9 own.drained9
#define started7 own.started7
static const u32 vramControl[9]={0x04000240,0x04000241,0x04000242,0x04000243,0x04000244,0x04000245,0x04000246,0x04000248,0x04000249};
static const u32 vramEnd[9]={0x20000,0x40000,0x60000,0x80000,0x90000,0x94000,0x98000,0xa0000,0xa4000};
static void checkedRead(u32 sector,u32* out){if(!RtsP4ReadSector(sector,out))RtsP4Fault(1);}
static int same(const void* a,const void* b,u32 n)
{const u8* x=a;const u8* y=b;for(u32 i=0;i<n;++i)if(x[i]!=y[i])return 0;return 1;}
static void zero(void* p,u32 n){u32* d=p;for(u32 i=0;i<n/4;++i)d[i]=0;}
void rtsP4Arm9Begin(void)
{
#ifdef PICO_RTS_LIVE_RESTORE
    gRtsM2.readback=(u32*)gRtsArm7Mailbox.data;
#endif
    rtsP4InvalidateLine((u32)&gRtsP4);
    replayed=0;drained9=0;started7=0;
}
u32 rtsP4Start7(void)
{
    // Caller already disabled D-cache AND write buffering. Direct volatile
    // stores/reads are sufficient: no cache maintenance in this wait path.
#ifdef PICO_RTS_CPU_TRACE
    RtsP4Progress(2,40);
#endif
    gRtsP4.ready=0;
#ifdef PICO_RTS_CPU_TRACE
    RtsP4Progress(2,41);
#endif
    if(rtsP4SendStart7((RtsArm9CpuState*)gRtsM2.readback)!=0x800)
        RtsP4Fault(8128); // Local outgoing nibble must latch before waiting.
#ifdef PICO_RTS_CPU_TRACE
    RtsP4Progress(2,42);
#endif
    u32 previous=R16(0x04000006),frames=0,last=~0u;
    for(u32 spins=0x400000;spins;--spins)
    {
        if(gRtsP4.ready){started7=1;RtsP4Heartbeat(0);return 1;}
        u32 peer=R16(0x04000180)&15;
        if(peer!=last)
        {
            last=peer;
#ifdef PICO_RTS_CPU_TRACE
            RtsP4Progress(2,60+peer);
#endif
        }
        u32 line=R16(0x04000006);
        if(line<previous && ++frames>=180)return 0;
        previous=line;
    }
    return 0;
}

int rtsP4Request(u32 command,u32 block)
{
    volatile RtsArm7Mailbox* m=&gRtsArm7Mailbox;u32 seq=m->request+1;
    m->block=block;m->request=seq;
    rtsP4Drain();
    m->command=command;
    u32 start=gRtsM2Frames[0],last=start,budget=0x100000;
    while(m->completed!=seq)
    {
        u32 now=gRtsM2Frames[0];
        if(now-start>=180)RtsP4Fault(8008);
        if(now!=last){last=now;budget=0x100000;RtsP4Heartbeat((now&1)*16);}
        else if(!budget--)RtsP4Fault(8007);
    }
    m->command=0;if(m->status)RtsP4Fault(8020+m->status);return 1;
}
void rtsP4Drain9(void)
{
    gRtsP4.to9.count=0;
    if(R16(0x04000184)&0x4000){gRtsP4.error=4201;return;}
    while(!(R16(0x04000184)&0x100))
    {
        u32 n=gRtsP4.to9.count;if(n==16)RtsP4Fault(8031);
        gRtsP4.to9.data[n]=R32(0x04100000);gRtsP4.to9.count=n+1;
    }
    drained9=1;
}
static void send7(void)
{
    u32 n=gRtsP4.to7.count;if(n>16)RtsP4Fault(8031);
    for(u32 i=0;i<n;++i){if(R16(0x04000184)&2)RtsP4Fault(8032);R32(0x04000188)=gRtsP4.to7.data[i];}
}
void rtsP4ReplayCurrent(void)
{
    if(replayed || !started7)return;
    u32 control=rtsP4GetControl();
    if(control&4)
    {
        // Early refusal, before D-cache off: never clean ARM7-owned lines.
        for(u32 i=0;i<96;i+=32){u32 a=(u32)&gRtsP4.to7+i;rtsP4InvalidateLine(a);}
        if(drained9)RtsP4Fault(8033); // Caller must replay before cache restoration.
    }
    send7();if(drained9)rtsP4Request(3,0);replayed=1;
}
static u32 headerCrc(RtsM2Header* h)
{u32 saved=h->reserved[82];h->reserved[82]=0;u32 value=~RtsP4Crc(~0u,(const u32*)h,128);h->reserved[82]=saved;return value;}
void rtsP4SealHeader(RtsM2Header* h){h->reserved[82]=headerCrc(h);}
u32 rtsP4FreezeHeader(void)
{
    WorkerState* s=&gRtsM2;RtsM2Header* h=&s->header;
    rtsCaptureArm9Cpu((RtsArm9CpuState*)s->readback,h->regs[13],h->regs[14],h->reserved[0]);
#ifdef PICO_RTS_CPU_TRACE
    RtsP4Progress(2,29);
#endif
    memcpy(h->reserved+16,s->readback,184);memcpy(h->reserved+62,&gRtsP4Identity,80);
    h->reserved[15]=RTS_P4_MAGIC;h->reserved[83]=R32(0x04000210);h->reserved[84]=R32(0x04000214);
    h->reserved[85]=((const u32*)h->frameAddress)[2]|((u32)R16(0x04000184)<<16);
    h->reserved[86]=R16(0x04000102)|((u32)R16(0x04000106)<<16);
    h->reserved[87]=R16(0x0400010a)|((u32)R16(0x0400010e)<<16);
    h->reserved[88]=R16(0x04000304);h->reserved[89]=1; // Experimental format; internal graphics state remains incomplete.
    return 0;
}
u32 rtsP4FreezePayload(void)
{
    if(gRtsP4.error)return gRtsP4.error;
    const u32* io=gRtsSoundShadow.reserved;
    u32 detail=0;
    if(RtsBuildSoundRestartDetailed(&gRtsSoundShadow,io,io[16]&65535,io[16]>>16,io[26],0,&detail))return detail;
    rtsP4Drain9();if(gRtsP4.error)return gRtsP4.error;
    RtsVideoCapture* v=&gRtsP4Scratch.video;
    for(u32 i=0;i<16;++i)v->reserved[i]=R32(0x04000640+i*4);
    for(u32 i=0;i<9;++i)v->reserved[16+i]=R32(0x04000680+i*4);
    v->reserved[64]=gRtsP4.to9.count;v->reserved[65]=gRtsP4.to7.count;
    for(u32 i=0;i<16;++i){v->reserved[32+i]=gRtsP4.to9.data[i];v->reserved[48+i]=gRtsP4.to7.data[i];}
    return 0;
}
static int guestRead(void* user,u32 a,void* out,u32 bytes)
{
    (void)user;RtsM2Header* h=&gRtsM2.header;u32 offset;
    if(a>=0x02000000 && a<0x02400000){if(bytes>0x02400000-a)return 0;offset=a-0x02000000;}
    else if(a>=h->dtcmBase && a<h->dtcmBase+0x4000){if(bytes>h->dtcmBase+0x4000-a)return 0;offset=0x400000+a-h->dtcmBase;}
    else if(a>=0x01ff8000 && a<0x02000000){if(bytes>0x02000000-a)return 0;offset=0x404000+a-0x01ff8000;}
    else if(a>=0x03800000 && a<0x04000000){if(bytes>0x10000-(a&65535))return 0;offset=0x40c200+(a&65535);}
    else if(a>=0x03000000 && a<0x03800000){if(bytes>0x8000-(a&32767))return 0;offset=0x41c200+(a&32767);}
    else return 0;
    offset+=512;u8* dst=out;
    while(bytes){u32 inside=offset&511,n=512-inside;if(n>bytes)n=bytes;checkedRead(offset/512,gRtsM2.readback);memcpy(dst,(u8*)gRtsM2.readback+inside,n);dst+=n;offset+=n;bytes-=n;}
    return 1;
}
static void writeVideo(u32 offset,const u16* source)
{
    WorkerState* s=&gRtsM2;u32 a,bank=9;u8 old=0;
    if(offset<0xa4000)
    {
        bank=0;while(offset>=vramEnd[bank])++bank;
        old=R8(vramControl[bank]);R8(vramControl[bank])=0x80;(void)R8(vramControl[bank]);
        a=0x06800000+offset;
        if(bank==2 && offset-0x40000<RTS_PROGRESS_HEIGHT*512)
            for(u32 i=0;i<RTS_PROGRESS_WIDTH;++i)s->videoBackup[(offset-0x40000)/512*RTS_PROGRESS_WIDTH+i]=source[i];
    }
    else a=(offset<0xa4800 ? 0x05000000 : 0x07000000)+((offset-0xa4000)&2047);
    for(u32 i=0;i<256;++i)R16(a+i*2)=source[i];
    if(bank<9){R8(vramControl[bank])=old;(void)R8(vramControl[bank]);}
}
static void finishDisplay(const RtsVideoCapture* v)
{
    WorkerState* s=&gRtsM2;
    for(u32 y=0;y<RTS_PROGRESS_HEIGHT;++y)for(u32 x=0;x<RTS_PROGRESS_WIDTH;++x)R16(0x06840000+y*512+x*2)=s->videoBackup[y*RTS_PROGRESS_WIDTH+x];
    for(u32 i=0;i<9;++i)R8(vramControl[i])=v->vram[i];
    for(u32 i=0;i<8;++i)R16(0x04000008+(i&3)*2+(i>=4 ? 0x1000 : 0))=v->bgControl[i];
    R16(0x04000304)=v->power;R32(0x04000000)=v->display[0];R32(0x04001000)=v->display[1];
    R16(0x0400006c)=v->brightness[0];R16(0x0400106c)=v->brightness[1];s->videoActive=0;
}
u32 rtsP4Load(const RtsP4CardState* card)
{
    WorkerState* s=&gRtsM2;RtsM2Header* h=&s->header;RtsArm9RestoreTail tail;
    checkedRead(0,s->readback);RtsM2Header* old=(RtsM2Header*)s->readback;
    if(old->magic==RTS_P4_MAGIC && old->version==RTS_P4_VERSION && old->phase!=2)return 1001;
    if(old->magic!=RTS_P4_MAGIC || old->version!=RTS_P4_VERSION || old->fileBytes!=RTS_P4_FILE_BYTES || old->payloadBytes!=RTS_P4_PAYLOAD_BYTES ||
       old->gameCode!=RTS_M2_GAME || old->phase!=2 || old->error || (old->flags!=4 && old->flags!=6) || headerCrc(old)!=old->reserved[82])return 1002;
    if(!same(old->reserved+62,&gRtsP4Identity,32))return 1003;
    if(!same(old->reserved+70,gRtsP4Identity.build,32))return 1009;
    if(old->workspaceBase!=s->base || old->workspaceBytes!=s->bytes || !gRtsP4TailAddress ||
       !same(old->reserved+43,h->reserved+43,76) || old->reserved[86]!=h->reserved[86] || old->reserved[87]!=h->reserved[87] ||
       old->reserved[1]!=card->exmem || old->reserved[16]!=RTS_ARM9_CPU_MAGIC || old->reserved[17]!=1 ||
       old->reserved[60] || old->reserved[59])return 1005;
    memcpy(h,old,512);
    u32 value=~0u;
    for(u32 i=0;i<RTS_P4_PAYLOAD_BYTES/512;++i)
    {checkedRead(i+1,s->readback);value=RtsP4Crc(value,s->readback,128);RtsP4Heartbeat(i);if(!(i&63))RtsP4Progress(1,i);}
    if(~value!=h->payloadCrc)return 1004;
    // Capture format remains fixed and tightly scoped. All context checks read
    // file bytes, not the current game that is about to be overwritten.
    if(RtsBuildArm9Continuation(h,1,guestRead,0,&tail.continuation))return 1005;
    checkedRead(1+0x40c000/512,s->readback);memcpy((void*)&gRtsArm7Mailbox.context,s->readback,512);
    if(RtsValidateArm7Continuation((const RtsArm7Context*)&gRtsArm7Mailbox.context,s->base,s->bytes,1,guestRead,0))return 1005;
#ifdef PICO_RTS_LIVE_RESTORE
    const RtsArm7Context* a7=(const RtsArm7Context*)&gRtsArm7Mailbox.context;
    if(a7->parkSp<0x03000000 || a7->parkSp>=0x04000000 ||
       gRtsP4Arm7TailAddress<0x03800000 || gRtsP4Arm7TailAddress>=0x03810000)return 1005;
#endif
    checkedRead(1+0x424200/512,s->readback);
    const RtsVideoCapture* video=(const RtsVideoCapture*)s->readback;
    if(video->magic!=RTS_VIDEO_MAGIC || video->version!=1 || video->vramBytes!=0xa4000 || video->paletteBytes!=2048 || video->oamBytes!=2048 ||
       !same(video->display,gRtsP4Scratch.video.display,8) || !same(video->vram,gRtsP4Scratch.video.vram,36) || video->wram!=3 || video->reserved[64]>16 || video->reserved[65]>16)return 1005;
    // L0 smoke test deliberately leaves internal 3D/write-only state unchanged.
    // It requires the same display configuration; it does not promise scene rollback.
    u32 timer7a=gRtsSoundShadow.reserved[21],timer7b=gRtsSoundShadow.reserved[22];
    checkedRead(1+RTS_P4_SOUND_OFFSET/512,s->readback);memcpy(&gRtsP4Scratch.sound,s->readback,512);
    const u32* io=gRtsP4Scratch.sound.reserved;
    if(io[21]!=timer7a || io[22]!=timer7b || RtsBuildSoundRestart(&gRtsP4Scratch.sound,io,io[16]&65535,io[16]>>16,io[26],0))return 1006;
    // Destructive phase: transport failure now holds both CPUs, never resumes a
    // partly restored game. All code and stacks executing here are in workspace.
    for(u32 i=0;i<RTS_P4_PAYLOAD_BYTES/512;++i)
    {
        checkedRead(i+1,s->readback);
        if(i<0x400000/512)
        {u32 a=0x02000000+i*512;if(a<s->base || a>=s->base+s->bytes)memcpy((void*)a,s->readback,512);}
        else if(i<0x404000/512)memcpy((void*)(h->dtcmBase+(i-0x400000/512)*512),s->readback,512);
        else if(i<0x40c000/512)memcpy((void*)(0x01ff8000+(i-0x404000/512)*512),s->readback,512);
        else if(i==0x40c000/512)memcpy((void*)&gRtsArm7Mailbox.context,s->readback,512);
        else if(i<0x424200/512){memcpy((void*)gRtsArm7Mailbox.data,s->readback,512);rtsP4Request(2,i-0x40c200/512);}
        else if(i==0x424200/512)memcpy(&gRtsP4Scratch.video,s->readback,512);
        else if(i<RTS_P4_SOUND_OFFSET/512)writeVideo((i-0x424400/512)*512,(const u16*)s->readback);
        else memcpy(&gRtsSoundShadow,s->readback,512);
        RtsP4Heartbeat(i);if(!(i&63))RtsP4Progress(2,i);
    }
    RtsVideoCapture* v=&gRtsP4Scratch.video;
    gRtsP4.to9.count=v->reserved[64];gRtsP4.to7.count=v->reserved[65];
    for(u32 i=0;i<16;++i){gRtsP4.to9.data[i]=v->reserved[32+i];gRtsP4.to7.data[i]=v->reserved[48+i];}
    zero(s->readback,512);memcpy(s->readback,h->reserved+16,184);
    RtsArm9CpuState* cpu=(RtsArm9CpuState*)s->readback;
    memcpy(cpu->padding,v,112); // Preserve final readable display state before scratch becomes sound plan.
    finishDisplay((const RtsVideoCapture*)cpu->padding);
    io=gRtsSoundShadow.reserved;
    if(RtsBuildSoundRestart(&gRtsSoundShadow,io,io[16]&65535,io[16]>>16,io[26],&gRtsP4Scratch.plan))RtsP4Fault(8040);
    rtsP4Request(4,0);send7();rtsP4Request(3,0);
    R32(0x040001a8)=card->command0;R32(0x040001ac)=card->command1;R16(0x040001a0)=card->aux;
    R32(0x040001a4)=card->cardControl&0x7f7fffff;
#ifdef PICO_RTS_LIVE_RESTORE
    // Return Slot-1, retaining ARM9 RAM priority until ARM7 has restored all
    // registers and entered its private-WRAM tail.
    R16(0x04000204)=card->exmem&~0x8000u;
    if((R16(0x04000204)^(card->exmem&~0x8000u))&0x8800)RtsP4Fault(9);
    rtsP4Request(5,0);
    u32 previous=R16(0x04000006),frames=0,spins=0x400000;
    while((R16(0x04000180)&15)!=7)
    {
        u32 line=R16(0x04000006);
        if((line<previous && ++frames>=180) || !--spins)
        {RtsP4OpenProgress();RtsP4Fault(8140+(R16(0x04000180)&15));}
        previous=line;
    }
    R16(0x04000204)=card->exmem;
    if((R16(0x04000204)^card->exmem)&0x8800)RtsP4Fault(9);
#else
    R16(0x04000204)=card->exmem;
    if((R16(0x04000204)^card->exmem)&0x800)RtsP4Fault(9);
    rtsP4Request(5,0);
#endif
    R16(0x04000184)=((h->reserved[85]>>16)&0x8404)|0x4000;
    R16(0x04000180)=h->reserved[85]&0x4f00;
    R32(0x04000214)=~h->reserved[84];R32(0x04000210)=h->reserved[83];
    tail.region2=h->reserved[0];tail.control=h->control;
    u32 tailAddress=h->frameAddress-56;memcpy((void*)tailAddress,&tail,sizeof(tail));
    R32(0x04000208)=1;
#ifndef PICO_RTS_LIVE_RESTORE
    gRtsP4.release=1;
#endif
    rtsP4Drain();
    rtsRestoreArm9State(cpu,(const RtsArm9RestoreTail*)tailAddress,(void*)gRtsP4TailAddress);
    RtsP4Fault(8041);return 0;
}
