/* R3: ISR 调用无 FromISR 版本的 API */
void timer_isr_handler(void *arg)
{
    (void)arg;
    vTaskDelay(2);            /* R3：无 FromISR 版本，中断内禁延时 */
}
void app_main(void) { }
