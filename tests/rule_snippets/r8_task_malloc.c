/* R8: 任务路径动态内存（WARN 级） */
#include <stdlib.h>
void app_main(void)
{
    for (int i = 0; i < 3; i++) {
        char *p = (char *)malloc(64);   /* R8：周期路径禁堆 */
        (void)p;
    }
}
