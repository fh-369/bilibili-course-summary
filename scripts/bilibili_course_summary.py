#!/usr/bin/env python3
"""
bilibili-course-summary 主脚本
输入B站课程链接，自动下载指定分P、转写逐字稿、智能识别PPT画面，生成学习笔记。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ========== B站解析 ==========

def _headers(referer="https://www.bilibili.com/"):
    return {"User-Agent": USER_AGENT, "Referer": referer, "Accept-Language": "zh-CN,zh;q=0.9"}


def _fetch_json(url, referer="https://www.bilibili.com/"):
    req = Request(url, headers=_headers(referer))
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"B站API错误: {data.get('message')}")
    return data.get("data", {})


def parse_url(url):
    """从URL提取BV号和p参数。"""
    parsed = urlparse(url)
    bvid_match = re.search(r"(BV[0-9A-Za-z]{10})", parsed.path)
    if not bvid_match:
        raise ValueError(f"无法识别BV号: {url}")
    bvid = bvid_match.group(1)
    page = 1
    p_match = re.search(r"[?&]p=(\d+)", "?" + parsed.query)
    if p_match:
        page = int(p_match.group(1))
    return {"bvid": bvid, "page": page}


def get_pagelist(bvid):
    url = "https://api.bilibili.com/x/player/pagelist?" + urlencode({"bvid": bvid})
    data = _fetch_json(url)
    return data if isinstance(data, list) else []


def get_metadata(bvid):
    url = "https://api.bilibili.com/x/web-interface/view?" + urlencode({"bvid": bvid})
    return _fetch_json(url)


def get_playurl(bvid, cid, quality=32):
    params = {"bvid": bvid, "cid": str(cid), "qn": str(quality), "fnval": "0"}
    url = "https://api.bilibili.com/x/player/playurl?" + urlencode(params)
    data = _fetch_json(url)
    durl = data.get("durl", [])
    if not durl:
        raise RuntimeError("未获取到视频直链")
    return durl[0]["url"]


def resolve_target(url):
    info = parse_url(url)
    pages = get_pagelist(info["bvid"])
    if not pages:
        raise RuntimeError("未获取到分P列表")
    if info["page"] < 1 or info["page"] > len(pages):
        raise ValueError(f"分P页码超出范围，共{len(pages)}个分P")
    target = pages[info["page"] - 1]
    meta = get_metadata(info["bvid"])
    return {
        "bvid": info["bvid"], "page": info["page"], "cid": target["cid"],
        "title": meta.get("title", info["bvid"]),
        "part_title": target.get("part", f"P{info['page']}"),
        "duration": target.get("duration", 0),
        "play_url": get_playurl(info["bvid"], target["cid"]),
        "total_pages": len(pages),
    }


# ========== 下载与音频 ==========

def download_video(play_url, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    req = Request(play_url, headers=_headers())
    with urlopen(req, timeout=60) as resp, open(output_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise FileNotFoundError(f"下载失败: {output_path}")
    return os.path.abspath(output_path)


def convert_to_mp3(video_path, output_dir):
    import av
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    mp3_path = os.path.join(output_dir, f"{base}.mp3")
    container = av.open(video_path)
    audio_stream = next((s for s in container.streams if s.type == "audio"), None)
    if not audio_stream:
        raise RuntimeError("无音频流")
    codec = av.codec.Codec("libmp3lame", "w")
    ctx = av.codec.CodecContext.create(codec)
    ctx.bit_rate = 128000
    ctx.sample_rate = audio_stream.codec_context.sample_rate
    ctx.format = "fltp"
    ctx.layout = "stereo" if audio_stream.codec_context.channels == 2 else "mono"
    ctx.open()
    with open(mp3_path, "wb") as out_f:
        for frame in container.decode(audio_stream):
            for packet in ctx.encode(frame):
                out_f.write(packet)
        for packet in ctx.encode(None):
            out_f.write(packet)
    container.close()
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 100000:
        raise RuntimeError(f"MP3转换失败或文件过小: {mp3_path}")
    return os.path.abspath(mp3_path)


# ========== 飞书妙记 ==========

def _run_lark(args, cwd=None):
    cmd = ["lark-cli"] + args + ["--format", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"lark-cli失败: {r.stderr}")
    return json.loads(r.stdout)


def upload_to_minutes(audio_path, poll_interval=30, max_retries=10):
    audio_dir = os.path.dirname(audio_path)
    audio_name = os.path.basename(audio_path)
    # 上传云空间
    up = _run_lark(["drive", "+upload", "--file", f"./{audio_name}"], cwd=audio_dir)
    file_token = up["data"]["file_token"]
    # 创建妙记
    mu = _run_lark(["minutes", "+upload", "--file-token", file_token])
    minute_token = mu["data"]["minute_token"]
    minute_url = mu["data"]["minute_url"]
    # 轮询获取逐字稿（lark-cli输出目录有白名单限制，必须用Temp目录）
    import tempfile
    notes_dir = os.path.join(tempfile.gettempdir(), "bilibili_minutes")
    os.makedirs(notes_dir, exist_ok=True)
    for _ in range(max_retries):
        nr = _run_lark(["vc", "+notes", "--minute-tokens", minute_token, "--output-dir", notes_dir])
        notes = nr.get("data", {}).get("notes", [])
        if notes:
            tf = notes[0].get("artifacts", {}).get("transcript_file")
            if tf and os.path.exists(tf):
                with open(tf, "r", encoding="utf-8") as f:
                    return {"minute_url": minute_url, "minute_token": minute_token,
                            "transcript": f.read(), "transcript_file": os.path.abspath(tf)}
        time.sleep(poll_interval)
    raise RuntimeError(f"妙记转写超时: {minute_token}")


# ========== 智能抽帧 ==========

def extract_frames(video_path, output_dir, sample_interval=2.0, mse_threshold=500.0):
    import av
    from PIL import Image
    os.makedirs(output_dir, exist_ok=True)
    container = av.open(video_path)
    stream = container.streams.video[0]
    fps = float(stream.average_rate)
    step = max(1, int(fps * sample_interval))
    saved = []
    prev = None
    count = 0
    for frame in container.decode(video=0):
        count += 1
        if count % step != 0:
            continue
        ts = count / fps
        small = list(frame.to_image().convert("L").resize((160, 90)).getdata())
        if prev is None:
            p = os.path.join(output_dir, f"f{len(saved):02d}_{int(ts//60):02d}m{int(ts%60):02d}s.jpg")
            frame.to_image().save(p, quality=85)
            saved.append(p)
            prev = small
            continue
        mse = sum((a-b)**2 for a, b in zip(prev, small)) / len(small)
        if mse > mse_threshold:
            p = os.path.join(output_dir, f"f{len(saved):02d}_{int(ts//60):02d}m{int(ts%60):02d}s.jpg")
            frame.to_image().save(p, quality=85)
            saved.append(p)
            prev = small
    container.close()
    return saved


# ========== 总结生成 ==========

def generate_summary(target, transcript, frames, minute_url):
    mins = target["duration"] // 60
    secs = target["duration"] % 60
    md = f"""# {target['part_title']}

