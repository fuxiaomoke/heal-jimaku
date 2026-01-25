import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QSpacerItem, QSizePolicy, QWidget, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QGroupBox, QSpinBox, QTextEdit, QButtonGroup, QRadioButton,
    QFormLayout, QScrollArea, QFrame, QStackedWidget, QGridLayout, QListWidget,
    QListWidgetItem, QApplication, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QSize, QThread
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap

from ui.custom_widgets import CustomLabel, TransparentWidget, StrokeCheckBoxWidget
from utils.file_utils import resource_path
from config import (
    DEFAULT_CLOUD_TRANSCRIPTION_PROVIDER,
    DEFAULT_ELEVENLABS_API_KEY,
    DEFAULT_ELEVENLABS_API_REMEMBER_KEY,
    DEFAULT_ELEVENLABS_API_LANGUAGE,
    DEFAULT_ELEVENLABS_API_NUM_SPEAKERS,
    DEFAULT_ELEVENLABS_API_ENABLE_DIARIZATION,
    DEFAULT_ELEVENLABS_API_TAG_AUDIO_EVENTS,
    DEFAULT_SONIOX_API_KEY,
    DEFAULT_SONIOX_API_REMEMBER_KEY,
    DEFAULT_SONIOX_LANGUAGE_HINTS,
    DEFAULT_SONIOX_ENABLE_SPEAKER_DIARIZATION,
    DEFAULT_SONIOX_ENABLE_LANGUAGE_IDENTIFICATION,
    DEFAULT_SONIOX_CONTEXT_TERMS,
    DEFAULT_SONIOX_CONTEXT_TEXT,
    DEFAULT_SONIOX_CONTEXT_GENERAL,
    CLOUD_PROVIDER_ELEVENLABS_WEB,
    CLOUD_PROVIDER_ELEVENLABS_API,
    CLOUD_PROVIDER_SONIOX_API,
    SUPPORTED_LANGUAGES,
    SONIOX_SUPPORTED_LANGUAGES,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE_URL,
    DEFAULT_LLM_MODEL_NAME,
    DEFAULT_LLM_TEMPERATURE,
    USER_LLM_API_KEY_KEY,
    USER_LLM_API_BASE_URL_KEY,
    USER_LLM_MODEL_NAME_KEY,
    USER_LLM_TEMPERATURE_KEY
)
from core.elevenlabs_api import (
    ElevenLabsSTTClient, 
    ELEVENLABS_MODELS, 
    DEFAULT_ELEVENLABS_WEB_MODEL, 
    DEFAULT_ELEVENLABS_API_MODEL
)
from core.soniox_api import SonioxClient
from core.llm_api import call_llm_api_for_segmentation

# [新增] 导入 OCR 模块
from core.dots_ocr import run_dots_ocr

# 文件处理库导入（处理可能的导入错误）
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# 导入json用于读取配置文件
try:
    import json
    JSON_AVAILABLE = True
except ImportError:
    JSON_AVAILABLE = False


class OCRWorker(QThread):
    """OCR识别后台工作线程"""

    finished = pyqtSignal(str)  # OCR完成信号 (识别后的文本)
    error = pyqtSignal(str)     # 错误信号

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """执行OCR识别"""
        try:
            import time
            start_time = time.time()
            print(f"[OCR] 开始处理文件: {self.file_path}")

            # 调用OCR模块
            ocr_content = run_dots_ocr(self.file_path)

            if ocr_content is None:
                self.error.emit("OCR识别失败，请检查网络连接或重试")
            else:
                processing_time = time.time() - start_time
                print(f"[OCR] 识别完成，耗时: {processing_time:.2f}秒，文本长度: {len(ocr_content)}字符")
                self.finished.emit(ocr_content)

        except ImportError:
            self.error.emit("使用OCR功能需要安装 gradio_client 库")
        except Exception as e:
            self.error.emit(f"OCR识别过程出错: {str(e)}")


class ScriptCleaningWorker(QThread):
    """台本清洗后台工作线程"""

    finished = pyqtSignal(str)  # 清洗完成信号 (清洗后的文本)
    error = pyqtSignal(str)     # 错误信号

    def __init__(self, raw_text, api_key, api_base_url, model_name, temperature):
        super().__init__()
        self.raw_text = raw_text
        self.api_key = api_key
        self.api_base_url = api_base_url
        self.model_name = model_name
        self.temperature = temperature

    def run(self):
        """执行台本清洗"""
        try:
            # ASMR/广播剧专用清洗系统提示词
            system_prompt = """你是一个专业的广播剧/ASMR台本数据清洗专家。
任务目标：提取原始文本中的“有效对白”，去除所有干扰 ASR（自动语音识别）语言模型的噪音。

### 核心处理规则
1. 【彻底去除噪音】：
   - 删除所有动作描写、旁白（通常在 ( ), （ ）, [ ], 【 】 内）。
     * 必须保留对象：注意，在括号内的心理活和人物的自言自语需要保留！！！
   - 删除所有环境音效（SE）标记（如：<开门声>, *脚步声*, SE:雨）。
   - 删除一眼就能看出来的幻觉，常见的就是各种不自然的单字或者单个符号重复过多次，以至于严重破坏剧情内容。
   - 删除所有无实际语义的生理拟声词（呼吸、呻吟、舔舐、接吻等）。
     * 删除对象示例：ハァ、んっ、チュ、ぁ…、っ…、(喘息)、(kiss)
     * 必须保留对象：具有明确语义的感叹词（如：あれ？、えーと、Damn、Oh、喂、哎呀）。

2. 【智能保留角色】：
   - 如果是多角色对话，必须保留“角色名: ”前缀（如 "A: "），这能极大帮助 ASR 区分说话人。
   - 如果是单人独白或旁白读信，则无需强行加角色名。

3. 【严格输出格式】：
   - 仅输出清洗后的文本，**严禁**包含任何解释性语句（如“清洗结果如下”）。
   - 保持原有的对话换行逻辑，不要合并成一段。

### Few-Shot 示例（请严格模仿以下处理逻辑）

输入示例 1：
(ドアが開く音)
妹：あっ、お兄ちゃん！おかえり。(駆け寄ってくる)
兄：(内心：しまった、隠しておいた本が...) た、ただいま。
妹：ん？...くんくん(匂いを嗅ぐ)...なんか甘い匂いしない？
(SE: ドサッ)

输出示例 1：
妹：あっ、お兄ちゃん！おかえり。
兄：(内心：しまった、隠しておいた本が...) た、ただいま。
妹：なんか甘い匂いしない？

输入示例 2：
【回想】
A: 好きです！付き合ってください！
(心臓の音: ドクン...ドクン...)
B: ...えーと、ごめんなさい。チュッ（おでこにキス）
A: え...？嘘...ぁ...ぁ...（泣き崩れる）

输出示例 2：
A: 好きです！付き合ってください！
B: ...えーと、ごめんなさい。
A: え...？嘘...

无论输入格式多么混乱，请提取出“人类能听到的有效语音内容”及其必要的“对话者标记”。
请现在开始处理用户输入的文本： """

            MAX_CHUNK_SIZE = 4500 # 安全阈值
            cleaned_segments = []

            try:
                # 1. 判断是否需要分割
                if len(self.raw_text) > MAX_CHUNK_SIZE:
                    # 调用分割方法
                    chunks = self._split_text(self.raw_text, MAX_CHUNK_SIZE)

                    # 2. 循环处理
                    for i, chunk in enumerate(chunks):
                        # 调用 LLM (复用原有 _call_llm_directly 逻辑)
                        segment_cleaned = self._call_llm_directly(
                            api_key=self.api_key,
                            text_content=chunk,
                            api_base_url=self.api_base_url,
                            model_name=self.model_name,
                            temperature=self.temperature,
                            system_prompt=system_prompt
                        )

                        if segment_cleaned:
                            cleaned_segments.append(segment_cleaned)
                        else:
                            # 容错：清洗失败则保留原文，防止丢失
                            cleaned_segments.append(chunk)
                else:
                    # 短文本直接处理
                    result = self._call_llm_directly(
                        api_key=self.api_key,
                        text_content=self.raw_text,
                        api_base_url=self.api_base_url,
                        model_name=self.model_name,
                        temperature=self.temperature,
                        system_prompt=system_prompt
                    )
                    if result:
                        cleaned_segments.append(result)

                # 3. 合并结果
                final_text = "\n".join(cleaned_segments)
                if final_text and len(final_text.strip()) > 0:
                    self.finished.emit(final_text.strip())
                else:
                    self.error.emit("清洗失败：LLM未返回有效结果")

            except Exception as inner_e:
                self.error.emit(f"清洗出错: {str(inner_e)}")

        except Exception as e:
            self.error.emit(f"清洗过程出错：{str(e)}")

    def _call_llm_directly(self, api_key, text_content, api_base_url, model_name, temperature, system_prompt):
        """直接调用LLM API进行台本清洗，不进行分割"""
        import requests
        import traceback

        try:
            # 构建请求URL
            if "generativelanguage.googleapis.com" in api_base_url:
                # Gemini API
                target_url = f"{api_base_url.rstrip('/')}/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{
                        "parts": [{"text": f"系统提示：{system_prompt}\n\n用户输入：{text_content}"}]
                    }],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 8192
                    }
                }
                response = requests.post(target_url, json=payload, timeout=180)
            elif "api.anthropic.com" in api_base_url or "/v1/messages" in api_base_url:
                # Claude API
                target_url = f"{api_base_url.rstrip('/')}/v1/messages"
                payload = {
                    "model": model_name,
                    "max_tokens": 8192,
                    "messages": [
                        {"role": "user", "content": f"系统提示：{system_prompt}\n\n用户输入：{text_content}"}
                    ]
                }
                if temperature is not None:
                    payload["temperature"] = temperature
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01"
                }
                response = requests.post(target_url, headers=headers, json=payload, timeout=180)
            else:
                # OpenAI 兼容格式
                if "/v1" in api_base_url or "/v2" in api_base_url:
                    target_url = api_base_url.rstrip('/') + "/chat/completions"
                elif api_base_url.endswith('/'):
                    target_url = api_base_url + "v1/chat/completions"
                else:
                    target_url = api_base_url.rstrip('/') + "/v1/chat/completions"

                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text_content}
                    ],
                    "max_tokens": 8192
                }
                if temperature is not None:
                    payload["temperature"] = temperature
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                response = requests.post(target_url, headers=headers, json=payload, timeout=180)

            # 处理响应
            response.raise_for_status()
            data = response.json()

            # 解析不同格式的响应
            content = None
            if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if isinstance(choice, dict) and choice.get("message", {}).get("content") is not None:
                    content = choice["message"]["content"]
            elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0:
                candidate = data["candidates"][0]
                if isinstance(candidate, dict) and candidate.get("content", {}).get("parts", [{}]) and \
                   isinstance(candidate["content"]["parts"], list) and len(candidate["content"]["parts"]) > 0 and \
                   isinstance(candidate["content"]["parts"][0], dict) and candidate["content"]["parts"][0].get("text") is not None:
                    content = candidate["content"]["parts"][0]["text"]
            elif data.get("content") and isinstance(data["content"], list) and len(data["content"]) > 0:
                part = data["content"][0]
                if isinstance(part, dict) and part.get("text") is not None:
                    content = part["text"]

            if content is not None:
                return content.strip()
            else:
                # 如果没有找到内容，记录响应数据用于调试
                print(f"警告: 无法从LLM响应中解析内容。响应: {str(data)[:500]}")
                return None

        except requests.exceptions.Timeout:
            print("错误: LLM API 请求超时 (180秒)")
            return None
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 'N/A'
            error_text = e.response.text[:200] if e.response is not None else str(e)
            print(f"错误: LLM API 请求失败 (状态码: {status_code}), 错误: {error_text}")
            return None
        except Exception as e:
            print(f"错误: 调用LLM API时发生未知错误: {str(e)}")
            print(traceback.format_exc())
            return None

    def _split_text(self, text, max_chars):
        """
        智能分割逻辑：优先按双换行(段落)->单换行->句号分割
        """
        chunks = []
        current_pos = 0
        text_len = len(text)

        while current_pos < text_len:
            end_pos = min(current_pos + max_chars, text_len)

            if end_pos < text_len:
                # 尝试找最佳分割点，避免截断句子
                split_pos = text.rfind('\n\n', current_pos, end_pos) # 找段落
                if split_pos == -1:
                    split_pos = text.rfind('\n', current_pos, end_pos) # 找行
                if split_pos == -1:
                    # 正则找句号
                    match = re.search(r'[。！？.!?]', text[current_pos:end_pos][::-1])
                    if match:
                        split_pos = end_pos - match.start()

                # 实在找不到就强制截断
                if split_pos == -1: split_pos = end_pos
            else:
                split_pos = text_len

            chunk = text[current_pos:split_pos]
            if chunk.strip(): chunks.append(chunk)
            current_pos = split_pos

        return chunks


