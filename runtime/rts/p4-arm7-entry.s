.cpu arm7tdmi
.syntax unified
.arm
.macro entry_trace number
.ifdef RTS_TRACE_CPU
    ldr r12,=0x04000180
    ldrh r5,[r12]
    bic r5,r5,#0xf00
    orr r5,r5,#(\number<<8)
    strh r5,[r12]
.endif
.endm
.section .text.p4Arm7Entry,"ax"
.global rtsP4Arm7Entry
.type rtsP4Arm7Entry,%function
rtsP4Arm7Entry:
    stmdb sp!,{r0-r12,lr}
    entry_trace 2
    mov r4,sp
    ldr sp,=gRtsP4Arm7Stack+384
    stmdb sp!,{r4,lr}
    entry_trace 3
    // r4 points at the original private saved arguments. Capture on the
    // independent IRQ stack; the record keeps the original game-frame SP.
    ldr r1,[r4,#4]
    ldr r2,[r4,#8]
    ldr r3,[r4,#12]
    ldr r0,=gRtsArm7Mailbox
    entry_trace 4
    bl rtsArm7CaptureContext
    entry_trace 8
    ldr r0,[r4]
    ldr r1,[r4,#16]
    ldr r3,=rtsP4Arm7Loop
    mov lr,pc
    bx r3
    ldmia sp!,{r4,lr}
    mov sp,r4
    ldmia sp!,{r0-r12,lr}
    bx lr
.ltorg
.section .data.p4Pointers,"aw"
.global gRtsP4Pointers
gRtsP4Pointers:
.ifdef RTS_GENERIC_SOUND
    .word rtsP4Arm7Entry,rtsP4Arm7Begin,rtsSoundObserveStore,0
.else
    .word rtsP4Arm7Entry,rtsP4Arm7Begin,rtsSoundObservePcm,rtsSoundObserveTimer
.endif
    .word gRtsSoundBusy,gRtsSoundShadow,gRtsP4,gRtsP4Identity
    .word rtsArm9RestoreTail,gRtsP4TailAddress,gRtsP4SavedSequence,gRtsP4LoadVerify
    .word gRtsP4Scratch
.ifdef RTS_GENERIC_SOUND
    .word 0,gRtsP4Arm7TailAddress
.else
    .word rtsSoundObserveReload,gRtsP4Arm7TailAddress
.endif
