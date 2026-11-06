/* blink_uart_demo — 最小完整工程：LED 非阻塞闪烁 + 日志节拍
 * 范式：templates/main_idf.c（软定时器表 + 让出循环）。知识沉淀示例，未上板实测。
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "blink";

#define BLINK_GPIO      GPIO_NUM_2      /* 经典 esp32 devkit 板载 LED；S3/C3 按模组核对 */
#define BLINK_PERIOD_MS 500
#define LOG_PERIOD_MS   5000

static bool led_state = false;
static int64_t next_blink_us = 0;
static int64_t next_log_us = 0;
static uint32_t blink_count = 0;

static void app_init_pins(void)
{
    gpio_reset_pin(BLINK_GPIO);
    gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(BLINK_GPIO, 0);
}

static void app_soft_timer_tick(void)
{
    int64_t now = esp_timer_get_time();          /* 微秒时基 */

    if (now >= next_blink_us) {
        led_state = !led_state;
        gpio_set_level(BLINK_GPIO, led_state);
        blink_count++;
        next_blink_us = now + (int64_t)BLINK_PERIOD_MS * 1000;
    }
    if (now >= next_log_us) {
        ESP_LOGI(TAG, "alive, blink_count=%lu", (unsigned long)blink_count);
        next_log_us = now + (int64_t)LOG_PERIOD_MS * 1000;
    }
}

void app_main(void)
{
    app_init_pins();
    ESP_LOGI(TAG, "blink_uart_demo start");
    next_blink_us = esp_timer_get_time();
    next_log_us = next_blink_us;

    while (1) {
        app_soft_timer_tick();
        vTaskDelay(pdMS_TO_TICKS(10));           /* 让出：IDLE 喂狗 */
    }
}