def read_file_content(file_path):
    """
    读取文件内容，支持多种格式 (TXT/DOCX 使用本地读取，PDF/图片 使用在线 OCR)

    Args:
        file_path: 文件路径

    Returns:
        str: 文件内容文本
        str: 错误信息（如果有）
        bool: 是否为需要异步OCR处理的文件
    """
    try:
        file_path = file_path.strip('"\'')  # 去除可能的引号

        if not os.path.exists(file_path):
            return None, f"文件不存在：{file_path}", False

        # 获取文件扩展名
        _, ext = os.path.splitext(file_path.lower())

        # === 1. 文本文件 (本地读取) ===
        if ext == '.txt':
            encodings_to_try = ['utf-8', 'gbk', 'utf-16', 'ascii', 'latin-1', 'cp1252']
            for encoding in encodings_to_try:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    if content and content.strip():
                        return content, None, False
                    else:
                        return "", None, False
                except (UnicodeDecodeError, UnicodeError):
                    continue
                except Exception as e:
                    return None, f"读取文本文件时出错：{str(e)}", False
            return None, "文件编码错误，请使用UTF-8、GBK或其他常见编码的文本文件", False

        # === 2. Word 文档 (本地读取) ===
        elif ext == '.docx':
            if not DOCX_AVAILABLE:
                return None, "处理Word文档需要安装python-docx库", False
            try:
                doc = docx.Document(file_path)
                content = []
                for paragraph in doc.paragraphs:
                    if paragraph.text:
                        content.append(paragraph.text)
                return '\n'.join(content), None, False
            except Exception as e:
                return None, f"读取Word文档时出错：{str(e)}", False

        # === 3. PDF 和 图片 (使用 Dots OCR) - 返回需要异步处理标记 ===
        elif ext in ['.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp']:
            # 检查文件大小 (OCR上传通常有限制，这里设个软限制例如 20MB)
            try:
                file_size = os.path.getsize(file_path)
                if file_size > 20 * 1024 * 1024:
                    return None, f"OCR文件过大（{file_size/1024/1024:.1f}MB），建议小于20MB", False
            except:
                pass

            # 返回需要异步处理的标记
            return None, None, True

        else:
            return None, f"不支持的文件格式：{ext}。支持格式: txt, docx, pdf, jpg, png...", False

    except Exception as e:
        import traceback
        print(f"文件读取异常详情：{traceback.format_exc()}")
        return None, f"读取文件时发生未知错误：{str(e)}", False


