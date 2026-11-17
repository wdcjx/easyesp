/* R12: legacy 驱动 API（WARN 级） */
#include <driver/i2c.h>
void app_main(void)
{
    i2c_param_config(0, ((void *)0));   /* R12：IDF 5.2+ 用 driver/i2c_master.h */
}
