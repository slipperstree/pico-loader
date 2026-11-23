.cpu arm946e-s
.syntax unified
.section .text.entry,"ax"
.arm
.global rtsM2Entry
.type rtsM2Entry,%function
rtsM2Entry:
    stmdb sp!,{r0-r12,lr}
    mov r0,sp
    mov r4,sp
    ldr sp,=gRtsM2Stack+1024
    stmdb sp!,{r4,lr}
    bl rtsM2Run
    ldmia sp!,{r4,lr}
    mov sp,r4
    ldmia sp!,{r0-r12,lr}
    bx lr
