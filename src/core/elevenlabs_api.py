"""
ElevenLabs API 客户端模块

提供音频转文字服务的API客户端实现，支持多种音频格式的转录处理。
包含文件信息获取、API请求处理、错误处理等功能。

作者: fuxiaomoke
版本: 0.2.2.0
"""

import requests
import json
import os
import time
import random
import wave
from typing import Optional, Any, Dict, List, Tuple

from mutagen import File as MutagenFile

# ElevenLabs API 常量定义
# 根据官方文档，STT端点为 /v1/speech-to-text
ELEVENLABS_STT_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"

DEFAULT_STT_MODEL_ID = "scribe_v2"  # 默认使用的转录模型ID（推荐 v2）
DEFAULT_ELEVENLABS_WEB_MODEL = "scribe_v2"  # 免费版默认模型
DEFAULT_ELEVENLABS_API_MODEL = "scribe_v2"  # 付费版默认模型

# 可用模型列表 (value, display_text)
ELEVENLABS_MODELS = [
    ("scribe_v2", "scribe_v2 (推荐，更精准)"),
    ("scribe_v1", "scribe_v1 (旧版本)")
]

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/123.0.2420.97"
]

# 默认Accept-Language列表
DEFAULT_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,ja;q=0.6",
    "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,ja;q=0.5"
]

