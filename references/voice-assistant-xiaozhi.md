# 语音 AI 助手实战范式（xiaozhi-esp32）

> 何时读：做语音交互 / AI 对话盒子 / WebSocket 实时音频 / 唤醒词 / 板级工厂抽象 / 防变砖 OTA 时——架构范式、协议细节、安装构建、坑位速查。
> 状态：实战项目沉淀（源自已上板工程 `D:\ESP32project\xiaozhi-esp32-main\xiaozhi-esp32-main`，上游 github.com/78/xiaozhi-esp32；本文为源码转写，未在本机二次复测；esp-sr 模型清单等以官方仓库为准）。

## 0. 定位与安装（本地路径与命令）

- 定位（README_zh.md:11）：小智 AI 聊天机器人 = 语音交互入口 + Qwen/DeepSeek 大模型 + MCP 协议多端控制。支持 ESP32 / C3 / C5 / C6 / S3 / P4（S31 需 IDF 6.1+），**138 板卡目录 / 171 固件变体**。
- **IDF 硬门槛**：≥ v6.0.1，推荐 `release/v6.1` 分支，**不支持 5.x**（本机 D:\ESPIDE 的 5.3.1 编不了它）。勿用 `v6.1` 发布标签——C3 有 Wi-Fi 初始化失败（官方 issue #2344）。切 SDK 后：IDF 目录 `git submodule update --init --recursive` → 重新 export → 项目内 `idf.py fullclean`。
- **免开发环境烧录**：飞书教程 https://ccnphfhqs21z.feishu.cn/wiki/Zpz4wXBtdimBrLk25WdcXzxcnNS ；固件默认接 xiaozhi.me 官方服务器（注册免费 Qwen 实时模型），控制台 https://xiaozhi.me 。
- **源码构建命令**（AGENTS.md:51-71，build.py 封装 set-target/menuconfig/选板，会改本地 sdkconfig）：

```bash
source /path/to/esp-idf/export.sh
idf.py --version
python3 scripts/build.py --list-boards
python3 scripts/build.py <board-directory> --name <variant-name>
python3 -m unittest discover -s scripts/tests -v
```

- **Docker 构建**（基础镜像 `espressif/idf:release-v6.1`，产出 xiaozhi.bin / merged-binary.bin / build.log / manifest.json）：

```bash
docker build --platform linux/arm64 -f docker/firmware-builder/Dockerfile -t xiaozhi/firmware-builder:idf61-arm64 .
docker run --rm --platform linux/arm64 \
  -e FIRMWARE_BOARD_DIR=xmini/c3 -e FIRMWARE_BOARD_NAME=xmini-c3 \
  -e FIRMWARE_LANGUAGE=zh-CN -e FIRMWARE_WAKE_WORD=nihaoxiaozhi \
  -v "$PWD/output:/output" xiaozhi/firmware-builder:idf61-arm64
```

- 开发者文档：`docs/custom-board_zh.md`（自定义开发板）、`docs/mcp-usage_zh.md`（MCP 物联网控制）。

## 1. 应用架构与状态机

- 入口 `main/main.cc:14-29`：`app_main → nvs_flash_init（损坏则 erase 重试）→ Application::GetInstance().Initialize() → Run()`（永不返回）。
- 设备状态（`device_state.h:4-17`）：`kDeviceStateUnknown/Starting/WifiConfiguring/Idle/Connecting/Listening/Speaking/Notifying/Upgrading/Activating/AudioTesting/FatalError`。合法转换**集中一张表**（`device_state_machine.cc:42-106`）：Idle 可去 Connecting/Listening/Speaking/Notifying/Activating/Upgrading/WifiConfiguring；Listening⇄Speaking 互转、二者回 Idle；FatalError 只进不出；TransitionTo 原子更新 + 锁外回调。**所有状态变更必须经 Application::SetDeviceState**（AGENTS.md:32）——运行时状态出现表外路径即 bug。
- 事件驱动：FreeRTOS 事件组 MAIN_EVENT 位（`application.h:25-39`）：SCHEDULE / SEND_AUDIO / WAKE_WORD_DETECTED / VAD_CHANGE / ERROR / ACTIVATION_DONE / CLOCK_TICK / NETWORK_CONNECTED / DISCONNECTED / TOGGLE_CHAT / START|STOP_LISTENING / STATE_CHANGED / PLAYBACK_DRAINED / STARTUP_HINT_TIMEOUT；`Run()` 主循环 `xEventGroupWaitBits`（application.cc:186-301）；**多源回调统一 Schedule() 串行投递主任务**（AGENTS.md:33）——消锁竞争的关键纪律。
- 任务表：main（运行时提优先级 10，栈 8192=CONFIG_ESP_MAIN_TASK_STACK_SIZE）；audio_input 2048×3 prio8 pin core0；audio_output 2048×2 prio4；opus_codec 2048×12 prio2；AFE 处理任务 "audio_afe" prio3 栈 4096（**栈在 PSRAM**）；encode_wake_word 静态任务 prio2 栈 4096×6（custom 版 ×7）；activation 4096×2 prio2；MQTT 重连用 esp_timer 只在 Idle 态发起。

