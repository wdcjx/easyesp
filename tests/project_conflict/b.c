/* 跨文件冲突：组件 B 也声明 gpio8 -> M5 */
/* === EASYESP MANIFEST V1 ===
target: esp32
track: idf
pins:
- gpio: 8 func: button
=== END MANIFEST === */
#include "driver/gpio.h"
void button_init(void) { gpio_set_direction(GPIO_NUM_8, GPIO_MODE_INPUT); }
