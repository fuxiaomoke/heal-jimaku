"""
Soniox Speech-to-Text API 客户端
支持异步转录、Context优化、多语言识别等功能
"""

import os
import json
import time
import requests
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class SonioxTranscriptionConfig:
    """Soniox转录配置"""
    api_key: str
    language_hints: List[str] = None
    enable_speaker_diarization: bool = True
    enable_language_identification: bool = True
    context_terms: List[str] = None
    context_text: str = None
    context_general: List[Dict[str, str]] = None
    model: str = "stt-async-v5"

    def __post_init__(self):
        if self.language_hints is None:
            self.language_hints = []
        if self.context_terms is None:
            self.context_terms = []
        if self.context_general is None:
            self.context_general = []

class SonioxClient:
    """Soniox Speech-to-Text API 客户端"""

    SONIOX_API_BASE_URL = "https://api.soniox.com"

    def __init__(self, signals_forwarder: Optional[Any] = None):
        self._signals = signals_forwarder
        self._session = requests.Session()

    def _emit_log(self, message: str, level: str = "info"):
        """发射日志信号"""
        if self._signals:
            if hasattr(self._signals, 'log_message'):
                self._signals.log_message.emit(f"[Soniox API] {message}")
            elif hasattr(self._signals, 'log_signal'):
                self._signals.log_signal.emit(f"[Soniox API] {message}")
        else:
            print(f"[Soniox API] {message}")

    def _emit_progress(self, current: int, total: int, message: str = ""):
        """发射进度信号"""
        if self._signals:
            percent = 0
            if total > 0:
                percent = int((current / total) * 100)

            if hasattr(self._signals, 'progress'):
                self._signals.progress.emit(percent)
            elif hasattr(self._signals, 'progress_signal'):
                self._signals.progress_signal.emit(current, total, message)

    def stop_current_task(self):
        """
        停止当前的转录任务

        Soniox API 支持通过关闭请求来取消转录任务。
        这个方法会设置停止标志并关闭活动的网络会话。
        """
        self._emit_log("收到停止当前任务的请求")

        try:
            # 关闭会话以取消正在进行的请求
            if hasattr(self._session, 'close'):
                self._session.close()
                self._emit_log("已关闭网络会话，取消正在进行的请求")

            # 创建新的会话以备后续使用
            self._session = requests.Session()

        except Exception as e:
            self._emit_log(f"停止Soniox任务时发生错误: {e}")

    def get_audio_info(self, audio_file_path: str) -> Tuple[Optional[float], Optional[int]]:
        """获取音频文件信息"""
        try:
            file_size = os.path.getsize(audio_file_path)
            try:
                from mutagen import File as MutagenFile
                audio_file = MutagenFile(audio_file_path)
                if audio_file is not None and hasattr(audio_file, 'info'):
                    duration = audio_file.info.length
                    return duration, file_size
            except Exception:
                pass
            return None, file_size
        except Exception as e:
            self._emit_log(f"获取音频信息失败: {e}")
            return None, None

    def _build_transcription_config(self, config: SonioxTranscriptionConfig,
                                   file_id: Optional[str] = None,
                                   audio_url: Optional[str] = None) -> Dict[str, Any]:
        """构建转录请求配置"""
        transcription_config = {
            "model": config.model,
            "enable_speaker_diarization": config.enable_speaker_diarization,
            "enable_language_identification": config.enable_language_identification,
        }

        if file_id:
            transcription_config["file_id"] = file_id
        elif audio_url:
            transcription_config["audio_url"] = audio_url

        if config.language_hints:
            transcription_config["language_hints"] = config.language_hints

        context = {}
        if config.context_general: context["general"] = config.context_general
        if config.context_terms: context["terms"] = config.context_terms
        if config.context_text and config.context_text.strip(): context["text"] = config.context_text.strip()

        if context: transcription_config["context"] = context

        return transcription_config

    def upload_audio_file(self, audio_file_path: str, api_key: str) -> Optional[str]:
        """上传音频文件到Soniox"""
        try:
            self._emit_log(f"开始上传音频文件: {os.path.basename(audio_file_path)}")
            self._emit_progress(1, 10, "上传音频文件")

            upload_url = f"{self.SONIOX_API_BASE_URL}/v1/files"
            headers = {"Authorization": f"Bearer {api_key}"}

            file_size = os.path.getsize(audio_file_path)
            self._emit_log(f"文件大小: {file_size / (1024*1024):.2f} MB")

            with open(audio_file_path, "rb") as f:
                files = {"file": f}
                response = self._session.post(upload_url, headers=headers, files=files, timeout=300)

            if response.status_code not in [200, 201]:
                error_msg = f"上传失败: HTTP {response.status_code} - {response.text}"
                self._emit_log(f"[Error] {error_msg}")
                return None

            result = response.json()
            file_id = result.get("id")

            if file_id:
                self._emit_log(f"文件上传成功，文件ID: {file_id}")
                self._emit_progress(3, 10, "上传完成")
                return file_id
            else:
                self._emit_log(f"[Error] 上传响应中未找到文件ID。响应: {result}")
                return None

        except Exception as e:
            self._emit_log(f"[Error] 上传音频文件异常: {e}")
            return None

    def create_transcription(self, config: SonioxTranscriptionConfig,
                           file_id: Optional[str] = None,
                           audio_url: Optional[str] = None) -> Optional[str]:
        """创建转录任务"""
        try:
            self._emit_log("创建Soniox转录任务...")
            self._emit_progress(4, 10, "创建任务")

            create_url = f"{self.SONIOX_API_BASE_URL}/v1/transcriptions"
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
            }

            transcription_config = self._build_transcription_config(
                config, file_id, audio_url
            )

            self._emit_log(f"使用配置: 模型={config.model}, 语言提示={config.language_hints}")

            response = self._session.post(
                create_url,
                headers=headers,
                json=transcription_config,
                timeout=30
            )

            if response.status_code not in [200, 201]:
                error_msg = f"创建转录失败: HTTP {response.status_code} - {response.text}"
                self._emit_log(f"[Error] {error_msg}")
                return None

            result = response.json()
            transcription_id = result.get("id")

            if transcription_id:
                self._emit_log(f"转录任务创建成功，ID: {transcription_id}")
                return transcription_id
            else:
                self._emit_log(f"[Error] 创建响应中未找到转录ID。响应: {result}")
                return None

        except Exception as e:
            self._emit_log(f"[Error] 创建转录任务异常: {e}")
            return None

    def _fetch_transcript_content(self, transcription_id: str, api_key: str) -> Optional[Dict]:
        """[关键新增] 任务完成后，单独获取 Transcript 内容"""
        try:
            self._emit_log("正在获取详细转录内容 (Transcript)...")
            # 根据文档，获取 Transcript 的端点是 /transcriptions/{id}/transcript
            transcript_url = f"{self.SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}/transcript"
            headers = {"Authorization": f"Bearer {api_key}"}

            # 这里不需要太长的超时，因为内容应该已经准备好了
            response = self._session.get(transcript_url, headers=headers, timeout=60)

            if response.status_code != 200:
                self._emit_log(f"[Error] 获取 Transcript 失败: HTTP {response.status_code} - {response.text}")
                return None
            
            transcript_data = response.json()
            # 简单的验证
            if "tokens" in transcript_data:
                token_count = len(transcript_data["tokens"])
                self._emit_log(f"成功获取 Transcript，包含 {token_count} 个 tokens")
            else:
                self._emit_log(f"[Warning] Transcript 数据中未发现 'tokens' 字段: {list(transcript_data.keys())}")

            return transcript_data

        except Exception as e:
            self._emit_log(f"[Error] 获取 Transcript 内容异常: {e}")
            return None

    def poll_transcription_result(self, transcription_id: str, api_key: str,
                                 timeout_seconds: int = 3600) -> Optional[Dict]:
        """轮询转录结果"""
        try:
            self._emit_log("开始轮询Soniox转录结果...")
            self._emit_progress(5, 10, "等待转录完成")

            # 轮询状态的URL
            status_url = f"{self.SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            start_time = time.time()
            poll_interval = 2

            while True:
                elapsed_time = time.time() - start_time

                if elapsed_time > timeout_seconds:
                    self._emit_log(f"[Error] 转录超时 ({timeout_seconds}秒)")
                    return None

                try:
                    response = self._session.get(status_url, headers=headers, timeout=30)
                except requests.RequestException as e:
                    self._emit_log(f"轮询请求网络错误: {e}，稍后重试...")
                    time.sleep(poll_interval)
                    continue

                if response.status_code != 200:
                    # 401/403/404 这种错误再试也没用
                    if response.status_code in [401, 403, 404]:
                        self._emit_log(f"[Error] 获取转录状态失败 (不可恢复): HTTP {response.status_code} - {response.text}")
                        return None
                    
                    self._emit_log(f"获取转录状态失败: HTTP {response.status_code}，稍后重试...")
                    time.sleep(poll_interval)
                    continue

                status_result = response.json()
                status = status_result.get("status")

                if status == "completed":
                    self._emit_log("Soniox转录任务状态已完成！")
                    
                    # [关键修复] 任务完成后，单独调用接口获取内容
                    transcript_content = self._fetch_transcript_content(transcription_id, api_key)
                    
                    if transcript_content:
                        # 将 transcript 的内容合并到状态结果中返回
                        # 这样外部既能看到 status 也能拿到 tokens
                        final_result = status_result.copy()
                        final_result.update(transcript_content)
                        
                        self._emit_progress(10, 10, "转录完成")
                        return final_result
                    else:
                        self._emit_log("[Error] 任务完成但无法获取 Transcript 内容")
                        return None
                        
                elif status in ["failed", "error"]:
                    error_message = status_result.get("error_message", "未知错误")
                    self._emit_log(f"[Error] 转录失败，服务器返回状态: {status}, 信息: {error_message}")
                    return None
                elif status in ["queued", "processing", "transcribing"]:
                    # 动态调整轮询间隔
                    if elapsed_time > 10 and poll_interval < 5: poll_interval = 5
                    if elapsed_time > 60 and poll_interval < 10: poll_interval = 10
                    pass
                else:
                    self._emit_log(f"未知状态: {status}")

                time.sleep(poll_interval)

        except Exception as e:
            self._emit_log(f"[Error] 轮询转录结果异常: {e}")
            import traceback
            self._emit_log(traceback.format_exc())
            return None

    def transcribe_audio_file(self, audio_file_path: str,
                            config: SonioxTranscriptionConfig) -> Optional[Dict]:
        """完整的音频文件转录流程"""
        try:
            self._emit_log(f"准备处理音频: {audio_file_path}")
            
            # 1. 获取音频信息
            duration, file_size = self.get_audio_info(audio_file_path)
            if duration:
                self._emit_log(f"音频时长: {duration:.2f}秒")

            # 2. 上传文件
            file_id = self.upload_audio_file(audio_file_path, config.api_key)
            if not file_id:
                return None

            # 3. 创建转录任务
            transcription_id = self.create_transcription(config, file_id=file_id)
            if not transcription_id:
                return None

            # 4. 轮询结果 (内部会自动调用 _fetch_transcript_content)
            result = self.poll_transcription_result(transcription_id, config.api_key)
            
            if result:
                # 添加元数据
                result["soniox_metadata"] = {
                    "file_id": file_id,
                    "transcription_id": transcription_id,
                    "audio_duration": duration,
                    "audio_file_size": file_size,
                    "config": {
                        "model": config.model,
                        "language_hints": config.language_hints,
                        "enable_speaker_diarization": config.enable_speaker_diarization
                    }
                }
                return result
            else:
                return None

        except Exception as e:
            self._emit_log(f"[Error] 音频转录流程异常: {e}")
            return None

    def delete_file(self, file_id: str, api_key: str) -> bool:
        """删除云端存储的音频文件 (DELETE /v1/files/{file_id})"""
        try:
            # ID 直接拼接在 URL 后面
            url = f"{self.SONIOX_API_BASE_URL}/v1/files/{file_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            # 使用 DELETE 方法
            response = self._session.delete(url, headers=headers)

            if response.status_code == 200:
                self._emit_log(f"✅ 云端文件 {file_id} 删除成功")
                return True
            elif response.status_code == 204:
                # 204 No Content也表示删除成功
                self._emit_log(f"✅ 云端文件 {file_id} 删除成功 (204 No Content)")
                return True
            else:
                self._emit_log(f"云端文件删除失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self._emit_log(f"删除文件异常: {e}")
            return False

    def delete_transcription(self, transcription_id: str, api_key: str) -> bool:
        """删除云端转录任务记录 (DELETE /v1/transcriptions/{transcription_id})"""
        try:
            # ID 直接拼接在 URL 后面
            url = f"{self.SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            # 使用 DELETE 方法
            response = self._session.delete(url, headers=headers)

            if response.status_code == 200:
                self._emit_log(f"✅ 云端转录记录 {transcription_id} 删除成功")
                return True
            elif response.status_code == 204:
                # 204 No Content也表示删除成功
                self._emit_log(f"✅ 云端转录记录 {transcription_id} 删除成功 (204 No Content)")
                return True
            else:
                self._emit_log(f"云端转录记录删除失败: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self._emit_log(f"删除转录记录异常: {e}")
            return False

    def test_connection(self, api_key: str) -> Tuple[bool, str]:
        """测试API连接"""
        try:
            self._emit_log("测试Soniox API连接...")

            models_url = f"{self.SONIOX_API_BASE_URL}/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = self._session.get(models_url, headers=headers, timeout=30)

            if response.status_code in [200, 201]:
                return True, "连接成功！API Key有效。"
            else:
                return False, f"连接失败: HTTP {response.status_code} - {response.text}"

        except Exception as e:
            return False, f"测试连接异常: {e}"

# 便捷函数
def create_soniox_config(api_key: str, **kwargs) -> SonioxTranscriptionConfig:
    return SonioxTranscriptionConfig(api_key=api_key, **kwargs)

def transcribe_with_soniox(audio_file_path: str, config: SonioxTranscriptionConfig,
                          signals_forwarder: Optional[Any] = None) -> Optional[Dict]:
    client = SonioxClient(signals_forwarder)
    return client.transcribe_audio_file(audio_file_path, config)