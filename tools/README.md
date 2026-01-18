# 命令行工具 - 自动字幕生成

独立的命令行工具，用于从视频文件自动生成字幕。支持长视频自动分割、批量转录和 LLM 优化。

## 功能特性

- ✅ **视频音频提取**: 支持多种视频格式（mp4, mkv, avi, webm 等）
- ✅ **智能音频分割**: 自动将超长音频分割为 28 分钟片段（避开 ElevenLabs 30 分钟限制）
- ✅ **静音检测分割**: 在静音处切割，避免截断句子
- ✅ **批量转录**: 支持 ElevenLabs API（付费）和 Web 版（免费，可能失效）
- ✅ **JSON 合并**: 自动合并多个转录结果并调整时间戳
- ✅ **LLM 优化**: 使用大语言模型优化字幕分割和断句
- ✅ **配置共享**: 与 GUI 版本共享配置文件

## 安装依赖

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或单独安装命令行工具所需的依赖
pip install av requests mutagen langdetect
```

**重要**: `av` 库是 FFmpeg 的 Python 绑定，用于视频音频处理。如果安装失败，请确保系统已安装 FFmpeg。

## 使用方法

### 基本使用

```bash
# 最简单的使用方式（需要先在 GUI 中配置 API Key）
python tools/auto_subtitle.py video.mp4
```

### 指定语言

```bash
# 指定目标语言（支持: zh, ja, en, ko）
python tools/auto_subtitle.py video.mp4 --language ja
```

### 使用 API Key

```bash
# 使用 ElevenLabs API Key（推荐，免费版已失效）
python tools/auto_subtitle.py video.mp4 --elevenlabs-api-key YOUR_ELEVENLABS_KEY

# 使用 LLM API Key
python tools/auto_subtitle.py video.mp4 --llm-api-key sk-xxx

# 同时指定两个 API Key
python tools/auto_subtitle.py video.mp4 \
  --llm-api-key sk-xxx \
  --elevenlabs-api-key el-xxx
```

### 完整配置示例

```bash
python tools/auto_subtitle.py video.mp4 \
  --llm-api-key sk-xxx \
  --elevenlabs-api-key el-xxx \
  --language ja \
  --api-url https://api.deepseek.com/v1/chat/completions \
  --model deepseek-chat \
  --temperature 0.3 \
  --max-duration 1680
```

## 参数说明

### 必需参数

- `video`: 视频文件路径（支持 mp4, mkv, avi, webm, mov 等格式）

### 可选参数

- `--llm-api-key`: LLM API Key（用于字幕优化，不指定则使用配置文件中的）
- `--elevenlabs-api-key`: ElevenLabs API Key（用于音频转录，不指定则使用免费版）
- `--language`: 目标语言，可选值: `zh`(中文), `ja`(日文), `en`(英文), `ko`(韩文)
- `--api-url`: LLM API 地址（默认: DeepSeek API）
- `--model`: LLM 模型名称（默认: deepseek-chat）
- `--temperature`: LLM 温度参数（默认: 0.3，范围 0.0-1.0）
- `--max-duration`: 音频分割最大时长，单位秒（默认: 1680 = 28分钟）

## 工作流程

1. **音频提取**: 从视频中提取音频并转换为 OGG 格式（16kHz, 单声道）
2. **音频分割**: 如果音频超过 28 分钟，自动分割为多个片段（在静音处切割）
3. **批量转录**: 使用 ElevenLabs API 转录所有音频片段
4. **JSON 合并**: 合并多个转录结果，调整时间戳
5. **LLM 优化**: 使用大语言模型优化字幕分割和断句
6. **SRT 生成**: 生成标准 SRT 字幕文件

## 配置文件

工具会自动读取 GUI 保存的配置文件：`~/.heal_jimaku/config/config.json`

如果配置文件中已保存 API Key，可以直接使用：

```bash
# 无需指定 API Key，自动从配置文件读取
python tools/auto_subtitle.py video.mp4
```

## 支持的文件格式

### 视频格式
- MP4, MKV, AVI, WebM, MOV, FLV, WMV, M4V, TS, MTS

### 音频格式
- MP3, WAV, FLAC, M4A, OGG, Opus, AAC, WMA

## 输出文件

- **SRT 字幕**: 与视频文件同名，扩展名为 `.srt`
- **临时文件**: 音频提取和分割产生的临时文件保存在系统临时目录

## 常见问题

### 1. PyAV 安装失败

```bash
# Windows: 下载预编译的 wheel 文件
pip install av

