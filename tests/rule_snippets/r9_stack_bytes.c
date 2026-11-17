/* R9: 栈深度单位是字节 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static void worker(void *arg) { (void)arg; }
void app_main(void)
{
    xTaskCreate(worker, "worker", 256, NULL, 2, NULL);   /* R9：<512 VIOL */
}
