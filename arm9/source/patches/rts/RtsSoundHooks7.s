// Original ARM7 SDK observation stubs. Optional and not installed yet.
#ifdef PICO_RTS_AUDIO_SHADOW
.cpu arm7tdmi
.syntax unified
.arm
.section patch_rtsSoundPcm,"ax"
.global rtsSoundPcmHook,rtsSoundPcmBusy,rtsSoundPcmObserve,rtsSoundPcmResume
rtsSoundPcmHook:
    stmdb sp!,{r0-r3,r12,lr}
    mrs r3,cpsr
    stmdb sp!,{r3,r12}         // Keep 8-byte alignment at the C helper call.
    orr r12,r3,#128
    msr cpsr_c,r12
    ldr r12,rtsSoundPcmBusy
    ldr r2,[r12]
    add r2,r2,#1
    str r2,[r12]
    msr cpsr_cxsf,r3
    add r0,sp,#8
    add r1,sp,#32
    ldr r12,rtsSoundPcmObserve
    mov lr,pc
    bx r12
    ldmia sp!,{r3,r12}
    msr cpsr_cxsf,r3
    ldmia sp!,{r0-r3,r12,lr}
    stmdb sp!,{r4-r8,lr}
    mov r8,r1
    ldr pc,rtsSoundPcmResume
rtsSoundPcmBusy: .word 0
rtsSoundPcmObserve: .word 0
rtsSoundPcmResume: .word 0
.section patch_rtsSoundTimer,"ax"
.global rtsSoundTimerHook,rtsSoundTimerBusy,rtsSoundTimerObserve,rtsSoundTimerResume
rtsSoundTimerHook:
    stmdb sp!,{r0-r3,r12,lr}
    mrs r3,cpsr
    stmdb sp!,{r3,r12}         // Keep 8-byte alignment at the C helper call.
    orr r12,r3,#128
    msr cpsr_c,r12
    ldr r12,rtsSoundTimerBusy
    ldr r2,[r12]
    add r2,r2,#1
    str r2,[r12]
    msr cpsr_cxsf,r3
    add r0,sp,#8
    ldr r12,rtsSoundTimerObserve
    mov lr,pc
    bx r12
    ldmia sp!,{r3,r12}
    msr cpsr_cxsf,r3
    ldmia sp!,{r0-r3,r12,lr}
    rsb r1,r1,#0x10000
    lsl r0,r0,#4
    ldr pc,rtsSoundTimerResume
rtsSoundTimerBusy: .word 0
rtsSoundTimerObserve: .word 0
rtsSoundTimerResume: .word 0
.section patch_rtsSoundExit,"ax"
.global rtsSoundExitHook,rtsSoundExitBusy
rtsSoundExitHook:
    stmdb sp!,{r0-r3,r12,lr}
    mrs r3,cpsr
    stmdb sp!,{r3,r12}
    orr r12,r3,#128
    msr cpsr_c,r12
    ldr r12,rtsSoundExitBusy
    ldr r1,[r12]
    subs r1,r1,#1
    movcc r1,#0
    str r1,[r12]
    ldmia sp!,{r3,r12}
    msr cpsr_cxsf,r3
    ldmia sp!,{r0-r3,r12,lr}
    bx lr
rtsSoundExitBusy: .word 0
#endif
