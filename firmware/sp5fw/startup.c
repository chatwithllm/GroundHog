/* Minimal Cortex-M3 startup for GD32F103CB.
 * Vector table at 0x08000000 (flashed there; VTOR default). */

#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
int main(void);

void Reset_Handler(void)
{
    /* copy .data from flash (LMA) to RAM */
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) *dst++ = *src++;
    /* zero .bss */
    for (dst = &_sbss; dst < &_ebss; ) *dst++ = 0;
    main();
    for (;;) { }
}

void Default_Handler(void)
{
    /* Fail quiet even if a bad live register poke causes a bus/hard fault. */
    volatile uint32_t * const tim_ccer = (uint32_t *)0x40012C20u;
    volatile uint32_t * const tim_ccr1 = (uint32_t *)0x40012C34u;
    volatile uint32_t * const tim_ccr2 = (uint32_t *)0x40012C38u;
    volatile uint32_t * const tim_ccr3 = (uint32_t *)0x40012C3Cu;
    volatile uint32_t * const tim_bdtr = (uint32_t *)0x40012C44u;
    *tim_ccr1=0; *tim_ccr2=0; *tim_ccr3=0; *tim_ccer=0; *tim_bdtr=0;
    for (;;) { }
}

/* Weak aliases for the core exceptions -> Default_Handler unless overridden. */
void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));

/* Minimal vector table: 16 core vectors is enough for a polling firmware. */
__attribute__((section(".isr_vector"), used))
void (* const g_vectors[])(void) = {
    (void (*)(void))(&_estack),  /* 0x00 initial SP */
    Reset_Handler,               /* 0x04 reset */
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,                  /* reserved */
    SVC_Handler,
    DebugMon_Handler,
    0,                           /* reserved */
    PendSV_Handler,
    SysTick_Handler,
};
