/* R13: RS-485 手动 DE 时序 */
#include "driver/uart.h"
#include "driver/gpio.h"
#define RS485_DE_PIN 4
void rs485_send(const char *buf, int len)
{
    gpio_set_level(RS485_DE_PIN, 1);
    uart_write_bytes(UART_NUM_1, buf, len);
    gpio_set_level(RS485_DE_PIN, 0);   /* R13：未 wait_tx_done 就拉低 DE */
}
void app_main(void) { }
