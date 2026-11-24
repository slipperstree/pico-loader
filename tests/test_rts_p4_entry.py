from pathlib import Path
import sys
r=Path(sys.argv[1]);test=r/'tests/test_rts_p4_worker.py';s=test.read_text(encoding='utf-8').split('disk={physical[0]:bytes(blank)}')[0]
s=s.replace('u=Uc(UC_ARCH_ARM,UC_MODE_ARM);a7=', 'u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.ctl_set_cpu_model(UC_CPU_ARM_946);a7=')
s=s.replace("def stage(cpu,a,n,d):state['stages'].append((cpu.reg_read(UC_ARM_REG_R0),cpu.reg_read(UC_ARM_REG_R1)))", "def stage(cpu,a,n,d):\n  state['stages'].append((cpu.reg_read(UC_ARM_REG_R0),cpu.reg_read(UC_ARM_REG_R1)));cpu.emu_stop()")
s=s.replace('done9=0x020f0000','done9=entryregs[13]&~1')
s=s.replace('and not base<=a<limit:', 'and not base<=a<limit and not entry<=a<frame:')
s=s.replace('u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,stack+1024);u.reg_write(UC_ARM_REG_LR,done9);u.reg_write(UC_ARM_REG_R0,entry)', 'u.reg_write(UC_ARM_REG_CPSR,0xdf);u.reg_write(UC_ARM_REG_SP,frame);u.reg_write(UC_ARM_REG_LR,entryregs[13])\n for reg,value in zip(REGS,entryregs[:13]):u.reg_write(reg,value)')
s=s.replace("u.emu_start(syms['rtsM2Run']|1", "u.emu_start(base+meta['entry_offset']")
s=s.replace(" if partial:\n  assert state['fault']", " if state['stages']==[(0,0)]:print('PASS actual ARM946 worker wrapper -> Thumb entry -> first S0 progress stage');return state\n if partial:\n  assert state['fault']")
g={'__file__':str(test)};exec(compile(s,str(test),'exec'),g);g['make']({g['physical'][0]:bytes(g['blank'])})
