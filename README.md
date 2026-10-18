# Heal-Jimaku (治幕) - 字幕优化导出工具

> **⚠️ 项目状态（2026 年 10 月）**
>
> **本项目的维护停了。** 我的精力现在都在别的项目上，暂时没有余力加功能或者修问题。
>
> 另外有个坏消息：**「免费获取JSON」不能用了。** ElevenLabs 从 2026 年 10 月起给免费转录接口加了人机验证（hCaptcha），每次转录都要先拿到一个一次性的验证令牌，没有令牌的请求一律返回 `401 Unauthorized`。这种验证只能在浏览器里完成，而治幕是 PyQt 做的桌面程序，没有浏览器内核，拿不到令牌，所以这个功能在当前版本上就是不能用了。**它不是 bug，重装或者等更新都不会好**，也不用再为它提 Issue 了，我这边也修不了。
>
> **其余功能都正常**，包括这个程序最主要的用法：
>
> - **已有 JSON 的断句、优化、导出**：Whisper、Deepgram、AssemblyAI、Soniox、ElevenLabs 官方 API 等工具产出的词级时间戳 JSON，拖进来照常处理，不受影响；
> - **ElevenLabs 官方 API**：填上自己的 API Key，走官方的付费通道；
> - **Soniox 云端转录**：台本辅助、说话人分离都正常。
>
> 以后我会重写一版 v1.0，换掉现在这套界面框架，界面也重新设计。做好会在这个仓库发布，README 里也会写明。在那之前，v0.2.5 和更早的安装包会一直留在 [Releases](https://github.com/fuxiaomoke/heal-jimaku/releases) 里，随时可以下载。
>
> *Status (Oct 2026): maintenance mode — my focus is on other projects for now. ElevenLabs' free transcription entry started requiring a one-time hCaptcha token in Oct 2026; a PyQt desktop app has no browser engine to obtain one, so "free JSON" fails with 401. This is not a bug, and a version update cannot fix it. Everything else — local JSON post-processing, the ElevenLabs official API, Soniox — still works. A v1.0 rewrite is planned.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/) [![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/) [![DeepSeek API](https://img.shields.io/badge/AI%20Model-DeepSeek-orange.svg)](https://platform.deepseek.com/) [![ElevenLabs API](https://img.shields.io/badge/API-ElevenLabs-blueviolet.svg)](https://elevenlabs.io/) [![Soniox API](https://img.shields.io/badge/STT-Soniox-purple.svg)](https://soniox.com/) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/fuxiaomoke/heal-jimaku)

**Heal-Jimaku (治幕)** 是一款利用大语言模型对多语言文本（现已优化支持中文、英文、日文、韩文的智能分割处理提示词）进行智能分割，并将带有精确时间戳的 JSON 文件（可来自本地文件或通过内置的 **云端转录服务** 生成）转换为更自然、易读且适配DLsite审核（现已支持用户自行调整格式）要求的 SRT 字幕文件的桌面应用程序。它的开发初衷是"治愈"那些因没有断句功能或断句不佳导致缺乏语义连贯性而难以编辑阅读的音声转录结果，从而提高我对同人音声字幕的翻译效率。

![Heal-Jimaku 应用截图](https://raw.githubusercontent.com/fuxiaomoke/heal-jimaku/main/assets/screenshot.png)

## ✨ 项目特性

- **智能文本分割**: 深度整合大语言模型API**（默认使用 [DeepSeek](https://platform.deepseek.com/)，但现已支持配置其他API）**，利用大模型强大的语言理解能力及**两阶段处理方法（先生成全文摘要辅助理解上下文，再对文本块进行智能分割）**，并使用优化的多语言处理提示词（支持中文、日文、英文、韩文），根据语义和标点符号进行自然断句，**有效处理长文本并提升分割准确性**。

- **全能云端转录**:

  - **多服务商支持**: 提供 **ElevenLabs (Web/免费)** 模式、**ElevenLabs 官方 API** 和 **Soniox API** 三种转录服务，满足不同用户对稳定性、隐私和识别精度的需求。（**注意：ElevenLabs Web/免费 模式已失效，见开头的项目状态**）

- **台本辅助转录与智能清洗**:

  - 专为同人音声/广播剧设计的**革命性功能**。在 **Soniox 模式**下，支持导入 **TXT, Word (.docx), PDF** 格式的原始台本。
  - **LLM 智能清洗**: 程序会自动调用您配置的大模型，智能去除台本中的**拟声词**（如"哦齁齁~"）、**环境音效**（如 [开门声]）和**动作指示**（如"抚摸头部"），提取纯净的对话文本作为"Context上下文"发送给 Soniox 转录引擎，**极大提升生僻词、专有名词、角色名的识别准确率**。
  - **支持多种台本格式**:
    - TXT 纯文本台本
    - Word (.docx) 格式台本
    - PDF 格式台本（自动 OCR 识别，集成 Dots OCR 服务）

- **批量处理功能**: 支持批量处理多个 JSON 文件或音频文件，提高处理效率。

- **拖拽处理功能**: 支持拖拽 JSON 文件或媒体文件到窗口进行快速处理，提供直观的用户体验。

- **STT 结果优化**: 专为处理包含逐词时间戳的 JSON 文件设计，支持多种主流 ASR 服务商格式（如 ElevenLabs, Soniox, Whisper, Deepgram, AssemblyAI），优化语音转录文字 (STT) 的原始输出。

- **Soniox 独占 AI 后处理**: 针对 Soniox 生成的结果，程序可调用大模型进行二次校对，智能修正发音相似但逻辑不通的错别字（需在主界面手动勾选）。

- **SRT 字幕生成**: 输出行业标准的 `.srt` 字幕文件，兼容各类字幕编辑器以及视频播放器。

- **用户可配置的参数系统**:

  - SRT参数配置:

    允许用户通过设置对话框自定义关键SRT生成参数，包括：

    - 字幕目标最小持续时间 (秒)
    - 字幕最大持续时间 (秒)
    - 每行字幕最大字符数
    - 字幕间默认间隙 (毫秒)

  - LLM高级管理**（新增LLM详细配置功能！！！）**，支持：

    - 自定义API地址（支持各种**主流格式的API服务**）
    - **新增对 OpenAI, Claude (Anthropic), Gemini (Google) API 格式的显式支持**
    - 模型名称配置
    - 温度参数调节（控制输出随机性）
    - API连接测试功能
    - API Key管理与持久化保存
    - **多配置管理**：支持保存多个 LLM 配置，方便快速切换

- **图形用户界面**: 基于 PyQt6 构建，提供直观易用的操作界面。自定义控件和优化后的UI显示，同时也支持自定义多个背景图片，提供更舒适的用户体验。

- **用户友好的日志系统**:

  - 全新设计的日志处理器，将技术术语转换为小白用户能理解的语言
  - 实时进度状态提示，操作指导更清晰
  - 支持 emoji 表情增强可读性

- **配置持久化**:

  - 保存 LLM API配置（API地址、模型名称、温度、API Key等）。
  - 记住上次使用的文件、目录路径、选择的JSON格式以及输入模式（本地JSON或免费获取）。
  - 保存用户自定义的SRT生成参数、免费转录参数。

- **处理反馈**: 提供优化后的**详细日志输出**和**LLM处理进度条**显示。

- **错误处理**: 集成 `faulthandler` 以记录崩溃日志，方便调试。

- **数据迁移支持**: 从旧版本平滑升级，自动迁移配置文件和固定背景图片。

## 🚀 解决的问题

许多语音转录文字(STT) 工具可以生成带有word级或character级的时间戳的json响应，但这些文本要么缺少自然的断句输出，无法直接导出标准格式的字幕使用，要么导出的字幕断句效果一般，依旧需要费时费力的人工校对。Heal-Jimaku 通过以下方式，在一定程度上解决了这个问题：

1. **语义断句**: 利用大语言模型理解文本内容，**并通过预先生成的全文摘要来增强对长文本上下文的把握**，在最符合语义逻辑的地方进行分割。
2. **标点优化**: 智能处理括号、引号及各种句末标点，确保字幕的连贯性。
3. **时长与字数控制**: 遵循字幕的基本规范（现在可通过用户设置进行调整），调整字幕条目的显示时长和每行字数。
4. **便捷获取初始JSON**: 集成的"免费获取JSON"功能，使用户无需依赖外部STT工具即可快速开始字幕优化流程。**（已于 2026 年 10 月失效，见开头的项目状态；可以先用其他 ASR 工具生成 JSON 再导入）**
5. **灵活的API配置**: 支持配置第三方大语言模型API服务，不再局限于特定的API提供商。
6. **台本辅助识别**: 通过导入原始台本并智能清洗，在 Soniox 模式下为模型提供 Context 上下文，显著提升专有名词和生僻词的识别准确率。

## 🛠️ 安装指南

### 操作系统

- Windows

### 依赖环境

- Python 3.8 或更高版本(如果单纯使用exe程序，则不需要)
- 一个有效的大语言模型 API Key（默认支持 [DeepSeek](https://platform.deepseek.com/)，可通过LLM高级管理窗口配置其他格式的API）
- (可选，若使用 Soniox 或 ElevenLabs 转录功能) [Soniox API Key](https://soniox.com/) [ElevenLabs API Key](https://elevenlabs.io/) 
- (可选) 网络连接[多节点最佳，没有也不要紧]（只有「免费获取JSON」需要，该功能已失效，可以忽略）

### 直接运行打包好的可执行文件(最简单)

1. **在release界面找到最新的发行版，下载Heal-Jimaku.zip压缩包**
2. **解压到本地**
3. **双击运行 治幕.exe 文件**

### 从源码运行

1. **克隆仓库**:

   ```bash
   git clone https://github.com/fuxiaomoke/heal-jimaku.git
   cd heal-jimaku
   ```

2. **创建并激活虚拟环境** (推荐):

   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **安装依赖**:

   ```bash
   # 安装GUI程序依赖
   pip install -r requirements.txt
   
   # 如果需要使用命令行工具（tools目录），额外安装：
   pip install -r requirements-tools.txt
   ```

   主要依赖包括：

   - `PyQt6`
   - `requests`
   - `mutagen`
   - `langdetect`
   - `gradio_client` (用于处理PDF文档OCR识别)
   - `python-docx` (用于处理Word文档)
   
   命令行工具额外依赖：
   - `av` (PyAV - FFmpeg的Python绑定，用于视频音频提取，仅命令行工具需要)

4. **运行应用**:

   ```bash
   python src\main.py
   ```

   *(注意: 启动脚本已更改为 `src\main.py`)*

### (可选) 打包为可执行文件

如果您希望构建独立的可执行文件，可以使用packaging子文件夹中的build_heal_jimaku.bat脚本。

在packaging子文件夹中直接双击脚本，或在该文件夹下打开cmd命令提示符：

```bash
..\heal-jimaku\packaging>build_heal_jimaku.bat
```

打包后的文件将位于项目根目录下，双击运行即可。

(注意：`packaging/file_version_info.txt` 文件用于 Windows 打包时定义版本信息，PyInstaller 会自动查找。当前版本为 `0.2.2.0`)

## 📖 使用说明

详细的使用步骤和界面说明，包括如何使用 **Soniox 云端转录**、**台本辅助转录**、**免费获取JSON**（已失效）、**自定义高级SRT设置** 以及 **LLM高级配置**，请参见 [**USAGE.md**](https://github.com/fuxiaomoke/heal-jimaku/blob/main/docs/USAGE.md)。

## ⚙️ 配置文件

应用程序会在首次成功保存设置或启动时，在用户主目录下的 `.heal_jimaku` 文件夹中创建一个 `config` 文件夹，并在这个文件夹中创建一个 `config.json` 文件。该文件用于存储：

- LLM API配置（API地址、模型名称、温度参数、API Key [如果选择了"记住 API Key"]）
- 多个 LLM 配置及默认配置标记
- 上次使用的 JSON 文件路径或音频文件路径
- 上次使用的导出目录路径
- 上次选择的JSON格式
- 上次使用的输入模式
- 用户自定义的高级SRT参数 (最小/最大时长、每行最大字符数、字幕间默认间隙)
- 用户自定义的免费转录API参数 (转录语言、说话人数、是否标记音频事件)
- 背景图片设置
- 迁移状态记录

同时，崩溃日志会保存在用户主目录下的 `.heal_jimaku/logs/heal_jimaku_crashes.log`。

## 🛣️ 功能进度（历史记录，不再更新）

下面这些是开发时记下的进度：打了勾的都已经在旧版本里实现，没打勾的不会再在这个版本里做，会放到 v1.0 里重新考虑。

- [x] 允许用户在界面中自行调整 SRT 生成参数 (如最小/最大时长、每行最大字符数)。 *(已通过设置对话框实现)*
- [x] 支持更多的 json 输入格式（比如whisper、assemblyai、deepgram等）。 *(已实现)*
- [x] 与作者的另一个语音转字幕项目功能类似，一键上传音频生成高质量字幕。*(已通过"免费获取JSON"功能初步实现，该功能已于 2026 年 10 月失效，见开头的项目状态)*
- [x] 允许用户配置不同的大语言模型API服务，支持更多API提供商。 *(已通过LLM高级管理实现)*
- [x] 批量处理功能。 *(已实现)*
- [x] 拖拽处理功能。 *(已实现)*
- [x] 自定义背景图片管理。 *(已实现)*
- [x] 参考台本优化识别结果。 *(已通过 Soniox Context 功能部分实现)*
- [ ] 双声道音频分轨处理与合并
- [ ] 更好看的 UI
- [ ] 生成字幕预览
- [ ] 时间轴手动调整

## 🤝 贡献

这个项目已经停更了，所以我不再接收新功能和技术建议——提了也没有人去实现，反而让人白等。

想自己改的话：直接 fork，Apache-2.0 授权，随你怎么改，不用问我，也不用发 PR（我不会合并）。

如果发现 README 或文档里有写错的地方（比如某条说明已经不符合现状），欢迎直接发 [邮件](mailto:l1335575367@gmail.com) 告诉我，回得慢，但都会看。

## 📄 开源许可

本项目基于 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) 开源。

## 🙏 致谢

- 感谢 [DeepSeek](https://www.deepseek.com/) 提供的强大语言模型支持。
- 感谢 [LINUX DO](https://linux.do/) 的佬友们提供的各种大模型公益API。
- 感谢 [ElevenLabs](https://elevenlabs.io/)（早先的「免费获取JSON」功能依赖其 STT 服务）、[OpenAI (Whisper)](https://openai.com/research/whisper), [Deepgram](https://deepgram.com/), [AssemblyAI](https://www.assemblyai.com/), [Soniox](https://soniox.com/) 等提供的优质语音转录服务与模型。
- 感谢 [小红书 hi lab](https://github.com/rednote-hilab)  开源的高质量OCR模型。
- 感谢 [PyQt](https://riverbankcomputing.com/software/pyqt/intro) 开发团队。
