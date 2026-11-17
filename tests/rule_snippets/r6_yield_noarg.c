/* R6: portYIELD_FROM_ISR 缺参数 */
void i2c_isr_handler(void *arg)
{
    (void)arg;
    portYIELD_FROM_ISR();     /* R6：必须传入 woken */
}
void app_main(void) { }
