#include <fstream>
#include <vector>
#include <cstdint>
#include <cstdio>
#include "RtsSdkSound.h"
int main(int argc,char** argv){
    if(argc!=2)return 2;
    std::ifstream input(argv[1],std::ios::binary);uint32_t h[128]{};
    if(!input.read((char*)h,512))return 3;
    if(!h[15] || h[15]>0x100000)return 4;
    std::vector<uint32_t> data((h[15]+3)/4);
    input.seekg(h[12]);if(!input.read((char*)data.data(),h[15]))return 5;
    RtsSdkSound::Image image{data.data(),h[15],h[14]};RtsSdkSound::Plan plan;
    bool ok=RtsSdkSound::find(image,plan);
    std::printf("{\"recognized\":%s,\"sites\":[",ok ? "true":"false");
    if(ok)for(unsigned i=0;i<7;++i)std::printf("%s[%u,%u,%u]",i ? ",":"",plan.sites[i].offset,plan.sites[i].instruction,plan.sites[i].runtime);
    std::puts("]}");return 0;
}
