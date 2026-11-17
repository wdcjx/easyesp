/* M2: 声明并使用超出目标芯片编号上限的 GPIO */
/* === EASYESP MANIFEST V1 ===
target: esp32c3
track: idf
pins:
- gpio: 25 func: relay
=== END MANIFEST === */
#include "driver/gpio.h"
void app_main(void)
{
    gpio_set_direction(GPIO_NUM_25, GPIO_MODE_OUTPUT);   /* M2：C3 上限 21 */
}
