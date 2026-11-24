// Altered research version. VBlank epilogue ABI follows Pico Loader's cheat hook.
// B (request) -> A (ARM9 ACK) -> C (both parked) -> 0 (release).
#ifdef PICO_RTS_PROBE
.cpu arm7tdmi
.syntax unified
.section patch_rts7, "ax"
.arm
.global rts7_arm, rts7_thumb, rts7_hold_count, rts7_fired, rts7_pending
.global rts7_frames, rts7_spin_budget
rts7_arm:
    ldmia sp!, {r0, r1}
    mov lr, r1
    b rts7_body
.thumb
.thumb_func
rts7_thumb:
    pop {r0, r1}
    mov lr, r1
    bx pc
    nop
.arm
rts7_body:
    stmdb sp!, {r2-r12, lr}
    adr r4, rts7_pending
    ldr r3, [r4]
    cmp r3, #0
    beq rts7_keys
    ldr r0, rts7_ipc
    ldrh r1, [r0]
    and r2, r1, #0xf00
    cmp r2, #0xb00
    bne rts7_cancel_state
    and r2, r1, #15
    cmp r2, #10
    beq rts7_park
    add r3, r3, #1
    str r3, [r4]
    cmp r3, #60              // Withdraw an unanswered request after 60 VBlanks.
    blo rts7_done
    bic r1, r1, #0xf00
    strh r1, [r0]
rts7_cancel_state:
    mov r3, #0
    str r3, [r4]
    b rts7_done
rts7_keys:
    ldr r0, rts7_keyinput
    ldrh r1, [r0]
    ldr r2, rts7_hotkey
#ifdef PICO_RTS_RESTORE_PROBE
    tst r1,r2
    moveq r3,#0
    beq 80f
    add r2,r2,#1
    tst r1,r2
    bne rts7_rearm
    mov r3,#1
80: adr r0,rts7_operation
    str r3,[r0]
#else
    tst r1, r2
    bne rts7_rearm
#endif
    adr r0, rts7_fired
    ldr r1, [r0]
    cmp r1, #0
    bne rts7_done
    adr r0, rts7_hold_count
    ldr r1, [r0]
    add r1, r1, #1
    str r1, [r0]
    cmp r1, #30
    blo rts7_done
    ldr r0, rts7_card
    ldr r1, [r0]
    tst r1, #0x80000000
    bne rts7_done
    ldr r0, rts7_ipc
    ldrh r1, [r0]
    ldr r2, rts7_nibble_mask
    tst r1, r2              // Never replace non-idle game IPCSYNC nibbles.
    bne rts7_done
    orr r1, r1, #0xb00
    strh r1, [r0]
    adr r0, rts7_pending
    mov r1, #1
    str r1, [r0]
    adr r0, rts7_fired
    str r1, [r0]
    b rts7_done
rts7_rearm:
    adr r0, rts7_hold_count
    mov r1, #0
    str r1, [r0]
    adr r0, rts7_fired
    str r1, [r0]
    b rts7_done
rts7_park:
#ifdef PICO_RTS_SNAPSHOT
    ldr r0,rts7_diagnostic_address
    mov r2,#0
    str r2,[r0]
    ldr r0,rts7_read_busy_address
    ldr r2,[r0]
    ldr r0,rts7_write_busy_address
    ldr r3,[r0]
    orrs r2,r2,r3
    movne r2,#4096
    bne rts7_m2_report_refusal
    // Check the owning CPU's card registers, not ARM9's inactive interface.
    ldr r0,rts7_exmem
    ldrh r2,[r0]
    tst r2,#0x800
    beq rts7_m2_dma_check
    ldr r0,rts7_card
    ldr r2,[r0]
    tst r2,#0x80000000
    movne r2,#4
    bne rts7_m2_report_refusal
    ldr r0,rts7_spi
    ldrh r2,[r0]
    tst r2,#0x80
    movne r2,#8
    bne rts7_m2_report_refusal
