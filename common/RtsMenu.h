#pragma once
#include <stdint.h>
#include <stddef.h>
#define RTS_MENU_SLOT_COUNT 4u
#define RTS_MENU_WIDTH 256u
#define RTS_MENU_HEIGHT 192u
#define RTS_MENU_HOTKEY 0x0304u /* L + R + Select, active-high key bits */
#define RTS_MENU_DEBUG_PATH "/_pico/rts-debug.txt"
enum RtsMenuPhase {RTS_MENU_SLOTS,RTS_MENU_ACTIONS,RTS_MENU_BUSY,RTS_MENU_CLOSED};
enum RtsMenuAction {RTS_MENU_NONE,RTS_MENU_SAVE,RTS_MENU_LOAD,RTS_MENU_RESUME};
enum RtsMenuKeys {RTS_KEY_A=1,RTS_KEY_B=2,RTS_KEY_RIGHT=16,RTS_KEY_LEFT=32,RTS_KEY_UP=64,RTS_KEY_DOWN=128};
typedef struct {uint16_t year;uint8_t month,day,hour,minute,second,reserved;} RtsMenuTime;
typedef struct {uint8_t occupied,reserved[3];RtsMenuTime time;} RtsMenuSlot;
typedef struct {
 RtsMenuSlot slots[RTS_MENU_SLOT_COUNT];
 uint16_t previous_keys,repeat_frames;
 uint8_t selected,action,phase,debug_enabled,wait_hotkey_release,percent,reserved[2];
} RtsMenu;
typedef struct {RtsMenu previous;char debug[32];uint8_t initialized,reserved[3];} RtsMenuPaint;

typedef void (*RtsMenuBlit)(void* user,unsigned slot,uint16_t* pixels,unsigned stride,unsigned x,unsigned y);
#ifdef __cplusplus
extern "C" {
#endif
void RtsMenuInit(RtsMenu*,int debug_enabled);
enum RtsMenuAction RtsMenuTick(RtsMenu*,uint16_t active_high_keys);
void RtsMenuSetProgress(RtsMenu*,uint32_t completed,uint32_t total);
void RtsMenuFinish(RtsMenu*);
void RtsMenuFormatTime(const RtsMenuTime*,char date[11],char clock[9]);
void RtsMenuRender(const RtsMenu*,uint16_t pixels[256*192],RtsMenuBlit,void* user,const char* debug_line);
void RtsMenuRenderUpdate(const RtsMenu*,uint16_t pixels[256*192],RtsMenuPaint*,RtsMenuBlit,void* user,const char* debug_line);
int RtsMenuDebugEnabled(const char* text,size_t length);
#ifdef __cplusplus
}
#endif
