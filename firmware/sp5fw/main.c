/* SP5-MAIN interactive "poke" firmware — motor/H-bridge mapping bench tool.
 * Target: GD32F103CB (STM32F103-compatible), Cortex-M3.
 * Clock: HSE 8 MHz (crystal Y1) -> PLL x9 = 72 MHz  (exact 115200 baud).
 *
 * Control over USART2 / CON1 (PA2 TX, PA3 RX), 115200 8N1, line-based ASCII:
 *   p <ch> <pct>      PWM channel ch=1..3 (PA8/PA9/PA10), duty capped at 15%
 *   o <P><pin> <v>    drive GPIO as push-pull output: e.g. "o A11 1", "o B3 0"
 *   i <P><pin>        set GPIO as input, print its level (for Hall/limit reads)
 *   s                 STOP: all PWM duty = 0
 *   ?                 print current PWM state
 * P = A or B, pin = 0..15.  Unknown/garbage lines are ignored with "err".
 *
 * SAFETY: at boot all PWM = 0 (motors off). Driving motors moves wheels —
 * only with chassis off the ground.
 */

#include <stdint.h>
#include "smbus.h"

#define REG(a) (*(volatile uint32_t *)(a))

/* RCC */
#define RCC_BASE     0x40021000u
#define RCC_CR       REG(RCC_BASE+0x00)
#define RCC_CFGR     REG(RCC_BASE+0x04)
#define RCC_APB2ENR  REG(RCC_BASE+0x18)
#define RCC_APB1ENR  REG(RCC_BASE+0x1C)
#define FLASH_ACR    REG(0x40022000u)
#define AFIO_MAPR    REG(0x40010004u)

/* GPIO */
#define GPIOA 0x40010800u
#define GPIOB 0x40010C00u
#define GPIO_CRL(b)  REG((b)+0x00)
#define GPIO_CRH(b)  REG((b)+0x04)
#define GPIO_IDR(b)  REG((b)+0x08)
#define GPIO_BSRR(b) REG((b)+0x10)
#define GPIO_BRR(b)  REG((b)+0x14)

/* USART2 (APB1 = 36 MHz) */
#define USART2 0x40004400u
#define USART_SR(u)  REG((u)+0x00)
#define USART_DR(u)  REG((u)+0x04)
#define USART_BRR(u) REG((u)+0x08)
#define USART_CR1(u) REG((u)+0x0C)
#define SR_TXE (1u<<7)
#define SR_RXNE (1u<<5)

/* TIM1 (APB2 = 72 MHz) */
#define TIM1 0x40012C00u
#define TIM_CR1(t)   REG((t)+0x00)
#define TIM_CR2(t)   REG((t)+0x04)
#define TIM_SMCR(t)  REG((t)+0x08)
#define TIM_DIER(t)  REG((t)+0x0C)
#define TIM_SR(t)    REG((t)+0x10)
#define TIM_EGR(t)   REG((t)+0x14)
#define TIM_CCMR1(t) REG((t)+0x18)
#define TIM_CCMR2(t) REG((t)+0x1C)
#define TIM_CCER(t)  REG((t)+0x20)
#define TIM_PSC(t)   REG((t)+0x28)
#define TIM_ARR(t)   REG((t)+0x2C)
#define TIM_RCR(t)   REG((t)+0x30)
#define TIM_CCR1(t)  REG((t)+0x34)
#define TIM_CCR2(t)  REG((t)+0x38)
#define TIM_CCR3(t)  REG((t)+0x3C)
#define TIM_BDTR(t)  REG((t)+0x44)
#define TIM_CNT(t)   REG((t)+0x24)
#define TIM2 0x40000000u   /* free-running 1 kHz timebase for uptime/keepalive */

#define PWM_ARR      3600u   /* 72MHz/3600 = 20 kHz; CCR = pct*36 */
#define PWM_SAFE_MAX 15      /* bench rule: normal commands never exceed 15% */

/* ADC1 (APB2) — shunt/battery sense */
#define ADC1 0x40012400u
#define ADC_SR(a)    REG((a)+0x00)
#define ADC_CR2(a)   REG((a)+0x08)
#define ADC_SMPR2(a) REG((a)+0x10)
#define ADC_SQR1(a)  REG((a)+0x2C)
#define ADC_SQR3(a)  REG((a)+0x34)
#define ADC_DR(a)    REG((a)+0x4C)

static void putc_(char c){ while(!(USART_SR(USART2)&SR_TXE)){} USART_DR(USART2)=(uint8_t)c; }
static void puts_(const char*s){ while(*s) putc_(*s++); }
static void putu_(uint32_t v){ char b[11]; int i=10; b[i--]=0; if(!v){putc_('0');return;} while(v&&i>=0){b[i--]='0'+v%10; v/=10;} puts_(&b[i+1]); }
static void puth_(uint32_t v,int digits){ const char*H="0123456789ABCDEF"; for(int i=digits-1;i>=0;i--) putc_(H[(v>>(i*4))&0xFu]); }
static void puti_(int32_t v){ if(v<0){ putc_('-'); v=-v; } putu_((uint32_t)v); }
static int streq(const char*a,const char*b){ while(*a&&*b){ if(*a!=*b)return 0; a++;b++; } return *a==*b; }
/* accepts decimal or 0x-prefixed hex */
static int parse_num(const char*t,uint32_t*out){
    uint32_t v=0; int i=0,any=0;
    if(t[0]=='0'&&(t[1]=='x'||t[1]=='X')){
        for(i=2;t[i];i++){ char c=t[i]; uint32_t d;
            if(c>='0'&&c<='9')d=(uint32_t)(c-'0');
            else if(c>='a'&&c<='f')d=(uint32_t)(c-'a'+10);
            else if(c>='A'&&c<='F')d=(uint32_t)(c-'A'+10);
            else return 0;
            if(v>(0xFFFFFFFFu-d)/16u)return 0;
            v=v*16u+d; any=1; }
    } else {
        for(i=0;t[i];i++){ char c=t[i]; uint32_t d;
            if(c<'0'||c>'9')return 0;
            d=(uint32_t)(c-'0');
            if(v>(0xFFFFFFFFu-d)/10u)return 0;
            v=v*10u+d; any=1; }
    }
    if(!any)return 0;
    *out=v;
    return 1;
}
static const char* smberr(int r){ return r==SMB_OK?"ok":(r==SMB_ENAK?"NAK":(r==SMB_ETMO?"TMO":"LEN")); }

static void clock_init(void)
{
    RCC_CR |= (1u<<16);                 /* HSEON */
    while(!(RCC_CR & (1u<<17))){}       /* HSERDY */
    FLASH_ACR = (1u<<4) | 0x2u;         /* prefetch + 2 wait states */
    /* CFGR: PLLSRC=HSE, PLLMUL=x9 (0111<<18), PPRE1=/2 (100<<8) */
    RCC_CFGR = (0u<<17) | (1u<<16) | (0x7u<<18) | (0x4u<<8);
    RCC_CR |= (1u<<24);                 /* PLLON */
    while(!(RCC_CR & (1u<<25))){}       /* PLLRDY */
    RCC_CFGR |= (0x2u<<0);              /* SW = PLL */
    while(((RCC_CFGR>>2)&0x3u)!=0x2u){} /* SWS = PLL */
}

/* set one pin's 4-bit CNF/MODE nibble */
static void gpio_cfg(uint32_t base, int pin, uint32_t nib)
{
    if(pin<8){ int s=pin*4; GPIO_CRL(base)=(GPIO_CRL(base)&~(0xFu<<s))|(nib<<s); }
    else     { int s=(pin-8)*4; GPIO_CRH(base)=(GPIO_CRH(base)&~(0xFu<<s))|(nib<<s); }
}

static void pwm_init(void)
{
    RCC_APB2ENR |= (1u<<11);            /* TIM1EN */
    gpio_cfg(GPIOA,8,0xB); gpio_cfg(GPIOA,9,0xB); gpio_cfg(GPIOA,10,0xB); /* AF-PP 50MHz */
    TIM_CCER(TIM1)=0; TIM_BDTR(TIM1)=0; /* hard off before changing mode */
    TIM_DIER(TIM1)=0; TIM_SR(TIM1)=0;
    TIM_CR1(TIM1)=0; TIM_CR2(TIM1)=0; TIM_SMCR(TIM1)=0;
    TIM_PSC(TIM1)=0; TIM_ARR(TIM1)=PWM_ARR-1; TIM_RCR(TIM1)=0;
    TIM_CNT(TIM1)=0;
    TIM_CCMR1(TIM1)=(0x6u<<4)|(1u<<3)|(0x6u<<12)|(1u<<11); /* CH1,CH2 PWM1 + preload */
    TIM_CCMR2(TIM1)=(0x6u<<4)|(1u<<3);                     /* CH3 PWM1 + preload */
    TIM_CCR1(TIM1)=0; TIM_CCR2(TIM1)=0; TIM_CCR3(TIM1)=0;
    TIM_EGR(TIM1)=1u;                                      /* load zero now */
    TIM_SR(TIM1)=0;                                        /* clear UIF from UG */
    TIM_CCER(TIM1)=(1u<<0)|(1u<<4)|(1u<<8);               /* CC1E,CC2E,CC3E */
    TIM_BDTR(TIM1)=(1u<<15);                              /* MOE */
    TIM_CR1(TIM1)=(1u<<7)|(1u<<0);                        /* ARPE + CEN */
}

static void delay(volatile uint32_t n){ while(n--){ __asm__ volatile("nop"); } }

/* ---- 1 kHz free-running timebase on TIM2 (APB1 /2 -> timer clk = 72 MHz) --- */
static void tick_init(void)
{
    RCC_APB1ENR |= (1u<<0);            /* TIM2EN */
    TIM_PSC(TIM2) = 72000u-1u;         /* 72 MHz / 72000 = 1 kHz */
    TIM_ARR(TIM2) = 0xFFFFu;
    TIM_CR1(TIM2) = (1u<<0);           /* CEN */
}
static uint32_t s_ms_hi=0; static uint16_t s_ms_prev=0;
/* must be polled at least once per 65 s; the main loop calls it constantly */
static uint32_t millis(void)
{
    uint16_t c=(uint16_t)TIM_CNT(TIM2);
    if(c<s_ms_prev) s_ms_hi += 0x10000u;
    s_ms_prev=c;
    return s_ms_hi + (uint32_t)c;
}

