# POV 裸眼 3D 风扇屏（ESP32-S3 全息风扇广告机）

> 何时读：要做 POV（视觉暂留）旋转显示、LED 风扇屏、大规模 WS2812 阵列 + 步进电机同步、或「设备在 NAT 后用第三方 MQTT 云做手机遥控」的架构时读本文。
> 状态：知识沉淀（源自开源工程 3-d-bare-eye-fan-screen v1.0，作者已上板运行并有 B 站演示 BV1tN411y7ZS；本文为源码转写，未二次上板；原工程 IDF 4.4.4，迁移段对齐 ESP-IDF 5.3.x 官方文档）。

## 1. 系统定位与硬件架构

商用「全息风扇广告机」的开源学生复刻（2023，GPL-3.0）：旋转 4 臂 WS2812 灯带靠视觉暂留成像，同步播 wav 音乐，手机 Web APP 云端遥控。

| 部件 | 选型 | 关键参数 / 引脚 |
|---|---|---|
| 主控 | ESP32-S3 N16R8 | 240MHz 双核，16MB flash + 8MB **Octal PSRAM**（sdkconfig：SPIRAM_MODE_OCT + SPIRAM_USE_MALLOC） |
| 旋转驱动 | TMC2209 + 步进电机 | PUL=GPIO5 / DIR=GPIO4 / EN=GPIO3 / MS1=16 / MS2=15 / SPRD=8 / DIAG=7 / INDEX=6 / KEY=GPIO0 |
| LED | WS2812 ×4 臂×20 灯（1615 封装） | GPIO 40/39/38/41，RMT 通道 0–3 |
| 音频 | MAX98357A I2S 功放 3W | BCK=48 / WS=45 / DO=47（legacy I2S0） |
| 调光/功率 | GPIO46 LEDC 20kHz | duty 250/1023，用途源码未注明（推断 LED 供电或电机功率 MOS，以原理图为准） |

控制面：手机 H5（jQuery + mqtt.js，`wss://plant.qinzr.top:8017/mqtt`，打包成安卓 APP）↔ 第三方公网 MQTT broker ↔ ESP32（`mqtt://plant.qinzr.top:1883`）。设备不暴露公网端口——**瘦终端 + 第三方云中转**是 NAT 环境零成本遥控的实用架构；代价见 §9 安全清单。ESP32 本地另有 HTTP 服务（8080，/writefile 等）用于同网段大文件上传。

## 2. POV 数据模型（本文核心资产）

**几何**：一圈 = 200 个角坐标（`a_p` 0–199），半径 80 像素（外圈半径方向），4 条灯臂互成 90°（角坐标偏移 50）。一幅画 = 200 列 × 80 半径 × RGB。

**内存布局**：`ledData = malloc(200*80*3)`（48,000B，PSRAM）：列 i 行 j 的像素在 `ledData[i*240 + j*12 + 臂序*3 + 色序]`——每列 240B = 20 个半径点 × 4 臂 × 3 色（灯带只点 20/80 个半径采样）。

**极坐标映射**（PC 与固件共用同一公式，160×160 直角坐标源图）：

```c
int32_t port = ((int32_t)(-sin(i/31.831)*j+80)*160 + (int32_t)(cos(i/31.831)*j) + 80);
// i/31.831: 0..199 → 0..2π；j: 半径 0..79；port: y*160+x
```

**渲染**：`led_task`（核 1，prio 8）每收到一次二值信号量，按当前 `a_p` 给 4 臂各写 20 像素：`strip1@a_p、strip2@(a_p+100)%200、strip3@(a_p+150)%200、strip4@(a_p+50)%200`（对臂 180°、邻臂 90°），然后 4 条 `refresh`。刷新与列节拍靠二值信号量节流，自然丢拍——POV 显示容忍丢拍但依赖转速恒定。

## 3. 步进开环同步 + 软起动（可复用范式）

无霍尔、无编码器、无 Index 中断（GPIO6 留了未用）——**位置完全由步进脉冲数推算**：