# Linux: 先安装 FFmpeg 开发库
sudo apt-get install libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev
pip install av

# macOS: 使用 Homebrew 安装 FFmpeg
brew install ffmpeg
pip install av
```

### 2. ElevenLabs 免费版失效

ElevenLabs 免费版已经失效，建议使用 API Key：

```bash
python tools/auto_subtitle.py video.mp4 --elevenlabs-api-key YOUR_KEY
```

### 3. LLM API Key 从哪里获取？

- **DeepSeek**: https://platform.deepseek.com/
- **OpenAI**: https://platform.openai.com/
- **其他兼容 OpenAI API 的服务**

### 4. 如何处理超长视频？

工具会自动将超过 28 分钟的音频分割为多个片段，无需手动处理。分割点会选择在静音处，避免截断句子。

### 5. 生成的字幕在哪里？

字幕文件与视频文件在同一目录，文件名相同，扩展名为 `.srt`。

例如：
- 视频: `video.mp4`
- 字幕: `video.srt`

## 技术架构

```
tools/
├── auto_subtitle.py          # 命令行入口
└── core/
    ├── audio_extractor.py    # 音频提取和分割
    ├── audio_processor.py    # 音频处理编排
    └── subtitle_pipeline.py  # 字幕生成流程

复用 src/ 目录的模块:
├── core/
│   ├── elevenlabs_api.py     # ElevenLabs API 客户端
│   ├── transcription_parser.py # 转录数据解析
│   ├── srt_processor.py      # SRT 字幕处理
│   ├── llm_api.py            # LLM API 客户端
│   └── data_models.py        # 数据模型
└── config.py                 # 配置管理
```

## 示例输出

```
使用配置:
  LLM API URL: https://api.deepseek.com/v1/chat/completions
  LLM 模型: deepseek-chat
  LLM 温度: 0.3
  ElevenLabs API Key: el-1234567...abcd
  语言: ja

[00:12:34] 开始处理视频: video.mp4
============================================================
[00:12:34] 步骤 1/5: 提取音频
  提取音频中...  提取进度: 100.0%
[00:12:45] ✓ 音频提取完成: /tmp/video_extracted.ogg
============================================================
[00:12:45] 步骤 2/5: 检查音频时长并分割
  音频时长: 3600.0秒 (60.0分钟)
  最大时长限制: 1680秒 (28.0分钟)
  音频超过限制，开始分割...
[00:13:15] ✓ 音频已分割为 3 个片段
============================================================
[00:13:15] 步骤 3/5: ElevenLabs 转录
  [1/3] 转录: video_part001.ogg (1680.0秒)
  使用 ElevenLabs API (付费版)
  ✓ 已保存: /tmp/video_part001.json
  [2/3] 转录: video_part002.ogg (1680.0秒)
  ...
[00:25:30] ✓ 转录完成，生成 3 个JSON文件
============================================================
[00:25:30] 步骤 4/5: 合并转录结果
  合并 3 个JSON文件...
  ✓ 成功合并 3 个文件，共 5432 个单词
[00:25:31] ✓ JSON合并完成: /tmp/video_merged.json
============================================================
[00:25:31] 步骤 5/5: LLM优化并生成SRT
  解析转录JSON...
  ✓ 解析完成: 5432 个单词
  文本长度: 12345 字符
  调用LLM进行文本分割优化...
  ✓ LLM分割完成: 234 个片段
  生成SRT字幕...
  ✓ 生成 234 条字幕
[00:25:45] ✓ SRT生成完成: video.srt
============================================================
[00:25:45] ✓ 全部完成！

============================================================
✓ 字幕已生成: video.srt
============================================================
```

## 许可证

本工具是 heal-jimaku 项目的一部分，遵循项目的开源许可证。

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**作者**: fuxiaomoke  
**版本**: 0.2.2.0
