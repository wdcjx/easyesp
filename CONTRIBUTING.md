# 贡献指南

欢迎反馈与共建。本仓库是给 AI agent 用的 ESP32 知识技能，一切内容以**准确、可编译、可复查**为先。

## 两条贡献路径

1. **开 Issue**（最省事）：
   - 🐛 [Bug 反馈](https://github.com/wdcjx/easyesp/issues/new?template=bug_report.md)：文档 API 写错、validator 误报/漏报、坑清单修法不对、模板编译不过。
   - 📦 [工程沉淀建议](https://github.com/wdcjx/easyesp/issues/new?template=knowledge.md)：你有实测过的工程模式/坑位，建议收进 references/。
2. **直接 PR**：改动遵守下面的规范，自测过了再提。

## 文档写作规范（references/ 与 SKILL.md）

- **受众是 AI agent**：表格化、密度优先；中文行文，API/代码/路径保持英文原文。
- 每份文档开头两行引用块：
  - `> 何时读：…`（触发条件，供 agent 路由）
  - `> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）`——有实测后如实更新。
  - 源自实测工程的文档用实战档写法：`> 状态：实战项目沉淀（源自**已上板工程**「项目名」，源工程在真实硬件运行；本文为源码转写、未在本机二次复测…）`。**仓库约定：用户提供的沉淀工程默认已上板**，按实战档声明，不写「未上板实测」。
- **代码必须完整可编译**，API 名称逐字准确；不确定的写「以官方文档为准」，**严禁编造**。
- 数值只给手册典型值并标注来源（datasheet/TRM/官方文档版本）。
- 单文件 5–10KB（peripheral/wifi 类 8–12KB，known-pitfalls 上限 12KB）；超了就拆主题。
- 新文件统一 **UTF-8 无 BOM**；引用仓库内文件用相对路径，定位用「相对路径 + 行号/章节号」。

## 坑清单格式（references/known-pitfalls.md）

表格行，一条一行：

```markdown
| N | 【分类】症状（用户能看到的现象/日志关键词） | 根因（一句话机理） | 修法（可执行的动作/代码要点） |
```

- 编号从 1 连续递增，不重号不跳号（CI 会查）。
- 症状写"现象"而不是写"错误用法"；修法写到能直接照做。

## validator 纪律（scripts/validate_esp_generated.py）

- 改规则或改样本后必须同步：
  1. `tests/` 下的反例/正例样本与规则一一对应；
  2. `scripts/ci_check.py` 的 `BASELINE` 表更新为新计数（逐文件实测，不是拍脑袋）；
  3. 本地跑 `python scripts/ci_check.py` 全绿再提交。
- 新增规则的汇报文案要写清楚「为什么」（机理一句话），面向没踩过坑的读者。
- 检查器只用 Python 标准库，不引第三方依赖。

## 提交前自测

```bash
# validator 基线
python scripts/validate_esp_generated.py tests/bad_sample_isr.c tests/bad_sample_task.c tests/bad_sample_ble.cpp tests/manifest_bad_sample.c  # 应 FAIL
python scripts/validate_esp_generated.py templates/main_idf.c tests/good_sample_ble.cpp tests/manifest_good_sample.c examples/blink_uart_demo/main/blink_uart_demo.c examples/arduino_blink_uart/arduino_blink_uart.ino  # 应 PASS

# CI 全量回归（与 GitHub Actions 完全一致）
python scripts/ci_check.py
```

## Commit 风格

中文一句话说清做了什么，正文列要点。例：`沉淀三个实战项目：BLE HID / 实时控制 / IoT 网关`。

## License

提交即表示同意以 [MIT](LICENSE) 授权发布。
