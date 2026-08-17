/* smbus.h — software (bit-bang) SMBus master for SP5-MAIN pack link.
 * Pins: PB6 = SCL, PB7 = SDA  (I2C1 default pins; stock fw held both high).
 * No libc, no interrupts. Blocking, ~1 ms per short transaction.
 */
#ifndef SMBUS_H
#define SMBUS_H

#include <stdint.h>

/* result codes */
#define SMB_OK    0
#define SMB_ENAK  1   /* slave did not ACK */
#define SMB_ETMO  2   /* clock stretch / stuck line timeout */
#define SMB_ELEN  3   /* block length out of range */

/* line drive models --------------------------------------------------------
 * SMB_MODE_OD : true open-drain (CNF=01 MODE=11 -> 0x7). Releasing the line
 *               makes it Hi-Z and the BOARD's external pull-ups raise it.
 *               Correct and safe: we never fight a slave that is pulling low.
 * SMB_MODE_PU : emulated OD for boards with NO external pull-ups. Release =
 *               input-with-pull-up (0x8, ODR=1, ~40k internal). Drive low =
 *               push-pull output low (0x3). Weak pull-up => keep speed low.
 * Start in OD. Use smb_probe_pullups() to decide.                            */
#define SMB_MODE_OD 1
#define SMB_MODE_PU 0

void     smb_init(void);                 /* configures PB6/PB7, leaves bus idle */
void     smb_set_mode(int mode);
int      smb_get_mode(void);
void     smb_set_speed(uint32_t qdly);   /* quarter-bit delay loop count */
uint32_t smb_get_speed(void);

/* Release both lines and sample them. Reports whether something holds each
 * line high, i.e. whether external pull-ups are fitted. 1 = high. */
void smb_probe_pullups(int *scl_high, int *sda_high);

/* Clock out up to 9 pulses to free a slave that is jamming SDA low. */
void smb_recover(void);

/* Bus-level */
int smb_ping(uint8_t addr);                                   /* SMB_OK if ACK */

/* SMBus protocol transactions (addr = 7-bit, e.g. 0x0B for a smart battery) */
int smb_read_byte (uint8_t addr, uint8_t cmd, uint8_t  *out);
int smb_read_word (uint8_t addr, uint8_t cmd, uint16_t *out); /* LSB first    */
int smb_write_word(uint8_t addr, uint8_t cmd, uint16_t val);
int smb_write_byte(uint8_t addr, uint8_t cmd, uint8_t  val);
/* Block read: first returned byte is the count. *len returns actual count. */
int smb_read_block(uint8_t addr, uint8_t cmd, uint8_t *buf, uint8_t *len, uint8_t maxlen);

#endif /* SMBUS_H */
