// Altered research version of Pico Loader; not an LNH-team release.
// Reversible CPU rendezvous. No RAM/VRAM remapping and no storage accesses.
#ifdef PICO_RTS_PROBE
.cpu arm946e-s
.syntax unified
.arm

.section patch_rts9_gate, "ax"
.global rts9_gate, rts9_enabled, rts9_guard_address, rts9_return
rts9_gate:
    stmdb sp!, {r0-r3, r12, lr}
    mrs r2, cpsr
    stmdb sp!, {r2, r3}
    ldr r0, rts9_enabled
    cmp r0, #0
    beq rts9_return
    and r3, r2, #0x1f
    cmp r3, #0x1f             // Never park an IRQ, SVC, FIQ or abort handler.
    bne rts9_return
    tst r2, #0x80             // A critical section is not a safe rendezvous.
    bne rts9_return
    ldr pc, rts9_guard_address
rts9_return:
    ldmia sp!, {r2, r3}
    msr cpsr_cxsf, r2
    ldmia sp!, {r0-r3, r12, lr}
    bx lr
rts9_enabled: .word 0
rts9_guard_address: .word 0

.section patch_rts9_guard, "ax"
.global rts9_guard, rts9_guard_return, rts9_park_address
rts9_guard:
    ldr r0, 1f
    ldrh r1, [r0]
    and r3, r1, #0xf00
    cmp r3, #0
    bne 3f
    and r3, r1, #15
    cmp r3, #11
    bne 3f
    ldr r0, 2f
    ldr r1, [r0]
    tst r1, #0x80000000       // Do not park in a cartridge transfer.
    bne 3f
    ldr pc, rts9_park_address
3:  ldr pc, rts9_guard_return
1:  .word 0x04000180
2:  .word 0x040001a4
rts9_guard_return: .word 0
rts9_park_address: .word 0

.section patch_rts9_park, "ax"
.global rts9_park, rts9_park_return, rts9_dim_address, rts9_resume_address
.global rts9_ready_budget
rts9_park:
    ldr r0, 1f
    ldr r1, [r0]
    cmp r1, #1
    ldrne pc, rts9_park_return
    mov r3, #0
    str r3, [r0]
    orr r3, r2, #0xc0
    msr cpsr_c, r3
    ldr r0, 2f
    ldrh r1, [r0]
    stmdb sp!, {r1, r3}       // Original outgoing nibble/control bits.
    orr r1, r1, #0xa00
    strh r1, [r0]            // ACK: ARM9 parked, not yet both CPUs.
    ldr r12, rts9_ready_budget
3:  ldrh r1, [r0]
    and r1, r1, #15
    cmp r1, #12
    ldreq pc, rts9_dim_address
    cmp r1, #11
    ldrne pc, rts9_resume_address
    subs r12, r12, #1
    bne 3b
    ldr pc, rts9_resume_address
1:  .word 0x04000208
2:  .word 0x04000180
rts9_park_return: .word 0
rts9_dim_address: .word 0
rts9_resume_address: .word 0
rts9_ready_budget: .word 0x04000000

.section patch_rts9_dim, "ax"
.global rts9_dim, rts9_dim_resume, rts9_hold_budget
rts9_dim:
    ldr r0, 1f
    ldrh r1, [r0]
    ldr r2, 2f
    ldrh r3, [r2]
    stmdb sp!, {r1, r3}
    mov r1, #0x8000
    orr r1, r1, #8
    strh r1, [r0]
    strh r1, [r2]            // Dim only after ARM7 also reports parked.
    ldr r0, 3f
    ldr r12, rts9_hold_budget
4:  ldrh r1, [r0]
    and r1, r1, #15
    cmp r1, #12
    bne 5f
    subs r12, r12, #1
    bne 4b
5:  ldmia sp!, {r1, r3}
    ldr r0, 1f
    strh r1, [r0]
    ldr r0, 2f
    strh r3, [r0]
    ldr pc, rts9_dim_resume
1:  .word 0x0400006c
2:  .word 0x0400106c
3:  .word 0x04000180
rts9_dim_resume: .word 0
rts9_hold_budget: .word 0x04000000

.section patch_rts9_resume, "ax"
.global rts9_resume, rts9_resume_return
rts9_resume:
    ldmia sp!, {r0, r1}
    ldr r1, 1f
    strh r0, [r1]            // Restore our nibble; preserve IRQ control bits.
    ldr r0, 2f
    mov r1, #1
    str r1, [r0]             // CPU IRQs remain masked until original CPSR returns.
    ldr pc, rts9_resume_return
1:  .word 0x04000180
2:  .word 0x04000208
rts9_resume_return: .word 0
#endif
