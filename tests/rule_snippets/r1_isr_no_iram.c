/* R1: attachInterrupt 注册的 ISR 缺少 IRAM_ATTR */
#include "Arduino.h"
void btn_isr(void) { digitalWrite(2, 1); }
void setup(void) { attachInterrupt(0, btn_isr, FALLING); }
void loop(void) { }
