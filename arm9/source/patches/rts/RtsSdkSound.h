#pragma once
#include <stdint.h>
#include <stddef.h>

// Read-only recognizer for common NTR SDK sound MMIO stores. No game IDs.
// This header is shared by the real installer and native fixture tests.
namespace RtsSdkSound {
struct Site {uint32_t offset,instruction,runtime;};
struct Plan {Site sites[7];};
struct Image {
    const uint32_t* words; uint32_t bytes,base;
    bool within(uint32_t off,uint32_t n) const {return off<=bytes && n<=bytes-off;}
    uint32_t at(uint32_t off) const {return words[off/4];}
    uint32_t find(const uint32_t (&pattern)[4]) const {
        for(uint32_t i=0;i+16<=bytes;i+=4)
            if(at(i)==pattern[0] && at(i+4)==pattern[1] && at(i+8)==pattern[2] && at(i+12)==pattern[3])return i;
        return UINT32_MAX;
    }
    bool runtime(uint32_t off,uint32_t& result) const {
        if(!within(off,4))return false;
        if(base>=0x03000000 && base<0x04000000){result=base+off;return true;}
        // SDK ARM7 startup's autoload loop loads its 3-word parameter block.
        // The NTR list contains target/initialized-size/BSS-size triples.
        for(uint32_t i=0;i<0x400 && within(i,16);i+=4) {
            if((at(i)&0xfffff000)!=0xe59f0000 || at(i+4)!=0xe5901000 || at(i+8)!=0xe5902004 || at(i+12)!=0xe5903008)continue;
            uint32_t literal=i+8+(at(i)&4095);if(!within(literal,4))continue;
            uint32_t param=at(literal)-base;if(!within(param,12))continue;
            uint32_t first=at(param)-base,last=at(param+4)-base,source=at(param+8)-base;
            if(first>last || !within(first,last-first) || ((last-first)%12) || !within(source,0))continue;
            bool valid=true;uint32_t mapped=base+off;
            for(uint32_t j=first;j<last;j+=12) {
                uint32_t target=at(j),size=at(j+4);
                if(!within(source,size) || target>UINT32_MAX-size){valid=false;break;}
                if(off>=source && off-source<size){if(size-(off-source)<4)return false;mapped=target+off-source;}
                source+=size;
            }
            if(valid){result=mapped;return true;}
        }
        return false;
    }
    bool site(uint32_t offset,Site& out) const {
        if(!within(offset,4))return false;
        uint32_t op=at(offset),rn=(op>>16)&15,rd=(op>>12)&15,address;
        if(rn>12 || rd>12 || !((op&0xfff00000)==0xe5800000 || (op&0xfff000f0)==0xe1c000b0) || !runtime(offset,address))return false;
        out={offset,op,address};return true;
    }
};
inline bool find(const Image& image,Plan& out) {
    const uint32_t pcmOld[]={0xe1a07002,0xe1a06003,0xe59d1020,0xe59d502c};
    const uint32_t timerOld[]={0xe2611801,0xe1a00200,0xe2800301,0xe2800b01};
    const uint32_t psgOld[]={0xe92d40f0,0xe24dd004,0xe1a07001,0xe1a06003};
    const uint32_t noiseOld[]={0xe92d40f0,0xe24dd004,0xe1a07002,0xe1a06003};
    const uint32_t pcmNew[]={0xe1c020b8,0xe59d201c,0xe1c030ba,0xe581240c};
    const uint32_t timerNew[]={0xe1a00200,0xe2800301,0xe2611801,0xe2800b01};
    const uint32_t psgNew[]={0xe5802400,0xe2611801,0xe2800b01,0xe1c010b8};
    const uint32_t noiseNew[]={0xe5801400,0xe2661801,0xe2800b01,0xe1c010b8};
    uint32_t pcm=image.find(pcmOld),timer=image.find(timerOld),psg=image.find(psgOld),noise=image.find(noiseOld),offsets[7];
    if(pcm!=UINT32_MAX && pcm>=8 && timer!=UINT32_MAX && psg!=UINT32_MAX && noise!=UINT32_MAX) {
        pcm-=8;if(!image.within(pcm,0xbc) || image.at(pcm)!=0xe92d41f0 || image.at(pcm+4)!=0xe1a08001)return false;
        offsets[0]=pcm+0x9c;offsets[1]=pcm+0xa4;offsets[2]=pcm+0xac;offsets[3]=pcm+0xb0;
        offsets[4]=timer+0x10;offsets[5]=psg+0x94;offsets[6]=noise+0x8c;
    } else {
        pcm=image.find(pcmNew);timer=image.find(timerNew);psg=image.find(psgNew);noise=image.find(noiseNew);
        if(pcm==UINT32_MAX || timer==UINT32_MAX || psg==UINT32_MAX || noise==UINT32_MAX)return false;
        offsets[0]=pcm;offsets[1]=pcm+8;offsets[2]=pcm+12;offsets[3]=pcm+16;
        offsets[4]=timer+16;offsets[5]=psg+12;offsets[6]=noise+12;
    }
    for(uint32_t i=0;i<7;++i)if(!image.site(offsets[i],out.sites[i]))return false;
    return true;
}
}
