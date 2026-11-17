# 任务书：RS-485 Modbus 主机轮询从站

> 何时读：技能评测用（见 evals/README.md），非面向最终用户的功能需求文档。
> 状态：静态测试输入。仅按本任务书实现，不引入任务书之外的假设。

## 需求（用户原话风格）

ESP32-S3 通过一块 MAX485 接了 3 个 Modbus RTU 从站（地址 1/2/3，9600 8N1），
帮我写个主机程序每 500ms 轮询每个从站的保持寄存器 0x0000 起 2 个寄存器，
CRC 帮我算好，读到的值存到全局数组里给别的任务用。485 芯片的 DE/RE 接在
GPIO4。

## 平台与约束

- 芯片：ESP32-S3；框架：ESP-IDF 5.3.x。
- 单文件 main.c；MANIFEST V1（uart tx/rx 引脚 + gpio: 4 func: rs485_de）。
- 交付前自检：validator 0 VIOLATION。

## 行为清单（人工核对）

1. 方向二选一并说明取舍：A 硬件 RS485（uart_set_mode UART_MODE_RS485_HALF_DUPLEX，
   RTS 脚接 DE）；B 手动 GPIO4——发送前置 DE、`uart_wait_tx_done` 后再拉低（顺序错
   即截尾）。
2. 帧构造：ADDR|0x03|0x00|0x00|0x00|0x02|CRC_L|CRC_H（CRC16 Modbus 多项式 0xA001，
   低字节在前，附实现或表驱动均可）。
3. 轮询任务 500ms 节拍（vTaskDelay/软件定时器），逐从站请求-响应，响应带
   timeout（uart_read_bytes timeout 或字节间隔判帧），超时/坏 CRC 记数不重启。
4. 共享数组 volatile + 临界区或队列（若别的任务读）；无符号 u16 解释，
   无符号扩展坑（#110）。
5. 无忙等轮询烧 CPU；单字节间判断不依赖固定 1ms delay 粗估（#106/#124 家族）。

## 必查规则（validator + 坑位）

- R13（uart_write_bytes 后必须 uart_wait_tx_done 才拉 DE——本任务核心考点）、
  R7（等待超时）、R5（若用事件中断收）。
- 坑位：#116–124 段全部；modbus-rtu-485.md §2 速查表。

## 判定

0 VIOLATION + 行为清单 5/5 = PASS；手动 DE 无 wait_tx_done、CRC 字节序颠倒、
忙等任一即 FAIL（记录到 ROADMAP）。