static void adc_init(void)
{
    RCC_APB2ENR |= (1u<<9);            /* ADC1EN */
    RCC_CFGR = (RCC_CFGR&~(0x3u<<14)) | (0x2u<<14); /* ADCPRE=/6 -> 12 MHz */
    /* shunt/sense pins to analog input (CNF=00 MODE=00 = 0x0) */
    gpio_cfg(GPIOA,1,0x0); gpio_cfg(GPIOA,4,0x0); gpio_cfg(GPIOA,5,0x0);
    gpio_cfg(GPIOA,6,0x0); gpio_cfg(GPIOA,7,0x0);
    gpio_cfg(GPIOB,0,0x0); gpio_cfg(GPIOB,1,0x0);
    ADC_CR2(ADC1) = (1u<<0);           /* ADON: wake */
    delay(20000);
    ADC_CR2(ADC1) |= (1u<<3); while(ADC_CR2(ADC1)&(1u<<3)){}  /* RSTCAL */
    ADC_CR2(ADC1) |= (1u<<2); while(ADC_CR2(ADC1)&(1u<<2)){}  /* CAL */
    ADC_SMPR2(ADC1) = 0x3FFFFFFFu;     /* ch0-9 max sample time (239.5cyc) */
    ADC_SQR1(ADC1)  = 0;               /* 1 conversion */
    /* SWSTART trigger: EXTSEL=111, EXTTRIG=1, keep ADON */
    ADC_CR2(ADC1) = (1u<<0)|(0x7u<<17)|(1u<<20);
}

static uint32_t read_adc(uint32_t ch)
{
    uint32_t timeout=100000u;
    /* GD32 can leave EOC asserted long enough that a back-to-back caller
     * consumes the previous channel's DR before the new conversion starts. */
    (void)ADC_DR(ADC1);
    ADC_SR(ADC1) &= ~(1u<<1);
    ADC_SQR3(ADC1) = ch;
    ADC_CR2(ADC1) |= (1u<<22);         /* SWSTART */
    while(!(ADC_SR(ADC1)&(1u<<1))){ if(--timeout==0u) return 0xFFFFFFFFu; }
    return ADC_DR(ADC1) & 0x0FFFu;
}

/* The sources have different impedances. Discard one conversion after every
 * mux change, then average, so the prior channel cannot look like a rail
 * transition during an automated GPIO sweep. */
static uint32_t read_adc_avg(uint32_t ch, uint32_t n)
{
    uint32_t sum=0;
    uint32_t v=read_adc(ch);
    if(v==0xFFFFFFFFu) return v;
    for(uint32_t k=0;k<n;k++){
        v=read_adc(ch);
        if(v==0xFFFFFFFFu) return v;
        sum += v;
    }
    return n ? (sum/n) : 0u;
}

static void uart_init(void)
{
    RCC_APB2ENR |= (1u<<2)|(1u<<3)|(1u<<0);  /* IOPAEN,IOPBEN,AFIOEN */
    AFIO_MAPR = 0x02000000u;                 /* SWJ_CFG=010: JTAG off, SWD on -> frees PA15/PB3/PB4 */
    RCC_APB1ENR |= (1u<<17);                 /* USART2EN */
    gpio_cfg(GPIOA,2,0xB);                    /* PA2 AF-PP TX */
    gpio_cfg(GPIOA,3,0x4);                    /* PA3 floating input RX */
    USART_BRR(USART2)=0x138;                  /* 36MHz/115200 */
    USART_CR1(USART2)=(1u<<13)|(1u<<3)|(1u<<2); /* UE,TE,RE */
}

static uint32_t pwm_deadline=0;

static void motor_stop(void)
{
    /* MOE/CCER clear is immediate; CCR writes alone are not, due to preload. */
    TIM_CCER(TIM1)=0; TIM_BDTR(TIM1)=0;
    /* Disable every TIM1 IRQ/DMA source before EGR.UG can set UIF. */
    TIM_DIER(TIM1)=0; TIM_SR(TIM1)=0;
    TIM_CR1(TIM1)=0; TIM_CR2(TIM1)=0; TIM_SMCR(TIM1)=0;
    TIM_PSC(TIM1)=0; TIM_ARR(TIM1)=PWM_ARR-1; TIM_RCR(TIM1)=0; TIM_CNT(TIM1)=0;
    TIM_CCR1(TIM1)=0; TIM_CCR2(TIM1)=0; TIM_CCR3(TIM1)=0;
    TIM_CCMR1(TIM1)=(0x6u<<4)|(1u<<3)|(0x6u<<12)|(1u<<11);
    TIM_CCMR2(TIM1)=(0x6u<<4)|(1u<<3);
    /* Canonical pin routing: TIM1 full remap off; SWD on with JTAG disabled. */
    AFIO_MAPR=0x02000000u;
    gpio_cfg(GPIOA,8,0xB); gpio_cfg(GPIOA,9,0xB); gpio_cfg(GPIOA,10,0xB);
    TIM_CR1(TIM1)=(1u<<7)|(1u<<0);
    TIM_EGR(TIM1)=1u;
    TIM_SR(TIM1)=0;
    TIM_CCER(TIM1)=(1u<<0)|(1u<<4)|(1u<<8);
    TIM_BDTR(TIM1)=(1u<<15);
    pwm_deadline=0;
}

static int motor_timer_canonical(void)
{
    return TIM_CR1(TIM1)==0x81u && TIM_CR2(TIM1)==0u && TIM_SMCR(TIM1)==0u &&
           /* UIF naturally reasserts while the 20 kHz timer runs; DIER=0 is
            * the safety invariant. SR is still cleared before every EGR. */
           TIM_DIER(TIM1)==0u &&
           TIM_PSC(TIM1)==0u && TIM_ARR(TIM1)==(PWM_ARR-1u) && TIM_RCR(TIM1)==0u &&
           TIM_CCMR1(TIM1)==0x6868u && TIM_CCMR2(TIM1)==0x0068u &&
           TIM_CCER(TIM1)==0x0111u && TIM_BDTR(TIM1)==0x8000u &&
           TIM_CCR1(TIM1)==0u && TIM_CCR2(TIM1)==0u && TIM_CCR3(TIM1)==0u &&
           (AFIO_MAPR&0x070000C0u)==0x02000000u &&
           (GPIO_CRH(GPIOA)&0x00000FFFu)==0x00000BBBu;
}

static void set_pwm(int ch, int pct)
{
    if(pct<0)pct=0;
    if(pct>PWM_SAFE_MAX)pct=PWM_SAFE_MAX;
    uint32_t ccr=(uint32_t)pct*36u;
    if(ch==1)TIM_CCR1(TIM1)=ccr; else if(ch==2)TIM_CCR2(TIM1)=ccr; else if(ch==3)TIM_CCR3(TIM1)=ccr;
    /* A lost UART/SSH session must not leave a motor command asserted. */
    if(pct>0) pwm_deadline=millis()+750u;
    else if(TIM_CCR1(TIM1)==0u&&TIM_CCR2(TIM1)==0u&&TIM_CCR3(TIM1)==0u) pwm_deadline=0;
}

/* parse "A11" style token -> base+pin; returns 1 ok */
static int parse_pin(const char*t, uint32_t*base, int*pin)
{
    if(t[0]=='A'||t[0]=='a')*base=GPIOA; else if(t[0]=='B'||t[0]=='b')*base=GPIOB; else return 0;
    int p=0,i=1; if(t[i]<'0'||t[i]>'9')return 0;
    while(t[i]>='0'&&t[i]<='9'){p=p*10+(t[i]-'0');i++;}
    if(t[i])return 0;
    if(p<0||p>15)return 0;
    *pin=p;
    return 1;
}

static int pin_is_hold(uint32_t base,int pin)
{
    if(base==GPIOA && (pin==0||pin==11||pin==12||pin==15)) return 1;
    if(base==GPIOB && (pin==3||pin==4||pin==5||pin==13||pin==14)) return 1;
    return 0;
}

static int pin_manual_output_ok(uint32_t base,int pin)
{
    if(base==GPIOA && (pin==0||pin==11||pin==12||pin==15)) return 1;
    if(base==GPIOB && (pin==3||pin==4||pin==5||pin==13||pin==14)) return 1;
    return 0;
}

static int pin_manual_input_ok(uint32_t base,int pin)
{
    return base==GPIOB && (pin==2||pin==8||pin==9||pin==12||pin==15);
}

/* ================= SMBus / smart-battery exploration state ================= */

static uint8_t  ka_addr    = 0x0B;   /* SBS smart battery default 7-bit addr */
static uint8_t  ka_cmd     = 0x09;   /* Voltage(mV) — benign periodic poll   */
static int      ka_on      = 1;      /* keepalive enabled at boot            */
static int      ka_verbose = 0;
static uint32_t ka_n=0, ka_err=0;
static uint16_t ka_lastv=0;
static int      ka_lastr=SMB_OK;
static uint32_t ka_next=0;
static int      hb_on=1;             /* periodic uptime heartbeat            */
static uint32_t hb_next=0;
static int      s_boot_scl=0, s_boot_sda=0;   /* pull-up probe taken at boot  */

struct sbs_e { uint8_t cmd; const char *name; };
/* standard SBS word registers worth grabbing in one shot */
static const struct sbs_e SBS[] = {
    {0x00,"MfrAccess"},  {0x03,"BattMode"},   {0x08,"Temp.1K"},   {0x09,"Volt_mV"},
    {0x0A,"Curr_mA"},    {0x0B,"AvgCurr"},    {0x0D,"RelSoC%"},   {0x0E,"AbsSoC%"},
    {0x0F,"RemCap"},     {0x10,"FullCap"},    {0x16,"BattStatus"},{0x17,"Cycles"},
    {0x18,"DesignCap"},  {0x19,"DesignV"},    {0x1A,"SpecInfo"},  {0x1B,"MfrDate"},
    {0x1C,"Serial"},     {0x3C,"CellV4"},     {0x3D,"CellV3"},    {0x3E,"CellV2"},
    {0x3F,"CellV1"},
};
#define SBS_N ((int)(sizeof(SBS)/sizeof(SBS[0])))

