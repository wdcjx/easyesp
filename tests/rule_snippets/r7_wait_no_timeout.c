/* R7: 硬件等待循环无超时（WARN 级） */
extern int sensor_ready(void);
void app_main(void)
{
    while (sensor_ready() == 0) { }   /* R7：未见超时与失败分支 */
}
