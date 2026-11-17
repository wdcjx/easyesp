/* R14: esp_event 处理器内阻塞（esp_event 静默失效回归样本） */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
static void evt_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    vTaskDelay(1000);   /* R14：处理器跑在 esp_event 任务上下文 */
}
void app_main(void)
{
    esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_START, evt_handler, NULL);
}
