/* target 冲突：B 面向 esp32c3 -> M6 */
/* === EASYESP MANIFEST V1 ===
target: esp32c3
track: idf
pins:
- gpio: 3 func: button
=== END MANIFEST === */
#include "driver/gpio.h"
void button_init(void) { gpio_set_direction(GPIO_NUM_3, GPIO_MODE_INPUT); }
