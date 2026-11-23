// M3 research only; deliberately not linked into the live M2 Loader.
.cpu arm946e-s
.syntax unified
.arm
.section .text.rtsArm9Continuation,"ax"
.global rtsEnterArm9Continuation
.type rtsEnterArm9Continuation,%function
rtsEnterArm9Continuation:
    mrs r3,cpsr
    orr r3,r3,#0xc0
    bic r3,r3,#0x1f
    orr r3,r3,#0x12
    msr cpsr_c,r3
    ldr r2,[r0]
    msr spsr_cxsf,r2
    add r1,r0,#4
    ldmia r1,{r13,r14}^
    nop                     // ARMv5 banked-register transfer interlock.
    add r0,r0,#12
    ldmia r0,{r0-r12,pc}^   // Atomically restore CPSR, registers and caller PC.