> 来源：{target['title']}
> 时长：{mins}分{secs}秒
> 飞书妙记：{minute_url}

---

## 核心内容

<!-- 基于逐字稿提炼 -->

## PPT画面要点

| 时间 | 内容 |
|---|---|
"""
    for fp in frames:
        t = os.path.basename(fp).split("_", 1)[1].rsplit(".", 1)[0] if "_" in fp else ""
        md += f"| {t} | 见截图 |\n"
    md += f"""
## 关键概念

<!-- 术语、定义、公式 -->

## 课堂要点

<!-- 练习题、注意事项 -->

---

> 逐字稿见 transcript.txt
> PPT截图见 frames/
"""
    return md


# ========== 主流程 ==========

def sanitize(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip("_")


def process_url(url, output_dir, audio_only=False, frame_threshold=500.0):
    print(f"\n{'='*50}\n处理: {url}\n{'='*50}")
    target = resolve_target(url)
    print(f"  P{target['page']}: {target['part_title']} ({target['duration']}秒)")

    dir_name = f"P{target['page']}_{sanitize(target['part_title'])}"
    vdir = os.path.join(output_dir, dir_name)
    os.makedirs(vdir, exist_ok=True)
    frames_dir = os.path.join(vdir, "frames")

    # 下载
    vpath = os.path.join(vdir, f"bilibili_{target['bvid']}_p{target['page']}_480P.mp4")
    if not os.path.exists(vpath):
        print("  下载视频...")
        download_video(target["play_url"], vpath)

    # 转音频
    print("  转音频...")
    apath = convert_to_mp3(vpath, vdir)

    # 妙记转写
    print("  飞书妙记转写（等待1-3分钟）...")
    mr = upload_to_minutes(apath)
    with open(os.path.join(vdir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(mr["transcript"])

    # 抽帧
    print("  智能抽帧...")
    frames = extract_frames(vpath, frames_dir, mse_threshold=frame_threshold)
    print(f"  保存 {len(frames)} 帧")

    # 总结
    md = generate_summary(target, mr["transcript"], frames, mr["minute_url"])
    with open(os.path.join(vdir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md)

    if audio_only and os.path.exists(vpath):
        os.remove(vpath)

    print(f"  ✅ 完成: {vdir}")
    return vdir


def generate_master_summary(output_dir):
    """扫描所有分P文件夹，按页码排序，汇总生成总文档。"""
    import re as _re
    entries = []
    for name in os.listdir(output_dir):
        full = os.path.join(output_dir, name)
        if not os.path.isdir(full):
            continue
        m = _re.match(r"P(\d+)_", name)
        if not m:
            continue
        summary_path = os.path.join(full, "summary.md")
        if os.path.exists(summary_path):
            entries.append((int(m.group(1)), name, summary_path))
    if not entries:
        return
    entries.sort(key=lambda x: x[0])

    parts = ["# 课程笔记汇总\n"]
    parts.append(f"共 {len(entries)} 个分P，按顺序排列：\n")
    parts.append("## 目录\n")
    for pnum, name, _ in entries:
        title = name.split("_", 1)[1] if "_" in name else name
        parts.append(f"- [P{pnum}: {title}](#p{pnum})\n")
    parts.append("\n---\n")

    for pnum, name, spath in entries:
        with open(spath, "r", encoding="utf-8") as f:
            content = f.read()
        parts.append(f'<a id="p{pnum}"></a>\n\n{content}\n\n---\n')

    master_path = os.path.join(output_dir, "ALL_SUMMARIES.md")
    with open(master_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"\n📚 汇总文档已生成: {master_path}")
    return master_path


def main():
    ap = argparse.ArgumentParser(description="B站课程视频智能总结")
    ap.add_argument("urls", nargs="*", help="B站视频链接")
    ap.add_argument("--series", help="合集BV号")
    ap.add_argument("--p-range", help="分P范围 如 9,20")
    ap.add_argument("--output-dir", default="./notes", help="输出目录")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--frame-threshold", type=float, default=500.0)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    urls = list(args.urls or [])

    if args.series:
        pages = get_pagelist(args.series)
        start, end = 1, len(pages)
        if args.p_range:
            parts = args.p_range.split(",")
            start = int(parts[0])
            end = int(parts[1]) if len(parts) > 1 else len(pages)
        for p in range(start, end + 1):
            try:
                process_url(f"https://www.bilibili.com/video/{args.series}/?p={p}",
                            args.output_dir, args.audio_only, args.frame_threshold)
            except Exception as e:
                print(f"  ❌ P{p}失败: {e}")
    elif urls:
        for u in urls:
            try:
                process_url(u, args.output_dir, args.audio_only, args.frame_threshold)
            except Exception as e:
                print(f"  ❌ 失败 [{u}]: {e}")
    else:
        ap.print_help()

    # 所有视频处理完后，生成汇总文档
    if urls or args.series:
        generate_master_summary(args.output_dir)


if __name__ == "__main__":
    main()
