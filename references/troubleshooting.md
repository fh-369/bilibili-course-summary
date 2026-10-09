# 常见问题排查

## 错误1：MP3转换失败 `avcodec_open2("libmp3lame", {}) returned 22`

**原因**：PyAV创建MP3编码器时初始化方式不对。`av.CodecContext.create("mp3", "w")` 不会自动设置采样率、声道数、格式，导致编码器打开失败。

**正确写法**：
```python
codec = av.codec.Codec("libmp3lame", "w")
ctx = av.codec.CodecContext.create(codec)
ctx.bit_rate = 128000
ctx.sample_rate = audio_stream.codec_context.sample_rate
ctx.format = "fltp"
ctx.layout = "stereo" if channels == 2 else "mono"
ctx.open()
```

**预防**：转换后检查MP3文件大小，小于100KB直接报错。

---

## 错误2：MP3文件是0字节空文件

**原因**：批量转换时，如果第一个视频转换失败但脚本没有中断，后续视频会跳过（因为文件已存在），但实际是空文件。

**预防**：每次转换后校验文件大小 > 100KB，否则重新转换。

---

## 错误3：lark-cli输出目录报错 `outside the built-in allowlist`

**原因**：lark-cli 的 `--output-dir` 有路径白名单限制，只允许：
- cwd（当前工作目录）
- `~/AppData/Local/Temp`
- `~/files`
- `~/.doubao`、`~/Doubao` 等

不能写到D盘任意目录。

**解决**：先输出到 `tempfile.gettempdir()` 临时目录，再复制到项目目录。

---

## 错误4：lark-cli上传失败 `Expecting value: line 1 column 1 (char 0)`

**原因**：lark-cli的stdout为空或不是JSON。常见于：
- MP3文件是0字节空文件
- 文件太大超出限制
- 授权过期

**预防**：上传前先检查MP3文件大小 > 100KB。

---

## 错误5：总是下到第1集，不是用户要的分P

**原因**：URL中的 `?p=页码` 没被解析，默认下第1个分P。

**解决**：脚本已自动从query string解析p参数。确认URL格式正确。

---

## 错误6：妙记转写超时

**原因**：长视频转写时间超过轮询窗口。

**解决**：脚本默认轮询15次×20秒=5分钟。超长视频可手动增加 `max_retries`。

---

## 错误7：抽帧数量异常

- **帧数太少（<5帧）**：MSE阈值太大，画面变化检测不灵敏，调小到300
- **帧数太多（>200帧）**：阈值太小，鼠标移动也被判定为切换，调大到800
- **默认值**：500，每2秒采样一次

---

## 错误8：B站API风控(412/429)

**原因**：短时间内批量请求太多。

**解决**：等5-10分钟再试，不要连续批量下载。
