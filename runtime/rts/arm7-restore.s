// Original ARM7TDMI restore research. No live call site or load hotkey.
.cpu arm7tdmi
.syntax unified
.arm
.section .text.rtsArm7Restore,"ax"
.global rtsArm7RestoreSector, rtsEnterArm7Continuation
.type rtsArm7RestoreSector,%function
// Stackless sector writer, executable in main RAM while private WRAM is replaced.
rtsArm7RestoreSector:
    cmp r0,#192
    bhs refuse
    mrs r2,cpsr
    and r3,r2,#192
    cmp r3,#192
    bne refuse
    and r2,r2,#31
    cmp r2,#31
    cmpne r2,#18
    bne refuse
    tst r1,#3
    bne refuse
    mov r2,#0x02000000
    cmp r1,r2
    blo refuse
    bic r12,lr,#1
    cmp r12,r2
    blo refuse
    mov r3,#0x02400000
    cmp r12,r3
    bhs refuse
    sub r3,r3,#512
    cmp r1,r3
    bhi refuse
    ldr r2,=0x04000208
    ldr r2,[r2]
    cmp r2,#0
    bne refuse
    cmp r0,#128
    blo private
    ldr r2,=0x04000241
    ldrb r2,[r2]
    and r2,r2,#3
    cmp r2,#3
    bne refuse
    sub r0,r0,#128
    mov r2,#0x03000000
    b copy
private:
    mov r2,#0x03800000
copy:
    add r2,r2,r0,lsl #9
    add r3,r1,#512
1:  ldr r12,[r1],#4
    str r12,[r2],#4
    cmp r1,r3
    blo 1b
    mov r0,#1
    bx lr
refuse:
    mov r0,#0
    bx lr

.type rtsEnterArm7Continuation,%function
// r0=externally validated stable main-RAM context. Memory/hardware already
// restored, both CPUs controlled. Restores the original VBlank epilogue ABI:
// r0/r1 are caller-scratch; r2-r12/LR, banked state, SP/CPSR and IME restored.
rtsEnterArm7Continuation:
    mrs r1,cpsr
    orr r1,r1,#192
    msr cpsr_c,r1
    bic r1,r1,#31
    orr r2,r1,#31
    msr cpsr_c,r2
    ldr sp,[r0,#80]
    ldr lr,[r0,#84]
    orr r2,r1,#18
    msr cpsr_c,r2
    ldr sp,[r0,#92]
    ldr lr,[r0,#96]
    ldr r3,[r0,#100]
    msr spsr_cxsf,r3
    orr r2,r1,#19
    msr cpsr_c,r2
    ldr sp,[r0,#104]
    ldr lr,[r0,#108]
    ldr r3,[r0,#112]
    msr spsr_cxsf,r3
    orr r2,r1,#23
    msr cpsr_c,r2
    ldr sp,[r0,#116]
    ldr lr,[r0,#120]
    ldr r3,[r0,#124]
    msr spsr_cxsf,r3
    orr r2,r1,#27
    msr cpsr_c,r2
    ldr sp,[r0,#128]
    ldr lr,[r0,#132]
    ldr r3,[r0,#136]
    msr spsr_cxsf,r3
    orr r2,r1,#17
    msr cpsr_c,r2
    ldr sp,[r0,#140]
    ldr lr,[r0,#144]
    ldr r3,[r0,#148]
    msr spsr_cxsf,r3
    add r2,r0,#152
    ldmia r2,{r8-r12}
    ldr r2,[r0,#12]
    orr r3,r2,#192
    msr cpsr_c,r3
    ldr sp,[r0,#8]
    add sp,sp,#48              // Original hook would pop r2-r12/LR here.
    ldr r3,[r0,#16]
    ldr r1,=0x04000208
    str r3,[r1]
    msr cpsr_cxsf,r2
    add r0,r0,#32
    ldmia r0,{r2-r12,lr}
    bx lr
.ltorg