class ElevenLabsSTTClient:
    """
    ElevenLabs语音转文本API客户端
    """
    def __init__(self, signals_forwarder: Optional[Any] = None):
        self._signals = signals_forwarder

    def _log(self, message: str):
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(f"[ElevenLabs API] {message}")
        else:
            print(f"[ElevenLabs API] {message}")

    def _is_worker_running(self) -> bool:
        if self._signals and hasattr(self._signals, 'parent') and \
           hasattr(self._signals.parent(), 'is_running'):
            return self._signals.parent().is_running
        return True
    
    def _convert_brackets(self, text: str) -> str:
        """
        将方括号转换为圆括号
        [event] → (event)
        
        用于统一 v2 模型的音频事件格式，使其与 v1 保持一致
        
        Args:
            text: 包含方括号的文本
            
        Returns:
            转换后的文本，所有 [event] 变为 (event)
        """
        import re
        return re.sub(r'\[([^\]]+)\]', r'(\1)', text)
    
    def _normalize_v2_audio_events(self, response_data: dict, model_id: str) -> dict:
        """
        将 v2 的音频事件格式 [event] 转换为 v1 格式 (event)
        
        这样可以保持与现有系统的兼容性，无需修改提示词和处理逻辑
        
        Args:
            response_data: API 响应数据
            model_id: 使用的模型ID
            
        Returns:
            格式化后的响应数据
        """
        # 只对 v2 模型进行转换
        if model_id != "scribe_v2":
            return response_data
        
        try:
            # 转换 text 字段
            if "text" in response_data and isinstance(response_data["text"], str):
                response_data["text"] = self._convert_brackets(response_data["text"])
            
            # 转换 words 数组中每个词的 text 字段
            if "words" in response_data and isinstance(response_data["words"], list):
                for word in response_data["words"]:
                    if isinstance(word, dict) and "text" in word and isinstance(word["text"], str):
                        word["text"] = self._convert_brackets(word["text"])
            
            # 标记已进行格式转换
            if "elevenlabs_api_metadata" not in response_data:
                response_data["elevenlabs_api_metadata"] = {}
            response_data["elevenlabs_api_metadata"]["format_normalized"] = True
            
        except Exception as e:
            self._log(f"警告: 格式转换失败: {e}，使用原始响应")
            # 继续使用原始响应，不中断流程
        
        return response_data

    def stop_current_task(self):
        """
        停止当前的转录任务

        目前ElevenLabs API不支持直接取消正在进行的请求，
        但我们可以设置标志位来标记任务应该被停止。
        实际的取消会在下一个检查点进行。
        """
        self._log("收到停止当前任务的请求")

        # 注意：ElevenLabs API目前不直接支持请求取消
        # 这个方法主要用于记录和未来扩展
        # 实际的停止效果依赖于 _is_worker_running() 检查

    def get_audio_info(self, audio_file_path: str) -> Tuple[Optional[float], Optional[float]]:
        """获取音频文件的时长和大小"""
        duration_seconds: Optional[float] = None
        file_size_mb: Optional[float] = None
        try:
            if not os.path.exists(audio_file_path):
                self._log(f"错误: 音频文件未找到: {audio_file_path}")
                return None, None

            file_size_bytes = os.path.getsize(audio_file_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            try:
                audio_info = MutagenFile(audio_file_path)
                if audio_info and hasattr(audio_info, 'info') and hasattr(audio_info.info, 'length'):
                    duration_seconds = float(audio_info.info.length)
            except Exception:
                pass

            # 回退到wave模块
            if duration_seconds is None and audio_file_path.lower().endswith(".wav"):
                try:
                    with wave.open(audio_file_path, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        if rate > 0:
                            duration_seconds = frames / float(rate)
                except Exception:
                    pass

            return duration_seconds, file_size_mb

        except Exception as e:
            self._log(f"获取音频信息时发生错误: {e}")
            return None, None

    def transcribe_audio(self,
                         audio_file_path: str,
                         language_code: Optional[str] = None, 
                         num_speakers: Optional[int] = None,
                         tag_audio_events: bool = True,
                         model_id: Optional[str] = None) -> Optional[Dict]:
        """
        Web免费版转录 (使用相同的API端点，但不带API Key)
        """
        if not self._is_worker_running():
            self._log("转录任务已取消")
            return None

        # 复用官方API逻辑，只是不传Key
        # 注意：实际的Web版可能需要特殊的Cookie或Token，这里保持原逻辑结构
        # 如果是纯逆向Web接口，这里应该填写逆向逻辑。
        # 假设这里是尝试使用API端点但不带鉴权（allow_unauthenticated=1）
        
        try:
            return self.transcribe_audio_official_api(
                audio_file_path=audio_file_path,
                api_key="", # 无Key
                language_code=language_code,
                num_speakers=num_speakers or 0,
                tag_audio_events=tag_audio_events,
                model_id=model_id  # 传递模型ID
            )
        except Exception as e:
            self._log(f"Web版转录失败: {e}")
            return None

    def transcribe_audio_official_api(self, audio_file_path: str, api_key: str,
                                    language_code: Optional[str] = None,
                                    num_speakers: int = 0,
                                    enable_diarization: bool = True,
                                    tag_audio_events: bool = True,
                                    model_id: Optional[str] = None) -> Optional[Dict]:
        """
        使用ElevenLabs官方API进行音频转录
        
        Args:
            audio_file_path: 音频文件路径
            api_key: API密钥（免费版传空字符串）
            language_code: 语言代码
            num_speakers: 说话人数量
            enable_diarization: 是否启用说话人分离
            tag_audio_events: 是否标记音频事件
            model_id: 模型ID（scribe_v1 或 scribe_v2），默认使用 DEFAULT_STT_MODEL_ID
        """
        try:
            self._log("开始使用ElevenLabs官方API转录音频...")
            
            # 使用传入的模型ID或默认值
            if model_id is None:
                model_id = DEFAULT_STT_MODEL_ID
            
            self._log(f"使用模型: {model_id}")

            if not os.path.exists(audio_file_path):
                self._log(f"错误: 音频文件未找到: {audio_file_path}")
                return None

            # [关键] 统一使用 /v1/speech-to-text
            api_url = ELEVENLABS_STT_API_URL

            # === 根据模式使用不同的构造方式 ===
            if api_key:
                # === 付费/API 模式 ===
                self._log("使用付费/API模式 (带API Key)")

                # 1. 付费版请求头
                headers = {
                    "Accept": "application/json",
                    "xi-api-key": api_key  # 必须包含API Key
                }

                # 2. 付费版表单数据
                payload_data = {
                    "model_id": model_id,  # 使用传入的模型ID
                    "timestamps_granularity": "word",  # 付费版可以使用
                    "tag_audio_events": tag_audio_events,
                    "diarize": enable_diarization
                }

                # 3. 付费版其他参数
                if language_code and language_code != "auto":
                    payload_data["language_code"] = language_code
                if num_speakers > 0:
                    payload_data["num_speakers"] = num_speakers

                # 4. 付费版不使用URL参数
                params_data = None

                self._log(f"付费版API参数: {json.dumps(payload_data, ensure_ascii=False)}")

            else:
                # === 免费/Web 模式 ===
                self._log("使用免费/Web模式 (免登录)")

                # 1. 免费版请求头 (模拟浏览器，按照原始脚本)
                headers = {
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": random.choice(DEFAULT_ACCEPT_LANGUAGES),
                    "Origin": "https://elevenlabs.io",
                    "Referer": "https://elevenlabs.io/",
                    "User-Agent": random.choice(DEFAULT_USER_AGENTS),
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site"
                }

                # 2. 免费版URL参数 (按照原始脚本)
                params_data = {
                    "allow_unauthenticated": "1"
                }

                # 3. 免费版表单数据 (绝对不包含timestamps_granularity)
                payload_data = {
                    "model_id": model_id,  # 使用传入的模型ID
                    "tag_audio_events": tag_audio_events,  # 修复：使用bool值而不是字符串
                    "diarize": enable_diarization            # 修复：使用bool值而不是字符串
                }

                # 4. 免费版其他参数
                if language_code and language_code != "auto":
                    payload_data["language_code"] = language_code
                if num_speakers > 0:
                    payload_data["num_speakers"] = num_speakers

                self._log(f"免费版URL参数: {json.dumps(params_data, ensure_ascii=False)}")
                self._log(f"免费版表单数据: {json.dumps(payload_data, ensure_ascii=False)}")

            # 获取音频信息用于日志
            duration, file_size = self.get_audio_info(audio_file_path)
            if duration:
                self._log(f"音频信息: {duration:.2f}s, {file_size:.2f}MB")

            # 发送请求
            with open(audio_file_path, "rb") as f:
                # 根据文件扩展名确定MIME类型
                file_extension = os.path.splitext(audio_file_path)[1].lower()
                mime_type_map = {
                    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
                    ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".opus": "audio/opus",
                    ".aac": "audio/aac", ".webm": "audio/webm", ".mp4": "video/mp4",
                    ".mov": "video/quicktime"
                }
                mime_type = mime_type_map.get(file_extension, 'application/octet-stream')

                files = {"file": (os.path.basename(audio_file_path), f, mime_type)}

                # 添加重试机制 - 修复网络超时问题
                max_retries = 3
                retry_delay = 5  # 秒

                for attempt in range(max_retries):
                    try:
                        # 根据模式使用不同的发送方式
                        if api_key:
                            # 付费版：不使用URL参数，只使用表单数据
                            self._log(f"发送付费版请求... (尝试 {attempt + 1}/{max_retries})")
                            response = requests.post(
                                api_url,
                                headers=headers,
                                data=payload_data,
                                files=files,
                                timeout=(60, 1800) # 修复：增加连接超时到60秒
                            )
                        else:
                            # 免费版：使用URL参数 + 表单数据，按照原始脚本的方式
                            self._log(f"发送免费版请求... (尝试 {attempt + 1}/{max_retries})")
                            response = requests.post(
                                api_url,
                                params=params_data,  # URL参数
                                headers=headers,
                                data=payload_data,   # 表单数据
                                files=files,
                                timeout=(120, 1800) # 修复：增加连接超时到120秒，应对网络波动
                            )

                        # 如果成功发送，跳出重试循环
                        break

                    except (requests.exceptions.Timeout,
                            requests.exceptions.ConnectionError,
                            ConnectionError,
                            TimeoutError) as e:
                        if attempt < max_retries - 1:  # 不是最后一次尝试
                            self._log(f"网络超时，{retry_delay}秒后重试... 错误: {str(e)}")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避：5s, 10s, 20s
                        else:
                            # 最后一次尝试失败，重新抛出异常
                            self._log(f"重试{max_retries}次后仍然失败")
                            raise

            if response.status_code == 200:
                result = response.json()
                
                # 格式转换：将 v2 的 [event] 转换为 (event)
                result = self._normalize_v2_audio_events(result, model_id)
                
                # 注入元数据方便后续处理
                result["elevenlabs_api_metadata"] = {
                    "api_type": "official",
                    "model_id": model_id,  # 记录使用的模型
                    "audio_duration": duration
                }
                self._log("ElevenLabs转录成功！")
                return result
            
            elif response.status_code == 401:
                self._log("错误: 401 Unauthorized - API Key 无效或过期")
                return None
            else:
                self._log(f"错误: API请求失败 [{response.status_code}]: {response.text[:200]}")
                return None

        except Exception as e:
            self._log(f"转录过程发生异常: {e}")
            import traceback
            self._log(traceback.format_exc())
            return None

    def test_official_api_connection(self, api_key: str) -> Tuple[bool, str]:
        """
        测试 ElevenLabs API 连接 (兼容受限 Key)
        
        原理：向 STT 接口发送一个空请求。
        - 如果 Key 有效：服务器会处理鉴权，然后发现没有文件，返回 422 或 400。
        - 如果 Key 无效：服务器直接返回 401 Unauthorized。
        """
        try:
            self._log("测试 ElevenLabs 官方 API 连接...")
            self._log(f"API Key: {api_key[:6]}...{api_key[-4:] if len(api_key) > 10 else ''}")

            # 使用 STT 接口进行测试，而不是 /v1/user
            test_url = ELEVENLABS_STT_API_URL
            headers = {
                "xi-api-key": api_key,
                "Accept": "application/json"
            }

            self._log(f"发送探测请求到: {test_url}")
            
            # 发送不带文件的空 POST 请求
            response = requests.post(test_url, headers=headers, timeout=30)
            
            code = response.status_code
            self._log(f"收到响应，状态码: {code}")

            # 判定逻辑
            if code == 401:
                return False, "API Key 无效或无权访问 (401 Unauthorized)"
            
            elif code == 422 or code == 400:
                # 422/400 意味着鉴权通过了，只是服务器抱怨没发文件
                # 这是验证受限 Key 的最佳证据
                try:
                    err_detail = response.json()
                    self._log(f"服务器返回验证信息: {err_detail}")
                except:
                    pass
                return True, "连接成功！(API Key 有效，鉴权通过)"
            
            elif code == 200:
                # 理论上不应该发生，除非 ElevenLabs 允许空请求
                return True, "连接成功！(服务响应正常)"
                
            else:
                return False, f"API 测试收到意外状态码: {code} - {response.text[:100]}"

        except requests.exceptions.Timeout:
            return False, "连接超时 (请检查网络)"
        except requests.exceptions.RequestException as e:
            return False, f"网络请求错误: {str(e)}"
        except Exception as e:
            self._log(f"测试连接异常: {e}")
            return False, f"测试过程发生错误: {str(e)}"

    def delete_transcription(self, transcription_id: str, api_key: str) -> bool:
        """
        删除云端转录历史记录
        API文档参考: DELETE /v1/speech-to-text/transcripts/{transcription_id}
        """
        try:
            # 构造删除接口的 URL
            # 注意：这里的基础路径是 /v1/speech-to-text/transcripts
            url = f"https://api.elevenlabs.io/v1/speech-to-text/transcripts/{transcription_id}"

            # 必须包含 API Key 才能有权限删除
            headers = {
                "xi-api-key": api_key
            }

            self._log(f"正在删除ElevenLabs转录记录: {transcription_id}")

            # 发送 DELETE 请求
            response = requests.delete(url, headers=headers, timeout=10)

            # 200 OK 表示删除成功
            if response.status_code == 200:
                self._log(f"云端转录记录 {transcription_id} 删除成功")
                return True
            elif response.status_code == 404:
                self._log(f"转录记录不存在或已被删除: {transcription_id}")
                return True  # 不存在也算清理成功
            else:
                self._log(f"云端记录删除失败: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.Timeout:
            self._log("删除请求超时")
            return False
        except requests.exceptions.RequestException as e:
            self._log(f"删除请求网络错误: {str(e)}")
            return False
        except Exception as e:
            self._log(f"执行删除操作时发生异常: {e}")
            return False