## 2. 通信协议（服务器下发配置 → WebSocket / MQTT+UDP）

- **协议选择**：开机 activation 任务先 HTTP POST OTA 接口，服务器响应里 `mqtt` / `websocket` 配置**整体写入 NVS**（ota.cc:159-199）；有 mqtt 配置→MqttProtocol，否则 websocket，都无→默认 MQTT（application.cc:556-575）。
- **OTA 上报**：url = `Settings("wifi").GetString("ota_url")` 否则 CONFIG_OTA_URL（默认 `https://api.tenclass.net/xiaozhi/ota/`）。HTTP 头：`Activation-Version`(1/2)、`Device-Id`=MAC、`Client-Id`=软件 UUID、`Serial-Number`=eFuse、`User-Agent="BOARD_NAME/版本"`。响应含 `activation{message,code,challenge,timeout_ms}`、`mqtt`、`websocket`、`server_time`（校时 settimeofday）、`firmware{version,url,force}`。
- **WebSocket**：hello 握手（websocket_protocol.cc:210-234）：

```json
{"type":"hello","version":3,"features":{"aec":false,"mcp":true},
 "transport":"websocket","audio_params":{"format":"opus","sample_rate":16000,
 "channels":1,"frame_duration":60}}
```

  文本消息带 session_id；type 词表：`listen{state:start/stop/detect, mode:auto|manual|realtime}`、`tts{state,start/sentence_start,text}`、`stt{text}`、`llm{emotion}`、`mcp{payload}`、`abort[reason:wake_word_detected]`、`system{command:reboot}`、`notify{audio_url,subtitles}`、`goodbye`。**120s 无下行判通道超时**。
- **二进制帧版本化**（protocol.h:19-33）：v1 裸 opus；v2 `packed{u16 version; u16 type(0=OPUS,1=JSON); u32 reserved; u32 timestamp; u32 payload_size; u8[]}`；v3 `packed{u8 type; u8 reserved; u16 payload_size; u8[]}`。
- **MQTT+UDP 双通道**：MQTT 承载控制（TLS 默认 8883），UDP 承载音频：16B 头 `|type 1u|flags 1u|payload_len 2u|ssrc 4u|timestamp 4u|sequence 4u|payload|`，AES-128-CTR（PSA Crypto；key/nonce 由服务端 hello 的 `udp{server,port,key,nonce}` hex 下发；nonce 字节 2-3=payload_len、8-11=timestamp、12-15=递增 sequence）。心跳 = MQTT keepalive（默认 240）+ 120s 通道超时。

## 3. 音频管线（AFE / Opus / 队列 / AEC）

- 引擎按芯片分派：**S3/P4/S31→AfeAudioEngine**（CONFIG_USE_AUDIO_PROCESSOR，`depends on (S3||P4||S31) && SPIRAM`）；**ESP32/C3/C5/C6→LiteAudioEngine** 独立 WakeNet（无 AFE 全家桶）。
- AFE 关键调用（afe_audio_engine.cc:116-195）：`afe_config_init(input_format("M"/"MR"), models_, AFE_TYPE_FD, AFE_MODE_LOW_COST)`；`aec_init = codec_->input_reference()`；`aec_mode=AEC_MODE_FD_LOW_COST`；`aec_nlp_level=AEC_NLP_LEVEL_VERYAGGR`；`ns_init=false`；`vad_init / VAD_MODE_0 / vad_min_noise_ms=100`；`wakenet_init`；`memory_alloc_mode=AFE_MEMORY_ALLOC_MORE_PSRAM`；`esp_afe_handle_from_config → afe_iface_->create_from_config`。模型：`esp_srmodel_init("model")` + `esp_srmodel_filter(ESP_WN_PREFIX/…)`；自定义唤醒词走 MultiNet（CustomWakeWord），阈值默认 20。独立 WakeNet：`esp_wn_handle_from_name → wakenet_iface_->create(model_name, DET_MODE_95)`。
- Opus：`esp_audio_codec` 的 `esp_opus_enc`；帧长 60ms、bitrate=ESP_OPUS_BITRATE_AUTO、APPLICATION_AUDIO、上行 16000Hz 单声道；服务器下发 24000/60 时仅告警不阻断（重采样失真风险点）。
- 定容队列（audio_service.h:40-46,189-193）：FixedQueue 编译期容量——send=40 包(2400ms)、decode=20 包(1200ms)、encode/playback task 各 2；**音频路径零运行期大分配 + 任务栈放 PSRAM**。
- 数据流：Mic→Codec(I2S)→AudioInputTask→Engine(AEC/VAD/WakeNet)→16k mono PCM→encode 队列→OpusCodecTask→send 队列→主循环 SEND_AUDIO→protocol；下行反向。**SEND_AUDIO 失败必须清空剩余队列，否则 Opus 任务等队列空间→整条输入管线死锁**（application.cc:253-258）。
- AEC 三态 `AecMode{kAecOff, kAecOnDeviceSide, kAecOnServerSide}`：device AEC 仅白名单板可选（S3-BOX 系列、Korvo2、Waveshare AMOLED 等，Kconfig.projbuild:1068-1081）；device 与 server AEC 同开直接 `#error`；AEC 关→AutoStop 听音、AEC 开→Realtime 全双工。唤醒词音频上传：最近 2 秒 PCM 存 64KB PSRAM 环形缓冲（CONFIG_SEND_WAKE_WORD_DATA 默认 y）。

