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
- 已安装并授权 `lark-cli`（飞书命令行工具）

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
| "lark-cli输出目录随便写哪都行" | lark-cli有路径白名单，必须输出到Temp目录再复制 |
| "MP3文件存在就行，不管大小" | 空文件(0字节)会导致妙记上传失败，必须校验>100KB |
| "转音频用av.CodecContext.create('mp3','w')就行" | 必须用av.codec.Codec('libmp3lame','w')并显式设置采样率/声道/格式 |

## Red Flags

- 下载的文件名显示 `p1` 但用户要的是其他集数 → p参数没解析
- 抽帧数量少于5帧或多于200帧 → MSE阈值不对
- 妙记一直转写不出来 → 先检查MP3是不是0字节空文件
- 妙记上传报JSON解析错误 → MP3文件无效或lark-cli未授权
- 总结内容是课程宣传/导学而不是技术内容 → 下错了分P
- 批量处理时后面的视频全部失败 → 第一个视频的错误没中断，后续用了空文件

## Verification

完成后确认：
- [ ] 输出文件夹名包含正确的P号和标题
- [ ] transcript.txt 存在且非空
- [ ] summary.md 存在且包含核心内容
- [ ] frames/ 目录有PPT截图
- [ ] 总结内容对应用户要求的那集，不是第1集
