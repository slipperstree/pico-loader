"""Read-only checker for M2 diagnostic captures. Never restores console memory."""
import json,struct,sys,zlib
from pathlib import Path

def check(path):
    data=Path(path).read_bytes()
    if len(data) not in (0x40c200,0x424400):raise ValueError(f'文件大小不符：{len(data)}')
    h=struct.unpack_from('<128I',data)
    m3=h[0]==0x31435452
    expected=(0x31435452,0x30001,0x424400,0x4a473241) if m3 else (0x324d5452,0x20001,0x40c200,0x4a473241)
    if h[:4]!=expected or len(data)!=expected[2] or h[5]!=len(data)-512:
        raise ValueError('文件标识或版本不符')
    if h[4]!=2:raise ValueError('尚未完成快照写入' if h[4]==0 else f'快照未完成或校验未通过（阶段 {h[4]}）')
    if h[18]:raise ValueError('快照记录了错误，不能作为成功捕获')
    value=zlib.crc32(data[512:])
    if h[19] not in (1,3):raise ValueError('快照诊断标记不符')
    fast=bool(h[19]&2)
    if value!=h[6] or (not fast and value!=h[17]):raise ValueError('快照载荷 CRC32 不符')
    if fast and h[17]!=0:raise ValueError('快速模式不得伪造完整读回 CRC')
    base,size=h[8:10]
    if base<0x02300000 or size==0 or size>0x10000 or base%512 or size%512 or base+size>0x023ff000:
        raise ValueError('工作区边界不符')
    if any(data[512+base-0x02000000:512+base-0x02000000+size]):raise ValueError('工作区排除区域未清零')
    if h[11]!=0x4000 or h[12]!=0x01ff8000 or h[13]!=0x8000:raise ValueError('TCM 布局不符')
    result={'result':'PASS','bytes':len(data),'sequence':h[7],'payload_crc32':f'{value:08X}',
            'workspace':f'{base:08X}+{size:04X}', 'dtcm_base':f'{h[10]:08X}',
            'capture':'4MiB RAM + 16KiB DTCM + 32KiB ITCM',
            'console_full_readback':not fast,'desktop_payload_crc_verified':True,
            'status':'M2 capture only; game-state load is not implemented'}
    if m3:
        a=struct.unpack_from('<128I',data,512+0x40c000)
        if h[46:50]!=(0x31433741,0x40c000,512,0x18000):raise ValueError('ARM7 分段布局不符')
        if a[0:2]!=(0x31433741,1) or a[4]!=1 or a[5]!=3 or a[3]&31 not in (18,31):raise ValueError('ARM7 上下文/WRAM 分配不符')
        if a[2]%4 or not (0x03800000<=a[2]<=0x03810000-48 or 0x02000000<=a[2]<=0x02400000-48 or 0x03000000<=a[2]<=0x03008000-48):raise ValueError('ARM7 栈地址不符')
        if h[8]<=a[2]<h[8]+h[9]:raise ValueError('ARM7 栈落在保留工作区')
        if a[2]>=0x03800000:offset=512+0x40c200+a[2]-0x03800000
        elif a[2]>=0x03000000:offset=512+0x41c200+a[2]-0x03000000
        else:offset=512+a[2]-0x02000000
        if data[offset:offset+48]!=data[512+0x40c000+32:512+0x40c000+80]:raise ValueError('ARM7 保存栈与上下文不一致')
        result['capture']+=' + ARM7 parked/banked context + 64KiB private WRAM + 32KiB shared WRAM'
        result['arm7']={'park_sp':f'{a[2]:08X}','mode':f'{a[3]&31:02X}','wram_allocation':a[5],'private_bytes':65536,'shared_bytes':32768}
        result['status']='M3.1 extended diagnostic capture only; game-state load is not implemented'
    if h[42]==0x31544650:
        result['timing_frames']={'write':h[43],'readback':h[44],'through_payload':h[45]}
        result['timing_seconds_approx_60hz']={k:round(v/60,2) for k,v in result['timing_frames'].items()}
    return result

if __name__=='__main__':
    try:print(json.dumps(check(sys.argv[1]),ensure_ascii=False,indent=2))
    except (ValueError,OSError,IndexError) as e:
        print('FAIL:',e);sys.exit(1)
