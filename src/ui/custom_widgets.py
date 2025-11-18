from typing import Optional
import os
from PyQt6.QtWidgets import QWidget, QLabel, QCheckBox, QHBoxLayout
from PyQt6.QtGui import QPainter, QColor, QBrush, QLinearGradient, QFont
from PyQt6.QtCore import Qt, pyqtSignal
from utils.file_utils import resource_path

# --- 自定义控件 ---
class TransparentWidget(QWidget):
    """一个具有半透明背景和圆角的自定义QWidget。"""
    def __init__(self, parent: Optional[QWidget] = None, bg_color: QColor = QColor(255, 255, 255, 3)):
        super().__init__(parent)
        self.bg_color = bg_color
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 10, 10)

class CustomLabel(QLabel):
    """具有描边效果的自定义QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 默认颜色设置
        self.main_color = QColor(92, 138, 111) # 默认主文本颜色 (绿色)
        self.stroke_color = QColor(242, 234, 218) # 默认描边颜色 (白/米白色)
        # 设置透明背景
        self.setStyleSheet("background-color: transparent;")


    # 允许单独设置颜色
    def setCustomColors(self, main_color, stroke_color):
        # 支持字符串颜色值
        if isinstance(main_color, str):
            self.main_color = QColor(main_color)
        else:
            self.main_color = main_color

        if isinstance(stroke_color, str):
            self.stroke_color = QColor(stroke_color)
        else:
            self.stroke_color = stroke_color

        self.update() # 请求重新绘制以应用新颜色

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)

        # 绘制描边 (只有当描边颜色不是完全透明时才绘制)
        if self.stroke_color.alpha() > 0:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    shadow_rect = rect.translated(dx, dy)
                    painter.setPen(self.stroke_color)
                    painter.drawText(shadow_rect, self.alignment(), text)

        # 绘制主文本
        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)

class CustomLabel_title(QLabel):
    """用于标题的自定义描边QLabel。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 强制设置楷体字体
        title_font = QFont('楷体', 22, QFont.Weight.Bold)
        # 强制设置字体族，防止回退
        title_font.setStyleHint(QFont.StyleHint.SansSerif)
        title_font.setFamily('楷体')

        # 使用样式表强制设置字体，覆盖任何继承的字体设置
        self.setStyleSheet("""
            QLabel {
                font-family: '楷体', 'KaiTi', 'STKaiti', 'SimSun', serif !important;
                font-size: 22pt;
                font-weight: bold;
                background-color: transparent;
            }
        """)

        self.setFont(title_font)

        # 默认颜色设置
        self.main_color = QColor(87, 128, 183) # 默认主标题颜色 (蓝色)
        self.stroke_color = QColor(242, 234, 218) # 默认描边颜色 (白/米白色)

    # 允许单独设置颜色
    def setCustomColors(self, main_color, stroke_color):
        # 支持字符串颜色值
        if isinstance(main_color, str):
            self.main_color = QColor(main_color)
        else:
            self.main_color = main_color

        if isinstance(stroke_color, str):
            self.stroke_color = QColor(stroke_color)
        else:
            self.stroke_color = stroke_color

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.text()
        rect = self.rect()
        font = self.font()
        painter.setFont(font)

        if self.stroke_color.alpha() > 0:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    shadow_rect = rect.translated(dx, dy)
                    painter.setPen(self.stroke_color)
                    painter.drawText(shadow_rect, self.alignment(), text)

        painter.setPen(self.main_color)
        painter.drawText(rect, self.alignment(), text)
class StrokeCheckBoxWidget(QWidget):
    """具有描边文字的复选框组件"""
    toggled = pyqtSignal(bool)  # 自定义信号

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setup_ui(text, font_size=12) 

    def setup_ui(self, text, font_size=12, font_family="猫啃忘形圆"):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 获取勾选图标的正确路径
        checkmark_path = resource_path('checkmark.png')

        # 根据图标是否存在设置不同的样式
        if checkmark_path and os.path.exists(checkmark_path):
            # 使用图片背景
            checkbox_style = f"""
                QCheckBox::indicator {{
                    width: 18px;
                    height: 18px;
                    border: 2px solid #5c8a6f;
                    border-radius: 4px;
                    background-color: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background-image: url('{checkmark_path.replace(os.sep, '/')}');
                    background-position: center;
                    background-repeat: no-repeat;
                    border-color: #5c8a6f;
                }}
                QCheckBox::indicator:hover {{
                    border-color: #5c8a6f;
                }}
            """
        else:
            # 没有图标文件时使用CSS绘制的勾选标记
            checkbox_style = """
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border: 2px solid #5c8a6f;
                    border-radius: 4px;
                    background-color: transparent;
                }
                QCheckBox::indicator:checked {
                    background-color: #5c8a6f;
                    border-color: #5c8a6f;
                }
                QCheckBox::indicator:checked::after {
                    content: '✓';
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                }
                QCheckBox::indicator:hover {
                    border-color: #5c8a6f;
                }
            """

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet(checkbox_style)

        # 描边标签 - 直接传入字体大小和字体族
        self.label = CustomLabel(text)
        # 通过样式表设置字体大小、字体族、粗体和透明背景
        self.label.setStyleSheet(f"background-color: transparent; font-size: {font_size}pt; font-family: '{font_family}'; font-weight: bold;")

        self.label.setCustomColors(
            main_color=QColor(92, 138, 111),  # 与主界面"API Key"相同的颜色
            stroke_color=QColor(242, 234, 218)  # 米白色描边
        )

        layout.addWidget(self.checkbox)
        layout.addWidget(self.label)

        # 连接内部checkbox的信号到我们的自定义信号
        self.checkbox.toggled.connect(self.toggled.emit)

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, checked):
        self.checkbox.setChecked(checked)

    def text(self):
        return self.label.text()

    def setText(self, text):
        self.label.setText(text)

    def setToolTip(self, tooltip):
        self.checkbox.setToolTip(tooltip)
        self.label.setToolTip(tooltip)

    
