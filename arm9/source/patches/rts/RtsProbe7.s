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
    tst r1, r2
    bne rts7_rearm
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
    adr r0, rts7_fired
    mov r1, #1
    str r1, [r0]
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
    b rts7_done
rts7_rearm:
    adr r0, rts7_hold_count
    mov r1, #0
    str r1, [r0]
    adr r0, rts7_fired
    str r1, [r0]
    b rts7_done
rts7_park:
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
    ldr r0, rts7_ipc
    bic r10, r1, #0xf00
    orr r3, r10, #0xc00
    strh r3, [r0]
    ldr r0, rts7_vcount
    ldrh r6, [r0]
    ldr r7, rts7_frames
    ldr r5, rts7_spin_budget
rts7_frame_loop:
    ldrh r3, [r0]
    cmp r3, r6
    mov r6, r3
    sublo r7, r7, #1        // Physical scanline wrap, independent of game timers.
    cmp r7, #0
    beq rts7_release
    ldr r1, rts7_ipc
    ldrh r2, [r1]
    and r2, r2, #15
    cmp r2, #10
    bne rts7_release
    subs r5, r5, #1
    bne rts7_frame_loop
rts7_release:
    ldr r0, rts7_ipc
    strh r10, [r0]
    ldr r5, rts7_spin_budget
rts7_wait_release:
    ldrh r1, [r0]
    and r1, r1, #15
    cmp r1, #10
    bne rts7_restore
    subs r5, r5, #1
    bne rts7_wait_release
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
rts7_hotkey: .word 0x384
rts7_nibble_mask: .word 0xf0f
rts7_hold_count: .word 0
rts7_fired: .word 0
rts7_pending: .word 0
rts7_frames: .word 180
rts7_spin_budget: .word 0x04000000
#endif
