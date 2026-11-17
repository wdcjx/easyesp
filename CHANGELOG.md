# 更新日志

格式：面向技能使用者与贡献者的变更摘要；工程级细节见 ROADMAP.md 各轮沉淀表。

## 1.1.0（2026-11-17）

工程化加固轮（源自外部审查 + m03292 优先级清单）：

- **新增实战文档 4 份**（25→29 份，坑 165→203 条）：Wi-Fi NAT 中继路由
  （esp32s3-wifi-relay，#166–173）、IoT 浇水控制器（esp32-watering，#174–187）、
  IDF 轨摄像头图传（esp-idf-camera，#188–193）、力反馈旋钮与 LVGL 圆屏
  （super_knob，#194–203）；症状速查映射同步扩至 #1–203。
- **技能自更新**：SKILL.md 新增「自更新」节——agent 定位安装目录后三层更新
  （git pull --ff-only 带重试 / `npx skills update`（skills CLI 原生，读
  skills-lock.json）/ DSH 技能库重装），更新后汇报版本变化。
- **validator v1.1.0**：规则稳定 ID（R1–R15 纪律类 / M1–M6 MANIFEST 类 / R99 输入类）+
  `--format json` 结构化输出（validator_version / result / findings[{file,line,level,rule,message}]）。
- **跨文件聚合检查**：M5 同一 GPIO 被多个文件声明占用、M6 target 芯片冲突（多组件工程引脚
  冲突此前单文件视角不可见）。
- **规则级单测** tests/run_rule_tests.py：每条规则一个最小片段（R1–R15/M1–M6 共 21 例），
  断言命中规则 ID、无 R0（消息措辞与 RULE_TABLE 失配立即报警）、result 符合预期。
- **修复三缺陷**（外部审查实证）：esp_event/esp_http_client 处理器注册完全漏检阻塞违规
  （实参级解析）；不存在的文件名静默跳过改为可见 WARNING；读失败警告被覆盖吞掉。
- **CI 基线扩至 15 条目**：十二单文件样本 + manifest_ok（跨文件 PASS）+
  project_conflict（M5）/ target_conflict（M6）目录条目 + 规则级单测。
- **供应链**：三个 workflow 的 actions 全部钉 commit SHA（arduino/setup-arduino-cli 的
  `@v2` 实为浮动分支——已钉 v2.1.0 提交）；.gitattributes 统一行尾（Windows CRLF rebase
  冲突根治）。
- **evals/**：四份静态技能测试任务书（Wi-Fi 重连+NVS / BLE HID / 低功耗深睡传感器 /
  RS-485 Modbus 轮询），每份含可核对行为清单与必查规则。
- SKILL.md frontmatter 增加 `version:`（与 CHANGELOG 对应）。

## 1.0.0（2026-11-11）

首个正式发行（Release https://github.com/wdcjx/easyesp/releases/tag/v1.0.0）：

- 25 份 references 领域文档、165 条实战坑清单、症状速查全量映射（#1–165）。
- 双轨框架（ESP-IDF 5.3.x 主 / Arduino 3.x 副）+ MicroPython 商用范式；三芯片
  （ESP32/S3/C3）。
- validator 静态纪律检查（16 类规则 + MANIFEST 引脚声明核对 M 系列）。
- CI：静态一致性回归（ci_check.py）+ 真实编译（build.yml：espressif/idf:v5.3.1 三目标
  idf.py build + arduino-cli 三板编译）。
- 实战文档 12 份（已上板源工程转写）；Traffic Record 每日流量记录。