/* ============ arbitrary-pin bit-bang I2C scanner (find BMS SCL/SDA) ============
 * smbus.c is hardwired to PB6/PB7, which already answers as a 0x6A sensor —
 * not the battery pack. The pack's real SCL/SDA are two OTHER GPIOA/GPIOB
 * pins. This is a second, independent, parameterized bit-bang master so we
 * can try candidate pin pairs live without touching the working PB6/7 bus
 * or the PB5/13/14 power-hold pins that keep the board alive.
 * Same "open-drain release = Hi-Z" model as smbus.c; no internal-pullup
 * fallback on purpose — the whole point is to find lines that ALREADY have
 * a real pull-up (the pack's own bus bias), since a pin with none can't be
 * the BMS link anyway.
 */
#define XI2C_QDLY    120u
#define XI2C_STRETCH 6000u
#define XI2C_NIB_PU  0x8u   /* input, pull-up/down selected by ODR */
#define XI2C_NIB_PP  0x3u   /* output push-pull 50MHz */

typedef struct { uint32_t sclB; int sclP; uint32_t sdaB; int sdaP; } xi2c_pins_t;

/* IMPORTANT: these candidate pins are UNKNOWN quantities — we don't yet know
 * which, if any, have a real external pull-up. True open-drain "release"
 * (Hi-Z, no drive) on a line with NO pull-up does not float to a clean
 * high; it just lingers near whatever it was last driven to (parasitic
 * capacitance), which showed up live as every single address "ACKing" on
 * PB10=SCL scans — a false-positive, not a real device. Fix: always use
 * the MCU's internal weak pull-up (~40k) on release, exactly like smbus.c's
 * SMB_MODE_PU. That guarantees "release with nothing pulling it down"
 * reads a genuine, repeatable HIGH, so a LOW on release means something is
 * actually there. Slower speed (120 vs smbus.c's default 40) gives the
 * weak pull-up time to actually charge the line before we sample it. */
static void xi2c_release(uint32_t base,int pin){ gpio_cfg(base,pin,XI2C_NIB_PU); GPIO_BSRR(base)=(1u<<pin); }
static void xi2c_low(uint32_t base,int pin){ GPIO_BRR(base)=(1u<<pin); gpio_cfg(base,pin,XI2C_NIB_PP); }
static int  xi2c_read(uint32_t base,int pin){ return (int)((GPIO_IDR(base)>>pin)&1u); }
static void xi2c_qd(void){ volatile uint32_t n=XI2C_QDLY; while(n--){ __asm__ volatile("nop"); } }

/* pins we must never let this scanner touch, even by mistake:
 * PB5/PB6/PB7/PB13/PB14 = power-hold + the working (0x6A) SMBus, PA2/PA3 =
 * console UART, PA13/PA14 = SWD (needed to reflash later). */
static int xi2c_pin_reserved(uint32_t base,int pin)
{
    if(pin_is_hold(base,pin)) return 1;
    if(base==GPIOB && (pin==5||pin==6||pin==7||pin==13||pin==14)) return 1;
    if(base==GPIOB && (pin==8||pin==9||pin==12||pin==15)) return 1;
    if(base==GPIOA && (pin==2||pin==3||pin==13||pin==14)) return 1;
    /* PB10/PB11 = USART3 TX/RX to a REAL module (stock ran it 19200 8N1).
     * That is why PB10 idles high and toggles "slowly" -- it is a driven UART
     * line, not an I2C bus. Scanning it only ever produces stuck-line
     * artifacts, so keep the hunter off it entirely. */
    if(base==GPIOB && (pin==10||pin==11)) return 1;
    return 0;
}

/* ---- STOCK IDLE RESTORE (fixes the board powering itself off) -------------
 * Stock firmware drove PA0/PA11/PA12/PA15/PB3/PB4 as push-pull LOW and
 * PB5/PB13/PB14 as push-pull HIGH. v6 only ever re-drove the HIGH group, and
 * every x* command ends by leaving its two pins as FLOATING inputs (0x4).
 * Floating one of the stock-LOW pins releases part of the power-hold, and the
 * pack cuts the rail ~30-60 s later -- that is what killed `xall` mid-sweep
 * and what powered the board off during the pull-up survey. Call this after
 * every x* operation. PB6/PB7 are deliberately untouched: smb_init() owns
 * them (they carry the working 0x6A bus). */
static void xrestore(void)
{
    static const struct { uint32_t base; int pin; } LOWPINS[] = {
        {GPIOA,0},{GPIOA,11},{GPIOA,12},{GPIOA,15},{GPIOB,3},{GPIOB,4}
    };
    for(int k=0;k<(int)(sizeof(LOWPINS)/sizeof(LOWPINS[0]));k++){
        GPIO_BRR(LOWPINS[k].base)=(1u<<LOWPINS[k].pin);   /* level first */
        gpio_cfg(LOWPINS[k].base,LOWPINS[k].pin,0x3);     /* then drive  */
    }
    /* Set the latch before output mode to avoid a stale-low glitch. */
    GPIO_BSRR(GPIOB)=(1u<<5)|(1u<<13)|(1u<<14);
    gpio_cfg(GPIOB,5,0x3); gpio_cfg(GPIOB,13,0x3); gpio_cfg(GPIOB,14,0x3);
    /* stock inputs: B8/B9/B12 pull-down (EXTI), B15 pull-up */
    GPIO_BRR(GPIOB)=(1u<<8)|(1u<<9)|(1u<<12);
    gpio_cfg(GPIOB,8,0x8); gpio_cfg(GPIOB,9,0x8); gpio_cfg(GPIOB,12,0x8);
    GPIO_BSRR(GPIOB)=(1u<<15); gpio_cfg(GPIOB,15,0x8);
}

/* Guarded 120 ms drive probe. amask selects PA0/PA11/PA12 high and bmask
 * selects PB13/PB14/PB5 low. Callers expose only tightly constrained mappings;
 * arbitrary masks are never accepted from UART. */
