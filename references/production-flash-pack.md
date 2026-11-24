# production-flash-pack — 量产烧录分发包解剖（ESP32-C3 + W25Q32 实例）

> 何时读：要给一块裸机/成品板做**出厂烧录分发包**（合并镜像+烧录工具+操作教程），或遇 ESP32-C3 GPIO11 不能当 IO、efuse 解锁、Flash Download Tool 量产批烧、电池设备烧录保持供电、烧录日志审计时。
> 状态：实战档。源样本=「固件、烧录工具、操作教程」分发包（无线音频收发器 WiFiScan v1.0，作者 hgszh@outlook.com，固件 2023-05-17 / arduino-esp32 2.0.x / IDF 4.4.2-dirty 时代，含三份真实烧录日志），bin 已逐字节验尸、教程 docx 已转写；未上板复测。命令与 efuse 语义以 Espressif 官方文档为准。

## 1. 分发包解剖（一个可照抄的交付结构）

```
固件、烧录工具、操作教程/
├─ w25q32 固件.bin          # 合并全镜像 551,952B（0x0 起，见 §2）
├─ 操作教程.docx             # 面向产线操作员（§5 全文转写）
└─ 烧录工具/
   ├─ flash_download_tool_3.9.3.exe
   ├─ bin/                  # 四件套分件烧录备选：bootloader/partitions/boot_app0/WiFiScan.ino.bin + 地址.txt
   ├─ configure/esp32c3/    # FDT 板级配置（multi_download.conf 等，§4）
   ├─ doc/                  # FDT 中英文 PDF 手册
   ├─ logs/<MAC>.txt        # 每次烧录留痕（文件名=芯片 MAC）
   └─ dl_temp/*.bin_rep     # FDT 烧录暂存副本（会话残留，可删）
```

设计意图：产线工人只需要「装上 USB-TTL → 按教程点软件 → 看进度条」；镜像、地址、时序、芯片选型全部由包作者锁定。

## 2. 合并全镜像布局（0x0 单文件烧录）

| 偏移 | 内容 | 证据 |
|---|---|---|
| 0x0 | bootloader（13936B 版本另附），`E9` 镜像头 + 入口 0x403CE000（C3 IRAM） | 头 8 字节 `E9 03 02 2F` |
| 0x8000 | 分区表（`AA 50` magic）：**nvs 0x9000/0x6000 → phy_init 0xF000/0x1000 → factory 0x10000/0x100000** | 逐条解析 |
| 0xE000 | boot_app0（otadata 复位态，全 0xFF=下次起从 factory 启动） | dump 全 FF |
| 0x10000 | app（486KB），esp_app_desc：project "main"、ver "1"、May 17 2023、**v4.4.2-dirty** | 0x10020 处 0xABCD5432 |

- **量产最小分区表纪律**：三区（nvs/phy_init/factory 1MB），无 OTA 无 spiffs——出厂镜像没有 OTA 上升空间，后续升级只能现场重烧；这是「无网络、无升级诉求」产品 的合理选择，反之要留 ota_0/ota_1。
- 合并镜像 vs 四件套（bin/ 目录+地址.txt：0x0 / 0x8000 / 0xe000 / 0x10000）：合并镜像防呆（一个文件一个地址 0x0）；四件套便于单独升级 app。镜像头 `spi_mode=DIO` 与教程让选 FDT「QIO 80MHz」并存——FDT 的 flash_freq/flash_mode 配置为 `keep` 时以镜像头为准，教程的选择是对**镜像头之外的控制器参数**下指令，两头不一致时以 esptool 实际下发为准（hedge：以 FDT 手册为准）。
- 固件功能实证（strings）：页面 Transceiver/Radio/Config TX Audio/Others；AMIC/LINE 输入、Au Gain ±12dB 六档、ALC、Bass、MONO；ST7735S SPI 屏（TFT_eSPI/GFX 系初始化日志串）；AutoPowerOff/poweron_minutes/Last Power-On 用电统计；rssi 检测。即一块**带屏无线音频收发器**。

## 3. C3 GPIO11 = VDD_SPI：efuse 解锁（本包最重的知识点）

- **事实**：ESP32-C3 的 GPIO11 复位默认是 **VDD_SPI 电源输出脚**（给 SPI flash 供 3.3V），不是普通 IO。
- 本板 flash 已由板上电源供电，GPIO11 被设计接**发射机功放的 LDO 使能**——必须先把 GPIO11 从电源职责里解锁：
  ```
  pip install esptool
  espefuse.py -p COMx burn_efuse VDD_SPI_AS_GPIO 1
  # 提示后输入 BURN 确认
  ```
- **不可逆**：eFuse 一次性熔断，烧错无法恢复（烧完 VDD_SPI 不再供电，若板上 flash 恰好靠它供电=变砖）。烧前必须确认硬件供电来源。
- 时序：教程安排在烧录固件**之后**做（保持烧录连线不动，直接 espefuse 走同一串口）。
- 我们的坑清单侧写：C3「GPIO11–17 内置 flash 占用」只讲了引脚禁区，没讲 GPIO11 可经 efuse 释放为 IO（本包实证），已补坑 #216/#217。

