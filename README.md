# Heal-Jimaku (治幕) - 字幕优化导出工具

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](https://www.apache.org/licenses/LICENSE-2.0) [![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/) [![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/) [![DeepSeek API](https://img.shields.io/badge/AI%20Model-DeepSeek-orange.svg)](https://platform.deepseek.com/) [![ElevenLabs API](https://img.shields.io/badge/Free%20STT-ElevenLabs-blueviolet.svg)](https://elevenlabs.io/) [![Soniox API](https://img.shields.io/badge/STT-Soniox-purple.svg)](https://soniox.com/) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/fuxiaomoke/heal-jimaku)

**Heal-Jimaku (治幕)** 是一款利用大语言模型对多语言文本（现已优化支持中文、英文、日文、韩文的智能分割处理提示词）进行智能分割，并将带有精确时间戳的 JSON 文件（可来自本地文件或通过内置的 **云端转录服务** 生成）转换为更自然、易读且适配DLsite审核（现已支持用户自行调整格式）要求的 SRT 字幕文件的桌面应用程序。它的开发初衷是"治愈"那些因没有断句功能或断句不佳导致缺乏语义连贯性而难以编辑阅读的音声转录结果，从而提高我对同人音声字幕的翻译效率。

![Heal-Jimaku 应用截图](https://raw.githubusercontent.com/fuxiaomoke/heal-jimaku/main/assets/screenshot.png)

## ✨ 项目特性

- **智能文本分割**: 深度整合大语言模型API**（默认使用 [DeepSeek](https://platform.deepseek.com/)，但现已支持配置其他API）**，利用大模型强大的语言理解能力及**两阶段处理方法（先生成全文摘要辅助理解上下文，再对文本块进行智能分割）**，并使用优化的多语言处理提示词（支持中文、日文、英文、韩文），根据语义和标点符号进行自然断句，**有效处理长文本并提升分割准确性**。

- **全能云端转录**:

  - **多服务商支持**: 提供 **ElevenLabs (Web/免费)** 模式、**ElevenLabs 官方 API** 和 **Soniox API** 三种转录服务，满足不同用户对稳定性、隐私和识别精度的需求。

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
4. **便捷获取初始JSON**: 集成的"免费获取JSON"功能，使用户无需依赖外部STT工具即可快速开始字幕优化流程。
5. **灵活的API配置**: 支持配置第三方大语言模型API服务，不再局限于特定的API提供商。
6. **台本辅助识别**: 通过导入原始台本并智能清洗，在 Soniox 模式下为模型提供 Context 上下文，显著提升专有名词和生僻词的识别准确率。

## 🛠️ 安装指南

### 操作系统

- Windows

### 依赖环境

- Python 3.8 或更高版本(如果单纯使用exe程序，则不需要)
- 一个有效的大语言模型 API Key（默认支持 [DeepSeek](https://platform.deepseek.com/)，可通过LLM高级管理窗口配置其他格式的API）
- (可选，若使用 Soniox 或 ElevenLabs 转录功能) [Soniox API Key](https://soniox.com/) [ElevenLabs API Key](https://elevenlabs.io/) 
- (可选，若使用免费获取JSON功能) 网络连接[多节点最佳，没有也不要紧]

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
   pip install -r requirements.txt
   ```

   主要依赖包括：

   - `PyQt6`
   - `requests`
   - `mutagen`
   - `langdetect`
   - `gradio_client` (用于处理PDF文档OCR识别)
   - `python-docx` (用于处理Word文档)

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

详细的使用步骤和界面说明，包括如何使用新增的 **Soniox 云端转录**、**台本辅助转录**、**免费获取JSON** 功能、**自定义高级SRT设置** 以及 **LLM高级配置**，请参见 [**USAGE.md**](https://github.com/fuxiaomoke/heal-jimaku/blob/main/docs/USAGE.md)。

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

## 🆕 v0.2.2.0 新功能

### 🎯 核心功能升级

- **Soniox 云端转录深度集成**:
  - 引入业界领先的 Soniox 语音识别 API
  - 支持多语言高精度识别（中文、日语、英语、韩语等）
  - 说话人分离（Diarization）功能，自动识别不同说话人
  - Context 上下文功能，通过台本辅助显著提升专有名词识别率
  - Soniox 专属 AI 后处理：智能修正发音相似的错别字
- **台本辅助转录与智能清洗**（革命性功能）:
  - 支持导入 **TXT, Word (.docx), PDF** 格式的原始台本
  - **LLM 智能清洗台本**：
    - 自动去除拟声词（如"哦齁齁~"、"呜呜~"）
    - 移除环境音效标记（如 [开门声]、[脚步声]）
    - 清除动作指示（如"抚摸头部"、"转身离开"）
    - 提取纯净对话文本作为 Soniox Context
  - **PDF 台本 OCR 识别**：
    - 集成 Dots OCR 服务
    - 自动识别 PDF 台本内容
    - OCR 结果智能清洗（去除页码、编号等）
  - **显著提升识别准确率**：
    - 生僻词识别准确率提升 30-50%
    - 专有名词（角色名、地名）几乎不会错
    - 特定领域术语识别更精准

### 🔧 用户体验优化

- **用户友好日志系统**:
  - 将技术日志转换为小白用户能理解的语言
  - 实时进度状态显示
  - 提供操作指导和错误提示
  - 支持 emoji 表情增强可读性

- **数据迁移功能**:
  - 从旧版本平滑升级
  - 自动迁移配置文件
  - 迁移固定背景图片
  - 简化的迁移策略，只迁移关键用户数据

### 📦 v0.2.0.0 关键功能回顾

- **批量处理功能**: 支持批量处理多个JSON文件或音频文件，提高工作效率。
  - 批量JSON处理：可同时选择多个JSON文件进行批量字幕优化。
  - 批量音频处理：可同时选择多个音频/视频文件进行批量转录和优化。
  - 智能处理模式：自动识别文件类型和数量，提供最佳处理方案。
- **拖拽处理功能**: 提供更直观的文件操作体验。
  - 支持拖拽JSON文件或媒体文件到主窗口。
  - 智能文件类型识别和处理模式切换。
  - 拖拽视觉反馈和错误提示。
  - 防止非法文件混合拖拽。
- **多语言处理提示词优化**:
  - 优化了所有提示词的分割逻辑。
- **增强的多语言支持**:
  - 新增**韩语(Korean)**和**通用(Universal)**的处理提示词，全面覆盖摘要生成和智能分割任务。
- **LLM高级管理升级**:
  - "LLM高级管理"功能全面实现，现已在UI中内置支持 **OpenAI、Claude (Anthropic)、Gemini (Google)** 三种主流API格式，并支持"自动检测"，极大增强了API的兼容性。
- **LLM输出后处理**:
  - 新增智能后处理逻辑，自动修正LLM分割结果中常见的括号内容（如 `(音效)文本` 或 `(音效1)(音效2)`）与正文混合或粘连的问题，提高分割准确性。
- **字幕时间戳优化**:
  - 新增结束时间校正算法，自动修正因ASR词间隙过大或单个词元（如语气词）时长异常导致的字幕显示时间不合理的问题。
  - 优化对 `(笑声)` 等括号内音频事件的处理，防止它们被错误分割或时长被不当延长。
- **背景管理**：
  - 新增背景图片管理窗口，支持自定义应用背景界面
  - 支持多背景轮播


## 🛣️ 未来规划 (后面要是有空的话)

- [x] 允许用户在界面中自行调整 SRT 生成参数 (如最小/最大时长、每行最大字符数)。 *(已通过设置对话框实现)*
- [x] 支持更多的 json 输入格式（比如whisper、assemblyai、deepgram等）。 *(已实现)*
- [x] 与作者的另一个语音转字幕项目功能类似，一键上传音频生成高质量字幕。 *(已通过"免费获取JSON"功能初步实现)*
- [x] 允许用户配置不同的大语言模型API服务，支持更多API提供商。 *(已通过LLM高级管理实现)*
- [x] 批量处理功能。 *(已实现)*
- [x] 拖拽处理功能。 *(已实现)*
- [x] 自定义背景图片管理。 *(已实现)*
- [x] 参考台本优化识别结果。 *(已通过 Soniox Context 功能部分实现，后续也会针对 ElevenLabs 的服务进行对应的优化处理)*
- [ ] 双声道音频分轨处理与合并
- [ ] 更好看的UI，这个我尽量好吧
- [ ] 生成字幕预览
- [ ] 时间轴手动调整

## 🤝 贡献

欢迎各种形式的贡献！如果您有任何建议、发现 Bug 或想要添加新功能，请随时：

1. 提交 [Issues](https://github.com/fuxiaomoke/heal-jimaku/issues) 来报告问题或提出建议。
2. 直接发 [邮件](mailto:l1335575367@gmail.com) 拷打作者，虽然我很菜，但是会尽力解决问题的。

## 📄 开源许可

本项目基于 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) 开源。

## 🙏 致谢

- 感谢 [DeepSeek](https://www.deepseek.com/) 提供的强大语言模型支持。
- 感谢 [LINUX DO](https://linux.do/) 的佬友们提供的各种大模型公益API。
- 感谢 [ElevenLabs](https://elevenlabs.io/) (当前"免费获取JSON"功能主要依赖其STT服务), [OpenAI (Whisper)](https://openai.com/research/whisper), [Deepgram](https://deepgram.com/), [AssemblyAI](https://www.assemblyai.com/), [Soniox](https://soniox.com/) 等提供的优质语音转录服务与模型。
- 感谢 [小红书 hi lab](https://github.com/rednote-hilab)  开源的高质量OCR模型。
- 感谢 [PyQt](https://riverbankcomputing.com/software/pyqt/intro) 开发团队。
