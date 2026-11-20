# retrogo-s3-handheld — 多模拟器掌机固件（retro-go on ESP32-S3 + ST7789V）

> 何时读：要做游戏掌机/多 App 分区固件、SPI 屏高性能显示管线（脏行+缩放+滤波）、I2S 外部 DAC 音频、I2C 扩展手柄、SDMMC 1-bit、或评估「一个固件多个独立应用」的 OTA 分区切换架构时。
> 状态：实战档。源工程 retro-go 1.41（ducalex，GPL-2.0，IDF 4.2–5.2 支持、上游主线 4.3）下载副本含 ESP32-S3 双目标（esplay-s3 完整板级 + esp32s3-devkit-c 最小板级），作者已上板；本文按所读源码转写，未二次复测；API 对齐 IDF 4.x/5.x 交界（大量 legacy 驱动，见 §9 迁移）。

## 1. 源工程定位

- 形态：launcher（菜单/浏览/主题/Web 文件管理器/固件更新器）+ 每个模拟器一个独立 app 分区（retro-core 目录下 main_nes.c / main_gbc.c / main_snes.c / main_sms.c / main_pce.c / main_lynx.cpp / main_gw.c…共享 shared.h），launcher 也是其中一个 app。支持的系统：NES/SNES(慢)/GB/GBC/G&W/SG-1000/SMS/MD(慢)/GG/ColecoVision/PCE/Lynx/DOOM/MSX。
- 每个核心各自编译为独立镜像，靠 OTA 分区切换互跳（§2），不是单进程多核心。
- 显示/音频/输入/存储/设置抽成 `components/retro-go`（rg_*.c 约 6.4K 行），按 `targets/<board>/config.h` 宏配置编译。
- 构建：`make TARGET=esplay-s3`（env.py 设 IDF_TARGET=esp32s3 / FW_FORMAT=esplay），产物 .fw（odroid/esplay 引导器格式）或 .img；tools/mkfw.py 打包；上游文档明言可能需要给 IDF 打 sdcard-fix / panic-hook 补丁。

## 2. 多 App 分区架构（本工程最有复用价值的骨架）

| 机制 | 事实 |
|---|---|
| 应用切换 | `rg_system_switch_app(partition, name, args, flags)`：NVS 写 boot name/args/flags → `esp_ota_set_boot_partition(esp_partition_find_first(APP, ANY, partition))` → restart |
| 回 launcher | `RG_BOOT_ONCE` 标志：app 启动时若置位，立即 `esp_ota_set_boot_partition(launcher)`（下次重启自动回菜单）；崩溃重启也会落回 launcher |
| 参数传递 | 跨 app 无共享内存，全靠 NVS `NS_BOOT` 命名空间（boot name/args/flags）+ 重启 |
| .fw 兼容 | `CONFIG_PARTITION_TABLE_MD5=n`（odroid 分区表无校验）、`CONFIG_APP_BUILD_BOOTLOADER=n`（引导器由 .fw 容器自带） |
| 更新器 | launcher/updater.c 从网络下载固件到 `/odroid/firmware`（G32 板是 `/espgbc/firmware`） |
| WebUI | launcher/webui.c 用 esp_http_server 做 SD 卡文件管理器（RG_ENABLE_NETWORKING 门控） |

纪律对照：这是「固件=多合一菜单 + 独立小应用」的参考实现；比起单进程塞全部功能，每个 app 独享全部 RAM/flash，代价是切换要重启。

## 3. S3 目标硬件事实（targets/esplay-s3/config.h，94 行全量要点）

| 域 | 配置 |
|---|---|
| 屏 | ST7789V 320×240（`RG_SCREEN_WIDTH/HEIGHT`），SPI2_HOST 80MHz，MOSI=12 CLK=48 CS=8 DC=47 BCKL=39 RST=3，MISO=NC |
| 板级屏调谐 | `RG_SCREEN_INIT()` 追加 ST7789V 专用序列：VCOM 0xC5=0x1A、MADCTL 0x36=0x60（MX+MV=横屏）、Porch 0xB2、Gate 0xB7、VCOM 0xBB=0x3F、0xC0/0xC2/0xC3/0xC4 电源链、帧率 0xC6=111Hz、0xE0/0xE1 gamma 双曲线 |
| 存储 | SDMMC `SDMMC_HOST_SLOT_1` 1-bit：CMD=14 CLK=21 D0=17（SDMMC_FREQ_DEFAULT 20MHz） |
| 音频 | 仅外部 I2S DAC（INT_DAC=0）：BCK=38 WS=13 DATA=9，功放使能 GPIO18 |
| 输入 | I2C 扩展芯片 0x20（SDA=10 SCL=11，400kHz）8 键位图 + 本机 L=40 R=41 MENU=42；**OPTION 也=41（与 R 同脚）** |
| 电池 | ADC1_CHANNEL_3 分压 ×2，3500–4200mV 线性百分比 |
| LED | GPIO2 |
| 对照 | `esp32s3-devkit-c` 是最小带机：SDSPI(SPI3)+40MHz 屏+无板级 init+GPIO 直读手柄（driver 7）——新板移植的起点模板 |

