#pragma once
// Precise RC-PWM capture for the F405 -> C6 link.
// Measures the HIGH pulse width (us) of each servo signal via GPIO edge interrupts.
// Rate-independent and exact (unlike duty_cycle). D6=GPIO16 (left), D7=GPIO17 (right).
#include "esp_timer.h"
#include "driver/gpio.h"

volatile uint32_t rc_l_rise = 0, rc_r_rise = 0;
volatile uint32_t rc_l_width = 0, rc_r_width = 0;   // last valid pulse width in us (0 = none yet)
volatile int64_t  rc_l_last = 0, rc_r_last = 0;     // esp_timer time of last valid pulse (for staleness)

static void IRAM_ATTR rc_l_isr(void *arg) {
  uint32_t now = (uint32_t) esp_timer_get_time();
  if (gpio_get_level(GPIO_NUM_16)) {
    rc_l_rise = now;                       // rising edge
  } else {
    uint32_t w = now - rc_l_rise;          // falling edge -> width
    if (w > 800 && w < 2200) { rc_l_width = w; rc_l_last = esp_timer_get_time(); }
  }
}
static void IRAM_ATTR rc_r_isr(void *arg) {
  uint32_t now = (uint32_t) esp_timer_get_time();
  if (gpio_get_level(GPIO_NUM_17)) {
    rc_r_rise = now;
  } else {
    uint32_t w = now - rc_r_rise;
    if (w > 800 && w < 2200) { rc_r_width = w; rc_r_last = esp_timer_get_time(); }
  }
}

static void rc_pwm_setup() {
  gpio_config_t io = {};
  io.pin_bit_mask = (1ULL << 16) | (1ULL << 17);
  io.mode = GPIO_MODE_INPUT;
  io.pull_up_en = GPIO_PULLUP_DISABLE;
  io.pull_down_en = GPIO_PULLDOWN_ENABLE;   // unplugged -> low -> no pulses -> STOP
  io.intr_type = GPIO_INTR_ANYEDGE;
  gpio_config(&io);
  gpio_install_isr_service(0);
  gpio_isr_handler_add(GPIO_NUM_16, rc_l_isr, NULL);
  gpio_isr_handler_add(GPIO_NUM_17, rc_r_isr, NULL);
}

// helpers used from the ESPHome lambdas: return width in us, or 0 if stale (>100ms no pulse)
static float rc_l_us() {
  if (rc_l_last == 0 || (esp_timer_get_time() - rc_l_last) > 100000) return 0;
  return (float) rc_l_width;
}
static float rc_r_us() {
  if (rc_r_last == 0 || (esp_timer_get_time() - rc_r_last) > 100000) return 0;
  return (float) rc_r_width;
}
