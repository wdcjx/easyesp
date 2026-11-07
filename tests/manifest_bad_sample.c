/*
 * manifest_bad_sample.c — EASYESP MANIFEST V1 声明核对反例（validator M 系列自测样本）
 *
 * 期望：FAIL，V2W1。
 *   V1: pins 中 GPIO8 声明两次（led + buzzer）——一引脚一功能
 *   V1: GPIO25 超出 esp32c3 编号上限（21），芯片上不存在
 *   W1: GPIO9 实际使用但未在 pins 声明——分配表应是单一事实源
 */
/* === EASYESP MANIFEST V1 ===
target: esp32c3
track: idf
pins:
  - gpio: 8 func: led
  - gpio: 8 func: buzzer     // 同一引脚两个功能：VIOL
  - gpio: 2 func: button
=== END MANIFEST === */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_timer.h"

#define LED_GPIO    GPIO_NUM_8
#define BUTTON_GPIO GPIO_NUM_2
#define RELAY_GPIO  GPIO_NUM_25   /* C3 无此引脚（上限 GPIO21）：VIOL */
#define ADC_PIN     GPIO_NUM_9    /* 用了但 pins 没声明：WARN */

void app_main(void)
{
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_reset_pin(BUTTON_GPIO);
    gpio_set_direction(BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_reset_pin(RELAY_GPIO);
    gpio_set_direction(RELAY_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(RELAY_GPIO, 0);

    bool led = false;
    int64_t t0 = esp_timer_get_time();
    while (1) {
        if (esp_timer_get_time() - t0 >= 500000) {
            t0 = esp_timer_get_time();
            led = !led;
            gpio_set_level(LED_GPIO, led ? 1 : 0);
        }
        (void)ADC_PIN;
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
