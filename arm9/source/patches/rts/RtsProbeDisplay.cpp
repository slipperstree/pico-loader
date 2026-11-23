// Research-only prompt. The upstream ErrorDisplay borrows 0x02100000, which
// must not be used after a game's binaries have been loaded.
#include "common.h"
#ifdef PICO_RTS_PROBE
#include <libtwl/mem/memVram.h>
#include <libtwl/gfx/gfx.h>
#include <libtwl/gfx/gfxStatus.h>
#include <libtwl/gfx/gfxPalette.h>
#include <libtwl/gfx/gfxBackground.h>
#include "errorDisplay/nitroFont2.h"
#include "font_nft2.h"
#include "fastClear.h"
#include "RtsProbe.h"

static void waitFrame()
{
    while (gfx_getVCount() != 191);
    while (gfx_getVCount() == 191);
}

extern "C" [[gnu::noinline]] void rtsProbeMessage(const char* message)
{
    // The loader's stack lives in its own DTCM, not the game's main RAM.
    alignas(4) u8 strip[256*16];
    nft2_header_t font = *(const nft2_header_t*)font_nft2;
    const u32 base = (u32)font_nft2;
    auto resolve = [base](u32 value) { return value < base ? base+value : value; };
    // Existing error prompts may already have unpacked this shared asset.
    // Normalize a LOCAL header; never unpack/modify the asset twice.
    font.glyphInfoPtr = (const nft2_glyph_t*)resolve((u32)font.glyphInfoPtr);
    font.charMapPtr = (const nft2_char_map_entry_t*)resolve((u32)font.charMapPtr);
    font.glyphDataPtr = (const u8*)resolve((u32)font.glyphDataPtr);
    mem_setVramEMapping(MEM_VRAM_E_MAIN_BG_00000);
    for (int row = 0; row < 192; row += 16)
    {
        memset(strip, 0, sizeof(strip));
        nft2_string_render_params_t params { .x=0, .y=-row, .width=256, .height=16, .textWidth=0 };
        nft2_renderString(&font, message, strip, 256, &params);
        // Word-copy to VRAM: byte writes to a framebuffer are not suitable.
        memcpy((u8*)GFX_BG_MAIN + row*256, strip, sizeof(strip));
    }
    waitFrame();
    for (int i=0; i<16; ++i)
    {
        int gray = i*2+(i ? 1 : 0);
        GFX_PLTT_BG_MAIN[i] = gray | (gray<<5) | (gray<<10);
    }
    REG_BG3PA=256; REG_BG3PB=0; REG_BG3PC=0; REG_BG3PD=256;
    REG_BG3X=0; REG_BG3Y=0;
    REG_BG3CNT=(1<<7)|(1<<14);
    REG_BLDCNT=0;
    REG_DISPCNT=3|(1<<11)|(1<<16);
    REG_MASTER_BRIGHT=0;
    GFX_PLTT_BG_SUB[0]=0;
    REG_MASTER_BRIGHT_SUB=0x8010;
    REG_DISPCNT_SUB=0x10000;
    waitFrame();
    bool previousA = ((~REG_KEYINPUT)&KEY_A) != 0;
    for (;;)
    {
        waitFrame();
        bool pressedA = ((~REG_KEYINPUT)&KEY_A) != 0;
        if (!previousA && pressedA) break;
        previousA = pressedA;
    }
    REG_MASTER_BRIGHT=0x4010;
    REG_MASTER_BRIGHT_SUB=0x4010;
    REG_DISPCNT=0;
    REG_DISPCNT_SUB=0;
    mem_setVramEMapping(MEM_VRAM_E_LCDC);
    fastClear((void*)0x06880000,0x10000);
    fastClear((void*)GFX_PLTT_BG_MAIN,512);
    fastClear((void*)GFX_PLTT_BG_SUB,512);
}
#endif