static int drive_mask_test(uint32_t amask,uint32_t bmask,uint32_t ch,uint32_t pct,
                           const char *tag,uint32_t ai,uint32_t bi)
{
    static const int apin[3]={0,11,12};
    static const int bpin[3]={13,14,5};
    /* Corrected after explicit EOC clearing exposed the old one-channel lag. */
    static const uint8_t sch[3]={5,6,7};       /* PA5, PA6, PA7 */
    static const uint8_t rch[2]={4,8};         /* PA4 rail divider, PB0 rail/gate node */
    uint32_t base[3]={0,0,0},vmin[3]={0,0,0},vmax[3]={0,0,0};
    uint32_t drivebase[3]={0,0,0};
    uint32_t rbase[2]={0,0},rmin[2]={0,0},rmax[2]={0,0};
    uint32_t aidr=0,bidr=0,aexpect=0,bexpect=0;
    uint32_t elapsed=0,drive_start=0;
    int drive_started=0;
    int tripped=0,adc_error=0,aborted=0,timer_error=0,pin_error=0,pin_stage=0;
    int rail_error=0,clean_error=0;
    int rail_gate=(tag[0]=='P'&&tag[1]=='5'&&tag[2]==0);
    if((amask&~0x7u)||(bmask&~0x7u)||ch<1u||ch>3u||pct>5u){ puts_("err: drive range\r\n"); return 0; }

    motor_stop();
    if(!motor_timer_canonical()){ timer_error=1; goto cleanup; }
    xrestore();
    aexpect=0u; bexpect=(1u<<5)|(1u<<13)|(1u<<14);
    aidr=GPIO_IDR(GPIOA)&((1u<<0)|(1u<<11)|(1u<<12));
    bidr=GPIO_IDR(GPIOB)&((1u<<5)|(1u<<13)|(1u<<14));
    if(aidr!=aexpect || bidr!=bexpect){
        pin_error=1; pin_stage=1; goto cleanup;
    }
    for(int k=0;k<3;k++){
        base[k]=vmin[k]=vmax[k]=read_adc_avg(sch[k],8);
        if(base[k]==0xFFFFFFFFu||base[k]<600u||base[k]>1800u){ adc_error=1; goto cleanup; }
    }
    for(int k=0;k<2;k++){
        rbase[k]=rmin[k]=rmax[k]=read_adc_avg(rch[k],4);
        if(rbase[k]==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
    }
    if(rail_gate&&rbase[1]>500u){ rail_error=1; goto cleanup; }

    /* If both sides change, lower B first, then atomically raise selected A
     * controls. This preserves the established low/low intermediate. */
    uint32_t bbits=0u,abits=0u;
    for(int k=0;k<3;k++) if(bmask&(1u<<k)) bbits|=(1u<<bpin[k]);
    for(int k=0;k<3;k++) if(amask&(1u<<k)) abits|=(1u<<apin[k]);
    if(bbits) GPIO_BRR(GPIOB)=bbits;
    if(abits) GPIO_BSRR(GPIOA)=abits;
    /* Allow the APB write and externally loaded output pads to settle before
     * sampling IDR. An immediate read can still return the preceding level. */
    delay(1024u);
    aexpect=abits; bexpect=((1u<<5)|(1u<<13)|(1u<<14))&~bbits;
    aidr=GPIO_IDR(GPIOA)&((1u<<0)|(1u<<11)|(1u<<12));
    bidr=GPIO_IDR(GPIOB)&((1u<<5)|(1u<<13)|(1u<<14));
    if(aidr!=aexpect || bidr!=bexpect){
        pin_error=1; pin_stage=2; goto cleanup;
    }

    /* Precharge/settle the enabled rail for 200 ms before PWM. */
    uint32_t ts=millis();
    while((millis()-ts)<200u){
        for(int k=0;k<3;k++){
            uint32_t v=read_adc_avg(sch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<vmin[k])vmin[k]=v;
            if(v>vmax[k])vmax[k]=v;
            uint32_t d=(v>base[k])?(v-base[k]):(base[k]-v);
            if(d>120u){ tripped=1; goto cleanup; }
        }
        for(int k=0;k<2;k++){
            uint32_t v=read_adc_avg(rch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<rmin[k])rmin[k]=v;
            if(v>rmax[k])rmax[k]=v;
        }
        if(USART_SR(USART2)&SR_RXNE){
            uint8_t c=(uint8_t)USART_DR(USART2);
            if(c=='!'||c==0x1Bu||c==0x03u){ aborted=1; goto cleanup; }
        }
    }
    if(rail_gate&&(rmax[0]<(rbase[0]+300u)||rmax[1]<2000u)){
        rail_error=1; goto cleanup;
    }

    /* Re-baseline the shunts with the rail/control state fully asserted. */
    for(int k=0;k<3;k++){
        drivebase[k]=read_adc_avg(sch[k],8);
        if(drivebase[k]==0xFFFFFFFFu||drivebase[k]<600u||drivebase[k]>1800u){ adc_error=1; goto cleanup; }
        if(drivebase[k]<vmin[k])vmin[k]=drivebase[k];
        if(drivebase[k]>vmax[k])vmax[k]=drivebase[k];
    }

    set_pwm((int)ch,(int)pct);
    uint32_t t0=drive_start=millis();
    drive_started=1;
    while((millis()-t0)<120u){
        for(int k=0;k<3;k++){
            uint32_t v=read_adc_avg(sch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<vmin[k])vmin[k]=v;
            if(v>vmax[k])vmax[k]=v;
            uint32_t d=(v>drivebase[k])?(v-drivebase[k]):(drivebase[k]-v);
            uint32_t d0=(v>base[k])?(v-base[k]):(base[k]-v);
            if(d>120u||d0>120u){ tripped=1; goto cleanup; }
        }
        for(int k=0;k<2;k++){
            uint32_t v=read_adc_avg(rch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<rmin[k])rmin[k]=v;
            if(v>rmax[k])rmax[k]=v;
        }
        if(USART_SR(USART2)&SR_RXNE){
            uint8_t c=(uint8_t)USART_DR(USART2);
            if(c=='!'||c==0x1Bu||c==0x03u){ aborted=1; goto cleanup; }
        }
    }
cleanup:
    if(drive_started) elapsed=millis()-drive_start;
    motor_stop();
    /* xrestore uses the same safe low/low intermediate on the way to stock. */
    xrestore();
    delay(1024u);
    if(!motor_timer_canonical() ||
       (GPIO_IDR(GPIOA)&((1u<<0)|(1u<<11)|(1u<<12)))!=0u ||
       (GPIO_IDR(GPIOB)&((1u<<5)|(1u<<13)|(1u<<14)))!=((1u<<5)|(1u<<13)|(1u<<14)))
        clean_error=1;

    puts_(tag); puts_(" a="); putu_(ai); puts_(" b="); putu_(bi); puts_(" ch="); putu_(ch);
    puts_(" pct="); putu_(pct); puts_(" ms="); putu_(elapsed);
    if(clean_error) puts_(" CLEANERR"); else if(timer_error) puts_(" TIMERERR");
    else if(rail_error) puts_(" RAILERR"); else if(pin_error) puts_(" PINERR");
    else if(adc_error) puts_(" ADCERR"); else if(aborted) puts_(" ABORT");
    else if(tripped) puts_(" TRIP"); else puts_(" ok");
    for(int k=0;k<3;k++){
        puts_(" s"); putu_((uint32_t)k); putc_('='); putu_(base[k]); putc_('/');
        putu_(drivebase[k]); putc_('/'); putu_(vmin[k]); putc_('/'); putu_(vmax[k]);
    }
    for(int k=0;k<2;k++){
        puts_(" r"); putu_((uint32_t)k); putc_('='); putu_(rbase[k]); putc_('/');
        putu_(rmin[k]); putc_('/'); putu_(rmax[k]);
    }
    puts_(" pin="); putu_((uint32_t)pin_stage); putc_('/'); puth_(aidr,4); putc_('/');
    puth_(bidr,4); putc_('/'); puth_(aexpect,4); putc_('/'); puth_(bexpect,4);
    puts_("\r\n");
    return !(clean_error||timer_error||rail_error||pin_error||adc_error||aborted||tripped);
}

/* Original one-A/one-B matrix, with 9 meaning leave that side stock. */
static void drive_pair_test(uint32_t ai,uint32_t bi,uint32_t ch,uint32_t pct)
{
    if((ai>2u&&ai!=9u)||(bi>1u&&bi!=9u)) { puts_("err: dt range\r\n"); return; }
    drive_mask_test(ai==9u?0u:(1u<<ai),bi==9u?0u:(1u<<bi),ch,pct,"DT",ai,bi);
}

/* v9 topology probe: PA0 is always the common rail enable. aopt optionally
 * adds PA11/PA12 high; bopt optionally lowers PB13/PB14. The parser requires
 * a literal ARM token so this cannot be invoked by an old script by accident. */
static void drive_rail_combo_test(uint32_t aopt,uint32_t bopt,uint32_t ch,uint32_t pct)
{
    uint32_t amask=1u,bmask=0u;
    if(aopt>2u||bopt>2u){ puts_("err: d9 range\r\n"); return; }
    if(aopt) amask|=(1u<<aopt);
    if(bopt) bmask=(1u<<(bopt-1u));
    drive_mask_test(amask,bmask,ch,pct,"D9",aopt,bopt);
}

/* v11 final static-pair hypothesis: PA0 high with the normally-held PB5 low.
 * This may release the pack's power hold, so it is available only through the
 * separately armed p5 command and only at zero or one percent PWM. */
static void drive_pb5_pair_test(uint32_t ch,uint32_t pct)
{
    static int zero_qualified=0;
    if(ch<1u||ch>3u||pct>1u){ puts_("err: p5 range\r\n"); return; }
    if(pct&& !zero_qualified){ puts_("err: p5 zero-duty qualification required\r\n"); return; }
    int ok=drive_mask_test(1u,4u,ch,pct,"P5",0u,5u);
    if(pct==0u) zero_qualified=ok;
    else if(!ok) zero_qualified=0;
}

/* v10 complementary-output probe. Only the two known TIM1 N outputs are
 * exposed: pair 1 = PA8/PB13, pair 2 = PA9/PB14. At 1%, the physical state
 * is PA-low/PB-high for 99% of each 200 us period and PA-high/PB-low for a
 * short compare interval, with about 1 us of timer-enforced dead time. */
static void complementary_test(uint32_t pair,uint32_t pct)
{
    static const uint8_t sch[3]={5,6,7};
    static const uint8_t rch[2]={4,8};
    const uint32_t carr=14399u;          /* 72 MHz / 14400 = 5 kHz */
    const uint32_t pct_ticks=144u;       /* 1% = 2 us raw compare interval */
    const uint32_t deadtime=72u;         /* about 1 us at CKD=00 */
    uint32_t base[3]={0,0,0},onbase[3]={0,0,0},vmin[3]={0,0,0},vmax[3]={0,0,0};
    uint32_t rbase[2]={0,0},rmin[2]={0,0},rmax[2]={0,0};
    uint32_t drive_start=0,elapsed=0;
    int timer_error=0,pin_error=0,adc_error=0,rail_live=0,rail_error=0;
    int tripped=0,aborted=0,clean_error=0,drive_started=0,phase=0;
    int apin,bpin;
    uint32_t ccmr1,ccer;

    if((pair!=1u&&pair!=2u)||pct>15u){ puts_("err: c10 range\r\n"); return; }
    apin=(pair==1u)?8:9;
    bpin=(pair==1u)?13:14;
    ccmr1=(pair==1u)?0x0068u:0x6800u;
    ccer=(pair==1u)?0x0005u:0x0050u; /* CCxE + CCxNE, active-high polarity */

    motor_stop();
    if(!motor_timer_canonical()){ timer_error=1; goto cleanup; }
    xrestore();
    if((GPIO_IDR(GPIOA)&((1u<<0)|(1u<<11)|(1u<<12)))!=0u ||
       (GPIO_IDR(GPIOB)&((1u<<13)|(1u<<14)))!=((1u<<13)|(1u<<14)) ||
       (GPIO_IDR(GPIOA)&(1u<<apin))!=0u){
        pin_error=1; goto cleanup;
    }
    for(int k=0;k<3;k++){
        base[k]=vmin[k]=vmax[k]=read_adc_avg(sch[k],8);
        if(base[k]==0xFFFFFFFFu||base[k]<600u||base[k]>1800u){ adc_error=1; goto cleanup; }
    }
    for(int k=0;k<2;k++){
        rbase[k]=rmin[k]=rmax[k]=read_adc_avg(rch[k],4);
        if(rbase[k]==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
    }
    /* PB0 is a slow rail/gate node. Refuse to start while it is still high
     * from a preceding test so the rail transition remains observable. */
    if(rbase[1]>500u){ rail_live=1; goto cleanup; }

    /* Hand all three main outputs to defined GPIO-low levels before changing
     * the timer profile; nonselected AF pins must not float when CCxE clears. */
    TIM_CCER(TIM1)=0; TIM_BDTR(TIM1)=0; TIM_DIER(TIM1)=0; TIM_SR(TIM1)=0;
    GPIO_BRR(GPIOA)=(1u<<8)|(1u<<9)|(1u<<10);
    gpio_cfg(GPIOA,8,0x3); gpio_cfg(GPIOA,9,0x3); gpio_cfg(GPIOA,10,0x3);

    /* Program the complete diagnostic profile with every output hard-off. */
    TIM_CR1(TIM1)=0; TIM_CR2(TIM1)=0; TIM_SMCR(TIM1)=0;
    TIM_PSC(TIM1)=0; TIM_ARR(TIM1)=carr; TIM_RCR(TIM1)=0; TIM_CNT(TIM1)=0;
    TIM_CCMR1(TIM1)=ccmr1; TIM_CCMR2(TIM1)=0;
    TIM_CCR1(TIM1)=0; TIM_CCR2(TIM1)=0; TIM_CCR3(TIM1)=0;
    TIM_EGR(TIM1)=1u; TIM_SR(TIM1)=0;
    TIM_CCER(TIM1)=ccer;
    TIM_BDTR(TIM1)=(1u<<15)|deadtime;
    TIM_CR1(TIM1)=0x81u;

    /* The timer is already producing the captured PA-low/PB-high idle state.
     * Hand only the selected main/N pins to AF after preloading GPIO levels. */
    GPIO_BRR(GPIOA)=(1u<<apin);
    GPIO_BSRR(GPIOB)=(1u<<bpin);
    gpio_cfg(GPIOA,apin,0xB);
    gpio_cfg(GPIOB,bpin,0xB);           /* selected CHxN AF-PP 50 MHz */
    delay(1024u);
    if(TIM_CR1(TIM1)!=0x81u||TIM_CR2(TIM1)!=0u||TIM_SMCR(TIM1)!=0u||
       TIM_DIER(TIM1)!=0u||TIM_PSC(TIM1)!=0u||TIM_ARR(TIM1)!=carr||
       TIM_RCR(TIM1)!=0u||TIM_CCMR1(TIM1)!=ccmr1||TIM_CCMR2(TIM1)!=0u||
       TIM_CCER(TIM1)!=ccer||TIM_BDTR(TIM1)!=((1u<<15)|deadtime)||
       TIM_CCR1(TIM1)!=0u||TIM_CCR2(TIM1)!=0u||TIM_CCR3(TIM1)!=0u){
        timer_error=1; goto cleanup;
    }
    if(((GPIO_CRH(GPIOA)>>((apin-8)*4))&0xFu)!=0xBu ||
       ((GPIO_CRH(GPIOB)>>((bpin-8)*4))&0xFu)!=0xBu){
        pin_error=1; goto cleanup;
    }
    if((GPIO_IDR(GPIOA)&(1u<<apin))!=0u || (GPIO_IDR(GPIOB)&(1u<<bpin))==0u){
        pin_error=1; goto cleanup;
    }
    uint32_t cnt0=TIM_CNT(TIM1);
    delay(1024u);
    if(TIM_CNT(TIM1)==cnt0){ timer_error=1; goto cleanup; }

    phase=1;
    GPIO_BSRR(GPIOA)=(1u<<0);           /* rail enable asserted last */
    delay(1024u);
    if((GPIO_IDR(GPIOA)&(1u<<0))==0u){ pin_error=1; goto cleanup; }

    uint32_t ts=millis();
    while((millis()-ts)<200u){
        for(int k=0;k<3;k++){
            uint32_t v=read_adc_avg(sch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<vmin[k])vmin[k]=v;
            if(v>vmax[k])vmax[k]=v;
            uint32_t d=(v>base[k])?(v-base[k]):(base[k]-v);
            if(d>120u){ tripped=1; goto cleanup; }
        }
        for(int k=0;k<2;k++){
            uint32_t v=read_adc_avg(rch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<rmin[k])rmin[k]=v;
            if(v>rmax[k])rmax[k]=v;
        }
        if(USART_SR(USART2)&SR_RXNE){
            uint8_t c=(uint8_t)USART_DR(USART2);
            if(c=='!'||c==0x1Bu||c==0x03u){ aborted=1; goto cleanup; }
        }
    }
    if(rmax[0]<(rbase[0]+300u)||rmax[1]<2000u){ rail_error=1; goto cleanup; }
    for(int k=0;k<3;k++){
        onbase[k]=read_adc_avg(sch[k],8);
        if(onbase[k]==0xFFFFFFFFu||onbase[k]<600u||onbase[k]>1800u){ adc_error=1; goto cleanup; }
        if(onbase[k]<vmin[k])vmin[k]=onbase[k];
        if(onbase[k]>vmax[k])vmax[k]=onbase[k];
    }

    phase=2;
    uint32_t compare=pct*pct_ticks;
    if(pair==1u) TIM_CCR1(TIM1)=compare;
    else         TIM_CCR2(TIM1)=compare;
    if((pair==1u&&TIM_CCR1(TIM1)!=compare) ||
       (pair==2u&&TIM_CCR2(TIM1)!=compare) ||
       (pair==1u&&TIM_CCR2(TIM1)!=0u) ||
       (pair==2u&&TIM_CCR1(TIM1)!=0u) || TIM_CCR3(TIM1)!=0u){
        timer_error=1; goto cleanup;
    }
    /* Transfer the preloaded compare at a known boundary and clear UIF before
     * starting the measured 120 ms window. DIER is verified disabled. */
    TIM_EGR(TIM1)=1u;
    TIM_SR(TIM1)=0;
    drive_start=millis(); drive_started=1;
    while((millis()-drive_start)<120u){
        for(int k=0;k<3;k++){
            uint32_t v=read_adc_avg(sch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<vmin[k])vmin[k]=v;
            if(v>vmax[k])vmax[k]=v;
            uint32_t d0=(v>base[k])?(v-base[k]):(base[k]-v);
            uint32_t d1=(v>onbase[k])?(v-onbase[k]):(onbase[k]-v);
            if(d0>120u||d1>120u){ tripped=1; goto cleanup; }
        }
        for(int k=0;k<2;k++){
            uint32_t v=read_adc_avg(rch[k],2);
            if(v==0xFFFFFFFFu){ adc_error=1; goto cleanup; }
            if(v<rmin[k])rmin[k]=v;
            if(v>rmax[k])rmax[k]=v;
        }
        if(USART_SR(USART2)&SR_RXNE){
            uint8_t c=(uint8_t)USART_DR(USART2);
            if(c=='!'||c==0x1Bu||c==0x03u){ aborted=1; goto cleanup; }
        }
    }

cleanup:
    if(drive_started) elapsed=millis()-drive_start;
    /* Kill switching and the rail before handing CHxN back to GPIO. */
    TIM_BDTR(TIM1)=0; TIM_CCER(TIM1)=0;
    GPIO_BRR(GPIOA)=(1u<<0);
    if(pair==1u||pair==2u){
        GPIO_BRR(GPIOA)=(1u<<apin);
        gpio_cfg(GPIOA,apin,0x3);
        GPIO_BSRR(GPIOB)=(1u<<bpin);
        gpio_cfg(GPIOB,bpin,0x3);
    }
    motor_stop();
    xrestore();
    delay(1024u);
    if(!motor_timer_canonical() ||
       (GPIO_IDR(GPIOA)&((1u<<0)|(1u<<11)|(1u<<12)))!=0u ||
       (GPIO_IDR(GPIOB)&((1u<<5)|(1u<<13)|(1u<<14)))!=((1u<<5)|(1u<<13)|(1u<<14)) ||
       ((GPIO_CRH(GPIOB)>>((bpin-8)*4))&0xFu)!=0x3u)
        clean_error=1;

    puts_("C10 pair="); putu_(pair); puts_(" pol=N pct="); putu_(pct);
    puts_(" phase="); putu_((uint32_t)phase); puts_(" ms="); putu_(elapsed);
    if(clean_error) puts_(" CLEANERR"); else if(timer_error) puts_(" TIMERERR");
    else if(pin_error) puts_(" PINERR"); else if(adc_error) puts_(" ADCERR");
    else if(rail_live) puts_(" RAILLIVE"); else if(rail_error) puts_(" RAILERR");
    else if(aborted) puts_(" ABORT"); else if(tripped) puts_(" TRIP"); else puts_(" ok");
    for(int k=0;k<3;k++){
        puts_(" s"); putu_((uint32_t)k); putc_('='); putu_(base[k]); putc_('/');
        putu_(onbase[k]); putc_('/'); putu_(vmin[k]); putc_('/'); putu_(vmax[k]);
    }
    for(int k=0;k<2;k++){
        puts_(k==0?" pa4=":" pb0="); putu_(rbase[k]); putc_('/');
        putu_(rmin[k]); putc_('/'); putu_(rmax[k]);
    }
    puts_("\r\n");
}

static int xi2c_ping(xi2c_pins_t *p, uint8_t addr);   /* fwd: defined below */

/* ---- real-device vs stuck-line discriminator ------------------------------
 * A floating or stuck-low SDA makes EVERY address look like an ACK, which is
 * exactly the contiguous 0x08,0x09,0x0A... block xall reported on PB10. A
 * genuine device must pass all four tests. */
static int xi2c_lines_idle_high(xi2c_pins_t *p)
{
    xi2c_release(p->sclB,p->sclP); xi2c_release(p->sdaB,p->sdaP);
    { volatile uint32_t n=20000u; while(n--){ __asm__ volatile("nop"); } }
    return xi2c_read(p->sclB,p->sclP) && xi2c_read(p->sdaB,p->sdaP);
}

/* 1 = looks like a real device at addr */
static int xi2c_verify(xi2c_pins_t *p, uint8_t addr)
{
    /* (a) must ACK its own address, twice in a row */
    if(xi2c_ping(p,addr)!=SMB_OK) return 0;
    if(xi2c_ping(p,addr)!=SMB_OK) return 0;
    /* (d) SDA must be released high again after the transfer */
    if(!xi2c_read(p->sdaB,p->sdaP)) return 0;
    /* (b) immediate neighbours must NOT ACK */
    if(addr>0x08u && xi2c_ping(p,(uint8_t)(addr-1))==SMB_OK) return 0;
    if(addr<0x77u && xi2c_ping(p,(uint8_t)(addr+1))==SMB_OK) return 0;
    return 1;
}

static int xi2c_scl_wait(xi2c_pins_t*p)
{
    uint32_t tries=XI2C_STRETCH;
    xi2c_release(p->sclB,p->sclP);
    while(!xi2c_read(p->sclB,p->sclP)){ if(--tries==0u) return SMB_ETMO; xi2c_qd(); }
    return SMB_OK;
}
static int xi2c_start(xi2c_pins_t*p)
{
    xi2c_release(p->sdaB,p->sdaP); xi2c_qd();
    if(xi2c_scl_wait(p)) return SMB_ETMO;
    xi2c_qd();
    xi2c_low(p->sdaB,p->sdaP); xi2c_qd(); xi2c_qd();
    xi2c_low(p->sclB,p->sclP); xi2c_qd();
    return SMB_OK;
}
static int xi2c_stop(xi2c_pins_t*p)
{
    xi2c_low(p->sdaB,p->sdaP); xi2c_qd();
    if(xi2c_scl_wait(p)) return SMB_ETMO;
    xi2c_qd(); xi2c_qd();
    xi2c_release(p->sdaB,p->sdaP); xi2c_qd(); xi2c_qd();
    return SMB_OK;
}
static int xi2c_putbit(xi2c_pins_t*p,int b)
{
    if(b) xi2c_release(p->sdaB,p->sdaP); else xi2c_low(p->sdaB,p->sdaP);
    xi2c_qd();
    if(xi2c_scl_wait(p)) return SMB_ETMO;
    xi2c_qd(); xi2c_qd();
    xi2c_low(p->sclB,p->sclP);
    xi2c_qd();
    return SMB_OK;
}
static int xi2c_getbit(xi2c_pins_t*p,int*b)
{
    xi2c_release(p->sdaB,p->sdaP); xi2c_qd();
    if(xi2c_scl_wait(p)) return SMB_ETMO;
    xi2c_qd();
    *b=xi2c_read(p->sdaB,p->sdaP);
    xi2c_qd();
    xi2c_low(p->sclB,p->sclP);
    xi2c_qd();
    return SMB_OK;
}
static int xi2c_putbyte(xi2c_pins_t*p,uint8_t v)
{
    int i,ack;
    for(i=7;i>=0;i--){ if(xi2c_putbit(p,(v>>i)&1u)) return SMB_ETMO; }
    if(xi2c_getbit(p,&ack)) return SMB_ETMO;
    return ack?SMB_ENAK:SMB_OK;
}
static int xi2c_getbyte(xi2c_pins_t*p,uint8_t*v,int send_ack)
{
    int i,b; uint8_t r=0;
    for(i=0;i<8;i++){ if(xi2c_getbit(p,&b)) return SMB_ETMO; r=(uint8_t)((r<<1)|(uint8_t)b); }
    if(xi2c_putbit(p, send_ack?0:1)) return SMB_ETMO;
    *v=r; return SMB_OK;
}
static int xi2c_ping(xi2c_pins_t*p,uint8_t addr)
{
    int r;
    if(xi2c_start(p)){ (void)xi2c_stop(p); return SMB_ETMO; }
    r=xi2c_putbyte(p,(uint8_t)(addr<<1));
    (void)xi2c_stop(p);
    return r;
}
static int xi2c_read_word(xi2c_pins_t*p,uint8_t addr,uint8_t cmd,uint16_t*out)
{
    int r; uint8_t lo=0,hi=0;
    if(xi2c_start(p)){ (void)xi2c_stop(p); return SMB_ETMO; }
    if((r=xi2c_putbyte(p,(uint8_t)(addr<<1)))) goto done;
    if((r=xi2c_putbyte(p,cmd))) goto done;
    if((r=xi2c_start(p))) goto done;                          /* repeated START */
    if((r=xi2c_putbyte(p,(uint8_t)((addr<<1)|1u)))) goto done;
    if((r=xi2c_getbyte(p,&lo,1))) goto done;                  /* ACK  */
    if((r=xi2c_getbyte(p,&hi,0))) goto done;                  /* NACK */
    if(out) *out=(uint16_t)(((uint16_t)hi<<8)|lo);
done:
    (void)xi2c_stop(p);
    return r;
}

/* Candidate pins for the BMS SCL/SDA link: everything left over once you take
 * out the console UART, SWD, PWM/ADC-in-use pins, and the power-hold/PB6-7
 * pins the poke fw already claims. PB10/PB11 go first — they are the chip's
 * native I2C2 pins, the single most likely spot for a hardware SMBus link. */
static const struct { uint32_t base; int pin; const char *name; } XCAND[] = {
    /* PB10/PB11 REMOVED: they are USART3 TX/RX to a real module (stock ran
     * 19200 8N1 there), not an I2C bus. Every "hit" on them was a stuck-line
     * artifact and they are now in xi2c_pin_reserved() as well. */
    {GPIOB,15,"B15"},                     /* pull-up, no EXTI -- best candidate */
    {GPIOB,9, "B9" },                     /* pull-up present                    */
    {GPIOB,8, "B8" },                     /* stock-idle: inputs, undetermined   */
    {GPIOB,12,"B12"},                     /* stock-idle: input, EXTI          */
    {GPIOA,0, "A0" }, {GPIOA,11,"A11"},
    {GPIOA,12,"A12"}, {GPIOA,15,"A15"},
    {GPIOB,3, "B3" }, {GPIOB,4, "B4" },
};
#define XCAND_N ((int)(sizeof(XCAND)/sizeof(XCAND[0])))

static void ka_poll(uint32_t now)
{
    ka_next = now + 1000u;
    uint16_t v=0;
    int r = smb_read_word(ka_addr, ka_cmd, &v);
    ka_n++;
    if(r) ka_err++; else ka_lastv=v;
    ka_lastr=r;
    if(ka_verbose){
        puts_("\r\nka 0x"); puth_(ka_cmd,2); puts_(" -> "); puts_(smberr(r));
        if(!r){ puts_(" 0x"); puth_(v,4); puts_(" ("); putu_(v); putc_(')'); }
        puts_("\r\n> ");
    }
}

int main(void)
{
    clock_init();
    uart_init();
    /* Always establish the complete captured stock-idle state before PWM. */
    xrestore();
    /* Power-hold: drive stock-idle-HIGH outputs high so the pack keeps the
     * rail latched after button release (PB5/6/7/13/14). Prevents idle power-off. */
    GPIO_BSRR(GPIOB) = (1u<<5)|(1u<<6)|(1u<<7)|(1u<<13)|(1u<<14);
    gpio_cfg(GPIOB,5,0x3); gpio_cfg(GPIOB,6,0x3); gpio_cfg(GPIOB,7,0x3);
    gpio_cfg(GPIOB,13,0x3); gpio_cfg(GPIOB,14,0x3);

    /* Timebase + SMBus FIRST, and fire one poll immediately: the pack's
     * discharge FET may time out 30-60 s after button release, so the
     * handshake has to start before anything slow. PB6/PB7 change role
     * here from "power-hold" to SCL/SDA (both idle high either way). */
    tick_init();
    smb_init();
    /* If the lines do not idle high there is no usable pull-up: every transfer
     * would stall on the stretch timeout (~1 s) and choke the console. Detect
     * once, hold off the keepalive, and let the operator pick 'bmode pu'. */
    smb_probe_pullups(&s_boot_scl, &s_boot_sda);
    if(s_boot_scl && s_boot_sda) ka_poll(millis());
    else                         ka_on = 0;

    pwm_init();
    adc_init();
    puts_("\r\n=== SP5 diagnostic fw v11 @72MHz ===\r\n"
          "  p<ch><pct> o<Ppin><v> i<Ppin> a s ?\r\n"
          "  dt <aidx 0-2> <bidx 0-1> <ch 1-3> <pct 0-5>  guarded 120ms probe\r\n"
          "  dt 9 9 <ch 1-3> <pct 0-5>  guarded stock-state probe\r\n"
          "  use index 9 on either side to leave that side at stock\r\n"
          "  d9 ARM <aopt 0-2> <bopt 0-2> <ch 1-3> <pct 0-5>  PA0 rail combo\r\n"
          "  p5 ARM <ch 1-3> <pct 0-1>  PA0 high + PB5 low guarded probe\r\n"
          "  c10 ARM <pair 1-2> N <pct 0-15>  PA0 + complementary PWM probe\r\n"
          "  bscan bpu bmode<od|pu> bspeed<n> ba<addr> br<cmd> brb<cmd>\r\n"
          "  bblk<cmd> bw<cmd><val> bdump bdumpx bka<0|1> bkv<0|1> bkc<cmd> bstat brec bhb<0|1>\r\n"
          "  xpu<P1><P2> xscan<P1><P2> xrd<P1><P2><cmd> xall  (arbitrary-pin I2C, uses ba addr)\r\n");
    puts_("SMBus PB6=SCL PB7=SDA  idle: SCL="); putu_((uint32_t)s_boot_scl);
    puts_(" SDA="); putu_((uint32_t)s_boot_sda);
    if(s_boot_scl && s_boot_sda) puts_("  pull-ups OK, keepalive RUNNING\r\n> ");
    else puts_("  NO PULL-UPS: keepalive OFF. Try 'bmode pu','bspeed 120','bka 1'\r\n> ");

    char line[48]; int n=0;
    for(;;){
        /* Keepalive + heartbeat. Only between lines (n==0) so a blocking
         * SMBus transaction can never eat characters mid-command. */
        uint32_t now = millis();
        if(pwm_deadline && (int32_t)(now-pwm_deadline)>=0){
            motor_stop();
            puts_("\r\nAUTO-STOP pwm timeout\r\n> ");
        }
        if(n==0){
            if(ka_on && (int32_t)(now-ka_next) >= 0) ka_poll(now);
            if(hb_on && (int32_t)(now-hb_next) >= 0){
                hb_next = now + 5000u;
                puts_("\r\n[t="); putu_(now); puts_("ms ka="); putu_(ka_n);
                puts_(" err="); putu_(ka_err); puts_(" last="); puts_(smberr(ka_lastr));
                if(ka_lastr==SMB_OK){ puts_(" v="); putu_(ka_lastv); }
                puts_("]\r\n> ");
            }
        }
        if(!(USART_SR(USART2)&SR_RXNE)) continue;
        char c=(char)(USART_DR(USART2)&0xFF);
        if(c=='\r'||c=='\n'){
            line[n]=0;
            /* tokenize on spaces */
            char*tok[7]; int nt=0; int i=0;
            while(line[i]&&nt<7){ while(line[i]==' ')i++; if(!line[i])break; tok[nt++]=&line[i]; while(line[i]&&line[i]!=' ')i++; if(line[i])line[i++]=0; }
            if(nt==0){ /* nothing */ }
            else if(streq(tok[0],"dt")&&nt>=5){
                uint32_t ai,bi,ch,pct;
                if(parse_num(tok[1],&ai)&&parse_num(tok[2],&bi)&&parse_num(tok[3],&ch)&&parse_num(tok[4],&pct))
                    drive_pair_test(ai,bi,ch,pct);
                else puts_("err\r\n");
            }
            else if(streq(tok[0],"d9")&&nt==6&&streq(tok[1],"ARM")){
                uint32_t aopt,bopt,ch,pct;
                if(parse_num(tok[2],&aopt)&&parse_num(tok[3],&bopt)&&parse_num(tok[4],&ch)&&parse_num(tok[5],&pct))
                    drive_rail_combo_test(aopt,bopt,ch,pct);
                else puts_("err\r\n");
            }
            else if(streq(tok[0],"p5")&&nt==4&&streq(tok[1],"ARM")){
                uint32_t ch,pct;
                if(parse_num(tok[2],&ch)&&parse_num(tok[3],&pct))
                    drive_pb5_pair_test(ch,pct);
                else puts_("err\r\n");
            }
            else if(streq(tok[0],"c10")&&nt==5&&streq(tok[1],"ARM")&&streq(tok[3],"N")){
                uint32_t pair,pct;
                if(parse_num(tok[2],&pair)&&parse_num(tok[4],&pct))
                    complementary_test(pair,pct);
                else puts_("err\r\n");
            }
            else if(streq(tok[0],"p")&&nt==3){
                uint32_t ch,pct;
                if(parse_num(tok[1],&ch)&&parse_num(tok[2],&pct)&&ch>=1u&&ch<=3u){
                    if(pct>(uint32_t)PWM_SAFE_MAX)pct=(uint32_t)PWM_SAFE_MAX;
                    motor_stop();                 /* also canonicalizes TIM1 after raw pokes */
                    if(!motor_timer_canonical()) puts_("REJECT TIM1 not canonical; reset required\r\n");
                    else {
                        set_pwm((int)ch,(int)pct);
                        puts_("pwm ch"); putu_(ch); puts_(" = "); putu_(pct); puts_("% (750ms timeout)\r\n");
                    }
                } else puts_("err\r\n");
            }
            else if(tok[0][0]=='o'&&nt>=3){
                uint32_t b,ov; int pin; if(parse_pin(tok[1],&b,&pin)&&parse_num(tok[2],&ov)&&ov<=1u&&pin_manual_output_ok(b,pin)){
                    int high=(int)ov;
                    if((b==GPIOB&&((pin==3&&high)||(pin==5&&!high))) || TIM_CCR1(TIM1)||TIM_CCR2(TIM1)||TIM_CCR3(TIM1)){
                        puts_("REJECT unsafe GPIO state (PB3-high, PB5-low, or PWM active)\r\n");
                    } else {
                        if(high) GPIO_BSRR(b)=(1u<<pin); else GPIO_BRR(b)=(1u<<pin);
                        gpio_cfg(b,pin,0x3); /* GP out PP 50MHz */
                        puts_("set "); putc_(tok[1][0]); putu_(pin); puts_(" = "); putu_((uint32_t)high); puts_("\r\n");
                    }
                } else puts_("err\r\n");
            }
            else if(tok[0][0]=='i'&&nt>=2){
                uint32_t b; int pin; if(parse_pin(tok[1],&b,&pin)){
                    if(pin_is_hold(b,pin)||!pin_manual_input_ok(b,pin)) puts_("REJECT pin cannot be left floating\r\n");
                    else {
                        gpio_cfg(b,pin,0x4); /* floating input */
                        puts_("in "); putc_(tok[1][0]); putu_(pin); puts_(" = "); putu_((GPIO_IDR(b)>>pin)&1u); puts_("\r\n");
                    }
                } else puts_("err\r\n");
            }
            else if(tok[0][0]=='a'){
                static const uint8_t chs[7]={1,4,5,6,7,8,9};
                static const char*lbl[7]={"PA1","PA4","PA5","PA6","PA7","PB0","PB1"};
                for(int k=0;k<7;k++){
                    uint32_t v=read_adc_avg(chs[k],4);
                    puts_(lbl[k]); putc_('='); if(v==0xFFFFFFFFu) puts_("ERR"); else putu_(v);
                    putc_(k<6?' ':'\n');
                }
                putc_('\r');
            }
            else if(tok[0][0]=='s'){ motor_stop(); puts_("STOP all pwm=0\r\n"); }
            else if(tok[0][0]=='?'){ puts_("ccr: "); putu_(TIM_CCR1(TIM1)); putc_(' '); putu_(TIM_CCR2(TIM1)); putc_(' '); putu_(TIM_CCR3(TIM1)); puts_(" /3600\r\n"); }
            /* generic 32-bit register access: mr <hexaddr> ; mw <hexaddr> <hexval> */
            else if(streq(tok[0],"mr")&&nt>=2){ uint32_t ma; if(parse_num(tok[1],&ma)){
                puts_("["); puth_(ma,8); puts_("]="); puth_(REG(ma),8); puts_("\r\n");
            } else puts_("err\r\n"); }
            else if(streq(tok[0],"mw")&&nt>=3){ uint32_t ma,mv; if(parse_num(tok[1],&ma)&&parse_num(tok[2],&mv)){
                if(TIM_CCR1(TIM1)||TIM_CCR2(TIM1)||TIM_CCR3(TIM1)) puts_("REJECT mw while PWM active\r\n");
                else {
                    REG(ma)=mv; puts_("["); puth_(ma,8); puts_("]<="); puth_(mv,8);
                    puts_(" rd="); puth_(REG(ma),8); puts_("\r\n");
                }
            } else puts_("err\r\n"); }
            /* one-shot TIM1 state dump (all the bridge-relevant regs) */
            else if(streq(tok[0],"treg")){
                puts_("CR1="); puth_(TIM_CR1(TIM1),4);
                puts_(" CR2="); puth_(REG(TIM1+0x04),4);
                puts_(" SR="); puth_(REG(TIM1+0x10),4);
                puts_(" CCMR1="); puth_(TIM_CCMR1(TIM1),4);
                puts_(" CCMR2="); puth_(TIM_CCMR2(TIM1),4);
                puts_(" CCER="); puth_(TIM_CCER(TIM1),4);
                puts_(" BDTR="); puth_(TIM_BDTR(TIM1),4);
                puts_("\r\n CCR="); putu_(TIM_CCR1(TIM1)); putc_('/'); putu_(TIM_CCR2(TIM1)); putc_('/'); putu_(TIM_CCR3(TIM1));
                puts_(" ARR="); putu_(TIM_ARR(TIM1));
                puts_(" MAPR="); puth_(AFIO_MAPR,8);
                puts_(" GBCRH="); puth_(GPIO_CRH(GPIOB),8);
                puts_(" GACRH="); puth_(GPIO_CRH(GPIOA),8);
                puts_("\r\n");
            }
            else if(tok[0][0]=='b'){
                uint32_t x=0,y=0;
                if(streq(tok[0],"bscan")){
                    int found=0; puts_("scan:");
                    for(uint32_t ad=0x08u; ad<=0x77u; ad++){
                        if(smb_ping((uint8_t)ad)==SMB_OK){ puts_(" 0x"); puth_(ad,2); found++; }
                    }
                    if(!found) puts_(" none");
                    puts_("\r\n");
                }
                else if(streq(tok[0],"bpu")){
                    int sc=0,sd=0; smb_probe_pullups(&sc,&sd);
                    puts_("float SCL(PB6)="); putu_((uint32_t)sc);
                    puts_(" SDA(PB7)="); putu_((uint32_t)sd);
                    puts_((sc&&sd)?"  -> ext pull-ups present, keep 'bmode od'\r\n"
                                  :"  -> NO ext pull-ups, use 'bmode pu' + 'bspeed 120'\r\n");
                }
                else if(streq(tok[0],"bmode")&&nt>=2){
                    smb_set_mode(tok[1][0]=='o');
                    puts_("mode="); puts_(smb_get_mode()==SMB_MODE_OD?"od":"pu"); puts_("\r\n");
                }
                else if(streq(tok[0],"bspeed")&&nt>=2&&parse_num(tok[1],&x)){
                    smb_set_speed(x); puts_("qdly="); putu_(smb_get_speed()); puts_("\r\n");
                }
                else if(streq(tok[0],"ba")&&nt>=2&&parse_num(tok[1],&x)){
                    ka_addr=(uint8_t)x; puts_("addr=0x"); puth_(ka_addr,2); puts_("\r\n");
                }
                else if(streq(tok[0],"br")&&nt>=2&&parse_num(tok[1],&x)){
                    uint16_t v=0; int r=smb_read_word(ka_addr,(uint8_t)x,&v);
                    puts_("r 0x"); puth_(x,2); puts_(" = "); puts_(smberr(r));
                    if(!r){ puts_("  0x"); puth_(v,4); puts_("  u="); putu_(v);
                            puts_("  s="); puti_((int32_t)(int16_t)v); }
                    puts_("\r\n");
                }
                else if(streq(tok[0],"brb")&&nt>=2&&parse_num(tok[1],&x)){
                    uint8_t v=0; int r=smb_read_byte(ka_addr,(uint8_t)x,&v);
                    puts_("rb 0x"); puth_(x,2); puts_(" = "); puts_(smberr(r));
                    if(!r){ puts_("  0x"); puth_(v,2); puts_("  "); putu_(v); }
                    puts_("\r\n");
                }
                else if(streq(tok[0],"bw")&&nt>=3&&parse_num(tok[1],&x)&&parse_num(tok[2],&y)){
                    int r=smb_write_word(ka_addr,(uint8_t)x,(uint16_t)y);
                    puts_("w 0x"); puth_(x,2); puts_(" <- 0x"); puth_(y,4);
                    puts_(" : "); puts_(smberr(r)); puts_("\r\n");
                }
                else if(streq(tok[0],"bblk")&&nt>=2&&parse_num(tok[1],&x)){
                    uint8_t buf[34]; uint8_t ln=0;
                    int r=smb_read_block(ka_addr,(uint8_t)x,buf,&ln,(uint8_t)sizeof(buf));
                    puts_("blk 0x"); puth_(x,2); puts_(" = "); puts_(smberr(r));
                    puts_(" n="); putu_(ln); puts_("  ");
                    for(int k=0;k<(int)ln;k++){ puth_(buf[k],2); putc_(' '); }
                    puts_(" |");
                    for(int k=0;k<(int)ln;k++) putc_((buf[k]>=32&&buf[k]<127)?(char)buf[k]:'.');
                    puts_("|\r\n");
                }
                else if(streq(tok[0],"bdump")){
                    for(int k=0;k<SBS_N;k++){
                        uint16_t v=0; int r=smb_read_word(ka_addr,SBS[k].cmd,&v);
                        puts_("0x"); puth_(SBS[k].cmd,2); putc_(' '); puts_(SBS[k].name); puts_(" = ");
                        if(r) puts_(smberr(r));
                        else { puts_("0x"); puth_(v,4); puts_(" ("); putu_(v); putc_(')'); }
                        puts_("\r\n");
                    }
                }
                else if(streq(tok[0],"bdumpx")){
                    /* Full byte-register sweep 0x00-0xFF on the known PB6/7 bus
                     * at the current 'ba' address (default 0x6A device). Only
                     * ACKed registers print, to keep this readable. */
                    puts_("bdumpx addr=0x"); puth_(ka_addr,2); puts_(":\r\n");
                    int nfound=0;
                    for(uint32_t cmdv=0; cmdv<=0xFFu; cmdv++){
                        uint8_t v=0; int r=smb_read_byte(ka_addr,(uint8_t)cmdv,&v);
                        if(r==SMB_OK){ puts_("0x"); puth_(cmdv,2); putc_('='); puth_(v,2); putc_(' '); nfound++;
                                       if(nfound%8==0) puts_("\r\n"); }
                    }
                    puts_("\r\ndone n="); putu_((uint32_t)nfound); puts_("\r\n");
                }
                else if(streq(tok[0],"bka")&&nt>=2){ ka_on=(tok[1][0]!='0'); puts_("ka="); putu_((uint32_t)ka_on); puts_("\r\n"); }
                else if(streq(tok[0],"bkv")&&nt>=2){ ka_verbose=(tok[1][0]!='0'); puts_("kav="); putu_((uint32_t)ka_verbose); puts_("\r\n"); }
                else if(streq(tok[0],"bkc")&&nt>=2&&parse_num(tok[1],&x)){ ka_cmd=(uint8_t)x; puts_("kacmd=0x"); puth_(ka_cmd,2); puts_("\r\n"); }
                else if(streq(tok[0],"bhb")&&nt>=2){ hb_on=(tok[1][0]!='0'); puts_("hb="); putu_((uint32_t)hb_on); puts_("\r\n"); }
                else if(streq(tok[0],"brec")){ smb_recover(); puts_("bus recover done\r\n"); }
                else if(streq(tok[0],"bstat")){
                    puts_("t="); putu_(millis()); puts_("ms addr=0x"); puth_(ka_addr,2);
                    puts_(" kacmd=0x"); puth_(ka_cmd,2); puts_(" ka="); putu_(ka_n);
                    puts_(" err="); putu_(ka_err); puts_(" last="); puts_(smberr(ka_lastr));
                    puts_(" v="); putu_(ka_lastv);
                    puts_(" mode="); puts_(smb_get_mode()==SMB_MODE_OD?"od":"pu");
                    puts_(" qdly="); putu_(smb_get_speed()); puts_("\r\n");
                }
                else puts_("err\r\n");
            }
            else if(tok[0][0]=='x'){
                if(streq(tok[0],"xpu")&&nt>=3){
                    uint32_t b1,b2; int p1,p2;
                    if(!parse_pin(tok[1],&b1,&p1)||!parse_pin(tok[2],&b2,&p2)) puts_("err\r\n");
                    else if(xi2c_pin_reserved(b1,p1)||xi2c_pin_reserved(b2,p2)) puts_("err: reserved pin\r\n");
                    else {
                        gpio_cfg(b1,p1,0x4); gpio_cfg(b2,p2,0x4); /* floating input */
                        delay(20000);
                        int l1=(int)((GPIO_IDR(b1)>>p1)&1u), l2=(int)((GPIO_IDR(b2)>>p2)&1u);
                        puts_("xpu "); puts_(tok[1]); putc_('='); putu_((uint32_t)l1);
                        puts_("  "); puts_(tok[2]); putc_('='); putu_((uint32_t)l2); puts_("\r\n");
                        xrestore();   /* MUST: never leave a power-hold pin floating */
                    }
                }
                else if(streq(tok[0],"xscan")&&nt>=3){
                    uint32_t b1,b2; int p1,p2;
                    if(!parse_pin(tok[1],&b1,&p1)||!parse_pin(tok[2],&b2,&p2)) puts_("err\r\n");
                    else if(xi2c_pin_reserved(b1,p1)||xi2c_pin_reserved(b2,p2)) puts_("err: reserved pin\r\n");
                    else if(b1==b2&&p1==p2) puts_("err: same pin\r\n");
                    else {
                        xi2c_pins_t pp={b1,p1,b2,p2};
                        puts_("xscan SCL="); puts_(tok[1]); puts_(" SDA="); puts_(tok[2]); puts_(" :");
                        uint32_t t0=millis();
                        /* GATE 1: both lines must idle high. SMBus needs pull-ups;
                         * without them every address "ACKs" and the scan is noise. */
                        if(!xi2c_lines_idle_high(&pp)){
                            puts_(" NO-PULLUP (SCL="); putu_((uint32_t)xi2c_read(b1,p1));
                            puts_(" SDA="); putu_((uint32_t)xi2c_read(b2,p2));
                            puts_(") -- cannot be an SMBus pair\r\n");
                            xrestore();
                        } else {
                            int found=0, run=0, stuck=0, timedout=0;
                            for(uint32_t ad=0x08u; ad<=0x77u; ad++){
                                if((ad&0x07u)==0 && (millis()-t0)>4000u){ timedout=1; break; }
                                if(xi2c_ping(&pp,(uint8_t)ad)==SMB_OK){
                                    run++;
                                    /* GATE 2: 4 consecutive ACKs == stuck line, not 4 devices */
                                    if(run>=4){ stuck=1; break; }
                                    /* GATE 3+4: verified device only */
                                    if(xi2c_verify(&pp,(uint8_t)ad)){
                                        puts_(" 0x"); puth_(ad,2); puts_("(VERIFIED)");
                                        found++;
                                    }
                                } else run=0;
                            }
                            if(stuck)         puts_(" STUCK-LINE (>=4 consecutive ACKs) -- artifact, ignore");
                            else if(timedout) puts_(" SLOW/bailed");
                            else if(!found)   puts_(" none");
                            puts_(" ["); putu_(millis()-t0); puts_("ms]\r\n");
                            xrestore();
                        }
                    }
                }
                else if(streq(tok[0],"xrd")&&nt>=4){
                    uint32_t b1,b2,x; int p1,p2;
                    if(!parse_pin(tok[1],&b1,&p1)||!parse_pin(tok[2],&b2,&p2)||!parse_num(tok[3],&x)) puts_("err\r\n");
                    else if(xi2c_pin_reserved(b1,p1)||xi2c_pin_reserved(b2,p2)) puts_("err: reserved pin\r\n");
                    else if(b1==b2&&p1==p2) puts_("err: same pin\r\n");
                    else {
                        xi2c_pins_t pp={b1,p1,b2,p2};
                        xi2c_release(b1,p1); xi2c_release(b2,p2); delay(4000);
                        uint16_t v=0; int r=xi2c_read_word(&pp,ka_addr,(uint8_t)x,&v);
                        puts_("xrd SCL="); puts_(tok[1]); puts_(" SDA="); puts_(tok[2]);
                        puts_(" addr=0x"); puth_(ka_addr,2); puts_(" cmd=0x"); puth_(x,2);
                        puts_(" = "); puts_(smberr(r));
                        if(!r){ puts_("  0x"); puth_(v,4); puts_("  u="); putu_(v); }
                        puts_("\r\n");
                        xrestore();
                    }
                }
                else if(streq(tok[0],"xall")){
                    /* Auto-sweep every ordered pair among XCAND: both roles
                     * (A,B) and (B,A) are tried since which pin is SCL vs
                     * SDA is unknown. Only pairs that ACK something print —
                     * keeps the output usable even if the window is short.
                     * PB6/7 keepalive is serviced between pairs so a long
                     * sweep can't itself starve the anti-power-off poll. */
                    puts_("xall: "); putu_((uint32_t)XCAND_N); puts_(" pins, ");
                    putu_((uint32_t)(XCAND_N*(XCAND_N-1))); puts_(" ordered pairs, addr 0x08-0x77...\r\n");
                    int totalhits=0; int pairidx=0;
                    for(int si=0; si<XCAND_N; si++){
                        for(int di=0; di<XCAND_N; di++){
                            if(si==di) continue;
                            pairidx++;
                            if(pairidx%15==1){ puts_(".."); putu_((uint32_t)pairidx); putc_('/');
                                               putu_((uint32_t)(XCAND_N*(XCAND_N-1))); puts_(" t="); putu_(millis()); puts_("ms\r\n"); }
                            uint32_t now=millis();
                            if(ka_on && (int32_t)(now-ka_next)>=0) ka_poll(now);
                            uint32_t b1=XCAND[si].base; int p1=XCAND[si].pin;
                            uint32_t b2=XCAND[di].base; int p2=XCAND[di].pin;
                            if(xi2c_pin_reserved(b1,p1)||xi2c_pin_reserved(b2,p2)) continue; /* belt+suspenders */
                            xi2c_pins_t pp={b1,p1,b2,p2};
                            /* Fast reject: no pull-ups on BOTH lines => cannot be SMBus.
                             * Kills ~all of the 132 pairs in <1 ms each and removes the
                             * stuck-line artifacts that produced the fake 0x08..0x0F block. */
                            if(!xi2c_lines_idle_high(&pp)){ xrestore(); continue; }
                            /* Per-pair time budget: one pin can be electrically slow (real
                             * capacitive load, e.g. genuinely wired to a chip -- we saw B10
                             * take ~14s/pair instead of the expected tens of ms) and that
                             * must never be allowed to eat the whole power window. Bail out
                             * of the address loop once this pair alone has burned >900ms. */
                            uint32_t pair_t0 = millis();
                            int found=0, run=0, stuck=0, timedout=0;
                            for(uint32_t ad=0x08u; ad<=0x77u; ad++){
                                if((ad&0x07u)==0 && (millis()-pair_t0)>900u){ timedout=1; break; }
                                if(xi2c_ping(&pp,(uint8_t)ad)==SMB_OK){
                                    run++;
                                    if(run>=4){ stuck=1; break; }   /* stuck line, not devices */
                                    if(xi2c_verify(&pp,(uint8_t)ad)){
                                        if(!found){ puts_("HIT SCL="); puts_(XCAND[si].name);
                                                    puts_(" SDA="); puts_(XCAND[di].name); puts_(" :"); }
                                        puts_(" 0x"); puth_(ad,2); puts_("(VERIFIED)");
                                        found++;
                                    }
                                } else run=0;
                            }
                            if(found){ totalhits+=found; puts_("\r\n"); }
                            else if(stuck||timedout){ /* artifact: stay silent, keeps output usable */ }
                            xrestore();   /* MUST: restore power-hold before next pair */
                        }
                    }
                    puts_("xall done, hits="); putu_((uint32_t)totalhits); puts_("\r\n");
                }
                else puts_("err\r\n");
            }
            else puts_("err\r\n");
            n=0; puts_("> ");
        } else if(n<(int)sizeof(line)-1){ line[n++]=c; }
    }
}