## 4. 板级抽象（138 板卡的组织方式）

- `main/boards/common/board.h:46` `void* create_board()`；L87-90 `#define DECLARE_BOARD(BOARD_CLASS_NAME) {void* create_board(){return new BOARD_CLASS_NAME();}}`；L62-65 `Board::GetInstance()` 静态单例调工厂。纯虚接口：GetBoardType/GetAudioCodec/GetNetwork/StartNetwork/GetNetworkStateIcon/SetPowerSaveLevel/GetBoardJson/GetDeviceStatusJson；可选：GetDisplay/GetLed/GetBacklight/GetCamera/GetBatteryLevel/GetTemperature。`PowerSaveLevel{LOW_POWER,BALANCED,PERFORMANCE}`。每个构建变体只导出一个 DECLARE_BOARD；**禁止改已有板引脚（板身份影响 OTA 兼容）**（AGENTS.md:28-29）。
- 板目录三件套：`config.h`（引脚宏）+ `config.json`（`{"type","target","builds":[{name,sdkconfig_append}]}`）+ 板 `.cc`（以 DECLARE_BOARD 结尾）。
- bread-compact-wifi 引脚示例（config.h:14-19,31-38,57）：simplex mic WS=4/SCK=5/DIN=6；spk DOUT=7/BCLK=15/LRCK=16；BOOT=0、TOUCH=47、VOL±=40/39；OLED SDA=41/SCL=42；LED=48。esp32-s3-box-3：ES8311+ES7210 MCLK=2/BCLK=17/WS=45/DOUT=15/DIN=16/PA=46（AUDIO_INPUT_REFERENCE=true 走 AEC）。
- **加新板四步**（AGENTS.md:43-47）：①复制板目录写三件套；②Kconfig.projbuild 加 `config BOARD_TYPE_X depends on <target>`；③main/CMakeLists.txt 加 `elseif(CONFIG_BOARD_TYPE_X) set(BOARD_DIR ...)`（BOARD_TYPE 必须匹配 `^[a-z0-9.-]+$`，CMakeLists.txt:993-995）；④`python3 scripts/build.py <board-dir> --name <variant>`。

## 5. OTA 防变砖与激活

- 版本检查：ActivationTask→CheckVersion 循环 MAX_RETRY=10、10s 起指数退避；`IsNewVersionAvailable` 按点分十进制逐段比较，**解析失败一律视为无更新**（防降级/升级死循环，ota.cc:439-465）；`firmware.force=1` 强制升级。
- 升级流程（ota.cc:280-406）：HTTP 流式读、4KB 页 buffer（内部 RAM）、**先攒够 esp_app_desc_t 镜像头再 `esp_ota_begin(OTA_WITH_SEQUENTIAL_WRITES)`**→`esp_ota_write`→`esp_ota_end`（校验失败报 ESP_ERR_OTA_VALIDATE_FAILED）→`esp_ota_set_boot_partition`→重启。
- 回滚：`CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`；启动联网成功后 `MarkCurrentVersionValid` 在 `ESP_OTA_IMG_PENDING_VERIFY` 时 `esp_ota_mark_app_valid_cancel_rollback`；factory 分区跳过标记。升级前停音频服务、失败恢复音频 + LOW_POWER 继续运行。
- 激活：有 eFuse 序列号时 Activation-Version=2——`esp_hmac_calculate(HMAC_KEY0, challenge)` 出 HMAC-SHA256，POST `{algorithm:"hmac-sha256", serial_number, challenge, hmac}` 到 `<ota_url>/activate`；202→重试（上限 10）；普通激活码走语音逐位播报 0-9 ogg。

