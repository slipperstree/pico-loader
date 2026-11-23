#include "RtsArm7Restore.h"
typedef uint32_t u32;
static int within(u32 a,u32 n,u32 base,u32 bytes){return a>=base && n<=bytes && a-base<=bytes-n;}
static int captured(u32 a,u32 n,u32 base,u32 bytes)
{
    if(within(a,n,0x02000000,0x400000))return a+n<=base || a>=base+bytes;
    if(a>=0x03800000 && a<0x04000000)return n<=0x10000-(a&0xffff);
    return a>=0x03000000 && a<0x03800000 && n<=0x8000-(a&0x7fff);
}
int RtsValidateArm7Continuation(const RtsArm7Context* c,u32 base,u32 bytes,int verified,RtsReadArm7Bytes read,void* user)
{
    if(!verified)return RTS_A7_UNVERIFIED;
    if(!c || !read || c->magic!=RTS_ARM7_CONTEXT_MAGIC || c->version!=1 || c->ime!=1 || c->wramMode!=3 ||
       c->reserved[0] || c->reserved[1] || !bytes || (base&511) || (bytes&511) ||
       base<0x02300000 || base>=0x023ff000 || bytes>0x023ff000-base)return RTS_A7_CONTEXT;
    for(u32 i=0;i<85;++i)if(c->padding[i])return RTS_A7_CONTEXT;
    u32 mode=c->parkCpsr&31;
    if(mode!=18 || (c->parkCpsr&0x01000020) || !(c->parkCpsr&0x80))return RTS_A7_MODE;
    u32 bank=mode==18 ? 1 : 0,lr=c->frame[11],pc=lr&~1u;
    if((c->parkSp&3) || !captured(c->parkSp,48,base,bytes) ||
       (!(lr&1) && (pc&3)) || !captured(pc,lr&1 ? 2 : 4,base,bytes))return RTS_A7_RANGE;
    if(c->banks[0][2] || c->banks[bank][0]!=c->parkSp || c->banks[bank][1]!=lr)return RTS_A7_FRAME;
    u32 frame[12];
    if(!read(user,c->parkSp,frame,sizeof(frame)))return RTS_A7_READ;
    for(u32 i=0;i<12;++i)if(frame[i]!=c->frame[i])return RTS_A7_FRAME;
    return RTS_A7_OK;
}
