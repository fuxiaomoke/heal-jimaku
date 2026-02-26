"""
SRT字幕处理器模块

负责将ASR（自动语音识别）转录结果转换为标准的SRT字幕格式。
包含智能文本分割、时间戳精确对齐、字幕条目优化等核心功能。
支持多语言处理和自定义参数配置。

作者: fuxiaomoke
版本: 0.2.2.0
"""

import re
import difflib
import json
from typing import List, Optional, Any, Dict
from .data_models import TimestampedWord, ParsedTranscription, SubtitleEntry
import config as app_config # 使用别名以减少潜在冲突并清晰化来源

class SrtProcessor:
    """
    SRT字幕处理器

    负责将ASR转录结果转换为SRT字幕格式，包括文本分割、时间戳对齐、
    字幕优化等核心功能。
    """

    # SRT处理阶段的权重常量
    WEIGHT_ALIGN = 20  # 对齐阶段权重（基础SRT生成）
    WEIGHT_MERGE = 20  # 合并阶段权重
    WEIGHT_FORMAT = 20 # 格式化阶段权重（不包括AI纠错）
    WEIGHT_AI_CORRECTION = 40  # AI纠错阶段权重（仅Soniox模式使用）

    def __init__(self, initial_config: Optional[Dict[str, Any]] = None) -> None:
        """初始化SRT处理器"""
        self._signals: Optional[Any] = None
        self._current_progress_offset: int = 0
        self._current_progress_range: int = 100

    # Soniox 专用常量集合 (Mode C)
    SONIOX_THRESHOLDS = {
        "CONF_LIMIT": app_config.DEFAULT_SONIOX_LOW_CONFIDENCE_THRESHOLD,        # 置信度红线阈值
        "LARGE_GAP": 0.80,         # 异常大间距阈值 (秒)
        "EXT_GAP_MIN": 0.55,       # 安全加尾巴的最小间距 (秒)
        "TAIL_LEN": 0.30,          # 尾巴长度 (秒)
        "START_PAD": 0.25,         # 开始时间前摇 (秒)
        "RAPID_GAP": 0.15          # 急速连读判定阈值 (秒)
    }
    def __init__(self, initial_config: Optional[Dict[str, Any]] = None):
        self._signals: Optional[Any] = None
        self._current_progress_offset: int = 0
        self._current_progress_range: int = 100

        # 初始化SRT处理参数的默认值
        self.min_duration_target: float = app_config.DEFAULT_MIN_DURATION_TARGET
        self.max_duration: float = app_config.DEFAULT_MAX_DURATION
        self.max_chars_per_line: int = app_config.DEFAULT_MAX_CHARS_PER_LINE
        self.default_gap_ms: int = app_config.DEFAULT_DEFAULT_GAP_MS

        # 初始化LLM配置相关的成员变量
        self.llm_api_key: Optional[str] = app_config.DEFAULT_LLM_API_KEY
        self.llm_base_url: Optional[str] = app_config.DEFAULT_LLM_API_BASE_URL
        self.llm_model_name: Optional[str] = app_config.DEFAULT_LLM_MODEL_NAME
        self.llm_temperature: float = app_config.DEFAULT_LLM_TEMPERATURE

        if initial_config:
            self.configure_from_main_config(initial_config)

    def set_signals_forwarder(self, signals_forwarder: Any):
        self._signals = signals_forwarder

    def configure_from_main_config(self, main_config_data: Dict[str, Any]):
        """
        Update SRT processor parameters from main application configuration.

        Args:
            main_config_data: Dictionary containing configuration values using USER_..._KEY constants
        """
        # Update SRT parameters using USER_..._KEY from main configuration
        self.min_duration_target = float(main_config_data.get(app_config.USER_MIN_DURATION_TARGET_KEY, app_config.DEFAULT_MIN_DURATION_TARGET))
        self.max_duration = float(main_config_data.get(app_config.USER_MAX_DURATION_KEY, app_config.DEFAULT_MAX_DURATION))
        self.max_chars_per_line = int(main_config_data.get(app_config.USER_MAX_CHARS_PER_LINE_KEY, app_config.DEFAULT_MAX_CHARS_PER_LINE))
        self.default_gap_ms = int(main_config_data.get(app_config.USER_DEFAULT_GAP_MS_KEY, app_config.DEFAULT_DEFAULT_GAP_MS))

        # Update LLM parameters - use same approach as ConversionWorker for consistency
        # First try to get from legacy config keys (for backward compatibility)
        self.llm_api_key = main_config_data.get(app_config.USER_LLM_API_KEY_KEY, app_config.DEFAULT_LLM_API_KEY)
        self.llm_base_url = main_config_data.get(app_config.USER_LLM_API_BASE_URL_KEY, app_config.DEFAULT_LLM_API_BASE_URL)
        self.llm_model_name = main_config_data.get(app_config.USER_LLM_MODEL_NAME_KEY, app_config.DEFAULT_LLM_MODEL_NAME)
        self.llm_temperature = float(main_config_data.get(app_config.USER_LLM_TEMPERATURE_KEY, app_config.DEFAULT_LLM_TEMPERATURE))

        # If legacy keys are empty, try the new multi-profile system as fallback
        if not self.llm_api_key:
            current_llm_profile = app_config.get_current_llm_profile(main_config_data)
            self.llm_api_key = current_llm_profile.get("api_key", app_config.DEFAULT_LLM_API_KEY)
            if not self.llm_base_url or self.llm_base_url == app_config.DEFAULT_LLM_API_BASE_URL:
                self.llm_base_url = current_llm_profile.get("api_base_url", app_config.DEFAULT_LLM_API_BASE_URL)
            if not self.llm_model_name or self.llm_model_name == app_config.DEFAULT_LLM_MODEL_NAME:
                self.llm_model_name = current_llm_profile.get("model_name", app_config.DEFAULT_LLM_MODEL_NAME)

        self.log(f"配置LLM参数: API key前10字符={self.llm_api_key[:10] if self.llm_api_key else 'None'}..., base_url={self.llm_base_url}, model={self.llm_model_name}")

    # --- 新增/恢复 update_srt_params 方法 ---
    def update_srt_params(self, srt_params_dict: Dict[str, Any]):
        """
        Update SRT processing parameters from a simple dictionary.

        This method is called by MainWindow.start_conversion() with parameters
        from self.advanced_srt_settings.

        Args:
            srt_params_dict: Dictionary containing SRT processing parameters
        """
        self.min_duration_target = float(srt_params_dict.get('min_duration_target', self.min_duration_target))
        self.max_duration = float(srt_params_dict.get('max_duration', self.max_duration))
        self.max_chars_per_line = int(srt_params_dict.get('max_chars_per_line', self.max_chars_per_line))
        self.default_gap_ms = int(srt_params_dict.get('default_gap_ms', self.default_gap_ms))


    def update_llm_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ):
        self.log("正在单独更新 SrtProcessor 的LLM API参数...")
        if api_key is not None: self.llm_api_key = api_key
        if base_url is not None: self.llm_base_url = base_url
        if model is not None: self.llm_model_name = model
        if temperature is not None: self.llm_temperature = float(temperature)
        self.log(f"  LLM参数单独更新后: BaseURL='{self.llm_base_url}', Model='{self.llm_model_name}', Temp={self.llm_temperature}, APIKeySet={bool(self.llm_api_key)}")

    def get_current_llm_config_for_api_call(self) -> Dict[str, Any]:
        return {
            "api_key": self.llm_api_key,
            "custom_api_base_url_str": self.llm_base_url,
            "custom_model_name": self.llm_model_name,
            "custom_temperature": self.llm_temperature,
        }

    def log(self, message: str):
        if self._signals and hasattr(self._signals, 'log_message') and hasattr(self._signals.log_message, 'emit'):
            self._signals.log_message.emit(f"[SRT Processor] {message}")
        else:
            print(f"[SRT Processor] {message}")

    def _is_worker_running(self) -> bool: 
        if self._signals and hasattr(self._signals, 'parent') and \
           hasattr(self._signals.parent(), 'is_running'): 
            return self._signals.parent().is_running
        return True

    def _emit_srt_progress(self, current_step: int, total_steps: int):
        if total_steps == 0:
            internal_percentage = 100
        else:
            internal_percentage = min(int((current_step / total_steps) * 100), 100)
        
        if self._signals and hasattr(self._signals, 'progress') and hasattr(self._signals.progress, 'emit'):
            global_progress = self._current_progress_offset + int(internal_percentage * (self._current_progress_range / 100.0))
            capped_progress = min(max(global_progress, self._current_progress_offset), self._current_progress_offset + self._current_progress_range)
            capped_progress = min(capped_progress, 99) 
            self._signals.progress.emit(capped_progress)

    def _is_bracketed_content(self, text: str) -> bool:
        """检查文本是否为括号内容（任何括号内的内容都应该独立处理）"""
        if not text or not text.strip():
            return False

        text = text.strip()

        # 检查是否完全被括号包围
        # 支持各种括号类型：()、（）、【】、[]、{}、<>
        bracket_patterns = [
            r"^\(.*\)$",      # ()
            r"^（.*）$",        # （）
            r"^【.*】$",        # 【】
            r"^\[.*\]$",        # []
            r"^\{.*\}$",        # {}
            r"^<.*>$",          # <>
        ]

        return any(re.match(pattern, text) for pattern in bracket_patterns)

    
    def _is_audio_event_words(self, words_list) -> bool:
        """检查词列表是否为括号内容（代表非语言声音或特殊标记）"""
        if not words_list:
            return False

        # 组合所有词的文本
        full_text = "".join([w.text for w in words_list]).strip()

        # 检查是否为括号内容
        if self._is_bracketed_content(full_text):
            return True

        # 如果ASR标记为audio_event类型，也认为是音频事件
        return any(getattr(w, 'type', 'word') == 'audio_event' for w in words_list)

    def format_timecode(self, seconds_float: float) -> str:
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0:
            return "00:00:00,000"
        total_seconds_int = int(seconds_float)
        milliseconds = int(round((seconds_float - total_seconds_int) * 1000))
        if milliseconds >= 1000:
            total_seconds_int += 1
            milliseconds = 0
        hours = total_seconds_int // 3600
        minutes = (total_seconds_int % 3600) // 60
        seconds = total_seconds_int % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def check_word_has_punctuation(self, word_text: str, punctuation_set: set) -> bool:
        """检查词汇是否包含标点符号（包括词汇本身是标点或以标点结尾）"""
        import re
        import unicodedata

        cleaned_text = word_text.strip()
        if not cleaned_text:
            return False

        # 0. 只过滤明显的无效内容：纯空格、单个标点符号
        if len(cleaned_text) == 1:
            # 只过滤单个空格和单个标点符号
            if cleaned_text == ' ' or cleaned_text in punctuation_set:
                return True

        # 调试：记录详细的检测过程
        step1_match = cleaned_text in punctuation_set
        step2_match = False
        step3_match = False
        step4_match = False

        # 1. 检查词汇本身是否在预定义标点符号集合中
        if step1_match:
            return True

        # 2. 检查词汇是否以预定义标点符号结尾 - 精确匹配，优先级最高
        for punct in punctuation_set:
            if cleaned_text.endswith(punct):
                return True

        # 3. 检查常见的省略号模式（仅对ELLIPSIS_PUNCTUATION检测）
        # 只有在检测省略号集合时才使用省略号正则表达式
        ellipsis_chars_in_set = any(p in punctuation_set for p in ['...', '......', '‥', '…'])
        if ellipsis_chars_in_set:
            ellipsis_patterns = [r'…+', r'‥+', r'\.{3,}']  # 按优先级排序，避免重叠
            for pattern in ellipsis_patterns:
                if re.search(pattern + '$', cleaned_text):
                    return True

        # 4. 使用Unicode类别检测标点符号 - 但排除常见标点避免重复匹配
        # Unicode标点符号类别：Pc (连接符), Pd (破折号), Pe (后引号), Pf (后引号), Pi (前引号), Po (其他标点), Ps (前引号)
        last_char = cleaned_text[-1] if len(cleaned_text) > 0 else ''
        # 排除已经被精确处理的常见标点符号，避免交叉匹配
        excluded_chars = {'.', '。', '?', '？', '!', '！', ',', '、', '，', '…', '‥'}
        if last_char and last_char not in excluded_chars:
            if unicodedata.category(last_char) in ['Pc', 'Pd', 'Pe', 'Pf', 'Pi', 'Po', 'Ps']:
                return True

        return False

    def get_segment_words_fuzzy(self, text_segment: str, all_parsed_words: List[TimestampedWord], start_search_index: int) -> tuple[List[TimestampedWord], int, float]:
        """
        Fuzzy matching algorithm for aligning LLM segments with ASR word timestamps.

        Args:
            text_segment: LLM-generated text segment to align
            all_parsed_words: List of ASR words with timestamps
            start_search_index: Starting index in the word list for search

        Returns:
            Tuple of (matched_words, next_search_index, match_ratio)
        """
        segment_clean = text_segment.strip().replace(" ", "")
        if not segment_clean:
            return [], start_search_index, 0.0

        best_match_words_ts_objects: List[TimestampedWord] = []
        best_match_ratio = 0.0
        best_match_end_index = start_search_index

        # 使用适当的搜索窗口大小
        base_len_factor = 3
        min_additional_words = 20
        max_additional_words = 60
        estimated_words_in_segment = len(text_segment.split())
        search_window_size = len(segment_clean) * base_len_factor + min(max(estimated_words_in_segment * 2, min_additional_words), max_additional_words)
        max_lookahead_outer = min(start_search_index + search_window_size, len(all_parsed_words))

        for i in range(start_search_index, max_lookahead_outer):
            if not self._is_worker_running():
                break

            current_words_text_list = []
            current_word_ts_object_list: List[TimestampedWord] = []
            max_j_lookahead = min(i + len(segment_clean) + 30, len(all_parsed_words))

            for j in range(i, max_j_lookahead):
                word_obj = all_parsed_words[j]
                current_word_ts_object_list.append(word_obj)
                current_words_text_list.append(word_obj.text.replace(" ", ""))
                built_text = "".join(current_words_text_list)

                if not built_text.strip():
                    continue

                matcher = difflib.SequenceMatcher(None, segment_clean, built_text, autojunk=False)
                ratio = matcher.ratio()

                update_best = False
                if ratio > best_match_ratio:
                    update_best = True
                elif abs(ratio - best_match_ratio) < 1e-9:
                    if best_match_words_ts_objects:
                        current_len_diff = abs(len(built_text) - len(segment_clean))
                        best_len_diff = abs(len("".join(w.text.replace(" ","") for w in best_match_words_ts_objects)) - len(segment_clean))
                        if current_len_diff < best_len_diff:
                            update_best = True
                    else:
                        update_best = True

                if update_best and ratio > 0.01:
                    best_match_ratio = ratio
                    best_match_words_ts_objects = list(current_word_ts_object_list)
                    best_match_end_index = j + 1

                if ratio > 0.95 and len(built_text) > len(segment_clean) * 1.8:
                    break

            if best_match_ratio > 0.98:
                break

        if not best_match_words_ts_objects:
            self.log(f"严重警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 无法在ASR词语中找到任何匹配。将跳过此片段。搜索起始索引: {start_search_index}")
            return [], start_search_index, 0.0

        if best_match_ratio < app_config.ALIGNMENT_SIMILARITY_THRESHOLD:
            matched_text_preview = "".join([w.text for w in best_match_words_ts_objects])
            self.log(f"警告: LLM片段 \"{text_segment}\" (清理后: \"{segment_clean}\") 与ASR词语的对齐相似度较低 ({best_match_ratio:.2f})。ASR匹配文本: \"{matched_text_preview}\"")

            # 回退对齐策略：如果相似度不低于阈值的70%，则使用回退策略
            relaxed_threshold = app_config.ALIGNMENT_SIMILARITY_THRESHOLD * 0.7
            if best_match_ratio >= relaxed_threshold:
                self.log(f"⚠️ 使用回退对齐策略，相似度: {best_match_ratio:.2f} (低于标准阈值 {app_config.ALIGNMENT_SIMILARITY_THRESHOLD:.2f} 但高于回退阈值 {relaxed_threshold:.2f})")
                # 在回退策略下，仍然返回匹配结果，但记录警告
                return best_match_words_ts_objects, best_match_end_index, best_match_ratio
            else:
                # 如果连回退阈值都达不到，则返回空结果
                self.log(f"❌ 回退对齐策略失败，相似度{best_match_ratio:.2f}低于回退阈值{relaxed_threshold:.2f}，跳过此片段")
                return [], start_search_index, 0.0

        return best_match_words_ts_objects, best_match_end_index, best_match_ratio

    # --- 结束时间修正 辅助函数 ---
    def _apply_end_time_correction(self, segment_words: List[TimestampedWord], raw_end_time: float, segment_start_time: float) -> float:
        """
        应用结束时间修正逻辑（检查词间空隙、倒二词时长、末尾词时长）。
        """
        if not segment_words:
            return raw_end_time

        duration_threshold = 0.35  # 异常时长阈值 (0.35s)
        gap_threshold = 0.6       # 异常空隙阈值 (0.6s)
        correction_padding = 0.25  # 修正时使用的"留白" (0.25s)
        
        # 检查1 (空隙优先): 检查倒数第二个词和最后一个词之间的“空隙”
        if len(segment_words) > 1:
            last_word = segment_words[-1]
            word_before_last = segment_words[-2]
            
            gap_duration = last_word.start_time - word_before_last.end_time
            
            if gap_duration > gap_threshold:
                self.log(f"字幕时间优化: 修正词间异常空隙 ({gap_duration:.2f}s)")
                # 以"倒二词"的 *开始* 时间为基准
                new_end_time = word_before_last.start_time + correction_padding
                
                # 安全检查
                if new_end_time < segment_start_time:
                    return segment_start_time + correction_padding
                return new_end_time # 命中规则，立即返回

        # 检查2 (倒二词时长): (仅在“空隙”干净时才执行此检查)
        if len(segment_words) > 1:
            word_before_last = segment_words[-2]
            word_before_last_duration = word_before_last.end_time - word_before_last.start_time
            
            if word_before_last_duration > duration_threshold:
                self.log(f"字幕时间优化: 修正异常词时长 ({word_before_last_duration:.2f}s)")
                new_end_time = word_before_last.start_time + correction_padding
                
                # 安全检查
                if new_end_time < segment_start_time:
                    return segment_start_time + correction_padding
                return new_end_time # 命中规则，立即返回

        # 检查3 (末尾词时长): (仅在“空隙”和“倒二词”都干净时才执行此检查)
        last_word = segment_words[-1]
        last_word_duration = last_word.end_time - last_word.start_time
        
        if last_word_duration > duration_threshold:
            self.log(f"字幕时间优化: 修正末尾词异常时长 ({last_word_duration:.2f}s)")
            new_end_time = last_word.start_time + correction_padding

            # 安全检查
            if new_end_time < segment_start_time:
                return segment_start_time + correction_padding
            return new_end_time # 命中规则

        # 如果所有检查都通过，返回原始时间
        return raw_end_time
    # --- 辅助函数 结束 ---

    def _apply_smart_split_strategy(self, sentence_text: str, sentence_words: List[TimestampedWord],
                              original_start_time: float, original_end_time: float
                             ) -> Optional[List[SubtitleEntry]]:
        """
        智能分割策略：强制在标点符号处分割，最多3段，允许超限

        规则：
        1. 如果句子中有非句末标点，强制在标点处分割
        2. 最多分割成3段，如果做不到则允许超限
        3. 优先选择句末标点，其次是逗号，最后是中间强制分割

        Args:
            sentence_text: 要分割的句子文本
            sentence_words: 词汇列表
            original_start_time: 开始时间
            original_end_time: 结束时间

        Returns:
            分割后的字幕条目列表，如果不适用此策略则返回None
        """
        import re

        # 检查句子中是否有非句末标点符号
        # 移除句末的标点符号进行检查
        text_without_end = re.sub(r'[。！？\.\!]?$', '', sentence_text.strip())
        has_non_end_punctuation = (
            '，' in text_without_end or
            '、' in text_without_end or
            '...' in text_without_end or
            '…' in text_without_end
        )

        if not has_non_end_punctuation:
            # 没有非句末标点，不应用此策略
            return None

        self.log(f"   🔧 智能分割: 检测到内含标点，应用强制分割策略")

        # 寻找所有可能的分割点
        split_indices = []
        for i, word_obj in enumerate(sentence_words[:-1]):  # 不在最后一个词后分割
            w_text = word_obj.text.strip()

            # 优先级1: 句末标点（。！？. !）
            if self.check_word_has_punctuation(w_text, app_config.FINAL_PUNCTUATION):
                split_indices.append(i)
            # 优先级2: 省略号（...）
            elif self.check_word_has_punctuation(w_text, app_config.ELLIPSIS_PUNCTUATION):
                split_indices.append(i)
            # 优先级3: 逗号类（，、）
            elif self.check_word_has_punctuation(w_text, app_config.COMMA_PUNCTUATION):
                split_indices.append(i)

        if not split_indices:
            self.log(f"   ⚠️ 智能分割: 虽有标点但未找到合适分割点，使用默认策略")
            return None

        # 选择最佳分割点：尽量均匀分割，优先靠前的标点
        if len(split_indices) >= 2:
            # 有多个分割点，选择能产生较均匀分割的点
            target_split_positions = [
                len(sentence_words) // 3,  # 三分之一位置
                len(sentence_words) // 2,  # 二分之一位置
                len(sentence_words) * 2 // 3  # 三分之二位置
            ]
            best_splits = []
            for target_pos in target_split_positions:
                closest_idx = min(split_indices, key=lambda i: abs(i - target_pos))
                if closest_idx not in best_splits:
                    best_splits.append(closest_idx)
            selected_splits = best_splits[:2]  # 最多选择2个分割点，产生3段
        else:
            selected_splits = split_indices[:2]  # 最多2个分割点

        if not selected_splits:
            return None

        self.log(f"   📏 智能分割: 选择{len(selected_splits)}个分割点，预计生成{len(selected_splits)+1}段")

        # 执行分割
        result_entries = []
        start_idx = 0

        for split_idx in selected_splits:
            if split_idx < start_idx:
                continue

            # 创建当前段
            segment_words = sentence_words[start_idx:split_idx+1]
            segment_text = "".join([w.text for w in segment_words])
            segment_start = segment_words[0].start_time
            segment_end = segment_words[-1].end_time

            entry = SubtitleEntry(0, segment_start, segment_end, segment_text, segment_words)
            # 允许超限，设置标记
            if entry.duration > self.max_duration or len(segment_text) > self.max_chars_per_line:
                entry.is_intentionally_oversized = True
                self.log(f"   ⚠️ 智能分割: 段落超限但接受 - \"{segment_text[:20]}...\" ({entry.duration:.2f}s)")
            else:
                self.log(f"   ✅ 智能分割: 段落正常 - \"{segment_text[:20]}...\" ({entry.duration:.2f}s)")

            result_entries.append(entry)
            start_idx = split_idx + 1

        # 处理最后一段
        if start_idx < len(sentence_words):
            segment_words = sentence_words[start_idx:]
            segment_text = "".join([w.text for w in segment_words])
            segment_start = segment_words[0].start_time
            segment_end = original_end_time  # 最后一段使用原始结束时间

            entry = SubtitleEntry(0, segment_start, segment_end, segment_text, segment_words)
            if entry.duration > self.max_duration or len(segment_text) > self.max_chars_per_line:
                entry.is_intentionally_oversized = True
                self.log(f"   ⚠️ 智能分割: 最后段落超限但接受 - \"{segment_text[:20]}...\" ({entry.duration:.2f}s)")
            else:
                self.log(f"   ✅ 智能分割: 最后段落正常 - \"{segment_text[:20]}...\" ({entry.duration:.2f}s)")

            result_entries.append(entry)

        self.log(f"   🎯 智能分割完成: 共{len(result_entries)}段")
        return result_entries

    def split_long_sentence(self, sentence_text: str, sentence_words: List[TimestampedWord],
                            original_start_time: float, original_end_time: float, _recursion_depth: int = 0,
                            override_end_time: Optional[float] = None
                           ) -> List[SubtitleEntry]:
        """
        分割超长的句子，基于标点符号优先级进行智能分割

        优先使用传入的纠错后文本进行分割，保持AI纠错结果

        Args:
            sentence_text: 要分割的句子文本（可能是AI纠错后的）
            sentence_words: 词汇列表（包含时间戳，用于时间对齐）
            original_start_time: 原始开始时间
            original_end_time: 原始结束时间
            _recursion_depth: 递归深度，用于防止无限递归

        Returns:
            分割后的字幕条目列表
        """
        # 常量定义
        MAX_RECURSION_DEPTH = 10
        MIN_SEGMENT_LENGTH = 3  # 最少3个词才尝试分割
        MAX_SEGMENTS = 3  # 最多分割成3段
        FORCE_PUNCTUATION_SPLIT = True  # 是否强制在标点符号处分割

        # 防止无限递归
        if _recursion_depth > MAX_RECURSION_DEPTH:
            self.log(f"   警告：递归深度过深({_recursion_depth})，强制返回")
            entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            entry.is_intentionally_oversized = True
            return [entry]

        # 防止过短片段继续分割
        if len(sentence_words) <= MIN_SEGMENT_LENGTH:
            self.log(f"   片段过短({len(sentence_words)}词)，停止分割")
            entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                entry.end_time = entry.start_time + app_config.MIN_DURATION_ABSOLUTE
            if entry.duration > self.max_duration or len(sentence_text) > self.max_chars_per_line:
                entry.is_intentionally_oversized = True
            return [entry]

        # 检查是否为括号内容，如果是则不分割
        if self._is_bracketed_content(sentence_text.strip()):
            self.log(f"   检测到括号内容，跳过长句分割: \"{sentence_text}\"")
            entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                entry.end_time = entry.start_time + app_config.MIN_DURATION_ABSOLUTE
            if entry.duration > self.max_duration or len(sentence_text) > self.max_chars_per_line:
                entry.is_intentionally_oversized = True
            return [entry]

        # 空词列表处理
        if not sentence_words:
            if sentence_text.strip():
                self.log(f"警告: split_long_sentence 收到空词列表但有文本: \"{sentence_text}\"。将创建单个条目。")
                entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, [])
                if entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                    entry.end_time = entry.start_time + app_config.MIN_DURATION_ABSOLUTE
                if entry.duration > self.max_duration or len(sentence_text) > self.max_chars_per_line:
                    entry.is_intentionally_oversized = True
                return [entry]
            return []

        # 单个词处理
        if len(sentence_words) <= 1:
            entry = SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)
            if entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                entry.end_time = entry.start_time + app_config.MIN_DURATION_ABSOLUTE
            if entry.duration > self.max_duration or len(sentence_text) > self.max_chars_per_line:
                entry.is_intentionally_oversized = True
            return [entry]

        # 预检查长度
        char_len = len(sentence_text)
        if char_len <= self.max_chars_per_line and (original_end_time - original_start_time) <= self.max_duration:
            return [SubtitleEntry(0, original_start_time, original_end_time, sentence_text, sentence_words)]

        # 检查是否需要应用智能分割策略
        if FORCE_PUNCTUATION_SPLIT and _recursion_depth == 0:
            # 应用智能分割策略：标点强制分割 + 最多3段 + 允许超限
            smart_split_result = self._apply_smart_split_strategy(
                sentence_text, sentence_words, original_start_time, original_end_time
            )
            if smart_split_result:
                return smart_split_result

        entries = []
        words_to_process = list(sentence_words)

        # 寻找标点符号分割点（按优先级排序）
        potential_split_indices_by_priority = {
            'final': [],      # 。！？（最高优先级）
            'semicolon': [],  # ；（第二优先级）
            'ellipsis': [],   # ……（第三优先级）
            'comma': []       # ，、（第四优先级）
        }

  
        for idx, word_obj in enumerate(words_to_process[:-1]):  # 不在最后一个词后分割
            w_text = word_obj.text.strip()

              # 按优先级顺序检测标点：final > semicolon > ellipsis > comma
            if self.check_word_has_punctuation(w_text, app_config.FINAL_PUNCTUATION):
                potential_split_indices_by_priority['final'].append(idx)
            elif self.check_word_has_punctuation(w_text, app_config.ELLIPSIS_PUNCTUATION):
                # 检查是否包含分号（中文分号优先级高于省略号）
                if ';' in w_text or '；' in w_text:
                    potential_split_indices_by_priority['semicolon'].append(idx)
                else:
                    potential_split_indices_by_priority['ellipsis'].append(idx)
            elif self.check_word_has_punctuation(w_text, app_config.COMMA_PUNCTUATION):
                potential_split_indices_by_priority['comma'].append(idx)

        # 选择最佳分割点 - 按优先级顺序：final > semicolon > ellipsis > comma
        best_split_index = -1
        center_pos = len(words_to_process) / 2
        find_closest = lambda indices: min(indices, key=lambda i: abs(i - center_pos)) if indices else -1

        # 按优先级顺序检查
        if potential_split_indices_by_priority['final']:
            best_split_index = find_closest(potential_split_indices_by_priority['final'])
        elif potential_split_indices_by_priority['semicolon']:
            best_split_index = find_closest(potential_split_indices_by_priority['semicolon'])
        elif potential_split_indices_by_priority['ellipsis']:
            # 对于省略号，优先选择真正的省略号('...'或'…')
            real_ellipsis_indices = []
            for idx in potential_split_indices_by_priority['ellipsis']:
                w_text = words_to_process[idx].text.strip()
                if '...' in w_text or '…' in w_text:  # 真正的省略号
                    real_ellipsis_indices.append(idx)

            if real_ellipsis_indices:
                # 从真正的省略号中选择距离中心最近的
                best_split_index = find_closest(real_ellipsis_indices)
            else:
                # 如果没有真正的省略号，选择最接近的伪省略号
                best_split_index = find_closest(potential_split_indices_by_priority['ellipsis'])
        elif potential_split_indices_by_priority['comma']:
            best_split_index = find_closest(potential_split_indices_by_priority['comma'])

        # 如果没有标点，在中间分割
        if best_split_index == -1:
            best_split_index = len(words_to_process) // 2

        # 执行分割
        first_segment_words = words_to_process[:best_split_index+1]
        second_segment_words = words_to_process[best_split_index+1:]

        # 智能分割纠错后的文本，保持AI纠错结果
        corrected_segments = self._split_corrected_text_by_words(sentence_text, first_segment_words, second_segment_words)

        # 处理第一段
        first_text = corrected_segments["first"]
        # 如果智能分割失败，回退到原始逻辑
        if not first_text:
            first_text = "".join([w.text for w in first_segment_words])
        first_start = first_segment_words[0].start_time
        # 对于第一段，使用词的原始结束时间；只有在没有第二段时才考虑override_end_time
        first_end = first_segment_words[-1].end_time
        first_duration = first_end - first_start

        # 检查分割后的片段时长
        if first_duration > self.max_duration:
            # 递归分割：再次调用split_long_sentence来处理超限的第一段
            entries.extend(self.split_long_sentence(first_text, first_segment_words, first_start, first_end, _recursion_depth + 1, override_end_time))
        else:
            first_entry = SubtitleEntry(0, first_start, first_end, first_text, first_segment_words)

            # === [修复] 对返回条目应用时间检测修正 ===
            if first_entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                first_entry.end_time = first_entry.start_time + app_config.MIN_DURATION_ABSOLUTE

            # 对非音频事件且时长合理的条目应用Mode B时间检测
            is_audio_event = self._is_bracketed_content(first_text)
            if not is_audio_event and len(first_segment_words) > 1 and first_duration <= self.max_duration:
                # 应用 Mode B 的时间修正逻辑
                corrected_end_time = self._apply_end_time_correction(
                    first_segment_words,
                    first_entry.end_time,
                    first_entry.start_time
                )
                if corrected_end_time != first_entry.end_time:
                    self.log(f"字幕时间优化: 对分割条目应用时间修正 (原时长: {first_entry.duration:.2f}s -> 修正后: {corrected_end_time - first_entry.start_time:.2f}s)")
                    first_entry.end_time = corrected_end_time

            entries.append(first_entry)

        # 处理第二段
        if second_segment_words:  # 确保还有词汇
            second_text = corrected_segments["second"]
            # 如果智能分割失败，回退到原始逻辑
            if not second_text:
                second_text = "".join([w.text for w in second_segment_words])
            second_start = second_segment_words[0].start_time
            # 对于第二段（最后一段），使用override_end_time（如果提供了的话）
            second_end = override_end_time if override_end_time is not None else second_segment_words[-1].end_time
            second_duration = second_end - second_start

            # 检查分割后的片段时长
            if second_duration > self.max_duration:
                # 递归分割：再次调用split_long_sentence来处理超限的第二段
                entries.extend(self.split_long_sentence(second_text, second_segment_words, second_start, second_end, _recursion_depth + 1, override_end_time))
            else:
                second_entry = SubtitleEntry(0, second_start, second_end, second_text, second_segment_words)

                # === [修复] 对返回条目应用时间检测修正 ===
                if second_entry.duration < app_config.MIN_DURATION_ABSOLUTE:
                    second_entry.end_time = second_entry.start_time + app_config.MIN_DURATION_ABSOLUTE

                # 对非音频事件且时长合理的条目应用Mode B时间检测
                is_audio_event = self._is_bracketed_content(second_text)
                if not is_audio_event and len(second_segment_words) > 1 and second_duration <= self.max_duration:
                    # 应用 Mode B 的时间修正逻辑
                    corrected_end_time = self._apply_end_time_correction(
                        second_segment_words,
                        second_entry.end_time,
                        second_entry.start_time
                    )
                    if corrected_end_time != second_entry.end_time:
                        self.log(f"字幕时间优化: 对分割条目应用时间修正 (原时长: {second_entry.duration:.2f}s -> 修正后: {corrected_end_time - second_entry.start_time:.2f}s)")
                        second_entry.end_time = corrected_end_time

                entries.append(second_entry)

        # === [新增] 对分割后的条目进行间距验证 ===
        if len(entries) >= 2:
            entries = self._validate_and_adjust_split_spacing(entries)

        return entries

    def _split_corrected_text_by_words(self, corrected_text: str, first_words: List[TimestampedWord],
                                     second_words: List[TimestampedWord]) -> Dict[str, str]:
        """
        根据词汇分割点智能分割纠错后的文本

        Args:
            corrected_text: AI纠错后的完整文本
            first_words: 第一段词汇（包含分割点）
            second_words: 第二段词汇

        Returns:
            包含分割后两段文本的字典: {"first": "第一段", "second": "第二段"}
        """
        if not second_words:
            return {"first": corrected_text, "second": ""}

        first_segment_text = "".join([w.text for w in first_words])
        second_segment_text = "".join([w.text for w in second_words])

        # 重新构建原始的词汇顺序，用于对齐
        all_words = first_words + second_words
        original_text = "".join([w.text for w in all_words])

        # 方法1：直接使用词汇文本拼接（优先级最高）
        # 这是最准确的方法，因为它直接使用词汇分割结果
        result = {"first": first_segment_text, "second": second_segment_text}

        # 验证拼接结果是否与原始文本匹配（去除空格后）
        combined = (first_segment_text + second_segment_text).replace(" ", "")
        original_clean = corrected_text.replace(" ", "")

        if combined == original_clean:
            return result
        else:
            # 方法2：智能对齐（fallback）
            # 在纠错文本中寻找第一段文本的起始位置
            first_text_clean = first_segment_text.replace(" ", "")

        # 寻找第一段在纠错文本中的位置
            split_pos = -1
            if first_text_clean in corrected_text.replace(" ", ""):
                # 直接匹配
                corrected_clean = corrected_text.replace(" ", "")
                split_pos = corrected_clean.find(first_text_clean) + len(first_text_clean)
            else:
                # 模糊匹配：寻找最接近的匹配
                best_match_pos = -1
                best_match_ratio = 0

                for i in range(len(corrected_text)):
                    for j in range(i + min(5, len(corrected_text) - i), len(corrected_text) + 1):
                        segment = corrected_text[i:j]
                        # 计算与第一段的相似度
                        if len(first_text_clean) > 0 and len(segment) > 0:
                            common_chars = sum(1 for a, b in zip(first_text_clean[:len(segment)], segment) if a == b)
                            ratio = common_chars / max(len(segment), len(first_text_clean[:len(segment)]))

                            if ratio > best_match_ratio and ratio > 0.7:  # 至少70%匹配
                                best_match_ratio = ratio
                                best_match_pos = i + len(segment)

                if best_match_pos > 0:
                    split_pos = best_match_pos

        # 如果找到了分割位置，使用它
            if split_pos > 0 and split_pos < len(corrected_text):
                first_text = corrected_text[:split_pos].strip()
                second_text = corrected_text[split_pos:].strip()
                result = {"first": first_text, "second": second_text}
                return result

        # 方法3：回退到原始逻辑
        return {"first": first_segment_text, "second": second_segment_text}

    def _validate_and_adjust_split_spacing(self, entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        对分割后的字幕条目进行间距验证和调整

        确保分割后的相邻字幕之间保持用户设定的最小间距要求

        Args:
            entries: 分割后的字幕条目列表

        Returns:
            经过间距验证和调整的字幕条目列表
        """
        if len(entries) < 2:
            return entries

        min_spacing_seconds = self.default_gap_ms / 1000.0
        adjustments_made = 0

        self.log(f"   🔍 分割间距验证：检查{len(entries)}个分割条目的最小间距 (要求: {self.default_gap_ms}ms)")

        for i in range(len(entries) - 1):
            current_entry = entries[i]
            next_entry = entries[i + 1]

            # 计算当前间距
            current_gap = next_entry.start_time - current_entry.end_time

            if current_gap < min_spacing_seconds:
                self.log(f"   🔍 检测到分割间距过小：字幕{current_entry.index} -> 字幕{next_entry.index} "
                        f"(当前间距: {current_gap:.3f}s, 要求最小间距: {min_spacing_seconds:.3f}s)")

                # 应用间距调整逻辑
                adjustment_needed = min_spacing_seconds - current_gap

                # 检查调整的安全性：使用0.35s阈值
                max_safe_adjustment = 0.35

                if adjustment_needed <= max_safe_adjustment:
                    # 安全调整：移动下一个字幕的开始时间
                    new_start_time = next_entry.start_time + adjustment_needed

                    # 确保不会与后续字幕产生重叠
                    if i + 2 < len(entries):
                        following_entry = entries[i + 2]
                        if new_start_time + 0.1 >= following_entry.start_time:  # 保留0.1s安全距离
                            self.log(f"   ⚠️ 调整受限：会与字幕{following_entry.index}重叠")
                            new_start_time = following_entry.start_time - 0.1
                            adjustment_needed = new_start_time - next_entry.start_time

                    # 应用调整
                    if adjustment_needed > 0.001:  # 只进行有意义的调整
                        original_duration = next_entry.duration
                        next_entry.start_time = new_start_time
                        self.log(f"   ✅ 调整分割字幕{next_entry.index}开始时间: +{adjustment_needed:.3f}s "
                                f"(时长: {original_duration:.3f}s -> {next_entry.duration:.3f}s)")
                        adjustments_made += 1
                else:
                    # 调整量过大，记录警告但不调整
                    self.log(f"   ⚠️ 跳过调整：所需调整量({adjustment_needed:.3f}s)超过安全阈值({max_safe_adjustment:.3f}s)")

        if adjustments_made == 0:
            self.log("   🔍 分割间距验证：未发现需要调整的间距问题")
        else:
            self.log(f"   🔍 分割间距验证：完成，共调整了 {adjustments_made} 个分割字幕的时序")

        return entries

    # --- 智能合并算法辅助函数 (移植自 Scribe2SRT) ---
    def _filter_low_confidence_words(self, words: List[TimestampedWord]) -> List[TimestampedWord]:
        """
        过滤低置信度词汇，排除包含标点符号的词汇

        Args:
            words: 词汇列表

        Returns:
            过滤后的低置信度词汇列表（已排除标点符号）
        """
        all_punctuation = app_config.ALL_SPLIT_PUNCTUATION
        filtered_words = []

        for word in words:
            # 只保留真正低置信度且不包含标点符号的词汇
            if word.confidence < self.SONIOX_THRESHOLDS["CONF_LIMIT"]:
                if not self.check_word_has_punctuation(word.text, all_punctuation):
                    filtered_words.append(word)

        return filtered_words

    def _is_cjk(self, text: str) -> bool:
        """检查文本是否包含 CJK (中日韩) 字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff' or \
               '\u3040' <= char <= '\u309f' or \
               '\u30a0' <= char <= '\u30ff' or \
               '\uac00' <= char <= '\ud7af':
                return True
        return False

    def _calculate_cps(self, text: str, duration: float) -> float:
        """计算每秒字符数 (CPS)"""
        if duration <= 0: return 999.0
        # 去除空白字符计算实际字符数
        char_count = len(re.sub(r'\s+', '', text))
        return char_count / duration

    def _can_merge_entries(self, entry1: SubtitleEntry, entry2: SubtitleEntry) -> tuple[bool, str]:
        """检查两个条目是否可以合并"""
        # 1. 检查音频事件 (Audio Events)
        # 任何包含音频事件的条目都不应合并
        is_evt1 = self._is_bracketed_content(entry1.text) or (self._is_audio_event_words(entry1.words_used) if entry1.words_used else False)
        is_evt2 = self._is_bracketed_content(entry2.text) or (self._is_audio_event_words(entry2.words_used) if entry2.words_used else False)
        if is_evt1 or is_evt2: return False, "包含音频事件"

        # 2. 检查时间间隔 (Gap)
        gap = entry2.start_time - entry1.end_time
        if gap > 2.0: return False, "时间间隔过大"
        
        # 3. 检查合并后的时长 (Duration)
        merged_duration = entry2.end_time - entry1.start_time
        if merged_duration > self.max_duration: return False, "合并后时长过长"

        # 4. 检查文本长度和 CPS
        # 确定分隔符：如果是两个 CJK 文本，中间不加空格
        sep = "" if (self._is_cjk(entry1.text) and self._is_cjk(entry2.text)) else " "
        merged_text = entry1.text + sep + entry2.text
        
        if len(merged_text) > self.max_chars_per_line: return False, "合并后文本过长"
        
        cps = self._calculate_cps(merged_text, merged_duration)
        # 动态 CPS 限制：CJK 稍微严格一点，Latin 宽松一点
        max_cps = 13.0 if self._is_cjk(merged_text) else 18.0 
        if cps > max_cps: return False, f"合并后语速过快 (CPS: {cps:.1f})"

        return True, "OK"

    def _calculate_merge_benefit(self, entry1: SubtitleEntry, entry2: SubtitleEntry) -> float:
        """计算合并收益分数 (分数越高越值得合并)"""
        score = 0.0
        
        # 1. 时长收益：合并过短的条目收益很高
        if entry1.duration < self.min_duration_target:
            score += (self.min_duration_target - entry1.duration) * 20
        if entry2.duration < self.min_duration_target:
            score += (self.min_duration_target - entry2.duration) * 20
            
        # 2. 间隔收益：间隔越小越好
        gap = entry2.start_time - entry1.end_time
        if gap < 0.3:
            score += (0.3 - gap) * 10
        elif gap < 0.5:
            score += (0.5 - gap) * 5
            
        # 3. 文本长度收益：合并极短文本收益较高
        if len(entry1.text) < 5: score += 5
        if len(entry2.text) < 5: score += 5
        
        return score

    def _merge_two_entries(self, entry1: SubtitleEntry, entry2: SubtitleEntry) -> SubtitleEntry:
        """执行合并操作"""
        # 智能处理空格
        sep = "" if (self._is_cjk(entry1.text) and self._is_cjk(entry2.text)) else " "
        merged_text = entry1.text + sep + entry2.text
        
        merged_words = (entry1.words_used or []) + (entry2.words_used or [])
        merged_ratio = min(entry1.alignment_ratio, entry2.alignment_ratio)
        
        return SubtitleEntry(0, entry1.start_time, entry2.end_time, merged_text, merged_words, merged_ratio)
    # --- 智能合并算法结束 ---

    def _process_mode_c_soniox(self, entries: List[SubtitleEntry], parsed_transcription: Optional[ParsedTranscription] = None) -> List[str]:
        """
        Mode C: Soniox专用处理逻辑

        Args:
            entries: 字幕条目列表，会被直接修改
            parsed_transcription: 转录数据（可选，包含元数据）

        Returns:
            List[str]: 校对提示列表
        """
        self.log("--- 开始Mode C处理：Soniox专用时间优化 ---")

        low_conf_hints: List[str] = []
        i = 0

        while i < len(entries):
            curr = entries[i]
            next_entry = entries[i + 1] if i + 1 < len(entries) else None

            # 1. 收集低置信度词 (用于生成校对报告)，排除标点符号
            low_conf_words = self._filter_low_confidence_words(curr.words_used)
            if low_conf_words:
                # 获取上下文：前后各一个条目
                prev_text = entries[i-1].text if i > 0 else ""
                next_text = entries[i+1].text if i+1 < len(entries) else ""

                # 格式化校对提示
                low_conf_words_str = ", ".join([f"{w.text}({w.confidence:.2f})" for w in low_conf_words])
                hint = f"低置信度词汇: {low_conf_words_str}\n"
                hint += f"上下文: {prev_text} [{curr.text}] {next_text}\n"
                hint += f"时间: {self.format_timecode(curr.start_time)} --> {self.format_timecode(curr.end_time)}\n"
                hint += "-" * 50
                low_conf_hints.append(hint)

            if next_entry:
                gap = next_entry.start_time - curr.end_time

                # 2. 急速连读处理 (逻辑③)
                if gap < self.SONIOX_THRESHOLDS["RAPID_GAP"]:
                    self.log(f"连读合并: 间距{gap:.2f}s < {self.SONIOX_THRESHOLDS['RAPID_GAP']}s, 合并条目")
                    merged_entry = self._merge_two_entries(curr, next_entry)
                    # 用合并后的条目替换当前条目
                    entries[i] = merged_entry
                    entries.pop(i + 1)  # 移除已合并的下一个条目
                    continue  # 跳过i+1的处理

                # 3. 异常大间距修正 (逻辑① - 仅针对低置信度句尾)
                if curr.words_used:
                    last_word = curr.words_used[-1]
                    if (last_word.confidence < self.SONIOX_THRESHOLDS["CONF_LIMIT"] and
                        gap > self.SONIOX_THRESHOLDS["LARGE_GAP"]):
                        self.log(f"异常修正: 低置信度({last_word.confidence:.2f}) + 大间距({gap:.2f}s), 执行中点切断")
                        curr.end_time += (gap / 2)  # 中点切断
                        gap = next_entry.start_time - curr.end_time  # 更新gap

                # 4. 舒适度优化 (逻辑② & 开始时间优化)
                if gap > self.SONIOX_THRESHOLDS["EXT_GAP_MIN"]:
                    # 只有空间足够大，才同时做"加尾巴"和"前摇"
                    curr.end_time += self.SONIOX_THRESHOLDS["TAIL_LEN"]       # 加尾巴
                    next_entry.start_time -= self.SONIOX_THRESHOLDS["START_PAD"]  # 下一句前摇
                    self.log(f"舒适度优化: 加尾巴{self.SONIOX_THRESHOLDS['TAIL_LEN']}s, 前摇{self.SONIOX_THRESHOLDS['START_PAD']}s")

                # 5. 物理防重叠兜底
                if curr.end_time > next_entry.start_time:
                    self.log(f"防重叠修正: 强制分离重叠条目")
                    curr.end_time = next_entry.start_time - 0.01

            i += 1

        self.log(f"--- Mode C时间优化完成，生成{len(low_conf_hints)}条校对提示 ---")
        return low_conf_hints

    def _apply_mode_b_time_optimization(self, entries: List[SubtitleEntry]) -> None:
        """
        Mode B: ElevenLabs兼容时间优化策略

        对每个字幕条目单独进行3步检测和时间修正，然后判断是否需要分割
        """
        self.log("--- 开始Mode B时间优化：一句一句优化时间戳对比 ---")

        optimized_entries = []

        for entry in entries:
            # 跳过音频事件
            if self._is_audio_event_words(entry.words_used):
                optimized_entries.append(entry)
                continue

            # 跳过括号内容
            if self._is_bracketed_content(entry.text):
                optimized_entries.append(entry)
                continue

            # 跳过词数不足的条目
            if len(entry.words_used) <= 1:
                optimized_entries.append(entry)
                continue

            # 第一步：应用3步时间修正
            original_end_time = entry.end_time
            corrected_end_time = self._apply_end_time_correction(entry.words_used, entry.end_time, entry.start_time)

            # 第二步：重新计算时长，判断是否超限
            corrected_duration = max(0.001, corrected_end_time - entry.start_time)

            # 第三步：根据修正后的时长决定处理方式
            if corrected_duration > self.max_duration or len(entry.text) > self.max_chars_per_line:
                # 修正后仍然超限，需要进行分割
                self.log(f"   ⚠️ Mode B: 修正后仍超限，需分割: \"{entry.text[:30]}...\" (修正后时长: {corrected_duration:.2f}s)")

                # 使用修正后的时间进行分割
                original_text_for_splitting = "".join([w.text for w in entry.words_used])
                split_entries = self.split_long_sentence(
                    original_text_for_splitting,
                    entry.words_used,
                    entry.start_time,
                    corrected_end_time,  # 使用修正后的时间
                    0,
                    corrected_end_time  # 传递override_end_time
                )

                # 设置alignment_ratio
                for split_entry in split_entries:
                    split_entry.alignment_ratio = entry.alignment_ratio

                optimized_entries.extend(split_entries)
            else:
                # 修正后不超限，使用修正后的时间
                if corrected_end_time != original_end_time:
                    self.log(f"   ✨ Mode B: 时间修正避免了分割: \"{entry.text[:30]}...\" (原时长: {entry.duration:.2f}s -> 修正后: {corrected_duration:.2f}s)")

                # 创建使用修正后时间的新条目
                optimized_entry = SubtitleEntry(
                    entry.index,
                    entry.start_time,
                    corrected_end_time,
                    entry.text,
                    entry.words_used,
                    entry.alignment_ratio
                )
                optimized_entries.append(optimized_entry)

        # 替换原entries
        entries.clear()
        entries.extend(optimized_entries)

        self.log(f"--- Mode B时间优化完成，处理了{len(optimized_entries)}个条目 ---")

    def _apply_mode_b_merge_optimization(self, entries: List[SubtitleEntry]) -> None:
        """
        Mode B: 基于优化后时间戳的合并优化

        在时间优化完成后，基于优化后的时间戳进行智能合并决策
        """
        self.log("--- 开始Mode B合并优化：基于优化后时间戳 ---")

        # Mode B使用适中的合并策略
        merge_gap_threshold = 0.8  # 与原有逻辑保持一致
        self.log(f"Mode B: 使用适中的合并策略 (间隙阈值: {merge_gap_threshold}s)")

        merged_entries: List[SubtitleEntry] = []
        idx_merge = 0
        total_entries = len(entries)

        while idx_merge < total_entries:
            if not self._is_worker_running():
                self.log("任务被用户中断(Mode B合并阶段)。"); return

            current_entry = entries[idx_merge]
            merged_this_iteration = False

            # 尝试与下一条合并（基于优化后的时间戳）
            if idx_merge + 1 < len(entries):
                next_entry = entries[idx_merge + 1]

                # 检查是否满足合并的基本硬件性条件
                can_merge, reason = self._can_merge_entries(current_entry, next_entry)

                if can_merge:
                    # 计算合并收益（基于优化后的时间戳）
                    benefit = self._calculate_merge_benefit(current_entry, next_entry)

                    # 只有收益超过阈值才合并 (Mode B 默认阈值 5.0)
                    if benefit > 5.0:
                        self.log(f"   Mode B合并 (收益 {benefit:.1f}): \"{current_entry.text[:15]}...\" + \"{next_entry.text[:15]}...\"")
                        merged_entry = self._merge_two_entries(current_entry, next_entry)
                        merged_entries.append(merged_entry)
                        idx_merge += 2
                        merged_this_iteration = True
                    else:
                        pass

            if not merged_this_iteration:
                merged_entries.append(current_entry)
                idx_merge += 1

            # 【修复】移除独立方法中的进度更新，转由主方法process_to_srt处理
            # 这样可以确保使用正确的动态权重分配
            # current_phase2_progress_component = int(((idx_merge) / total_entries if total_entries > 0 else 1) * self.WEIGHT_MERGE)
            # self._emit_srt_progress(current_phase2_progress_component, 100)

        self.log(f"--- Mode B合并优化完成，处理了{len(merged_entries)}个条目 ---")

        # 替换原entries
        entries.clear()
        entries.extend(merged_entries)

    def _apply_mode_a_time_optimization(self, entries: List[SubtitleEntry]) -> None:
        """
        Mode A: 基础时间优化策略

        适用于Whisper、Deepgram、AssemblyAI等无特调策略的JSON格式。
        只进行必要的处理，跳过复杂的时间优化算法。

        Args:
            entries: 字幕条目列表，会被直接修改
        """
        self.log("--- 开始Mode A时间优化：最小必要处理 ---")

        # Mode A只进行最基础的安全检查，不进行任何复杂时间优化
        # 1. 确保时间戳合理性（结束时间不早于开始时间）
        # 2. 应用绝对最小时长要求

        min_duration_absolute = app_config.DEFAULT_MIN_DURATION_ABSOLUTE

        for i, entry in enumerate(entries):
            # 确保结束时间至少比开始时间晚1毫秒
            if entry.end_time <= entry.start_time:
                self.log(f"基础修正: 条目{i+1}结束时间不早于开始时间")
                entry.end_time = entry.start_time + 0.001

            # 应用绝对最小时长要求（但不进行其他时长优化）
            current_duration = entry.duration
            if current_duration < min_duration_absolute:
                self.log(f"基础修正: 条目{i+1}时长{current_duration:.2f}s < {min_duration_absolute}s，调整")
                entry.end_time = entry.start_time + min_duration_absolute

        self.log(f"--- Mode A时间优化完成，对{len(entries)}个条目进行基础安全检查 ---")

    def _apply_mode_c_optimization_to_entries(self, entries: List[SubtitleEntry], parsed_transcription: Optional[ParsedTranscription] = None) -> List[str]:
        """
        Mode C: 在最终格式化前对entries应用Soniox专用优化
        这在Phase 3期间调用，会影响后续的时间优化逻辑

        Args:
            entries: 字幕条目列表
            parsed_transcription: 转录数据（可选，包含元数据）
        """
        self.log("--- Mode C预优化: 应用Soniox置信度和时间调整 ---")
        hints = []

        # 首先收集低置信度词汇用于校对提示，排除标点符号
        for i, entry in enumerate(entries):
            low_conf_words = self._filter_low_confidence_words(entry.words_used)
            if low_conf_words:
                # 获取上下文：前后各一个条目
                prev_text = entries[i-1].text if i > 0 else ""
                next_text = entries[i+1].text if i+1 < len(entries) else ""

                # 格式化校对提示
                low_conf_words_str = ", ".join([f"{w.text}({w.confidence:.2f})" for w in low_conf_words])
                hint = f"低置信度词汇: {low_conf_words_str}\n"
                hint += f"上下文: {prev_text} [{entry.text}] {next_text}\n"
                hint += f"时间: {self.format_timecode(entry.start_time)} --> {self.format_timecode(entry.end_time)}\n"
                hint += "-" * 50
                hints.append(hint)

        # 然后应用时间优化逻辑
        i = 0
        while i < len(entries):
            curr = entries[i]
            next_entry = entries[i + 1] if i + 1 < len(entries) else None

            if next_entry:
                gap = next_entry.start_time - curr.end_time

                # 连读合并预处理 - 检查合并后是否超限
                if gap < self.SONIOX_THRESHOLDS["RAPID_GAP"]:
                    # 预计算合并后的时长，防止超限
                    merged_duration = next_entry.end_time - curr.start_time
                    if merged_duration > self.max_duration:
                        self.log(f"Mode C连读合并跳过: 间隙{gap:.2f}s但合并后时长{merged_duration:.2f}s > {self.max_duration}s")
                    else:
                        merged_entry = self._merge_two_entries(curr, next_entry)
                        entries[i] = merged_entry
                        entries.pop(i + 1)
                        self.log(f"Mode C连读合并: 间隙{gap:.2f}s < {self.SONIOX_THRESHOLDS['RAPID_GAP']}s")
                        continue

                # 异常大间距修正 (仅针对低置信度句尾)
                if curr.words_used:
                    last_word = curr.words_used[-1]
                    if (last_word.confidence < self.SONIOX_THRESHOLDS["CONF_LIMIT"] and
                        gap > self.SONIOX_THRESHOLDS["LARGE_GAP"]):
                        self.log(f"Mode C异常修正: 低置信度({last_word.confidence:.2f}) + 大间距({gap:.2f}s)")
                        curr.end_time += (gap / 2)  # 中点切断
                        gap = next_entry.start_time - curr.end_time

                # 舒适度优化预处理
                if gap > self.SONIOX_THRESHOLDS["EXT_GAP_MIN"]:
                    curr.end_time += self.SONIOX_THRESHOLDS["TAIL_LEN"]
                    next_entry.start_time -= self.SONIOX_THRESHOLDS["START_PAD"]
                    self.log(f"Mode C舒适度优化: 间隙{gap:.2f}s加尾巴和前摇")

                # 物理防重叠兜底
                if curr.end_time > next_entry.start_time:
                    self.log(f"Mode C防重叠修正: 强制分离重叠条目")
                    curr.end_time = next_entry.start_time - 0.01

            i += 1

        # 特殊处理：为最后一个字幕基于音频实际结束时间进行优化
        if len(entries) > 0 and parsed_transcription:
            last_entry = entries[-1]
            soniox_metadata = parsed_transcription.soniox_metadata

            if soniox_metadata and "audio_duration" in soniox_metadata:
                # 获取音频实际结束时间（毫秒转秒）
                audio_end_time = soniox_metadata["audio_duration"] / 1000.0

                # 如果最后一个字幕的结束时间离音频结束还有空间，则延长
                gap_to_end = audio_end_time - last_entry.end_time

                if gap_to_end > self.SONIOX_THRESHOLDS["TAIL_LEN"]:
                    # 有足够空间，添加尾巴
                    last_entry.end_time += self.SONIOX_THRESHOLDS["TAIL_LEN"]
                    self.log(f"Mode C最后一个字幕优化: 音频结束{audio_end_time:.2f}s，字幕延长{self.SONIOX_THRESHOLDS['TAIL_LEN']}s")
                else:
                    # 空间不足，延长到接近音频结束
                    extension = gap_to_end * 0.8  # 延长到距离音频结束还有20%空间
                    if extension > 0.1:  # 至少延长0.1秒才有意义
                        last_entry.end_time += extension
                        self.log(f"Mode C最后一个字幕优化: 音频结束{audio_end_time:.2f}s，字幕延长{extension:.2f}s")
            elif soniox_metadata:
                self.log(f"Mode C最后一个字幕优化: 检测到元数据但缺少audio_duration，跳过优化")
            else:
                # 没有元数据，强制延长0.3秒作为兜底
                tail_extension = 0.3
                last_entry.end_time += tail_extension
                self.log(f"Mode C最后一个字幕优化: 无元数据，强制延长{tail_extension}s")

        self.log(f"--- Mode C预优化完成，收集到{len(hints)}条校对提示 ---")
        return hints

    def _split_comfort_optimized_entry(self, entry: SubtitleEntry) -> List[SubtitleEntry]:
        """
        对已经添加了舒适度时间的超限片段进行特殊分割
        不重复添加舒适度时间，只根据标点符号进行分割
        """
        self.log(f"   特殊分割：处理舒适度优化后的超限片段 (时长: {entry.duration:.2f}s, 词汇数: {len(entry.words_used)})")

        # 如果词汇太少无法分割，返回原片段
        if len(entry.words_used) <= 1:
            self.log(f"   特殊分割：词汇数太少({len(entry.words_used)})，无法分割")
            return [entry]

        # 查找分割点（标点符号）
        split_points = []
        for i, word in enumerate(entry.words_used):
            if self.check_word_has_punctuation(word.text, app_config.ALL_SPLIT_PUNCTUATION):
                split_points.append(i)

        if not split_points:
            self.log(f"   特殊分割：未找到标点符号分割点")
            return [entry]

        # 选择最佳分割点（靠近中间位置的标点符号）
        middle_pos = len(entry.words_used) // 2
        best_point = min(split_points, key=lambda x: abs(x - middle_pos))

        self.log(f"   特殊分割：选择分割点{best_point}，词汇: '{entry.words_used[best_point].text}'")

        # 分割词汇列表
        first_words = entry.words_used[:best_point + 1]
        second_words = entry.words_used[best_point + 1:]

        if not first_words or not second_words:
            self.log(f"   特殊分割：分割后某部分为空，放弃分割")
            return [entry]

        # 计算时间分配
        total_duration = entry.end_time - entry.start_time

        # 使用词汇数比例分配时间，因为舒适度优化后原词汇时间戳可能已不准确
        first_ratio = len(first_words) / len(entry.words_used)
        first_duration = total_duration * first_ratio
        second_duration = total_duration - first_duration

        # 计算分割点的基础时间
        split_base_time = entry.start_time + first_duration

        # 基于原始词汇时间戳进行舒适度优化
        if first_words and second_words:
            # 获取第一片段最后一个词和第二片段第一个词的原始时间戳
            last_word_first = first_words[-1]  # "で、"
            first_word_second = second_words[0]  # "あ"

            # 计算原始间隙（秒）
            original_gap = first_word_second.start_time - last_word_first.end_time
            self.log(f"   特殊分割间隙分析：'{last_word_first.text}'结束({last_word_first.end_time:.3f}s) 到 '{first_word_second.text}'开始({first_word_second.start_time:.3f}s)，间隙={original_gap:.3f}s")

            # 判断是否需要进行舒适度优化
            if original_gap > self.SONIOX_THRESHOLDS["EXT_GAP_MIN"]:
                # 间隙足够大，可以添加尾巴和前摇
                # 第一片段添加尾巴（但不能超过第二片段开始时间的一半）
                max_tail_space = original_gap / 2
                first_end_adjustment = min(self.SONIOX_THRESHOLDS["TAIL_LEN"], max_tail_space)

                # 第二片段添加前摇
                second_start_adjustment = min(self.SONIOX_THRESHOLDS["START_PAD"],
                                           original_gap - first_end_adjustment)

                self.log(f"   特殊分割舒适度优化：间隙{original_gap:.3f}s > {self.SONIOX_THRESHOLDS['EXT_GAP_MIN']}s，添加尾巴{first_end_adjustment:.3f}s，前摇{second_start_adjustment:.3f}s")

                # 使用原始词汇时间戳创建分割后的条目，应用舒适度优化
                first_entry = SubtitleEntry(
                    index=entry.index,
                    start_time=entry.start_time,
                    end_time=last_word_first.end_time + first_end_adjustment,  # 使用原始结束时间+尾巴
                    text="".join([w.text for w in first_words]),
                    words_used=first_words
                )

                second_entry = SubtitleEntry(
                    index=entry.index + 1,
                    start_time=first_word_second.start_time - second_start_adjustment,  # 使用原始开始时间-前摇
                    end_time=entry.end_time,
                    text="".join([w.text for w in second_words]),
                    words_used=second_words
                )
            else:
                self.log(f"   特殊分割跳过优化：间隙{original_gap:.3f}s <= {self.SONIOX_THRESHOLDS['EXT_GAP_MIN']}s，保持原始时间")

                # 不进行优化，直接使用原始词汇时间戳
                first_entry = SubtitleEntry(
                    index=entry.index,
                    start_time=entry.start_time,
                    end_time=last_word_first.end_time,  # 使用原始结束时间
                    text="".join([w.text for w in first_words]),
                    words_used=first_words
                )

                second_entry = SubtitleEntry(
                    index=entry.index + 1,
                    start_time=first_word_second.start_time,  # 使用原始开始时间
                    end_time=entry.end_time,
                    text="".join([w.text for w in second_words]),
                    words_used=second_words
                )
        else:
            # 没有词汇的边界情况，使用简单的比例分割
            first_entry = SubtitleEntry(
                index=entry.index,
                start_time=entry.start_time,
                end_time=entry.start_time + first_duration,
                text="".join([w.text for w in first_words]),
                words_used=first_words
            )

            second_entry = SubtitleEntry(
                index=entry.index + 1,
                start_time=entry.start_time + first_duration,
                end_time=entry.end_time,
                text="".join([w.text for w in second_words]),
                words_used=second_words
            )

        self.log(f"   特殊分割完成：片段1({first_entry.duration:.2f}s, {len(first_words)}词), 片段2({second_entry.duration:.2f}s, {len(second_words)}词)")

        # === [新增] 对舒适度优化分割后的条目进行间距验证 ===
        split_entries = [first_entry, second_entry]
        split_entries = self._validate_and_adjust_split_spacing(split_entries)

        return split_entries

    def _apply_mode_a_optimization_to_entries(self, entries: List[SubtitleEntry]) -> None:
        """
        Mode A: 在最终格式化前对entries应用基础优化
        这在Phase 3期间调用，确保只进行最小必要处理
        """
        self.log("--- Mode A预优化: 应用基础安全检查 ---")

        # 只进行最基础的安全检查
        for entry in entries:
            if entry.end_time <= entry.start_time:
                entry.end_time = entry.start_time + 0.001

    # --- AI 错词校对方法 (仅用于Soniox模式) ---
    def _mark_low_confidence_words(self, words: List[TimestampedWord]) -> List[TimestampedWord]:
        """
        标记低置信度词汇，用于后续纠错

        Args:
            words: Soniox返回的带置信度的词汇列表

        Returns:
            标记后的词汇列表，低置信度词汇会被特殊标记
        """
        marked_words = []
        for word in words:
            # 创建词汇副本以避免修改原始数据
            marked_word = TimestampedWord(
                text=word.text,
                start_time=word.start_time,
                end_time=word.end_time,
                speaker_id=word.speaker_id,
                confidence=word.confidence
            )

            # 如果置信度低于阈值，添加标记
            if word.confidence < self.SONIOX_THRESHOLDS["CONF_LIMIT"]:
                marked_word.text = f"【{word.text}】"

            marked_words.append(marked_word)

        return marked_words

    def _apply_soniox_ultimate_optimization(self, srt_lines: List[str]) -> List[str]:
        """
        Soniox专用终极优化：动态前移字幕开始时间
        根据上一个字幕结束时间到当前字幕开始时间的距离除以25来计算前移量

        Args:
            srt_lines: 已生成的SRT行列表

        Returns:
            优化后的SRT行列表
        """
        if not srt_lines:
            return srt_lines

        
        # 第一步：提取所有字幕信息
        subtitles = []

        for entry_str in srt_lines:
            entry_lines = entry_str.strip().split('\n')
            if len(entry_lines) >= 3:
                # 第一行应该是字幕编号
                if entry_lines[0].strip().isdigit():
                    current_num = int(entry_lines[0].strip())

                    # 第二行应该是时间戳
                    if '-->' in entry_lines[1]:
                        time_line = entry_lines[1].strip()
                        start_str, end_str = time_line.split(' --> ')

                        start_time = self._parse_srt_time(start_str)
                        end_time = self._parse_srt_time(end_str)

                        # 剩下的行是字幕内容
                        content_lines = []
                        for content_line in entry_lines[2:]:
                            if content_line.strip():  # 只添加非空行
                                content_lines.append(content_line.strip())

                        subtitles.append({
                            'number': current_num,
                            'start': start_time,
                            'end': end_time,
                            'content': content_lines,
                            'entry_str': entry_str  # 保存原始条目字符串
                        })

        if not subtitles:
            return srt_lines

        # 第二步：进行优化并重新构建SRT
        optimized_entries = []

        # 先计算所有调整量
        adjustments = {}
        for subtitle in subtitles:
            current_num = subtitle['number']
            current_start = subtitle['start']
            current_end = subtitle['end']

            adjustment = 0.0
            if current_num == 1:
                # 第一个字幕：从0秒到开始时间的距离除以25，最大不超过0.6秒
                adjustment = min(current_start / 25.0, 0.6)
                if adjustment > 0.001:  # 只记录有意义的调整
                    self.log(f"   ⚡ 终极优化：字幕{current_num} 前移 {adjustment:.3f}s")
            else:
                # 找到上一个字幕
                prev_subtitle = None
                for s in subtitles:
                    if s['number'] == current_num - 1:
                        prev_subtitle = s
                        break

                if prev_subtitle:
                    gap = current_start - prev_subtitle['end']
                    adjustment = min(gap / 20.0, 0.5)  # 最大不超过0.5秒
                    if adjustment > 0.001:  # 只记录有意义的调整
                        self.log(f"   ⚡ 终极优化：字幕{current_num} 前移 {adjustment:.3f}s")

            adjustments[current_num] = adjustment

        # 重新构建SRT条目
        for i, subtitle in enumerate(subtitles):
            current_num = subtitle['number']
            current_start = subtitle['start']
            current_end = subtitle['end']
            adjustment = adjustments[current_num]

            # 应用优化
            if adjustment > 0.001:
                new_start = max(0.001, current_start - adjustment)

                # 【修复核心】：直接使用列表中的上一个元素，而不是通过序号查找
                prev_end = 0.0
                if i > 0:
                    # 获取列表中的前一个条目
                    prev_subtitle = subtitles[i - 1]
                    # 计算前一个条目经过调整后的结束时间
                    prev_adjustment = adjustments.get(prev_subtitle['number'], 0.0)
                    if prev_adjustment > 0.001:
                        # 如果前一个条目也被调整了，需要计算其新的开始时间
                        prev_new_start = max(0.001, prev_subtitle['start'] - prev_adjustment)
                        # 确保前一个条目的时间逻辑正确
                        if prev_new_start <= prev_end:
                            prev_new_start = prev_end + 0.001
                        # 前一个条目的结束时间保持不变，所以使用原始结束时间
                        prev_end = prev_subtitle['end']
                    else:
                        # 前一个条目没有被调整，直接使用原始结束时间
                        prev_end = prev_subtitle['end']

                # 安全检查：防止与上一个字幕重叠
                if new_start <= prev_end:
                    new_start = prev_end + 0.001

                # 重新格式化时间戳
                new_start_str = self._format_timecode(new_start)
                new_end_str = self._format_timecode(current_end)
                time_line = f"{new_start_str} --> {new_end_str}"
            else:
                # 不调整，使用原始时间戳
                original_lines = subtitle['entry_str'].strip().split('\n')
                time_line = original_lines[1]  # 原始时间戳行

            # 构建新条目
            entry_lines = [
                str(current_num),
                time_line
            ]
            entry_lines.extend(subtitle['content'])
            entry_lines.append("")  # 空行

            optimized_entries.append('\n'.join(entry_lines))

        # 返回与原始格式相同的字符串列表（每个条目包含完整内容+空行）
        result_list = []
        for entry in optimized_entries:
            result_list.append(entry + '\n')  # 确保每个条目以换行结束

        return result_list

    def _parse_srt_time(self, time_str: str) -> float:
        """将SRT时间格式转换为秒数"""
        # 格式: 00:03:47,330
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_parts = parts[2].split(',')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1])

            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            return total_seconds
        except:
            return 0.0

    def _format_timecode(self, seconds: float) -> str:
        """将秒数转换为SRT时间格式"""
        try:
            hours = int(seconds // 3600)
            remaining = seconds % 3600
            minutes = int(remaining // 60)
            secs = int(remaining % 60)
            milliseconds = int((remaining % 1) * 1000)

            return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
        except:
            return "00:00:00,000"

    def _apply_word_level_spacing_validation(self, entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        Soniox模式专用词级间距验证：在终极优化完成后检查和修正字幕间距

        根据用户要求：对于soniox模式，直接在Soniox终极优化完成之后，
        查看是否有两个字幕的间距小于用户设定的最小间距的情况，
        使用0.35s阈值和词级时间戳进行精细化调整

        调整逻辑：
        1. 判断前一个字幕的倒数第二个词的结尾时间和最后一个词的开始时间的距离是否超过0.35
        2. 若超过了，则将第一个字幕的结束时间设置为第一个字幕的倒数第二个词的结尾时间加0.35
        3. 然后将第二个字幕的开始时间调整为第一个字幕新的结尾时间再加上用户设定的最小间距
        4. 如果没有超过，就进行反向判断

        Args:
            entries: 已完成终极优化的SubtitleEntry列表

        Returns:
            经过词级间距验证和修正的SubtitleEntry列表
        """
        if len(entries) < 2:
            self.log("   🎯 词级间距验证：样本数量不足，跳过检查")
            return entries

        self.log(f"   🎯 词级间距验证：开始检查最小间距 (用户设定: {self.default_gap_ms}ms)")
        self.log(f"   🔍 调试信息：检查{len(entries)}个字幕条目的词级间距")

        min_spacing_seconds = self.default_gap_ms / 1000.0
        max_word_gap = 0.35  # 0.35s阈值
        adjustments_made = 0

        for i in range(len(entries) - 1):
            current_entry = entries[i]
            next_entry = entries[i + 1]

            # 检查是否有足够的词汇进行分析
            if len(current_entry.words_used) < 2 or len(next_entry.words_used) < 2:
                self.log(f"   🔍 字幕{current_entry.index}->{next_entry.index}: 词汇数量不足，跳过词级分析")
                # 回退到简单间距检查
                simple_gap = next_entry.start_time - current_entry.end_time
                if simple_gap < min_spacing_seconds:
                    self.log(f"   🔍 检测到简单间距过小：字幕{current_entry.index} -> 字幕{next_entry.index} "
                            f"(当前间距: {simple_gap:.3f}s, 要求最小间距: {min_spacing_seconds:.3f}s)")
                    next_entry.start_time = current_entry.end_time + min_spacing_seconds
                    adjustments_made += 1
                continue

            current_gap = next_entry.start_time - current_entry.end_time

            if current_gap < min_spacing_seconds:
                self.log(f"   🔍 检测到间距过小：字幕{current_entry.index} -> 字幕{next_entry.index} "
                        f"(当前间距: {current_gap:.3f}s, 要求最小间距: {min_spacing_seconds:.3f}s)")

                # 应用用户指定的词级时间戳调整逻辑
                adjustment_made = self._apply_user_word_spacing_logic(current_entry, next_entry, min_spacing_seconds, max_word_gap)
                if adjustment_made:
                    adjustments_made += 1

        if adjustments_made == 0:
            self.log("   🎯 词级间距验证：未发现需要调整的间距问题")
        else:
            self.log(f"   🎯 词级间距验证：完成，共调整了 {adjustments_made} 个字幕的时序")

        return entries

    def _apply_user_word_spacing_logic(self, current_entry: SubtitleEntry, next_entry: SubtitleEntry,
                                    min_spacing_seconds: float, max_word_gap: float) -> bool:
        """
        应用用户的词级时间戳间距调整逻辑

        根据用户的详细要求进行词级分析：

        Args:
            current_entry: 当前字幕条目
            next_entry: 下一个字幕条目
            min_spacing_seconds: 用户设定的最小间距
            max_word_gap: 最大词间间距阈值(0.35s)

        Returns:
            是否进行了调整
        """
        current_words = current_entry.words_used
        next_words = next_entry.words_used

        # 检查前一个字幕的倒数第二个词的结尾时间和最后一个词的开始时间的距离
        if len(current_words) >= 2:
            # 获取当前字幕倒数第二个词的结尾时间和最后一个词的开始时间
            second_last_word = current_words[-2]
            last_word_current = current_words[-1]

            # 检查当前字幕内部的词间距离
            current_word_gap = last_word_current.start_time - second_last_word.end_time

            self.log(f"   🔍 词级分析：当前字幕{current_entry.index}词间距离 = {current_word_gap:.3f}s")

            if current_word_gap > max_word_gap:
                # 超过0.35s，应用第一种调整策略
                # 将第一个字幕的结束时间设置为倒数第二个词的结尾时间加0.35
                new_current_end_time = second_last_word.end_time + max_word_gap
                original_current_end = current_entry.end_time
                current_entry.end_time = new_current_end_time

                # 将第二个字幕的开始时间调整为第一个字幕新的结尾时间再加上用户设定的最小间距
                new_next_start_time = new_current_end_time + min_spacing_seconds
                original_next_start = next_entry.start_time
                next_entry.start_time = new_next_start_time

                self.log(f"   ✅ 词级调整策略1：字幕{current_entry.index}结束时间 {original_current_end:.3f}s -> {new_current_end_time:.3f}s")
                self.log(f"   ✅ 词级调整策略1：字幕{next_entry.index}开始时间 {original_next_start:.3f}s -> {new_next_start_time:.3f}s")
                self.log(f"   📝 词级调整原因：当前字幕内词间距离({current_word_gap:.3f}s) > {max_word_gap:.3f}s")

                return True

        # 如果第一种策略不适用，检查下一个字幕的第二个词的开始时间和第一个词的结束时间的距离
        if len(next_words) >= 2:
            # 获取下一个字幕的第一个词和第二个词
            first_word_next = next_words[0]
            second_word_next = next_words[1]

            # 检查下一个字幕内部的词间距离
            next_word_gap = second_word_next.start_time - first_word_next.end_time

            self.log(f"   🔍 词级分析：下一个字幕{next_entry.index}词间距离 = {next_word_gap:.3f}s")

            if next_word_gap > max_word_gap:
                # 超过0.35s，应用第二种调整策略
                # 将第二个字幕的开始时间设置为第二个字幕的第二个词的开始时间减去0.35
                new_next_start_time = second_word_next.start_time - max_word_gap
                original_next_start = next_entry.start_time

                # 确保新的开始时间不早于当前字幕结束时间
                if new_next_start_time < current_entry.end_time:
                    new_next_start_time = current_entry.end_time + min_spacing_seconds
                    self.log(f"   ⚠️ 词级调整限制：新的开始时间早于当前字幕结束时间，调整为 {new_next_start_time:.3f}s")

                # 将第一个字幕的结束时间调整为第二个字幕新的开始时间再减用户设定的最小间距
                new_current_end_time = new_next_start_time - min_spacing_seconds
                original_current_end = current_entry.end_time

                # 确保逻辑正确
                if new_current_end_time < original_current_end:
                    new_current_end_time = original_current_end  # 不缩短当前字幕

                current_entry.end_time = new_current_end_time
                next_entry.start_time = new_next_start_time

                self.log(f"   ✅ 词级调整策略2：字幕{next_entry.index}开始时间 {original_next_start:.3f}s -> {new_next_start_time:.3f}s")
                self.log(f"   ✅ 词级调整策略2：字幕{current_entry.index}结束时间 {original_current_end:.3f}s -> {new_current_end_time:.3f}s")
                self.log(f"   📝 词级调整原因：下一个字幕内词间距离({next_word_gap:.3f}s) > {max_word_gap:.3f}s")

                return True

        # 如果都不适用，进行简单间距调整
        simple_gap = next_entry.start_time - current_entry.end_time
        if simple_gap < min_spacing_seconds:
            next_entry.start_time = current_entry.end_time + min_spacing_seconds
            self.log(f"   ✅ 简单间距调整：字幕{next_entry.index}开始时间调整到保证{min_spacing_seconds:.3f}s间距")
            return True

        return False

    def _parse_srt_entries_from_strings(self, srt_strings: List[str]) -> List[Dict]:
        """
        从SRT字符串列表解析字幕条目

        Args:
            srt_strings: SRT格式的字符串列表

        Returns:
            解析后的字幕条目字典列表
        """
        parsed_subtitles = []

        for i, srt_entry in enumerate(srt_strings):
            # 分割完整条目的行
            entry_lines = srt_entry.strip().split('\n')
            if len(entry_lines) < 2:  # 至少需要序号和时间戳行
                continue

            # 解析序号
            try:
                subtitle_number = int(entry_lines[0].strip())
            except:
                continue

            # 解析时间戳
            time_line = entry_lines[1]
            if '-->' not in time_line:
                continue

            try:
                time_parts = time_line.split(' --> ')
                start_time = self._parse_srt_time(time_parts[0])
                end_time = self._parse_srt_time(time_parts[1])

                # 获取内容文本
                content_lines = entry_lines[2:] if len(entry_lines) > 2 else []

                parsed_subtitles.append({
                    'number': subtitle_number,
                    'start': start_time,
                    'end': end_time,
                    'content': content_lines,
                    'entry_str': srt_entry  # 保存原始字符串用于重构
                })

            except Exception as e:
                self.log(f"   ⚠️ 字幕{subtitle_number}时间戳解析失败: {str(e)}")
                continue

        return parsed_subtitles

    def _build_srt_strings_from_parsed_entries(self, parsed_entries: List[Dict]) -> List[str]:
        """
        从解析的字幕条目重新构建SRT字符串列表

        Args:
            parsed_entries: 解析的字幕条目字典列表

        Returns:
            SRT格式的字符串列表
        """
        result_srt_lines = []
        for subtitle in parsed_entries:
            if all(k in subtitle for k in ['number', 'start', 'end', 'content']):
                # 重新格式化时间戳
                start_time_str = self._format_timecode(subtitle['start'])
                end_time_str = self._format_timecode(subtitle['end'])
                time_line = f"{start_time_str} --> {end_time_str}"

                # 构建条目
                entry_lines = [
                    str(subtitle['number']),
                    time_line
                ]
                entry_lines.extend(subtitle['content'])
                entry_lines.append("")  # 空行

                result_srt_lines.append('\n'.join(entry_lines) + '\n')

        return result_srt_lines

    def _reconstruct_subtitle_entry_from_srt_string(self, srt_string: str) -> Optional[SubtitleEntry]:
        """
        从SRT格式字符串重构SubtitleEntry对象并关联词级数据

        Args:
            srt_string: SRT格式的字符串（包含序号、时间戳、文本）

        Returns:
            重构的SubtitleEntry对象，包含词级数据；失败返回None
        """
        try:
            lines = srt_string.strip().split('\n')
            if len(lines) < 3:  # 至少需要序号、时间戳、文本
                return None

            # 解析序号
            subtitle_number = int(lines[0].strip())

            # 解析时间戳
            time_line = lines[1]
            if '-->' not in time_line:
                return None

            time_parts = time_line.split(' --> ')
            start_time = self._parse_srt_time(time_parts[0])
            end_time = self._parse_srt_time(time_parts[1])

            # 提取文本内容
            text_content = ''.join(lines[2:]) if len(lines) > 2 else ""

            # 查找对应的词级数据
            # 需要在处理过程中保存的词级数据映射表
            word_data_for_entry = self._find_word_data_for_time_range(start_time, end_time)

            return SubtitleEntry(
                index=subtitle_number,
                start_time=start_time,
                end_time=end_time,
                text=text_content,
                words_used=word_data_for_entry
            )

        except Exception as e:
            self.log(f"   ⚠️ 重构字幕条目失败: {str(e)}")
            return None

    def _find_word_data_for_time_range(self, start_time: float, end_time: float) -> List[TimestampedWord]:
        """
        根据时间范围查找对应的词级数据

        注意：这是一个简化实现，实际中需要在整个处理过程中保存词级映射

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            该时间范围内的词汇列表
        """
        # 这是一个简化实现，实际应该从全局词级数据中查找
        # 暂时返回空列表，让间距验证回退到简单模式
        return []

    def _prepare_correction_prompt(self, segments: List[str], words: List[TimestampedWord]) -> List[str]:
        """
        [废弃方法] 准备AI纠错的提示词，使用滑动窗口提供上下文

        注意：此方法已被 _build_smart_correction_prompt 替代，保留仅为向后兼容
        新的智能纠错使用更完善的上下文提取和批次处理逻辑

        Args:
            segments: 需要纠错的文本片段列表
            words: Soniox返回的词汇列表（包含置信度信息）

        Returns:
            纠错提示词列表，每个提示词对应一个batch
        """
        # 标记低置信度词汇
        marked_words = self._mark_low_confidence_words(words)

        # 构建上下文文本
        context_text = "".join([w.text for w in marked_words])

        # 准备纠错提示词
        prompts = []
        batch_size = 5  # 每个batch处理5个片段，控制token消耗

        for i in range(0, len(segments), batch_size):
            batch_segments = segments[i:i + batch_size]

            # 构建上下文窗口（当前批次前后各一个片段）
            context_start = max(0, i - 1)
            context_end = min(len(segments), i + batch_size + 1)
            context_segments = segments[context_start:context_end]

            # 找到对应的时间窗口词汇
            segment_start_time = None
            segment_end_time = None

            # 这里简化处理，实际应该根据时间戳找到对应词汇
            # 为了实现简单，我们使用所有词汇作为上下文
            relevant_words = marked_words

            # 构建带标记的文本
            marked_text = "".join([w.text for w in relevant_words])

            # 构建完整的纠错提示
            prompt = f"""{app_config.DEEPSEEK_SYSTEM_PROMPT_CORRECTION}

以下是需要纠错的文本（已用【】标记低置信度词汇）：

{marked_text}

请重点关注以下片段的纠错：
{chr(10).join([f"{i+j}. {seg}" for j, seg in enumerate(batch_segments)])}
"""

            prompts.append(prompt)

        return prompts

    def _identify_segments_requiring_correction(self, segments: List[str], words: List[TimestampedWord], srt_entries: List[Dict] = None) -> List[int]:
        """
        基于时间戳精确识别需要纠错的片段

        Args:
            segments: 文本片段列表（LLM分割后的片段）
            words: Soniox返回的词汇列表（包含置信度信息）
            srt_entries: SRT条目列表（包含时间信息）

        Returns:
            需要纠错的片段索引列表
        """
        # 1. 收集低置信度词（带时间戳的对象）
        low_conf_word_objects = []
        all_punctuation = app_config.ALL_SPLIT_PUNCTUATION  # 使用合并的标点符号集合

        for word in words:
            # 跳过包含标点符号的词汇（包括标点符号本身和以标点结尾的词汇）
            if self.check_word_has_punctuation(word.text, all_punctuation):
                continue

            # 跳过单个字符的词汇（除非是汉字、平假名或片假名）
            text = word.text.strip()
            if len(text) == 1:
                # 检查是否为 CJK 汉字 (常用 + 扩展A)
                is_cjk = ('\u4e00' <= text <= '\u9fff') or ('\u3400' <= text <= '\u4dbf')

                # 检查是否为 平假名 (\u3040-\u309f) 或 片假名 (\u30a0-\u30ff)
                is_kana = ('\u3040' <= text <= '\u30ff')

                # 如果既不是汉字也不是假名（比如单个英文字母或数字），则跳过
                if not (is_cjk or is_kana):
                    continue

            # 阈值检查
            if word.confidence < app_config.DEFAULT_SONIOX_LOW_CONFIDENCE_THRESHOLD:
                low_conf_word_objects.append(word)

        if not low_conf_word_objects:
            return []

        segments_to_correct = []

        # 2. 如果有时间信息，使用时间轴匹配（精准）
        if srt_entries and segments:
            for i, entry in enumerate(srt_entries):
                # 边界检查：确保索引不超出范围
                if i >= len(segments):
                    break

                # 解析 SRT 时间字符串为秒数
                time_str = entry.get('time', '')
                if not time_str or '-->' not in time_str:
                    continue

                start_str, end_str = time_str.split(' --> ')
                try:
                    seg_start = self._parse_srt_time(start_str.strip())
                    seg_end = self._parse_srt_time(end_str.strip())
                except Exception:
                    # 时间解析失败，跳过这个条目
                    continue

                # 边界检查：确保时间范围有效
                if seg_start >= seg_end:
                    continue

                # 检查是否有任何低置信度词落在这个时间段内
                has_error = False
                for bad_word in low_conf_word_objects:
                    # 边界检查：确保word对象有时间属性
                    if not hasattr(bad_word, 'start_time') or not hasattr(bad_word, 'end_time'):
                        continue

                    # 边界检查：确保时间范围有效
                    if bad_word.start_time >= bad_word.end_time:
                        continue

                    # 计算词的中点时间
                    word_mid = (bad_word.start_time + bad_word.end_time) / 2

                    # 判定条件：词的中点在片段范围内（放宽 0.1秒 容差）
                    if (seg_start - 0.1) <= word_mid <= (seg_end + 0.1):
                        has_error = True
                        break  # 找到一个就足够标记该段

                if has_error:
                    segments_to_correct.append(i)

        # 3. 如果没有时间信息（兜底），回退到文本匹配（但不推荐）
        else:
            self.log("⚠️ 警告：缺少时间信息，回退到模糊文本匹配，可能导致过度纠错")

            # 将对象转换为文本列表进行回退匹配
            low_confidence_texts = [word.text for word in low_conf_word_objects]

            for i, segment in enumerate(segments):
                # 检查这个片段中是否包含任何低置信度词汇
                for low_conf_text in low_confidence_texts:
                    if low_conf_text in segment:
                        segments_to_correct.append(i)
                        break

        self.log(f"📊 精确识别结果: {len(segments)} 个片段中，{len(segments_to_correct)} 个需要纠错")
        return segments_to_correct

    def _prepare_smart_correction_batches(self, segments: List[str], words: List[TimestampedWord],
                                         target_segments: List[int]) -> List[List[int]]:
        """
        创建智能纠错批次，包含目标片段和上下文

        Args:
            segments: 所有片段
            words: 词汇列表
            target_segments: 需要纠错的片段索引

        Returns:
            纠错批次的片段索引列表，每个批次包含目标片段+上下文
        """
        if not target_segments:
            return []

        BATCH_SIZE = 15  # 每个批次最多15个目标片段
        batches = []

        # 将目标片段按索引排序，确保按顺序处理
        sorted_targets = sorted(target_segments)

        # 分批处理目标片段，每批最多BATCH_SIZE个
        for i in range(0, len(sorted_targets), BATCH_SIZE):
            batch_target_indices = sorted_targets[i:i + BATCH_SIZE]
            # 批次数量已在处理日志中显示

            # 使用set避免重复，分离目标片段和上下文片段的处理
            target_indices_set = set(batch_target_indices)
            context_indices_set = set()

            # 收集上下文索引（排除目标索引以避免重复）
            for target_idx in batch_target_indices:
                # 添加前一个片段作为上下文
                if target_idx > 0:
                    prev_idx = target_idx - 1
                    # 只有当前一个片段不是目标片段时才添加为上下文
                    if prev_idx not in sorted_targets:
                        context_indices_set.add(prev_idx)

                # 添加后一个片段作为上下文
                if target_idx + 1 < len(segments):
                    next_idx = target_idx + 1
                    # 只有当后一个片段不是目标片段时才添加为上下文
                    if next_idx not in sorted_targets:
                        context_indices_set.add(next_idx)

            # 合并目标索引和上下文索引，并排序
            all_indices = target_indices_set | context_indices_set
            batch_indices = sorted(all_indices)

            # 添加上下文后检查批次大小，如果过大则截断上下文
            if len(batch_indices) > BATCH_SIZE + 10:  # 允许一定的上下文空间
                # 优先保留目标片段，去掉一些上下文
                core_indices = [idx for idx in batch_indices if idx in batch_target_indices]
                remaining_slots = BATCH_SIZE - len(core_indices)

                if remaining_slots > 0:
                    # 添加必要的上下文
                    context_indices = [idx for idx in batch_indices if idx not in core_indices]
                    batch_indices = sorted(core_indices + context_indices[:remaining_slots])
                else:
                    batch_indices = core_indices

            batches.append(batch_indices)
            # 最终批次信息在处理时显示，这里不再重复

        return batches

    def _smart_context_extraction(self, full_text: str, batch_target_segments: List[str], max_length: int = 3000) -> str:
        """基于批次的智能上下文提取：动态提取批次相关上下文"""

        if len(full_text) <= max_length:
            # 如果全文不超过限制，直接返回全文
            return full_text

  # 使用config中定义的完整标点符号集合
        sentence_endings = app_config.FINAL_PUNCTUATION | {'…', '‥'}  # 添加单字符省略号
        multi_char_endings = list(app_config.ELLIPSIS_PUNCTUATION)  # 使用config中的完整省略号集合

        # 找到所有句子边界位置
        sentence_boundaries = [0]
        pos = 0
        while pos < len(full_text):
            # 检查单个字符标点
            if full_text[pos] in sentence_endings:
                sentence_boundaries.append(pos + 1)
            # 检查多字符标点
            elif pos >= 2 and full_text[pos-2:pos+1] in multi_char_endings:
                sentence_boundaries.append(pos + 1)
            pos += 1

        # 添加全文结束作为边界
        if len(full_text) not in sentence_boundaries:
            sentence_boundaries.append(len(full_text))

        # 找到批次中第一个和最后一个目标片段在全文中的位置
        batch_positions = []
        for segment in batch_target_segments:
            pos = full_text.find(segment)
            if pos != -1:
                batch_positions.append((pos, pos + len(segment)))

        if not batch_positions:
            # 如果找不到任何目标片段，返回中间3000字符
            center = len(full_text) // 2
            start = max(0, center - max_length // 2)
            end = min(len(full_text), start + max_length)
            return full_text[start:end]

        # 排序位置
        batch_positions.sort()
        target_start = batch_positions[0][0]  # 批次第一个片段的开始位置
        target_end = batch_positions[-1][1]   # 批次最后一个片段的结束位置

        # 计算批次覆盖的文本长度
        batch_distance = target_end - target_start

        if batch_distance >= max_length:
            # 情况B：批次本身距离就超过3000，只能截断到最近的句子边界
            # 向前找最近的句子结束标点
            context_start = target_start
            for boundary in reversed(sentence_boundaries):
                if boundary < target_start:
                    context_start = boundary
                    break

            # 向后找最近的句子结束标点
            context_end = target_end
            for boundary in sentence_boundaries:
                if boundary > target_end:
                    context_end = boundary
                    break

            # 即使这样还是可能超过3000，进一步截断到3000字符
            if context_end - context_start > max_length:
                center = (context_start + context_end) // 2
                context_start = max(0, center - max_length // 2)
                context_end = context_start + max_length

        else:
            # 情况A：批次距离小于3000，尽可能扩展到接近3000字符的最近句子边界
            # 目标：在不超过3000字符的前提下，尽可能包含更多完整的句子

            # 找到批次所在句子的索引范围
            batch_sentence_start = 0
            batch_sentence_end = len(sentence_boundaries) - 1

            for i in range(len(sentence_boundaries) - 1):
                if sentence_boundaries[i] <= target_start < sentence_boundaries[i+1]:
                    batch_sentence_start = i
                    break

            for i in range(len(sentence_boundaries) - 1):
                if sentence_boundaries[i] <= target_end <= sentence_boundaries[i+1]:
                    batch_sentence_end = i + 1
                    break

            # 从批次所在句子开始，向两侧扩展直到接近3000字符
            left_idx = batch_sentence_start
            right_idx = batch_sentence_end

            while left_idx > 0 or right_idx < len(sentence_boundaries) - 1:
                current_length = sentence_boundaries[right_idx] - sentence_boundaries[left_idx]

                if current_length >= max_length:
                    break

                # 优先扩展句子较少的一侧，保持平衡
                can_expand_left = left_idx > 0
                can_expand_right = right_idx < len(sentence_boundaries) - 1

                if can_expand_left and can_expand_right:
                    # 比较两侧可以扩展的长度
                    left_expand_len = sentence_boundaries[left_idx] - sentence_boundaries[left_idx-1]
                    right_expand_len = sentence_boundaries[right_idx+1] - sentence_boundaries[right_idx]

                    # 优先扩展较短的一侧
                    if left_expand_len <= right_expand_len:
                        left_idx -= 1
                    else:
                        right_idx += 1
                elif can_expand_left:
                    left_idx -= 1
                elif can_expand_right:
                    right_idx += 1
                else:
                    break

            # 获取结果边界
            context_start = sentence_boundaries[left_idx]
            context_end = sentence_boundaries[right_idx]

            # 确保不超出全文边界
            context_start = max(0, context_start)
            context_end = min(len(full_text), context_end)

            # 如果还是超过限制，进一步截断到3000字符
            final_length = context_end - context_start
            if final_length > max_length:
                center = (context_start + context_end) // 2
                context_start = max(0, center - max_length // 2)
                context_end = context_start + max_length

        result = full_text[context_start:context_end]

        # 添加截断提示
        if context_start > 0 or context_end < len(full_text):
            result = "..." + result + "...\n\n（注：上下文因长度限制被智能截取）"

        return result

    def _build_smart_correction_prompt(self, batch_segments: List[str], low_confidence_words: List[str] = None,
                                   all_segments: List[str] = None, target_indices: List[int] = None,
                                   target_local_indices: List[int] = None) -> str:
        """
        为智能纠错构建专用提示词（完整上下文+精确定位方案）

        Args:
            batch_segments: 当前批次的片段列表
            low_confidence_words: 低置信度词汇列表
            all_segments: 完整的转录文本片段列表（用于提供上下文）
            target_indices: 当前批次对应的所有片段中的索引
            target_local_indices: 当前批次中需要纠错的目标片段的局部索引列表

        Returns:
            智能纠错提示词
        """
        # 在片段中标记低置信度词汇
        marked_segments = []
        for segment in batch_segments:
            marked_segment = segment
            if low_confidence_words:
                for low_conf_word in low_confidence_words:
                    if low_conf_word in marked_segment:
                        marked_segment = marked_segment.replace(low_conf_word, f"【{low_conf_word}】")
            marked_segments.append(marked_segment)

        # 构建完整上下文
        full_context = ""
        if all_segments:
            full_context = "".join(all_segments)
            # 使用新的批次智能上下文提取
            full_context = self._smart_context_extraction(full_context, batch_segments, 3000)

        # 构建智能提示词
        if full_context:
            # 确保target_local_indices不为None，默认为所有索引
            if target_local_indices is None:
                target_local_indices = [i for i in range(len(marked_segments))]

            # 构建局部片段列表字符串
            formatted_segments = chr(10).join([f"{i}. {seg}" for i, seg in enumerate(marked_segments)])

            # === 关键修改：Prompt 模板 ===
            prompt = f"""请根据以下要求进行ASR错词校对：

{app_config.DEEPSEEK_SYSTEM_PROMPT_CORRECTION}

## 完整转录上下文
(仅供参考，用于理解语境)
{full_context}

## 当前纠错任务
以下片段列表包含【主要目标】和【局部上下文】。
请仔细阅读并执行以下核心指令：

### 核心指令：
1. **针对【目标索引】片段 ({target_local_indices})**：
   - **必须**：重点校对，修正所有标记的【低置信度词汇】及其他潜在错误。

2. **针对【非目标（上下文）片段】**：
   - **默认原则**：**不要修改**，直接忽略或返回原文本。
   - **例外条款**：如果你在上下文中发现了**极其明显的ASR错误**（例如：严重的同音字错误如"気筒"->"亀頭"、乱码、明显不合逻辑的词），**允许且建议**你对其进行修正。
   - **严禁操作**：严禁仅为了润色文笔、改变语气或精简句子而修改上下文。

### 待处理片段列表：
{formatted_segments}

### 输出要求：
请严格按照 JSON 格式返回修正结果：
{{"片段索引": "纠错后文本"}}

**注意**：
- 如果某片段（无论是目标还是上下文）**完全无需修改**，请**不要**包含在返回的 JSON 中，以节省资源。
- 仅返回有实际变动的片段。"""
        else:
            # 确保target_local_indices不为None，默认为所有索引
            if target_local_indices is None:
                target_local_indices = [i for i in range(len(marked_segments))]

            # 构建局部片段列表字符串
            formatted_segments = chr(10).join([f"{i}. {seg}" for i, seg in enumerate(marked_segments)])

            # 回退到原始方案
            prompt = f"""请根据以下要求进行ASR错词校对：

{app_config.DEEPSEEK_SYSTEM_PROMPT_CORRECTION}

以下片段列表包含【主要目标】和【局部上下文】。
请仔细阅读并执行以下核心指令：

### 核心指令：
1. **针对【目标索引】片段 ({target_local_indices})**：
   - **必须**：重点校对，修正所有标记的【低置信度词汇】及其他潜在错误。

2. **针对【非目标（上下文）片段】**：
   - **默认原则**：**不要修改**，直接忽略或返回原文本。
   - **例外条款**：如果你在上下文中发现了**极其明显的ASR错误**（例如：严重的同音字错误如"気筒"->"亀頭"、乱码、明显不合逻辑的词），**允许且建议**你对其进行修正。
   - **严禁操作**：严禁仅为了润色文笔、改变语气或精简句子而修改上下文。

### 待处理片段列表：
{formatted_segments}

### 输出要求：
请严格按照 JSON 格式返回修正结果：
{{"片段索引": "纠错后文本"}}

**注意**：
- 如果某片段（无论是目标还是上下文）**完全无需修改**，请**不要**包含在返回的 JSON 中，以节省资源。
- 仅返回有实际变动的片段。"""

        return prompt

    def _apply_post_srt_ai_correction(self, srt_content: str, words: List[TimestampedWord]) -> tuple[str, List[str]]:
        """
        在SRT生成完成后进行AI校对（后处理模式）

        Args:
            srt_content: 完整的SRT内容
            words: 原始词汇列表（用于收集低置信度词汇）

        Returns:
            tuple: (校对后的SRT内容, 校对提示列表)
        """
        if not srt_content.strip():
            return srt_content, []

        self.log("🤖 开始SRT后处理AI校对")
        correction_hints: List[str] = []

        # 【新增】获取当前进度偏移和范围，用于AI纠错阶段的细分进度
        current_offset = self._current_progress_offset
        total_range = self._current_progress_range

        try:
            # 1. 解析SRT内容为条目列表
            srt_entries = self._parse_srt_content(srt_content)
            if not srt_entries:
                self.log("⚠️ SRT内容解析为空，跳过AI校对")
                return srt_content, []

            self.log(f"   解析到 {len(srt_entries)} 个SRT条目")

            # 2. 收集低置信度词汇
            low_conf_words = self._collect_low_confidence_words(words)
            if not low_conf_words:
                self.log("✅ 未发现低置信度词汇，跳过AI校对")
                return srt_content, []

            # 统计信息在后续日志中显示，这里不再重复

            # 3. 提取需要校对的文本片段
            text_segments = [entry['text'] for entry in srt_entries]

            # 4. 标记低置信度词汇
            marked_segments = self._mark_low_confidence_words_in_segments(text_segments, low_conf_words)

            # 5. 检查是否需要校对
            has_corrections = any('【' in seg for seg in marked_segments)
            if not has_corrections:
                self.log("✅ 没有需要校对的内容，跳过AI校对")
                return srt_content, []

            self.log(f"   检测到需要校对的片段数量: {sum(1 for seg in marked_segments if '【' in seg)}")

            # 6. 执行AI校对（传递srt_entries以支持时间戳匹配）
            corrected_segments, ai_correction_hints = self._perform_text_correction(marked_segments, words, srt_entries)
            correction_hints.extend(ai_correction_hints)

            # 7. 重新生成SRT内容
            corrected_srt_content = self._rebuild_srt_content(srt_entries, corrected_segments)

            # 8. 清理AI可能错误添加的【】符号
            corrected_srt_content = self._clean_bracket_symbols(corrected_srt_content)

            # 校对统计已在其他地方显示，避免重复
            return corrected_srt_content, correction_hints

        except Exception as e:
            error_msg = f"❌ SRT后处理AI校对失败: {str(e)}"
            self.log(error_msg)
            correction_hints.append(error_msg)
            return srt_content, correction_hints

    def _parse_srt_content(self, srt_content: str) -> List[Dict]:
        """
        将SRT内容解析为条目列表

        Args:
            srt_content: SRT格式的文本内容

        Returns:
            List[Dict]: 包含索引、时间戳和文本的条目列表
        """
        entries = []
        lines = srt_content.strip().split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 跳过空行
            if not line:
                i += 1
                continue

            # 解析序号
            try:
                index = int(line)
                i += 1

                # 解析时间戳
                if i >= len(lines):
                    break
                time_line = lines[i].strip()
                i += 1

                # 解析文本（可能多行）
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1

                text = '\n'.join(text_lines)

                if text:  # 确保有文本内容
                    entries.append({
                        'index': index,
                        'time': time_line,
                        'text': text
                    })
            except (ValueError, IndexError):
                # 解析失败，跳过当前行
                i += 1
                continue

        return entries

    def _collect_low_confidence_words(self, words: List[TimestampedWord]) -> List[TimestampedWord]:
        """
        收集低置信度词汇

        Args:
            words: 词汇列表

        Returns:
            List[TimestampedWord]: 低置信度词汇列表
        """
        low_conf_words = []
        for word in words:
            if hasattr(word, 'confidence') and word.confidence is not None:
                if word.confidence < app_config.DEFAULT_SONIOX_LOW_CONFIDENCE_THRESHOLD:
                    low_conf_words.append(word)
        return low_conf_words

    def _mark_low_confidence_words_in_segments(self, segments: List[str], low_conf_words: List[TimestampedWord]) -> List[str]:
        """
        在文本片段中标记低置信度词汇（基于时间戳的精确标记）

        Args:
            segments: 文本片段列表
            low_conf_words: 低置信度词汇列表

        Returns:
            List[str]: 标记了低置信度词汇的文本片段列表
        """
        marked_segments = []

        for segment in segments:
            # 重新构建文本，只在低置信度词汇的具体位置添加标记
            marked_text = self._rebuild_text_with_precise_marking(segment, low_conf_words)
            marked_segments.append(marked_text)

        return marked_segments

    def _rebuild_text_with_precise_marking(self, text: str, low_conf_words: List[TimestampedWord]) -> str:
        """
        基于时间戳精确重建带标记的文本

        Args:
            text: 原始文本片段
            low_conf_words: 低置信度词汇列表（带时间戳信息）

        Returns:
            str: 在正确位置添加了【】标记的文本
        """
        if not low_conf_words:
            return text

        # 将低置信度词汇按开始时间排序，确保按顺序处理
        sorted_low_conf_words = sorted(low_conf_words, key=lambda w: w.start_time)

        # 逐字符重建文本
        result = []
        current_pos = 0
        text_len = len(text)

        # 记录哪些位置已经被标记（避免重复标记）
        marked_ranges = []

        for low_conf_word in sorted_low_conf_words:
            word_text = low_conf_word.text.strip()

            # 跳过不符合标记条件的词汇
            if not word_text:
                continue
            if not any(c.isalnum() for c in word_text):
                continue
            punctuation_count = sum(1 for c in word_text if not c.isalnum())
            if punctuation_count > len(word_text) / 2:
                continue

            # 在文本中查找这个词
            search_start = current_pos
            while search_start < text_len:
                found_pos = text.find(word_text, search_start)
                if found_pos == -1:
                    break

                # 检查这个位置是否已经被标记
                is_already_marked = False
                for marked_start, marked_end in marked_ranges:
                    if found_pos >= marked_start and found_pos + len(word_text) <= marked_end:
                        is_already_marked = True
                        break

                if not is_already_marked:
                    # 添加标记前的正常文本
                    result.append(text[current_pos:found_pos])

                    # 添加标记的词汇
                    result.append(f"【{word_text}】")

                    # 更新位置和记录标记范围
                    current_pos = found_pos + len(word_text)
                    marked_ranges.append((found_pos, current_pos))
                    break
                else:
                    # 已经标记，跳过
                    search_start = found_pos + 1

        # 添加剩余的文本
        if current_pos < text_len:
            result.append(text[current_pos:])

        return ''.join(result)

    def _clean_bracket_symbols(self, text: str) -> str:
        """
        清理文本中AI可能错误添加的【】符号

        Args:
            text: 需要清理的文本

        Returns:
            str: 清理后的文本
        """
        import re

        # 1. 处理单个字符被错误标记的情况，如"女【性】" -> "女性"
        # 先移除所有【】，保留内容
        text = re.sub(r'【([^】]+)】', r'\1', text)

        # 2. 处理嵌套的【】符号（如果还有残留的话）
        while '【【' in text:
            text = re.sub(r'【【([^】]+)】】', r'【\1】', text)

        # 3. 处理空的【】符号
        text = re.sub(r'【\s*】', '', text)

        # 4. 处理包含标点符号的【】符号，保留标点外的内容
        text = re.sub(r'【([^\s]*[、。！？,.!?]+[^\s]*)】', r'\1', text)

        # 5. 最后确保没有残留的未闭合【】符号
        # 移除孤立的【或】
        text = re.sub(r'【(?![^】]*】)', '', text)  # 移除没有对应】的【
        text = re.sub(r'(?<!【)】', '', text)      # 移除没有对应【的】

        return text

    def _perform_text_correction(self, marked_segments: List[str], words: List[TimestampedWord], srt_entries: List[Dict] = None) -> tuple[List[str], List[str]]:
        """
        执行文本纠错（复用现有的LLM纠错逻辑）

        Args:
            marked_segments: 标记了低置信度词汇的文本片段列表
            words: 原始词汇列表
            srt_entries: SRT条目列表（包含时间信息，用于精准定位）

        Returns:
            tuple: (纠错后的文本片段列表, 校对提示列表)
        """
        # 复用现有的_batch_correct_with_llm方法，传递srt_entries以支持时间戳匹配
        return self._batch_correct_with_llm(marked_segments, words, srt_entries)

    def _analyze_text_change(self, original_text: str, corrected_text: str) -> dict:
        """
        分析文本变化的类型：区分"物理修改"与"实质修改"

        逻辑：
        1. has_change: 只要字符串不同就是True -> 用于决定是否更新SRT文件（保留润色）
        2. is_content_change: 只有标准化后仍不同才是True -> 用于统计纠错数量（过滤标点差异）
        """
        import re

        # 1. 预处理：去除【】标记
        unmarked_original = re.sub(r'【([^】]+)】', r'\1', original_text)

        # 2. 定义标准化函数（核心修改点）
        def normalize_text(text: str) -> str:
            # 去除首尾空白
            text = text.strip()

            # === 核心：统一省略号格式 ===
            # 将各种变体的省略号统一替换为标准ASCII省略号，消除格式差异
            # 顺序很重要：先处理长的，再处理短的
            text = text.replace('……', '...').replace('......', '...').replace('…', '...')

            # 可选：统一全半角逗句号（视需求开启，防止 "hello," vs "hello，" 被算作错误）
            # text = text.replace('，', ',').replace('。', '.')

            # 去除标点符号周边的多余空格（防止 "Hello ." vs "Hello."）
            text = re.sub(r'\s*([，。！？、：；,.!?])\s*', r'\1', text)

            # 将连续的空格合并为一个
            text = re.sub(r'\s+', ' ', text)

            return text

        # 3. 获取标准化后的文本
        normalized_unmarked = normalize_text(unmarked_original)
        normalized_corrected = normalize_text(corrected_text)

        # 4. 执行双重判定
        # 物理判定：只要有变动（包括标点润色），就视为 True
        has_change = original_text != corrected_text

        # 逻辑判定：只有实质内容变了，才视为 True
        is_content_change = normalized_unmarked != normalized_corrected

        # 5. 准备日志用的截断文本
        max_display_length = 40
        before_text = unmarked_original if '【' in original_text else original_text
        before_short = before_text[:max_display_length]
        after_short = corrected_text[:max_display_length]

        return {
            "has_change": has_change,           # 控制是否写入 SRT
            "is_content_change": is_content_change, # 控制是否计入报告统计
            "before": before_text,
            "after": corrected_text,
            "before_short": before_short,
            "after_short": after_short,
            "original_text": original_text,
            "unmarked_original": unmarked_original
        }

    def _rebuild_srt_content(self, original_entries: List[Dict], corrected_texts: List[str]) -> str:
        """
        使用校对后的文本重新构建SRT内容

        Args:
            original_entries: 原始SRT条目列表
            corrected_texts: 校对后的文本列表

        Returns:
            str: 重新构建的SRT内容
        """
        rebuilt_lines = []

        for i, entry in enumerate(original_entries):
            # 使用对应的纠错文本（如果有的话）
            corrected_text = corrected_texts[i] if i < len(corrected_texts) else entry['text']

            # 构建SRT条目
            rebuilt_lines.append(str(entry['index']))
            rebuilt_lines.append(entry['time'])
            rebuilt_lines.append(corrected_text)
            rebuilt_lines.append('')  # 空行分隔

        return '\n'.join(rebuilt_lines).strip()

    def _batch_correct_with_llm(self, segments: List[str], words: List[TimestampedWord], srt_entries: List[Dict] = None) -> tuple[List[str], List[str]]:
        """
        使用LLM智能纠正低置信度词汇

        Args:
            segments: 原始文本片段列表
            words: Soniox返回的词汇列表（包含置信度信息）

        Returns:
            tuple: (纠正后的文本片段列表, 校对提示列表)
        """
        if not segments:
            return segments, []

        # 第0步：获取所有低置信度词汇（用于提示和识别）
        low_confidence_words = []
        for word in words:
            if word.confidence < app_config.DEFAULT_SONIOX_LOW_CONFIDENCE_THRESHOLD:
                low_confidence_words.append(word.text)

        # 第1步：智能识别需要纠错的片段（传递srt_entries以支持时间戳匹配）
        target_segments = self._identify_segments_requiring_correction(segments, words, srt_entries)

        if not target_segments:
            self.log("⚪ 未发现需要纠错的片段")
            return segments, []

        # 统计包含低置信度词汇的片段数量
        segments_with_corrections = set()
        for i in target_segments:
            segments_with_corrections.add(i)

        # 计算过滤后的词汇数量
        filtered_low_conf_count = 0
        for word_text in low_confidence_words:
            # low_confidence_words 中已经存储了字符串（word.text）
            word_text = word_text.strip()
            if (word_text and
                word_text.strip() and  # 非空
                not all(c in ' 、。！？,.!?ー…' for c in word_text)):  # 不是纯标点符号
                filtered_low_conf_count += 1

        correction_hints = []
        if low_confidence_words:
            correction_hints.append(f"📊 发现 {len(low_confidence_words)} 个低置信度词汇")
            correction_hints.append(f"🎯 {len(segments_with_corrections)} 个片段需要AI校对")

        self.log(f"🤖 开始AI校对:")
        # 只显示最重要的统计信息：去除符号后的低置信度词汇数量
        if filtered_low_conf_count != len(low_confidence_words):
            self.log(f"   • 📊 发现 {filtered_low_conf_count} 个低置信度词汇")
        else:
            self.log(f"   • 📊 发现 {filtered_low_conf_count} 个低置信度词汇")
        self.log(f"   • 🎯 {len(segments_with_corrections)} 个片段需要校对")

        # 不再显示片段预览，简化用户日志

        # 第2步：创建智能批次（包含上下文）- 确保只处理真正需要校对的片段
        segment_batches = self._prepare_smart_correction_batches(segments, words, target_segments)

        # === 修改点 1: 移除过时的验证警告，改用精准统计 ===

        # 统计所有批次里实际包含的"目标"总数
        global_target_set = set(target_segments)
        count_targets_in_batches = 0
        total_payload_size = 0

        for batch in segment_batches:
            total_payload_size += len(batch)
            for idx in batch:
                if idx in global_target_set:
                    count_targets_in_batches += 1

        self.log(f"🔍 批次构建统计：目标覆盖 {count_targets_in_batches}/{len(target_segments)}，总载荷 {total_payload_size} 片段(含上下文)")

        # 只有当"包含的目标数"不等于"原本的目标数"时，才报警
        if count_targets_in_batches != len(target_segments):
            self.log(f"⚠️ 严重警告：批次构建丢失了部分目标！({count_targets_in_batches} vs {len(target_segments)})")

        # 将全局目标转换为集合，提高查找效率
        global_target_set = set(target_segments)

        # 将全局目标转换为集合，提高查找效率（防止重复定义）
        if not hasattr(self, '_global_target_set'):
            self._global_target_set = set(target_segments)

        # 调用LLM进行纠错
        original_segments = list(segments)  # 保存原始带标记的副本，用于比较
        corrected_segments = list(segments)  # 创建副本用于修改
        total_corrections = 0

        for batch_idx, batch_indices in enumerate(segment_batches):
            batch_segments = [segments[i] for i in batch_indices]
            try:
                # === 修改点 2: 优化循环内的日志显示，消除歧义 ===
                # 计算当前批次里的目标数
                current_batch_targets = sum(1 for i in batch_indices if i in self._global_target_set)

                # 优化日志：明确显示 (总载荷 vs 目标数)
                self.log(f"🔥 处理批次 {batch_idx + 1}/{len(segment_batches)} (载荷: {len(batch_indices)}片段 | 含目标: {current_batch_targets}个)")

                # === 关键修改开始 ===
                # 计算当前批次中，哪些是真正的任务目标（Local Index）
                # batch_indices 包含了 [邻居, 目标, 邻居]
                # 我们需要找出 "目标" 在 batch_segments 中的下标 (0, 1, 2...)
                real_task_local_indices = []

                for local_idx, global_idx in enumerate(batch_indices):
                    if global_idx in self._global_target_set:
                        real_task_local_indices.append(local_idx)

                # 如果计算出没有目标（理论上不可能，防守性编程），则跳过
                if not real_task_local_indices:
                    self.log(f"  ⚠️ 批次 {batch_idx + 1} 中未找到目标片段，跳过")
                    continue

                # === 关键修改结束 ===

                # 为智能纠错构建专用prompt（包含完整上下文）
                smart_prompt = self._build_smart_correction_prompt(
                    batch_segments,
                    low_confidence_words,
                    all_segments=segments,  # 传入完整片段列表作为上下文
                    target_indices=batch_indices,  # 传入当前批次的实际索引
                    target_local_indices=real_task_local_indices  # 传入真实任务索引
                )
                response = self._call_llm_api(smart_prompt, batch_segments)

                # 解析LLM响应
                corrections = self._parse_llm_correction_response(response)

                if not corrections:
                    self.log(f"  ⚪ 无纠错结果")
                    continue

                # 应用纠错结果
                batch_corrections = 0

                for correction in corrections:
                    # LLM返回的是批次内相对索引（0, 1, 2...），对应batch_segments中的位置
                    relative_idx = correction.get("segment_index", -1)
                    corrected_text = correction["corrected_text"]

                    # 检查相对索引是否有效
                    if 0 <= relative_idx < len(batch_segments):
                        # 通过相对索引找到对应的绝对索引
                        if relative_idx < len(batch_indices):
                            actual_idx = batch_indices[relative_idx]

                            if actual_idx < len(original_segments):
                                # 使用原始带标记的文本进行比较
                                original_text = original_segments[actual_idx]

                                # 分析修改类型：真正修改 vs 标记去除
                                change_info = self._analyze_text_change(original_text, corrected_text)

                                if change_info["has_change"]:
                                    if change_info["is_content_change"]:
                                        # 真正的内容修改
                                        self.log(f"  🔧 片段{actual_idx + 1}: {change_info['before_short']}... → {change_info['after_short']}...")
                                        batch_corrections += 1
                                        total_corrections += 1
                                        # 添加到真正修改的记录中
                                        correction_hints.append(f"🔧 片段{actual_idx + 1}: {change_info['before']} → {change_info['after']}")
                                    else:
                                        # 仅去除标记，不显示详细信息
                                        pass

                                # 无论是否有变化都应用修正（因为LLM可能去除【】标记）
                                corrected_segments[actual_idx] = corrected_text

                if batch_corrections == 0:
                    self.log(f"  ⚪ 无实际变化")

            except Exception as e:
                self.log(f"  ❌ 批次失败: {e}")
                continue

        # 最终统计将在函数结束时显示，避免重复信息

        # 从correction_hints中统计真正修改的数量
        content_corrections = len([h for h in correction_hints if h.startswith("🔧 片段")])
        mark_removals = len([h for h in correction_hints if "去除标记" in str(h)]) if hasattr(self, '_log_messages') else None

        # 生成重新组织的校对总结
        # 获取统计信息（使用与标记逻辑相同的过滤条件）
        filtered_low_conf_words = []
        for word in words:
            if word.confidence < app_config.DEFAULT_SONIOX_LOW_CONFIDENCE_THRESHOLD:
                word_text = word.text.strip()

                # 应用更宽松的过滤条件，主要过滤纯标点符号和空白
                if (word_text and
                    word_text.strip() and  # 非空
                    not all(c in ' 、。！？,.!?ー…' for c in word_text)):  # 不是纯标点符号
                    filtered_low_conf_words.append(word)

        low_conf_words_count = len(filtered_low_conf_words)
        segments_needing_correction = len(target_segments) if 'target_segments' in locals() else 0

        # 构建报告标题和总体统计
        summary = f"🎯 AI校对报告："
        summary += f"\n📊 总体统计："
        summary += f"\n   • 发现 {low_conf_words_count} 个低置信度词汇"
        summary += f"\n   • {segments_needing_correction} 个片段需要AI校对"
        summary += f"\n   • 🔧 真正修改了 {content_corrections} 个片段的内容"
        if total_corrections > content_corrections:
            summary += f"\n   • ✨ 去除了 {total_corrections - content_corrections} 个片段的【】标记"

        # 处理修改详情
        detail_hints = [h for h in correction_hints if h.startswith("🔧 片段")]
        if detail_hints:
            # 分离统计信息和详细信息
            stats_only = summary
            details_section = "\n📋 具体修改详情：\n" + "─" * 58

            # 过滤掉所有统计类信息，只保留具体的修改详情
            filtered_hints = []
            for h in correction_hints:
                # 跳过各种统计信息
                if (h.startswith("🔧 片段") or
                    h.startswith("📊 发现") or
                    h.startswith("🎯 ") and "个片段需要AI校对" in h or
                    "低置信度词汇" in h and ":" in h):
                    continue
                filtered_hints.append(h)

            # 重新组织hints：统计 + 分隔线 + 详情
            correction_hints = filtered_hints
            correction_hints.insert(0, stats_only)
            correction_hints.insert(1, details_section)
            correction_hints.extend(detail_hints)
        else:
            # 没有具体修改的情况 - 重新构建hints而不是插入
            if content_corrections == 0 and total_corrections == 0:
                summary = "🎯 AI校对报告：无需任何修改"
            elif content_corrections == 0 and total_corrections > 0:
                summary = f"🎯 AI校对报告：仅去除了 {total_corrections} 个片段的【】标记"

            # 重新构建correction_hints，清除之前的统计信息
            correction_hints = [summary, "─" * 50]

        return corrected_segments, correction_hints

    def _is_reasoning_model(self, model_name: str) -> bool:
        """
        判断是否为reasoning模型（需要特殊参数处理）
        
        Reasoning模型特征：
        1. 使用 max_completion_tokens 而不是 max_tokens
        2. 不支持 temperature 等采样参数
        
        包括：
        - o系列: o1, o1-mini, o3, o3-mini, o4-mini 等
        - gpt-5系列: gpt-5, gpt-5.1, gpt-5.2, gpt-5.3 及其变体
        
        Args:
            model_name: 模型名称
            
        Returns:
            bool: 如果是reasoning模型返回True
        """
        if not model_name:
            return False
        
        import re
        model_lower = model_name.lower()
        
        # o系列 reasoning模型
        # 匹配: o1, o1-xxx, o3, o3-xxx, o4, o4-xxx 等
        if re.match(r'^o\d+', model_lower):
            return True
        
        # gpt-5系列及其所有变体
        # 匹配: gpt-5, gpt-5.x, gpt-5-xxx, gpt5-xxx 等
        if re.match(r'^gpt-?5', model_lower):
            return True
        
        return False

    def _call_llm_api(self, prompt: str, batch_segments: List[str]) -> str:
        """
        调用LLM API进行文本纠错

        Args:
            prompt: 纠错提示词

        Returns:
            LLM API响应文本
        """
        try:
            import requests
            import json

            # 获取LLM API配置
            api_config = self.get_current_llm_config_for_api_call()

            api_key = api_config['api_key']
            input_base_url = api_config.get('custom_api_base_url_str', app_config.DEFAULT_LLM_API_BASE_URL)
            model_name = api_config.get('custom_model_name', app_config.DEFAULT_LLM_MODEL_NAME)
            temperature = api_config.get('custom_temperature', app_config.DEFAULT_LLM_TEMPERATURE)

            # 处理API URL，确保包含正确的路径
            if not input_base_url:
                # 使用默认URL并添加完整路径
                base_url = app_config.DEFAULT_LLM_API_BASE_URL
                if not base_url.endswith('/'):
                    base_url += '/'
                base_url += "v1/chat/completions"
            else:
                raw_url = input_base_url.strip()
                # 检查是否是完整URL（以#结尾）
                if raw_url.endswith('#'):
                    base_url = raw_url[:-1]  # 移除#标记
                else:
                    # 根据API类型添加正确的路径
                    if "api.anthropic.com" in raw_url:
                        base_url = raw_url
                        if not base_url.endswith('/'):
                            base_url += '/'
                        base_url += "v1/messages"
                    elif "generativelanguage.googleapis.com" in raw_url:
                        base_url = raw_url
                        # Gemini API直接使用base_url，在请求时添加?key参数
                    else:
                        # OpenAI兼容格式
                        base_url = raw_url
                        if not base_url.endswith('/'):
                            base_url += '/'
                        base_url += "v1/chat/completions"

            # 直接使用传入的完整prompt，避免重复构建
            # prompt参数已经包含了完整的纠错指令
            full_prompt = prompt

            self.log(f"📞 调用LLM API: {model_name}")

            # 构建API请求
            if "generativelanguage.googleapis.com" in base_url:
                # Gemini API格式
                payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "max_tokens": 4000
                    }
                }
                headers = {"Content-Type": "application/json"}
                # Gemini API使用不同的认证方式
                response = requests.post(f"{base_url}?key={api_key}", headers=headers, json=payload, timeout=180)
            elif "/v1/messages" in base_url or "api.anthropic.com" in base_url:
                # Claude API格式
                payload = {
                    "model": model_name,
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": full_prompt}]
                }
                if temperature is not None:
                    payload["temperature"] = temperature

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01"
                }
                response = requests.post(base_url, headers=headers, json=payload, timeout=180)
            else:
                # OpenAI兼容格式 - 将完整prompt拆分为system和user部分
                # 从full_prompt中提取system_prompt部分
                lines = full_prompt.split('\n')
                system_content = ""
                user_content = ""

                # 找到系统提示词部分
                if lines and ("ASR错词校对" in lines[0] or "你是一位专业的ASR" in lines[0]):
                    # 如果第一行包含系统提示，则分割
                    system_content = '\n'.join([line for line in lines if line.strip() and (line.startswith('你是一位') or line.startswith('请严格遵守') or 'ASR错词校对' in line or '只修正错别字' in line or '严禁重写' in line or '输出格式' in line)])
                    user_content = '\n'.join([line for line in lines if line.strip() and line not in system_content.split('\n')])
                else:
                    # 否则使用默认分割
                    system_content = app_config.DEEPSEEK_SYSTEM_PROMPT_CORRECTION
                    user_content = full_prompt

                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ]
                }
                
                # [FIX] Reasoning模型（GPT-5系列、o系列）需要特殊处理
                if self._is_reasoning_model(model_name):
                    # 使用 max_completion_tokens 而不是 max_tokens
                    payload["max_completion_tokens"] = 4000
                    # 不传 temperature，使用模型默认值
                else:
                    # 传统模型使用 max_tokens 和自定义 temperature
                    payload["max_tokens"] = 4000
                    if temperature is not None:
                        payload["temperature"] = temperature

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                response = requests.post(base_url, headers=headers, json=payload, timeout=180)

            response.raise_for_status()
            data = response.json()

            # 解析响应
            content = None
            if "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content")
            elif "candidates" in data and data["candidates"]:
                content = data["candidates"][0].get("content", {}).get("parts", [{}])[0].get("text")

            if content:
                self.log(f"📨 LLM响应成功 ({len(content)}字符)")
                return content.strip()
            else:
                self.log("⚠️ LLM返回空内容")
                return '{"corrections": []}'

        except requests.exceptions.Timeout:
            self.log("⏰ LLM API超时")
            return '{"corrections": []}'
        except requests.exceptions.RequestException as e:
            self.log(f"🌐 LLM请求失败: {e}")
            return '{"corrections": []}'
        except json.JSONDecodeError as e:
            self.log(f"📄 LLM响应解析失败")
            return '{"corrections": []}'
        except Exception as e:
            self.log(f"❌ LLM调用失败: {e}")
            return '{"corrections": []}'

    def _parse_llm_correction_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析LLM纠错响应

        Args:
            response: LLM API返回的JSON响应

        Returns:
            纠正结果列表
        """
        try:
            if not response.strip():
                self.log("  ⚠️ LLM返回空响应")
                return []

            # 如果不是纯JSON格式，尝试提取JSON部分
            if not response.startswith('{') and not response.startswith('['):
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    response = json_match.group(0)
                else:
                    self.log("  ⚠️ 无法从响应中提取JSON")
                    return []

            # 解析JSON响应
            response_data = json.loads(response)

            # 根据系统提示词格式，响应应该是 {"line_id": "corrected_text", ...}
            valid_corrections = []

            # 优先处理系统提示词中定义的格式：{"0": "修正后的第一句", "5": "修正后的第六句"}
            for line_id, corrected_text in response_data.items():
                try:
                    # 跳过非字符串键
                    if not isinstance(line_id, str):
                        continue

                    # 检查是否是数字字符串（行号）
                    if line_id.isdigit():
                        segment_index = int(line_id)
                    else:
                        continue  # 跳过非数字键

                    if isinstance(corrected_text, str) and corrected_text.strip():
                        valid_corrections.append({
                            "segment_index": segment_index,
                            "original_text": "",  # 在这种格式中没有原始文本
                            "corrected_text": corrected_text.strip(),
                            "changes": []  # 在这种格式中没有变更列表
                        })
                        # 不再显示每个纠错的解析详情，简化用户日志
                except (ValueError, TypeError) as e:
                    self.log(f"  解析纠错项失败: {e}")
                    continue

            # 如果是标准格式 {"corrections": [...]} (兼容性处理)
            if "corrections" in response_data and not valid_corrections:
                corrections = response_data.get("corrections", [])
                for correction in corrections:
                    if not isinstance(correction, dict):
                        continue

                    segment_index = correction.get("segment_index", -1)
                    original_text = correction.get("original_text", "")
                    corrected_text = correction.get("corrected_text", "")
                    changes = correction.get("changes", [])

                    if (isinstance(segment_index, int) and segment_index >= 0 and
                        isinstance(corrected_text, str) and corrected_text.strip()):
                        valid_corrections.append({
                            "segment_index": segment_index,
                            "original_text": original_text,
                            "corrected_text": corrected_text,
                            "changes": changes
                        })

            if valid_corrections:
                # 纠错数量在最终统计中显示，这里不再重复
                pass

            return valid_corrections

        except json.JSONDecodeError as e:
            self.log("📄 JSON解析错误")
            return []
        except Exception as e:
            self.log(f"❌ 响应解析失败: {e}")
            return []

    def process_to_srt(self, parsed_transcription: ParsedTranscription,
                       llm_segments_text: List[str],
                       source_format: str = "elevenlabs",
                       enable_ai_correction: bool = False
                      ) -> tuple[Optional[str], List[str]]:
        self.log("--- 开始对齐 LLM 片段 (SrtProcessor) ---")

        # 在函数开始就初始化correction_hints，避免变量作用域错误
        correction_hints: List[str] = []

        # 确定处理模式
        source_format_lower = source_format.lower() if source_format else ""
        if source_format_lower == "soniox":
            processing_mode = "C"
            self.log("识别处理模式: Mode C (Soniox智能处理)")
        elif source_format_lower in ["elevenlabs", "elevenlabs_api"]:
            processing_mode = "B"
            self.log("识别处理模式: Mode B (ElevenLabs兼容处理)")
        else:
            processing_mode = "A"
            self.log(f"识别处理模式: Mode A (基础处理) - 源格式: {source_format}")

        # AI纠错功能将在SRT生成后进行，避免数据不一致问题
        # 注意：enable_ai_correction 参数将在最后阶段使用

        # 【修复】根据是否启用AI纠错动态调整进度权重分配
        if enable_ai_correction and source_format_lower == "soniox":
            # Soniox + AI纠错模式：为AI纠错阶段分配40%权重，其他阶段各20%
            phase_weight_align = self.WEIGHT_ALIGN  # 20%
            phase_weight_merge = self.WEIGHT_MERGE  # 20%
            phase_weight_format = self.WEIGHT_FORMAT  # 20%
            phase_weight_ai_correction = self.WEIGHT_AI_CORRECTION  # 40%
            self.log("进度分配: 基础SRT生成20% + 合并20% + 格式化20% + AI纠错40%")
        else:
            # 其他模式：使用原有的60%权重分配给前三个阶段
            phase_weight_align = 40  # 基础SRT生成
            phase_weight_merge = 30  # 合并
            phase_weight_format = 30  # 格式化
            phase_weight_ai_correction = 0  # 无AI纠错
            total_assigned = phase_weight_align + phase_weight_merge + phase_weight_format
            # 确保总权重为100%
            if total_assigned < 100:
                phase_weight_format = phase_weight_format + (100 - total_assigned)
            self.log(f"进度分配: 基础SRT生成{phase_weight_align}% + 合并{phase_weight_merge}% + 格式化{phase_weight_format}%")

        intermediate_entries: List[SubtitleEntry] = []
        word_search_start_index = 0
        unaligned_segments: List[str] = []
        all_parsed_words = parsed_transcription.words
        if not llm_segments_text: self.log("错误：LLM 未返回任何分割片段。"); return None
        if not all_parsed_words: self.log("错误：解析后的词列表为空，无法进行对齐。"); return None


        total_llm_segments = len(llm_segments_text)
        completed_steps_phase1 = 0
        self.log(f"SRT阶段1: 对齐LLM片段 (Mode {processing_mode})...")
        for i, text_seg_from_llm in enumerate(llm_segments_text):
            if not self._is_worker_running():
                self.log("⚠️ 任务被用户中断")
                return None
            matched_words, next_search_idx, match_ratio = self.get_segment_words_fuzzy(text_seg_from_llm, all_parsed_words, word_search_start_index)
            if not matched_words or match_ratio == 0:
                unaligned_segments.append(text_seg_from_llm)
                completed_steps_phase1 += 1
                # 【修复】使用动态分配的权重
                self._emit_srt_progress(int( (completed_steps_phase1 / total_llm_segments) * phase_weight_align ), 100)
                continue

            
            word_search_start_index = next_search_idx
            first_actual_word_index = -1
            for idx_fw, word_obj_fw in enumerate(matched_words):
                if word_obj_fw.text.strip(): first_actual_word_index = idx_fw; break
            last_actual_word_index = -1
            for idx_bw in range(len(matched_words) - 1, -1, -1):
                if matched_words[idx_bw].text.strip(): last_actual_word_index = idx_bw; break
            entry_text_from_llm = text_seg_from_llm.strip()
            actual_words_for_entry: List[TimestampedWord]
            if first_actual_word_index != -1 and last_actual_word_index != -1 :
                entry_start_time = matched_words[first_actual_word_index].start_time
                entry_end_time = matched_words[last_actual_word_index].end_time
                actual_words_for_entry = matched_words[first_actual_word_index : last_actual_word_index+1]
                if not actual_words_for_entry:
                    self.log(f"警告: 修正后的词列表为空，LLM片段 \"{entry_text_from_llm[:30]}...\"。将使用原始匹配边界。")
                    entry_start_time = matched_words[0].start_time; entry_end_time = matched_words[-1].end_time
                    actual_words_for_entry = matched_words
            else:
                self.log(f"警告: LLM片段 \"{entry_text_from_llm[:30]}...\" 匹配到的所有ASR词元均为空或空格。将使用原始匹配边界。")
                entry_start_time = matched_words[0].start_time; entry_end_time = matched_words[-1].end_time
                actual_words_for_entry = matched_words
            
            entry_duration = max(0.001, entry_end_time - entry_start_time)
            text_len = len(entry_text_from_llm)
            is_audio_event = self._is_audio_event_words(actual_words_for_entry) if actual_words_for_entry else False

            # 应用结束时间修正 (主流程)
            if is_audio_event:
                # 音频事件：保持原始结束时间，不应用时间修正
                final_audio_event_end_time = entry_end_time
                self.log(f"   检测到音频事件，保持原始时长: \"{entry_text_from_llm}\"")

                # 音频事件：使用修正后的时间（可能包含向前延长），但不向后延长
                audio_event_text_content = "".join([w.text for w in actual_words_for_entry])
                intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_audio_event_end_time, audio_event_text_content, actual_words_for_entry, match_ratio))
            else:
                # 根据处理模式决定是否在此阶段应用时间修正
                if processing_mode == "B":
                    # Mode B: 暂不应用时间修正，将在Mode B阶段进行专门的"一句一句优化"
                    # 使用原始时间创建字幕条目，让Mode B处理阶段进行时间优化
                    intermediate_entries.append(SubtitleEntry(0, entry_start_time, entry_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
                elif processing_mode == "C":
                    # Mode C: 应用Soniox专用的时间修正逻辑
                    corrected_end_time = self._apply_end_time_correction(actual_words_for_entry, entry_end_time, entry_start_time)
                    corrected_entry_duration = max(0.001, corrected_end_time - entry_start_time)

                    if corrected_entry_duration > self.max_duration or text_len > self.max_chars_per_line:
                        self.log(f"   ⚠️ Mode C: 片段超限，需分割: \"{entry_text_from_llm[:30]}...\" (修正后时长: {corrected_entry_duration:.2f}s, 文本长度: {text_len})")
                        original_text_for_splitting = "".join([w.text for w in actual_words_for_entry])
                        split_sub_entries = self.split_long_sentence(original_text_for_splitting, actual_words_for_entry, entry_start_time, corrected_end_time, 0, corrected_end_time)

                        final_entries = []
                        for sub_entry in split_sub_entries:
                            sub_entry.alignment_ratio = match_ratio
                            if sub_entry.duration > self.max_duration and len(sub_entry.words_used) > 1:
                                safe_text_for_recursion = "".join([w.text for w in sub_entry.words_used])
                                recursive_splits = self.split_long_sentence(safe_text_for_recursion, sub_entry.words_used, sub_entry.start_time, sub_entry.end_time, 1, corrected_end_time)
                                for recursive_entry in recursive_splits:
                                    recursive_entry.alignment_ratio = match_ratio
                                    final_entries.append(recursive_entry)
                            else:
                                final_entries.append(sub_entry)

                        if len(final_entries) > 1:
                            self.log(f"   ✅ Mode C: 片段已分割为 {len(final_entries)} 个子片段")
                        intermediate_entries.extend(final_entries)
                    elif corrected_entry_duration < self.min_duration_target:
                        # Mode C短时长处理
                        is_bracketed = self._is_bracketed_content(entry_text_from_llm)
                        if is_bracketed:
                            self.log(f"   Mode C: 检测到括号内容，保持原始时长: \"{entry_text_from_llm}\" ({corrected_entry_duration:.2f}s)")
                            final_short_entry_end_time = corrected_end_time
                        else:
                            final_short_entry_end_time = entry_start_time + self.min_duration_target
                            if corrected_entry_duration < app_config.MIN_DURATION_ABSOLUTE:
                                final_short_entry_end_time = entry_start_time + app_config.MIN_DURATION_ABSOLUTE
                            original_end_of_last_actual_word = actual_words_for_entry[-1].end_time if actual_words_for_entry else entry_start_time
                            max_allowed_extension = original_end_of_last_actual_word + 0.5
                            final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                            final_short_entry_end_time = max(final_short_entry_end_time, corrected_end_time)
                            final_short_entry_end_time = max(final_short_entry_end_time, entry_start_time + 0.001)

                        intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
                    else:
                        # Mode C正常情况
                        intermediate_entries.append(SubtitleEntry(0, entry_start_time, corrected_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
                else:
                    # Mode A: 应用基础的时间修正逻辑
                    corrected_end_time = self._apply_end_time_correction(actual_words_for_entry, entry_end_time, entry_start_time)
                    corrected_entry_duration = max(0.001, corrected_end_time - entry_start_time)

                    if corrected_entry_duration > self.max_duration or text_len > self.max_chars_per_line:
                        self.log(f"   ⚠️ Mode A: 片段超限，需分割: \"{entry_text_from_llm[:30]}...\" (修正后时长: {corrected_entry_duration:.2f}s, 文本长度: {text_len})")
                        original_text_for_splitting = "".join([w.text for w in actual_words_for_entry])
                        split_sub_entries = self.split_long_sentence(original_text_for_splitting, actual_words_for_entry, entry_start_time, corrected_end_time, 0, corrected_end_time)

                        final_entries = []
                        for sub_entry in split_sub_entries:
                            sub_entry.alignment_ratio = match_ratio
                            if sub_entry.duration > self.max_duration and len(sub_entry.words_used) > 1:
                                safe_text_for_recursion = "".join([w.text for w in sub_entry.words_used])
                                recursive_splits = self.split_long_sentence(safe_text_for_recursion, sub_entry.words_used, sub_entry.start_time, sub_entry.end_time, 1, corrected_end_time)
                                for recursive_entry in recursive_splits:
                                    recursive_entry.alignment_ratio = match_ratio
                                    final_entries.append(recursive_entry)
                            else:
                                final_entries.append(sub_entry)

                        if len(final_entries) > 1:
                            self.log(f"   ✅ Mode A: 片段已分割为 {len(final_entries)} 个子片段")
                        intermediate_entries.extend(final_entries)
                    elif corrected_entry_duration < self.min_duration_target:
                        # Mode A短时长处理
                        is_bracketed = self._is_bracketed_content(entry_text_from_llm)
                        if is_bracketed:
                            self.log(f"   Mode A: 检测到括号内容，保持原始时长: \"{entry_text_from_llm}\" ({corrected_entry_duration:.2f}s)")
                            final_short_entry_end_time = corrected_end_time
                        else:
                            final_short_entry_end_time = entry_start_time + self.min_duration_target
                            if corrected_entry_duration < app_config.MIN_DURATION_ABSOLUTE:
                                final_short_entry_end_time = entry_start_time + app_config.MIN_DURATION_ABSOLUTE
                            original_end_of_last_actual_word = actual_words_for_entry[-1].end_time if actual_words_for_entry else entry_start_time
                            max_allowed_extension = original_end_of_last_actual_word + 0.5
                            final_short_entry_end_time = min(final_short_entry_end_time, max_allowed_extension)
                            final_short_entry_end_time = max(final_short_entry_end_time, corrected_end_time)
                            final_short_entry_end_time = max(final_short_entry_end_time, entry_start_time + 0.001)

                        intermediate_entries.append(SubtitleEntry(0, entry_start_time, final_short_entry_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
                    else:
                        # Mode A正常情况
                        intermediate_entries.append(SubtitleEntry(0, entry_start_time, corrected_end_time, entry_text_from_llm, actual_words_for_entry, match_ratio))
            completed_steps_phase1 += 1
            # 【修复】使用动态分配的权重
            self._emit_srt_progress(int( (completed_steps_phase1 / total_llm_segments) * phase_weight_align ), 100)
        self.log("--- LLM片段对齐结束 ---")
        if unaligned_segments:
            self.log(f"\\n--- 以下 {len(unaligned_segments)} 个LLM片段未能成功对齐，已跳过 ---")
            for seg_idx, seg_text in enumerate(unaligned_segments): self.log(f"- 片段 {seg_idx+1}: \"{seg_text}\"")
            self.log("----------------------------------------\\n")
        if not intermediate_entries: self.log("错误：对齐后没有生成任何有效的字幕条目。"); return None
        intermediate_entries.sort(key=lambda e: e.start_time)
        
        # --- Phase 2: 智能合并 (模式特定) ---
        self.log(f"SRT阶段2: 合并调整字幕条目 (Mode {processing_mode})...")

        # 根据模式设置合并参数
        if processing_mode == "C":
            # Mode C: Soniox - 更激进的合并策略，因为时间戳更精确
            merge_gap_threshold = 0.5  # 更小的间隙允许合并
            self.log("Mode C: 使用激进的合并策略 (间隙阈值: 0.5s)")
        elif processing_mode == "B":
            # Mode B: ElevenLabs - 适中的合并策略
            merge_gap_threshold = 0.8  # 原有的阈值
            self.log("Mode B: 使用适中的合并策略 (间隙阈值: 0.8s)")
        else:
            # Mode A: 基础 - 保守的合并策略
            merge_gap_threshold = 1.0  # 更保守的阈值
            self.log("Mode A: 使用保守的合并策略 (间隙阈值: 1.0s)")
        merged_entries: List[SubtitleEntry] = []
        idx_merge = 0
        total_intermediate_entries = len(intermediate_entries)
        
        while idx_merge < total_intermediate_entries:
            if not self._is_worker_running(): self.log("任务被用户中断(合并阶段)。"); return None
            
            current_entry = intermediate_entries[idx_merge]
            merged_this_iteration = False
            
            # 尝试与下一条合并
            if idx_merge + 1 < len(intermediate_entries):
                next_entry = intermediate_entries[idx_merge+1]
                
                # 检查是否满足合并的基本硬性条件
                can_merge, reason = self._can_merge_entries(current_entry, next_entry)
                
                if can_merge:
                    # 计算合并收益
                    benefit = self._calculate_merge_benefit(current_entry, next_entry)
                    
                    # 只有收益超过阈值才合并 (Scribe2SRT 默认阈值 5.0)
                    if benefit > 5.0:
                        self.log(f"   合并字幕 (收益 {benefit:.1f}): \"{current_entry.text[:15]}...\" + \"{next_entry.text[:15]}...\"")
                        merged_entry = self._merge_two_entries(current_entry, next_entry)
                        merged_entries.append(merged_entry)
                        idx_merge += 2
                        merged_this_iteration = True
                    else:
                        pass

            if not merged_this_iteration:
                merged_entries.append(current_entry)
                idx_merge += 1
                
            current_phase2_progress_component = int(((idx_merge) / total_intermediate_entries if total_intermediate_entries > 0 else 1) * phase_weight_merge)
            # 【修复】合并阶段进度计算：阶段1权重 + 当前阶段2进度
            self._emit_srt_progress(phase_weight_align + current_phase2_progress_component, 100)
        # --- End Phase 2 ---

        self.log(f"--- 合并调整后得到 {len(merged_entries)} 个字幕条目，开始最终格式化 ---")
        self.log(f"SRT阶段3: 最终格式化字幕 (Mode {processing_mode})...")

        # 初始化校对提示列表（必须在模式处理之前）
        correction_hints: List[str] = []

        # 根据模式设置时间优化参数
        if processing_mode == "C":
            # Mode C: Soniox - 应用置信度基础的时间优化
            self.log("Mode C: 应用Soniox专用时间优化策略")
            correction_hints.extend(self._apply_mode_c_optimization_to_entries(merged_entries, parsed_transcription))

            # 【修复】Mode C时间优化阶段完成后，手动更新进度
            # 阶段1(20%) + 阶段2(20%) = 40%
            mode_c_optimization_completion_progress = phase_weight_align + phase_weight_merge
            self._emit_srt_progress(mode_c_optimization_completion_progress, 100)
        elif processing_mode == "B":
            # Mode B: ElevenLabs - 先应用一句一句优化，再进行合并
            self.log("Mode B: 应用ElevenLabs一句一句优化策略")
            self._apply_mode_b_time_optimization(merged_entries)
            # Mode B需要在时间优化后进行合并，因为合并决策应该基于优化后的时间戳
            self.log("Mode B: 开始基于优化后时间戳的合并调整")
            self._apply_mode_b_merge_optimization(merged_entries)

            # 【修复】Mode B合并阶段完成后，手动更新进度（跳过独立方法的进度计算）
            # 阶段1(20%) + 阶段2(20%) = 40%
            mode_b_merge_completion_progress = phase_weight_align + phase_weight_merge
            self._emit_srt_progress(mode_b_merge_completion_progress, 100)
        else:
            # Mode A: 基础 - 最小必要处理
            self.log("Mode A: 应用基础时间优化策略")
            self._apply_mode_a_optimization_to_entries(merged_entries)

            # 【修复】Mode A时间优化阶段完成后，手动更新进度
            # 阶段1(20%) + 阶段2(20%) = 40%
            mode_a_optimization_completion_progress = phase_weight_align + phase_weight_merge
            self._emit_srt_progress(mode_a_optimization_completion_progress, 100)
        final_srt_formatted_list: List[str] = []
        final_entry_objects: List[SubtitleEntry] = []  # <--- [新增] 初始化列表
        last_processed_entry_object: Optional[SubtitleEntry] = None
        subtitle_index = 1
        total_merged_final_entries = len(merged_entries)
        for entry_idx, current_entry in enumerate(merged_entries):
            if not self._is_worker_running(): self.log("任务被用户中断(最终格式化阶段)。"); return None
            self.log(f"   格式化条目 {entry_idx+1}/{total_merged_final_entries}: \"{current_entry.text[:30]}...\"")
            if last_processed_entry_object is not None:

                # 只有Mode B执行复杂的时间优化逻辑
                if processing_mode == "B":
                    # Mode B: ElevenLabs - 复杂时间优化逻辑
                    raw_gap = current_entry.start_time - last_processed_entry_object.end_time

                    # 检测并修正时间重叠
                    if raw_gap < -0.01:  # 检测到负时间（重叠）
                        self.log(f"字幕时间重叠修正: 调整重叠时间 {raw_gap:.3f}s")
                        new_start_time = last_processed_entry_object.end_time + 0.01
                        if new_start_time < current_entry.end_time:
                            current_entry.start_time = new_start_time

                    # 应用开始时间修正 (提前0.25s)
                    current_is_audio_event = self._is_bracketed_content(current_entry.text)
                    if not current_is_audio_event and raw_gap > 0.5:
                        self.log(f"字幕时间优化: 检测到较大时间间隙 ({raw_gap:.2f}s)")
                        new_start_time = current_entry.start_time - 0.25
                        if new_start_time > last_processed_entry_object.end_time:
                            self.log(f"字幕时间优化: 提前开始时间以减少间隙")
                            current_entry.start_time = new_start_time
                        else:
                            self.log(f"时间优化跳过: 会与上一句重叠")

                    # 100ms 间隙逻辑
                    last_is_audio_event = self._is_bracketed_content(last_processed_entry_object.text)
                    gap_seconds = self.default_gap_ms / 1000.0

                    if not (current_is_audio_event or last_is_audio_event):
                        if current_entry.start_time < last_processed_entry_object.end_time + gap_seconds:
                            new_current_start_time = last_processed_entry_object.end_time + gap_seconds
                            min_current_duration = app_config.MIN_DURATION_ABSOLUTE
                            if new_current_start_time + min_current_duration <= current_entry.end_time:
                                self.log(f"字幕时间优化: 调整以保持最小间距")
                                current_entry.start_time = new_current_start_time
                            if final_srt_formatted_list:
                                final_srt_formatted_list[-1] = last_processed_entry_object.to_srt_format(self)
                else:
                    # Mode A & C: 只进行基本的重叠修正
                    raw_gap = current_entry.start_time - last_processed_entry_object.end_time
                    if raw_gap < -0.01:
                        self.log(f"基础重叠修正: 调整重叠时间 {raw_gap:.3f}s")
                        current_entry.start_time = last_processed_entry_object.end_time + 0.01
            current_duration = current_entry.duration
            entry_is_audio_event = False
            if current_entry.words_used: entry_is_audio_event = any(not w.text.strip() or getattr(w, 'type', 'word') == 'audio_event' or re.match(r"^\(.*\)$|^（.*）$", w.text.strip()) for w in current_entry.words_used)

            # 初始化变量，避免UnboundLocalError
            min_duration_to_apply_val = None

            # 根据模式应用不同的时长处理
            if not current_entry.is_intentionally_oversized and not entry_is_audio_event:
                if processing_mode == "A":
                    # Mode A: 只应用绝对最小时长
                    min_duration_to_apply_val = app_config.MIN_DURATION_ABSOLUTE if current_duration < app_config.MIN_DURATION_ABSOLUTE else None
                elif processing_mode == "C":
                    # Mode C: 应用Soniox专用时长策略（可能更严格）
                    min_duration_to_apply_val = self.min_duration_target if current_duration < self.min_duration_target else None
                else:
                    # Mode B: ElevenLabs 兼容模式
                    min_duration_to_apply_val = None

                    # 计算最终生效的最小目标：取用户设置和系统底限中的较大者
                    # 例如：用户设1.2s，系统底限1.0s -> 目标为 1.2s
                    final_target_min = max(self.min_duration_target, app_config.MIN_DURATION_ABSOLUTE)

                    # 只有当时长小于这个目标时才应用修正
                    if current_duration < final_target_min:
                        min_duration_to_apply_val = final_target_min

            if min_duration_to_apply_val is not None:
                current_entry.end_time = max(current_entry.end_time, current_entry.start_time + min_duration_to_apply_val)

            # 最大时长限制（所有模式都应用）
            if not current_entry.is_intentionally_oversized and current_entry.duration > self.max_duration:
                # Mode C特殊处理：尝试对舒适度优化后的超限片段进行分割
                if processing_mode == "C" and len(current_entry.words_used) > 1:
                    self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_duration:.2f}s 超出最大值 {self.max_duration}s，尝试特殊分割。")

                    # 尝试分割超限片段（不重复添加舒适度时间）
                    split_entries = self._split_comfort_optimized_entry(current_entry)

                    if len(split_entries) > 1:
                        # 分割成功，立即格式化所有分割后的片段并添加到final_srt_formatted_list
                        self.log(f"特殊分割成功：原片段分为 {len(split_entries)} 个子片段")

                        for split_idx, split_entry in enumerate(split_entries):
                            split_entry.index = subtitle_index + split_idx

                            # 1. 生成 SRT 字符串
                            final_srt_formatted_list.append(split_entry.to_srt_format(self))

                            # 2. [新增] 收集正确的对象
                            final_entry_objects.append(split_entry)

                            self.log(f"   格式化分割片段 {split_idx+1}/{len(split_entries)}: ...")
                    # if len(split_entries) > 1:
                    #     # 分割成功，立即格式化所有分割后的片段并添加到final_srt_formatted_list
                    #     self.log(f"特殊分割成功：原片段分为 {len(split_entries)} 个子片段")

                    #     # 立即格式化所有分割后的片段并添加到final_srt_formatted_list
                    #     for split_idx, split_entry in enumerate(split_entries):
                    #         split_entry.index = subtitle_index + split_idx
                    #         final_srt_formatted_list.append(split_entry.to_srt_format(self))
                    #         self.log(f"   格式化分割片段 {split_idx+1}/{len(split_entries)}: \"{split_entry.text[:30]}...\"")

                        # 更新索引和last_processed_entry_object
                        subtitle_index += len(split_entries)
                        last_processed_entry_object = split_entries[-1]
                        # 跳过当前条目的后续处理，不要修改merged_entries
                        continue
                    else:
                        # 无法分割，保持原样并截断
                        self.log(f"特殊分割失败，截断超限片段")
                        current_entry.end_time = current_entry.start_time + self.max_duration
                else:
                    # 其他模式或无法分割的片段，直接截断
                    self.log(f"字幕 \"{current_entry.text[:30]}...\" 时长 {current_duration:.2f}s 超出最大值 {self.max_duration}s，将被截断。")
                    current_entry.end_time = current_entry.start_time + self.max_duration
            if current_entry.end_time <= current_entry.start_time: 
                 current_entry.end_time = current_entry.start_time + 0.001
            
            current_entry.index = subtitle_index

            # 1. 生成 SRT 字符串
            final_srt_formatted_list.append(current_entry.to_srt_format(self))

            # 2. [新增] 收集正确的对象
            final_entry_objects.append(current_entry)

            last_processed_entry_object = current_entry; subtitle_index += 1
            current_phase3_progress_component = int(((entry_idx + 1) / total_merged_final_entries if total_merged_final_entries > 0 else 1) * phase_weight_format)
            # 【修复】格式化阶段进度计算：阶段1权重 + 阶段2权重 + 当前阶段3进度
            self._emit_srt_progress(phase_weight_align + phase_weight_merge + current_phase3_progress_component, 100)
        self.log("--- SRT 内容生成和格式化完成 ---")

        # Soniox专用词级间距验证：在终极优化之前应用词级调整逻辑
        if processing_mode == "C" and len(final_entry_objects) >= 2:  # <--- 使用新列表判断
            self.log("--- Soniox词级间距验证：在终极优化前检查最小间距要求 ---")

            # 应用词级间距验证 (传入正确的新列表)
            # 注意：_apply_word_level_spacing_validation 会直接修改传入对象的时间属性
            self._apply_word_level_spacing_validation(final_entry_objects)

            # 基于调整后的对象重新生成 SRT 列表
            final_srt_formatted_list = []
            for entry in final_entry_objects:  # <--- 使用正确的新列表重构
                final_srt_formatted_list.append(entry.to_srt_format(self))

            self.log("--- Soniox词级间距验证完成 ---")

        # Soniox专用终极优化：动态前移开始时间
        if processing_mode == "C" and len(final_srt_formatted_list) > 0:
            self.log("--- Soniox终极优化：动态调整字幕开始时间 ---")
            optimized_srt_list = self._apply_soniox_ultimate_optimization(final_srt_formatted_list)
            final_srt_formatted_list = optimized_srt_list
            self.log("--- Soniox终极优化完成 ---")

            # 注意：词级间距验证已在终极优化前完成，无需在此重复进行

        # 生成最终SRT内容
        final_srt_content = "".join(final_srt_formatted_list).strip()

        # 【新增】在SRT生成完成后进行AI校对（后处理模式）
        if enable_ai_correction and processing_mode == "C" and final_srt_content:
            if not self.llm_api_key:
                self.log("⚠️ 未配置LLM API密钥，跳过AI校对")
                correction_hints.append("⚠️ 未配置LLM API密钥，跳过AI校对")
                # 【修复】AI纠错阶段跳过时，直接标记为完成
                completion_progress = phase_weight_align + phase_weight_merge + phase_weight_format + phase_weight_ai_correction
                self._emit_srt_progress(completion_progress, 100)
            else:
                try:
                    self.log("🤖 开始AI纠错阶段（占总进度40%）")
                    # 【修复】AI纠错阶段开始进度（前三个阶段完成）
                    ai_correction_start_progress = phase_weight_align + phase_weight_merge + phase_weight_format
                    self._emit_srt_progress(ai_correction_start_progress, 100)

                    final_srt_content, ai_correction_hints = self._apply_post_srt_ai_correction(
                        final_srt_content, parsed_transcription.words
                    )
                    correction_hints.extend(ai_correction_hints)

                    # 【修复】AI纠错阶段完成进度
                    completion_progress = ai_correction_start_progress + phase_weight_ai_correction
                    self._emit_srt_progress(completion_progress, 100)
                    self.log("✅ AI纠错阶段完成")
                except Exception as e:
                    error_msg = f"❌ SRT后处理AI校对失败: {str(e)}"
                    self.log(error_msg)
                    correction_hints.append(error_msg)
                    # 【修复】AI纠错失败时也标记为完成进度
                    completion_progress = phase_weight_align + phase_weight_merge + phase_weight_format + phase_weight_ai_correction
                    self._emit_srt_progress(completion_progress, 100)
        elif enable_ai_correction and processing_mode != "C":
            self.log(f"⚠️ AI纠错仅支持Soniox模式，当前为{processing_mode}模式")
            correction_hints.append(f"⚠️ AI纠错仅支持Soniox模式，当前为{processing_mode}模式")

        # 最终确保清理所有残留的【】符号
        final_srt_content = self._clean_bracket_symbols(final_srt_content)

        # 【修复】确保进度总是达到100%
        final_progress = phase_weight_align + phase_weight_merge + phase_weight_format + phase_weight_ai_correction
        self._emit_srt_progress(final_progress, 100)

        # 返回已生成的SRT内容和校对提示
        return final_srt_content, correction_hints