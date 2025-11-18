#!/usr/bin/env python3
"""
背景设置对话框 - 专门用于设置背景图片相关选项
采用分层权限设计，平衡功能性与简洁性
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QGroupBox, QButtonGroup, QRadioButton, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor

from ui.custom_widgets import CustomLabel_title, CustomLabel
from config import (
    USER_CUSTOM_BACKGROUND_FOLDER_KEY, USER_ENABLE_RANDOM_BACKGROUND_KEY,
    USER_FIXED_BACKGROUND_PATH_KEY,
    USER_REMEMBERED_CUSTOM_FOLDER_KEY, USER_REMEMBERED_CUSTOM_IMAGE_KEY,
    USER_BACKGROUND_SOURCE_KEY, BACKGROUND_SOURCE_USER_SELECTED, BACKGROUND_SOURCE_CAROUSEL_FIXED,
    DEFAULT_CUSTOM_BACKGROUND_FOLDER, DEFAULT_ENABLE_RANDOM_BACKGROUND,
    DEFAULT_FIXED_BACKGROUND_PATH, DEFAULT_REMEMBERED_CUSTOM_FOLDER,
    DEFAULT_REMEMBERED_CUSTOM_IMAGE, DEFAULT_BACKGROUND_SOURCE
)
from utils.file_utils import resource_path
import shutil
import sys


class BackgroundSettingsDialog(QDialog):
    """背景设置对话框，专门处理背景图片相关设置"""
    settings_applied = pyqtSignal(dict)

    def __init__(self, current_settings: dict, background_manager=None, parent=None):
        """初始化背景设置对话框"""
        super().__init__(parent)
        self.setWindowTitle("背景设置")
        self.setModal(True)
        self.current_settings = current_settings
        self.background_manager = background_manager

        # 创建用户数据目录用于保存固定背景图片
        self.user_data_dir = self._get_user_data_dir()
        self.fixed_backgrounds_dir = os.path.join(self.user_data_dir, "fixed_backgrounds")
        if not os.path.exists(self.fixed_backgrounds_dir):
            os.makedirs(self.fixed_backgrounds_dir, exist_ok=True)

        # 设置无边框窗口和半透明背景
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        container = QWidget(self)
        container.setObjectName("backgroundDialogContainer")
        container.setStyleSheet("""
            QWidget#backgroundDialogContainer {
                background-color: rgba(60, 60, 80, 220);
                                border-radius: 10px;
            }
        """)

        # 布局设置
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(18)

        # 颜色主题设置（与其他弹窗保持一致）
        self.target_main_color = QColor(87, 128, 183)  # 蓝色主题
        self.target_stroke_color = QColor(242, 234, 218)

        # 创建标题栏
        title_bar_layout = QHBoxLayout()
        title_label = CustomLabel_title("背景设置")
        title_label.setCustomColors(main_color=self.target_main_color, stroke_color=self.target_stroke_color)
        title_font = QFont('楷体', 20, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setObjectName("dialogCloseButton")
        close_button.setToolTip("关闭")
        close_button.clicked.connect(self.reject)

        title_bar_layout.addStretch()
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_button)
        main_layout.addLayout(title_bar_layout)

        # === 背景模式选择 ===
        mode_group = QGroupBox("背景模式")
        mode_group.setStyleSheet("""
            QGroupBox {
                font: bold 14pt '楷体';
                border: 2px solid rgba(87, 128, 183, 120);
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: rgba(255, 255, 255, 0.05);
                color: #B34A4A;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
            }
        """)

        mode_layout = QVBoxLayout()

        # 创建单选按钮组
        self.mode_button_group = QButtonGroup()

        # 选项1: 默认轮播
        option1_label = CustomLabel("默认背景图片轮播(推荐)")
        option1_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        option1_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.default_random_radio = QRadioButton()
        self.default_random_radio.setStyleSheet("margin: 5px;")
        self.mode_button_group.addButton(self.default_random_radio, 1)

        # 选项2: 默认固定
        option2_label = CustomLabel("使用当前的背景图片作为固定背景")
        option2_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        option2_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.default_fixed_radio = QRadioButton()
        self.default_fixed_radio.setStyleSheet("margin: 5px;")
        self.mode_button_group.addButton(self.default_fixed_radio, 2)

        # 选项3: 自定义轮播
        option3_label = CustomLabel("选择自定义文件夹轮播背景图")
        option3_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        option3_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.custom_random_radio = QRadioButton()
        self.custom_random_radio.setStyleSheet("margin: 5px;")
        self.mode_button_group.addButton(self.custom_random_radio, 3)

        # 选项4: 自定义固定
        option4_label = CustomLabel("选择自定义图片作为固定背景")
        option4_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        option4_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.custom_fixed_radio = QRadioButton()
        self.custom_fixed_radio.setStyleSheet("margin: 5px;")
        self.mode_button_group.addButton(self.custom_fixed_radio, 4)

        # 创建选项布局
        option1_layout = QHBoxLayout()
        option1_layout.addWidget(self.default_random_radio)
        option1_layout.addWidget(option1_label)
        option1_layout.addStretch()
        mode_layout.addLayout(option1_layout)

        option2_layout = QHBoxLayout()
        option2_layout.addWidget(self.default_fixed_radio)
        option2_layout.addWidget(option2_label)
        option2_layout.addStretch()
        mode_layout.addLayout(option2_layout)

        option3_layout = QHBoxLayout()
        option3_layout.addWidget(self.custom_random_radio)
        option3_layout.addWidget(option3_label)
        option3_layout.addStretch()
        mode_layout.addLayout(option3_layout)

        option4_layout = QHBoxLayout()
        option4_layout.addWidget(self.custom_fixed_radio)
        option4_layout.addWidget(option4_label)
        option4_layout.addStretch()
        mode_layout.addLayout(option4_layout)

        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)

        # === 自定义设置区域 ===
        custom_group = QGroupBox("自定义设置")
        custom_group.setStyleSheet("""
            QGroupBox {
                font: bold 14pt '楷体';
                border: 2px solid rgba(87, 128, 183, 120);
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
                background-color: rgba(255, 255, 255, 0.05);
                color: #B34A4A;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
            }
        """)

        custom_layout = QVBoxLayout()

        # 自定义文件夹路径
        folder_layout = QHBoxLayout()
        folder_label = CustomLabel("自定义文件夹:")
        folder_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        folder_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.custom_folder_edit = QLineEdit()
        # 从记忆的路径恢复，如果没有则从当前使用的路径恢复
        remembered_folder = self.current_settings.get(USER_REMEMBERED_CUSTOM_FOLDER_KEY, DEFAULT_REMEMBERED_CUSTOM_FOLDER)
        current_folder = self.current_settings.get(USER_CUSTOM_BACKGROUND_FOLDER_KEY, DEFAULT_CUSTOM_BACKGROUND_FOLDER)
        folder_to_display = remembered_folder if remembered_folder else current_folder
        self.custom_folder_edit.setText(folder_to_display)
        self.custom_folder_edit.setPlaceholderText("选择包含图片的文件夹...")
        # 初始样式将在_update_custom_ui_state中设置

        self.browse_folder_button = QPushButton("浏览...")
        self.browse_folder_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(70, 130, 220, 170);
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(107, 148, 203, 200);
            }
            QPushButton:pressed {
                background-color: rgba(67, 108, 163, 200);
            }
        """)
        self.browse_folder_button.clicked.connect(self._browse_background_folder)

        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.custom_folder_edit, 1)
        folder_layout.addWidget(self.browse_folder_button)

        custom_layout.addLayout(folder_layout)

        # 自定义固定图片路径
        custom_fixed_layout = QHBoxLayout()
        custom_fixed_label = CustomLabel("自定义固定图片:")
        custom_fixed_label.setFont(QFont('楷体', 16, QFont.Weight.Bold))
        custom_fixed_label.setCustomColors("#5C8A6F", self.target_stroke_color)

        self.custom_image_edit = QLineEdit()
        self.custom_image_edit.setPlaceholderText("选择单张图片作为固定背景...")
        # 初始样式将在_update_custom_ui_state中设置

        self.browse_image_button = QPushButton("选择图片...")
        self.browse_image_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(70, 130, 220, 170);
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(107, 148, 203, 200);
            }
            QPushButton:pressed {
                background-color: rgba(67, 108, 163, 200);
            }
        """)
        self.browse_image_button.clicked.connect(self._browse_custom_image)

        custom_fixed_layout.addWidget(custom_fixed_label)
        custom_fixed_layout.addWidget(self.custom_image_edit, 1)
        custom_fixed_layout.addWidget(self.browse_image_button)
        custom_layout.addLayout(custom_fixed_layout)

        # 从记忆的路径恢复固定图片路径
        remembered_image = self.current_settings.get(USER_REMEMBERED_CUSTOM_IMAGE_KEY, DEFAULT_REMEMBERED_CUSTOM_IMAGE)
        current_image = self.current_settings.get(USER_FIXED_BACKGROUND_PATH_KEY, DEFAULT_FIXED_BACKGROUND_PATH)
        image_to_display = remembered_image if remembered_image else current_image
        if image_to_display:
            self.custom_image_edit.setText(image_to_display)
            # 验证图片是否还存在
            if not os.path.exists(image_to_display):
                self.custom_image_edit.setStyleSheet(self.custom_image_edit.styleSheet() + """
                    QLineEdit {
                        background-color: rgba(255, 100, 100, 0.1);
                        color: rgba(255, 200, 200, 0.8);
                    }
                """)

        # 提示信息 - 移到自定义设置标题下方
        custom_group_layout = QVBoxLayout()
        custom_group_layout.setSpacing(15)

        # 提示信息
        info_label = CustomLabel("支持图片格式：PNG, JPG, JPEG, BMP, GIF | 文件夹为空时将使用默认背景")
        info_label.setFont(QFont('楷体', 12, QFont.Weight.Normal))
        info_label.setCustomColors("#5C8A6F", self.target_stroke_color)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        custom_layout.addWidget(info_label)

        custom_group.setLayout(custom_layout)
        main_layout.addWidget(custom_group)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.addStretch()

        self.confirm_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")

        button_style = """
            QPushButton {
                background-color: rgba(70, 130, 220, 170);
                color: white;
                border: none;
                border-radius: 6px;
                font-family: '楷体';
                font-weight: bold;
                font-size: 14pt;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: rgba(107, 148, 203, 200);
            }
            QPushButton:pressed {
                background-color: rgba(67, 108, 163, 200);
            }
        """

        self.confirm_button.setStyleSheet(button_style)
        self.cancel_button.setStyleSheet(button_style)

        self.confirm_button.clicked.connect(self.accept_settings)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.confirm_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # 初始化UI状态
        self._initialize_ui_state()

        self.resize(900, 576)

        # 设置整体样式，包括关闭按钮
        style = """
            QPushButton#dialogCloseButton {
                background-color: rgba(255, 99, 71, 160);
                color: white;
                border: none;
                border-radius: 15px;
                font-weight: bold;
                font-family: Arial, sans-serif;
                font-size: 14pt;
                padding: 0px;
                min-width: 30px; max-width:30px;
                min-height:30px; max-height:30px;
            }
            QPushButton#dialogCloseButton:hover {
                background-color: rgba(255, 99, 71, 200);
            }
        """
        self.setStyleSheet(style)

    def _get_user_data_dir(self) -> str:
        """获取用户数据目录路径"""
        home_dir = os.path.expanduser("~")
        app_data_dir = os.path.join(home_dir, ".heal_jimaku")
        if not os.path.exists(app_data_dir):
            os.makedirs(app_data_dir, exist_ok=True)
        return app_data_dir

    def _is_temp_path(self, path: str) -> bool:
        """检查路径是否为临时路径（PyInstaller的_MEIPASS）"""
        try:
            # 检查是否在PyInstaller的临时目录中
            meipass_base = sys._MEIPASS  # type: ignore
            return os.path.commonpath([path, meipass_base]) == meipass_base
        except AttributeError:
            # 开发环境下不是临时路径
            return False

    def _copy_temp_background_to_permanent(self, temp_path: str) -> str:
        """
        将临时背景图片复制到永久位置

        Args:
            temp_path: 临时路径

        Returns:
            str: 永久保存的路径
        """
        if not temp_path or not os.path.exists(temp_path):
            return temp_path

        # 如果不是临时路径，直接返回原路径
        if not self._is_temp_path(temp_path):
            return temp_path

        # 生成唯一的文件名，避免冲突
        original_name = os.path.basename(temp_path)
        name, ext = os.path.splitext(original_name)
        timestamp = str(int(os.path.getmtime(temp_path)))
        unique_name = f"{name}_{timestamp}{ext}"
        permanent_path = os.path.join(self.fixed_backgrounds_dir, unique_name)

        try:
            # 复制文件到永久位置
            shutil.copy2(temp_path, permanent_path)
            return permanent_path
        except Exception as e:
            print(f"警告：无法复制临时背景图片到永久位置: {e}")
            # 如果复制失败，返回原路径
            return temp_path

    def _cleanup_permanent_backgrounds(self, new_fixed_path: str = ""):
        """
        清理永久背景文件夹中不再使用的图片

        Args:
            new_fixed_path: 新的固定背景路径（如果有），不会被清理
        """
        try:
            if not os.path.exists(self.fixed_backgrounds_dir):
                return

            # 获取当前设置中的固定背景路径
            current_fixed_path = self.current_settings.get(USER_FIXED_BACKGROUND_PATH_KEY, "")

            # 遍历永久文件夹中的所有文件
            for filename in os.listdir(self.fixed_backgrounds_dir):
                file_path = os.path.join(self.fixed_backgrounds_dir, filename)
                if os.path.isfile(file_path):
                    # 如果这个文件不是当前使用的固定背景，也不是即将使用的固定背景，则删除
                    if file_path != current_fixed_path and file_path != new_fixed_path:
                        try:
                            os.remove(file_path)
                            print(f"已清理不再使用的固定背景图片: {filename}")
                        except Exception as e:
                            print(f"清理背景图片失败 {filename}: {e}")
        except Exception as e:
            print(f"清理永久背景文件夹时出错: {e}")

    def _is_permanent_background(self, path: str) -> bool:
        """检查路径是否为永久背景文件夹中的文件"""
        if not path:
            return False
        try:
            return os.path.commonpath([path, self.fixed_backgrounds_dir]) == self.fixed_backgrounds_dir
        except ValueError:
            return False

    def _initialize_ui_state(self):
        """根据当前设置初始化UI状态"""
        enable_random = self.current_settings.get(USER_ENABLE_RANDOM_BACKGROUND_KEY, DEFAULT_ENABLE_RANDOM_BACKGROUND)
        custom_folder = self.current_settings.get(USER_CUSTOM_BACKGROUND_FOLDER_KEY, DEFAULT_CUSTOM_BACKGROUND_FOLDER)
        fixed_background_path = self.current_settings.get(USER_FIXED_BACKGROUND_PATH_KEY, DEFAULT_FIXED_BACKGROUND_PATH)
        background_source = self.current_settings.get(USER_BACKGROUND_SOURCE_KEY, DEFAULT_BACKGROUND_SOURCE)

        # 记忆的路径用于UI恢复
        remembered_custom_folder = self.current_settings.get(USER_REMEMBERED_CUSTOM_FOLDER_KEY, "")
        remembered_custom_image = self.current_settings.get(USER_REMEMBERED_CUSTOM_IMAGE_KEY, "")

        # 恢复用户输入的路径
        if remembered_custom_folder:
            self.custom_folder_edit.setText(remembered_custom_folder)
        if remembered_custom_image:
            self.custom_image_edit.setText(remembered_custom_image)

        # 根据设置选择对应模式
        if custom_folder and custom_folder.strip() and enable_random:
            # 有自定义文件夹且启用轮播 -> 自定义轮播模式 (第3选项)
            self.custom_random_radio.setChecked(True)
        elif fixed_background_path and fixed_background_path.strip():
            # 有固定背景路径 -> 需要根据背景来源判断显示哪个选项
            if background_source == BACKGROUND_SOURCE_USER_SELECTED:
                # 用户手动选择的自定义图片 -> 自定义固定图片模式 (第4选项)
                self.custom_fixed_radio.setChecked(True)
            else:
                # 从轮播中固定的图片 -> 固定当前图片模式 (第2选项)
                self.default_fixed_radio.setChecked(True)
        else:
            # 没有固定背景 -> 根据enable_random选择默认模式
            if enable_random:
                # 默认轮播模式 (第1选项)
                self.default_random_radio.setChecked(True)
            else:
                # 默认固定模式 (第2选项)
                self.default_fixed_radio.setChecked(True)

        # 启用/禁用自定义设置区域
        self._update_custom_ui_state()

        # 连接信号
        self.mode_button_group.buttonClicked.connect(self._on_mode_changed)

    def _on_mode_changed(self):
        """模式改变时更新UI状态"""
        self._update_custom_ui_state()

    def _update_custom_ui_state(self):
        """更新自定义设置的启用状态"""
        is_custom_fixed_mode = self.custom_fixed_radio.isChecked()
        is_custom_random_mode = self.custom_random_radio.isChecked()

        # 文件夹选择控件（仅在自定义轮播模式下启用）
        self.custom_folder_edit.setEnabled(is_custom_random_mode)
        self.browse_folder_button.setEnabled(is_custom_random_mode)

        # 自定义图片选择控件（仅在自定义固定模式下启用）
        self.custom_image_edit.setEnabled(is_custom_fixed_mode)
        self.browse_image_button.setEnabled(is_custom_fixed_mode)

        if is_custom_random_mode:
            self.custom_folder_edit.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(255, 255, 255, 0.15);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.4);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 11pt;
                }
                QLineEdit:focus {
                    border-color: rgba(87, 128, 183, 0.8);
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """)
            self.browse_folder_button.setEnabled(True)
        else:
            self.custom_folder_edit.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(255, 255, 255, 0.05);
                                        color: rgba(255, 255, 255, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 11pt;
                }
            """)
            self.browse_folder_button.setEnabled(False)

        # 设置自定义图片选择框的样式
        if is_custom_fixed_mode:
            self.custom_image_edit.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(255, 255, 255, 0.15);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.4);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 11pt;
                }
                QLineEdit:focus {
                    border-color: rgba(87, 128, 183, 0.8);
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """)
        else:
            self.custom_image_edit.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(255, 255, 255, 0.05);
                                        color: rgba(255, 255, 255, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 11pt;
                }
            """)

    def _browse_background_folder(self):
        """浏览并选择自定义背景文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择背景文件夹",
            self.custom_folder_edit.text() or os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.custom_folder_edit.setText(folder)

    def _browse_custom_image(self):
        """浏览并选择自定义固定背景图片"""
        file_filter = "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择背景图片",
            self.custom_image_edit.text() or os.path.expanduser("~"),
            file_filter
        )
        if file_path:
            # 验证选择的文件是否是有效图片
            try:
                from PyQt6.QtGui import QPixmap
                pixmap = QPixmap(file_path)
                if pixmap.isNull():
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "无效图片", "选择的文件不是有效的图片格式，请重新选择。")
                    return
            except Exception:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "加载失败", f"无法加载图片文件：{file_path}")
                return

            # 验证通过，设置路径
            self.custom_image_edit.setText(file_path)
            # 重置样式为正常状态
            self.custom_image_edit.setStyleSheet("""
                QLineEdit {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 11pt;
                }
                QLineEdit:focus {
                    border-color: rgba(87, 128, 183, 0.8);
                    background-color: rgba(255, 255, 255, 0.15);
                }
            """)

    def accept_settings(self):
        """应用设置并关闭对话框"""
        # 总是保存用户输入的所有路径（路径记忆功能）
        saved_custom_folder = self.custom_folder_edit.text().strip()
        saved_custom_image = self.custom_image_edit.text().strip()

        # 根据选择的模式确定设置
        if self.default_random_radio.isChecked():
            # 默认轮播 - 不设置固定背景路径，并清理永久背景图片
            self._cleanup_permanent_backgrounds()

            background_settings = {
                USER_ENABLE_RANDOM_BACKGROUND_KEY: True,
                USER_CUSTOM_BACKGROUND_FOLDER_KEY: "",  # 默认模式不使用自定义文件夹
                USER_FIXED_BACKGROUND_PATH_KEY: "",  # 轮播模式下不设置固定背景
                # 保存用户输入的路径用于UI恢复
                USER_REMEMBERED_CUSTOM_FOLDER_KEY: saved_custom_folder,
                USER_REMEMBERED_CUSTOM_IMAGE_KEY: saved_custom_image
            }
        elif self.default_fixed_radio.isChecked():
            # 固定当前背景 - 检查是否已经使用自定义图片固定
            current_background_source = self.current_settings.get(USER_BACKGROUND_SOURCE_KEY, DEFAULT_BACKGROUND_SOURCE)
            current_fixed_path = self.current_settings.get(USER_FIXED_BACKGROUND_PATH_KEY, DEFAULT_FIXED_BACKGROUND_PATH)

            if current_background_source == BACKGROUND_SOURCE_USER_SELECTED and current_fixed_path:
                # 已经是自定义图片固定模式 - 第2选项是无意义的，保持原来的状态
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "提示", "您已经选择了自定义图片固定模式。")
                # 恢复原来的UI状态（第4选项）
                self.custom_fixed_radio.setChecked(True)
                return

            # 否则，固定当前背景图片
            fixed_background_path = ""
            if self.background_manager and self.background_manager.last_background_path:
                fixed_background_path = self.background_manager.last_background_path
                # 检查并处理临时路径
                fixed_background_path = self._copy_temp_background_to_permanent(fixed_background_path)

            # 清理不再使用的永久背景图片，但保留当前选择的图片
            self._cleanup_permanent_backgrounds(fixed_background_path)

            background_settings = {
                USER_ENABLE_RANDOM_BACKGROUND_KEY: False,
                USER_CUSTOM_BACKGROUND_FOLDER_KEY: "",  # 默认模式不使用自定义文件夹
                USER_FIXED_BACKGROUND_PATH_KEY: fixed_background_path,
                USER_BACKGROUND_SOURCE_KEY: BACKGROUND_SOURCE_CAROUSEL_FIXED,  # 从轮播中固定的图片
                # 保存用户输入的路径用于UI恢复
                USER_REMEMBERED_CUSTOM_FOLDER_KEY: saved_custom_folder,
                USER_REMEMBERED_CUSTOM_IMAGE_KEY: saved_custom_image
            }
        elif self.custom_random_radio.isChecked():
            # 自定义轮播 - 验证文件夹选择
            custom_folder_path = self.custom_folder_edit.text().strip()

            if not custom_folder_path:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "请选择文件夹", "请先选择一个包含图片的文件夹作为自定义轮播背景。")
                return

            if not os.path.exists(custom_folder_path):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "文件夹不存在", f"选择的文件夹不存在：\n{custom_folder_path}")
                return

            if not os.path.isdir(custom_folder_path):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "路径不是文件夹", f"选择的路径不是文件夹：\n{custom_folder_path}")
                return

            # 验证文件夹中是否包含图片
            from .background_manager import BackgroundManager
            temp_manager = BackgroundManager()
            is_valid, error_message, image_count = temp_manager.validate_background_folder(custom_folder_path)

            if not is_valid:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "文件夹无效", f"选择的文件夹无效：\n{error_message}")
                return

            # 自定义轮播模式 - 清理永久背景图片
            self._cleanup_permanent_backgrounds()

            # 验证通过，创建设置
            background_settings = {
                USER_ENABLE_RANDOM_BACKGROUND_KEY: True,
                USER_CUSTOM_BACKGROUND_FOLDER_KEY: custom_folder_path,  # 使用当前选择的文件夹
                USER_FIXED_BACKGROUND_PATH_KEY: "",
                USER_BACKGROUND_SOURCE_KEY: BACKGROUND_SOURCE_CAROUSEL_FIXED,  # 从轮播中固定的图片
                # 保存用户输入的路径用于UI恢复
                USER_REMEMBERED_CUSTOM_FOLDER_KEY: custom_folder_path,  # 当前就是保存的路径
                USER_REMEMBERED_CUSTOM_IMAGE_KEY: saved_custom_image
            }
        else:
            # 自定义固定 - 验证图片选择
            custom_image_path = self.custom_image_edit.text().strip()

            if not custom_image_path:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "请选择图片", "请先选择一张图片作为固定背景。")
                return

            if not os.path.exists(custom_image_path):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "图片不存在", f"选择的图片文件不存在：\n{custom_image_path}")
                return

            # 验证是否为有效图片
            try:
                from PyQt6.QtGui import QPixmap
                pixmap = QPixmap(custom_image_path)
                if pixmap.isNull():
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "无效图片", "选择的文件不是有效的图片格式，请重新选择。")
                    return
            except Exception:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "加载失败", f"无法加载图片文件：\n{custom_image_path}")
                return

            # 自定义固定模式 - 清理不再使用的永久背景图片，但保留当前选择的图片（如果它是永久图片）
            self._cleanup_permanent_backgrounds(custom_image_path)

            # 验证通过，创建设置
            background_settings = {
                USER_ENABLE_RANDOM_BACKGROUND_KEY: False,
                USER_CUSTOM_BACKGROUND_FOLDER_KEY: "",  # 自定义固定模式不使用自定义文件夹
                USER_FIXED_BACKGROUND_PATH_KEY: custom_image_path,
                USER_BACKGROUND_SOURCE_KEY: BACKGROUND_SOURCE_USER_SELECTED,  # 用户手动选择的自定义图片
                # 保存用户输入的路径用于UI恢复
                USER_REMEMBERED_CUSTOM_FOLDER_KEY: saved_custom_folder,
                USER_REMEMBERED_CUSTOM_IMAGE_KEY: custom_image_path  # 当前就是保存的路径
            }

        # 发送设置应用信号
        self.settings_applied.emit(background_settings)
        self.accept()

    def mousePressEvent(self, event):
        """鼠标按下事件，用于窗口拖拽功能"""
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 40:
                self.drag_pos = event.globalPosition().toPoint()
                self.is_dragging_dialog = True
                event.accept()
            else:
                self.is_dragging_dialog = False
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件，实现窗口拖拽"""
        if hasattr(self, 'is_dragging_dialog') and self.is_dragging_dialog and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件，结束窗口拖拽"""
        if hasattr(self, 'is_dragging_dialog'):
            self.is_dragging_dialog = False
        super().mouseReleaseEvent(event)