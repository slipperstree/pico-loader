#include "RtsMenu.h"
enum {BLACK=0x8000,WHITE=0xffff,GREEN=0x83e0};
typedef struct {char c;uint8_t bits[5];} Glyph;
static const Glyph font[]={
 {'0',{62,81,73,69,62}},{'1',{0,66,127,64,0}},{'2',{66,97,81,73,70}},{'3',{33,65,69,75,49}},
 {'4',{24,20,18,127,16}},{'5',{39,69,69,69,57}},{'6',{60,74,73,73,48}},{'7',{1,113,9,5,3}},
 {'8',{54,73,73,73,54}},{'9',{6,73,73,41,30}},
 {'A',{126,9,9,9,126}},{'B',{127,73,73,73,54}},{'C',{62,65,65,65,34}},{'D',{127,65,65,34,28}},
 {'E',{127,73,73,73,65}},{'F',{127,9,9,9,1}},{'G',{62,65,73,73,122}},{'H',{127,8,8,8,127}},
 {'I',{0,65,127,65,0}},{'J',{32,64,65,63,1}},{'K',{127,8,20,34,65}},{'L',{127,64,64,64,64}},
 {'M',{127,2,12,2,127}},{'N',{127,4,8,16,127}},{'O',{62,65,65,65,62}},{'P',{127,9,9,9,6}},
 {'Q',{62,65,81,33,94}},{'R',{127,9,25,41,70}},{'S',{70,73,73,73,49}},{'T',{1,1,127,1,1}},
 {'U',{63,64,64,64,63}},{'V',{31,32,64,32,31}},{'W',{63,64,56,64,63}},{'X',{99,20,8,20,99}},
 {'Y',{7,8,112,8,7}},{'Z',{97,81,73,69,67}},
 {'a',{32,84,84,84,120}},{'d',{56,68,68,72,127}},{'e',{56,84,84,84,24}},
 {'g',{12,82,82,82,62}},{'i',{0,68,125,64,0}},{'l',{0,65,127,64,0}},
 {'m',{124,4,24,4,120}},{'n',{124,8,4,4,120}},{'o',{56,68,68,68,56}},
 {'p',{124,20,20,20,8}},{'r',{124,8,4,4,8}},{'t',{4,63,68,64,32}},
 {'u',{60,64,64,32,124}},{'v',{28,32,64,32,28}},{'y',{12,80,80,80,60}},
 {'/',{32,16,8,4,2}},{':',{0,54,54,0,0}},{'%',{99,19,8,100,99}},{'-',{8,8,8,8,8}}};
static void pixel(uint16_t* p,int x,int y,unsigned color){if((unsigned)x<256 && (unsigned)y<192)p[y*256+x]=(uint16_t)color;}
static void rect(uint16_t* p,int x,int y,int w,int h,unsigned color){for(int j=0;j<h;++j)for(int i=0;i<w;++i)if(!i||!j||i==w-1||j==h-1)pixel(p,x+i,y+j,color);}
static void fill(uint16_t* p,int x,int y,int w,int h,unsigned color){for(int j=0;j<h;++j)for(int i=0;i<w;++i)pixel(p,x+i,y+j,color);}
static void text(uint16_t* p,int x,int y,const char* s,unsigned color,unsigned scale)
{
 for(;*s;++s,x+=6*scale)for(unsigned i=0;i<sizeof(font)/sizeof(font[0]);++i)if(font[i].c==*s)
  for(unsigned cx=0;cx<5;++cx)for(unsigned cy=0;cy<7;++cy)if(font[i].bits[cx]&(1u<<cy))fill(p,x+cx*scale,y+cy*scale,scale,scale,color);
}
void RtsMenuRender(const RtsMenu* m,uint16_t p[256*192],RtsMenuBlit blit,void* user,const char* debug)
{
 for(unsigned i=0;i<256*192;++i)p[i]=BLACK;
 text(p,104,3,"S/L Menu",WHITE,1);
 if(m->phase==RTS_MENU_CLOSED)return;
 if(m->phase==RTS_MENU_BUSY)
 {
  const char* title=m->action==RTS_MENU_LOAD ? "Loading" : "Saving";text(p,m->action==RTS_MENU_LOAD ? 107 : 110,66,title,WHITE,1);
  rect(p,23,91,210,20,WHITE);fill(p,25,93,(206u*m->percent)/100,16,GREEN);
  char percent[5];unsigned n=0;if(m->percent==100)percent[n++]='1';if(m->percent>=10)percent[n++]='0'+(m->percent/10)%10;
  percent[n++]='0'+m->percent%10;percent[n++]='%';percent[n]=0;text(p,128-(int)n*6,121,percent,WHITE,2);
  if(m->debug_enabled && debug)text(p,4,177,debug,WHITE,1);
  return;
 }
 for(unsigned i=0;i<4;++i)
 {
  int x=i&1 ? 144 : 16,y=i>=2 ? 107 : 20;
  if(i==m->selected)rect(p,x-2,y-2,86,66,GREEN);
  rect(p,x,y,82,62,WHITE);
  if(m->slots[i].occupied)
  {
   if(blit)blit(user,i,p,256,x+1,y+1);
   char date[11],clock[9];RtsMenuFormatTime(&m->slots[i].time,date,clock);
   text(p,x+11,y+64,date,WHITE,1);text(p,x+17,y+74,clock,WHITE,1);
  }
  else text(p,x+26,y+27,"Empty",WHITE,1);
 }
 if(m->phase==RTS_MENU_ACTIONS)
 {
  int x=(m->selected&1 ? 144 : 16)+84,y=(m->selected>=2 ? 107 : 20)-3;
  text(p,x,y,"Save",m->action==RTS_MENU_SAVE ? GREEN : WHITE,1);
  if(m->slots[m->selected].occupied)text(p,x,y+10,"Load",m->action==RTS_MENU_LOAD ? GREEN : WHITE,1);
 }
}
