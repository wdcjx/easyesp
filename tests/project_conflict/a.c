/* 跨文件冲突：组件 A 声明 gpio8 */
/* === EASYESP MANIFEST V1 ===
target: esp32
track: idf
pins:
- gpio: 8 func: relay
=== END MANIFEST === */
#include "driver/gpio.h"
void relay_init(void) { gpio_set_direction(GPIO_NUM_8, GPIO_MODE_OUTPUT); }
