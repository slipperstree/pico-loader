#include <stdint.h>
#include <stddef.h>
#include "RtsSnapshotInfo.h"
#ifdef PICO_RTS_ARM7_CAPTURE
#include "RtsArm7Capture.h"
volatile RtsArm7Mailbox gRtsArm7Mailbox __attribute__((aligned(32)));
#endif
#ifdef PICO_RTS_VIDEO_CAPTURE
#include "RtsVideoCapture.h"
#ifdef PICO_RTS_RESTORE_PROBE
#include "RtsP4.h"
#define gRtsVideo (gRtsP4Scratch.video)
#else
RtsVideoCapture gRtsVideo;
#endif
#endif
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;
#define REG32(a) (*(volatile u32*)(a))
#define REG16(a) (*(volatile u16*)(a))
#define REG8(a) (*(volatile u8*)(a))
#define CARDCTRL 0x040001a4u
#define CMD 0x040001a8u
#define DATA 0x04100010u
#define IPC 0x04000180u
#define WAIT_LIMIT 0x00400000u

#include "worker-state.h"
_Static_assert(offsetof(WorkerState,base)==sizeof(RtsSnapshotInfo),"M2 workspace ABI");
_Static_assert(offsetof(WorkerState,header)==sizeof(RtsSnapshotInfo)+8,"M2 header ABI");
WorkerState gRtsM2;
volatile u32 gRtsM2Frames[8] __attribute__((aligned(32))); // Dedicated cache line, ARM7 writes word 0.
u32 gRtsM2Stack[256] __attribute__((aligned(8)));
#define IO_TIMEOUT_FRAMES 180u
#define IO_CLOCK_STALL_SPINS 0x00100000u
static struct {u32 started,last,spins,sector,error;} ioState;
static void heartbeat(u32 index);

