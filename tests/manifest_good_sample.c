/*
 * manifest_good_sample.c — EASYESP MANIFEST V1 声明核对正例（validator M 系列自测样本）
 *
 * 期望：PASS，V0W0。声明与代码一致：pins 覆盖全部实际使用的 GPIO，
 * 编号在 esp32c3 存在范围（0-21）且避开 flash/USB 受禁区。
 */
/* === EASYESP MANIFEST V1 ===
target: esp32c3
track: idf
pins:
  - gpio: 8 func: led        // C3 常用板载 LED（GPIO8，避 flash 11-17 与 USB 18/19）
  - gpio: 2 func: button     // C3 strapping 引脚 BOOT 键：上拉输入读取
=== END MANIFEST === */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_timer.h"

#define LED_GPIO   GPIO_NUM_8
#define BUTTON_GPIO GPIO_NUM_2

void app_main(void)
{
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_reset_pin(BUTTON_GPIO);
    gpio_set_direction(BUTTON_GPIO, GPIO_MODE_INPUT);

    bool led = false;
    int64_t t0 = esp_timer_get_time();
    while (1) {
        if (esp_timer_get_time() - t0 >= 500000) {   /* 500ms 翻转，微秒时基 */
            t0 = esp_timer_get_time();
            led = !led;
            gpio_set_level(LED_GPIO, led ? 1 : 0);
        }
        vTaskDelay(pdMS_TO_TICKS(10));               /* 让出，喂 IDLE/看门狗 */
    }
}