```c
static bool IRAM_ATTR timer_group_isr_callback(void *args) {   // 100kHz（10µs 周期）
    GPIO.out_w1tc = (1 << STEP_PUL);      // 直写寄存器（GPIO<32，比 gpio_set_level 快）
    num++;
    if (num % speed == 0) {               // speed=分频除数：越大越慢
        num1++;
        GPIO.out_w1ts = (1 << STEP_PUL);
        if (num1 % 8 == 0) {              // 8 脉冲 = 1 个角坐标
            a_p = (a_p + 1) % 200;
            xSemaphoreGive(ctrl_task_sem); // 唤醒渲染
        }
    }
    return high_task_awoken == pdTRUE;
}
```

软起动：主循环 `if(speed1>12) speed1 = speed1*0.9; speed=speed1;`（每 100ms ×0.9，从 100 斜坡到 12）——步进电机直接高速起步会失步，指数斜坡是最简惯用解。`open_btn` 重新置 `speed1=100` 从头爬坡。注意 `timer_interval_sec` 形参名撒谎：实传 10 × TIMER_SCALE(40MHz) = 400 tick = 10µs，是原始 tick 不是秒（坑 146）。

TMC2209 要点：ENN **低有效**（EN=1 反而脱机）；MS1=MS2=0 全步进； StealthChop 静音（README 选型理由：不干扰旁边放音乐）。S3 strapping 引脚被大量占用：GPIO0(KEY)/3(EN)/45(WS)/46(PWM)，启动电平须与外设需求兼容。

## 4. WS2812 四通道 RMT

原工程 vendored 2019 版 `led_strip` 组件（`led_strip_init(channel, gpio, num)` 老 API），并**魔改了 `refresh`**：注释掉 `rmt_wait_tx_done`，`rmt_write_sample(..., false)` 非阻塞——否则 4×20 灯 ×30µs/bit 的串行等待会拖死列节拍。S3 RMT 恰好 4 个 TX 通道，4 臂正好用满。组件的时序 tick（t0h/t1l_ticks）是**全局变量被 4 带共享**——本工程同 clk_div=2 侥幸无害，不同分频即互相破坏（坑 148）。

IDF 5.3 迁移：官方 `espressif/led_strip` managed component，`led_strip_new_rmt_device()` + RMT_CLK_SRC_DEFAULT，四条各配一个 `led_strip_rmt_config_t`（`.flags.invert_out=false`、`resolution_hz`），天然并行无共享 tick。

## 5. JPEG 显示链（esp_rom_tjpgd ROM 解码器）

零依赖方案：ESP32 ROM 内置 TJpgD，`#include "esp_rom_tjpgd.h"`，3100B 起 work buffer（本工程 3500B）。文件流式输入（不整读进内存）：

```c
static uint32_t infunc(esp_rom_tjpgd_dec_t *d, uint8_t *buf, uint32_t len) {
    JpegDev *jd = (JpegDev *)d->device;
    return buf ? fread(buf, 1, len, jd->fp)          // 正常读
               : (fseek(jd->fp, len, SEEK_CUR) ? 0 : len); // buf==NULL=跳过
}
static uint32_t outfunc(esp_rom_tjpgd_dec_t *d, void *bitmap, esp_rom_tjpgd_rect_t *rect) {
    // 按 rect 增量块拷到 outData（解码器分块回调，不是一次整图）
    unsigned char *in = bitmap, *out = jd->outData + ((jd->outW * rect->top) + rect->left) * 3;
    int bws = 3 * ((rect->right - rect->left) + 1), bwd = 3 * jd->outW;
    for (int y = rect->top; y <= rect->bottom; y++) { memcpy(out, in, bws); in += bws; out += bwd; }
    return 1;
}
// prepare(分配 work,绑 infunc) → decomp(绑 outfunc, scale=0)
```

解码完再跑 §2 极坐标公式映射到 ledData。**picture 模式按源码实际是坏的**：亮度缩放 `jd.outData[port*3]*(j+3)/300` 在 C 里是整数除法，j≤79 时 (j+3)/300 恒 0 → 全黑（坑 139）；PC 侧 Python 原型 `(j+3)/300` 是 float 除法再 int()——同一公式两种语言语义不同，移植即坏。另注意 `outData` 固定 `malloc(160*160*3)` 且 outW/outH 写死 160，上传非 160×160 图会越界写（坑 151）；错误码容忍表里 `JDR_FMT1` 被放行是特例别照抄。

## 6. 视频与音频链

