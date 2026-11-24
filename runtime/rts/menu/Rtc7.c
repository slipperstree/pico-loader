// DS RTC GPIO transaction follows the register protocol used by libtwl/sioRtc.
// Runs only in the parked ARM7 server, with IRQs disabled. Restore pin state.
#include <stdint.h>
#include "RtsMenu.h"
#define R16(a) (*(volatile uint16_t*)(a))
static void delay(void){for(volatile unsigned i=0;i<12;++i)__asm__ volatile("nop");}
static void pins(unsigned bits){R16(0x04000138)=(R16(0x04000138)&~0x77u)|bits;delay();}
static void readRtc(unsigned command,uint8_t* out,unsigned length)
{
 pins(0x72);pins(0x76);
 for(unsigned i=0;i<8;++i){unsigned bit=(command>>i)&1;pins(0x74|bit);pins(0x76|bit);}
 for(unsigned j=0;j<length;++j){unsigned value=0;for(unsigned i=0;i<8;++i){pins(0x64);value|=(R16(0x04000138)&1)<<i;pins(0x66);}out[j]=value;}
 pins(0x62);
}
static unsigned bcd(unsigned x){return (x>>4)*10+(x&15);}
void RtsMenuReadClock7(void* out)
{
 uint16_t mode=R16(0x04000134),gpio=R16(0x04000138);
 R16(0x04000134)=(mode&~0xc000u)|0x8000u;
 uint8_t status=0,raw[7];readRtc(0x86,&status,1);readRtc(0xa6,raw,7);
 R16(0x04000138)=gpio;R16(0x04000134)=mode;
 RtsMenuTime* t=out;t->year=2000+bcd(raw[0]);t->month=bcd(raw[1]);t->day=bcd(raw[2]);
 unsigned hour=bcd(raw[4]&0x3f);if(!(status&2)){if(hour==12)hour=0;if(raw[4]&0x40)hour+=12;}
 t->hour=hour;t->minute=bcd(raw[5]);t->second=bcd(raw[6]);t->reserved=0;
 if(t->month<1 || t->month>12 || t->day<1 || t->day>31 || hour>23 || t->minute>59 || t->second>59)t->year=0;
}
