# blink_uart_demo（ESP-IDF 5.3.x）

> 何时读：想看"按 easyesp 纪律写出来的最小完整工程长什么样"时打开。
> 状态：知识沉淀示例（未上板实测；API 对齐 ESP-IDF 5.3.x，以官方文档为准）。

最小完整 IDF 工程：板载 LED 非阻塞闪烁 + UART 日志。演示
templates/main_idf.c 的软定时器表 + 让出循环范式在一个真实工程布局中的样子。

构建烧录（先激活 IDF 环境，见 references/esp-idf-basics.md）：

    idf.py set-target esp32        # S3/C3 换 esp32s3 / esp32c3
    idf.py build flash monitor

自检：`python scripts/validate_esp_generated.py examples/blink_uart_demo --dir examples`，
本工程应 0 VIOLATION。
