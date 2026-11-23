#include <stdint.h>
#include <stddef.h>
#include "RtsSnapshotInfo.h"
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

typedef struct {
    RtsSnapshotInfo info;
    u32 base, bytes;
    RtsM2Header header;
    u32 readback[128], zero[128];
    u16 videoBackup[96*8];
    u32 oldDisplay;
    u16 oldBrightness;
    u8 oldVramC, videoActive;
} WorkerState;
_Static_assert(offsetof(WorkerState,base)==sizeof(RtsSnapshotInfo),"M2 workspace ABI");
_Static_assert(offsetof(WorkerState,header)==sizeof(RtsSnapshotInfo)+8,"M2 header ABI");
WorkerState gRtsM2;
u32 gRtsM2Stack[256] __attribute__((aligned(8)));

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
static const u8 digits[10][5]={
 {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},
 {0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},
 {0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
 {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},
 {0x36,0x49,0x49,0x49,0x36},{6,0x49,0x49,0x29,0x1e}};
static u8 glyph(u32 c,u32 x)
{
    if(c>='0' && c<='9')return digits[c-'0'][x];
    if(c=='M'){const u8 a[5]={0x7f,2,12,2,0x7f};return a[x];}
    if(c=='S'){const u8 a[5]={0x46,0x49,0x49,0x49,0x31};return a[x];}
    if(c=='/'){const u8 a[5]={0x20,0x10,8,4,2};return a[x];}
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
    u8 text[15]={'M','2',' ','S',(u8)('0'+stage),' ','0','0','0','0','/','8','2','8','8'};
    static const u16 place[4]={1000,100,10,1};
    for(u32 i=0;i<4;++i){u8 digit=0;while(value>=place[i]){value-=place[i];++digit;}text[6+i]='0'+digit;}
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

static u32 crc(u32 value,const u32* words,u32 count)
{
    for (u32 i=0;i<count;++i)
    {
        value^=words[i];
        for (u32 bit=0;bit<32;++bit)value=(value>>1)^((0u-(value&1))&0xedb88320u);
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
static u32 ioBudget;
static int waitBits(u32 bits,u32 desired)
{
    for(u32 i=0;i<WAIT_LIMIT && ioBudget;++i,--ioBudget)if((REG32(CARDCTRL)&bits)==desired)return 1;
    return 0;
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
    for(u32 i=0;i<4096 && ioBudget;++i)
    {
        command(0xe4,0,0xa7446000);
        if(!waitBits(0x00800000,0x00800000))return 0;
        u32 response=REG32(DATA);
        if(!waitBits(0x80000000,0))return 0;
        if(response)return 1;
        --ioBudget;
    }
    return 0;
}
static int readSector(u32 index,u32* out)
{
    u32 sector;
    if(!mapSector(index,&sector))return 0;
    ioBudget=WAIT_LIMIT;
    command(0xe3,sector,0xa0406000);
    if(!waitBits(0x80000000,0) || !ready())return 0;
    command(0xe5,0,0xa1444000);
    for(u32 i=0;i<128;++i)
    {
        if(!waitBits(0x00800000,0x00800000))return 0;
        out[i]=REG32(DATA);
    }
    return waitBits(0x80000000,0);
}
static int writeSector(u32 index,const u32* src)
{
    u32 sector;
    if(!mapSector(index,&sector))return 0;
    ioBudget=WAIT_LIMIT;
    command(0x9b0de1f6,sector,0xe1486000);
    for(u32 i=0;i<128;++i)
    {
        if(!waitBits(0x00800000,0x00800000))return 0;
        REG32(DATA)=src[i];
    }
    return waitBits(0x80000000,0) && ready();
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
    REG16(IPC)=(REG16(IPC)&~0xf00u)|0xd00;
    for(u32 i=0;i<WAIT_LIMIT;++i)if((REG16(IPC)&15)!=12)return;
}
__attribute__((noreturn)) static void fault(u32 code)
{
    gRtsM2.header.error=code;
    if(gRtsM2.videoActive)progress(9,code);
    REG16(IPC)=(REG16(IPC)&~0xf00u)|0xe00;
    REG16(0x0400006c)=0; // Keep the stage/error line readable.
    REG16(0x0400106c)=0x4010;
    // Fail closed after a transport error: do not resume game save callbacks
    // with an unknown card transaction still pending. User must reboot.
    for(;;)__asm__ volatile("nop");
}
static void flushCaches(void)
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

void rtsM2Run(const u32* entryRegs)
{
    WorkerState* s=&gRtsM2;
    RtsM2Header* h=&s->header;
    // Two saved words belong to the secure stub's MPU-region guard.
    const u32* frame=entryRegs+16;
    u32 control,dtcm,itcm;
    __asm__ volatile("mrc p15,0,%0,c1,c0,0\n mrc p15,0,%1,c9,c1,0\n mrc p15,0,%2,c9,c1,1":"=r"(control),"=r"(dtcm),"=r"(itcm));
    // First target's standard SDK TCM layout only. A rejection does not write SD.
    int safe=(control&0x50000)==0x50000 && (dtcm&0x3f)==10 && itcm==0x20 &&
        (dtcm&~0xfffu)>=0x02400000 && (dtcm&~0xfffu)<=0x02ffc000 &&
        !(REG32(0x04000064)&0x80000000) && !(REG16(0x04000204)&0x800) && !(REG32(CARDCTRL)&0x80000000) && !(REG16(0x040001a0)&0x80);
    for(u32 i=0;i<4;++i)if(REG32(0x040000b8+i*12)&0x80000000)safe=0;
    u32 first;
    if(!safe || !mapSector(0,&first)){signalDone();return;}
    progressOpen();
    progress(1,0);
    clear(h,sizeof(*h));
    h->magic=RTS_M2_MAGIC;h->version=RTS_M2_VERSION;h->fileBytes=RTS_M2_FILE_BYTES;h->gameCode=RTS_M2_GAME;
    h->payloadBytes=RTS_M2_PAYLOAD_BYTES;h->workspaceBase=s->base;h->workspaceBytes=s->bytes;
    h->dtcmBase=dtcm&~0xfffu;h->dtcmBytes=0x4000;h->itcmBase=0x01ff8000;h->itcmBytes=0x8000;
    h->control=control;h->dtcmConfig=dtcm;h->itcmConfig=itcm;
    for(u32 i=0;i<4;++i)h->regs[i]=frame[6+i];
    for(u32 i=4;i<12;++i)h->regs[i]=entryRegs[i];
    h->regs[12]=frame[10];h->regs[13]=(u32)(frame+12);h->regs[14]=frame[11];h->regs[15]=entryRegs[13];
    h->reserved[0]=entryRegs[14]; // Original protected MPU region 2.
    h->gateCpsr=frame[4];h->frameAddress=(u32)frame;h->flags=1; // explicitly NOT restorable
    progress(2,0);
    flushCaches();
    u32 transientControl=control&~5u; // MPU + D-cache off; retain both TCMs and I-cache.
    __asm__ volatile("mcr p15,0,%0,c1,c0,0"::"r"(transientControl):"memory");
    u16 aux=REG16(0x040001a0);
    u32 oldCommand0=REG32(CMD),oldCommand1=REG32(CMD+4),oldCardControl=REG32(CARDCTRL);
    progress(3,0);
    if(!readSector(0,s->readback))fault(1);
    const RtsM2Header* previous=(const RtsM2Header*)s->readback;
    if(previous->magic!=RTS_M2_MAGIC || previous->version!=RTS_M2_VERSION ||
       previous->fileBytes!=RTS_M2_FILE_BYTES || previous->gameCode!=RTS_M2_GAME ||
       previous->payloadBytes!=RTS_M2_PAYLOAD_BYTES)fault(2);
    h->sequence=previous->sequence+1;
    h->phase=1; // invalidate completion BEFORE touching the previous payload
    progress(4,0);
    if(!writeSector(0,(const u32*)h))fault(3);
    u32 value=~0u;
    for(u32 index=0;index<RTS_M2_PAYLOAD_BYTES/512;++index)
    {
        const u32* src;
        if(index<0x400000/512)
        {
            u32 address=0x02000000+index*512;
            src=(address>=s->base && address<s->base+s->bytes) ? s->zero : (const u32*)address;
        }
        else if(index<(0x400000+0x4000)/512)src=(const u32*)(h->dtcmBase+(index-0x400000/512)*512);
        else src=(const u32*)(0x01ff8000+(index-(0x400000+0x4000)/512)*512);
        value=crc(value,src,128);
        if(!writeSector(index+1,src))fault(4);
        heartbeat(index);
        if((index&63)==0)progress(5,index);
    }
    h->payloadCrc=~value;
    value=~0u;
    for(u32 index=0;index<RTS_M2_PAYLOAD_BYTES/512;++index)
    {
        if(!readSector(index+1,s->readback))fault(5);
        value=crc(value,s->readback,128);
        heartbeat(index);
        if((index&63)==0)progress(6,index);
    }
    h->verifyCrc=~value;
    if(h->verifyCrc!=h->payloadCrc)fault(6);
    progress(7,RTS_M2_PAYLOAD_BYTES/512);
    h->phase=2;
    if(!writeSector(0,(const u32*)h) || !readSector(0,s->readback))fault(7);
    for(u32 i=0;i<128;++i)if(s->readback[i]!=((u32*)h)[i])fault(8);
    REG32(CMD)=oldCommand0;REG32(CMD+4)=oldCommand1;
    REG16(0x040001a0)=aux;
    REG32(CARDCTRL)=oldCardControl&0x7f7fffff;
    u32 zero=0;
    __asm__ volatile("mcr p15,0,%0,c7,c10,4"::"r"(zero):"memory");
    __asm__ volatile("mcr p15,0,%0,c1,c0,0"::"r"(control):"memory");
    progressClose();
    signalDone();
}