## 4. 显示管线（rg_display.c，872 行）

- **SPI 队列架构**：`spi_task`（核 1，优先级 7）+ 10 事务队列 + 5 个 DMA 缓冲池（`rg_alloc(MEM_DMA)`）；`pre_cb` 按 `t->user` 位打 DC 线；缓冲用完由 spi_task 回收回队列。`lcd_get_buffer()` 2.5s 拿不到就 `RG_PANIC("display")`。
- **初始化三层**：①RST 脉冲 100ms 低/10ms 等待；②通用序列（注释明言借自 jobitjoseph/retro-go-ST7789：0x3A=0x55 RGB565、0x21 反色、0xCF/0xED/0xE8/0xCB/0xF7/0xEA/0xC0/0xC1/0xC5/0xC7/0x36=0x08/0xB1/0xB6/0xF6/0xF2/0xE0/0xE1、0x11 退出睡眠、0x29 开显示）；③目标板 `RG_SCREEN_INIT()` 再压一遍板级调谐（§3）。宏名叫 `ILI9341_CMD` 但实际驱动 ST7789V——命令地址两屏大量重叠，序列按 ST7789 手册语义写的。
- **脏行更新**：每行 32 位 checksum（`screen_line_checksum[]`），只重发变化的行；重复行（缩放产生的 SAME 行）用 `memcpy` 复制上一行进 DMA 缓冲。
- **缩放/滤波**：`map_viewport_to_source_x/y[]` 预计算查表做任意缩放（custom_zoom 0.1–2.0）；x 滤波只在相邻映射同源列时 blend，y 滤波对 REPEATED 行上下 blend；`blend_pixels` 用位技巧 RGB565 快速均值（byte-swap + 0xF7DE/0x0821 掩码）。
- **像素格式**：RENDER_LINE 宏三分支——调色板（8bit 索引查表）、565LE（byteswap）、565 直拷。
- **背光**：LEDC 13-bit 5kHz + fade（50ms 渐变），init 时 0% 防开机白屏闪。窗口函数 0x2A/0x2B/0x2C 带边界校验 LOGW。
- **帧节流**：display_task 用长度 1 的队列 peek+receive——生产者新帧直接覆盖旧帧（天然丢帧节流），收到 `(void*)-1` 退出。

## 5. 音频（rg_audio.c，416 行，legacy driver/i2s.h）

- 外部 DAC：I2S_NUM_0 master TX、16bit、I2S_CHANNEL_FMT_RIGHT_LEFT、STAND_I2S、dma_buf_count=4 × dma_buf_len=180（**单位是立体声样本=4 字节**，约 800 样本目标注释）；`use_apll=true` 仅经典 ESP32（S3 无 APLL，靠分数 PLL）。
- 内部 DAC（仅经典 ESP32，S3 编译期 `#error` 拒绝）：**差分单声道技巧**——左右通道发 0x8000±sample，外部用减法器还原，把 8bit DAC 拼成等效 16bit 分辨率。
- 提交路径：本地 180 帧栈缓冲分块 `i2s_write(..., 1000ms)`；音量软件乘法（0–100%）；静音=volume 0。Dummy sink 用 `rg_usleep(count/sampleRate)` 假装节拍。
- 生命周期：deinit 逐 pin `gpio_reset_pin` + 卸驱动 + 关功放；设备锁用长度 1 的队列模拟（ACQUIRE/RELEASE 宏）。
- 每帧统计 busyTime 进 sysmon 性能计数器。

## 6. 输入（rg_input.c + rg_i2c.c）

- esplay-s3 手柄：I2C 0x20 **无寄存器 5 字节裸读**，键位 = `~((data[2]<<8)|data[1])` 低 16 位 active-low；data[0]/[3]/[4] 弃用（esplay-micro 兼容布局）。I2C 读失败→当帧无键，无错误上抛。
- 本机键 GPIO_PULLUP_ONLY 直读（L/R/MENU/OPTION）。
- 组合键虚拟化：无 MENU 键的板子 SELECT+START=MENU、SELECT+A=OPTION（编译期 `RG_GAMEPAD_HAS_*_BTN` 门控）。
- 防抖：移位寄存器连续 2 次采样（debounce_level=0x03）；input_task 独立任务。
- rg_i2c.c 用的还是 **legacy i2c_param_config/i2c_driver_install**（400kHz 主机）。

## 7. 存储（rg_storage.c）

- esplay-s3：SDMMC 1-bit（`SDMMC_HOST_FLAG_1BIT` + `slot_config.width=1`）；**S3 关键差异 `SOC_SDMMC_USE_GPIO_MATRIX`——SDMMC 引脚不再是固定 IO_MUX 脚，可任意 GPIO**（本板 14/21/17），d1/d3 显式 -1。
- 挂载失败降级重试：仅 TIMEOUT/INVALID_RESPONSE/INVALID_CRC 三类错误才降到 `SDMMC_FREQ_PROBING` 再试一次，其余错误直接判失败。
- `do_transaction` 钩子注入 LED 闪烁（磁盘活动灯）；FATFS LFN heap 模式 max LFN 255、max_files=8；挂载点 /sd。
- 五种后端编译期切换：Host(桌面)/SDSPI/SDMMC/USB/Flash(wear levelling)。

