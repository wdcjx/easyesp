/*
 * bad_sample_rs485.c —— RS-485 DE 时序 + legacy 驱动 API 反例
 *
 * R13：手动 DE 方向控制，uart_write_bytes 后未 uart_wait_tx_done 就拉低 DE
 *      （write_bytes 只是入队返回，末尾字节还没移出——坑 #120 截尾帧）
 * R12：legacy i2c 驱动 API（IDF 5.2+ 应改 driver/i2c_master.h 新驱动，坑 #101）
 *
 * 期望：FAIL  V=1（R13） W=1（R12）
 */
#include "driver/uart.h"
#include "driver/gpio.h"
#include <driver/i2c.h>

#define RS485_DE_PIN GPIO_NUM_4

static void rs485_send(const char *buf, int len)
{
    gpio_set_level(RS485_DE_PIN, 1);          /* 进入发送态 */
    uart_write_bytes(UART_NUM_1, buf, len);
    gpio_set_level(RS485_DE_PIN, 0);          /* R13：字节还在 TX FIFO 里就拉低 DE */
}

static void legacy_i2c_init(void)
{
    int port = I2C_NUM_0;
    i2c_config_t conf = {0};
    i2c_param_config(port, &conf);            /* R12：legacy i2c API */
    i2c_driver_install(port, I2C_MODE_MASTER, 0, 0, 0);
}

void app_main(void)
{
    char msg[8] = "AB";
    rs485_send(msg, 2);
    legacy_i2c_init();
}
