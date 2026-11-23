#include "RtsSavePath.h"
int RtsMakeSavePath(const char* rom,char* out,size_t capacity)
{
    if(!rom || !out)return 0;
    size_t length=0,dot=0;
    while(rom[length]){char c=rom[length];if(c=='/' || c=='\\')dot=0;else if(c=='.')dot=length;++length;}
    size_t stem=dot ? dot : length;
    if(!length || stem>capacity || capacity-stem<5)return 0;
    for(size_t i=0;i<stem;++i)out[i]=rom[i];
    out[stem]='.';out[stem+1]='r';out[stem+2]='t';out[stem+3]='s';out[stem+4]=0;return 1;
}
