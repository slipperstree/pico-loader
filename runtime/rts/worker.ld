OUTPUT_FORMAT("elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(rtsM2Entry)
SECTIONS {
 . = 0x02200000;
 __image_start = .;
 .text : { KEEP(*(.text.entry)) KEEP(*(.text.arm7capture)) *(.text*) }
 .rodata : { *(.rodata*) }
 .data : { *(.data*) }
 . = ALIGN(4);
 __file_end = .;
 .bss (NOLOAD) : { *(.bss*) *(COMMON) }
 . = ALIGN(512);
 __image_end = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