**视频离线预解**（关键架构决策）：PC 端 OpenCV（`程序/Python程序/opencv.ipynb`）把 mp4 逐帧 → 直角转极坐标 → 每帧 48000B，串接成大文件 `imgarrays`（≤80 帧≈3.7MB）上传到 littlefs。固件 `video_task` 每 20ms `memcpy(ledData, ledDatas+48000*i, 48000)` 逐帧喂——**把极坐标映射和亮度缩放全部移出 MCU**，ESP32 只做 memcpy，S3 + PSRAM（ledDatas 4.8MB 只能落 PSRAM）扛住 50fps。对比：JPEG 实时解码路径（§5）则把同一逻辑放在 MCU 上跑。

**音频**：legacy `driver/i2s.h`，44100/16bit/mono(ONLY_LEFT)/MSB，`i2s_write(0, music_data+44, music_Size-44, ...)` 整段一次性写。+44 假定标准 WAV 头；采样率写死 44100，上传 8kHz 的 wav 会 5.5 倍快放（坑 152）。IDF 5.3 迁移：`driver/i2s_std.h`（`i2s_new_channel` + `i2s_channel_init_std` + `i2s_channel_write`）。`music_task` 只在 `is_video=1` 时播——音乐与视频模式强耦合是设计如此。

## 7. 云端控制面（topic 表 + 大载荷陷阱）

| topic（/qinzr2/ 前缀） | 方向 | 载荷 | ESP32 行为 |
|---|---|---|---|
| open_btn | APP→ESP | "1" | 切换 STEP_EN（电机启停）+ speed1=100 重爬坡 |
| next_pic_btn / last_pic_btn | APP→ESP | "1" | page_num±1，置 is_page_change |
| pic_btn / video_btn | APP→ESP | "1" | is_video=0/1（图/视频模式，兼音乐开关） |
| image_esp | APP→ESP | JPEG 二进制 | 写 /littlefs/000N.jpeg + 触发解码 |
| image_phone | ESP→APP | JPEG 二进制 | 切图时回发当前图，APP base64 预览 |
| light | APP→ESP | on/off | 空实现（模板残留） |

**大载荷陷阱**（坑 142/143）：esp-mqtt 默认 `buffer_size=1024`，>1KB 消息分多个 `MQTT_EVENT_DATA` 事件送达（`current_data_offset`/`total_data_len` 标注分块）。本工程忽略分块字段、每个事件里 `fopen(path,"w")+fwrite(event->data,event->data_len)`——每个分块都重新打开文件覆盖写，最终文件只剩最后 1KB 分块，**MQTT 传图链路按源码必然损坏**；且 `event->data_len` 是全消息长时还会堆越读。正确做法：按 `current_data_offset==0` 开文件、追加写、`current_data_offset+len==total_data_len` 关文件；或调大 `mqtt_cfg.buffer.size`。可靠传大文件走同网段 HTTP `/writefile`（100B/块循环 `httpd_req_recv` → `fwrite`），但那要求手机与设备同 LAN——与云遥控初衷矛盾，生产方案应是 MQTT 分块重组或 HTTPS 下载。

## 8. 存储与分区

```
# partitions_two_ota_fat.csv（名字与内容严重不符：无双 OTA、无 FAT）
nvs 0x4000 / otadata 0x2000 / phy 0x1000 / factory app 1500K / littlefs(subtype=spiffs) 6M
```

littlefs 挂载 `format_if_mount_failed=true`：**全新 flash 首启格出空文件系统，`/littlefs/imgarrays`、`/littlefs/music.wav` fopen 返回 NULL，代码全程不检查 → fread(NULL) 崩在 app_main**（坑 140）。`123.wav` 455KB 经 `EMBED_FILES` 链进 app 分区但只活在注释代码里（坑 153）。`fread(ledDatas+48000*video_page,...)` 读帧循环用 `while(!feof(f))` 先判后读，EOF 多计一帧，`video_task` 里 `for(i<video_page-2)` 的魔法 -2 就是补偿（坑 141）。大 malloc（music 2MB / ledDatas 4.8MB / ledData 48KB）依赖 `SPIRAM_USE_MALLOC`，`SPIRAM_MALLOC_ALWAYSINTERNAL=16384` 保证小对象留内部 RAM——换无 PSRAM 芯片直接死。

