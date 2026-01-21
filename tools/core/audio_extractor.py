"""
音频提取模块 - 从视频文件中提取音频并转换为 OGG 格式

使用 PyAV 库（FFmpeg Python 绑定）实现视频音频提取功能。
支持长音频文件的智能分割（基于静音检测）和转录结果合并。

作者: fuxiaomoke
版本: 0.2.2.0
"""

import os
import tempfile
import json
import math
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# 支持的视频格式
VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.webm', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.mts'}

# 支持的音频格式（无需转换）
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus', '.aac', '.wma'}

# OGG 编码参数（针对语音转录优化）
OGG_SAMPLE_RATE = 16000  # 16kHz 足够语音识别
OGG_CHANNELS = 1  # 单声道
OGG_QUALITY = 4  # VBR 质量 0-10，4 约等于 128kbps，适合语音


def is_video_file(file_path: str) -> bool:
    """
    检查文件是否为视频格式
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为视频文件
    """
    ext = Path(file_path).suffix.lower()
    return ext in VIDEO_EXTENSIONS


def is_audio_file(file_path: str) -> bool:
    """
    检查文件是否为音频格式
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为音频文件
    """
    ext = Path(file_path).suffix.lower()
    return ext in AUDIO_EXTENSIONS


def is_media_file(file_path: str) -> bool:
    """
    检查文件是否为支持的媒体格式（音频或视频）
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为媒体文件
    """
    return is_audio_file(file_path) or is_video_file(file_path)


