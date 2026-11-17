/* M4: 使用未在 MANIFEST 声明的 GPIO（WARN 级） */
/* === EASYESP MANIFEST V1 ===
target: esp32
track: idf
pins:
- gpio: 2 func: led
=== END MANIFEST === */
#include "driver/gpio.h"
void app_main(void)
{
    gpio_set_direction(GPIO_NUM_5, GPIO_MODE_OUTPUT);   /* M4：5 未声明 */
}