rts7_m2_dma_check:
    // Reject DMA and sound capture before granting a memory snapshot.
    ldr r0, rts7_dma_control
    mov r3, #4
91: ldr r2, [r0], #12
    tst r2, #0x80000000
    bne rts7_m2_dma_refusal
    subs r3, r3, #1
    bne 91b
    ldr r0, rts7_capture_control
    ldrh r2, [r0]
    ldr r3, rts7_capture_mask
    tst r2, r3
    bne rts7_m2_capture_refusal
    b rts7_m2_guard_done
rts7_m2_dma_refusal:
    mov r2,#512
    b rts7_m2_report_refusal
rts7_m2_capture_refusal:
    mov r2,#1024
rts7_m2_report_refusal:
    ldr r0,rts7_diagnostic_address
    str r2,[r0]
rts7_m2_guard_done:
#endif
    // ARM9 is parked. Do not call BIOS/SDK/file I/O from this critical section.
    mov r3, #0
    str r3, [r4]
    mrs r8, cpsr
    orr r3, r8, #0xc0
    msr cpsr_c, r3
    ldr r0, rts7_ime
    ldr r9, [r0]
    mov r3, #0
    str r3, [r0]
    bic r10, r1, #0xf00
#if defined(PICO_RTS_ARM7_CAPTURE) && !defined(PICO_RTS_RESTORE_PROBE)
    mov r1,sp
    mov r2,r8
    mov r3,r9
    ldr r0,rts7_mailbox_address
    ldr r12,rts7_capture_address
    mov lr,pc
    bx r12
    ldr r2,[r0,#12]
    cmp r2,#0
    movne r2,#8192
    ldrne r0,rts7_diagnostic_address
    strne r2,[r0]
#endif
    ldr r0, rts7_ipc
    orr r3, r10, #0xc00
    strh r3, [r0]
    ldr r0, rts7_vcount
    ldrh r6, [r0]
#ifdef PICO_RTS_SNAPSHOT
    mov r7,#0
    ldr r1,rts7_clock_address
    str r7,[r1]
#else
    ldr r7, rts7_frames
#endif
#ifdef PICO_RTS_RESTORE_PROBE
    // Publish C before touching any new P4 state/capture code. ARM9 will
    // explicitly send 8 only AFTER its display feedback and cache transition.
    ldr r5,rts7_spin_budget
    ldr r0,rts7_ipc
82: ldrh r1,[r0]
    and r1,r1,#15
    cmp r1,#8
    beq 83f
    cmp r1,#13
    beq rts7_release
    cmp r1,#14
    beq rts7_m2_fault
    cmp r1,r6
    ldrne r5,rts7_spin_budget
    mov r6,r1
    subs r5,r5,#1
    bne 82b
    b rts7_m2_fault
83:
#ifdef PICO_RTS_CPU_TRACE
    ldr r0,rts7_ipc
    ldrh r1,[r0]
    bic r1,r1,#0xf00
    orr r1,r1,#0x100
    strh r1,[r0] // checkpoint 1: received explicit start 8
#endif
    mov r0,r10
    mov r1,sp
    mov r2,r8
    mov r3,r9
    ldr r4,rts7_operation
    ldr r12,rts7_loop_address
    mov lr,pc
    bx r12
    b rts7_release
#else
    ldr r5, rts7_spin_budget
#ifdef PICO_RTS_SNAPSHOT
    mov r11, #10
#endif
rts7_frame_loop:
#ifdef PICO_RTS_ARM7_CAPTURE
    ldr r0,rts7_mailbox_address
    ldr r12,rts7_service_address
    mov lr,pc
    bx r12
    ldr r0,rts7_vcount
#endif
    ldrh r3, [r0]
    cmp r3, r6
    mov r6, r3
#ifdef PICO_RTS_SNAPSHOT
    addlo r7,r7,#1
    ldrlo r1,rts7_clock_address
    strlo r7,[r1]           // Read-only, separately aligned counter for ARM9.
#else
    sublo r7, r7, #1        // Physical scanline wrap, independent of game timers.
#endif
#ifndef PICO_RTS_SNAPSHOT
    cmp r7, #0
    beq rts7_release
#endif
    ldr r1, rts7_ipc
    ldrh r2, [r1]
    and r2, r2, #15
#ifdef PICO_RTS_SNAPSHOT
    cmp r2, #14
    beq rts7_m2_fault
    cmp r2, #10
    beq 92f
    cmp r2, #9
    bne rts7_release
92: cmp r2, r11
    ldrne r5, rts7_spin_budget
    mov r11, r2
#else
    cmp r2, #10
    bne rts7_release
#endif
    subs r5, r5, #1
    bne rts7_frame_loop
#ifdef PICO_RTS_SNAPSHOT
    // No heartbeat while card I/O may be active: fail closed, do not resume.
    b rts7_m2_fault
#endif
#endif // !PICO_RTS_RESTORE_PROBE
rts7_release:
    ldr r0, rts7_ipc
    strh r10, [r0]
    ldr r5, rts7_spin_budget
rts7_wait_release:
    ldrh r1, [r0]
    and r1, r1, #15
    cmp r1, #10
#ifdef PICO_RTS_CPU_TRACE
    beq 94f
    cmp r1,#13
94:
#endif
    bne rts7_restore
    subs r5, r5, #1
    bne rts7_wait_release
#ifdef PICO_RTS_CPU_TRACE
    b rts7_m2_fault // Never run game code while ARM9 still owns the handoff.
#else
    b rts7_restore
#endif
#ifdef PICO_RTS_SNAPSHOT
rts7_m2_decline:
    ldr r0,rts7_ipc
    ldrh r1,[r0]
    bic r1,r1,#0xf00
    strh r1,[r0]
    b rts7_cancel_state
rts7_m2_fault:
    b rts7_m2_fault
#endif
rts7_restore:
    ldr r0, rts7_ime
    str r9, [r0]
    msr cpsr_cxsf, r8
rts7_done:
    ldmia sp!, {r2-r12, lr}
    bx lr
.balign 4
rts7_keyinput: .word 0x04000130
rts7_ipc: .word 0x04000180
rts7_card: .word 0x040001a4
rts7_ime: .word 0x04000208
rts7_vcount: .word 0x04000006
rts7_hotkey: .word 0x381
rts7_nibble_mask: .word 0xf0f
rts7_hold_count: .word 0
rts7_fired: .word 0
rts7_pending: .word 0
#ifdef PICO_RTS_RESTORE_PROBE
rts7_operation: .word 0
#endif
rts7_frames: .word 180
rts7_spin_budget: .word 0x04000000
#ifdef PICO_RTS_SNAPSHOT
rts7_dma_control: .word 0x040000b8
rts7_capture_control: .word 0x04000508
rts7_capture_mask: .word 0x00008080
.global rts7_diagnostic_address
rts7_diagnostic_address: .word 0
.global rts7_read_busy_address, rts7_write_busy_address
rts7_read_busy_address: .word 0
rts7_write_busy_address: .word 0
rts7_exmem: .word 0x04000204
rts7_spi: .word 0x040001a0
.global rts7_clock_address
rts7_clock_address: .word 0
#ifdef PICO_RTS_ARM7_CAPTURE
.global rts7_mailbox_address, rts7_capture_address, rts7_service_address
rts7_mailbox_address: .word 0
rts7_capture_address: .word 0
rts7_service_address: .word 0
#ifdef PICO_RTS_RESTORE_PROBE
.global rts7_operation_address,rts7_begin_address,rts7_loop_address
rts7_operation_address: .word 0
rts7_begin_address: .word 0
rts7_loop_address: .word 0
#endif
#endif
#endif
#endif
