.cpu arm7tdmi
.syntax unified
.arm
.section .text.p4Arm7Entry,"ax"
.global rtsP4Arm7Entry
.type rtsP4Arm7Entry,%function
rtsP4Arm7Entry:
    stmdb sp!,{r0-r12,lr}
    mov r4,sp
    ldr sp,=gRtsP4Arm7Stack+384
    stmdb sp!,{r4,lr}
    // r4 points at the original private saved arguments. Capture on the
    // independent IRQ stack; the record keeps the original game-frame SP.
    ldr r1,[r4,#4]
    ldr r2,[r4,#8]
    ldr r3,[r4,#12]
    ldr r0,=gRtsArm7Mailbox
    bl rtsArm7CaptureContext
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
    .word rtsP4Arm7Entry,rtsP4Arm7Begin,rtsSoundObservePcm,rtsSoundObserveTimer
    .word gRtsSoundBusy,gRtsSoundShadow,gRtsP4,gRtsP4Identity
    .word rtsArm9RestoreTail,gRtsP4TailAddress,gRtsP4SavedSequence,gRtsP4FreshSlot
    .word gRtsP4Scratch
