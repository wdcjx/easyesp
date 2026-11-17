/* R4: ISR 用任务级 API（存在 FromISR 版本） */
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
static SemaphoreHandle_t s_sem;
void uart_isr_handler(void *arg)
{
    (void)arg;
    xSemaphoreGive(s_sem);    /* R4：必须改用 xSemaphoreGiveFromISR */
}
void app_main(void) { s_sem = xSemaphoreCreateBinary(); }
