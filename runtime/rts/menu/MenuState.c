#include "RtsMenu.h"
void RtsMenuInit(RtsMenu* m,int debug)
{
 uint8_t* p=(uint8_t*)m;for(unsigned i=0;i<sizeof(*m);++i)p[i]=0;
 m->debug_enabled=debug!=0;m->previous_keys=RTS_MENU_HOTKEY;m->wait_hotkey_release=1;
}
enum RtsMenuAction RtsMenuTick(RtsMenu* m,uint16_t keys)
{
 unsigned pressed=keys&~m->previous_keys,dir=keys&240,old=m->previous_keys&240;
 m->previous_keys=keys;
 if(m->wait_hotkey_release){if(!(keys&RTS_MENU_HOTKEY))m->wait_hotkey_release=0;return RTS_MENU_NONE;}
 if(m->phase==RTS_MENU_BUSY || m->phase==RTS_MENU_CLOSED)return RTS_MENU_NONE;
 if(dir && dir==old){if(m->repeat_frames<65535)++m->repeat_frames;if(m->repeat_frames>=18 && !((m->repeat_frames-18)%6))pressed|=dir;}
 else m->repeat_frames=0;
 if(pressed&RTS_KEY_B){if(m->phase==RTS_MENU_ACTIONS)m->phase=RTS_MENU_SLOTS;else{m->phase=RTS_MENU_CLOSED;return RTS_MENU_RESUME;}return RTS_MENU_NONE;}
 if(m->phase==RTS_MENU_SLOTS)
 {
  if(pressed&RTS_KEY_RIGHT)m->selected=(m->selected+1)&3;
  else if(pressed&RTS_KEY_LEFT)m->selected=(m->selected+3)&3;
  else if(pressed&(RTS_KEY_UP|RTS_KEY_DOWN))m->selected=(m->selected+2)&3;
  if(pressed&RTS_KEY_A){m->phase=RTS_MENU_ACTIONS;m->action=m->slots[m->selected].occupied ? RTS_MENU_LOAD : RTS_MENU_SAVE;}
 }
 else
 {
  if((pressed&(RTS_KEY_UP|RTS_KEY_DOWN)) && m->slots[m->selected].occupied)m->action=m->action==RTS_MENU_SAVE ? RTS_MENU_LOAD : RTS_MENU_SAVE;
  if(pressed&RTS_KEY_A){m->phase=RTS_MENU_BUSY;m->percent=0;return (enum RtsMenuAction)m->action;}
 }
 return RTS_MENU_NONE;
}
void RtsMenuSetProgress(RtsMenu* m,uint32_t completed,uint32_t total)
{
 unsigned percent=100;
 if(!total)percent=0;
 else if(completed<total){percent=0;/* No libgcc division or overflowing completed*100. */
  uint32_t step=total/100,remainder=total%100,threshold=0,carry=0;
  for(unsigned i=1;i<=100;++i){threshold+=step;carry+=remainder;if(carry>=100){++threshold;carry-=100;}if(threshold+(carry!=0)>completed)break;percent=i;}
 }
 m->percent=(uint8_t)percent;
}
void RtsMenuFinish(RtsMenu* m){m->percent=100;m->phase=RTS_MENU_CLOSED;}
static void two(char* p,unsigned x){p[0]='0'+(x/10)%10;p[1]='0'+x%10;}
void RtsMenuFormatTime(const RtsMenuTime* t,char date[11],char clock[9])
{
 if(!t->year){const char* d="----/--/--",*c="--:--:--";for(unsigned i=0;i<11;++i)date[i]=d[i];for(unsigned i=0;i<9;++i)clock[i]=c[i];return;}
 unsigned y=t->year;two(date,y/100);two(date+2,y);date[4]='/';two(date+5,t->month);date[7]='/';two(date+8,t->day);date[10]=0;
 two(clock,t->hour);clock[2]=':';two(clock+3,t->minute);clock[5]=':';two(clock+6,t->second);clock[8]=0;
}
int RtsMenuDebugEnabled(const char* t,size_t n)
{
 if(!t)return 1;
 if(n>=3 && (uint8_t)t[0]==239 && (uint8_t)t[1]==187 && (uint8_t)t[2]==191){t+=3;n-=3;}
 while(n && (*t==' ' || *t=='\r' || *t=='\n' || *t=='\t')){++t;--n;}
 while(n && (t[n-1]==' ' || t[n-1]=='\r' || t[n-1]=='\n' || t[n-1]=='\t'))--n;
 if((n==1 && *t=='0') || (n==3 && (t[0]=='o'||t[0]=='O') && (t[1]=='f'||t[1]=='F') && (t[2]=='f'||t[2]=='F')))return 0;
 return 1; /* Development default: missing/unrecognized/on/1 stays enabled. */
}