## 4. Flash Download Tool 3.9.3 量产事实（configure/esp32c3/*.conf）

| 配置 | 值 | 含义 |
|---|---|---|
| ESPTOOL_PARAM.chip | auto | 自动识别（也能防选错板） |
| baud | 115200 | 保守波特率：552KB 压缩后 27.8s（有效 158.6kbit/s）；线材/夹具差时稳，好线可提 921600 |
| flash_freq/mode/size | keep | 跟随镜像头，不在工具层覆盖 |
| after / before | no_reset / default_reset | DTR/RTS 复位节奏 |
| DOWNLOAD | com_port1..8 + checkmac | **8 串口批烧位**（本包未用，单口手点） |
| EFUSE CHECK | efuse_mode=1, halt=1 | efuse 校验失败即停线 |
| MAC SAVE / LOG_CHECK | False / AT+GMR 风格 | 日志校验出厂版本号 1.0.0（本包关闭） |

日志留痕格式（logs/&lt;MAC&gt;.txt）：连接波特率 → DEVICE SYNC → **MAC（高低 16bit）** → **flash JEDEC id** → 写入字节/压缩率/耗时/有效带宽 → Hash verified → PASS/FAIL + 总耗时。三份日志实证两块不同 MAC（60:55:F9:… 与 7C:DF:A1:B8:D2:8x）与两种 Winbond 片：**0xEF4016=W25Q32（4MB）、0xEF4017=W25Q64（8MB）**——JEDEC 对号是烧录日志里免费拿到的 BOM 审计数据。

## 5. 操作教程全文转写（产线 SOP 模板，措辞照抄含笔误）

A. 烧录：USB 转 TTL 烧录器；①烧录器 TXD→板 RXD、RXD→板 TXD；②烧录器 DTR、DTS（**笔误：应为 RTS**）→板 DTR、DTS；③板子上**焊一个负极排针**接烧录器 GND。打开 flash_download_tool_3.9.3.exe → 选 ESP32-C3 → 导入「w25q32 固件.bin」→ 勾选、地址 0x00、80MHz、QIO → 选端口号、115200。**正式烧录前用排针帽短接开机按钮旁两个排针使板子保持通电**→ Start → 绿进度条走完即成功。重启键 + 长按 ON/OFF 进主界面。**先别拆杜邦线，还要解锁 GPIO11。**

B. 解锁 GPIO11（原理照抄）：C3 的 GPIO11 默认 3.3V 输出给 spiflash 供电而非普通 IO；本板 spiflash 已有供电，而**发射机功放的 LDO 使能脚接 GPIO11**，需解锁为 IO 控制功放启停。保持连线，CMD 里 `pip install esptool` → `espefuse.py -p COM* burn_efuse VDD_SPI_AS_GPIO 1` → 输入 BURN → 解锁成功可当普通 IO。

SOP 值得抄的三点：给操作员的每一步都是「动作+预期结果」句式；硬件改动（焊排针）写进步骤而不是备注；高风险不可逆步骤（efuse）独立成节并解释**为什么**。

## 6. 烧录硬件手法清单

| 手法 | 适用 |
|---|---|
| DTR+RTS 两根都接（auto-reset 进 bootloader） | 免按 BOOT 键烧录；只有 TX/RX/GND 时须手按 BOOT+EN |
| 带电源按键的电池板：短接专用排针保持通电 | 本板不短接则烧到一半断电 |
| 量产接地：焊负极排针而非夹子 | 夹地易接触不良，烧录失败率高 |
| JEDEC id 对号 + MAC 记录 | 日志自动留 BOM 与 SN 追溯 |

## 7. 纪律对照（对到本 skill 既有体系）

- 分区表纪律（esp-idf-basics）+ 量产无 OTA 取舍（production-readiness §OTA 铁律反过来用：本产品**故意**无 OTA）。
- 烧录排障（known-pitfalls 工具链类 #31–35）补：FDT 量产位/efuse 检查/日志审计三个工厂侧手段。
- C3 引脚禁区表（gpio-pinout-guide）补 GPIO11 的 efuse 释放路径（§3）。
- 教程「DTR/DTS」笔误=文档笔误传染坑（同 #155 家族：给机器看的字段人类照抄）。

## 8. 可复用模式与坑位索引

1. 分发包=固件+工具+教程+日志四件闭环，交付即产线可复制（本包结构可照抄）。
2. 合并镜像 0x0 单文件烧录防呆，分件镜像留升级通道，两者同发。
3. espefuse burn_efuse VDD_SPI_AS_GPIO 1（C3 释放 GPIO11，先确认板上 flash 供电来源）。
4. FDT 日志=免费的 BOM/时间/结果审计，文件名用 MAC 即 SN。
5. 产线 SOP 写法：动作+预期结果、硬件改动入步骤、不可逆操作独立成节讲原理。
6. 烧后验尸命令组（免费质检）：读 JEDEC id、读 efuse、读 app_desc 版本，三连对上才放行。

坑位索引：#216–223（known-pitfalls.md「量产烧录/分发类」）。
