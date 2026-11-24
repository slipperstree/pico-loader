#include "RtsMenuRuntime.h"
#include "RtsP4.h"
#include "worker-state.h"
typedef uint32_t u32;typedef uint16_t u16;typedef uint8_t u8;
#define R32(a) (*(volatile u32*)(a))
#define R16(a) (*(volatile u16*)(a))
#define R8(a) (*(volatile u8*)(a))
#define FB ((u16*)0x06840000)
RtsMenuBoot gRtsMenuBoot;
static u32 restoreBuffer[128];
static struct {RtsMenu menu;u32 active,captureBank,captureValid,display,previews;u16 power,mainBright,subBright;u8 bankC,bankD;RtsMenuTime time;} ui;
static void copy(void* d,const void* s,u32 n){u16* a=d;const u16* b=s;for(u32 i=0;i<n/2;++i)a[i]=b[i];}
static void auxRead(u32 sector,u32* out){if(!RtsMenuRawRead(&gRtsMenuBoot.aux,sector,out))RtsP4Fault(61);}
static void auxWrite(u32 sector,const u32* in){if(!RtsMenuRawWrite(&gRtsMenuBoot.aux,sector,in))RtsP4Fault(62);}
static void frame(void)
{
 u32 previous=R16(0x04000006),spins=0x400000,found=0;
 while(spins--){u32 line=R16(0x04000006);if(line<previous){found=1;break;}previous=line;}
 if(!found)RtsP4Fault(63);
 RtsP4Heartbeat((gRtsM2Frames[0]&1)*16);
}
static void bankBackup(unsigned bank)
{
 u32 address=0x06840000+(bank-2)*0x20000;R8(0x04000240+bank)=0x80;(void)R8(0x04000240+bank);
 for(u32 i=0;i<256;++i){copy(gRtsM2.readback,(void*)(address+i*512),512);

  auxWrite((bank-2)*256+i,gRtsM2.readback);}
}
static void bankRestore(unsigned bank)
{
 u32 address=0x06840000+(bank-2)*0x20000;R8(0x04000240+bank)=0x80;(void)R8(0x04000240+bank);
 for(u32 i=0;i<256;++i){auxRead((bank-2)*256+i,restoreBuffer);copy((void*)(address+i*512),restoreBuffer,512);}
}
static void currentThumbnail(void)
{
 u32 address=0x06840000+(ui.captureBank-2)*0x20000;
 for(u32 sector=0;sector<20;++sector){u16* out=(u16*)gRtsM2.readback;for(u32 i=0;i<256;++i){u32 index=sector*256+i;
  out[i]=index<4800 && ui.captureValid ? R16(address+(((index/80)*16/5)*256+(index%80)*16/5)*2)|0x8000u : 0x8000;}
  auxWrite(RTS_MENU_CAPTURE_SECTOR+sector,gRtsM2.readback);}
}
static u32 metaSector(unsigned slot){return RTS_MENU_SLOT_META_SECTOR+slot*21;}
static void blit(void* user,unsigned slot,u16* out,unsigned stride,unsigned x,unsigned y)
{
 (void)user;if(!(ui.previews&(1u<<slot)))return;for(u32 sector=0;sector<20;++sector){auxRead(metaSector(slot)+1+sector,gRtsM2.readback);const u16* in=(const u16*)gRtsM2.readback;
  for(u32 i=0;i<256;++i){u32 index=sector*256+i;if(index<4800)out[(y+index/80)*stride+x+index%80]=in[i];}}
}
static void render(void){RtsMenuRender(&ui.menu,FB,blit,0,0);}
int RtsMenuRuntimeOpen(void)
{
 if(gRtsMenuBoot.magic!=RTS_MENU_BOOT_MAGIC)return RTS_MENU_RESUME;
 ui.display=gRtsM2.oldDisplay;ui.mainBright=gRtsP4Scratch.video.brightness[0];ui.subBright=gRtsP4Scratch.video.brightness[1];
 ui.power=R16(0x04000304);ui.bankC=gRtsM2.oldVramC;ui.bankD=R8(0x04000243);
 RtsMenuInit(&ui.menu,gRtsMenuBoot.debug);ui.active=1;ui.captureBank=2;ui.previews=0;
 rtsP4Request(6,0);
 // Capture into C when it belongs to the sub engine or is unused; otherwise
 // prefer D if it is not a main BG/OBJ/texture source. Both banks are preserved.
 unsigned c=ui.bankC&7,d=ui.bankD&7;
 if((ui.bankC&128) && c>=1 && c<=3)ui.captureBank=3;
 ui.captureValid=!(ui.captureBank==3 && (ui.bankD&128) && d>=1 && d<=3);
 bankBackup(2);bankBackup(3);
 R8(0x04000242)=ui.bankC;R8(0x04000243)=ui.bankD;
 R8(0x04000240+ui.captureBank)=0x80;(void)R8(0x04000240+ui.captureBank);
 R32(0x04000000)=ui.display;
 if(ui.captureValid){R32(0x04000064)=0x80300000u|(ui.captureBank<<16);frame();frame();if(R32(0x04000064)&0x80000000u)ui.captureValid=0;}
 R32(0x04000064)=0;currentThumbnail();
 R8(0x04000243)=ui.bankD;R8(0x04000242)=0x80;
 R32(0x04000000)=0xa0000;R16(0x04000304)=ui.power&~0x8000u;
 R16(0x0400006c)=0;R16(0x0400106c)=0x8008;
 for(unsigned i=0;i<4;++i){if(!RtsMenuRawRead(&gRtsMenuBoot.slots[i],0,gRtsM2.readback))RtsP4Fault(64);
  const RtsM2Header* h=(const RtsM2Header*)gRtsM2.readback;
  if(h->magic!=RTS_P4_MAGIC || h->version!=RTS_P4_VERSION || h->gameCode!=gRtsM2.info.gameCode || h->phase!=2 || h->error)continue;
  u32 sequence=h->sequence;ui.menu.slots[i].occupied=1;auxRead(metaSector(i),gRtsM2.readback);
  const RtsMenuMetadata* m=(const RtsMenuMetadata*)gRtsM2.readback;
  if(m->magic==RTS_MENU_META_MAGIC && m->version==1 && m->gameCode==gRtsM2.info.gameCode && m->sequence==sequence){ui.menu.slots[i].time=m->time;if(m->hasThumbnail)ui.previews|=1u<<i;}
 }
 render();
 for(;;){frame();unsigned before=ui.menu.selected|(ui.menu.phase<<8)|(ui.menu.action<<16);
  int action=RtsMenuTick(&ui.menu,(~R16(0x04000130))&0x3ff);
  if(action==RTS_MENU_RESUME)return action;
  if(action==RTS_MENU_SAVE || action==RTS_MENU_LOAD){copy(&gRtsM2.info,&gRtsMenuBoot.slots[ui.menu.selected],sizeof(RtsSnapshotInfo));gRtsM2.info.reserved=0;gRtsP4.operation=action==RTS_MENU_LOAD;
   rtsP4Request(8,0);copy(&ui.time,(void*)gRtsM2.readback,sizeof(ui.time));render();return action;}
  unsigned after=ui.menu.selected|(ui.menu.phase<<8)|(ui.menu.action<<16);if(before!=after)render();
 }
}
void RtsMenuRuntimeClose(void)
{
 if(!ui.active)return;
 bankRestore(2);bankRestore(3);R8(0x04000242)=0x80;R8(0x04000243)=ui.bankD;
 R32(0x04000000)=ui.display;R16(0x04000304)=ui.power;R16(0x0400006c)=ui.mainBright;R16(0x0400106c)=ui.subBright;
 rtsP4Request(7,0);ui.active=0;
}
void RtsMenuRuntimeProgress(u32 stage,u32 value)
{
 if(!ui.active)return;
 if(stage==8 || stage==9){char line[]="ERROR 0000   PRESS B";for(unsigned i=0;i<4;++i){line[9-i]='0'+value%10;value/=10;}ui.menu.phase=RTS_MENU_BUSY;
  ui.menu.debug_enabled=1;RtsMenuRender(&ui.menu,FB,0,0,line);return;}
 u32 total=RTS_M2_PAYLOAD_BYTES/512;
 if(gRtsP4.operation){if(stage==1)RtsMenuSetProgress(&ui.menu,value,total*2);if(stage==2)RtsMenuSetProgress(&ui.menu,value+(gRtsP4LoadVerify ? total : 0),total*(gRtsP4LoadVerify ? 2 : 1));}
 else{int full=!(gRtsM2.header.flags&RTS_M2_FLAG_NO_READBACK);if(stage==5)RtsMenuSetProgress(&ui.menu,value,total*(full ? 2 : 1));if(stage==6)RtsMenuSetProgress(&ui.menu,total+(full ? value : 0),total*(full ? 2 : 1));if(stage>=7)RtsMenuSetProgress(&ui.menu,1,1);}
 char line[]="DEBUG S0 0000";line[6]=gRtsP4.operation?'L':'S';line[7]='0'+stage;
 for(unsigned i=0;i<4;++i){line[12-i]='0'+value%10;value/=10;}
 RtsMenuRender(&ui.menu,FB,0,0,line);
}
void RtsMenuRuntimeSaved(u32 sequence)
{
 if(!ui.active)return;
 for(u32 i=0;i<20;++i){auxRead(RTS_MENU_CAPTURE_SECTOR+i,gRtsM2.readback);auxWrite(metaSector(ui.menu.selected)+1+i,gRtsM2.readback);}
 for(u32 i=0;i<128;++i)gRtsM2.readback[i]=0;
 RtsMenuMetadata* m=(RtsMenuMetadata*)gRtsM2.readback;m->magic=RTS_MENU_META_MAGIC;m->version=1;m->gameCode=gRtsM2.info.gameCode;m->sequence=sequence;m->time=ui.time;m->hasThumbnail=ui.captureValid;
 auxWrite(metaSector(ui.menu.selected),gRtsM2.readback);
}
int RtsMenuRuntimeReadVideo(u32 offset,u16* out)
{
 if(!ui.active)return 0;
 if(offset>=0x98000 && offset<0xa0000){auxRead(RTS_MENU_H_SECTOR+(offset-0x98000)/512,(u32*)out);return 1;}
 if(offset<0x40000 || offset>=0x80000)return 0;
 auxRead((offset-0x40000)/512,(u32*)out);return 1;
}
int RtsMenuRuntimeWriteVideo(u32 offset,const u16* in)
{
 if(!ui.active)return 0;
 if(offset>=0x98000 && offset<0xa0000){auxWrite(RTS_MENU_H_SECTOR+(offset-0x98000)/512,(const u32*)in);return 1;}
 if(offset<0x40000 || offset>=0x60000)return 0;
 auxWrite((offset-0x40000)/512,(const u32*)in);return 1;
}
void RtsMenuRuntimeFinishLoad(void)
{
 if(ui.active){bankRestore(2);ui.active=0;}
}
int RtsMenuRuntimeIsActive(void){return ui.active!=0;}
