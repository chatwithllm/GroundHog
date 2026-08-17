/* smbus.c — software (bit-bang) SMBus master on PB6=SCL, PB7=SDA.
 *
 * Target: GD32F103CB @ 72 MHz, bare metal, no libc.
 *
 * Why open-drain by default: during ACK bits and every read byte the SLAVE
 * pulls SDA low. If we released the line by driving it push-pull HIGH we
 * would short the slave's low driver against our high driver. So "release"
 * must mean Hi-Z. Real open-drain (nibble 0x7) does that and still lets us
 * read the true pin level from IDR. Only fall back to SMB_MODE_PU (internal
 * pull-up) if the board turns out to have no external pull-ups.
 */

#include "smbus.h"

#define REG(a) (*(volatile uint32_t *)(a))

#define GPIOB_BASE   0x40010C00u
#define GPIO_CRL(b)  REG((b)+0x00)
#define GPIO_CRH(b)  REG((b)+0x04)
#define GPIO_IDR(b)  REG((b)+0x08)
#define GPIO_BSRR(b) REG((b)+0x10)
#define GPIO_BRR(b)  REG((b)+0x14)

#define PIN_SCL 6
#define PIN_SDA 7

/* CNF/MODE nibbles */
#define NIB_OUT_PP 0x3u   /* general purpose output push-pull, 50 MHz */
#define NIB_OUT_OD 0x7u   /* general purpose output open-drain, 50 MHz */
#define NIB_IN_PUD 0x8u   /* input with pull-up/pull-down (ODR selects)  */

/* Quarter-bit delay. ~8 cycles per loop iteration at 72 MHz, so
 * qdly=40 -> ~4.4 us quarter -> ~57 kHz. Tunable at runtime. */
static uint32_t s_qdly = 40u;
static int      s_mode = SMB_MODE_OD;

/* Clock-stretch / stuck-line guard, in quarter-delay units (~25 ms worst case) */
#define STRETCH_TRIES 6000u

static void cfg(int pin, uint32_t nib)
{
    if (pin < 8) {
        int s = pin * 4;
        GPIO_CRL(GPIOB_BASE) = (GPIO_CRL(GPIOB_BASE) & ~(0xFu << s)) | (nib << s);
    } else {
        int s = (pin - 8) * 4;
        GPIO_CRH(GPIOB_BASE) = (GPIO_CRH(GPIOB_BASE) & ~(0xFu << s)) | (nib << s);
    }
}

static void qd(void)
{
    volatile uint32_t n = s_qdly;
    while (n--) { __asm__ volatile("nop"); }
}

/* ---- line primitives ---------------------------------------------------- */

static void line_release(int pin)
{
    if (s_mode == SMB_MODE_OD) {
        GPIO_BSRR(GPIOB_BASE) = (1u << pin);   /* ODR=1 -> Hi-Z on open-drain */
    } else {
        cfg(pin, NIB_IN_PUD);                  /* input first: avoid driving high */
        GPIO_BSRR(GPIOB_BASE) = (1u << pin);   /* ODR=1 -> internal pull-up      */
    }
}

static void line_low(int pin)
{
    if (s_mode == SMB_MODE_OD) {
        GPIO_BRR(GPIOB_BASE) = (1u << pin);    /* ODR=0 -> pulls low */
    } else {
        GPIO_BRR(GPIOB_BASE) = (1u << pin);    /* ODR=0 (briefly pull-down) */
        cfg(pin, NIB_OUT_PP);                  /* then actively drive low   */
    }
}

static int line_read(int pin)
{
    return (int)((GPIO_IDR(GPIOB_BASE) >> pin) & 1u);
}

#define SCL_LOW()     line_low(PIN_SCL)
#define SDA_LOW()     line_low(PIN_SDA)
#define SDA_RELEASE() line_release(PIN_SDA)
#define SDA_READ()    line_read(PIN_SDA)

