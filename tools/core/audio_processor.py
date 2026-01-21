"""
音频处理编排模块 - 纯 Python 实现，无 GUI 依赖

提供批量音频处理的高级编排功能，适用于：
- 命令行工具
- Web 服务
- 批处理脚本

作者: fuxiaomoke
版本: 0.2.2.0
"""

from typing import List, Tuple, Dict, Optional, Callable
import os
from tools.core.audio_extractor import (
    extract_audio_to_ogg, split_audio_by_duration,
    get_media_info, is_video_file, is_audio_file
)


class AudioProcessor:
    """
    音频处理编排器（纯 Python，无 Qt 依赖）
    
    使用回调函数模式传递进度和状态，适配任何 UI 框架或 CLI
    """
    
    def __init__(self, 
                 progress_callback: Optional[Callable[[str], None]] = None,
                 error_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            progress_callback: 进度回调 (message: str)
            error_callback: 错误回调 (error_message: str)
        """
        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.extracted_files: Dict[str, str] = {}
        self.split_results: Dict[str, List] = {}
    
    def _log(self, message: str):
        """内部日志"""
        if self.progress_callback:
            self.progress_callback(message)
        else:
            print(message)
    
    def _error(self, message: str):
        """内部错误"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"ERROR: {message}")
    
    def extract_multiple_videos(
        self, 
        video_files: List[str]
    ) -> Dict[str, str]:
        """
        批量提取视频音频
        
        Args:
            video_files: 视频文件路径列表
        
        Returns:
            Dict[原始视频路径, 提取的音频路径]
        
        Raises:
            Exception: 提取失败时抛出
        """
        results = {}
        total = len(video_files)
        
        for i, video_path in enumerate(video_files, 1):
            self._log(f"[{i}/{total}] 提取音频: {os.path.basename(video_path)}")
            
            def progress_cb(current, total_duration):
                if total_duration > 0:
                    percent = (current / total_duration) * 100
                    self._log(f"[{i}/{total}] 提取进度: {percent:.1f}%")
            
            success, msg, audio_path = extract_audio_to_ogg(
                video_path,
                progress_callback=progress_cb
            )
            
            if success:
                results[video_path] = audio_path
                self._log(f"[{i}/{total}] 完成: {audio_path}")
            else:
                error_msg = f"提取失败 [{os.path.basename(video_path)}]: {msg}"
                self._error(error_msg)
                raise Exception(error_msg)
        
        return results
    
    def split_long_audios(
        self,
        audio_files: List[str],
        max_duration: float = 1800.0,
        split_duration: float = 1680.0
    ) -> Dict[str, List[Tuple[str, float, float]]]:
        """
        检查并分割超长音频
        
        Args:
            audio_files: 音频文件路径列表
            max_duration: 触发分割的最大时长（秒）
            split_duration: 分割后每段的最大时长（秒）
        
        Returns:
            Dict[原始音频路径, chunk_info列表]
            chunk_info = [(chunk_path, start_time, end_time), ...]
        """
        results = {}
        files_need_split = []
        
        # 检查哪些文件需要分割
        for audio_file in audio_files:
            info = get_media_info(audio_file)
            if not info:
                self._error(f"无法获取音频信息: {audio_file}")
                continue
            
            if info['duration'] > max_duration:
                files_need_split.append((audio_file, info['duration']))
            else:
                # 不需要分割
                results[audio_file] = [(audio_file, 0.0, info['duration'])]
        
        if not files_need_split:
            return results
        
        # 分割超长音频
        total = len(files_need_split)
        for i, (audio_file, duration) in enumerate(files_need_split, 1):
            self._log(f"[{i}/{total}] 分割音频: {os.path.basename(audio_file)} ({duration/60:.1f}分钟)")
            
            def progress_cb(curr_chunk, total_chunks, msg):
                self._log(f"[{i}/{total}] {msg}")
            
            success, msg, chunk_info = split_audio_by_duration(
                audio_file,
                max_duration=split_duration,
                progress_callback=progress_cb
            )
            
            if success and chunk_info:
                results[audio_file] = chunk_info
                self._log(f"[{i}/{total}] 完成: 分割为 {len(chunk_info)} 个片段")
            else:
                error_msg = f"分割失败 [{os.path.basename(audio_file)}]: {msg}"
                self._error(error_msg)
                raise Exception(error_msg)
        
        return results
    
    def process_media_batch(
        self,
        media_files: List[str],
        auto_split: bool = True,
        max_duration: float = 1800.0,
        split_duration: float = 1680.0
    ) -> Tuple[List[str], Dict[str, List[Tuple[str, float, float]]]]:
        """
        批量处理媒体文件（视频提取 + 音频分割）
        
        Args:
            media_files: 媒体文件路径列表（视频或音频）
            auto_split: 是否自动分割超长音频
            max_duration: 触发分割的最大时长
            split_duration: 分割后每段的最大时长
        
        Returns:
            (audio_files, split_info)
            - audio_files: 处理后的音频文件列表
            - split_info: 分割信息字典
        """
        # 1. 分离视频和音频
        video_files = [f for f in media_files if is_video_file(f)]
        audio_files = [f for f in media_files if is_audio_file(f)]
        
        # 2. 提取视频音频
        if video_files:
            self._log(f"检测到 {len(video_files)} 个视频文件，开始提取音频...")
            extracted = self.extract_multiple_videos(video_files)
            audio_files.extend(extracted.values())
            self.extracted_files = extracted
        
        # 3. 分割超长音频
        split_info = {}
        if auto_split and audio_files:
            self._log(f"检查 {len(audio_files)} 个音频文件是否需要分割...")
            split_info = self.split_long_audios(audio_files, max_duration, split_duration)
            self.split_results = split_info
        
        return audio_files, split_info


# ============ 便捷函数（供快速调用）============

def extract_videos(
    video_files: List[str],
    progress_callback: Optional[Callable] = None
) -> Dict[str, str]:
    """便捷函数：批量提取视频音频"""
    processor = AudioProcessor(progress_callback=progress_callback)
    return processor.extract_multiple_videos(video_files)


def split_long_audios(
    audio_files: List[str],
    max_duration: float = 1800.0,
    split_duration: float = 1680.0,
    progress_callback: Optional[Callable] = None
) -> Dict[str, List[Tuple[str, float, float]]]:
    """便捷函数：检查并分割超长音频"""
    processor = AudioProcessor(progress_callback=progress_callback)
    return processor.split_long_audios(audio_files, max_duration, split_duration)