## 9. 安全清单（真实威胁，不是理论）

- broker 地址+账号密码明文进固件源码，同一账号密码还预填在 APP 登录框（`index.html` value= 属性，页面源码即泄露）——公网上任何人订阅/发布同 topic 即可遥控你的电机（坑 145）。
- `/readfile?name=../../nvs` 类路径穿越零过滤（sprintf 直拼 `/littlefs/%s`）；`/delfile` 可删任意路径；全部接口 CORS `*` 且无认证（坑 144）。
- WiFi 凭据硬编码（"wifi"/"12345678"）。
- 最小整改：一机一密（参考 micropython-env-controller.md §7 TuyaLink 的 HMAC 方案）、topic 带设备随机 ID、HTTP 接口加 token 校验、`name` 白名单化（`[0-9]{4}\.jpeg` 正则）。

## 10. IDF 4.4 → 5.3 迁移线

| 4.4 写法（本工程） | 5.3 对应 |
|---|---|
| `esp_event_loop_init(my_event_handler,…)` + `system_event_t` | `esp_event_loop_create_default()` + `esp_event_handler_register(WIFI_EVENT/IP_EVENT,…)` |
| `tcpip_adapter_init()` | `esp_netif_init()` + `esp_netif_create_default_wifi_sta()` |
| `driver/i2s.h` 全家 | `driver/i2s_std.h`（channel API） |
| `driver/timer.h` `timer_isr_callback_add` | `driver/gptimer.h`（`gptimer_register_event_callbacks`） |
| `driver/rmt.h` + vendored led_strip 组件 | `espressif/led_strip` managed component（`led_strip_new_rmt_device`） |
| `ledcSetup` 风格 legacy LEDC driver | LEDC 仍可用，S3 只有 `LEDC_LOW_SPEED_MODE`（本工程已正确） |

## 11. 纪律对照（对照 ISR/并发硬规则）

合格面：ISR 内直写 `GPIO.out_w1tc/w1ts`（避开函数调用开销）、ISR 返回 yield 布尔、任务全 `xTaskCreatePinnedToCore` 指定核、软起动斜坡、大缓冲全 PSRAM。
违规面：ISR 100kHz 里跑 `num%speed` 非幂二模除（240MHz 下可用但费 CPU，可改递减计数器）；`decode_task` 与 `video_task` 并发写 `ledData` 无互斥（切图瞬间撕裂）；`page_num--` 到 0/负数无下限钳位；HTTP/MQTT 回调里 fopen/fwrite 阻塞 IO；`led_strip_init` 里 `static led_strip_t *pStrip` 无意义的静态局部指针。

## 12. 可复用模式

1. **步进开环 = 位置传感器**：恒速旋转场景下脉冲计数替代编码器，ISR 里数脉冲给坐标，成本为零（失步即图像漂移，启动斜坡防失步是前提）。
2. 二值信号量做「每列一拍」节拍器：ISR give、渲染任务 take，天然丢拍容忍。
3. **重计算离线化**：极坐标映射/亮度缩放放 PC 预处理，MCU 退化为 memcpy 播放器——凡是「格式固定的帧流」都值得这么做。
4. tjpgd 文件流式解码：infunc 的 `buf==NULL → fseek` 分支是跳过不需要数据的协议约定，比整读省一倍内存。
5. 第三方公网 MQTT broker 当免费中继：手机与设备互访零端口映射——只适用于玩具，商用见 §9。
6. EMBED_FILES 塞资源进固件：改文件必须重刷固件，只适合 bootloader 级资产；用户数据一律走文件系统。

## 13. 坑位索引

图片全黑=整数除法（139）；首启必崩=空 FS 裸 fopen（140）；feof 多读+魔法-2（141）；MQTT 分块被忽略传图必坏（142/143）；路径穿越（144）；账密三处泄露（145）；ISR 模除+参数名义不符（146）；上下拉同开（147）；魔改组件全局 tick 共享（148）；BGR 疑似换序（149）；文件名 000%d vs 0010 漂移（150）；JPEG 尺寸/体积上限未检（151）；wav 速率/头假设（152）；455KB 死重嵌入（153）。详见 known-pitfalls.md #139–153。
