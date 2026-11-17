# 任务书：ESP32-C3 BLE HID 键盘

> 何时读：技能评测用（见 evals/README.md），非面向最终用户的功能需求文档。
> 状态：静态测试输入。仅按本任务书实现，不引入任务书之外的假设。

## 需求（用户原话风格）

我有一块 ESP32-C3 开发板（Arduino 框架），想做一个 BLE 无线键盘：板上 BOOT 键
（GPIO9）按一下发字符 'a'，按住超过 1 秒发左箭头键。电脑（Windows）配对一次
以后能自动重连，断电再上电不用重新配对。

## 平台与约束

- 芯片：ESP32-C3；框架：Arduino（arduino-esp32 3.x）+ NimBLE-Arduino（Bluedroid
  HID 键盘库在 3.x 已不可用——若交付用 BleKeyboard/Bluedroid 即 FAIL）。
- 单 .ino 即可；BOOT 键输入上拉；MANIFEST V1（gpio: 9 func: button）。
- 交付前自检：validator 0 VIOLATION。

## 行为清单（人工核对）

1. NimBLE 初始化 + HID 设备（0x1812）+ 键盘报告（usage 0x08 / report ref）；
   HID 报告描述符为标准 8 字节键盘。
2. BOOT 键 GPIO9 INPUT_PULLUP，去抖（非 delay 阻塞）；短按→keyPress('a')+notify；
   长按 1s→左箭头 usage 0x50，松开发空报告。
3. 断连回调里重启广播（advertising start）——只 start 不 restart 即坑位 #125 家族。
4. bonding：安全参数开 bonding（SEC_PAIR|MITM 可关），断电重连不重配对。
5. 键扫描不阻塞 loop()（millis/任务节拍），loop 内无 while(1)。

## 必查规则（validator + 坑位）

- R11（Arduino loop 纪律）、R1（若用中断方式读键，ISR 需 IRAM_ATTR+volatile）、
  M2/M4（GPIO9 属 C3 合法编号且须入 MANIFEST）。
- 坑位：#36–53 段（BLE 断连不重启广播/notify 尺寸）；#129（C3 无 touchRead）。

## 判定

0 VIOLATION + 行为清单 5/5 = PASS；用 Bluedroid 键盘库、断连不重广播、loop 阻塞
任一即 FAIL（记录到 ROADMAP）。
