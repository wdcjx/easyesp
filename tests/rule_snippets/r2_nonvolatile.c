/* R2: ISR 访问非 volatile 全局 */
static int s_flag = 0;
void gpio_isr_handler(void *arg)
{
    (void)arg;
    s_flag = 1;               /* R2：非 volatile 共享 */
}
void app_main(void) { (void)s_flag; }
