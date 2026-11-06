---
name: 🐛 Bug 反馈
about: 文档 API 写错 / validator 误报漏报 / 坑清单修法不对 / 模板编译不过
title: ''
labels: bug
assignees: ''
---

## 哪个文件、哪一段

<!-- 例：references/peripheral-recipes.md §4 I2C 新驱动的 i2c_master_transmit_receive 参数顺序；
     或 scripts/validate_esp_generated.py 对 xxx 报了误报。附相对路径 + 行号/章节号。 -->

## 环境（涉及上板问题时必填）

- 芯片/模组：<!-- 例：ESP32-WROOM-32 / ESP32-S3-N8 / ESP32-C3-MINI -->
- 框架与版本：<!-- 例：ESP-IDF 5.3.1 / arduino-esp32 2.0.11 / 3.x -->
- 构建方式：<!-- idf.py / PlatformIO / Arduino IDE -->

## 现象（实际发生了什么）

<!-- 文档写法编译报错？贴错误原文。上板不符合预期？贴 monitor 日志（含 Guru Meditation 全文更好）。 -->

## 期望/正确写法

<!-- 按哪个官方文档/版本核对应当怎么写；有实测结论更佳。 -->

## 最小复现（可选但强烈建议）

```c
// 贴最小代码或步骤
```

## 已排查 known-pitfalls.md 哪几条

<!-- 例：已对照 #26（NVS 先于 WiFi）、#49（PubSubClient 256B）——不适用/已排除。 -->
