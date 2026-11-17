/* 跨文件正常：组件 B 占 gpio4，与 A 无冲突 */
/* === EASYESP MANIFEST V1 ===
target: esp32
track: idf
pins:
- gpio: 4 func: button
=== END MANIFEST === */
#include "driver/gpio.h"
void button_init(void) { gpio_set_direction(GPIO_NUM_4, GPIO_MODE_INPUT); }