/* Release SCL and wait for it to actually go high (slave clock stretching). */
static int scl_release_wait(void)
{
    uint32_t tries = STRETCH_TRIES;
    line_release(PIN_SCL);
    while (!line_read(PIN_SCL)) {
        if (--tries == 0u) return SMB_ETMO;
        qd();
    }
    return SMB_OK;
}

/* ---- bus conditions ------------------------------------------------------ */

static int smb_start(void)
{
    SDA_RELEASE(); qd();
    if (scl_release_wait()) return SMB_ETMO;
    qd();
    SDA_LOW();  qd(); qd();
    SCL_LOW();  qd();
    return SMB_OK;
}

/* repeated START: assumes SCL is currently low */
static int smb_restart(void)
{
    SDA_RELEASE(); qd();
    if (scl_release_wait()) return SMB_ETMO;
    qd(); qd();
    SDA_LOW();  qd(); qd();
    SCL_LOW();  qd();
    return SMB_OK;
}

static int smb_stop(void)
{
    SDA_LOW(); qd();
    if (scl_release_wait()) return SMB_ETMO;
    qd(); qd();
    SDA_RELEASE(); qd(); qd();
    return SMB_OK;
}

/* ---- bit / byte level ---------------------------------------------------- */

static int put_bit(int b)
{
    if (b) SDA_RELEASE(); else SDA_LOW();
    qd();
    if (scl_release_wait()) return SMB_ETMO;
    qd(); qd();
    SCL_LOW();
    qd();
    return SMB_OK;
}

static int get_bit(int *b)
{
    SDA_RELEASE();
    qd();
    if (scl_release_wait()) return SMB_ETMO;
    qd();
    *b = SDA_READ();
    qd();
    SCL_LOW();
    qd();
    return SMB_OK;
}

/* returns SMB_OK if slave ACKed, SMB_ENAK if not, SMB_ETMO on stretch timeout */
static int put_byte(uint8_t v)
{
    int i, ack;
    for (i = 7; i >= 0; i--) {
        if (put_bit((v >> i) & 1u)) return SMB_ETMO;
    }
    if (get_bit(&ack)) return SMB_ETMO;
    return ack ? SMB_ENAK : SMB_OK;
}

static int get_byte(uint8_t *v, int send_ack)
{
    int i, b;
    uint8_t r = 0;
    for (i = 0; i < 8; i++) {
        if (get_bit(&b)) return SMB_ETMO;
        r = (uint8_t)((r << 1) | (uint8_t)b);
    }
    /* ACK = drive SDA low, NACK = leave it released */
    if (put_bit(send_ack ? 0 : 1)) return SMB_ETMO;
    *v = r;
    return SMB_OK;
}

/* ---- public API ---------------------------------------------------------- */

void smb_init(void)
{
    /* Leave both lines released (idle high) before changing drive mode, so we
     * never emit a spurious START on the pack's bus. */
    GPIO_BSRR(GPIOB_BASE) = (1u << PIN_SCL) | (1u << PIN_SDA);
    if (s_mode == SMB_MODE_OD) {
        cfg(PIN_SCL, NIB_OUT_OD);
        cfg(PIN_SDA, NIB_OUT_OD);
    } else {
        cfg(PIN_SCL, NIB_IN_PUD);
        cfg(PIN_SDA, NIB_IN_PUD);
    }
    GPIO_BSRR(GPIOB_BASE) = (1u << PIN_SCL) | (1u << PIN_SDA);
}

void smb_set_mode(int mode)
{
    s_mode = mode ? SMB_MODE_OD : SMB_MODE_PU;
    smb_init();
}

int smb_get_mode(void) { return s_mode; }

void     smb_set_speed(uint32_t qdly) { s_qdly = qdly ? qdly : 1u; }
uint32_t smb_get_speed(void)          { return s_qdly; }

