#include "RtsVideoCapture.h"
typedef uint32_t u32;typedef uint16_t u16;
#define REG32(a) (*(volatile u32*)(a))
#define REG16(a) (*(volatile u16*)(a))
#define REG8(a) (*(volatile uint8_t*)(a))
static const u32 control[9]={0x04000240,0x04000241,0x04000242,0x04000243,0x04000244,0x04000245,0x04000246,0x04000248,0x04000249};
static const u32 starts[10]={0,0x20000,0x40000,0x60000,0x80000,0x90000,0x94000,0x98000,0xa0000,0xa4000};
int RtsPrepareVideoCapture(RtsVideoCapture* s,u32 main,u32 sub)
{
    u32* words=(u32*)s;for(u32 i=0;i<128;++i)words[i]=0;
    for(u32 i=0;i<9;++i)s->vram[i]=REG8(control[i]);
    if((s->vram[2]&0x87)==0x82 || (s->vram[3]&0x87)==0x82)return 0;
    s->version=1;s->vramBytes=RTS_VIDEO_VRAM_BYTES;s->paletteBytes=s->oamBytes=2048;
    s->display[0]=REG32(0x04000000);s->display[1]=REG32(0x04001000);
    s->brightness[0]=main;s->brightness[1]=sub;
    s->power=REG16(0x04000304);s->wram=REG8(0x04000247)&3;
    for(u32 i=0;i<8;++i)s->bgControl[i]=REG16(0x04000008+(i&3)*2+(i>=4 ? 0x1000 : 0));
    s->magic=RTS_VIDEO_MAGIC;return 1;
}
__attribute__((noinline)) int RtsReadVideoSector(const RtsVideoCapture* s,u32 sector,u16* out,const u16* backup)
{
    if(s->magic!=RTS_VIDEO_MAGIC || sector>=(RTS_VIDEO_SECTION_BYTES-512)/512)return 0;
    u32 offset=sector*512,bank=9,address;
    uint8_t old=0;
    if(offset<RTS_VIDEO_VRAM_BYTES)
    {
        bank=0;while(offset>=starts[bank+1])++bank;
        old=REG8(control[bank]);REG8(control[bank])=0x80;
        (void)REG8(control[bank]); // Complete mapping write before LCDC access.
        address=0x06800000+offset;
    }
    else address=(offset<RTS_VIDEO_VRAM_BYTES+2048 ? 0x05000000 : 0x07000000)+((offset-RTS_VIDEO_VRAM_BYTES)&2047);
    for(u32 i=0;i<256;++i)out[i]=REG16(address+i*2);
    if(bank<9)
    {
        REG8(control[bank])=old;(void)REG8(control[bank]);
        // Bank C has the live progress line. File must contain original game
        // pixels. A 512-byte sector is exactly one 256-pixel framebuffer row.
        if(bank==2 && offset-0x40000<8*512)
            for(u32 i=0;i<96;++i)out[i]=backup[(offset-0x40000)/512*96+i];
    }
    return 1;
}
