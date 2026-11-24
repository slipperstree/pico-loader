#include "RtsSoundRestart.h"
typedef uint32_t u32;
void RtsInitSoundShadow(RtsSoundShadow* s)
{
    u32* p=(u32*)s;for(u32 i=0;i<128;++i)p[i]=0;
    s->version=1;s->magic=RTS_SOUND_SHADOW_MAGIC;
}
int RtsObserveSoundWrite(RtsSoundShadow* s,u32 address,u32 bytes,u32 value)
{
    if(!s || s->magic!=RTS_SOUND_SHADOW_MAGIC || s->version!=1)return -1;
    if(address<0x04000400 || address>=0x04000500)return 0;
    u32 offset=address-0x04000400,ch=offset/16,at=offset&15;
    if((bytes!=1 && bytes!=2 && bytes!=4) || (address&(bytes-1)) || bytes>16-at){s->unsupported=1;return -1;}
    u32* words=(u32*)&s->channels[ch];
    for(u32 i=0;i<bytes;++i)
    {
        u32 b=at+i,field=b<8 ? b/4 : b<10 ? 2 : b<12 ? 3 : 4;
        u32 shift=8*(b<8 ? b&3 : b<10 ? b-8 : b<12 ? b-10 : b-12);
        words[field]=(words[field]&~(255u<<shift))|(((value>>(8*i))&255u)<<shift);
        s->coverage[ch]|=1u<<b;
    }
    ++s->sequence;return 1;
}
static int sampleRange(u32 a,u32 words)
{
    if(a&3 || !words || words>0x400000)return 0;
    u32 n=words*4;
    // This experiment runs in 4 MiB DS mode. ARM7 sound DMA sees main RAM
    // throughout 02xxxxxx; keep the actual source alias for replay, but bound
    // the sample against the canonical 4 MiB backing span without wrap.
    if((a&0xff000000u)==0x02000000u)return n<=0x400000u-(a&0x3fffffu);
    if(a>=0x03000000 && a<0x03800000)return n<=0x8000-(a&0x7fff);
    return a>=0x03800000 && a<0x04000000 && n<=0x10000-(a&0xffff);
}
int RtsBuildSoundRestartDetailed(const RtsSoundShadow* s,const u32 controls[16],u32 master,u32 bias,u32 capture,RtsSoundRestartPlan* out,u32* detail)
{
    if(detail)*detail=0;
#define REJECT(code,why) do {if(detail)*detail=(why);return (code);} while(0)
    if(!s || !controls)REJECT(1,4301);
    if(s->magic!=RTS_SOUND_SHADOW_MAGIC || s->version!=1)REJECT(1,4302);
    if(s->unsupported)REJECT(1,4303);
    if(master>65535)REJECT(1,4304);
    if(bias>1023)REJECT(1,4305);
    if(capture&0x8080)REJECT(1,4306);
    RtsSoundRestartPlan plan;u32* p=(u32*)&plan;for(u32 i=0;i<128;++i)p[i]=0;
    plan.magic=RTS_SOUND_PLAN_MAGIC;plan.version=1;plan.master=master;plan.bias=bias;plan.sequence=s->sequence;
    for(u32 ch=0;ch<16;++ch)
    {
        u32 control=controls[ch];if(!(control&0x80000000))continue;
        const RtsSoundChannel* c=&s->channels[ch];u32 format=(control>>29)&3;
        u32 required=format==3 ? 0x300u : 0xfff0u;
        if((s->coverage[ch]&required)!=required)REJECT(2,4400+ch);
        if(c->timer>65535 || c->loop>65535 || c->length>0x3fffff)REJECT(3,4500+ch);
        if(format==3){if(ch<8)REJECT(3,4700+ch);}
        else if(!sampleRange(c->source,c->loop+c->length))REJECT(3,4600+ch);
        plan.activeMask|=1u<<ch;
        RtsSoundChannel* d=&plan.channels[ch];
        d->control=control;d->source=c->source;d->timer=c->timer;d->loop=c->loop;d->length=c->length;
    }
    if(out){u32* dst=(u32*)out;for(u32 i=0;i<128;++i)dst[i]=p[i];}
#undef REJECT
    return 0;
}
int RtsBuildSoundRestart(const RtsSoundShadow* s,const u32 controls[16],u32 master,u32 bias,u32 capture,RtsSoundRestartPlan* out)
{
    return RtsBuildSoundRestartDetailed(s,controls,master,bias,capture,out,0);
}
void RtsPrepareSoundRestart(const RtsSoundRestartPlan* p,RtsSoundWrite write,void* user)
{
    if(!p || !write || p->magic!=RTS_SOUND_PLAN_MAGIC || p->version!=1)return;
    write(user,0x04000500,2,0); // Mute output before stopping/reconfiguring channels.
    for(u32 ch=0;ch<16;++ch)write(user,0x04000400+ch*16,4,0);
    write(user,0x04000504,2,p->bias);
    for(u32 ch=0;ch<16;++ch)if(p->activeMask&(1u<<ch))
    {
        const RtsSoundChannel* c=&p->channels[ch];u32 a=0x04000400+ch*16;
        write(user,a,4,c->control&~0x80000000u);
        write(user,a+8,2,c->timer);
        if(((c->control>>29)&3)!=3)
        {write(user,a+10,2,c->loop);write(user,a+12,4,c->length);write(user,a+4,4,c->source);}
    }
}
void RtsReleaseSoundRestart(const RtsSoundRestartPlan* p,RtsSoundWrite write,void* user)
{
    if(!p || !write || p->magic!=RTS_SOUND_PLAN_MAGIC || p->version!=1)return;
    for(u32 ch=0;ch<16;++ch)if(p->activeMask&(1u<<ch))write(user,0x04000400+ch*16,4,p->channels[ch].control);
    write(user,0x04000500,2,p->master);
}
