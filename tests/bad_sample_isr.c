/* tests/bad_sample_isr.c — 反例样本：中断纪律违规集
 * 用途：validate_esp_generated.py 自测。本文件【故意】包含多处 VIOLATION，
 * 运行自测时应全部被报出；禁止把本文件内容当作正确写法参考。
 * 正确范式见 references/isr-and-concurrency-rules.md。
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"

int shared_count = 0;                 /* 违规点：与 ISR 共享却未加 volatile */
volatile bool event_flag = false;

QueueHandle_t event_queue;

void button_isr_handler(void *arg)
{
    shared_count++;                   /* 违规：访问非 volatile 共享全局 */
    vTaskDelay(10);                   /* 违规：ISR 内阻塞延时 */
    printf("pressed\n");              /* 违规：ISR 内 printf */
    xQueueSend(event_queue, &shared_count, 0);   /* 违规：任务级 API，应为 xQueueSendFromISR */
    portENTER_CRITICAL(&spinlock);    /* 违规：ISR 内应为 portENTER_CRITICAL_ISR */
    portYIELD_FROM_ISR();             /* 违规：缺少 woken 参数 */
}

void ext_isr(void)
{
    event_flag = true;
    xTaskNotifyGive(worker_task_handle);   /* 违规：无 FromISR 版本，应置标志/用 vTaskNotifyGiveFromISR */
}

/* 旧示例遗留：ICACHE_RAM_ATTR 已废弃，应改 IRAM_ATTR */
static ICACHE_RAM_ATTR void legacy_isr(void)
{
    event_flag = true;
}

void app_main(void)
{
    gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    gpio_isr_handler_add(GPIO_NUM_0, button_isr_handler, NULL);
    attachInterrupt(digitalPinToInterrupt(4), ext_isr, FALLING);
}
