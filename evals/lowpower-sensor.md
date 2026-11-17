# 任务书：电池低功耗温度节点（深睡 + 定时采集）

> 何时读：技能评测用（见 evals/README.md），非面向最终用户的功能需求文档。
> 状态：静态测试输入。仅按本任务书实现，不引入任务书之外的假设。

## 需求（用户原话风格）

用 ESP32 做个电池供电的温度采集节点：每 10 分钟醒一次，读 ADC（接了个 NTC，
分压电阻 10k），把温度通过 Wi-Fi 发到一个 HTTP 接口就回去睡觉。要求一节
18650 尽量撑得久，唤醒不用按任何键。

## 平台与约束

- 芯片：ESP32（经典）；框架：ESP-IDF 5.3.x。
- 单文件 main.c；MANIFEST V1（NTC 所接 ADC 通道对应 GPIO 按引脚表填写）。
- 交付前自检：validator 0 VIOLATION。

## 行为清单（人工核对）

1. 定时唤醒用 RTC 定时器：`esp_sleep_enable_timer wakeup(10*60*1000*1000ULL)`；
   不要求 ext0/ULP（任务书没给按键）。
2. 每次唤醒走完整 boot（深睡后 RAM 不保），采集→发送→`esp_deep_sleep_start()`；
   采集前 `esp_wifi_start` 连接，发完 `esp_wifi_stop` 再睡。
3. ADC 用 oneshot 新驱动（esp_adc/adc_oneshot.h + 校准），多次采样取均值，
   NTC 换算用 Beta 公式（25℃/3950，按任务书给定分压参数，hedged 标注）。
4. HTTP 发送带总超时（esp_http_client timeout 配置或手动 esp_timer 界限），
   连不上最多重试 2 次就去睡（不能因 Wi-Fi 不在耗干电池）。
5. 无 NVS 需求可不写；但若写 NVS 参数须 nvs_flash_init 先行。

## 必查规则（validator + 坑位）

- R7（等待循环须超时）、R9（若建任务栈字节单位）、R5 家族（ISR 纪律，若用
  ADC 连续采样中断）。
- 坑位：power-and-sleep.md（停 Wi-Fi 再睡/深睡前外设 deinit 顺序）；
  #82–93 段（量产类：耗电毛刺与看门狗）。

## 判定

0 VIOLATION + 行为清单 5/5 = PASS；深睡前不停 Wi-Fi、HTTP 无超时、忙等任一即
FAIL（记录到 ROADMAP）。
