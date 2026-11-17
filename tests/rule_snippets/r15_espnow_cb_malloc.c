/* R15: 任务上下文回调内堆操作 */
#include <stdlib.h>
#include "esp_now.h"
static void on_recv(const uint8_t *mac, const uint8_t *data, int len)
{
    (void)mac; (void)data;
    char *p = (char *)malloc(len);   /* R15：回调路径禁止堆操作 */
    (void)p;
}
void app_main(void) { esp_now_register_recv_cb(on_recv); }
