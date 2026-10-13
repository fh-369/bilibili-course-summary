---
name: bilibili-course-summary
description: 输入B站课程视频链接，自动下载指定分P、转写逐字稿、智能识别PPT画面，生成结构化Markdown学习笔记。Use when 用户发来B站课程链接（含?p=页码）要求总结、提取笔记、整理课程内容，或需要批量处理B站合集多个分P。
---

# B站课程视频智能总结

## Overview

输入B站课程链接，自动完成：下载指定分P → 转音频 → 飞书妙记转写逐字稿 → 智能画面变化检测抽帧 → PPT画面识别 → 生成Markdown学习笔记。每个分P输出独立文件夹，包含视频、音频、逐字稿、总结笔记和PPT截图。

## When to Use

**触发条件：**
- 用户发来B站视频链接（`bilibili.com/video/BVxxx`），要求总结、提取笔记、整理内容
- 用户要求批量处理B站合集的多个分P
- 课程类视频有PPT/板书，需要同时获取口播内容和视觉信息

**不适用：**
- 需要登录/大会员才能看的视频
- 纯直播录像（无PPT，画面变化无规律）
- YouTube等其他平台
- 用户只要下载视频不要总结

## 环境依赖

运行前确认：
- Python 3.10+，已安装 `av`(PyAV)、`pillow`、`curl_cffi`
  - 安装命令：`python -m pip install av pillow curl_cffi`
  - **注意**：必须用 `python -m pip`，直接 `pip` 可能装到别的 Python
- 已安装并授权 `lark-cli`（飞书命令行工具）
  - 验证：`lark-cli minutes +search --format json`（返回参数错误而非未授权，即代表已登录）

详细配置见 [references/setup.md](references/setup.md)。

## Core Process

### Step 1：解析分P列表
- 从URL中解析 `?p=页码` 参数（**必须解析，不能默认第1集**）
- 调用B站API `x/player/pagelist` 获取所有分P的cid和标题
- 定位目标分P

### Step 2：下载视频
- 调用B站播放API获取CDN直链
- 下载MP4到输出目录（默认480P）

### Step 3：转音频
- 用PyAV提取音频，转MP3

### Step 4：飞书妙记转写
- `lark-cli drive +upload` 上传音频到云空间
- `lark-cli minutes +upload` 创建妙记任务
- 轮询 `lark-cli vc +notes`（间隔30秒，最多10次）获取逐字稿

### Step 5：智能画面抽帧
- 每隔2秒采样一帧，缩放到160×90灰度
- 计算与上一帧的MSE（均方误差）
- MSE > 500 → 画面切换了，保存该帧；否则跳过
- **不固定间隔抽帧**，确保不漏PPT切换，也不存重复帧

### Step 6：PPT画面识别
- 逐帧识别截图中的流程图、公式、代码、表格

### Step 7：生成笔记
- 综合逐字稿 + 画面识别，输出Markdown总结

### Step 8：生成汇总文档
- 所有分P处理完后，自动在输出目录根生成 `ALL_SUMMARIES.md`
- 按分P页码排序，包含目录跳转和每集完整内容

## 执行命令

```bash
# 单个链接
python scripts/bilibili_course_summary.py "https://www.bilibili.com/video/BV1Fzszz4Ek7/?p=9" --output-dir "./notes"

# 多个链接
python scripts/bilibili_course_summary.py "URL1" "URL2" --output-dir "./notes"

# 合集全量
python scripts/bilibili_course_summary.py --series "BV1Fzszz4Ek7" --output-dir "./notes"

# 指定分P范围
python scripts/bilibili_course_summary.py --series "BV1Fzszz4Ek7" --p-range 9,20 --output-dir "./notes"
```

## Common Rationalizations

| 借口 | 实际 |
|---|---|
| "URL里p参数不重要，默认下第1集就行" | 必须解析p参数，否则下错集数，总结内容完全不对 |
| "固定2分钟抽一帧就够了" | 固定间隔会漏掉中间PPT切换，必须用MSE变化检测 |
| "直接上传视频给妙记就行" | 妙记只收音频，必须先转MP3再上传 |
| "逐字稿已经够了，不需要识别画面" | PPT上的公式、图表、代码口播讲不清楚，必须抽帧识别 |
| "lark-cli输出目录随便写哪都行" | lark-cli有路径白名单，必须用 `~/AppData/Local/Temp`，不能用 `C:\WINDOWS\TEMP` |
| "MP3文件存在就行，不管大小" | 空文件(0字节)会导致妙记上传失败，必须校验>100KB |
| "转音频用av.CodecContext.create('mp3','w')就行" | 必须用av.codec.Codec('libmp3lame','w')并显式设置采样率/声道/格式 |
| "urllib.request 就能请求 B 站 API" | `x/web-interface/view` 等接口会 412 反爬，必须用 `curl_cffi`  impersonate=chrome120 |
| "视频流用 HTTP/2 更快" | bilivideo CDN 会 `HTTP/2 stream reset`，下载必须强制 `http_version=1` |
| "下载完不校验大小" | CDN 经常截断，必须对比 `Content-Length`，不一致就重试 |
| "summary.md 模板就是最终笔记" | 脚本生成的 summary.md 是空骨架，必须基于 transcript.txt 重写结构化内容 |
| "妙记 token 过期就放弃" | lark-cli 偶发 `temporary token expired`，重试一次即可 |

## Red Flags

- 下载的文件名显示 `p1` 但用户要的是其他集数 → p参数没解析
- 抽帧数量少于5帧或多于200帧 → MSE阈值不对
- 妙记一直转写不出来 → 先检查MP3是不是0字节空文件
- 妙记上传报JSON解析错误 → MP3文件无效或lark-cli未授权
- 总结内容是课程宣传/导学而不是技术内容 → 下错了分P
- 批量处理时后面的视频全部失败 → 第一个视频的错误没中断，后续用了空文件
- `HTTP Error 412` / `Expecting value: line 1 column 1` → B站反爬，必须装 curl_cffi 且用 impersonate
- `curl: (92) HTTP/2 stream reset` / `curl: (18) end of response` → CDN 截断，强制 HTTP/1.1 + 按 Content-Length 重试
- `Invalid data found when processing input: avcodec_send_packet` → mp4 下载不完整，删了重下
- `--output ... is outside the built-in allowlist` → lark-cli 拒绝了 C:\WINDOWS\TEMP，改用 ~/AppData/Local/Temp
- `parse temporary token from Authorization failed: temporary token expired` → lark-cli 会话 token 过期，重跑即可

## Verification

完成后确认：
- [ ] 输出文件夹名包含正确的P号和标题
- [ ] transcript.txt 存在且非空
- [ ] summary.md 存在且包含核心内容
- [ ] frames/ 目录有PPT截图
- [ ] 总结内容对应用户要求的那集，不是第1集
