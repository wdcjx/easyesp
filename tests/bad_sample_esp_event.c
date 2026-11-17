/* BAD 样本（第 12 个，锁定铁律 B 对 esp_event 处理器的检测）：
 * esp_event_handler_register 的 handler 是第 3 个实参，
 * esp_event_handler_register_with 的是第 4 个实参。
 * 旧版正则抓到的是事件 ID（WIFI_EVENT_STA_START），检测空转——本样本锁死该回归。 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_wifi.h"

static void evt_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    vTaskDelay(1000);   /* VIOL：处理器跑在 esp_event 任务上下文，禁阻塞 */
}

void app_main(void)
{
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_START,
                                               evt_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register_with(esp_event_loop_get_default(),
                                                    IP_EVENT, IP_EVENT_STA_GOT_IP,
                                                    evt_handler, NULL));
}
