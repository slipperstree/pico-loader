// Original ARM7TDMI helpers. No BIOS calls, stack writes or private-WRAM writes.
.cpu arm7tdmi
.syntax unified
.arm
.section .text.arm7capture,"ax"
.global rtsArm7CaptureContext, rtsArm7CaptureService
// r0=mailbox, r1=parked SP, r2=original CPSR, r3=original IME.
// Preserves r4-r11 (including their current-mode banks), SP and return LR.
.type rtsArm7CaptureContext,%function
rtsArm7CaptureContext:
    add r0,r0,#544
    str lr,[r0,#24]             // Temporary helper return; cleared before publish.
    str r1,[r0,#8]
    str r2,[r0,#12]
    str r3,[r0,#16]
    mov r3,#0
    str r3,[r0]
    mov r3,#1
    str r3,[r0,#4]
    and r3,r2,#31
    cmp r3,#31
    cmpne r3,#18
    bne capture_bad_mode
    mov r3,#0
copy_frame:
    ldr r2,[r1,r3]
    add r12,r0,#32
    str r2,[r12,r3]
    add r3,r3,#4
    cmp r3,#48
    blo copy_frame
    ldr r1,=0x04000241
    ldrb r1,[r1]
    and r1,r1,#3
    str r1,[r0,#20]
    mrs r1,cpsr
    str r1,[r0,#28]             // Masked helper CPSR for restoring original mode.
    bic r1,r1,#31
    orr r1,r1,#192
    orr r2,r1,#31
    msr cpsr_c,r2
    str sp,[r0,#80]
    str lr,[r0,#84]
    mov r3,#0
    str r3,[r0,#88]
    orr r2,r1,#18
    msr cpsr_c,r2
    str sp,[r0,#92]
    str lr,[r0,#96]
    mrs r3,spsr
    str r3,[r0,#100]
    orr r2,r1,#19
    msr cpsr_c,r2
    str sp,[r0,#104]
    str lr,[r0,#108]
    mrs r3,spsr
    str r3,[r0,#112]
    orr r2,r1,#23
    msr cpsr_c,r2
    str sp,[r0,#116]
    str lr,[r0,#120]
    mrs r3,spsr
    str r3,[r0,#124]
    orr r2,r1,#27
    msr cpsr_c,r2
    str sp,[r0,#128]
    str lr,[r0,#132]
    mrs r3,spsr
    str r3,[r0,#136]
    orr r2,r1,#17
    msr cpsr_c,r2
    str sp,[r0,#140]
    str lr,[r0,#144]
    mrs r3,spsr
    str r3,[r0,#148]
    add r2,r0,#152
    stmia r2,{r8-r12}
    ldr r1,[r0,#28]
    msr cpsr_cxsf,r1
    // Calling the helper replaced the current bank's LR. Record pre-call LR
    // from the parked game frame, not our instrumentation return address.
    ldr r2,[r0,#12]
    and r2,r2,#31
    cmp r2,#31
    moveq r3,#84
    movne r3,#96
    ldr r2,[r0,#76]
    str r2,[r0,r3]
    ldr lr,[r0,#24]
    mov r3,#0
    str r3,[r0,#24]
    str r3,[r0,#28]
    ldr r1,=0x31433741
    str r1,[r0]                // Publish complete context last.
    ldr r1,[r0,#20]
    cmp r1,#3                 // First target: all shared WRAM assigned to ARM7.
    movne r3,#2
    sub r0,r0,#544
    str r3,[r0,#12]
    bx lr
capture_bad_mode:
    ldr lr,[r0,#24]
    mov r3,#0
    str r3,[r0,#24]
    sub r0,r0,#544
    mov r3,#3
    str r3,[r0,#12]
    bx lr

// r0=mailbox, caller parks on its original stack but this helper never uses it.
.type rtsArm7CaptureService,%function
rtsArm7CaptureService:
    ldr r1,[r0]
    cmp r1,#1
    bxne lr
    ldr r1,[r0,#4]
    ldr r2,[r0,#8]
    cmp r1,r2
    bxeq lr
    ldr r2,[r0,#16]
    cmp r2,#192
    bhs service_bad_block
    cmp r2,#128
    blo service_private
    ldr r3,=0x04000241
    ldrb r3,[r3]
    and r3,r3,#3
    cmp r3,#3
    bne service_bad_wram
    sub r2,r2,#128
    mov r3,#0x03000000
    b service_copy
service_private:
    mov r3,#0x03800000
service_copy:
    add r2,r3,r2,lsl #9
    add r3,r0,#32
    add r12,r3,#512
1:  ldr r1,[r2],#4
    str r1,[r3],#4
    cmp r3,r12
    blo 1b
    mov r3,#0
    b service_publish
service_bad_block:
    mov r3,#1
    b service_publish
service_bad_wram:
    mov r3,#2
service_publish:
    str r3,[r0,#12]
    ldr r1,[r0,#4]
    str r1,[r0,#8]             // Completion after data/status. ARM7 has no cache.
    bx lr
.ltorg