class ContextEditDialog(QDialog):
    """Context 编辑窗口"""

    def __init__(self, title, current_text, parent=None, placeholder_text=None):
        super().__init__(parent)
        self.parent_dialog = parent
        self.setWindowTitle(title)
        self.setModal(True)

        # 使用传入的占位符文本，如果没有则根据标题确定默认提示文本
        if placeholder_text:
            self.placeholder_text = placeholder_text
        else:
            self.placeholder_text = ""
            if "专有名词" in title:
                self.placeholder_text = "角色名、地名、特殊术语..."
            elif "剧情设定" in title:
                self.placeholder_text = "输入剧情背景、世界观、人物关系等设定，或导入台本文件..."

        # 设置窗口为90%大小并居中
        if parent:
            parent_geo = parent.geometry()
            width = int(parent_geo.width() * 0.9)
            height = int(parent_geo.height() * 0.9)
            x = parent_geo.x() + (parent_geo.width() - width) // 2
            y = parent_geo.y() + (parent_geo.height() - height) // 2
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                width = int(geo.width() * 0.6)
                height = int(geo.height() * 0.6)
                x = (geo.width() - width) // 2
                y = (geo.height() - height) // 2
            else:
                width, height = 800, 600
                x, y = 100, 100

        self.setGeometry(x, y, width, height)
        self.setMinimumSize(600, 400)

        # 设置窗口属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 主容器
        container = QWidget(self)
        container.setObjectName("contextEditDialogContainer")
        container.setStyleSheet("""
            QWidget#contextEditDialogContainer {
                background-color: rgba(60, 60, 80, 240);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
        """)

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(container)

        # 内容布局
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)

        # 标题栏
        self._create_title_bar(main_layout, title)

        # 文本编辑区域
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(current_text)
        self.text_edit.setPlaceholderText(self.placeholder_text)  # 添加占位符提示
        # 修改为更深的背景色，这样白色光标会更明显
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(50, 50, 70, 220);
                border: 1px solid rgba(135, 206, 235, 80);
                border-radius: 5px;
                color: #FFFFFF;
                font-family: 'Microsoft YaHei';
                font-size: 12pt;
                font-weight: bold;
                padding: 10px;
                outline: none;
                selection-background-color: rgba(120, 195, 225, 150);
            }
            QTextEdit:focus {
                border: 2px solid rgba(135, 206, 235, 220);
                background-color: rgba(70, 70, 90, 240);
            }
        """)
        main_layout.addWidget(self.text_edit)

        # 确定按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        confirm_button = QPushButton("确定")
        confirm_button.setFixedSize(120, 40)
        confirm_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(40, 167, 69, 180), stop:1 rgba(30, 130, 55, 200));
                color: white;
                border: 1px solid rgba(40, 167, 69, 150);
                border-radius: 8px;
                font-family: '楷体';
                font-size: 15pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(40, 167, 69, 220);
            }
        """)
        confirm_button.clicked.connect(self.accept)
        button_layout.addWidget(confirm_button)

        main_layout.addLayout(button_layout)

        # 添加拖拽功能
        self.drag_pos = QPoint()
        self.is_dragging = False

    def _create_title_bar(self, layout, title):
        title_bar_layout = QHBoxLayout()

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                color: #F2EADA;
                font: bold 18px '楷体';
                padding: 5px;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_button = QPushButton("×")
        close_button.setFixedSize(32, 32)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 99, 71, 160);
                color: white;
                border: none;
                border-radius: 16px;
                font-weight: bold;
                font-family: Arial;
                font-size: 16pt;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 99, 71, 220);
            }
        """)
        close_button.clicked.connect(self.reject)

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        layout.addLayout(title_bar_layout)

    def get_text(self):
        return self.text_edit.toPlainText()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 60:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging = True
                event.accept()
            else:
                self.is_dragging = False
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)


class CloudTranscriptionDialog(QDialog):
    """云端转录设置对话框 - 最终UI优化版"""

    settings_confirmed = pyqtSignal(dict)
    
    # 用于API测试结果的信号 (按钮对象, 成功与否, 消息)
    api_test_finished = pyqtSignal(object, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("云端转录设置")
        self.setModal(True)
        # 获取父窗口的配置引用，确保可以直接修改
        self.current_settings = getattr(parent, 'cloud_transcription_settings', {})
        self.selected_audio_file_path = ""
        self.selected_audio_files = []

        # 标记是否已经点击了确定按钮，防止重复保存
        self._confirmed = False

        # API客户端实例
        self.elevenlabs_client = None
        self.soniox_client = None

        # 台本导入相关状态
        self.has_script = False
        self.script_cleaning_worker = None
        self.script_is_cleaned = False  # 标记台本是否经过LLM清洗

        # OCR处理相关状态
        self.ocr_worker = None
        self.is_ocr_processing = False
        self._pending_ocr_content = None
        self._pending_ocr_error = None

        # === 窗口尺寸配置 ===
        self.DIALOG_SIZES = {
            0: (900, 720),  # Web版（修复：从650增加到720，确保内容完整显示）
            1: (900, 800),  # API版（增加了模型选择行）
            2: (980, 850)   # Soniox版
        }

        # 窗口属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 主容器
        container = QWidget(self)
        container.setObjectName("cloudTranscriptionDialogContainer")
        container.setStyleSheet("""
            QWidget#cloudTranscriptionDialogContainer {
                background-color: rgba(60, 60, 80, 240);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
        """)

        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(container)

        # 内容布局
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)

        # 颜色定义
        self.param_label_main_color = QColor(87, 128, 183)
        self.param_label_stroke_color = QColor(242, 234, 218)

        # 构建UI
        self._create_title_bar(main_layout)
        self._create_file_selection_area(main_layout)
        self._create_provider_selection_area(main_layout)
        self._create_dynamic_config_area(main_layout)
        
        # 弹性空间
        main_layout.addStretch(1)
        
        self._create_action_buttons(main_layout)

        # 初始化逻辑
        self._initialize_settings()

        # 连接测试结果信号到槽函数
        self.api_test_finished.connect(self._show_result_safe)

        # 连接编辑按钮事件
        if hasattr(self, 'terms_edit_button'):
            self.terms_edit_button.clicked.connect(self._edit_terms)
        if hasattr(self, 'context_edit_button'):
            self.context_edit_button.clicked.connect(self._edit_context)

        # 启动时初始化尺寸策略
        QTimer.singleShot(0, lambda: self._on_provider_changed(self.provider_combo.currentIndex()))

        # 初始化时检查批量模式状态
        QTimer.singleShot(100, self._check_and_update_batch_mode_ui)

    def showEvent(self, event):
        super().showEvent(event)
        # 确保弹窗尺寸正确（修复拖拽文件打开时高度不够的问题）
        # 关键修复：先调用_on_provider_changed来设置页面策略，再更新尺寸
        idx = self.provider_combo.currentIndex()
        self._on_provider_changed(idx)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        if self.parent_window:
            geo = self.parent_window.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = (geo.width() - self.width()) // 2
                y = (geo.height() - self.height()) // 2
                self.move(x, y)

    def _update_dialog_size(self):
        """强制应用预设的尺寸"""
        idx = self.provider_combo.currentIndex()
        width, height = self.DIALOG_SIZES.get(idx, (900, 500))
        
        self.setMinimumSize(0, 0) 
        self.resize(width, height)
        self.setMinimumSize(800, 350)
        self._center_on_parent()

    def _on_provider_changed(self, index):
        """服务商切换回调"""
        self.config_stack.setCurrentIndex(index)
        # 切换时不重新加载配置，保留用户已输入的内容
        
        # 调整 StackWidget 页面策略
        for i in range(self.config_stack.count()):
            page = self.config_stack.widget(i)
            if i == index:
                page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                page.show()
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
                page.hide()

        self._update_dialog_size()

    def _create_title_bar(self, layout):
        title_bar_layout = QHBoxLayout()
        
        title_label = CustomLabel("云端转录设置")
        title_label.setCustomColors(main_color=self.param_label_main_color, stroke_color=self.param_label_stroke_color)
        title_font = QFont('楷体', 22, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_button = QPushButton()
        close_button.setFixedSize(32, 32)
        close_button.setObjectName("dialogCloseButton")
        close_button.setToolTip("关闭")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        
        icon_path = resource_path("dialog_close_normal.png")
        if icon_path and os.path.exists(icon_path):
             close_button.setIcon(QIcon(icon_path))
             close_button.setIconSize(QSize(20, 20))
        else:
            close_button.setText("×")
            
        close_button.setStyleSheet("""
            QPushButton#dialogCloseButton {
                background-color: rgba(255, 99, 71, 160); 
                color: white;
                border: none; 
                border-radius: 16px;
                font-weight: bold; 
                font-family: Arial;
                font-size: 16pt;
                padding: 0px;
            }
            QPushButton#dialogCloseButton:hover {
                background-color: rgba(255, 99, 71, 220);
            }
        """)

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        layout.addLayout(title_bar_layout)

    def _create_file_selection_area(self, layout):
        file_group = QGroupBox("音频文件")
        file_group.setStyleSheet(self._get_group_style())
        
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(8)
        file_layout.setContentsMargins(15, 25, 15, 10)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.file_path_entry = QLineEdit()
        self.file_path_entry.setPlaceholderText("请点击浏览按钮选择音频文件...") 
        self.file_path_entry.setReadOnly(True)
        self.file_path_entry.setStyleSheet(self._get_input_style())
        self.file_path_entry.setMinimumHeight(38)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedSize(90, 38)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(self._get_btn_style())
        browse_btn.clicked.connect(self._select_audio_file)

        input_layout.addWidget(self.file_path_entry)
        input_layout.addWidget(browse_btn)
        file_layout.addLayout(input_layout)

        hint_label = QLabel("📁 支持批量选择多个音频文件进行处理")
        hint_label.setStyleSheet("color: rgba(242, 234, 218, 0.9); font-size: 13px; font-weight: bold; padding-left: 2px;")
        file_layout.addWidget(hint_label)

        layout.addWidget(file_group)

    def _create_provider_selection_area(self, layout):
        group = QGroupBox("服务商")
        group.setStyleSheet(self._get_group_style())
        
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(15, 25, 15, 15)
        group_layout.setSpacing(15)

        label = CustomLabel("转录服务商:")
        label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        label.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems([
            "ElevenLabs (Web/免费) - 免费在线版",
            "ElevenLabs (API/付费) - 官方API版",
            "Soniox (API/付费) - 官方API版"
        ])
        self.provider_combo.setMinimumHeight(38)
        self.provider_combo.setStyleSheet(self._get_combo_style())
        
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        group_layout.addWidget(label)
        group_layout.addWidget(self.provider_combo, 1)
        layout.addWidget(group)

    def _create_dynamic_config_area(self, layout):
        config_group = QGroupBox("转录参数")
        config_group.setStyleSheet(self._get_group_style())
        
        group_layout = QVBoxLayout(config_group)
        group_layout.setContentsMargins(5, 20, 5, 5)

        self.config_stack = QStackedWidget()
        self.config_stack.setStyleSheet("background: transparent;")
        self.config_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        
        self._create_elevenlabs_web_config()
        self._create_elevenlabs_api_config()
        self._create_soniox_api_config()

        group_layout.addWidget(self.config_stack)
        layout.addWidget(config_group)

    def _create_elevenlabs_web_config(self):
        """Page 0: ElevenLabs Web"""
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)
        label_font = QFont('楷体', 15, QFont.Weight.Bold)

        # Row 0: 语言
        lbl_lang = CustomLabel("目标语言:")
        lbl_lang.setFont(label_font)
        lbl_lang.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.el_web_language_combo = QComboBox()
        self.el_web_language_combo.addItems([n for c, n in SUPPORTED_LANGUAGES])
        self.el_web_language_combo.setStyleSheet(self._get_combo_style())
        self.el_web_language_combo.setMinimumHeight(38)

        layout.addWidget(lbl_lang, 0, 0)
        layout.addWidget(self.el_web_language_combo, 0, 1)

        # Row 1: 人数
        lbl_spk = CustomLabel("说话人数:")
        lbl_spk.setFont(label_font)
        lbl_spk.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.el_web_speakers_spin = QSpinBox()
        self.el_web_speakers_spin.setRange(0, 10)
        self.el_web_speakers_spin.setValue(0)
        self.el_web_speakers_spin.setSuffix(" 人 (0=自动)")
        self.el_web_speakers_spin.setToolTip("0 表示自动检测说话人数")
        self.el_web_speakers_spin.setStyleSheet(self._get_input_style())
        self.el_web_speakers_spin.setMinimumHeight(38)

        layout.addWidget(lbl_spk, 1, 0)
        layout.addWidget(self.el_web_speakers_spin, 1, 1)

        # Row 2: 模型版本
        lbl_model = CustomLabel("模型版本:")
        lbl_model.setFont(label_font)
        lbl_model.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.el_web_model_combo = QComboBox()
        for model_id, display_text in ELEVENLABS_MODELS:
            self.el_web_model_combo.addItem(display_text, model_id)
        self.el_web_model_combo.setStyleSheet(self._get_combo_style())
        self.el_web_model_combo.setMinimumHeight(38)
        self.el_web_model_combo.setToolTip(
            "scribe_v2: 推荐使用，识别更精准，日语自动过滤音频事件\n"
            "scribe_v1: 旧版本，包含更多音频事件标记，可能有误判"
        )

        layout.addWidget(lbl_model, 2, 0)
        layout.addWidget(self.el_web_model_combo, 2, 1)

        # Row 3: 开关 - 放在第1列，与上方控件对齐
        self.el_web_audio_events_check = StrokeCheckBoxWidget("标记音频事件 (如 [笑声])")
        # [默认设置] 默认不勾选音频事件
        self.el_web_audio_events_check.setChecked(False)
        layout.addWidget(self.el_web_audio_events_check, 3, 1, 1, 2, Qt.AlignmentFlag.AlignLeft)

        layout.setColumnStretch(1, 1)
        layout.setRowStretch(4, 1)

        self.config_stack.addWidget(page)

    def _create_elevenlabs_api_config(self):
        """Page 1: ElevenLabs API"""
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)
        label_font = QFont('楷体', 15, QFont.Weight.Bold)

        # Row 0: API Key
        lbl_key = CustomLabel("API Key:")
        lbl_key.setFont(label_font)
        lbl_key.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        key_box = QHBoxLayout()
        key_box.setSpacing(10)
        self.el_api_key_edit = QLineEdit()
        self.el_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.el_api_key_edit.setStyleSheet(self._get_input_style())
        self.el_api_key_edit.setMinimumHeight(38)
        
        self.el_api_key_toggle = QPushButton()
        self.el_api_key_toggle.setFixedSize(38, 38)
        self._setup_eye_button(self.el_api_key_toggle)
        self.el_api_key_toggle.clicked.connect(lambda: self._toggle_visibility(self.el_api_key_edit, self.el_api_key_toggle))
        
        key_box.addWidget(self.el_api_key_edit)
        key_box.addWidget(self.el_api_key_toggle)

        layout.addWidget(lbl_key, 0, 0)
        layout.addLayout(key_box, 0, 1, 1, 3)

        # Row 1: 记住 & 测试
        self.el_api_remember_check = StrokeCheckBoxWidget("记住API密钥")
        # [默认设置] 默认勾选记住API Key
        self.el_api_remember_check.setChecked(True)
        self.el_api_test_button = QPushButton("测试连接")
        self.el_api_test_button.setFixedSize(100, 34)
        self.el_api_test_button.setStyleSheet(self._get_btn_style())
        self.el_api_test_button.clicked.connect(self._test_elevenlabs_api_connection)

        layout.addWidget(self.el_api_remember_check, 1, 1, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.el_api_test_button, 1, 3, Qt.AlignmentFlag.AlignRight)

        # Row 2: 语言 & 人数
        lbl_lang = CustomLabel("目标语言:")
        lbl_lang.setFont(label_font)
        lbl_lang.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.el_api_language_combo = QComboBox()
        self.el_api_language_combo.addItems([n for c, n in SUPPORTED_LANGUAGES])
        self.el_api_language_combo.setStyleSheet(self._get_combo_style())
        self.el_api_language_combo.setMinimumHeight(38)

        lbl_spk = CustomLabel("说话人数:")
        lbl_spk.setFont(label_font)
        lbl_spk.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        self.el_api_speakers_spin = QSpinBox()
        self.el_api_speakers_spin.setRange(0, 32)
        self.el_api_speakers_spin.setValue(0)
        self.el_api_speakers_spin.setSuffix(" 人 (0=自动)")
        self.el_api_speakers_spin.setToolTip("0 表示自动检测说话人数")
        self.el_api_speakers_spin.setStyleSheet(self._get_input_style())
        self.el_api_speakers_spin.setMinimumHeight(38)

        layout.addWidget(lbl_lang, 2, 0)
        layout.addWidget(self.el_api_language_combo, 2, 1)
        layout.addWidget(lbl_spk, 2, 2)
        layout.addWidget(self.el_api_speakers_spin, 2, 3)

        # Row 3: 模型版本
        lbl_model = CustomLabel("模型版本:")
        lbl_model.setFont(label_font)
        lbl_model.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.el_api_model_combo = QComboBox()
        for model_id, display_text in ELEVENLABS_MODELS:
            self.el_api_model_combo.addItem(display_text, model_id)
        self.el_api_model_combo.setStyleSheet(self._get_combo_style())
        self.el_api_model_combo.setMinimumHeight(38)
        self.el_api_model_combo.setToolTip(
            "scribe_v2: 推荐使用，识别更精准，日语自动过滤音频事件\n"
            "scribe_v1: 旧版本，包含更多音频事件标记，可能有误判"
        )

        layout.addWidget(lbl_model, 3, 0)
        layout.addWidget(self.el_api_model_combo, 3, 1, 1, 3)

        # Row 4: 启用说话人分离 (单独一行)
        self.el_api_diarization_check = StrokeCheckBoxWidget("启用说话人分离")
        # [默认设置] 默认不勾选说话人分离
        self.el_api_diarization_check.setChecked(False)
        layout.addWidget(self.el_api_diarization_check, 4, 1, 1, 3, Qt.AlignmentFlag.AlignLeft)

        # Row 5: 标记音频事件 (单独一行)
        self.el_api_audio_events_check = StrokeCheckBoxWidget("标记音频事件")
        # [默认设置] 默认不勾选音频事件
        self.el_api_audio_events_check.setChecked(False)
        layout.addWidget(self.el_api_audio_events_check, 5, 1, 1, 3, Qt.AlignmentFlag.AlignLeft)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        self.config_stack.addWidget(page)

    def _create_soniox_api_config(self):
        """Page 2: Soniox API"""
        page = QWidget()
        main_layout = QGridLayout(page)
        main_layout.setContentsMargins(10, 0, 10, 0)
        main_layout.setSpacing(20)
        label_font = QFont('楷体', 15, QFont.Weight.Bold)

        # Row 0: API Key (紧凑布局，无左侧空白)
        lbl_key = CustomLabel("API Key:")
        lbl_key.setFont(label_font)
        lbl_key.setCustomColors(main_color=self.param_label_main_color, stroke_color=self.param_label_stroke_color)
        lbl_key.setFixedWidth(80)  # 设置固定宽度确保对齐

        self.soniox_api_key_edit = QLineEdit()
        self.soniox_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.soniox_api_key_edit.setStyleSheet(self._get_input_style())
        self.soniox_api_key_edit.setMinimumHeight(38)

        self.soniox_api_key_toggle = QPushButton()
        self.soniox_api_key_toggle.setFixedSize(38, 38)
        self._setup_eye_button(self.soniox_api_key_toggle)
        self.soniox_api_key_toggle.clicked.connect(lambda: self._toggle_visibility(self.soniox_api_key_edit, self.soniox_api_key_toggle))

        self.soniox_api_test_button = QPushButton("测试连接")
        self.soniox_api_test_button.setFixedSize(100, 34)
        self.soniox_api_test_button.setStyleSheet(self._get_btn_style())
        self.soniox_api_test_button.clicked.connect(self._test_soniox_api_connection)

        # 将所有控件放在同一行水平布局中确保对齐
        key_box = QHBoxLayout()
        key_box.setSpacing(10)
        key_box.setContentsMargins(0,0,0,0)
        key_box.addWidget(lbl_key)  # 标签放在最左侧
        key_box.addWidget(self.soniox_api_key_edit, 1)  # 输入框占用剩余空间
        key_box.addWidget(self.soniox_api_key_toggle)  # 切换按钮
        key_box.addWidget(self.soniox_api_test_button)  # 测试按钮

        main_layout.addLayout(key_box, 0, 0, 1, 4)  # 占据整行
        
        self.soniox_api_remember_check = StrokeCheckBoxWidget("记住API密钥")
        # [默认设置] 默认勾选记住API Key
        self.soniox_api_remember_check.setChecked(True)
        # 添加左边距以与API Key输入框对齐
        remember_layout = QHBoxLayout()
        remember_layout.setContentsMargins(80, 0, 0, 0)  # 80px左边距，与API Key标签宽度一致
        remember_layout.addWidget(self.soniox_api_remember_check)
        remember_layout.addStretch()  # 添加弹性空间

        main_layout.addLayout(remember_layout, 1, 0, 1, 4)  # 占据整行

        # 左栏 - 基础设置
        left_group = QGroupBox("基础设置")
        left_group.setStyleSheet(self._get_sub_group_style())
        left_layout = QVBoxLayout(left_group)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(15, 25, 15, 15)

        lbl_hints = CustomLabel("语言提示 (可不选或多选):")
        lbl_hints.setFont(label_font)
        lbl_hints.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)
        
        self.soniox_language_list = QListWidget()
        self.soniox_language_list.setStyleSheet(self._get_list_style())
        for code, name in SONIOX_SUPPORTED_LANGUAGES[:15]:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # 默认只勾选日语
            item.setCheckState(Qt.CheckState.Checked if code == "ja" else Qt.CheckState.Unchecked)
            self.soniox_language_list.addItem(item)
        
        left_layout.addWidget(lbl_hints)
        left_layout.addWidget(self.soniox_language_list)
        
        self.soniox_diarization_check = StrokeCheckBoxWidget("启用说话人分离")
        # [默认设置] 默认不勾选说话人分离
        self.soniox_diarization_check.setChecked(False)
        left_layout.addWidget(self.soniox_diarization_check, 0, Qt.AlignmentFlag.AlignLeft)

        self.soniox_language_identification_check = StrokeCheckBoxWidget("启用语言识别")
        # [默认设置] 默认勾选语言识别
        self.soniox_language_identification_check.setChecked(True)
        left_layout.addWidget(self.soniox_language_identification_check, 0, Qt.AlignmentFlag.AlignLeft)

        # 添加分隔线
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.Shape.HLine)
        separator_line.setFrameShadow(QFrame.Shadow.Sunken)
        separator_line.setStyleSheet("color: #666666;")
        left_layout.addWidget(separator_line, 0, Qt.AlignmentFlag.AlignLeft)

        # 右栏 - Context 优化
        right_group = QGroupBox("Context 优化")
        right_group.setStyleSheet(self._get_sub_group_style())
        right_layout = QVBoxLayout(right_group)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(15, 25, 15, 15)

        # 专有名词区域 - 标签和编辑按钮在同一行
        terms_label_layout = QHBoxLayout()
        terms_label_layout.setSpacing(10)

        lbl_terms = CustomLabel("专有名词:")
        lbl_terms.setFont(label_font)
        lbl_terms.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        self.terms_edit_button = self._create_edit_button("编辑专有名词（一行一个）")

        terms_label_layout.addWidget(lbl_terms)
        terms_label_layout.addStretch()  # 将编辑按钮推到右侧
        terms_label_layout.addWidget(self.terms_edit_button)

        self.soniox_terms_edit = QTextEdit()
        self.soniox_terms_edit.setPlaceholderText("角色名、地名、特殊术语...")
        self.soniox_terms_edit.setStyleSheet(self._get_input_style())

        # 剧情设定区域 - 标签、导入按钮和编辑按钮在同一行
        ctx_label_layout = QHBoxLayout()
        ctx_label_layout.setSpacing(10)

        lbl_ctx = CustomLabel("剧情设定:")
        lbl_ctx.setFont(label_font)
        lbl_ctx.setCustomColors(self.param_label_main_color, self.param_label_stroke_color)

        # 添加导入台本按钮
        self.import_script_button = QPushButton("📂 导入台本")
        self.import_script_button.setFixedSize(150, 34)
        self.import_script_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_script_button.setStyleSheet(self._get_btn_style())
        self.import_script_button.setToolTip("导入TXT/DOCX/PDF台本文件，支持LLM智能清洗")
        self.import_script_button.clicked.connect(self._handle_import_script)

        self.context_edit_button = self._create_edit_button("编辑剧情设定")

        ctx_label_layout.addWidget(lbl_ctx)
        ctx_label_layout.addWidget(self.import_script_button)  # 添加导入按钮
        ctx_label_layout.addStretch()  # 将编辑按钮推到右侧
        ctx_label_layout.addWidget(self.context_edit_button)

        self.soniox_context_edit = QTextEdit()
        self.soniox_context_edit.setPlaceholderText("输入剧情背景、世界观、人物关系等设定，或导入台本文件...")
        self.soniox_context_edit.setStyleSheet(self._get_input_style())

        # 添加到右侧布局
        right_layout.addLayout(terms_label_layout)
        right_layout.addWidget(self.soniox_terms_edit, 1)
        right_layout.addLayout(ctx_label_layout)
        right_layout.addWidget(self.soniox_context_edit, 2)

        main_layout.addWidget(left_group, 2, 0, 1, 2)
        main_layout.addWidget(right_group, 2, 2, 1, 2)

        for i in range(4):
            main_layout.setColumnStretch(i, 1)

        self.config_stack.addWidget(page)

    def _create_action_buttons(self, layout):
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 5, 0, 10)
        button_layout.setSpacing(20)
        
        button_layout.addStretch()

        cancel_button = QPushButton("取消")
        cancel_button.setFixedSize(120, 45)
        cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_button.setStyleSheet(self._get_cancel_btn_style())
        cancel_button.clicked.connect(self.reject)
        
        confirm_button = QPushButton("确定") # 修改文字为确定
        confirm_button.setFixedSize(120, 45)  # 统一尺寸为120x45
        confirm_button.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_button.setStyleSheet(self._get_ok_btn_style())
        confirm_button.clicked.connect(self._confirm_settings)

        button_layout.addWidget(confirm_button)  # 确定按钮放在左边
        button_layout.addWidget(cancel_button)   # 取消按钮放在右边
        button_layout.addStretch()

        layout.addWidget(button_container)

    def _setup_eye_button(self, button):
        button.setStyleSheet(self._get_icon_btn_style())
        icon_path = resource_path("eye-Invisible.png")
        if icon_path and os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(22, 22))
        else:
            button.setText("🙈")

    def _toggle_visibility(self, line_edit, button):
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            icon = resource_path("eye-Visible.png")
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            icon = resource_path("eye-Invisible.png")
        
        if icon and os.path.exists(icon):
            button.setIcon(QIcon(icon))
        else:
            button.setText("👁" if line_edit.echoMode() == QLineEdit.EchoMode.Password else "🙈")

    # --- Styles ---
    def _get_group_style(self):
        return "QGroupBox { color: #F2EADA; font: bold 16px '楷体'; border: 1px solid rgba(87, 128, 183, 0.4); border-radius: 8px; margin-top: 12px; padding-top: 15px; background-color: rgba(255, 255, 255, 8); } QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 5px; color: #B34A4A; }"
    
    def _get_sub_group_style(self):
        return "QGroupBox { color: #F2EADA; font: bold 14px '楷体'; border: 2px solid rgba(87, 128, 183, 0.6); border-radius: 6px; margin-top: 10px; background-color: transparent; } QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #FF6B6B; }"
    
    def _get_input_style(self):
        # 统一所有输入框样式：背景色、字体颜色、边框颜色、字体、内边距
        return """
            QLineEdit, QSpinBox, QTextEdit { 
                background-color: rgba(255, 255, 255, 60); 
                color: #FFFFFF; 
                border: 1px solid rgba(120, 195, 225, 140); 
                border-radius: 6px; 
                padding: 5px 10px; 
                font-size: 14px; 
                font-family: 'Microsoft YaHei'; 
            } 
            QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {
                border: 2px solid rgba(120, 195, 225, 220);
                background-color: rgba(255, 255, 255, 80);
            }
            /* 确保 QTextEdit 内部没有额外边框 */
            QTextEdit { outline: none; }
        """
    
    def _get_combo_style(self):
        dropdown_arrow_path_str = resource_path('dropdown_arrow.png')
        qss_dropdown_arrow = ""
        if dropdown_arrow_path_str and os.path.exists(dropdown_arrow_path_str):
             qss_dropdown_arrow = f"url('{dropdown_arrow_path_str.replace(os.sep, '/')}')"

        # 与 _get_input_style 保持高度一致
        return f"""
            QComboBox {{
                background-color: rgba(255, 255, 255, 60);
                color: #FFFFFF;
                border: 1px solid rgba(120, 195, 225, 140);
                border-radius: 6px;
                padding: 5px 8px;
                font-family: 'Microsoft YaHei';
                font-size: 14px;
                min-height: 1.9em;
            }}
            QComboBox:hover {{
                background-color: rgba(255, 255, 255, 80);
                border-color: rgba(120, 195, 225, 180);
            }}
            QComboBox:focus {{
                background-color: rgba(255, 255, 255, 80);
                border: 2px solid rgba(120, 195, 225, 220);
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border-left: 1px solid rgba(120, 195, 225, 140);
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background-color: rgba(120, 195, 225, 120);
            }}
            QComboBox::down-arrow {{
                image: {qss_dropdown_arrow if qss_dropdown_arrow else "none"};
                width: 12px;
                height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background-color: rgba(70, 70, 90, 240);
                color: #EAEAEA;
                border: 1px solid rgba(135, 206, 235, 150);
                border-radius: 6px;
                padding: 4px;
                outline: 0px;
                selection-background-color: rgba(120, 195, 225, 200);
                font-family: 'Microsoft YaHei';
                font-size: 14px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 10px;
                min-height: 2.2em;
                border-radius: 3px;
                background-color: transparent;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 195, 225, 200), stop:1 rgba(85, 160, 190, 180));
                color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 195, 225, 120), stop:1 rgba(85, 160, 190, 100));
            }}
            QScrollBar:vertical {{
                border: none;
                background: rgba(0, 0, 0, 30);
                width: 10px;
                margin: 0px 0px 0px 0px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 80);
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 120);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

    def _get_btn_style(self):
        return """
            QPushButton {
                background-color: rgba(100, 149, 237, 170);
                color: white;
                border: 1px solid rgba(135, 206, 235, 100);
                border-radius: 6px;
                font-family: '楷体';
                font-weight: bold;
                font-size: 13pt;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: rgba(120, 169, 247, 200); }
            QPushButton:pressed { background-color: rgba(80, 129, 217, 200); }
        """
    
    def _get_cancel_btn_style(self):
        return "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(220, 53, 69, 180), stop:1 rgba(180, 40, 50, 200)); color: white; border: 1px solid rgba(220, 53, 69, 150); border-radius: 8px; font-family: '楷体'; font-size: 15pt; font-weight: bold; } QPushButton:hover { background: rgba(220, 53, 69, 220); }"
    
    def _get_ok_btn_style(self):
        return "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(40, 167, 69, 180), stop:1 rgba(30, 130, 55, 200)); color: white; border: 1px solid rgba(40, 167, 69, 150); border-radius: 8px; font-family: '楷体'; font-size: 15pt; font-weight: bold; } QPushButton:hover { background: rgba(40, 167, 69, 220); }"
    
    def _get_icon_btn_style(self):
        return "QPushButton { background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 5px; color: #DDD; font-size: 16px; } QPushButton:hover { background: rgba(255, 255, 255, 0.2); }"
    
    def _get_list_style(self):
        return "QListWidget { background-color: rgba(255, 255, 255, 0.15); border: 1px solid rgba(87, 128, 183, 0.4); border-radius: 5px; color: #F2EADA; font-size: 13px; } QListWidget::item { padding: 4px; } QListWidget::item:hover { background: rgba(255, 255, 255, 0.2); }"

    def _create_edit_button(self, tooltip_text):
        """创建编辑按钮"""
        button = QPushButton()
        button.setFixedSize(150, 34)  # 宽度拉长到1.5倍
        button.setToolTip(tooltip_text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # 使用与测试连接按钮相同的样式
        button.setStyleSheet(self._get_btn_style())
        button.setText("📝 点击编辑")
        return button

    def _edit_terms(self):
        """编辑专有名词（一行一个）"""
        current_text = self.soniox_terms_edit.toPlainText()
        # 获取当前的占位符文本
        current_placeholder = self.soniox_terms_edit.placeholderText()
        dialog = ContextEditDialog("编辑专有名词（一行一个）", current_text, self, current_placeholder)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = dialog.get_text()
            self.soniox_terms_edit.setPlainText(new_text)

    def _edit_context(self):
        """编辑剧情设定"""
        current_text = self.soniox_context_edit.toPlainText()
        # 获取当前的占位符文本
        current_placeholder = self.soniox_context_edit.placeholderText()

        # 根据当前台本状态，设置不同的标题
        if self.has_script:
            if self.script_is_cleaned:
                dialog_title = "编辑清洗后的剧情设定"
            else:
                dialog_title = "编辑上传的台本"
        else:
            dialog_title = "编辑剧情设定"

        dialog = ContextEditDialog(dialog_title, current_text, self, current_placeholder)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = dialog.get_text()
            self.soniox_context_edit.setPlainText(new_text)

    def _handle_import_script(self):
        """处理台本导入"""
        if self.has_script:
            # 当前是"取消上传"模式
            reply = QMessageBox.question(
                self, "确认操作",
                "确定移除当前台本，恢复手动编辑吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._toggle_script_mode(active=False)
                self.soniox_context_edit.clear()
                self.script_is_cleaned = False  # 重置清洗状态
        else:
            # 当前是"导入"模式
            # [修改] 增加了图片格式支持
            file_filter = "支持的文件 (*.txt *.docx *.pdf *.jpg *.jpeg *.png *.bmp);;文本文件 (*.txt);;Word文档 (*.docx);;PDF/图片(OCR) (*.pdf *.jpg *.png *.jpeg);;所有文件 (*.*)"
            # 默认打开用户的文档文件夹
            documents_path = os.path.join(os.path.expanduser("~"), "Documents")
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择台本文件", documents_path, file_filter
            )

            if file_path:
                # 读取文件内容
                content, error, needs_ocr = read_file_content(file_path)

                if needs_ocr:
                    # 需要OCR处理的文件，启动异步OCR
                    self._start_ocr_processing(file_path)
                    return

                if error:
                    QMessageBox.warning(self, "文件读取错误", error)
                    return

                # 询问用户是否使用LLM智能清洗
                reply = QMessageBox.question(
                    self, "处理方式选择",
                    "检测到台本文件。是否使用LLM智能清洗噪音？\n\n"
                    "选择\"是\"：去除拟声词、环境音效、动作指示等，保留纯净对话\n"
                    "选择\"否\"：直接使用原文内容\n\n"
                    "推荐：ASMR/广播剧台本选择\"是\"以获得更好的转录效果。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # 使用LLM清洗
                    self._start_script_cleaning(content)
                else:
                    # 直接使用原文
                    self.soniox_context_edit.setPlainText(content)
                    self.script_is_cleaned = False  # 标记为原始台本，未清洗
                    self._toggle_script_mode(active=True)

    def _start_script_cleaning(self, raw_content):
        """开始台本清洗处理"""
        # 禁用相关控件防止重复操作
        self.import_script_button.setEnabled(False)
        self.import_script_button.setText("稍等,清洗中～")

        # 获取当前LLM配置（与主窗口保持一致的方式）
        import config as app_config

        try:
            # 使用与主窗口相同的方式获取当前LLM配置
            if hasattr(self.parent_window, 'config'):
                current_profile = app_config.get_current_llm_profile(self.parent_window.config)
                if current_profile:
                    api_key = current_profile.get("api_key", "")
                    api_base_url = current_profile.get("api_base_url", DEFAULT_LLM_API_BASE_URL)
                    model_name = current_profile.get("model_name", DEFAULT_LLM_MODEL_NAME)
                    temperature = current_profile.get("temperature", DEFAULT_LLM_TEMPERATURE)

                    # 添加调试信息
                    print(f"[台本清洗] 使用用户配置: {api_base_url} / {model_name}")
                else:
                    # 如果无法获取配置，使用默认值
                    api_key = DEFAULT_LLM_API_KEY
                    api_base_url = DEFAULT_LLM_API_BASE_URL
                    model_name = DEFAULT_LLM_MODEL_NAME
                    temperature = DEFAULT_LLM_TEMPERATURE
                    print(f"[台本清洗] 无法获取用户配置，使用默认值: {api_base_url} / {model_name}")
            else:
                # 如果父窗口没有配置，使用默认值
                api_key = DEFAULT_LLM_API_KEY
                api_base_url = DEFAULT_LLM_API_BASE_URL
                model_name = DEFAULT_LLM_MODEL_NAME
                temperature = DEFAULT_LLM_TEMPERATURE
                print(f"[台本清洗] 父窗口无配置，使用默认值: {api_base_url} / {model_name}")
        except Exception:
            # 如果读取配置失败，使用默认值
            api_key = DEFAULT_LLM_API_KEY
            api_base_url = DEFAULT_LLM_API_BASE_URL
            model_name = DEFAULT_LLM_MODEL_NAME
            temperature = DEFAULT_LLM_TEMPERATURE
            print(f"[台本清洗] 配置读取异常，使用默认值: {api_base_url} / {model_name}")

        # 创建并启动清洗工作线程
        self.script_cleaning_worker = ScriptCleaningWorker(
            raw_content, api_key, api_base_url, model_name, temperature
        )
        self.script_cleaning_worker.finished.connect(self._on_script_cleaning_finished)
        self.script_cleaning_worker.error.connect(self._on_script_cleaning_error)
        self.script_cleaning_worker.start()

    def _on_script_cleaning_finished(self, cleaned_text):
        """台本清洗完成回调"""
        # 计算清洗效果
        original_length = len(self.script_cleaning_worker.raw_text)
        cleaned_length = len(cleaned_text)
        diff_chars = original_length - cleaned_length

        # 更新UI
        self.soniox_context_edit.setPlainText(cleaned_text)
        self.script_is_cleaned = True  # 标记为已清洗的台本
        self._toggle_script_mode(active=True)

        # 显示结果
        QMessageBox.information(
            self, "清洗完成",
            f"台本清洗完成！\n\n"
            f"原始长度：{original_length} 字符\n"
            f"清洗后长度：{cleaned_length} 字符\n"
            f"过滤噪音：{diff_chars} 字符\n\n"
            f"已将纯净对话文本填入剧情设定框。"
        )

        # 清理工作线程
        self.script_cleaning_worker = None

    def _on_script_cleaning_error(self, error_message):
        """台本清洗错误回调"""
        # 恢复按钮状态
        self.import_script_button.setEnabled(True)
        self.import_script_button.setText("📂 导入台本")

        # 显示错误
        QMessageBox.critical(self, "清洗失败", f"台本清洗过程出错：\n\n{error_message}")

        # 清理工作线程
        self.script_cleaning_worker = None

    def _toggle_script_mode(self, active: bool):
        """切换台本模式状态"""
        self.has_script = active
        if not active:
            self.script_is_cleaned = False  # 退出台本模式时重置清洗状态

        if active:
            # === 锁定模式 ===
            # 1. 按钮变红，功能变为"取消"
            self.import_script_button.setEnabled(True)  # 确保按钮可点击
            self.import_script_button.setText("✖ 取消上传")
            self.import_script_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 74, 74, 180);
                    color: white;
                    border: 1px solid rgba(255, 74, 74, 255);
                    border-radius: 8px;
                    font-family: '楷体';
                    font-size: 15pt;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 74, 74, 220);
                }
            """)
            self.import_script_button.setToolTip("点击移除当前台本，恢复手动编辑")

            # 2. 文本框设为只读但仍允许编辑按钮工作
            self.soniox_context_edit.setReadOnly(True)
            self.soniox_context_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(50, 50, 50, 180);
                    border: 1px solid rgba(135, 206, 235, 60);
                    border-radius: 5px;
                    color: #CCCCCC;
                    font-family: 'Microsoft YaHei';
                    font-size: 12pt;
                    font-weight: bold;
                    padding: 10px;
                }
            """)
            # 注意：编辑按钮保持启用状态，允许用户查看和修改清洗后的文本

        else:
            # === 恢复模式 ===
            # 1. 按钮变回默认蓝色/绿色
            self.import_script_button.setEnabled(True)  # 确保按钮可点击
            self.import_script_button.setText("📂 导入台本")
            self.import_script_button.setStyleSheet(self._get_btn_style())
            self.import_script_button.setToolTip("导入TXT/DOCX/PDF台本文件，支持LLM智能清洗")

            # 2. 解锁
            self.soniox_context_edit.setReadOnly(False)
            self.soniox_context_edit.setStyleSheet(self._get_input_style())
            if hasattr(self, 'context_edit_button'):
                self.context_edit_button.setEnabled(True)

    # --- 逻辑功能 ---
    def _initialize_settings(self):
        # 总是默认显示免费服务（ElevenLabs Web），但保留已保存的设置
        self.provider_combo.setCurrentIndex(0)  # 默认显示免费服务
        
        # 一次性加载所有服务商的配置到UI控件中
        self._load_all_settings_to_ui()
        
        self._update_file_display()

    def _load_all_settings_to_ui(self):
        """加载所有服务商的配置到对应的UI控件"""
        # 1. 加载 ElevenLabs API 配置
        if hasattr(self, 'el_api_key_edit'):
            self.el_api_key_edit.setText(self.current_settings.get('elevenlabs_api_key', ''))
        if hasattr(self, 'el_api_remember_check'):
            self.el_api_remember_check.setChecked(self.current_settings.get('elevenlabs_api_remember_key', True))
        if hasattr(self, 'el_api_language_combo'):
            language = self.current_settings.get('elevenlabs_api_language', 'auto')
            for i, (code, name) in enumerate(SUPPORTED_LANGUAGES):
                if code == language:
                    self.el_api_language_combo.setCurrentIndex(i)
                    break
        if hasattr(self, 'el_api_speakers_spin'):
            self.el_api_speakers_spin.setValue(self.current_settings.get('elevenlabs_api_num_speakers', 0))
        if hasattr(self, 'el_api_diarization_check'):
            self.el_api_diarization_check.setChecked(self.current_settings.get('elevenlabs_api_enable_diarization', False))
        if hasattr(self, 'el_api_audio_events_check'):
            self.el_api_audio_events_check.setChecked(self.current_settings.get('elevenlabs_api_tag_audio_events', False))
        
        # 加载付费版模型选择
        if hasattr(self, 'el_api_model_combo'):
            api_model = self.current_settings.get('elevenlabs_api_model', DEFAULT_ELEVENLABS_API_MODEL)
            for i in range(self.el_api_model_combo.count()):
                if self.el_api_model_combo.itemData(i) == api_model:
                    self.el_api_model_combo.setCurrentIndex(i)
                    break
        
        # 加载免费版模型选择
        if hasattr(self, 'el_web_model_combo'):
            web_model = self.current_settings.get('elevenlabs_web_model', DEFAULT_ELEVENLABS_WEB_MODEL)
            for i in range(self.el_web_model_combo.count()):
                if self.el_web_model_combo.itemData(i) == web_model:
                    self.el_web_model_combo.setCurrentIndex(i)
                    break

        # 2. 加载 Soniox API 配置
        if hasattr(self, 'soniox_api_key_edit'):
            self.soniox_api_key_edit.setText(self.current_settings.get('soniox_api_key', ''))
        if hasattr(self, 'soniox_api_remember_check'):
            self.soniox_api_remember_check.setChecked(self.current_settings.get('soniox_api_remember_key', True))
        
        # 3. [修改] 强制重置 Soniox 语言提示为只勾选日语
        if hasattr(self, 'soniox_language_list'):
            # 忽略保存的设置，强制默认只勾选日语
            for i in range(self.soniox_language_list.count()):
                item = self.soniox_language_list.item(i)
                code = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(Qt.CheckState.Checked if code == "ja" else Qt.CheckState.Unchecked)

        # 4. 加载 Soniox 其他配置
        if hasattr(self, 'soniox_diarization_check'):
            self.soniox_diarization_check.setChecked(self.current_settings.get('soniox_enable_speaker_diarization', False)) # [默认] False
        if hasattr(self, 'soniox_language_identification_check'):
            self.soniox_language_identification_check.setChecked(self.current_settings.get('soniox_enable_language_identification', True))

        # === 修改开始：针对 Context 相关控件，强制清空 ===
        if hasattr(self, 'soniox_terms_edit'):
            self.soniox_terms_edit.clear()  # 强制设为空字符串，不读取历史配置

        if hasattr(self, 'soniox_context_edit'):
            self.soniox_context_edit.clear()  # 强制清空剧情设定
        # === 修改结束 ===

    def update_file_display(self):
        self._update_file_display()

    def _update_file_display(self):
        if self.selected_audio_file_path:
            self.file_path_entry.setText(os.path.basename(self.selected_audio_file_path))
        elif self.selected_audio_files:
            self.file_path_entry.setText(f"已选择 {len(self.selected_audio_files)} 个音频文件")
        else:
            self.file_path_entry.clear()

    def _select_audio_file(self):
        curr_dir = os.path.dirname(self.selected_audio_file_path) if self.selected_audio_file_path else os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(self, "选择音频", curr_dir, "音频文件 (*.mp3 *.wav *.flac *.m4a *.ogg *.aac);;所有文件 (*)")
        if files:
            if len(files) == 1:
                self.selected_audio_file_path = files[0]
                self.selected_audio_files = []
            else:
                self.selected_audio_file_path = ""
                self.selected_audio_files = files
            self._update_file_display()
            # 检查并更新批量模式下的 UI 状态
            self._check_and_update_batch_mode_ui()

    def _check_and_update_batch_mode_ui(self):
        """
        [新增方法] 检查是否为批量模式，并根据用户要求更新 Soniox 界面的 UI 状态
        """
        # 1. 判断是否为批量模式
        is_batch_mode = False
        if hasattr(self, 'selected_audio_files') and self.selected_audio_files:
            is_batch_mode = len(self.selected_audio_files) > 1

        # 确保控件已初始化
        if not hasattr(self, 'soniox_context_edit'):
            return

        if is_batch_mode:
            # === 批量模式处理 ===

            # 锁定上传台本按钮
            if hasattr(self, 'import_script_button'):
                self.import_script_button.setEnabled(False)
                self.import_script_button.setText("批量模式下禁用")
                self.import_script_button.setToolTip("批量模式下已禁用特定台本导入，请手动输入通用的背景设定")
                # 设置禁用状态的灰色样式
                self.import_script_button.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(128, 128, 128, 180);
                        color: rgba(255, 255, 255, 0.7);
                        border: 1px solid rgba(128, 128, 128, 150);
                        border-radius: 6px;
                        font-family: '楷体';
                        font-weight: bold;
                        font-size: 13pt;
                        padding: 6px 12px;
                    }
                    QPushButton:hover {
                        background-color: rgba(128, 128, 128, 200);
                    }
                """)

            # 修改提示语 (Placeholder)
            self.soniox_terms_edit.setPlaceholderText(
                "⚠️ 注意：批量模式下，仅当所有文件属于同一系列时才建议填写。\n"
                "若文件无关联，请留空。"
            )
            self.soniox_context_edit.setPlaceholderText(
                "⚠️ 注意：检测到您选择了批量模式。\n"
                "1. 若多个音视频文件无关联，请勿使用此功能。\n"
                "2. 若多个音视频文件属于同一故事，请仅输入总体背景/世界观。\n"
                "3. 如需精确匹配台本，请切换回单文件处理模式。"
            )
        else:
            # === 单文件模式 (恢复正常) ===
            if hasattr(self, 'import_script_button'):
                self.import_script_button.setEnabled(True)
                self.import_script_button.setText("📂 导入台本")
                self.import_script_button.setToolTip("导入TXT/DOCX/PDF台本文件")
                # 恢复正常按钮样式
                self.import_script_button.setStyleSheet(self._get_btn_style())

            self.soniox_terms_edit.setPlaceholderText("角色名、地名、特殊术语...")
            self.soniox_context_edit.setPlaceholderText("输入剧情背景、世界观、人物关系等设定，或导入台本文件...")

    def _confirm_settings(self):
        """确认设置并开始转录"""
        if not self.selected_audio_file_path and not self.selected_audio_files:
            QMessageBox.warning(self, "警告", "请先选择音频文件")
            return
            
        self._confirmed = True  # 标记已确认

        idx = self.provider_combo.currentIndex()
        providers = [CLOUD_PROVIDER_ELEVENLABS_WEB, CLOUD_PROVIDER_ELEVENLABS_API, CLOUD_PROVIDER_SONIOX_API]
        current_provider = providers[idx]
        
        # 基于现有配置创建副本
        settings = self.current_settings.copy()
        
        # 更新通用设置
        settings.update({
            'audio_file_path': self.selected_audio_file_path,
            'audio_files': self.selected_audio_files,
            'provider': current_provider
        })

        # 1. 收集 ElevenLabs Web 数据
        if hasattr(self, 'el_web_language_combo'):
            settings.update({
                'language': SUPPORTED_LANGUAGES[self.el_web_language_combo.currentIndex()][0], # 针对Web版的当前选择
                'num_speakers': self.el_web_speakers_spin.value(),
                'tag_audio_events': self.el_web_audio_events_check.isChecked(),
                'elevenlabs_web_model': self.el_web_model_combo.currentData()  # 保存免费版模型选择
            })
            
        # 2. 收集 ElevenLabs API 数据
        if hasattr(self, 'el_api_key_edit'):
            el_key = self.el_api_key_edit.text().strip()
            el_remember = self.el_api_remember_check.isChecked()
            
            # 检查 Key (如果是当前选择的提供商)
            if current_provider == CLOUD_PROVIDER_ELEVENLABS_API and not el_key:
                self._confirmed = False
                return QMessageBox.warning(self, "警告", "请输入 ElevenLabs API Key")
            
            # 更新当前任务配置
            if current_provider == CLOUD_PROVIDER_ELEVENLABS_API:
                 settings.update({
                    'api_key': el_key,
                    'language': SUPPORTED_LANGUAGES[self.el_api_language_combo.currentIndex()][0], # 覆盖上面的 language
                    'num_speakers': self.el_api_speakers_spin.value(), # 覆盖上面的 num_speakers
                    'enable_diarization': self.el_api_diarization_check.isChecked(),
                    'tag_audio_events': self.el_api_audio_events_check.isChecked() # 覆盖上面的 tag_audio_events
                 })
            
            # 持久化保存
            settings.update({
                'elevenlabs_api_key': el_key if el_remember else "",
                'elevenlabs_api_remember_key': el_remember,
                'elevenlabs_api_language': SUPPORTED_LANGUAGES[self.el_api_language_combo.currentIndex()][0],
                'elevenlabs_api_num_speakers': self.el_api_speakers_spin.value(),
                'elevenlabs_api_enable_diarization': self.el_api_diarization_check.isChecked(),
                'elevenlabs_api_tag_audio_events': self.el_api_audio_events_check.isChecked(),
                'elevenlabs_api_model': self.el_api_model_combo.currentData()  # 保存付费版模型选择
            })

        # 3. 收集 Soniox API 数据
        if hasattr(self, 'soniox_api_key_edit'):
            sx_key = self.soniox_api_key_edit.text().strip()
            sx_remember = self.soniox_api_remember_check.isChecked()
            
            if current_provider == CLOUD_PROVIDER_SONIOX_API and not sx_key:
                self._confirmed = False
                return QMessageBox.warning(self, "警告", "请输入 Soniox API Key")

            if current_provider == CLOUD_PROVIDER_SONIOX_API:
                settings.update({
                    'api_key': sx_key,
                })
            
            hints = []
            if hasattr(self, 'soniox_language_list'):
                for i in range(self.soniox_language_list.count()):
                    item = self.soniox_language_list.item(i)
                    if item.checkState() == Qt.CheckState.Checked:
                        hints.append(item.data(Qt.ItemDataRole.UserRole))

            # === [新增] Context 8000 字符限制处理 ===
            raw_context = self.soniox_context_edit.toPlainText().strip()

            # Soniox 限制 context 长度不能超过字数限制 (通常安全值为 8000 左右)
            SONIOX_MAX_CONTEXT_LENGTH = 8000
            if len(raw_context) > SONIOX_MAX_CONTEXT_LENGTH:
                # 超出限制时提醒用户，不自动截断
                QMessageBox.warning(self, "文本长度超出限制",
                    f"当前清洗后的文本长度为 {len(raw_context)} 字符，超过了 Soniox API 的 8000 字符限制。\n\n"
                    f"建议的处理方式：\n"
                    f"1. 手动截取前 8000 字符中最重要的部分\n"
                    f"2. 将内容拆分为多个较短的文件分别处理\n"
                    f"3. 只保留关键的背景设定，分别处理台词部分\n\n"
                    f"请修改剧情设定内容后再继续。")
                truncated_context = raw_context  # 不进行截断，让用户自行处理
            else:
                truncated_context = raw_context

            # 持久化保存
            settings.update({
                'soniox_api_key': sx_key if sx_remember else "",
                'soniox_api_remember_key': sx_remember,
                'soniox_language_hints': hints,
                'soniox_enable_speaker_diarization': self.soniox_diarization_check.isChecked(),
                'soniox_enable_language_identification': self.soniox_language_identification_check.isChecked(),
                'soniox_context_terms': [t.strip() for t in self.soniox_terms_edit.toPlainText().split('\n') if t.strip()],

                # [修改] 使用处理后的 truncated_context
                'soniox_context_text': truncated_context,

                'soniox_context_general': []
            })
            
        self.settings_confirmed.emit(settings)
        self.accept()

    def _show_result_safe(self, btn, ok, msg):
        """线程安全的结果显示方法"""
        try:
            btn.setEnabled(True)
            btn.setText("测试连接")
            if ok:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.warning(self, "失败", msg)
        except Exception as e:
            try:
                btn.setEnabled(True)
                btn.setText("测试连接")
            except:
                pass

    def _test_elevenlabs_api_connection(self):
        key = self.el_api_key_edit.text().strip()
        if not key: return QMessageBox.warning(self, "警告", "请先输入API密钥")
        self.el_api_test_button.setEnabled(False); self.el_api_test_button.setText("测试中")

        def task():
            try:
                client = self.elevenlabs_client or ElevenLabsSTTClient()
                ok, msg = client.test_official_api_connection(key)
                # 使用信号发射结果到主线程
                self.api_test_finished.emit(self.el_api_test_button, ok, msg)
            except Exception as e:
                error_msg = f"测试连接异常: {e}"
                # 使用信号发射错误到主线程
                self.api_test_finished.emit(self.el_api_test_button, False, error_msg)

        import threading
        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    def _test_soniox_api_connection(self):
        key = self.soniox_api_key_edit.text().strip()
        if not key: return QMessageBox.warning(self, "警告", "请先输入API密钥")
        self.soniox_api_test_button.setEnabled(False); self.soniox_api_test_button.setText("测试中")

        def task():
            try:
                client = self.soniox_client or SonioxClient()
                ok, msg = client.test_connection(key)
                # 使用信号发射结果到主线程
                self.api_test_finished.emit(self.soniox_api_test_button, ok, msg)
            except Exception as e:
                error_msg = f"测试连接异常: {e}"
                # 使用信号发射错误到主线程
                self.api_test_finished.emit(self.soniox_api_test_button, False, error_msg)

        import threading
        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    @staticmethod
    def get_transcription_settings(current_settings, parent=None):
        d = CloudTranscriptionDialog(parent)
        if d.exec() == QDialog.DialogCode.Accepted: return d.settings_confirmed
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 60:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging_dialog = True
                event.accept()
            else:
                self.is_dragging_dialog = False
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, 'is_dragging_dialog') and self.is_dragging_dialog and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging_dialog = False
        super().mouseReleaseEvent(event)

    def reject(self):
        """点击取消或按Esc时触发，保存状态后关闭"""
        self._save_keys_to_parent()
        super().reject()

    def closeEvent(self, event):
        """点击窗口关闭按钮(X)时触发，保存状态后关闭"""
        if not self._confirmed: # 如果已经点击了确定，这里就不需要再保存了
            self._save_keys_to_parent()
        super().closeEvent(event)
        
    def _start_ocr_processing(self, file_path):
        """开始OCR处理"""
        if self.is_ocr_processing:
            QMessageBox.warning(self, "警告", "正在处理OCR，请稍候...")
            return

        # 更新按钮状态
        self.import_script_button.setEnabled(False)
        self.import_script_button.setText("🔍 OCR识别中")
        self.import_script_button.setToolTip(f"正在识别文件: {os.path.basename(file_path)}")

        # 更新按钮样式为处理中的状态
        self.import_script_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 165, 0, 180);
                color: white;
                border: 1px solid rgba(255, 165, 0, 255);
                border-radius: 8px;
                font-family: '楷体';
                font-size: 15pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 165, 0, 220);
            }
        """)

        # 设置处理状态
        self.is_ocr_processing = True

        # 创建并启动OCR工作线程
        self.ocr_worker = OCRWorker(file_path)
        self.ocr_worker.finished.connect(self._on_ocr_finished)
        self.ocr_worker.error.connect(self._on_ocr_error)
        self.ocr_worker.start()

        # 显示提示信息
        QMessageBox.information(
            self, "OCR处理已开始",
            f"正在识别文件：{os.path.basename(file_path)}\n\n"
            "这可能需要几秒到几十秒时间，请耐心等待。\n"
            "识别完成后会自动询问是否进行LLM清洗。"
        )

    def _on_ocr_finished(self, ocr_content):
        """OCR识别完成回调"""
        # 先重置状态和连接，避免重复调用
        if self.ocr_worker:
            self.ocr_worker.finished.disconnect(self._on_ocr_finished)
            self.ocr_worker.error.disconnect(self._on_ocr_error)
            self.ocr_worker = None

        # 恢复按钮状态
        self.import_script_button.setEnabled(True)
        self.import_script_button.setText("📂 导入台本")
        self.import_script_button.setStyleSheet(self._get_btn_style())
        self.import_script_button.setToolTip("导入TXT/DOCX/PDF台本文件，支持LLM智能清洗")

        # 重置处理状态
        self.is_ocr_processing = False

        print(f"[OCR] 识别成功，文本长度: {len(ocr_content)}字符")

        # 存储结果到实例变量，避免lambda作用域问题
        self._pending_ocr_content = ocr_content

        # 使用定时器延迟执行UI操作，避免线程冲突
        QTimer.singleShot(150, self._delayed_handle_ocr_result)

    def _delayed_handle_ocr_result(self):
        """延迟处理OCR结果（安全的主线程方法）"""
        # 检查窗口是否还存在
        if not hasattr(self, '_pending_ocr_content') or not self.isVisible():
            return

        # 获取存储的结果并清理
        ocr_content = self._pending_ocr_content
        self._pending_ocr_content = None

        # 调用原始处理方法
        self._handle_ocr_result(ocr_content)

    def _handle_ocr_result(self, ocr_content):
        """处理OCR结果的UI操作（在主线程中执行）"""
        # 询问用户是否使用LLM智能清洗
        reply = QMessageBox.question(
            self, "处理方式选择",
            f"OCR识别完成！文本长度：{len(ocr_content)}字符\n\n"
            "是否使用LLM智能清洗噪音？\n\n"
            "选择\"是\"：去除拟声词、环境音效、动作指示等，保留纯净对话\n"
            "选择\"否\"：直接使用OCR识别结果\n\n"
            "推荐：ASMR/广播剧台本选择\"是\"以获得更好的转录效果。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 使用LLM清洗
            self._start_script_cleaning(ocr_content)
        else:
            # 直接使用OCR结果
            self.soniox_context_edit.setPlainText(ocr_content)
            self.script_is_cleaned = False  # 标记为原始台本，未清洗
            self._toggle_script_mode(active=True)

    def _on_ocr_error(self, error_message):
        """OCR识别错误回调"""
        # 先重置状态和连接，避免重复调用
        if self.ocr_worker:
            self.ocr_worker.finished.disconnect(self._on_ocr_finished)
            self.ocr_worker.error.disconnect(self._on_ocr_error)
            self.ocr_worker = None

        # 恢复按钮状态
        self.import_script_button.setEnabled(True)
        self.import_script_button.setText("📂 导入台本")
        self.import_script_button.setStyleSheet(self._get_btn_style())
        self.import_script_button.setToolTip("导入TXT/DOCX/PDF台本文件，支持LLM智能清洗")

        # 重置处理状态
        self.is_ocr_processing = False

        # 存储错误信息到实例变量，避免lambda作用域问题
        self._pending_ocr_error = error_message

        # 延迟显示错误信息，避免线程冲突
        QTimer.singleShot(150, self._delayed_handle_ocr_error)

    def _delayed_handle_ocr_error(self):
        """延迟处理OCR错误（安全的主线程方法）"""
        # 检查窗口是否还存在
        if not hasattr(self, '_pending_ocr_error') or not self.isVisible():
            return

        # 获取存储的错误信息并清理
        error_message = self._pending_ocr_error
        self._pending_ocr_error = None

        # 显示错误信息
        QMessageBox.critical(self, "OCR识别失败", f"台本OCR识别过程出错：\n\n{error_message}")

    def _save_keys_to_parent(self):
        """将当前输入的 API Key 实时同步到父窗口配置并保存"""
        if not self.parent_window:
            return
            
        # 确保父窗口有配置字典
        if not hasattr(self.parent_window, 'cloud_transcription_settings'):
            self.parent_window.cloud_transcription_settings = {}
        
        # 直接引用父窗口的设置字典
        settings = self.parent_window.cloud_transcription_settings
        
        # 1. 保存 ElevenLabs API Key
        if hasattr(self, 'el_api_remember_check'):
            is_remember = self.el_api_remember_check.isChecked()
            settings['elevenlabs_api_remember_key'] = is_remember
            
            if hasattr(self, 'el_api_key_edit'):
                key = self.el_api_key_edit.text().strip()
                # 如果勾选记住，则保存Key；否则保存空字符串(清空)
                settings['elevenlabs_api_key'] = key if is_remember else ""
                
        # 2. 保存 Soniox API Key
        if hasattr(self, 'soniox_api_remember_check'):
            is_remember = self.soniox_api_remember_check.isChecked()
            settings['soniox_api_remember_key'] = is_remember
            
            if hasattr(self, 'soniox_api_key_edit'):
                key = self.soniox_api_key_edit.text().strip()
                # 如果勾选记住，则保存Key；否则保存空字符串(清空)
                settings['soniox_api_key'] = key if is_remember else ""
        
        # 触发父窗口保存到磁盘
        if hasattr(self.parent_window, 'save_config'):
            self.parent_window.save_config()