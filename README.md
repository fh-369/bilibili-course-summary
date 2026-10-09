# bilibili-course-summary

B站课程视频智能总结Skill：输入B站课程链接，自动下载指定分P、转写逐字稿、智能识别PPT画面，生成结构化Markdown学习笔记。

## 功能

- **分P精确定位**：自动解析 `?p=页码`，下载指定分P（不会下错到第1集）
- **AI逐字稿**：通过飞书妙记自动转写语音为文字
- **智能抽帧**：MSE画面变化检测，自动捕获PPT切换，不漏页不重复
- **批量处理**：支持单个链接、多链接、合集全量遍历
- **结构化笔记**：每个分P输出独立文件夹，包含视频、音频、逐字稿、总结、PPT截图

## 安装

将本文件夹复制到你的skills目录下：

```bash
# Claude Code / 通用Agent Skill目录
~/.claude/skills/bilibili-course-summary/

# 或自定义目录
your-project/skills/bilibili-course-summary/
```

## 环境依赖

- Python 3.10+
- 安装Python依赖：`pip install av pillow curl_cffi`
- 已安装并授权 `lark-cli`（飞书命令行工具，用于语音转写）

详细配置见 [references/setup.md](references/setup.md)。

## 快速开始

```bash
# 单个视频
python scripts/bilibili_course_summary.py "https://www.bilibili.com/video/BV1Fzszz4Ek7/?p=9" --output-dir ./notes

# 多个视频
python scripts/bilibili_course_summary.py "URL1" "URL2" --output-dir ./notes

# 合集全量处理
python scripts/bilibili_course_summary.py --series "BV1Fzszz4Ek7" --output-dir ./notes

# 指定分P范围
python scripts/bilibili_course_summary.py --series "BV1Fzszz4Ek7" --p-range 9,20 --output-dir ./notes
```

## 输出结构

```
notes/
├── P9_机器学习建模流程/
│   ├── bilibili_BVxxxxx_p9_480P.mp4
│   ├── bilibili_BVxxxxx_p9_480P.mp3
│   ├── transcript.txt          # 逐字稿
│   ├── summary.md              # 总结笔记
│   └── frames/                # PPT截图（智能抽帧）
│       ├── f00_00m01s.jpg
│       └── ...
└── P10_特征工程介绍/
    └── ...
```

## 常见问题

见 [references/troubleshooting.md](references/troubleshooting.md)

## License

MIT
