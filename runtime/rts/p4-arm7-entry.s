.cpu arm7tdmi
.syntax unified
.arm
.section .text.p4Arm7Entry,"ax"
.global rtsP4Arm7Entry
rtsP4Arm7Entry:
    stmdb sp!,{r0-r12,lr}
    mov r4,sp
    ldr sp,=gRtsP4Arm7Stack+512
    stmdb sp!,{r4,lr}
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
