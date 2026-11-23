#pragma once
#include "sections.h"
#include "patches/PatchCode.h"
#include "../IWriteSectorsPatchCode.h"

DEFINE_SECTION_SYMBOLS(dspico_writesdsectors);

extern "C" void dspico_writeSdSectors(u32 dstSector, const void* src, u32 sectorCount);

#ifdef PICO_RTS_SNAPSHOT
extern u32 dspico_writesdsectors_busy;
#endif

class DSPicoWriteSdSectorsPatchCode : public PatchCode, public IWriteSectorsPatchCode
{
public:
#ifdef PICO_RTS_SNAPSHOT
    inline static u32 busyAddress=0;
#endif
    explicit DSPicoWriteSdSectorsPatchCode(PatchHeap& patchHeap)
        : PatchCode(SECTION_START(dspico_writesdsectors), SECTION_SIZE(dspico_writesdsectors), patchHeap) {
#ifdef PICO_RTS_SNAPSHOT
        busyAddress=(u32)GetAddressAtTarget(&dspico_writesdsectors_busy);
#endif
    }

    const WriteSectorsFunc GetWriteSectorFunction() const override
    {
        return (const WriteSectorsFunc)GetAddressAtTarget((void*)dspico_writeSdSectors);
    }
};
