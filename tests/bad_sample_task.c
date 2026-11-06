/* tests/bad_sample_task.c — 反例样本：任务侧纪律违规集
 * 用途：validate_esp_generated.py 自测。本文件【故意】包含多处 VIOLATION/WARNING，
 * 运行自测时应全部被报出；禁止把本文件内容当作正确写法参考。
 * 正确范式见 references/freertos-on-esp32.md。
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_wifi.h"

static SemaphoreHandle_t data_lock;
static TaskHandle_t worker_task_handle;

/* 违规：任务函数里用 FromISR API */
static void sensor_task(void *arg)
{
    BaseType_t woken = pdFALSE;
    for (;;) {
        xSemaphoreGiveFromISR(data_lock, &woken);   /* 违规：任务上下文禁用 FromISR */
        portENTER_CRITICAL_ISR(&spinlock);          /* 违规：任务侧应为 portENTER_CRITICAL */
    }
}

/* 违规：硬件等待循环无超时（WARNING 级） */
static int wait_sensor_ready(void)
{
    while (i2c_device_poll_ready(dev_handle)) {
        /* 空转：没有超时与失败分支 */
    }
    return 0;
}

void app_main(void)
{
    /* 违规：栈 256 —— ESP32 栈单位是字节（STM32 words 惯性），2048 起步 */
    xTaskCreatePinnedToCore(sensor_task, "sensor", 256, NULL, 5, &worker_task_handle, 1);

    /* 违规：工程未见 nvs_flash_init 就 esp_wifi_init（跨文件核对失败） */
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    /* WARNING：nvs_set_* 之后未见 nvs_commit */
    nvs_handle_t h;
    nvs_open("cfg", NVS_READWRITE, &h);
    nvs_set_i32(h, "mode", 2);

    wait_sensor_ready();
}
