#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cassert>
#include <initializer_list>
#include "fat/ff.h"
#include "fat/diskio.h"
#include "RtsSnapshotPrepare.h"
static FILE* image;
extern "C" DSTATUS disk_initialize(BYTE d){return d || !image ? STA_NOINIT : 0;}
extern "C" DSTATUS disk_status(BYTE d){return disk_initialize(d);}
extern "C" DRESULT disk_read(BYTE d,BYTE* b,DWORD s,UINT n){return d || fseek(image,(long)s*512,SEEK_SET) || fread(b,512,n,image)!=n ? RES_ERROR : RES_OK;}
extern "C" DRESULT disk_write(BYTE d,const BYTE* b,DWORD s,UINT n){return d || fseek(image,(long)s*512,SEEK_SET) || fwrite(b,512,n,image)!=n ? RES_ERROR : RES_OK;}
extern "C" DRESULT disk_ioctl(BYTE d,BYTE c,void* b){if(d)return RES_PARERR;if(c==CTRL_SYNC)return fflush(image) ? RES_ERROR : RES_OK;if(c==GET_SECTOR_COUNT){*(DWORD*)b=131072;return RES_OK;}if(c==GET_SECTOR_SIZE){*(WORD*)b=512;return RES_OK;}if(c==GET_BLOCK_SIZE){*(DWORD*)b=1;return RES_OK;}return RES_PARERR;}
static void check(FRESULT r){assert(r==FR_OK);}
static void write(FIL* f,const void* b,UINT n){UINT done=0;check(f_write(f,b,n,&done));assert(done==n);}
#ifdef PICO_RTS_RESTORE_PROBE
static void seal(RtsM2Header& h){h.reserved[82]=0;uint32_t c=~0u;auto b=(const unsigned char*)&h;for(unsigned i=0;i<512;++i){c^=b[i];for(unsigned j=0;j<8;++j)c=(c>>1)^(0xedb88320u&-(c&1));}h.reserved[82]=~c;}
#endif
static RtsM2Header initialHeader(){RtsM2Header h{};h.magic=RTS_M2_MAGIC;h.version=RTS_M2_VERSION;h.fileBytes=RTS_M2_FILE_BYTES;h.gameCode=RTS_M2_GAME;h.payloadBytes=RTS_M2_PAYLOAD_BYTES;
#ifdef PICO_RTS_RESTORE_PROBE
seal(h);
#endif
return h;}
static void fragmented(unsigned interval){
    check(f_unlink(RTS_M2_FILE_PATH));
    FIL f;check(f_open(&f,RTS_M2_FILE_PATH,FA_CREATE_ALWAYS|FA_WRITE));
    auto h=initialHeader();write(&f,&h,512);
    unsigned char zero[4096]{};unsigned block=0;
    for(unsigned n=0;n<RTS_M2_PAYLOAD_BYTES;n+=4096){
        write(&f,zero,RTS_M2_PAYLOAD_BYTES-n<4096 ? RTS_M2_PAYLOAD_BYTES-n : 4096);
        if(n%interval==0){char name[64];std::snprintf(name,sizeof(name),"/_pico/B%u-%u.dat",interval,block++);FIL b;check(f_open(&b,name,FA_CREATE_ALWAYS|FA_WRITE));write(&b,zero,sizeof(zero));check(f_close(&b));}
    }
    check(f_close(&f));
}
int main(int argc,char** argv){
    assert(argc==2);image=std::fopen(argv[1],"r+b");assert(image);
    FATFS fs;check(f_mount(&fs,"fat:",1));check(f_mkdir("/_pico"));
    RtsSnapshotInfo info;
    assert(PrepareRtsSnapshotFile(info));
    assert(info.magic==RTS_M2_MAGIC && info.extentCount && info.dataStart>=32);
    assert(info.reserved==RTS_M2_CONFIG_FULL_VERIFY); // Missing config -> full.
#ifdef PICO_RTS_RESTORE_PROBE
    // A non-ASCII per-ROM path is independent of the default research file.
    check(f_mkdir("/中文目录"));
    const char* named="/中文目录/逆转裁判2.rts";
    assert(PrepareRtsSnapshotFile(info,named));FIL namedFile;check(f_open(&namedFile,named,FA_READ));assert(f_size(&namedFile)==RTS_M2_FILE_BYTES);check(f_close(&namedFile));check(f_unlink(named));
    const char* other="/中文目录/另一游戏.rts";
    assert(PrepareRtsSnapshotFile(info,other,0x454d4147));assert(info.gameCode==0x454d4147);
    assert(PrepareRtsSnapshotFile(info,other,0x454d4147));
    assert(!PrepareRtsSnapshotFile(info,other,0x4a473241));check(f_unlink(other));
    puts("PASS per-game gameCode: arbitrary game accepted, foreign slot kept separate");
    // Simulated reboot must preserve all bytes of a completed checkpoint header.
    FIL saved;check(f_open(&saved,RTS_M2_FILE_PATH,FA_READ|FA_WRITE));
    RtsM2Header persistent{};UINT count=0;check(f_read(&saved,&persistent,512,&count));assert(count==512);
    persistent.phase=2;persistent.sequence=123;persistent.payloadCrc=0x12345678;persistent.reserved[62]=0xabcd;seal(persistent);
    check(f_lseek(&saved,0));write(&saved,&persistent,512);check(f_close(&saved));
    assert(PrepareRtsSnapshotFile(info));
    check(f_open(&saved,RTS_M2_FILE_PATH,FA_READ));RtsM2Header after{};check(f_read(&saved,&after,512,&count));check(f_close(&saved));assert(std::memcmp(&persistent,&after,512)==0);
#endif
    FIL mode;check(f_open(&mode,RTS_M2_VERIFY_PATH,FA_CREATE_ALWAYS|FA_WRITE));write(&mode,"fast\r\n",6);check(f_close(&mode));
    assert(PrepareRtsSnapshotFile(info) && info.reserved==0);
    check(f_open(&mode,RTS_M2_VERIFY_PATH,FA_CREATE_ALWAYS|FA_WRITE));write(&mode,"\xef\xbb\xbf" "fast\n",8);check(f_close(&mode));
    assert(PrepareRtsSnapshotFile(info) && info.reserved==0);
    check(f_open(&mode,RTS_M2_VERIFY_PATH,FA_CREATE_ALWAYS|FA_WRITE));write(&mode,"full\n",5);check(f_close(&mode));
    assert(PrepareRtsSnapshotFile(info) && info.reserved==RTS_M2_CONFIG_FULL_VERIFY);
    check(f_open(&mode,RTS_M2_VERIFY_PATH,FA_CREATE_ALWAYS|FA_WRITE));write(&mode,"invalid",7);check(f_close(&mode));
    assert(PrepareRtsSnapshotFile(info) && info.reserved==RTS_M2_CONFIG_FULL_VERIFY);
    puts("PASS save verify config: missing/full/invalid -> full, fast CRLF -> fast");
#ifdef PICO_RTS_RESTORE_PROBE
    assert(!(info.reserved&RTS_P4_CONFIG_LOAD_VERIFY));
    for(const char* value:{"full\r\n","\xef\xbb\xbf" "full\n","fast\n","invalid"})
    {
        check(f_open(&mode,RTS_P4_LOAD_VERIFY_PATH,FA_CREATE_ALWAYS|FA_WRITE));write(&mode,value,(UINT)std::strlen(value));check(f_close(&mode));
        assert(PrepareRtsSnapshotFile(info));bool full=std::strstr(value,"full");assert(bool(info.reserved&RTS_P4_CONFIG_LOAD_VERIFY)==full);
        assert(info.reserved&RTS_M2_CONFIG_FULL_VERIFY); // Independent from save configuration.
    }
    check(f_unlink(RTS_P4_LOAD_VERIFY_PATH));assert(PrepareRtsSnapshotFile(info) && !(info.reserved&RTS_P4_CONFIG_LOAD_VERIFY));
    puts("PASS load CRC opt-in: missing/fast/invalid off; full/BOM+CRLF on; independent save option");
#endif
    FIL f;check(f_open(&f,RTS_M2_FILE_PATH,FA_READ));assert(f_size(&f)==RTS_M2_FILE_BYTES);check(f_close(&f));
    unsigned sum=0;for(unsigned i=0;i<info.extentCount;++i){assert(info.extents[i].sector>=info.dataStart);assert(info.extents[i].count<=info.dataEnd-info.extents[i].sector);sum+=info.extents[i].count;}assert(sum==RTS_M2_FILE_SECTORS);
    unsigned last=info.extents[info.extentCount-1].sector+info.extents[info.extentCount-1].count-1;
    unsigned char sentinel[512];std::memset(sentinel,0x6b,512);
    assert(std::fseek(image,(long)last*512,SEEK_SET)==0);assert(std::fwrite(sentinel,1,512,image)==512);std::fflush(image);
    assert(PrepareRtsSnapshotFile(info));
    check(f_open(&f,RTS_M2_FILE_PATH,FA_READ));check(f_lseek(&f,RTS_M2_FILE_BYTES-512));unsigned char readback[512];UINT done;check(f_read(&f,readback,512,&done));assert(done==512 && !std::memcmp(readback,sentinel,512));check(f_close(&f));
    puts("PASS actual FatFs + preparer: create, close/sync, exact file length, physical last-sector map, existing payload preserved");
    check(f_open(&f,RTS_M2_FILE_PATH,FA_WRITE));unsigned foreign=0x12345678;write(&f,&foreign,4);check(f_close(&f));
    assert(!PrepareRtsSnapshotFile(info) && info.magic==0);
    check(f_open(&f,RTS_M2_FILE_PATH,FA_READ));unsigned seen=0;check(f_read(&f,&seen,4,&done));assert(seen==foreign && f_size(&f)==RTS_M2_FILE_BYTES);check(f_close(&f));
    puts("PASS foreign/incompatible file contents are not overwritten");
    fragmented(256*1024);
    assert(PrepareRtsSnapshotFile(info) && info.extentCount>1 && info.extentCount<=RTS_M2_MAX_EXTENTS);
    puts("PASS actual fragmented FAT chain accepted within extent budget");
    fragmented(64*1024);
    assert(!PrepareRtsSnapshotFile(info) && info.magic==0);
    puts("PASS excessive fragmentation rejected without publishing a runtime sector map");
    check(f_mount(nullptr,"fat:",0));std::fclose(image);
}
