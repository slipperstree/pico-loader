// Original ARM946E-S state capture; no CP15 writes or game-stack accesses.
.cpu arm946e-s
.syntax unified
.arm
// Optional P4.3 trace: never touches a mode's banked stack. Preserve all
// scratch registers, LR and flags in unused CPU-record padding.
.macro cpu_trace number
.ifdef RTS_TRACE_CPU
    str lr,[r0,#192]
    str r1,[r0,#196]
    str r2,[r0,#200]
    str r3,[r0,#204]
    str r12,[r0,#208]
    mrs r2,cpsr
    str r2,[r0,#212]
    mov r3,#\number
    bl rtsCpuTraceDigit
    ldr r2,[r0,#212]
    msr cpsr_f,r2
    ldr r1,[r0,#196]
    ldr r2,[r0,#200]
    ldr r3,[r0,#204]
    ldr r12,[r0,#208]
    ldr lr,[r0,#192]
.endif
.endm
.section .text.rtsCaptureArm9Cpu,"ax"
.global rtsCaptureArm9Cpu
.type rtsCaptureArm9Cpu,%function
rtsCaptureArm9Cpu:
    str r1,[r0,#184]
    str r2,[r0,#188]
    str r3,[r0,#12]
    mrs r1,cpsr
    str r1,[r0,#8]
    cpu_trace 1
    bic r1,r1,#31
    orr r1,r1,#192
    orr r2,r1,#31
    msr cpsr_c,r2
    str sp,[r0,#16]
    str lr,[r0,#20]
    mov r3,#0
    str r3,[r0,#24]
    cpu_trace 2
    orr r2,r1,#18
    msr cpsr_c,r2
    str sp,[r0,#28]
    str lr,[r0,#32]
    mrs r3,spsr
    str r3,[r0,#36]
    cpu_trace 3
    orr r2,r1,#19
    msr cpsr_c,r2
    str sp,[r0,#40]
    str lr,[r0,#44]
    mrs r3,spsr
    str r3,[r0,#48]
    cpu_trace 4
    orr r2,r1,#23
    msr cpsr_c,r2
    str sp,[r0,#52]
    str lr,[r0,#56]
    mrs r3,spsr
    str r3,[r0,#60]
    cpu_trace 5
    orr r2,r1,#27
    msr cpsr_c,r2
    str sp,[r0,#64]
    str lr,[r0,#68]
    mrs r3,spsr
    str r3,[r0,#72]
    cpu_trace 6
    orr r2,r1,#17
    msr cpsr_c,r2
    str sp,[r0,#76]
    str lr,[r0,#80]
    mrs r3,spsr
    str r3,[r0,#84]
    add r2,r0,#88
    stmia r2,{r8-r12}
    cpu_trace 7
    ldr r1,[r0,#8]
    msr cpsr_cxsf,r1
    cpu_trace 8
    mrc p15,0,r2,c1,c0,0
    str r2,[r0,#108]
    cpu_trace 9
    mrc p15,0,r2,c2,c0,0
    str r2,[r0,#112]
    cpu_trace 10
    mrc p15,0,r2,c2,c0,1
    str r2,[r0,#116]
    cpu_trace 11
    mrc p15,0,r2,c3,c0,0
    str r2,[r0,#120]
    cpu_trace 12
    mrc p15,0,r2,c5,c0,2
    str r2,[r0,#124]
    cpu_trace 13
    mrc p15,0,r2,c5,c0,3
    str r2,[r0,#128]
    cpu_trace 14
    mrc p15,0,r2,c6,c0,0
    str r2,[r0,#132]
    cpu_trace 15
    mrc p15,0,r2,c6,c1,0
    str r2,[r0,#136]
    cpu_trace 16
    mrc p15,0,r2,c6,c2,0
    str r2,[r0,#140]
    cpu_trace 17
    mrc p15,0,r2,c6,c3,0
    str r2,[r0,#144]
    cpu_trace 18
    mrc p15,0,r2,c6,c4,0
    str r2,[r0,#148]
    cpu_trace 19
    mrc p15,0,r2,c6,c5,0
    str r2,[r0,#152]
    cpu_trace 20
    mrc p15,0,r2,c6,c6,0
    str r2,[r0,#156]
    cpu_trace 21
    mrc p15,0,r2,c6,c7,0
    str r2,[r0,#160]
    cpu_trace 22
    mrc p15,0,r2,c9,c1,0
    str r2,[r0,#164]
    cpu_trace 23
    mrc p15,0,r2,c9,c1,1
    str r2,[r0,#168]
    cpu_trace 24
    mrc p15,0,r2,c9,c0,0
    str r2,[r0,#172]
    cpu_trace 25
    mrc p15,0,r2,c9,c0,1
    str r2,[r0,#176]
    cpu_trace 26
    mrc p15,0,r2,c13,c0,1
    str r2,[r0,#180]
    cpu_trace 27
    ldr r2,[r0,#184]
    str r2,[r0,#16]
    ldr r2,[r0,#188]
    str r2,[r0,#20]
    ldr r2,[r0,#12]
    str r2,[r0,#140]           // Snapshot pre-guard region 2, not temporary 0.
    mov r2,#0
    str r2,[r0,#12]
    str r2,[r0,#184]
    str r2,[r0,#188]
    mov r2,#1
    str r2,[r0,#4]
    ldr r2,=0x31503941
    str r2,[r0]                // Publish complete snapshot last.
    cpu_trace 28
.ifdef RTS_TRACE_CPU
    mov r2,#0
    .set trace_clear,192
    .rept 11
    str r2,[r0,#trace_clear]
    .set trace_clear,trace_clear+4
    .endr
.endif
    bx lr
.ltorg

.ifdef RTS_TRACE_CPU
.section .text.rtsCpuTraceDigit,"ax"
.type rtsCpuTraceDigit,%function
rtsCpuTraceDigit:
    mov r1,#0
1:  cmp r3,#10
    subge r3,r3,#10
    addge r1,r1,#1
    bge 1b
    str r3,[r0,#216]
    str r1,[r0,#220]
    mov r3,#0
    str r3,[r0,#232]
    ldr r2,=0x0684006c // ones digit: text column 9, pixel x54
    ldr r12,[r0,#216]
2:  ldr r1,=gRtsDigits
    add r12,r12,r12,lsl #2
    add r1,r1,r12
    mov r3,#5
3:  ldrb r12,[r1],#1
    str r1,[r0,#224]
    str r3,[r0,#228]
    mov r1,#7
4:  tst r12,#1
    ldrne r3,=0xffff
    moveq r3,#0x8000
    strh r3,[r2]
    add r2,r2,#512
    mov r12,r12,lsr #1
    subs r1,r1,#1
    bne 4b
    sub r2,r2,#3584
    add r2,r2,#2
    ldr r1,[r0,#224]
    ldr r3,[r0,#228]
    subs r3,r3,#1
    bne 3b
    ldr r3,[r0,#232]
    cmp r3,#0
    bne 5f
    mov r3,#1
    str r3,[r0,#232]
    ldr r12,[r0,#220]
    ldr r2,=0x06840060 // tens digit: text column 8, pixel x48
    b 2b
5:  bx lr
.ltorg
.endif

// All stack stores occur BEFORE the final clean. No C code may run between
// this clean and disabling D-cache, or fresh dirty stack values can be lost.
.section .text.rtsFlushCachesAndEnter,"ax"
.global rtsFlushCachesAndEnter
.type rtsFlushCachesAndEnter,%function
rtsFlushCachesAndEnter:
    stmdb sp!,{r4-r8,lr}
    mov r4,r0
    mov r5,r1
    mov r6,r2
    mov r7,r3
    mov r0,#0
    mov r3,#0
1:  mov r1,#0
2:  orr r2,r0,r1
    mcr p15,0,r3,c7,c10,4
    mcr p15,0,r2,c7,c14,2
    add r1,r1,#32
    cmp r1,#0x400
    blo 2b
    adds r0,r0,#0x40000000
    bne 1b
    mcr p15,0,r3,c7,c10,4
    mov r0,r7
    cpu_trace 31 // Only disposable CPU-record padding and uncached VRAM.
    mov r3,#0
    mcr p15,0,r3,c7,c5,0
    mcr p15,0,r4,c2,c0,1
    mcr p15,0,r5,c3,c0,0
    mcr p15,0,r6,c1,c0,0
    ldmia sp!,{r4-r8,pc}

// Exact IPC boundary. D-cache and write buffer are already off.
// r0 is disposable CPU-record scratch for optional stackless stamps.
.section .text.rtsP4SendStart7,"ax"
.global rtsP4SendStart7
.type rtsP4SendStart7,%function
rtsP4SendStart7:
    cpu_trace 43
    mov r12,#0x04000000
    add r12,r12,#0x180
    ldrh r1,[r12]
    cpu_trace 44
    // Preserve IRQ-enable only; never echo send-IRQ bit 13.
    and r1,r1,#0x4000
    orr r1,r1,#0x800
    strh r1,[r12]
    cpu_trace 45
    ldrh r1,[r12]
    and r0,r1,#0xf00
    bx lr
.ltorg