## 8. 系统层（rg_system.c，1327 行）

- **内存分区**：`rg_alloc(size, caps)`——MEM_SLOW→SPIRAM、MEM_FAST→INTERNAL、MEM_DMA→DMA caps（可组合）；启动打印 内部/外部 双堆统计。
- **无 PSRAM 处置**：`lowMemoryMode = (totalMemoryExt==0)`，弹窗「External memory not detected——Boot will continue but it will surely crash...」后**仍然继续跑**（模拟器帧缓冲必然放不进内部 RAM）。
- **panic 链**：`RTC_NOINIT_ATTR panic_trace_t` 存 RTC 内存，重启后写 /sd/crash.log（配合可选 IDF panic-hook 补丁逐字符截获 panic 输出）；addr2line 用 xtensa-esp32-elf-addr2line。
- **超频（危险区）**：`rg_system_set_overclock(level -4..+3)` 直写 **BBPLL ROM I2C 寄存器**（`rom_i2c_writeReg(0x66,...)`，ENDIV5/BBADC_DSMP/DIV/LREF/DCUR，480M 档），代码注释明言「None of this is documented by espressif」，首次调用先保存基准值、level 0 恢复。菜单里的实验功能。
- sysmon 任务（3KB 栈）巡检内存/性能计数器；sdkconfig：`FREERTOS_HZ=100`、TASK_WDT off、INT_WDT on、assert=SILENT、编译 SIZE 优化（注释：assert ENABLE 多 50K 放不下 2.5MB 目标）、`SPI_MASTER_IN_IRAM=y`（显示中断路径）。

## 9. 迁移与纪律对照（对 IDF 5.3 的落差）

| 本工程做法 | IDF 5.3 现状 |
|---|---|
| driver/i2s.h（i2s_driver_install/i2s_set_pin/i2s_write） | legacy，5.2+ 弃用；新驱动 i2s_std.h（本库 validator R12 家族命中） |
| i2c_param_config/i2c_driver_install | legacy；新驱动 i2c_master.h |
| dac_output/dac_i2s（内部 DAC 差分） | 经典 ESP32 专属，S3/C3 无 |
| CONFIG_ESP32_* 前缀 sdkconfig（S3 目标也这么写） | 4.x 时代通用前缀，5.x 分化为 CONFIG_ESP32S3_* |
| esp_ota_set_boot_partition 切 app | 仍然正路（官方 OTA 分区机制） |
| heap_caps 分区分配 | 正路，本 skill freertos 文档同款纪律 |

纪律对照：显示管线=「DMA 池+队列+脏行」三件套可移植到任何高帧率 SPI 屏项目；音频 chunk 提交与设备锁模式同 §5；多 App=OTA 分区切换，NVS 传参。本工程被 validator 命中的点（legacy 驱动/阻塞等待）多数是「上游 1.41 立足 IDF4.x」的历史包袱，抄架构别抄 API。

## 10. 可复用模式

1. SPI 屏三件套：事务队列任务+DMA 缓冲池+脏行 checksum（比整帧重发省一个数量级带宽）。
2. 目标板 config.h 宏覆盖：通用驱动 + `RG_SCREEN_INIT()` 板级调谐钩子，同构多板一线代码。
3. display_task 单帧队列 peek/receive：生产者覆盖式丢帧，天然背压。
4. 差分单声道（仅经典 ESP32 内部 DAC）；外部 DAC 永远更省心。
5. 挂载失败降速重试（仅限超时/CRC/无响应类错误）。
6. 多 App OTA 切换 + RG_BOOT_ONCE 自动回菜单 + NVS boot args。
7. RTC_NOINIT panic trace 落 SD 卡：现场设备排障不需要接串口。

## 11. 坑位索引

204–215（本 skill known-pitfalls.md「掌机/多 App 模拟器类」）：驱动宏名与实屏不符、set_rotation 写错 NVS 键、OPTION/R 共脚、I2C 手柄静默失败、SDMMC d1/d3 显式关、降速重试错误码白名单、无 PSRAM 强行继续、BBPLL 裸寄存器超频、TLS 全跳过、OTA 切换依赖 NVS 一致性、legacy 驱动全家、dma_buf_len 单位是立体声样本。

## 12. 自检清单（做同类项目时）

- [ ] 屏驱动宏/注释与实屏型号一致？init 序列来源注明？
- [ ] SPI 缓冲全部 DMA caps？事务回收闭环？
- [ ] NVS 键名与语义一一对应（复制粘贴 setter 检查）？
- [ ] 无 PSRAM 时是优雅降级还是「必崩继续」？
- [ ] OTA 分区切换失败路径（找不到分区）有 PANIC？
- [ ] 所有「未文档化寄存器」操作有恢复路径与风险标注？
