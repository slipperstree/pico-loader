#include "common.h"
#ifdef PICO_RTS_SNAPSHOT
#include <memory>
#include <cstring>
#include "fat/ff.h"
#include "RtsSnapshotPrepare.h"

static bool fullVerifyRequested()
{
    // Absent, unreadable or unrecognised configuration falls back to full.
    FIL file;
    if(f_open(&file,RTS_M2_VERIFY_PATH,FA_READ)!=FR_OK)return true;
    char mode[16]{};UINT count=0;
    bool ok=f_read(&file,mode,sizeof(mode)-1,&count)==FR_OK;
    ok=(f_close(&file)==FR_OK)&&ok;
    if(!ok)return true;
    while(count && (mode[count-1]=='\r' || mode[count-1]=='\n' || mode[count-1]==' ' || mode[count-1]=='\t'))mode[--count]=0;
    const char* value=mode;
    if(count>=3 && (unsigned char)mode[0]==0xef && (unsigned char)mode[1]==0xbb && (unsigned char)mode[2]==0xbf)value+=3;
    return strcmp(value,"fast")!=0;
}

bool PrepareRtsSnapshotFile(RtsSnapshotInfo& info)
{
    memset(&info,0,sizeof(info));
    FIL file;
    if (f_open(&file, RTS_M2_FILE_PATH, FA_OPEN_ALWAYS|FA_READ|FA_WRITE) != FR_OK) return false;
    auto close = [&]() { return f_close(&file)==FR_OK; };
    RtsM2Header header {};
    UINT done=0;
    if (f_size(&file)==0)
    {
        header.magic=RTS_M2_MAGIC;
        header.version=RTS_M2_VERSION;
        header.fileBytes=RTS_M2_FILE_BYTES;
        header.gameCode=RTS_M2_GAME;
        header.payloadBytes=RTS_M2_PAYLOAD_BYTES;
        if (f_write(&file,&header,sizeof(header),&done)!=FR_OK || done!=sizeof(header)) {close();return false;}
        auto zero=std::make_unique<u32[]>(1024);
        memset(zero.get(),0,4096);
        for (u32 left=RTS_M2_PAYLOAD_BYTES; left;)
        {
            u32 amount=left>4096 ? 4096 : left;
            if (f_write(&file,zero.get(),amount,&done)!=FR_OK || done!=amount) {close();return false;}
            left-=amount;
        }
        if (f_sync(&file)!=FR_OK) {close();return false;}
    }
    else
    {
        if (f_size(&file)!=RTS_M2_FILE_BYTES || f_read(&file,&header,sizeof(header),&done)!=FR_OK || done!=sizeof(header) ||
            header.magic!=RTS_M2_MAGIC || header.version!=RTS_M2_VERSION || header.fileBytes!=RTS_M2_FILE_BYTES ||
            header.gameCode!=RTS_M2_GAME || header.payloadBytes!=RTS_M2_PAYLOAD_BYTES)
        { close();return false; } // Never replace a foreign or incompatible file.
    }
    DWORD map[RTS_M2_MAX_EXTENTS*2+2] {};
    map[0]=sizeof(map)/sizeof(map[0]);
    file.cltbl=map;
    if (f_lseek(&file,CREATE_LINKMAP)!=FR_OK) {file.cltbl=nullptr;close();return false;}
    const auto fs=file.obj.fs;
    if (fs->csize==0 || (fs->csize & (fs->csize-1)) || fs->n_fatent<3) {close();return false;}
    uint64_t end=(uint64_t)fs->database+(uint64_t)(fs->n_fatent-2)*fs->csize;
    if (end>UINT32_MAX) {close();return false;}
    info.dataStart=fs->database;
    info.dataEnd=(u32)end;
    u32 left=RTS_M2_FILE_SECTORS;
    for (u32 i=1; i+1<sizeof(map)/sizeof(map[0]) && map[i]; i+=2)
    {
        u32 clusters=map[i], cluster=map[i+1];
        if (!left || info.extentCount>=RTS_M2_MAX_EXTENTS || cluster<2 || cluster>=fs->n_fatent ||
            clusters>fs->n_fatent-cluster) {close();return false;}
        uint64_t first=(uint64_t)fs->database+(uint64_t)(cluster-2)*fs->csize;
        uint64_t count=(uint64_t)clusters*fs->csize;
        if (first<info.dataStart || first+count>info.dataEnd) {close();return false;}
        u32 take=count>left ? left : (u32)count;
        for (u32 j=0;j<info.extentCount;++j)
        {
            auto e=info.extents[j];
            if (first<(uint64_t)e.sector+e.count && e.sector<first+take) {close();return false;}
        }
        info.extents[info.extentCount++]={take,(u32)first};
        left-=take;
    }
    file.cltbl=nullptr;
    if (!close() || left) {memset(&info,0,sizeof(info));return false;}
    info.version=RTS_M2_VERSION;
    info.fileSectors=RTS_M2_FILE_SECTORS;
    info.gameCode=RTS_M2_GAME;
    info.reserved=fullVerifyRequested() ? RTS_M2_CONFIG_FULL_VERIFY : 0;
    info.magic=RTS_M2_MAGIC; // Publish only a complete, closed and synced mapping.
    return true;
}
#endif
