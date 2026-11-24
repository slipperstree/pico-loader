OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(rtsM2Entry)
SECTIONS {
 .menu 0x06898000 : {
  KEEP(*menu-state.o(.text* .rodata* .data* .bss*))
  KEEP(*menu-render.o(.text* .rodata* .data* .bss*))
  KEEP(*menu-runtime.o(.text* .rodata* .data* .bss.restoreBuffer .bss.gRtsMenuBoot))
  KEEP(*libgcc.a:*(.text* .rodata* .data* .bss*))
 }
 . = 0x02200000;
 __image_start = .;
 .text : { KEEP(*(.text.entry)) KEEP(*(.text.arm7capture)) KEEP(*(.text.p4Arm7Entry)) KEEP(*(.text.rtsArm9RestoreTail)) *(.text*) }
 .rodata : { *(.rodata*) }
 .data ALIGN(4) : { KEEP(*(.data.p4Pointers)) *(.data*) }
 . = ALIGN(4);
 __file_end = .;
 .bss (NOLOAD) : { *(SORT_BY_ALIGNMENT(.bss*)) *(COMMON) }
 . = ALIGN(512);
 __image_end = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
