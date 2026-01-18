"""
字幕生成流程编排模块

独立的命令行工具核心逻辑，不依赖 GUI 组件。
实现完整的视频转字幕流程：音频提取 → 分割 → 转录 → 合并 → LLM优化 → SRT生成

作者: fuxiaomoke
版本: 0.2.2.0
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

# 添加项目根目录和 src 目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 从 src 导入可复用的模块
from core.elevenlabs_api import ElevenLabsSTTClient
from core.transcription_parser import TranscriptionParser
from core.srt_processor import SrtProcessor
from core.llm_api import call_llm_api_for_segmentation

# 从 tools.core 导入音频处理模块
from tools.core.audio_extractor import (
    extract_audio_to_ogg, split_audio_by_duration, 
    get_media_info, is_video_file, is_audio_file,
    merge_elevenlabs_transcriptions
)


class SubtitlePipeline:
    """无 GUI 依赖的字幕生成流程编排器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化流程编排器
        
        Args:
            config: 配置字典，包含：
                - llm_api_key: LLM API密钥
                - llm_api_url: LLM API地址
                - llm_model: LLM模型名称
                - language: 目标语言 (zh/ja/en/ko)
                - max_chunk_duration: 最大分割时长（秒）
                - temperature: LLM温度参数
        """
        self.config = config
        self.temp_files = []  # 记录临时文件用于清理
        
    def _log(self, message: str):
        """输出带时间戳的日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def process_video(self, video_path: str) -> str:
        """
        完整流程：视频 → SRT
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            str: 生成的SRT文件路径
        """
        try:
            self._log(f"开始处理视频: {video_path}")
            
            # Step 1: 提取音频
            self._log("=" * 60)
            self._log("步骤 1/5: 提取音频")
            audio_path = self._extract_audio(video_path)
            self._log(f"OK: 音频提取完成: {audio_path}")
            
            # Step 2: 分割音频（如果需要）
            self._log("=" * 60)
            self._log("步骤 2/5: 检查音频时长并分割")
            chunks = self._split_audio_if_needed(audio_path)
            if len(chunks) > 1:
                self._log(f"OK: 音频已分割为 {len(chunks)} 个片段")
            else:
                self._log("OK: 音频无需分割")
            
            # Step 3: 批量转录
            self._log("=" * 60)
            self._log("步骤 3/5: ElevenLabs 转录")
            json_files = self._transcribe_chunks(chunks)
            self._log(f"OK: 转录完成，生成 {len(json_files)} 个JSON文件")
            
            # Step 4: 合并 JSON（如果有多个）
            self._log("=" * 60)
            self._log("步骤 4/5: 合并转录结果")
            if len(json_files) > 1:
                merged_json = self._merge_transcriptions(json_files, chunks)
                self._log(f"OK: JSON合并完成: {merged_json}")
            else:
                merged_json = json_files[0]
                self._log(f"OK: 单文件无需合并: {merged_json}")
            
            # Step 5: LLM 优化 + SRT 生成
            self._log("=" * 60)
            self._log("步骤 5/5: LLM优化并生成SRT")
            srt_path = self._generate_srt(merged_json, video_path)
            self._log(f"OK: SRT生成完成: {srt_path}")
            
            self._log("=" * 60)
            self._log("OK: 全部完成！")
            
            return srt_path
            
        except Exception as e:
            self._log(f"Error: 处理失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            # 清理临时文件
            self._cleanup_temp_files()
    
    def _extract_audio(self, video_path: str) -> str:
        """提取音频并转换为OGG格式"""
        # 检查文件类型
        if is_audio_file(video_path):
            self._log("输入文件是音频格式，直接使用")
            return video_path
        
        if not is_video_file(video_path):
            raise ValueError(f"不支持的文件格式: {video_path}")
        
        # 提取音频
        last_percent = [-1]  # 使用列表避免闭包问题
        def progress_callback(current, total):
            if total > 0:
                percent = round((current / total) * 100, 1)
                if percent != last_percent[0]:
                    print(f"\r  提取进度: {percent:.1f}%", end='', flush=True)
                    last_percent[0] = percent
        
        print("  提取音频中...", end='', flush=True)
        
        success, msg, audio_path = extract_audio_to_ogg(
            video_path,
            progress_callback=progress_callback
        )
        
        if not success:
            print()  # 换行
            raise Exception(f"音频提取失败: {msg}")
        
        print()  # 完成后换行
        self.temp_files.append(audio_path)
        return audio_path
    
    def _split_audio_if_needed(self, audio_path: str) -> List[Tuple[str, float, float]]:
        """如果音频超过最大时长则分割"""
        # 获取音频信息
        info = get_media_info(audio_path)
        if not info:
            raise Exception("无法获取音频信息")
        
        duration = info['duration']
        max_duration = self.config.get('max_chunk_duration', 1680)
        
        self._log(f"  音频时长: {duration:.1f}秒 ({duration/60:.1f}分钟)")
        self._log(f"  最大时长限制: {max_duration}秒 ({max_duration/60:.1f}分钟)")
        
        # 如果不需要分割
        if duration <= max_duration:
            return [(audio_path, 0.0, duration)]
        
        # 分割音频
        self._log(f"  音频超过限制，开始分割...")
        
        def progress_callback(current, total, message):
            self._log(f"  {message}")
        
        success, msg, chunks = split_audio_by_duration(
            audio_path,
            max_duration=max_duration,
            progress_callback=progress_callback
        )
        
        if not success:
            raise Exception(f"音频分割失败: {msg}")
        
        # 记录临时文件
        for chunk_path, _, _ in chunks:
            self.temp_files.append(chunk_path)
        
        return chunks
    
    def _transcribe_chunks(self, chunks: List[Tuple[str, float, float]]) -> List[str]:
        """使用 ElevenLabs 转录所有音频片段"""
        client = ElevenLabsSTTClient()
        json_files = []
        
        # 获取 ElevenLabs API Key（如果有）
        elevenlabs_api_key = self.config.get('elevenlabs_api_key', '')
        
        for i, (chunk_path, start, end) in enumerate(chunks, 1):
            duration = end - start
            self._log(f"  [{i}/{len(chunks)}] 转录: {os.path.basename(chunk_path)} ({duration:.1f}秒)")
            
            # 根据是否有 API Key 选择不同的转录方法
            if elevenlabs_api_key:
                self._log(f"  使用 ElevenLabs API (付费版)")
                result = client.transcribe_audio_official_api(
                    audio_file_path=chunk_path,
                    api_key=elevenlabs_api_key,
                    language_code=self.config.get('language'),
                    num_speakers=0,
                    enable_diarization=True,
                    tag_audio_events=True
                )
            else:
                self._log(f"  使用 ElevenLabs Web (免费版，可能失效)")
                result = client.transcribe_audio(
                    chunk_path,
                    language_code=self.config.get('language'),
                    tag_audio_events=True
                )
            
            if not result:
                raise Exception(f"转录失败: {chunk_path}")
            
            # 保存 JSON
            json_path = chunk_path.rsplit('.', 1)[0] + '.json'
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            self._log(f"  OK: 已保存: {json_path}")
            json_files.append(json_path)
            self.temp_files.append(json_path)
        
        return json_files
    
    def _merge_transcriptions(self, json_files: List[str], chunks: List[Tuple]) -> str:
        """合并多个转录JSON文件"""
        # 生成合并文件路径
        base_path = json_files[0].replace('_part001.json', '_merged.json')
        if base_path == json_files[0]:
            # 如果没有 _part001 后缀，使用其他命名
            base_path = json_files[0].rsplit('.', 1)[0] + '_merged.json'
        
        self._log(f"  合并 {len(json_files)} 个JSON文件...")
        
        success, msg = merge_elevenlabs_transcriptions(json_files, chunks, base_path)
        
        if not success:
            raise Exception(f"合并失败: {msg}")
        
        self._log(f"  OK: {msg}")
        self.temp_files.append(base_path)
        return base_path
    
    def _generate_srt(self, json_path: str, video_path: str) -> str:
        """LLM优化并生成SRT"""
        # 1. 解析 JSON
        self._log("  解析转录JSON...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        parser = TranscriptionParser()
        parsed = parser.parse(data, 'elevenlabs')
        
        if not parsed:
            raise Exception("JSON解析失败")
        
        self._log(f"  OK: 解析完成: {len(parsed.words)} 个单词")
        
        # 2. 提取文本
        full_text = ' '.join([w.text for w in parsed.words])
        self._log(f"  文本长度: {len(full_text)} 字符")
        
        # 3. LLM 分割优化
        self._log("  调用LLM进行文本分割优化...")
        segments = call_llm_api_for_segmentation(
            api_key=self.config['llm_api_key'],
            text_to_segment=full_text,
            custom_api_base_url_str=self.config.get('llm_api_url'),
            custom_model_name=self.config.get('llm_model'),
            custom_temperature=self.config.get('temperature', 0.3),
            target_language=self.config.get('language')
        )
        
        if not segments:
            raise Exception("LLM分割失败")
        
        self._log(f"  OK: LLM分割完成: {len(segments)} 个片段")
        
        # 4. 生成 SRT
        self._log("  生成SRT字幕...")
        processor = SrtProcessor()
        
        srt_content, _ = processor.process_to_srt(
            parsed_transcription=parsed,
            llm_segments_text=segments,
            source_format='elevenlabs',
            enable_ai_correction=False
        )
        
        # 5. 保存 SRT
        srt_path = video_path.rsplit('.', 1)[0] + '.srt'
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # 统计字幕条目数
        subtitle_count = srt_content.count('\n\n') + 1
        self._log(f"  OK: 生成 {subtitle_count} 条字幕")
        
        return srt_path
    
    def _cleanup_temp_files(self):
        """清理临时文件"""
        # 暂时禁用清理，方便调试
        return
        
        if not self.temp_files:
            return
        
        self._log("清理临时文件...")
        temp_dir = tempfile.gettempdir()
        
        for file_path in self.temp_files:
            try:
                # 只删除临时目录中的文件
                if file_path.startswith(temp_dir) and os.path.exists(file_path):
                    os.remove(file_path)
                    self._log(f"  OK: 已删除: {os.path.basename(file_path)}")
            except Exception as e:
                self._log(f"  Error: 删除失败 {os.path.basename(file_path)}: {e}")
