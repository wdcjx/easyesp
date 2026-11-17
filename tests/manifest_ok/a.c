/* 跨文件正常：组件 A 占 gpio2 */
/* === EASYESP MANIFEST V1 ===
target: esp32
track: idf
pins:
- gpio: 2 func: led
=== END MANIFEST === */
#include "driver/gpio.h"
void led_init(void) { gpio_set_direction(GPIO_NUM_2, GPIO_MODE_OUTPUT); }