void* memcpy(void* dst,const void* src,size_t size)
{
    u8* d=dst; const u8* s=src;
    for(size_t i=0;i<size;++i)d[i]=s[i];
    return dst;
}
static void clear(void* dst,u32 bytes)
{
    u32* d=dst;
    for (u32 i=0;i<bytes/4;++i)d[i]=0;
}
// One 96x8 pixel line, with its exact VRAM bytes saved for restoration.
// Only digits, M/S, space and slash are needed for the stage/progress display.
const u8 gRtsDigits[10][5]={
 {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},
 {0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},
 {0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
 {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},
 {0x36,0x49,0x49,0x49,0x36},{6,0x49,0x49,0x29,0x1e}};
#define digits gRtsDigits
static u8 glyph(u32 c,u32 x)
{
    if(c>='0' && c<='9')return digits[c-'0'][x];
    static const u8 letters[]="BMLSNAVE/";
    static const u8 shapes[][5]={
        {0x7f,0x49,0x49,0x49,0x36},{0x7f,2,12,2,0x7f},{0x7f,0x40,0x40,0x40,0x40},
        {0x46,0x49,0x49,0x49,0x31},{0x7f,2,4,8,0x7f},{0x7e,9,9,9,0x7e},
        {0x1f,0x20,0x40,0x20,0x1f},{0x7f,0x49,0x49,0x49,0x41},{0x20,0x10,8,4,2}};
    if(c=='O')return digits[0][x];
    for(u32 i=0;i<sizeof(letters)-1;++i)if(c==letters[i])return shapes[i][x];
    return 0;
}
static void progressOpen(void)
{
    WorkerState* s=&gRtsM2;
    s->oldDisplay=REG32(0x04000000);
    s->oldBrightness=REG16(0x0400006c);
    s->oldVramC=REG8(0x04000242);
    REG8(0x04000242)=0x80; // Bank C temporarily in LCDC, framebuffer display.
    volatile u16* fb=(volatile u16*)0x06840000;
    for(u32 y=0;y<8;++y)for(u32 x=0;x<96;++x)s->videoBackup[y*96+x]=fb[y*256+x];
    REG32(0x04000000)=0x000a0000; // Main VRAM display, bank C.
    REG16(0x0400006c)=0;
    s->videoActive=1;
}
static void progress(u32 stage,u32 value)
{
    // 'M2 S5 0128/8288'. A stationary stage identifies where a fault happened.
    u8 text[15]={'M',
#ifdef PICO_RTS_RESTORE_PROBE
    '4'
#elif defined(PICO_RTS_ARM7_CAPTURE)
    '3'
#else
    '2'
#endif
    ,' ','S',(u8)('0'+stage),' ','0','0','0','0','/','8','2','8','8'};
#ifdef PICO_RTS_ARM7_CAPTURE
    #ifdef PICO_RTS_VIDEO_CAPTURE
    text[11]='9';text[12]='8';text[13]='0';text[14]='2';
#else
    text[11]='8';text[12]='4';text[13]='8';text[14]='1';
#endif
#endif
#ifdef PICO_RTS_RESTORE_PROBE
    text[3]=gRtsP4.operation ? 'L' : 'S';text[14]='3';
#endif
    static const u16 place[4]={1000,100,10,1};
    for(u32 field=0;field<(stage==9 ? 2u : 1u);++field)
    {
        u32 number=field ? ioState.sector : value;
        for(u32 i=0;i<4;++i){u8 digit=0;while(number>=place[i]){number-=place[i];++digit;}text[(field ? 11 : 6)+i]='0'+digit;}
    }
    if(stage==8){text[10]=' ';text[11]='B';text[12]=' ';text[13]=' ';text[14]=' ';}
#ifdef PICO_RTS_RESTORE_PROBE
    if(stage==8 && value==1001)memcpy(text,"NO SAVE   B    ",15);
#endif
    volatile u16* fb=(volatile u16*)0x06840000;
    for(u32 y=0;y<8;++y)for(u32 x=0;x<96;++x)fb[y*256+x]=0x8000;
    for(u32 i=0;i<15;++i)for(u32 x=0;x<5;++x){u8 bits=glyph(text[i],x);for(u32 y=0;y<7;++y)if(bits&(1u<<y))fb[y*256+i*6+x]=0xffff;}
}
static void progressClose(void)
{
    WorkerState* s=&gRtsM2;
    if(!s->videoActive)return;
    volatile u16* fb=(volatile u16*)0x06840000;
    for(u32 y=0;y<8;++y)for(u32 x=0;x<96;++x)fb[y*256+x]=s->videoBackup[y*96+x];
    REG32(0x04000000)=s->oldDisplay;
    REG16(0x0400006c)=s->oldBrightness;
    REG8(0x04000242)=s->oldVramC;
    s->videoActive=0;
}

static const u32 crcNibble[16]={0x00000000u,0x1db71064u,0x3b6e20c8u,0x26d930acu,0x76dc4190u,0x6b6b51f4u,0x4db26158u,0x5005713cu,0xedb88320u,0xf00f9344u,0xd6d6a3e8u,0xcb61b38cu,0x9b64c2b0u,0x86d3d2d4u,0xa00ae278u,0xbdbdf21cu};
static u32 crc(u32 value,const u32* words,u32 count)
{
    for (u32 i=0;i<count;++i)
    {
        value^=words[i];
        for(u32 nibble=0;nibble<8;++nibble)value=(value>>4)^crcNibble[value&15];
    }
    return value;
}
static int mapSector(u32 index,u32* result)
{
    RtsSnapshotInfo* m=&gRtsM2.info;
    if (m->magic!=RTS_M2_MAGIC || m->version!=RTS_M2_VERSION || m->gameCode!=RTS_M2_GAME ||
        m->fileSectors!=RTS_M2_FILE_SECTORS || !m->extentCount || m->extentCount>RTS_M2_MAX_EXTENTS ||
        m->dataStart>=m->dataEnd || index>=RTS_M2_FILE_SECTORS)return 0;
    u32 total=0;
    for (u32 i=0;i<m->extentCount;++i)
    {
        RtsM2Extent e=m->extents[i];
        if (!e.count || e.sector<m->dataStart || e.sector>=m->dataEnd || e.count>m->dataEnd-e.sector ||
            e.count>RTS_M2_FILE_SECTORS-total)return 0;
        for(u32 j=0;j<i;++j)
        {
            RtsM2Extent p=m->extents[j];
            if(e.sector<p.sector+p.count && p.sector<e.sector+e.count)return 0;
        }
        total+=e.count;
    }
    if (total!=RTS_M2_FILE_SECTORS)return 0;
    for (u32 i=0;i<m->extentCount;++i)
    {
        RtsM2Extent e=m->extents[i];
        if(index<e.count){*result=e.sector+index;return 1;}
        index-=e.count;
    }
    return 0;
}
// A CPU-speed-independent deadline spans the entire sector transaction.
// The spin fallback applies only if the independent ARM7 frame clock stops.
static void beginIo(u32 sector)
{
    ioState.started=ioState.last=gRtsM2Frames[0];
    ioState.spins=IO_CLOCK_STALL_SPINS;ioState.sector=sector;ioState.error=0;
}
static int ioWaitAllowed(u32 reason)
{
    u32 now=gRtsM2Frames[0];
    if(now-ioState.started>=IO_TIMEOUT_FRAMES){ioState.error=reason;return 0;}
    if(now!=ioState.last)
    {
        ioState.last=now;ioState.spins=IO_CLOCK_STALL_SPINS;
        heartbeat((now&1u)*16u);
    }
    else if(!ioState.spins--){ioState.error=7;return 0;}
    return 1;
}
static int waitBits(u32 bits,u32 desired,u32 reason)
{
    while((REG32(CARDCTRL)&bits)!=desired)if(!ioWaitAllowed(reason))return 0;
    return 1;
}
static void command(u32 first,u32 argument,u32 settings)
{
    // DS command bytes are sent in address order; the sector is big endian.
    REG32(CMD)=first;
    REG8(CMD+4)=argument>>24;REG8(CMD+5)=argument>>16;
    REG8(CMD+6)=argument>>8;REG8(CMD+7)=argument;
    REG8(0x040001a1)=0x80;
    REG32(CARDCTRL)=settings;
}
static int ready(void)
{
    for(;;)
    {
        command(0xe4,0,0xa7446000);
        if(!waitBits(0x00800000,0x00800000,4))return 0;
        u32 response=REG32(DATA);
        if(!waitBits(0x80000000,0,5))return 0;
        if(response)return 1;
        if(!ioWaitAllowed(6))return 0;
    }
    return 0;
}
static int readSector(u32 index,u32* out)
{
    beginIo(index);
    u32 sector;
    if(!mapSector(index,&sector)){ioState.error=1;return 0;}
    command(0xe3,sector,0xa0406000);
    if(!waitBits(0x80000000,0,3) || !ready())return 0;
    command(0xe5,0,0xa1444000);
    for(u32 i=0;i<128;++i)
    {
        if(!waitBits(0x00800000,0x00800000,2))return 0;
        out[i]=REG32(DATA);
    }
    return waitBits(0x80000000,0,3);
}
static int writeSector(u32 index,const u32* src)
{
    beginIo(index);
    u32 sector;
    if(!mapSector(index,&sector)){ioState.error=1;return 0;}
    command(0x9b0de1f6,sector,0xe1486000);
    for(u32 i=0;i<128;++i)
    {
        if(!waitBits(0x00800000,0x00800000,2))return 0;
        REG32(DATA)=src[i];
    }
    return waitBits(0x80000000,0,3) && ready();
}
static void heartbeat(u32 index)
{
    if((index&15)==0)
    {
        u16 ipc=REG16(IPC);
        REG16(IPC)=(ipc&~0xf00u)|((index&16) ? 0x900 : 0xa00);
    }
}
static void signalDone(void)
{
#ifdef PICO_RTS_RESTORE_PROBE
    rtsP4ReplayCurrent();
#endif
    REG16(IPC)=(REG16(IPC)&~0xf00u)|0xd00;
    for(u32 i=0;i<WAIT_LIMIT;++i)if((REG16(IPC)&15)!=12)return;
}
__attribute__((noreturn)) static void fault(u32 code)
{
    if(ioState.error)code=code*1000+ioState.error;
    gRtsM2.header.error=code;
    if(gRtsM2.videoActive)progress(9,code);
    REG16(IPC)=(REG16(IPC)&~0xf00u)|0xe00;
    REG16(0x0400006c)=0; // Keep the stage/error line readable.
    REG16(0x0400106c)=0x4010;
    // Fail closed after a transport error: do not resume game save callbacks
    // with an unknown card transaction still pending. User must reboot.
    for(;;)__asm__ volatile("nop");
}
__attribute__((noinline,target("arm"))) static void flushCaches(void)
{
    u32 zero=0;
    for(u32 way=0;;way+=0x40000000)
    {
        for(u32 line=0;line<0x400;line+=32)
        {
            u32 index=way|line;
            __asm__ volatile("mcr p15,0,%0,c7,c10,4\n mcr p15,0,%1,c7,c14,2"::"r"(zero),"r"(index):"memory");
        }
        if(way==0xc0000000)break;
    }
    __asm__ volatile("mcr p15,0,%0,c7,c10,4"::"r"(zero):"memory");
}

static void waitFrames(u32 frames)
{
    u32 previous=REG16(0x04000006),budget=WAIT_LIMIT;
    while(frames && budget--)
    {
        u32 current=REG16(0x04000006);
        if(current<previous){--frames;budget=WAIT_LIMIT;}
        previous=current;
    }
}
// Require a fresh B press, so keys already held on entry cannot dismiss S8.
// Both CPUs remain parked; keep the existing ARM7 watchdog alive while the
// user reads the reason. This path never performs card I/O.
static void waitRefusalAck(void)
{
    u32 tick=0;
    int released=0;
    for(;;)
    {
        heartbeat((tick++ & 1u)*16u);
        if(REG16(0x04000130)&2u)released=1;
        else if(released)return;
        waitFrames(1);
    }
}
static u32 asynchronousBusy(void)
{
    u32 mask=REG32(0x04000064)&0x80000000 ? 2048 : 0;
    for(u32 i=0;i<4;++i)if(REG32(0x040000b8+i*12)&0x80000000)mask|=16u<<i;
    if(REG32(CARDCTRL)&0x80000000)mask|=4;
    if(REG16(0x040001a0)&0x80)mask|=8;
    return mask;
}
static void showRefusal(u32 reason)
{
    // A live DMA/capture may own VRAM. In that case use only the same readable
    // brightness controls as M1, and leave all VRAM mappings untouched.
    if(reason & (0xf0u|512u|1024u|2048u|16384u))
    {
        u16 a=REG16(0x0400006c),b=REG16(0x0400106c);
        for(u32 n=0;n<3;++n)
        {
            REG16(0x0400006c)=0x400c;REG16(0x0400106c)=0x400c;waitFrames(8);
            REG16(0x0400006c)=0x8008;REG16(0x0400106c)=0x8008;waitFrames(8);
        }
        REG16(0x0400006c)=a;REG16(0x0400106c)=b;
    }
    else
    {
        progressOpen();progress(8,reason);waitRefusalAck();progressClose();
    }
}

#ifdef PICO_RTS_ARM7_CAPTURE
__attribute__((noinline,noinline,target("arm"))) static const u32* arm7Block(u32 block)
{
    volatile RtsArm7Mailbox* m=&gRtsArm7Mailbox;
    m->block=block;
    u32 request=m->request+1;
    m->request=request;
    __asm__ volatile("mcr p15,0,%0,c7,c10,4"::"r"(0):"memory");
    m->command=1;
    __asm__ volatile("mcr p15,0,%0,c7,c10,4"::"r"(0):"memory");
    beginIo(0x40c200/512+1+block);
    while(m->completed!=request)if(!ioWaitAllowed(8))fault(8);
    m->command=0;
    if(m->status){ioState.error=20+m->status;fault(8);}
    return (const u32*)m->data;
}
#endif
__attribute__((noinline,target("arm"))) static void readCpu(u32* p)
{
    __asm__ volatile("mrc p15,0,%0,c1,c0,0\n mrc p15,0,%1,c9,c1,0\n mrc p15,0,%2,c9,c1,1\n mrc p15,0,%3,c2,c0,1\n mrc p15,0,%4,c3,c0,0":"=r"(p[0]),"=r"(p[1]),"=r"(p[2]),"=r"(p[3]),"=r"(p[4]));
}
__attribute__((noinline,target("arm"))) static void invalidateLine(u32 a){__asm__ volatile("mcr p15,0,%0,c7,c6,1"::"r"(a):"memory");}
__attribute__((noinline,target("arm"))) static void setCache(u32 ci,u32 buffer,u32 control)
{
    __asm__ volatile("mcr p15,0,%0,c7,c10,4\n mcr p15,0,%0,c7,c5,0\n mcr p15,0,%1,c2,c0,1\n mcr p15,0,%2,c3,c0,0\n mcr p15,0,%3,c1,c0,0"::"r"(0),"r"(ci),"r"(buffer),"r"(control):"memory");
}
void rtsM2Run(const u32* entryRegs)
{
    WorkerState* s=&gRtsM2;
    RtsM2Header* h=&s->header;
    // r12 in the worker wrapper carries the secure stub's region-2 guard.
    const u32* frame=entryRegs+14;
#ifdef PICO_RTS_RESTORE_PROBE
    rtsP4Arm9Begin();
    u32 captureFlags=RTS_P4_EXPERIMENT_FLAG|(s->header.flags&RTS_M2_FLAG_NO_READBACK);
#else
    u32 captureFlags=s->header.flags==3 ? 3 : 1;
#endif
    u32 initialCpu[5];readCpu(initialCpu);
    u32 control=initialCpu[0],dtcm=initialCpu[1],itcm=initialCpu[2];
    // Finish hardware work already in flight; no CPU callback is resumed.
    // One-shot DMA and display capture can clear themselves at the next frame.
    if(asynchronousBusy())waitFrames(2);
    u32 reason=asynchronousBusy();
    if((control&0x50001)!=0x50001 || (dtcm&0x3f)!=10 || itcm!=0x20 ||
       (dtcm&~0xfffu)<0x02400000 || (dtcm&~0xfffu)>0x02ffc000)reason|=1;
#ifdef PICO_RTS_VIDEO_CAPTURE
    if(!RtsPrepareVideoCapture(&gRtsVideo,frame[0],frame[1]))reason|=16384;
#endif
    u16 oldExmem=REG16(0x04000204);
    // ARM7 publishes into an otherwise read-only cache line. Invalidate only
    // that line before reading the shared diagnostic word; never clean stale data.
    u32 shared=(u32)&s->info.reserved;
    invalidateLine(shared);
    reason|=s->info.reserved;
#ifdef PICO_RTS_RESTORE_PROBE
    // CPU9 can show a safe stage before ARM7's new C preflight. This makes a
    // failed ARM7 entry distinguishable from SD I/O, and gives it a deadline.
    if(!reason){progressOpen();progress(0,0);}

#endif
    u32 first;
    if(!mapSector(0,&first))reason|=256;
    if(reason)
    {
        h->error=reason;
#ifdef PICO_RTS_RESTORE_PROBE
        progressClose();
#endif
        showRefusal(reason);
        signalDone();return; // Never issue SD commands after a refusal.
    }
    // ARM7 published C only after its whole SD transaction and hardware guards.
    // Both CPUs stay parked. Borrow Slot-1 only, preserving all other EXMEM bits.
    if(oldExmem&0x800)
    {
        REG16(0x04000204)=oldExmem&~0x800u;
        if(REG16(0x04000204)&0x800)
        {
            REG16(0x04000204)=oldExmem;
            progressClose();showRefusal(2);signalDone();return;
        }
    }
    if(!s->videoActive)progressOpen();
    progress(1,0);
    clear(h,sizeof(*h));
    h->magic=RTS_M2_MAGIC;h->version=RTS_M2_VERSION;h->fileBytes=RTS_M2_FILE_BYTES;h->gameCode=RTS_M2_GAME;
    h->payloadBytes=RTS_M2_PAYLOAD_BYTES;h->workspaceBase=s->base;h->workspaceBytes=s->bytes;
    h->dtcmBase=dtcm&~0xfffu;h->dtcmBytes=0x4000;h->itcmBase=0x01ff8000;h->itcmBytes=0x8000;
    h->control=control;h->dtcmConfig=dtcm;h->itcmConfig=itcm;
    for(u32 i=0;i<4;++i)h->regs[i]=frame[6+i];
    for(u32 i=4;i<12;++i)h->regs[i]=entryRegs[i];
    h->regs[12]=frame[10];h->regs[13]=(u32)(frame+12);h->regs[14]=frame[11];h->regs[15]=entryRegs[13];
    h->reserved[0]=entryRegs[12]; // Original protected MPU region 2.
    h->reserved[1]=oldExmem; // Original Slot-1 ownership and wait settings.
    h->gateCpsr=frame[4];h->frameAddress=(u32)frame;h->flags=captureFlags; // diagnostic; bit 1 explicitly marks no full readback
    progress(2,0);
#ifdef PICO_RTS_RESTORE_PROBE
    rtsP4FreezeHeader();
#ifdef PICO_RTS_CPU_TRACE
    progress(2,30);
#endif
#endif
    u32 oldCi=initialCpu[3],oldBuffer=initialCpu[4];
    h->reserved[2]=oldCi;h->reserved[3]=oldBuffer;
    u32 transientCi=oldCi|2u,transientControl=(control&~4u)|0x1000u;
#ifdef PICO_RTS_RESTORE_PROBE
    // Prepare C locals/header before the final clean. The assembly transition
    // saves its own registers before cleaning and has no intervening stack write.
    rtsFlushCachesAndEnter(transientCi,0,transientControl,(RtsArm9CpuState*)s->readback);
#else
    flushCaches();
    setCache(transientCi,0,transientControl);
#endif
#ifdef PICO_RTS_CPU_TRACE
    progress(2,32);
#endif

#ifdef PICO_RTS_ARM7_CAPTURE
#ifndef PICO_RTS_RESTORE_PROBE
    if(gRtsArm7Mailbox.context.magic!=RTS_ARM7_CONTEXT_MAGIC || gRtsArm7Mailbox.status){ioState.error=25;fault(8);}
#endif
    h->reserved[8]=0x31433741; // ARM7 context marker and fixed diagnostic layout.
    h->reserved[9]=0x40c000;h->reserved[10]=512;h->reserved[11]=0x18000;
#endif
#ifdef PICO_RTS_VIDEO_CAPTURE
    h->reserved[12]=RTS_VIDEO_MAGIC;h->reserved[13]=0x424200;h->reserved[14]=RTS_VIDEO_SECTION_BYTES;
#endif
    h->reserved[4]=RTS_M2_TIMING_MAGIC;
    u32 started=gRtsM2Frames[0];
    u16 aux=REG16(0x040001a0);
    u32 oldCommand0=REG32(CMD),oldCommand1=REG32(CMD+4),oldCardControl=REG32(CARDCTRL);
#ifdef PICO_RTS_RESTORE_PROBE
    // S2 is already visible. D-cache and write buffering are OFF before
    // telling ARM7 to start its new main-RAM capture/prepare path.
#ifdef PICO_RTS_CPU_TRACE
    progress(2,33);
#endif
    if(!rtsP4Start7())fault(81);
#ifdef PICO_RTS_CPU_TRACE
    progress(2,34);
#endif
    u32 p4Reason=gRtsP4.error|s->info.reserved;
    if(!p4Reason && (gRtsArm7Mailbox.context.magic!=RTS_ARM7_CONTEXT_MAGIC || gRtsArm7Mailbox.status))p4Reason=8192;
    if(!p4Reason)p4Reason=rtsP4FreezePayload();
#ifdef PICO_RTS_CPU_TRACE
    progress(2,35);
#endif
    if(p4Reason){progress(8,p4Reason);waitRefusalAck();goto cleanup;}
    if(gRtsP4.operation)
    {
#ifdef PICO_RTS_CPU_TRACE
        progress(8,1007);waitRefusalAck();goto cleanup;
#else
        RtsP4CardState card={aux,oldCommand0,oldCommand1,oldCardControl,oldExmem};
        p4Reason=rtsP4Load(&card);progress(8,p4Reason);waitRefusalAck();goto cleanup;
#endif
    }
#endif
    progress(3,0);
    if(!readSector(0,s->readback))fault(1);
    const RtsM2Header* previous=(const RtsM2Header*)s->readback;
    if(previous->magic!=RTS_M2_MAGIC || previous->version!=RTS_M2_VERSION ||
       previous->fileBytes!=RTS_M2_FILE_BYTES || previous->gameCode!=RTS_M2_GAME ||
       previous->payloadBytes!=RTS_M2_PAYLOAD_BYTES)fault(2);
    h->sequence=previous->sequence+1;
    h->phase=1; // invalidate completion BEFORE touching the previous payload
    progress(4,0);
#ifdef PICO_RTS_RESTORE_PROBE
    rtsP4SealHeader(h);
#endif
    if(!writeSector(0,(const u32*)h))fault(3);
    u32 writeStarted=gRtsM2Frames[0];
    u32 value=~0u;
    for(u32 index=0;index<RTS_M2_PAYLOAD_BYTES/512;++index)
    {
        const u32* src;
        if(index<0x400000/512)
        {
            u32 address=0x02000000+index*512;
            if(address>=s->base && address<s->base+s->bytes)
            {
                // Header readback is no longer needed during payload writes.
                // Reuse its sector buffer for workspace exclusion, retaining
                // the bounded arena reservation despite the diagnostic features.
                clear(s->readback,sizeof(s->readback));src=s->readback;
            }
            else src=(const u32*)address;
        }
        else if(index<(0x400000+0x4000)/512)src=(const u32*)(h->dtcmBase+(index-0x400000/512)*512);
        else if(index<0x40c000/512)src=(const u32*)(0x01ff8000+(index-(0x400000+0x4000)/512)*512);
#ifdef PICO_RTS_ARM7_CAPTURE
        else if(index==0x40c000/512)src=(const u32*)&gRtsArm7Mailbox.context;
        else if(index<0x424200/512)src=arm7Block(index-0x40c000/512-1);
#ifdef PICO_RTS_VIDEO_CAPTURE
        else if(index==0x424200/512)src=(const u32*)&gRtsVideo;
#ifdef PICO_RTS_RESTORE_PROBE
        else if(index==RTS_P4_SOUND_OFFSET/512)src=(const u32*)&gRtsSoundShadow;
#endif
        else
        {
            if(!RtsReadVideoSector(&gRtsVideo,index-0x424200/512-1,(u16*)s->readback,s->videoBackup))
            {ioState.error=26;fault(8);}
            src=s->readback;
        }
#endif
#endif
        value=crc(value,src,128);
        if(!writeSector(index+1,src))fault(4);
        heartbeat(index);
        if((index&63)==0)progress(5,index);
    }
    h->payloadCrc=~value;
    h->reserved[5]=gRtsM2Frames[0]-writeStarted;
    if(!(h->flags&RTS_M2_FLAG_NO_READBACK))
    {
        u32 verifyStarted=gRtsM2Frames[0];
        value=~0u;
        for(u32 index=0;index<RTS_M2_PAYLOAD_BYTES/512;++index)
        {
            if(!readSector(index+1,s->readback))fault(5);
            value=crc(value,s->readback,128);
            heartbeat(index);
            if((index&63)==0)progress(6,index);
        }
        h->verifyCrc=~value;
        h->reserved[6]=gRtsM2Frames[0]-verifyStarted;
        if(h->verifyCrc!=h->payloadCrc)fault(6);
    }
    // Fast mode leaves verifyCrc at zero; never pretend a readback happened.
    h->reserved[7]=gRtsM2Frames[0]-started;
    progress(7,RTS_M2_PAYLOAD_BYTES/512);
    h->phase=2;
#ifdef PICO_RTS_RESTORE_PROBE
    rtsP4SealHeader(h);
#endif
    if(!writeSector(0,(const u32*)h) || !readSector(0,s->readback))fault(7);
    for(u32 i=0;i<128;++i)if(s->readback[i]!=((u32*)h)[i])fault(8);
#ifdef PICO_RTS_RESTORE_PROBE
    gRtsP4SavedSequence=h->sequence;gRtsP4FreshSlot=1;
cleanup:
    rtsP4ReplayCurrent();
#endif
    REG32(CMD)=oldCommand0;REG32(CMD+4)=oldCommand1;
    REG16(0x040001a0)=aux;
    REG32(CARDCTRL)=oldCardControl&0x7f7fffff;
    setCache(oldCi,oldBuffer,control);
    REG16(0x04000204)=oldExmem;
    if((REG16(0x04000204)^oldExmem)&0x800)fault(9);
    progressClose();
    signalDone();
}

#ifdef PICO_RTS_RESTORE_PROBE
__attribute__((noinline,target("arm"))) void rtsP4InvalidateLine(uint32_t a){__asm__ volatile("mcr p15,0,%0,c7,c6,1"::"r"(a):"memory");}
__attribute__((noinline,target("arm"))) uint32_t rtsP4GetControl(void){uint32_t c;__asm__ volatile("mrc p15,0,%0,c1,c0,0":"=r"(c));return c;}
__attribute__((noinline,target("arm"))) void rtsP4Drain(void){__asm__ volatile("mcr p15,0,%0,c7,c10,4"::"r"(0):"memory");}
uint32_t RtsP4Crc(uint32_t v,const uint32_t* p,uint32_t n){return crc(v,p,n);}
int RtsP4ReadSector(uint32_t i,uint32_t* p){return readSector(i,p);}
void RtsP4Progress(uint32_t stage,uint32_t value){progress(stage,value);}
void RtsP4Heartbeat(uint32_t index){heartbeat(index);}
void RtsP4Fault(uint32_t code){fault(code);}
#endif