def extract_audio_to_ogg(
    input_path: str,
    output_path: Optional[str] = None,
    sample_rate: int = OGG_SAMPLE_RATE,
    channels: int = OGG_CHANNELS,
    quality: int = OGG_QUALITY,
    progress_callback: Optional[callable] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    从视频文件中提取音频并转换为 OGG 格式
    
    Args:
        input_path: 输入视频文件路径
        output_path: 输出 OGG 文件路径，如果为 None 则自动生成临时文件
        sample_rate: 采样率，默认 16000 Hz
        channels: 声道数，默认 1（单声道）
        quality: VBR 质量等级 0-10，默认 4
        progress_callback: 进度回调函数，接收 (current_seconds, total_seconds) 参数
        
    Returns:
        Tuple[bool, str, Optional[str]]: (成功与否, 消息, 输出文件路径)
    """
    try:
        import av
    except ImportError:
        return False, "PyAV 库未安装，请运行: pip install av", None
    
    if not os.path.exists(input_path):
        return False, f"输入文件不存在: {input_path}", None
    
    # 生成输出路径
    if output_path is None:
        # 使用临时目录，文件名基于原文件名
        base_name = Path(input_path).stem
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"{base_name}_extracted.ogg")
    
    try:
        # 打开输入文件
        input_container = av.open(input_path)
        
        # 查找音频流
        audio_streams = [s for s in input_container.streams if s.type == 'audio']
        if not audio_streams:
            input_container.close()
            return False, "视频文件中没有找到音频流", None
        
        # 使用第一个音频流
        input_audio_stream = audio_streams[0]
        
        # 获取总时长用于进度显示
        total_duration = float(input_container.duration) / av.time_base if input_container.duration else 0
        
        # 创建输出容器
        output_container = av.open(output_path, 'w')
        
        # 添加 Vorbis 音频流 - 使用正确的 API
        output_audio_stream = output_container.add_stream('libvorbis', rate=sample_rate)
        output_audio_stream.codec_context.layout = 'mono' if channels == 1 else 'stereo'
        from fractions import Fraction
        output_audio_stream.codec_context.time_base = Fraction(1, sample_rate)
        
        # 创建重采样器
        resampler = av.AudioResampler(
            format='fltp',  # libvorbis 需要 float planar 格式
            layout='mono' if channels == 1 else 'stereo',
            rate=sample_rate
        )
        
        # 处理音频帧
        frame_count = 0
        output_pts = 0
        for packet in input_container.demux(input_audio_stream):
            for frame in packet.decode():
                frame_count += 1
                
                # 进度回调
                if progress_callback and total_duration > 0:
                    current_time = float(frame.pts * input_audio_stream.time_base) if frame.pts is not None else 0
                    progress_callback(current_time, total_duration)
                
                # 重采样
                resampled_frames = resampler.resample(frame)
                
                # 编码并写入
                for resampled_frame in resampled_frames:
                    resampled_frame.pts = output_pts
                    output_pts += resampled_frame.samples
                    for out_packet in output_audio_stream.encode(resampled_frame):
                        output_container.mux(out_packet)
        
        # 刷新编码器
        for out_packet in output_audio_stream.encode(None):
            output_container.mux(out_packet)
        
        # 关闭容器
        output_container.close()
        input_container.close()
        
        # 检查输出文件
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            return True, f"音频提取成功，文件大小: {file_size_mb:.2f} MB", output_path
        else:
            return False, "音频提取失败：输出文件为空", None
            
    except Exception as e:
        return False, f"音频提取失败: {str(e)}", None


def get_media_info(file_path: str) -> Optional[dict]:
    """
    获取媒体文件信息
    
    Args:
        file_path: 媒体文件路径
        
    Returns:
        dict: 包含媒体信息的字典，失败返回 None
    """
    try:
        import av
    except ImportError:
        return None
    
    try:
        container = av.open(file_path)
        
        info = {
            'duration': float(container.duration) / av.time_base if container.duration else 0,
            'format': container.format.name,
            'audio_streams': [],
            'video_streams': []
        }
        
        for stream in container.streams:
            if stream.type == 'audio':
                info['audio_streams'].append({
                    'codec': stream.codec_context.name if stream.codec_context else 'unknown',
                    'sample_rate': stream.sample_rate,
                    'channels': stream.channels
                })
            elif stream.type == 'video':
                info['video_streams'].append({
                    'codec': stream.codec_context.name if stream.codec_context else 'unknown',
                    'width': stream.width,
                    'height': stream.height
                })
        
        container.close()
        return info
        
    except Exception:
        return None


def cleanup_temp_ogg(file_path: str) -> bool:
    """
    清理临时 OGG 文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否成功删除
    """
    try:
        if file_path and os.path.exists(file_path):
            # 只删除临时目录中的文件
            temp_dir = tempfile.gettempdir()
            if file_path.startswith(temp_dir) and file_path.endswith('.ogg'):
                os.remove(file_path)
                return True
        return False
    except Exception:
        return False


def calculate_rms(audio_frame) -> float:
    """
    计算音频帧的 RMS（均方根）振幅
    
    Args:
        audio_frame: PyAV 音频帧
        
    Returns:
        float: RMS 值（线性振幅）
    """
    try:
        import numpy as np
        # 将音频帧转换为 numpy 数组
        audio_array = audio_frame.to_ndarray()
        # 计算 RMS
        rms = np.sqrt(np.mean(audio_array ** 2))
        return float(rms)
    except Exception:
        return 0.0


def rms_to_db(rms: float) -> float:
    """
    将 RMS 值转换为分贝 (dB)
    
    Args:
        rms: RMS 值（线性振幅）
        
    Returns:
        float: 分贝值
    """
    if rms <= 0:
        return -100.0  # 极小值
    return 20 * math.log10(rms)


def find_silence_near_target(
    audio_path: str,
    target_seconds: float = 1680.0,
    search_window: float = 120.0,
    silence_thresh_db: float = -40.0,
    min_silence_duration: float = 0.5
) -> float:
    """
    在目标时间点附近查找静音段
    
    Args:
        audio_path: 音频文件路径
        target_seconds: 目标时间点（秒）
        search_window: 搜索窗口大小（秒），在 target_seconds 前后搜索
        silence_thresh_db: 静音阈值（分贝），低于此值视为静音
        min_silence_duration: 最小静音持续时间（秒）
        
    Returns:
        float: 找到的静音点时间（秒），如果未找到则返回 target_seconds
    """
    try:
        import av
        import numpy as np
    except ImportError:
        return target_seconds
    
    try:
        container = av.open(audio_path)
        audio_streams = [s for s in container.streams if s.type == 'audio']
        if not audio_streams:
            container.close()
            return target_seconds
        
        audio_stream = audio_streams[0]
        sample_rate = audio_stream.sample_rate or 16000
        
        # 计算搜索范围
        search_start = max(0, target_seconds - search_window)
        search_end = target_seconds
        
        # 定位到搜索起始位置
        seek_timestamp = int(search_start / audio_stream.time_base)
        container.seek(seek_timestamp, stream=audio_stream)
        
        # 收集静音段
        silence_segments = []
        current_silence_start = None
        
        for packet in container.demux(audio_stream):
            for frame in packet.decode():
                if frame.pts is None:
                    continue
                
                frame_time = float(frame.pts * audio_stream.time_base)
                
                # 超出搜索范围则停止
                if frame_time > search_end:
                    break
                
                # 计算 RMS 和 dB
                rms = calculate_rms(frame)
                db = rms_to_db(rms)
                
                # 检测静音
                if db < silence_thresh_db:
                    if current_silence_start is None:
                        current_silence_start = frame_time
                else:
                    if current_silence_start is not None:
                        silence_duration = frame_time - current_silence_start
                        if silence_duration >= min_silence_duration:
                            silence_segments.append((current_silence_start, frame_time))
                        current_silence_start = None
        
        # 处理最后一个静音段
        if current_silence_start is not None:
            silence_duration = search_end - current_silence_start
            if silence_duration >= min_silence_duration:
                silence_segments.append((current_silence_start, search_end))
        
        container.close()
        
        # 选择最接近目标时间的静音段中点
        if silence_segments:
            best_silence = min(silence_segments, 
                             key=lambda s: abs((s[0] + s[1]) / 2 - target_seconds))
            split_point = (best_silence[0] + best_silence[1]) / 2
            return split_point
        
        return target_seconds
        
    except Exception as e:
        print(f"[静音检测] 错误: {e}")
        return target_seconds


def split_audio_by_duration(
    input_path: str,
    max_duration: float = 1680.0,
    output_dir: Optional[str] = None,
    sample_rate: int = OGG_SAMPLE_RATE,
    channels: int = OGG_CHANNELS,
    quality: int = OGG_QUALITY,
    progress_callback: Optional[callable] = None
) -> Tuple[bool, str, Optional[List[Tuple[str, float, float]]]]:
    """
    将音频文件分割成多个时长受限的片段（带静音检测）
    
    Args:
        input_path: 输入音频文件路径
        max_duration: 每个片段的最大时长（秒），默认 1680 秒（28 分钟）
        output_dir: 输出目录，如果为 None 则使用临时目录
        sample_rate: 采样率，默认 16000 Hz
        channels: 声道数，默认 1（单声道）
        quality: VBR 质量等级 0-10，默认 4
        progress_callback: 进度回调函数，接收 (current_chunk, total_chunks, message) 参数
        
    Returns:
        Tuple[bool, str, Optional[List[Tuple[str, float, float]]]]: 
        (成功与否, 消息, 片段信息列表 [(文件路径, 起始时间, 结束时间)])
    """
    import datetime
    
    def log_with_time(msg):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [音频分割] {msg}")
    
    try:
        import av
    except ImportError:
        return False, "PyAV 库未安装，请运行: pip install av", None
    
    if not os.path.exists(input_path):
        return False, f"输入文件不存在: {input_path}", None
    
    # 获取音频总时长
    media_info = get_media_info(input_path)
    if not media_info or media_info['duration'] <= 0:
        return False, "无法获取音频时长", None
    
    total_duration = media_info['duration']
    
    # 如果时长小于最大时长，无需分割
    if total_duration <= max_duration:
        return False, f"音频时长 {total_duration:.1f}s 小于最大时长 {max_duration:.1f}s，无需分割", None
    
    # 设置输出目录
    if output_dir is None:
        output_dir = tempfile.gettempdir()
    
    # 计算分割点
    split_points = [0.0]
    current_pos = 0.0
    
    while current_pos + max_duration < total_duration:
        target_split = current_pos + max_duration
        # 使用静音检测查找最佳分割点
        actual_split = find_silence_near_target(
            input_path, 
            target_seconds=target_split,
            search_window=120.0,
            silence_thresh_db=-40.0,
            min_silence_duration=0.5
        )
        split_points.append(actual_split)
        current_pos = actual_split
    
    split_points.append(total_duration)
    
    # 生成输出文件列表
    base_name = Path(input_path).stem
    chunk_info = []
    
    num_chunks = len(split_points) - 1
    log_with_time(f"将分割为 {num_chunks} 个片段")
    
    # 提取每个片段
    for i in range(num_chunks):
        start_time = split_points[i]
        end_time = split_points[i + 1]
        chunk_duration = end_time - start_time
        
        output_path = os.path.join(output_dir, f"{base_name}_part{i+1:03d}.ogg")
        
        if progress_callback:
            progress_callback(i + 1, num_chunks, f"正在分割片段 {i+1}/{num_chunks} ({chunk_duration:.1f}s)")
        
        log_with_time(f"片段 {i+1}/{num_chunks}: {start_time:.1f}s - {end_time:.1f}s -> {output_path}")
        
        # 提取片段
        success = extract_audio_segment(
            input_path, output_path,
            start_time, end_time,
            sample_rate, channels, quality
        )
        
        if not success:
            return False, f"提取片段 {i+1} 失败", None
        
        chunk_info.append((output_path, start_time, end_time))
    
    return True, f"成功分割为 {num_chunks} 个片段", chunk_info


def extract_audio_segment(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    sample_rate: int = OGG_SAMPLE_RATE,
    channels: int = OGG_CHANNELS,
    quality: int = OGG_QUALITY
) -> bool:
    """
    从音频文件中提取指定时间段
    
    Args:
        input_path: 输入音频文件路径
        output_path: 输出文件路径
        start_time: 起始时间（秒）
        end_time: 结束时间（秒）
        sample_rate: 采样率
        channels: 声道数
        quality: VBR 质量等级
        
    Returns:
        bool: 是否成功
    """
    try:
        import av
    except ImportError:
        return False
    
    try:
        input_container = av.open(input_path)
        audio_streams = [s for s in input_container.streams if s.type == 'audio']
        if not audio_streams:
            input_container.close()
            return False
        
        input_audio_stream = audio_streams[0]
        
        # 定位到起始位置
        seek_timestamp = int(start_time / input_audio_stream.time_base)
        input_container.seek(seek_timestamp, stream=input_audio_stream)
        
        # 创建输出容器
        output_container = av.open(output_path, 'w')
        output_audio_stream = output_container.add_stream('libvorbis', rate=sample_rate)
        output_audio_stream.codec_context.layout = 'mono' if channels == 1 else 'stereo'
        from fractions import Fraction
        output_audio_stream.codec_context.time_base = Fraction(1, sample_rate)
        
        # 创建重采样器
        resampler = av.AudioResampler(
            format='fltp',
            layout='mono' if channels == 1 else 'stereo',
            rate=sample_rate
        )
        
        # 处理音频帧
        output_pts = 0
        for packet in input_container.demux(input_audio_stream):
            for frame in packet.decode():
                if frame.pts is None:
                    continue
                
                frame_time = float(frame.pts * input_audio_stream.time_base)
                
                # 超出结束时间则停止
                if frame_time >= end_time:
                    break
                
                # 跳过起始时间之前的帧
                if frame_time < start_time:
                    continue
                
                # 重采样并编码
                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    resampled_frame.pts = output_pts
                    output_pts += resampled_frame.samples
                    for out_packet in output_audio_stream.encode(resampled_frame):
                        output_container.mux(out_packet)
        
        # 刷新编码器
        for out_packet in output_audio_stream.encode(None):
            output_container.mux(out_packet)
        
        output_container.close()
        input_container.close()
        
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        
    except Exception as e:
        print(f"[音频分割] 提取片段失败: {e}")
        return False


def merge_elevenlabs_transcriptions(
    json_files: List[str],
    chunk_info: List[Tuple[str, float, float]],
    output_path: str
) -> Tuple[bool, str]:
    """
    合并多个 ElevenLabs 转录 JSON 文件
    
    Args:
        json_files: JSON 文件路径列表
        chunk_info: 片段信息列表 [(文件路径, 起始时间, 结束时间)]
        output_path: 输出合并后的 JSON 文件路径
        
    Returns:
        Tuple[bool, str]: (成功与否, 消息)
    """
    try:
        if len(json_files) != len(chunk_info):
            return False, "JSON 文件数量与片段信息不匹配"
        
        merged = {
            "text": "",
            "words": [],
            "language_code": None,
            "language_confidence": 0.0
        }
        
        for i, (json_file, chunk_tuple) in enumerate(zip(json_files, chunk_info)):
            if not os.path.exists(json_file):
                return False, f"JSON 文件不存在: {json_file}"
            
            chunk_start_offset = chunk_tuple[1]  # 起始时间
            
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 合并文本（添加空格分隔）
            if i > 0 and merged["text"] and data.get("text"):
                merged["text"] += " "
            merged["text"] += data.get("text", "")
            
            # 调整时间戳并合并单词
            for word in data.get("words", []):
                adjusted_word = word.copy()
                if "start" in adjusted_word:
                    adjusted_word["start"] += chunk_start_offset
                if "end" in adjusted_word:
                    adjusted_word["end"] += chunk_start_offset
                merged["words"].append(adjusted_word)
            
            # 使用第一个片段的语言信息
            if i == 0:
                merged["language_code"] = data.get("language_code")
                merged["language_confidence"] = data.get("language_confidence", 0.0)
        
        # 写入合并后的 JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        
        total_words = len(merged["words"])
        return True, f"成功合并 {len(json_files)} 个文件，共 {total_words} 个单词"
        
    except Exception as e:
        return False, f"合并 JSON 失败: {str(e)}"