## 6. Settings（NVS 封装）与设备标识

- `main/settings.cc`：NVS 轻封装——构造 `nvs_open(namespace)`，**析构 dirty 才 `nvs_commit`**；GetString/SetString/GetInt(i32)/SetBool(u8)/EraseKey/EraseAll。已知命名空间：`wifi/ota_url`、`mqtt/{endpoint,client_id,username,password,keepalive,publish_topic}`、`websocket/{url,token,version}`、`assets/download_url`。**NVS 键是持久 API，改动需迁移**（AGENTS.md:36）。
- 设备标识（system_info.cc:35-57）：Device-Id = MAC 小写冒号（以太网板读 ESP_MAC_ETH、P4 走 esp_wifi_remote）；Client-Id = 软件 UUID；User-Agent = BOARD_NAME/版本。

## 7. sdkconfig 与分区要点

- defaults：COMPILER_OPTIMIZATION_SIZE、异常/RTTI 关、BOOTLOADER_APP_ROLLBACK_ENABLE、FLASH 16MB+`partitions/v2/16m.csv`、MAIN_TASK_STACK 8192、WDT 10s、**CONFIG_UART_ISR_IN_IRAM=y（修 ML307 FIFO 溢出）**、WiFi 静态 RX=6/动态=8 省内存、LVGL 大量 widget 裁剪。
- S3：SPIRAM OCT 80M、SPIRAM_MALLOC_ALWAYSINTERNAL=1024、MALLOC_RESERVE_INTERNAL=102400、指令 cache 32KB/数据 cache 行 64B、LVGL 内建 TLSF 1MB PSRAM 池（8MB 板在 lcd_display.cc 加池；无 PSRAM 变体由 build.py 切回 CLIB malloc）。
- 分区 `partitions/v2/16m.csv`：nvs 0x4000@0x9000、otadata 0x2000@0xd000、phy_init 0x1000@0xf000、ota_0 0x3F0000@0x20000、ota_1 0x3F0000、**assets spiffs 8M**（字体/表情/唤醒词模型网络更新）。4m.csv 只有 factory 无 OTA 槽；16m_c3 assets 4000K（C3 mmap 页数限制）。
- 依赖（idf_component.yml 摘要）：idf>=6.0.1、espressif/esp-sr==2.4.7、esp_audio_codec~2.5.0、esp_codec_dev~1.6.2、78/esp-wifi-connect~3.3.1、78/esp-ml307~3.8.1、lvgl~9.5.0、espressif/button~4.2.1、led_strip~3.0.3、esp32-camera^2.1.7(S3) 等，按 target rules 条件引入。

## 8. 可复用模式清单（迁到别的 ESP32 项目）

1. 板级工厂三件套（config.h/config.json/DECLARE_BOARD）+ CMake BOARD_TYPE 正则校验；
2. 状态机合法转换集中一表、单入口变更；
3. 事件位主循环 + Schedule 串行化（多源回调零锁竞争）；
4. 定容音频管线（FixedQueue + 静态栈 + PSRAM）；
5. 双传输抽象（Protocol 接口 + 版本化二进制帧 + hello/goodbye 协商、服务器下发配置入 NVS）；
6. 防变砖 OTA（先验镜像头→顺序写→pending_verify 回滚→解析失败拒升级）；
7. 资产分区化（固件与字体/模型分离，HTTP 更新）；
8. NVS namespace 封装（dirty 跟踪 + 析构 commit）；
9. PowerSaveLevel 三档策略 + 音频电源定时器；
10. MCP 工具前置排列利用服务端 prompt cache；设备状态 JSON 统一 GetDeviceStatusJson 供 AI 查询。

## 9. 坑位索引（详见 known-pitfalls.md）

#62 IDF 5.x 编不过｜#63 4M flash 无 OTA 槽｜#64 无 PSRAM 板唤醒卡死｜#65 发送失败不清队列→管线死锁｜#66 板型/引脚错乱｜#67 无 AEC 硬件唤醒不了｜#68 WebSocket 连不上（配置下发链）｜#69 device+server AEC 互斥｜#70 4G 事件任务内再发送死机｜#71 MCP 工具静默丢弃
