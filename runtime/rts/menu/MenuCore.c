#include "RtsMenuRuntime.h"
#include "RtsP4.h"
#include "worker-state.h"
typedef uint32_t u32;typedef uint16_t u16;
#define R8(a) (*(volatile uint8_t*)(a))
RtsMenuCoreBoot gRtsMenuCoreBoot;
u32 gRtsMenuLoaded;
// Initial loading may use the shared transfer buffer. At final load handoff,
// the CPU state owns that buffer; video scratch has already been consumed.
static u32* sectorBuffer;
__attribute__((noinline)) static void words(u32* to,const u32* from){for(unsigned j=0;j<128;++j)to[j]=from[j];}
static void read(unsigned sector){if(!RtsMenuRawRead(&gRtsMenuCoreBoot.aux,sector,sectorBuffer))RtsP4Fault(65);}
void RtsMenuLoadOverlay(void)
{
 sectorBuffer=gRtsM2.readback;
 if(gRtsMenuCoreBoot.magic!=RTS_MENU_BOOT_MAGIC)RtsP4Fault(66);
 uint8_t old=R8(0x04000248);gRtsMenuCoreBoot.oldBankH=old;R8(0x04000248)=0x80;(void)R8(0x04000248);
 for(unsigned i=0;i<64;++i){const u32* p=(const u32*)(0x06898000+i*512);words(sectorBuffer,p);
  if(!RtsMenuRawWrite(&gRtsMenuCoreBoot.aux,RTS_MENU_H_SECTOR+i,sectorBuffer))RtsP4Fault(67);}
 for(unsigned i=0;i<64;++i){read(RTS_MENU_IMAGE_SECTOR+i);u32* p=(u32*)(0x06898000+i*512);words(p,sectorBuffer);}
 read(RTS_MENU_AUX_HEADER_SECTOR);unsigned count=sectorBuffer[4];if(count>1024)RtsP4Fault(68);
 for(unsigned i=0;i<count;++i){if(!(i&127))read(RTS_MENU_RELOC_SECTOR+i/128);u32 offset=sectorBuffer[i&127];if(offset>32764 || (offset&3))RtsP4Fault(69);
  *(u32*)(0x06898000+offset)+=gRtsM2.base-0x02200000;}
 // The full per-game slot maps live in the overlay, not in the resident arena.
 u32* dst=(u32*)&gRtsMenuBoot;
 for(unsigned i=0;i<(sizeof(gRtsMenuBoot)+511)/512;++i){read(RTS_MENU_MAP_SECTOR+i);for(unsigned j=0;j<128 && i*128+j<sizeof(gRtsMenuBoot)/4;++j)dst[i*128+j]=sectorBuffer[j];}
 gRtsMenuLoaded=1;
}
void RtsMenuUnloadOverlay(void)
{
 if(!gRtsMenuLoaded)return;
 sectorBuffer=gRtsP4.operation ? (u32*)&gRtsP4Scratch : gRtsM2.readback;
 gRtsMenuLoaded=0; // No calls into the overlay after restoration starts.
 for(unsigned i=0;i<64;++i){read(RTS_MENU_H_SECTOR+i);u32* p=(u32*)(0x06898000+i*512);words(p,sectorBuffer);}
 R8(0x04000248)=gRtsMenuCoreBoot.oldBankH;gRtsMenuLoaded=0;
}
