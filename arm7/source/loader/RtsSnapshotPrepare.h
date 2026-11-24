#pragma once
#include "RtsSnapshotInfo.h"
#ifdef PICO_RTS_MENU
#include "RtsMenuRuntime.h"
bool PrepareRtsMenuFiles(RtsMenuBoot&,const char*,uint32_t);
#endif
bool PrepareRtsSnapshotFile(RtsSnapshotInfo& info,const char* path=RTS_M2_FILE_PATH,uint32_t gameCode=RTS_M2_GAME);
