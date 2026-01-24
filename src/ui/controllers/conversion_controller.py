"""
转换控制器 - 管理转换任务逻辑和线程管理

该控制器封装了转换任务的业务逻辑，将其与主UI分离，
以提高代码可维护性和可测试性。
"""

import os
from typing import Dict, Any, List
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from ..conversion_worker import ConversionWorker
from utils.user_friendly_logger import user_logger
import config as app_config


class ConversionController(QObject):
    """用于管理SRT转换任务的控制器。"""

    # UI交互信号
    task_started = pyqtSignal()
    task_finished = pyqtSignal(str, bool)
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)

    def __init__(self, config_manager, elevenlabs_client, srt_processor):
        """
        初始化转换控制器。

        Args:
            config_manager: 主窗口实例，包含配置信息
            elevenlabs_client: ElevenLabs API客户端
            srt_processor: SRT处理器实例
        """
        super().__init__()
        self.config_manager = config_manager
        self.elevenlabs_client = elevenlabs_client
        self.srt_processor = srt_processor

        # 线程管理
        self.worker = None
        self.thread = None

        # 僵尸线程管理 - 防止被过早GC
        self._zombie_threads = []

    def start_single_task(self, input_path: str, output_dir: str, mode: str, free_params: Dict[str, Any] = None, source_format: str = "elevenlabs", cloud_params: Dict[str, Any] = None, enable_ai_correction: bool = False, srt_params: Dict[str, Any] = None): # <--- [新增]
        """
        启动单文件转换任务。

        Args:
            input_path: 输入文件路径
            output_dir: 输出目录
            mode: 处理模式 ("local_json", "free_transcription", "cloud_transcription")
            free_params: 免费转录参数 (旧版兼容)
            source_format: JSON文件格式 (elevenlabs, whisper, deepgram, assemblyai, elevenlabs_api, soniox)
            cloud_params: 云端转录参数
            enable_ai_correction: AI错词校对开关
        """
        self._is_batch = False
        self._srt_params = srt_params # 保存到实例变量供 worker 使用
        self._start_conversion_worker(input_path, output_dir, mode, free_params, source_format, cloud_params, enable_ai_correction, srt_params)

    def start_batch_task(self, files: List[str], output_dir: str, mode: str, free_params: Dict[str, Any] = None, source_format: str = "elevenlabs", cloud_params: Dict[str, Any] = None, enable_ai_correction: bool = False, srt_params: Dict[str, Any] = None): # <--- [新增]
        """
        启动批量转换任务。

        Args:
            files: 要处理的文件列表
            output_dir: 输出目录
            mode: 处理模式 ("local_json", "free_transcription", "cloud_transcription")
            free_params: 免费转录参数 (旧版兼容)
            source_format: JSON文件格式 (elevenlabs, whisper, deepgram, assemblyai, elevenlabs_api, soniox)
            cloud_params: 云端转录参数
            enable_ai_correction: AI错词校对开关
        """
        self._is_batch = True
        self._batch_queue = list(files)
        self._current_batch_index = 0
        self._batch_stopped = False  # 重置停止标志
        self._output_dir = output_dir
        self._cloud_params = cloud_params
        self._mode = mode
        self._free_params = free_params
        self._source_format = source_format
        self._enable_ai_correction = enable_ai_correction  # 保存AI校正设置
        self._srt_params = srt_params  # 保存到实例变量供 worker 使用

        self.log_message.emit(f"开始批量处理 {len(files)} 个文件...")
        self._process_next_batch_item()

    def _handle_worker_log_message(self, message: str):
        """
        处理来自Worker的日志消息，转换为用户友好的消息

        Args:
            message: 来自Worker的原始日志消息
        """
        # 转换为用户友好的消息
        user_friendly_message = user_logger.format_user_message(message)

        # 转发到主窗口
        self.log_message.emit(user_friendly_message)

    def stop_task(self):
        """停止当前任务。"""
        # 设置批处理停止标志
        self._batch_stopped = True

        if self.worker:
            self.worker.stop()

        if self.thread:
            try:
                # 1. 断开所有 Worker 信号，防止停止后继续向 UI 发送日志或进度
                if hasattr(self.worker, 'signals'):
                    try:
                        self.worker.signals.progress.disconnect()
                        self.worker.signals.log_message.disconnect()
                        self.worker.signals.finished.disconnect()
                    except TypeError:
                        # 忽略可能已经断开的信号
                        pass

                # 2. 将线程转移到僵尸管理，防止被 GC 销毁
                # 这是修复 Crash 的核心：在线程真正结束前，必须持有它的引用
                self._abandon_current_thread(self.thread)

                # 3. 请求线程退出事件循环
                self.thread.quit()

                # 4. 这里的引用可以安全清除了，因为 _abandon_current_thread 已经接管了引用
                self.worker = None
                self.thread = None

                self.log_message.emit("任务已转为后台清理模式，可以开始新任务")

            except Exception as e:
                self.log_message.emit(f"停止线程时发生错误: {e}")
                self.worker = None
                self.thread = None
        else:
            self.log_message.emit("没有正在运行的任务")

    def _process_next_batch_item(self):
        """处理批处理队列中的下一个项目。"""
        # 如果批处理已被停止，直接结束
        if self._batch_stopped:
            completed_count = self._current_batch_index
            total_count = len(self._batch_queue)
            self.log_message.emit(f"批量处理已停止，已完成 {completed_count}/{total_count} 个文件")
            self.task_finished.emit("任务已提前停止", False)
            return

        if self._current_batch_index >= len(self._batch_queue):
            # 根据停止状态显示不同的完成消息
            if self._batch_stopped:
                completed_count = self._current_batch_index
                total_count = len(self._batch_queue)
                self.log_message.emit(f"批量处理已停止，已完成 {completed_count}/{total_count} 个文件")
                self.task_finished.emit("任务已提前停止", False)
            else:
                self.log_message.emit("批量处理完成！")
                self.task_finished.emit("所有文件已成功处理", True)
            return

        current_file = self._batch_queue[self._current_batch_index]
        self.log_message.emit(f"正在处理 ({self._current_batch_index + 1}/{len(self._batch_queue)}): {os.path.basename(current_file)}")

        # 根据模式构建参数
        input_json = ""
        current_free_params = self._free_params.copy() if self._free_params else None
        current_cloud_params = self._cloud_params.copy() if self._cloud_params else None

        if self._mode in ["free_transcription", "cloud_transcription"]:
            if current_free_params:
                current_free_params["audio_file_path"] = current_file
            if current_cloud_params:
                current_cloud_params["audio_file_path"] = current_file
        else:
            input_json = current_file

        self._start_conversion_worker(input_json, self._output_dir, self._mode, current_free_params, self._source_format, current_cloud_params, enable_ai_correction=self._enable_ai_correction, srt_params=self._srt_params)

    def _start_conversion_worker(self, input_path: str, output_dir: str, mode: str, free_params: Dict[str, Any] = None, source_format: str = "elevenlabs", cloud_params: Dict[str, Any] = None, enable_ai_correction: bool = False, srt_params: Dict[str, Any] = None): # <--- [新增]
        """
        初始化并启动转换工作线程。

        Args:
            input_path: 输入文件路径
            output_dir: 输出目录
            mode: 处理模式 ("local_json", "free_transcription", "cloud_transcription")
            free_params: 免费转录参数 (旧版兼容)
            source_format: JSON文件格式 (elevenlabs, whisper, deepgram, assemblyai, elevenlabs_api, soniox)
            cloud_params: 云端转录参数
        """
        # 【修复】在创建新线程前，先清理前一个线程
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.log_message.emit("警告：前一个线程仍在运行，先停止它")
            try:
                # 先断开信号，防止干扰
                if hasattr(self, 'worker') and self.worker and hasattr(self.worker, 'signals'):
                    try:
                        self.worker.signals.progress.disconnect()
                        self.worker.signals.log_message.disconnect()
                        self.worker.signals.finished.disconnect()
                    except:
                        pass

                self.thread.quit()
                if not self.thread.wait(2000):  # 等待2秒
                    self.log_message.emit("强制终止前一个线程")
                    self.thread.terminate()
                    self.thread.wait(1000)
            except Exception as e:
                self.log_message.emit(f"停止前一个线程时出错: {e}")

            # 清理前一个worker的引用
            if hasattr(self, 'worker') and self.worker:
                try:
                    if hasattr(self.worker, 'deleteLater'):
                        self.worker.deleteLater()
                except:
                    pass
                self.worker = None
                self.thread = None

            # 【修复】添加短暂延迟，确保前一个线程完全清理
            import time
            time.sleep(0.1)  # 100ms延迟

        self.task_started.emit()

        # 获取当前配置的 LLM 参数
        current_profile = app_config.get_current_llm_profile(self.config_manager.config)

        # 将profile格式转换为ConversionWorker期望的格式
        api_base_url = current_profile.get("api_base_url", app_config.DEFAULT_LLM_API_BASE_URL)

        llm_config = {
            app_config.USER_LLM_API_KEY_KEY: current_profile.get("api_key", app_config.DEFAULT_LLM_API_KEY),
            app_config.USER_LLM_API_BASE_URL_KEY: api_base_url,
            app_config.USER_LLM_MODEL_NAME_KEY: current_profile.get("model_name", app_config.DEFAULT_LLM_MODEL_NAME),
            app_config.USER_LLM_TEMPERATURE_KEY: current_profile.get("temperature", app_config.DEFAULT_LLM_TEMPERATURE),
            # [FIX] 传递 API 格式，确保用户设置的格式生效
            "api_format": current_profile.get("api_format", app_config.API_FORMAT_AUTO),
            # [FIX] 传递自定义 Headers（如 Claude 的 anthropic-version）
            "custom_headers": current_profile.get("custom_headers", {})
        }

        self.thread = QThread()
        self.worker = ConversionWorker(
            input_json_path=input_path,
            output_dir=output_dir,
            srt_processor=self.srt_processor,
            source_format="elevenlabs" if mode == "free_transcription" else source_format,
            input_mode=mode,
            free_transcription_params=free_params,
            elevenlabs_stt_client=self.elevenlabs_client,
            llm_config=llm_config,
            cloud_transcription_params=cloud_params,
            enable_ai_correction=enable_ai_correction,
            srt_params=srt_params # <--- [新增] 传递给 Worker
        )
        self.worker.moveToThread(self.thread)

        # 连接信号
        self.worker.signals.progress.connect(self.progress_updated)
        self.worker.signals.log_message.connect(self._handle_worker_log_message)
        self.worker.signals.finished.connect(self._on_worker_finished)

        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _on_worker_finished(self, msg: str, success: bool):
        """
        处理 Worker 完成信号
        """
        # 获取当前正在运行的线程引用
        current_thread = None
        try:
            if hasattr(self, 'thread') and self.thread:
                current_thread = self.thread
        except:
            pass

        # ------------------- 核心修复逻辑开始 -------------------
        # 只有当完成的线程是当前控制器持有的线程时，才进行处理
        if current_thread and current_thread == self.thread:
            try:
                # 1. 先断开 Worker 的所有信号连接
                # 这一步是为了防止后续非预期的信号干扰 UI
                try:
                    if hasattr(self.worker, 'signals'):
                        self.worker.signals.progress.disconnect()
                        self.worker.signals.log_message.disconnect()
                        self.worker.signals.finished.disconnect()
                except:
                    pass

                # 2. 【关键修改】不要在这里 wait() 或直接置空导致 GC
                # 使用 _abandon_current_thread 接管线程的所有权
                # 这会把 thread 加入 _zombie_threads 列表，防止被 Python 立即回收
                # 并会自动监听 thread.finished 信号来在真正结束后清理资源
                self._abandon_current_thread(current_thread)

                # 3. 请求线程退出 (如果它还在运行循环中)
                # 对于 run() 执行完自然退出的情况，quit() 也是安全的
                if current_thread.isRunning():
                    current_thread.quit()

                # 注意：这里绝对不要调用 current_thread.wait()
                # 因为我们在主线程，如果 worker 稍微卡顿，界面就会卡死
                # 且 wait() 结束后立即销毁对象正是崩溃的根源

                # 4. 确保 worker 对象后续也能被清理
                if hasattr(self.worker, 'deleteLater'):
                    self.worker.deleteLater()

            except Exception as e:
                self.log_message.emit(f"清理完成线程时发生错误: {e}")

            # 5. 安全地移除引用
            # 因为 _abandon_current_thread 已经持有了引用，这里可以安全置 None
            self.worker = None
            self.thread = None
        # ------------------- 核心修复逻辑结束 -------------------

        # 处理业务逻辑（批处理或单任务完成）
        if self._is_batch:
            if not success:
                self.log_message.emit(f"处理失败: {msg}")
            else:
                self.log_message.emit("处理成功。")

            # 清理完成后再处理下一个项目
            self._current_batch_index += 1
            self._process_next_batch_item()
        else:
            self.task_finished.emit(msg, success)
            # 这里的额外清理逻辑已移除，统一在上方处理

    def _abandon_current_thread(self, thread_to_save):
        """
        [新增/修复] 接管将要停止的线程，防止在阻塞 I/O 期间因引用丢失导致 Crash。
        """
        if thread_to_save is None:
            return

        # 1. 增加引用计数：加入列表，确保 Python 不会回收它
        self._zombie_threads.append(thread_to_save)

        # 2. 定义清理闭包：只有当线程真正发出了 finished 信号，才从列表中移除
        def cleanup_zombie():
            try:
                if thread_to_save in self._zombie_threads:
                    self._zombie_threads.remove(thread_to_save)

                # 确保资源释放
                if thread_to_save.isRunning():
                    thread_to_save.quit()
                    thread_to_save.wait() # 此时 wait 应该是瞬间完成的

                thread_to_save.deleteLater()
                # print(f"DEBUG: 僵尸线程已安全销毁，剩余僵尸数: {len(self._zombie_threads)}")
            except Exception:
                pass

        # 3. 连接 finished 信号到清理函数
        # 注意：这里使用的是 QThread 的 finished 信号，不是 Worker 的
        try:
            thread_to_save.finished.connect(cleanup_zombie)
        except Exception:
            pass