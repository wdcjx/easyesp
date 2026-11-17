/* R10: WiFi 先于 NVS */
#include "esp_wifi.h"
void app_main(void)
{
    esp_wifi_init(NULL);      /* R10：全工程未见 nvs_flash_init */
}