void smb_probe_pullups(int *scl_high, int *sda_high)
{
    /* Float both lines completely (no internal pull) and see what holds them. */
    cfg(PIN_SCL, 0x4u);   /* floating input */
    cfg(PIN_SDA, 0x4u);
    { volatile uint32_t n = 20000u; while (n--) { __asm__ volatile("nop"); } }
    if (scl_high) *scl_high = line_read(PIN_SCL);
    if (sda_high) *sda_high = line_read(PIN_SDA);
    smb_init();           /* restore */
}

void smb_recover(void)
{
    int i;
    SDA_RELEASE();
    for (i = 0; i < 9; i++) {
        line_release(PIN_SCL); qd(); qd();
        SCL_LOW();             qd(); qd();
    }
    line_release(PIN_SCL); qd();
    (void)smb_stop();
}

int smb_ping(uint8_t addr)
{
    int r;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    r = put_byte((uint8_t)((addr << 1) | 0u));
    (void)smb_stop();
    return r;
}

int smb_write_word(uint8_t addr, uint8_t cmd, uint16_t val)
{
    int r;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    if ((r = put_byte((uint8_t)((addr << 1) | 0u))))  goto done;
    if ((r = put_byte(cmd)))                          goto done;
    if ((r = put_byte((uint8_t)(val & 0xFFu))))       goto done;
    if ((r = put_byte((uint8_t)(val >> 8))))          goto done;
done:
    (void)smb_stop();
    return r;
}

int smb_write_byte(uint8_t addr, uint8_t cmd, uint8_t val)
{
    int r;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    if ((r = put_byte((uint8_t)((addr << 1) | 0u)))) goto done;
    if ((r = put_byte(cmd)))                         goto done;
    if ((r = put_byte(val)))                         goto done;
done:
    (void)smb_stop();
    return r;
}

int smb_read_word(uint8_t addr, uint8_t cmd, uint16_t *out)
{
    int r;
    uint8_t lo = 0, hi = 0;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    if ((r = put_byte((uint8_t)((addr << 1) | 0u)))) goto done;
    if ((r = put_byte(cmd)))                         goto done;
    if ((r = smb_restart()))                         goto done;
    if ((r = put_byte((uint8_t)((addr << 1) | 1u)))) goto done;
    if ((r = get_byte(&lo, 1)))                      goto done;   /* ACK  */
    if ((r = get_byte(&hi, 0)))                      goto done;   /* NACK */
    if (out) *out = (uint16_t)(((uint16_t)hi << 8) | lo);
done:
    (void)smb_stop();
    return r;
}

int smb_read_byte(uint8_t addr, uint8_t cmd, uint8_t *out)
{
    int r;
    uint8_t v = 0;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    if ((r = put_byte((uint8_t)((addr << 1) | 0u)))) goto done;
    if ((r = put_byte(cmd)))                         goto done;
    if ((r = smb_restart()))                         goto done;
    if ((r = put_byte((uint8_t)((addr << 1) | 1u)))) goto done;
    if ((r = get_byte(&v, 0)))                       goto done;   /* NACK */
    if (out) *out = v;
done:
    (void)smb_stop();
    return r;
}

int smb_read_block(uint8_t addr, uint8_t cmd, uint8_t *buf, uint8_t *len, uint8_t maxlen)
{
    int r, trunc = 0;
    uint8_t n = 0, i;
    if (smb_start()) { (void)smb_stop(); return SMB_ETMO; }
    if ((r = put_byte((uint8_t)((addr << 1) | 0u)))) goto done;
    if ((r = put_byte(cmd)))                         goto done;
    if ((r = smb_restart()))                         goto done;
    if ((r = put_byte((uint8_t)((addr << 1) | 1u)))) goto done;
    if ((r = get_byte(&n, 1)))                       goto done;   /* count, ACK */
    if (n > maxlen) { trunc = 1; n = maxlen; }
    for (i = 0; i < n; i++) {
        int last = ((int)i + 1 >= (int)n);
        if ((r = get_byte(&buf[i], last ? 0 : 1))) goto done;
    }
    if (len) *len = n;
    if (trunc) r = SMB_ELEN;   /* report truncation without losing it to a later OK */
done:
    (void)smb_stop();
    return r;
}
