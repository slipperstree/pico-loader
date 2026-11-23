"""Read-only checker for M2 diagnostic captures. Never restores console memory."""
import json,struct,sys,zlib
from pathlib import Path

def check(path):
    data=Path(path).read_bytes()
    if len(data)!=0x40c200:raise ValueError(f'文件大小不符：{len(data)}，应为 4243968 字节')
    h=struct.unpack_from('<128I',data)
    if h[:4]!=(0x324d5452,0x20001,0x40c200,0x4a473241) or h[5]!=0x40c000:
        raise ValueError('文件标识或版本不符')
    if h[4]!=2:raise ValueError('尚未完成快照写入' if h[4]==0 else f'快照未完成或校验未通过（阶段 {h[4]}）')
    value=zlib.crc32(data[512:])
    if value!=h[6] or value!=h[17]:raise ValueError('快照载荷 CRC32 不符')
    if h[19]!=1:raise ValueError('快照诊断标记不符')
    base,size=h[8:10]
    if base<0x02300000 or size==0 or size>0x10000 or base%512 or size%512 or base+size>0x023ff000:
        raise ValueError('工作区边界不符')
    if any(data[512+base-0x02000000:512+base-0x02000000+size]):raise ValueError('工作区排除区域未清零')
    if h[11]!=0x4000 or h[12]!=0x01ff8000 or h[13]!=0x8000:raise ValueError('TCM 布局不符')
    return {'result':'PASS','bytes':len(data),'sequence':h[7],'payload_crc32':f'{value:08X}',
            'workspace':f'{base:08X}+{size:04X}', 'dtcm_base':f'{h[10]:08X}',
            'capture':'4MiB RAM + 16KiB DTCM + 32KiB ITCM',
            'status':'M2 capture only; game-state load is not implemented'}

if __name__=='__main__':
    try:print(json.dumps(check(sys.argv[1]),ensure_ascii=False,indent=2))
    except (ValueError,OSError,IndexError) as e:
        print('FAIL:',e);sys.exit(1)
