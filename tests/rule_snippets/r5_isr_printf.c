/* R5: ISR 内 printf */
void spi_isr_handler(void *arg)
{
    (void)arg;
    printf("isr\n");         /* R5：中断内禁止 printf */
}
void app_main(void) { }
