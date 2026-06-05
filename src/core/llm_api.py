"""
LLM API 客户端模块

提供与多种大语言模型API服务的统一接口。
支持 OpenAI、Claude、Gemini、DeepSeek 等主流LLM服务商。
包含文本分割、摘要生成、连接测试等功能。

作者: fuxiaomoke
版本: 0.2.2.0
"""

import os
import requests
from typing import Optional, List, Any, Dict
import traceback
import time
import re

import config as app_config # 使用别名
from core.model_limits import get_max_output_tokens

from langdetect import detect

# 默认系统提示词配置
DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION = app_config.DEEPSEEK_SYSTEM_PROMPT_EN
DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN

# 文本分块处理的默认最大字符数（模型未知时的兜底值）
MAX_CHARS_PER_CHUNK = 2800

# LLM 请求重试与失败兜底配置
LLM_REQUEST_TIMEOUT_SECONDS = 180
LLM_MAX_REQUEST_ATTEMPTS = 3
LLM_RETRY_BACKOFF_SECONDS = (1.0, 2.0)
LLM_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
LLM_SPLIT_RETRY_CHARS = max(700, MAX_CHARS_PER_CHUNK // 2)
LLM_LOCAL_FALLBACK_MAX_CHARS = 120


def _sleep_with_cancel_check(seconds: float, is_running_func=None) -> bool:
    """可被取消打断的短等待。返回 False 表示等待期间任务已取消。"""
    end_time = time.time() + seconds
    while time.time() < end_time:
        if is_running_func and not is_running_func():
            return False
        time.sleep(min(0.2, max(0.0, end_time - time.time())))
    return not (is_running_func and not is_running_func())


def _should_retry_status(status_code: int) -> bool:
    return status_code in LLM_RETRYABLE_STATUS_CODES


def _post_json_with_retries(
    url: str,
    logger_func,
    context_label: str,
    is_running_func=None,
    max_attempts: int = LLM_MAX_REQUEST_ATTEMPTS,
    **kwargs,
) -> Optional[requests.Response]:
    """发送 JSON POST 请求，并对临时性失败做有限重试。"""
    kwargs.setdefault("timeout", LLM_REQUEST_TIMEOUT_SECONDS)

    for attempt in range(1, max_attempts + 1):
        if is_running_func and not is_running_func():
            logger_func(f"{context_label} 请求前任务已取消。")
            return None

        try:
            response = requests.post(url, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt >= max_attempts:
                logger_func(f"错误: {context_label} 请求失败，已尝试 {attempt}/{max_attempts} 次: {e}")
                return None
            delay = LLM_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(LLM_RETRY_BACKOFF_SECONDS) - 1)]
            logger_func(f"{context_label} 请求失败 ({type(e).__name__})，{delay:.1f} 秒后重试 {attempt + 1}/{max_attempts}...")
            if not _sleep_with_cancel_check(delay, is_running_func):
                logger_func(f"{context_label} 重试等待期间任务已取消。")
                return None
            continue
        except requests.exceptions.RequestException as e:
            response = e.response
            if response is None or _should_retry_status(response.status_code):
                if attempt >= max_attempts:
                    logger_func(f"错误: {context_label} 请求异常，已尝试 {attempt}/{max_attempts} 次: {e}")
                    return response
                delay = LLM_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(LLM_RETRY_BACKOFF_SECONDS) - 1)]
                logger_func(f"{context_label} 请求异常 ({e})，{delay:.1f} 秒后重试 {attempt + 1}/{max_attempts}...")
                if not _sleep_with_cancel_check(delay, is_running_func):
                    logger_func(f"{context_label} 重试等待期间任务已取消。")
                    return None
                continue
            raise

        if _should_retry_status(response.status_code) and attempt < max_attempts:
            delay = LLM_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(LLM_RETRY_BACKOFF_SECONDS) - 1)]
            logger_func(f"{context_label} 返回临时性错误 HTTP {response.status_code}，{delay:.1f} 秒后重试 {attempt + 1}/{max_attempts}...")
            if not _sleep_with_cancel_check(delay, is_running_func):
                logger_func(f"{context_label} 重试等待期间任务已取消。")
                return None
            continue

        setattr(response, "_llm_retry_attempt", attempt)
        if attempt > 1:
            logger_func(f"{context_label} 第 {attempt}/{max_attempts} 次请求已返回。")
        return response

    return None


def _split_long_segment_locally(text: str, max_chars: int) -> List[str]:
    """把过长文本按弱标点、空格或固定长度进一步切开。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    result: List[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        cut = end
        if end < len(text):
            search_start = max(pos, end - max(30, max_chars // 3))
            best = -1
            for m in re.finditer(r'[，、,；;：:\s]', text[search_start:end]):
                candidate = search_start + m.end()
                if candidate > pos:
                    best = candidate
            if best != -1:
                cut = best
        part = text[pos:cut].strip()
        if part:
            result.append(part)
        pos = cut
    return result


def _fallback_segment_text_locally(text: str, logger_func=None) -> List[str]:
    """LLM 不可用时的本地规则断句兜底，确保原文不整块丢失。"""
    if not text or not text.strip():
        return []

    primary_parts: List[str] = []
    for line in re.split(r'\n+', text):
        line = line.strip()
        if not line:
            continue
        start = 0
        for m in re.finditer(r'(?:[。．！？!?]|\.{3,}|…+|‥+)', line):
            end = m.end()
            part = line[start:end].strip()
            if part:
                primary_parts.append(part)
            start = end
        tail = line[start:].strip()
        if tail:
            primary_parts.append(tail)

    if not primary_parts:
        primary_parts = [text.strip()]

    segments: List[str] = []
    for part in primary_parts:
        segments.extend(_split_long_segment_locally(part, LLM_LOCAL_FALLBACK_MAX_CHARS))

    segments = _preprocess_bracket_mixed_segments(segments, logger_func or (lambda _msg: None))
    segments = _validate_and_fix_segments(segments, logger_func or (lambda _msg: None))
    if logger_func:
        logger_func(f"已使用本地规则兜底断句，生成 {len(segments)} 个片段。")
    return segments


def _is_reasoning_model(model_name: str) -> bool:
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


# ── 思考模式 (Thinking Mode) 辅助函数 ──

# thinking_level → budget_tokens 映射
_THINKING_BUDGETS = {1: 8192, 2: 32768}

# thinking_level → reasoning_effort 字符串映射
_THINKING_EFFORT = {1: "high", 2: "max"}


def _is_default_thinking_model(model_name: str) -> bool:
    """
    判断模型是否默认开启思考模式（需要显式关闭）。
    目前仅 DeepSeek V4 系列和 deepseek-chat/deepseek-reasoner 默认开启。
    不匹配 deepseek-v3 等旧模型。
    """
    if not model_name:
        return False
    m = model_name.lower()
    return bool(re.match(r'^deepseek[-_]?(v4|chat|reasoner)', m))


def _build_thinking_params(
    model_name: str,
    thinking_level: int,
    api_format: str,
    temperature: Optional[float],
) -> tuple[dict, Optional[float], Optional[int]]:
    """
    根据模型名、思考等级、API格式，构建思考模式的额外参数。

    Returns:
        (extra_params, effective_temperature, max_tokens_override)
        - extra_params: 需要合并到 payload 的字典
        - effective_temperature: 替代原 temperature 的值（None 表示不传）
        - max_tokens_override: 如果需要覆盖 max_tokens 则返回值，否则 None
    """
    model_lower = model_name.lower() if model_name else ""

    # ── 关闭思考 ──
    if thinking_level <= 0:
        if _is_default_thinking_model(model_name):
            # 仅对已知默认开启思考的模型显式禁用
            return {"thinking": {"type": "disabled"}}, temperature, None
        return {}, temperature, None

    budget = _THINKING_BUDGETS.get(thinking_level, 8192)
    effort = _THINKING_EFFORT.get(thinking_level, "high")

    # ── Claude 原生 API ──
    if api_format == app_config.API_FORMAT_CLAUDE:
        return (
            {"thinking": {"type": "enabled", "budget_tokens": budget}},
            1.0,  # Claude 开启思考时 temperature 必须为 1
            budget + 8192,  # max_tokens 必须 > budget_tokens
        )

    # ── Gemini 原生 API ──
    if api_format == app_config.API_FORMAT_GEMINI:
        return (
            {"thinkingConfig": {"thinkingBudget": budget}},
            None,  # 思考模式下不传 temperature
            None,
        )

    # ── OpenAI 兼容格式：按模型名分发 ──
    if "deepseek" in model_lower:
        return (
            {"thinking": {"type": "enabled"}, "reasoning_effort": effort},
            None,
            None,
        )

    if "qwen" in model_lower or "qwq" in model_lower:
        return (
            {"enable_thinking": True},
            None,
            None,
        )

    # 通用 fallback（OpenAI o系列、Grok 等认识 reasoning_effort）
    return (
        {"reasoning_effort": effort},
        None,
        None,
    )


def _extract_gemini_text(parts: list) -> str:
    """从 Gemini 响应的 parts 中提取文本，过滤掉 thought parts。"""
    text_parts = [p.get("text", "") for p in parts if not p.get("thought", False)]
    return "".join(text_parts)

def _parse_api_url_and_model(
    input_base_url_str: Optional[str],
    input_model_name: Optional[str],
    default_api_base_for_v1: str = app_config.DEFAULT_LLM_API_BASE_URL,
    default_model: str = app_config.DEFAULT_LLM_MODEL_NAME,
    api_format: Optional[str] = None  # API格式参数
) -> tuple[str, str]:
    """
    解析并构建完整的 API URL
    
    优化逻辑：优先信任 api_format 参数，而不是猜测 URL
    """
    effective_model = input_model_name if input_model_name else default_model
    
    # 1. 处理空 URL 的情况
    if not input_base_url_str:
        final_url = default_api_base_for_v1
        if not final_url.endswith('/'):
            final_url += '/'
        final_url += "v1/chat/completions"
        return final_url, effective_model

    raw_url = input_base_url_str.strip()

    # 2. 处理完整 URL（以 '#' 结尾）
    if raw_url.endswith("#"):
        final_url = raw_url[:-1]  # 移除 '#' 标记
        _log_api_message(f"使用完整API路径: {final_url}", None)
        return final_url, effective_model

    # 3. 确定 API 格式（优先使用参数，其次自动检测）
    determined_format = api_format
    if determined_format == app_config.API_FORMAT_AUTO or determined_format is None:
        # 仅在 AUTO 模式下才根据域名猜测
        if "api.anthropic.com" in raw_url:
            determined_format = app_config.API_FORMAT_CLAUDE
        elif "generativelanguage.googleapis.com" in raw_url:
            determined_format = app_config.API_FORMAT_GEMINI
        else:
            # 默认使用 OpenAI 格式（兼容性最好）
            determined_format = app_config.API_FORMAT_OPENAI

    # 4. 根据格式构建 URL
    if not raw_url.endswith('/'):
        raw_url += '/'
    
    if determined_format == app_config.API_FORMAT_CLAUDE:
        # Claude: /v1/messages
        # 防御性编程：避免重复添加
        if "v1/messages" not in raw_url:
            # 如果 URL 中已有 v1/，则只添加 messages
            if "v1/" in raw_url:
                final_url = raw_url.rstrip('/').split("v1/")[0] + "v1/messages"
            else:
                final_url = raw_url + "v1/messages"
        else:
            final_url = raw_url.rstrip('/')
            
    elif determined_format == app_config.API_FORMAT_GEMINI:
        # Gemini: /v1beta/models/{model}:generateContent
        if "generateContent" not in raw_url:
            final_url = raw_url + f"v1beta/models/{effective_model}:generateContent"
        else:
            final_url = raw_url.rstrip('/')
            
    elif determined_format == app_config.API_FORMAT_OPENAI:
        # OpenAI 兼容: /v1/chat/completions
        # 标准化处理，避免重复添加
        if "chat/completions" in raw_url:
            # 已经包含完整路径
            final_url = raw_url.rstrip('/')
        elif "v1/" in raw_url or "v2/" in raw_url:
            # 包含版本号但没有 chat/completions
            final_url = raw_url + "chat/completions"
        else:
            # 纯域名，添加完整路径
            final_url = raw_url + "v1/chat/completions"
    else:
        # 未知格式，使用 OpenAI 兼容格式作为后备
        _log_api_message(f"警告: 未知的API格式 '{determined_format}'，使用OpenAI兼容格式", None)
        final_url = raw_url + "v1/chat/completions"

    return final_url, effective_model

def _test_gemini_connection(api_key: str, raw_url: str, effective_model: str, test_temperature: float, _log_test_connection) -> tuple[bool, str]:
    """
    专门的Gemini API连接测试函数
    1. 先验证API密钥有效性（通过获取模型列表）
    2. 再验证具体模型的连接性
    """
    # 验证API密钥有效性
    try:
        models_url = f"{raw_url.rstrip('/')}/v1beta/models?key={api_key}"
        response = requests.get(models_url, timeout=10)

        if response.status_code != 200:
            if response.status_code == 400:
                return False, f"API密钥无效或已过期。请检查您的Google AI Studio API密钥。"
            elif response.status_code == 403:
                return False, f"API访问被禁止。请确认已启用Generative Language API。"
            else:
                return False, f"API密钥验证失败，状态码: {response.status_code}"

        # 解析可用模型
        data = response.json()
        models = data.get("models", [])
        available_model_names = [model["name"].split("/")[-1] for model in models if "name" in model]

        # _log_test_connection(f"API密钥有效，找到 {len(available_model_names)} 个可用模型")  # 隐藏详细信息

        # 检查用户选择的模型是否可用
        if effective_model not in available_model_names:
            # 寻找相似的可用模型
            similar_models = [m for m in available_model_names if "gemini" in m.lower()]
            if similar_models:
                # 尝试使用第一个可用的Gemini模型
                test_model = similar_models[0]
                # _log_test_connection(f"选择的模型 {effective_model} 不可用，使用 {test_model} 代替测试连接")  # 隐藏详细信息
            else:
                return False, f"选择的模型 {effective_model} 不可用，且未找到其他Gemini模型。可用模型: {available_model_names[:5]}"
        else:
            test_model = effective_model

    except Exception as e:
        return False, f"验证API密钥时出错: {str(e)}"

    # 测试模型连接性
    try:
        generate_url = f"{raw_url.rstrip('/')}/v1beta/models/{test_model}:generateContent?key={api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": "Hello"}]
            }],
            "generationConfig": {
                "maxOutputTokens": 10
            }
        }
        if test_temperature is not None:
            payload["generationConfig"]["temperature"] = test_temperature

        response = requests.post(
            generate_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("candidates") and isinstance(data.get("candidates"), list) and len(data.get("candidates")) > 0:
                if effective_model != test_model:
                    return True, f"连接成功！使用模型 {test_model} 返回了响应（原选择的模型 {effective_model} 不可用）。建议更新模型选择。"
                else:
                    return True, f"连接成功！Gemini 模型 {effective_model} 返回了响应。"
            else:
                return False, f"模型 {test_model} 响应格式异常: {str(data)[:200]}"
        elif response.status_code == 400:
            return False, f"模型 {test_model} 请求格式错误。请检查模型名称是否正确。"
        elif response.status_code == 403:
            return False, f"模型 {test_model} 访问被禁止。请检查API权限。"
        else:
            return False, f"模型 {test_model} 连接失败，状态码: {response.status_code}。错误: {response.text[:200]}"

    except requests.exceptions.Timeout:
        return False, f"模型 {test_model} 连接超时。"
    except Exception as e:
        return False, f"测试模型 {test_model} 连接时出错: {str(e)}"

def _test_claude_connection(api_key: str, raw_url: str, effective_model: str, test_temperature: float, _log_test_connection) -> tuple[bool, str]:
    """
    专门的Claude API连接测试函数
    1. 先验证API密钥有效性
    2. 再验证模型连接性
    """
    # _log_test_connection("验证Claude API密钥和模型连接性...")  # 简化日志

    # Claude API端点
    target_url = f"{raw_url.rstrip('/')}/v1/messages"

    payload = {
        "model": effective_model,
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello"}]
    }
    if test_temperature is not None:
        payload["temperature"] = test_temperature

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01"
    }

    try:
        response = requests.post(target_url, headers=headers, json=payload, timeout=20)

        if response.status_code == 401:
            return False, f"Claude API密钥无效或已过期。请检查您的Anthropic API密钥。"
        elif response.status_code == 400:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", "")
            if "model" in error_message.lower():
                return False, f"Claude模型 {effective_model} 无效或不可用。请检查模型名称。错误: {error_message}"
            else:
                return False, f"Claude API请求格式错误。错误: {error_message}"
        elif response.status_code == 403:
            return False, f"Claude API访问被禁止。请检查API权限和配额。"
        elif response.status_code == 429:
            return False, f"Claude API速率限制。请稍后再试。"

        response.raise_for_status()
        data = response.json()

        # 检查Claude特有的响应格式
        if data.get("content") and isinstance(data.get("content"), list) and len(data.get("content")) > 0:
            return True, f"连接成功！Claude 模型 {effective_model} 返回了响应。"
        elif data.get("error"):
            error_msg = data.get("error", {}).get("message", "未知错误")
            return False, f"Claude API返回错误: {error_msg}"
        else:
            return False, f"Claude API响应格式异常: {str(data)[:200]}"

    except requests.exceptions.Timeout:
        return False, f"Claude API连接超时。"
    except requests.exceptions.HTTPError as e:
        error_text = e.response.text[:200] if hasattr(e, 'response') and e.response else str(e)
        return False, f"Claude API HTTP错误: {e.response.status_code if hasattr(e, 'response') else 'Unknown'}。错误: {error_text}"
    except Exception as e:
        return False, f"测试Claude API连接时出错: {str(e)}"

def _test_openai_compatible_connection(api_key: str, custom_api_base_url_str: Optional[str], effective_model: str, test_temperature: float, _log_test_connection) -> tuple[bool, str]:
    """
    专门为公益站等OpenAI兼容API的连接测试函数
    1. 先验证API端点可达性（通过获取模型列表）
    2. 再验证模型连接性
    """
    # _log_test_connection("验证OpenAI兼容API连接性...")  # 简化日志

    if not custom_api_base_url_str:
        return False, "API地址为空"

    raw_url = custom_api_base_url_str.strip()

    # 第1步：尝试获取模型列表来验证API端点
    try:
        # 构建模型列表端点
        if "/v1" in raw_url:
            if raw_url.endswith('/'):
                models_url = raw_url + "models"
            else:
                models_url = raw_url + "/models"
        else:
            models_url = raw_url.rstrip('/') + "/v1/models"

        headers = {"Authorization": f"Bearer {api_key}"}
        # _log_test_connection(f"第1步：获取模型列表，URL: {models_url}")  # 简化日志

        response = requests.get(models_url, headers=headers, timeout=10)

        if response.status_code == 401:
            return False, "API密钥无效。请检查您的API密钥。"
        elif response.status_code == 404:
            # 端点不支持模型列表，直接进行连接测试
            # _log_test_connection("API不支持模型列表获取，直接进行连接测试")  # 简化日志
            return _test_openai_compatible_direct_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)
        elif response.status_code != 200:
            # _log_test_connection(f"获取模型列表失败，状态码: {response.status_code}，直接进行连接测试")  # 简化日志
            return _test_openai_compatible_direct_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)

        # 解析可用模型
        data = response.json()
        available_models = []
        if "data" in data and isinstance(data["data"], list):
            available_models = [model["id"] for model in data["data"] if isinstance(model, dict) and "id" in model]

        # _log_test_connection(f"找到 {len(available_models)} 个可用模型")  # 简化日志

        # 检查用户选择的模型是否可用
        if effective_model not in available_models and available_models:
            # 如果选择的模型不在列表中，但列表不为空，建议使用第一个可用模型
            suggested_model = available_models[0]
            # _log_test_connection(f"选择的模型 {effective_model} 不在可用列表中，建议使用 {suggested_model}")  # 简化日志
            effective_model = suggested_model

    except requests.exceptions.RequestException as e:
        # _log_test_connection(f"获取模型列表失败，直接进行连接测试: {str(e)}")  # 简化日志
        return _test_openai_compatible_direct_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)
    except Exception as e:
        # _log_test_connection(f"解析模型列表异常，直接进行连接测试: {str(e)}")  # 简化日志
        return _test_openai_compatible_direct_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)

    return _test_openai_compatible_direct_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)

def _test_openai_compatible_direct_connection(api_key: str, raw_url: str, effective_model: str, test_temperature: float, _log_test_connection) -> tuple[bool, str]:
    """直接测试OpenAI兼容API的模型连接"""
    # _log_test_connection(f"第2步：测试模型 {effective_model} 连接性...")  # 简化日志

    # 构建聊天完成端点
    target_url, _ = _parse_api_url_and_model(
        raw_url, effective_model,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )

    payload = {"model": effective_model, "messages": [{"role": "user", "content": "Hello"}]}
    if test_temperature is not None:
        payload["temperature"] = test_temperature

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    try:
        response = requests.post(target_url, headers=headers, json=payload, timeout=20)

        if response.status_code == 401:
            return False, "API密钥无效。请检查您的API密钥。"
        elif response.status_code == 404:
            return False, f"API端点未找到。请检查API地址，可能是模型 {effective_model} 不存在。"
        elif response.status_code == 429:
            return False, "API速率限制。请稍后再试。"
        elif response.status_code >= 500:
            return False, f"API服务器错误 ({response.status_code})。请稍后再试或联系服务提供商。"

        response.raise_for_status()
        data = response.json()

        # 检查OpenAI兼容的响应格式
        if (data.get("choices") and isinstance(data["choices"], list) and len(data["choices"]) > 0 and
            isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None):
            return True, f"连接成功！模型 {effective_model} 返回了响应。"
        elif data.get("error"):
            error_msg = data.get("error", {}).get("message", "未知错误")
            return False, f"API返回错误: {error_msg}"
        else:
            return False, f"API响应格式异常: {str(data)[:200]}"

    except requests.exceptions.Timeout:
        return False, "API连接超时。"
    except requests.exceptions.HTTPError as e:
        error_text = e.response.text[:200] if hasattr(e, 'response') and e.response else str(e)
        return False, f"API HTTP错误: {e.response.status_code if hasattr(e, 'response') else 'Unknown'}。错误: {error_text}"
    except Exception as e:
        return False, f"测试API连接时出错: {str(e)}"

def _log_api_message(message: str, signals_forwarder: Optional[Any], prefix: str = "[LLM API]"):
    """辅助函数，用于将日志消息发送到信号或打印到控制台"""
    if signals_forwarder and hasattr(signals_forwarder, 'log_message') and hasattr(signals_forwarder.log_message, 'emit'):
        signals_forwarder.log_message.emit(f"{prefix} {message}")
    else:
        print(f"{prefix} {message}")

def _split_text_into_chunks(text: str, max_chars: int, signals_forwarder: Optional[Any]) -> List[str]:
    def _log_splitter(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Splitter]")

    chunks: List[str] = []
    current_pos = 0; text_len = len(text)
    if not text.strip(): _log_splitter("输入文本为空或仅包含空白，不进行分割。"); return []
    while current_pos < text_len:
        end_pos = min(current_pos + max_chars, text_len); actual_chunk_end = end_pos
        if end_pos < text_len:
            para_break = text.rfind('\n\n', current_pos, end_pos)
            if para_break != -1 and para_break > current_pos: actual_chunk_end = para_break + 2
            else:
                line_break = text.rfind('\n', current_pos, end_pos)
                if line_break != -1 and line_break > current_pos: actual_chunk_end = line_break + 1
                else:
                    search_start_for_sentence_end = max(current_pos, end_pos - max(100, int(max_chars * 0.2)))
                    best_sentence_break = -1
                    sentence_terminators = r'[。．\.！\!？\?]'; 
                    for match in re.finditer(sentence_terminators, text[search_start_for_sentence_end:end_pos]):
                        break_candidate = search_start_for_sentence_end + match.end()
                        if break_candidate > current_pos: best_sentence_break = break_candidate
                    if best_sentence_break != -1: actual_chunk_end = best_sentence_break
                    else:
                        space_break = text.rfind(' ', current_pos, end_pos)
                        if space_break != -1 and space_break > current_pos: actual_chunk_end = space_break + 1
        chunk_to_add = text[current_pos:actual_chunk_end]
        if chunk_to_add.strip(): chunks.append(chunk_to_add)
        current_pos = actual_chunk_end
    if not chunks and text.strip(): chunks.append(text)
    _log_splitter(f"文本被分割为 {len(chunks)} 块."); return chunks

def _get_summary(
    api_key: str,
    full_text: str,
    system_prompt_summary: str,
    custom_api_base_url_str: Optional[str],
    custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None,
    api_format: Optional[str] = None,  # API格式参数
    thinking_level: int = 0  # 思考模式等级
) -> Optional[str]:
    def _log_summary_api(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Summary]")

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )
    effective_summary_temperature = custom_temperature if custom_temperature is not None else 0.5

    _log_summary_api(f"向 LLM API 请求文本摘要 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_summary_temperature})...")

    # 如果 api_format 是 auto 或 None，根据 URL 自动检测实际格式
    effective_api_format = api_format
    if effective_api_format == app_config.API_FORMAT_AUTO or effective_api_format is None:
        if custom_api_base_url_str and "generativelanguage.googleapis.com" in custom_api_base_url_str:
            effective_api_format = app_config.API_FORMAT_GEMINI
        elif custom_api_base_url_str and "api.anthropic.com" in custom_api_base_url_str:
            effective_api_format = app_config.API_FORMAT_CLAUDE
        else:
            effective_api_format = app_config.API_FORMAT_OPENAI

    # 根据检测后的有效格式构建请求
    # 获取思考模式参数
    thinking_params, effective_temp_after_thinking, max_tokens_override = _build_thinking_params(
        effective_model, thinking_level, effective_api_format, effective_summary_temperature
    )

    # 摘要任务的 max_tokens（摘要输出较短，使用 8192 兜底即可）
    summary_max_tokens = min(get_max_output_tokens(effective_model), 8192)

    if effective_api_format == app_config.API_FORMAT_GEMINI:
        # Gemini API 使用不同的请求格式和认证方式
        gen_config = {"maxOutputTokens": summary_max_tokens}
        if effective_temp_after_thinking is not None:
            gen_config["temperature"] = effective_temp_after_thinking
        # 注入 Gemini 思考参数
        if "thinkingConfig" in thinking_params:
            gen_config["thinkingConfig"] = thinking_params["thinkingConfig"]
        payload = {
            "contents": [{"parts": [{"text": f"系统提示：{system_prompt_summary}\n\n用户输入：{full_text}"}]}],
            "generationConfig": gen_config
        }
        # Gemini API 使用 URL 参数传递 API key
        response = _post_json_with_retries(
            f"{target_url}?key={api_key}",
            _log_summary_api,
            "摘要请求",
            json=payload,
        )
        if response is None:
            return None
    else:
        # 其他 API 使用 OpenAI 兼容格式（包括 Claude，因为摘要任务可以用 system prompt）
        payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_summary}, {"role": "user", "content": full_text}]}

        # [FIX] Reasoning模型（GPT-5系列、o系列）需要特殊处理
        if _is_reasoning_model(effective_model):
            # 使用 max_completion_tokens 而不是 max_tokens
            payload["max_completion_tokens"] = summary_max_tokens
            # 不传 temperature，使用模型默认值
        else:
            # 传统模型使用 max_tokens 和自定义 temperature
            max_tok = max_tokens_override if max_tokens_override else summary_max_tokens
            payload["max_tokens"] = max_tok
            if effective_temp_after_thinking is not None:
                payload["temperature"] = effective_temp_after_thinking

        # 注入 OpenAI/Claude 兼容的思考参数（thinking, enable_thinking, reasoning_effort 等）
        for k, v in thinking_params.items():
            if k != "thinkingConfig":  # thinkingConfig 仅用于 Gemini
                payload[k] = v

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        response = _post_json_with_retries(
            target_url,
            _log_summary_api,
            "摘要请求",
            headers=headers,
            json=payload,
        )
        if response is None:
            return None

    try:
        response.raise_for_status(); data = response.json()
        content = None; finish_reason = "unknown"
        if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
           isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
            choice = data["choices"][0]; content = choice.get("message", {}).get("content"); finish_reason = choice.get("finish_reason", "unknown")
        elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
             isinstance(data["candidates"][0], dict) and \
             data["candidates"][0].get("content", {}).get("parts") and \
             isinstance(data["candidates"][0].get("content").get("parts"), list) and \
             len(data["candidates"][0].get("content").get("parts")) > 0:
            parts = data["candidates"][0]["content"]["parts"]
            content = _extract_gemini_text(parts); finish_reason = data["candidates"][0].get("finishReason", "unknown")

        if content is not None:
            _log_summary_api(f"摘要获取成功。完成原因: {finish_reason}")
            if finish_reason == "MAX_TOKENS" or finish_reason == "length":
                _log_summary_api(f"警告: 摘要输出可能因达到API的默认max_tokens限制而被截断。")
            return content.strip()
        else:
            error_info = data.get('error', {});
            if not error_info and data.get("code") and data.get("message"): error_info = data
            error_msg = error_info.get('message', str(data))
            _log_summary_api(f"错误: LLM API 对摘要请求的响应中内容为空或格式不符。完成原因: {finish_reason}, 响应数据: {str(data)[:500]}")
    except requests.exceptions.Timeout: _log_summary_api(f"错误: LLM API 对摘要请求超时 (180秒)。URL: {target_url}"); return None
    except requests.exceptions.RequestException as e: 
        status_code = e.response.status_code if e.response is not None else 'N/A'
        _log_summary_api(f"错误: LLM API 对摘要请求失败 (状态码: {status_code}) URL: {target_url}: {e}"); return None
    except Exception as e: _log_summary_api(f"错误: 处理 LLM API 对摘要请求的响应时发生未知错误 (URL: {target_url}): {e}"); _log_summary_api(traceback.format_exc()); return None
    return None

def call_llm_api_for_segmentation(
    api_key: str, text_to_segment: str,
    custom_api_base_url_str: Optional[str], custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None, target_language: Optional[str] = None,
    api_format: Optional[str] = None,  # API格式参数
    thinking_level: int = 0,  # 思考模式等级
    is_multi_speaker: bool = False  # 多说话人标记
) -> Optional[List[str]]:
    def _log_main_api(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Main]")

    def is_running() -> bool:
        if signals_forwarder and hasattr(signals_forwarder, 'parent') and hasattr(signals_forwarder.parent(), 'is_running'):
            return signals_forwarder.parent().is_running
        return True
    if not is_running(): _log_main_api("API调用前任务已取消。"); return None

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME,
        api_format
    )
    effective_temperature = custom_temperature if custom_temperature is not None else app_config.DEFAULT_LLM_TEMPERATURE

    # 如果 api_format 是 auto，根据 URL 自动检测实际格式
    effective_api_format = api_format
    if effective_api_format == app_config.API_FORMAT_AUTO or effective_api_format is None:
        if custom_api_base_url_str and "generativelanguage.googleapis.com" in custom_api_base_url_str:
            effective_api_format = app_config.API_FORMAT_GEMINI
        elif custom_api_base_url_str and "api.anthropic.com" in custom_api_base_url_str:
            effective_api_format = app_config.API_FORMAT_CLAUDE
        else:
            effective_api_format = app_config.API_FORMAT_OPENAI

    detected_lang_code_for_prompt = None
    # 1. 优先使用明确传入的目标语言 (来自ASR或用户选择)
    if target_language and target_language in ['zh', 'ja', 'en', 'ko']: # 增加了 ko
        detected_lang_code_for_prompt = target_language
    else:
        # 2. 尝试自动检测
        try:
            if text_to_segment.strip():
                detected_lang_raw = detect(text_to_segment)
                if detected_lang_raw.startswith('zh'): detected_lang_code_for_prompt = 'zh'
                elif detected_lang_raw == 'ja': detected_lang_code_for_prompt = 'ja'
                elif detected_lang_raw == 'en': detected_lang_code_for_prompt = 'en'
                elif detected_lang_raw == 'ko': detected_lang_code_for_prompt = 'ko' # 增加韩语检测
        except Exception:
            pass

    # 3. 选择分割用的系统提示词
    # 默认改为 UNIVERSAL，而不是 EN
    system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_UNIVERSAL

    if detected_lang_code_for_prompt == 'ja':
        system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_JA
    elif detected_lang_code_for_prompt == 'zh':
        system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_ZH
    elif detected_lang_code_for_prompt == 'en':
        system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_EN
    elif detected_lang_code_for_prompt == 'ko': # 增加韩语逻辑
        system_prompt_segmentation = app_config.DEEPSEEK_SYSTEM_PROMPT_KO

    # 3.5 多说话人时追加提醒，让 LLM 不要合并不同说话人的台词
    if is_multi_speaker:
        if detected_lang_code_for_prompt == 'ja':
            system_prompt_segmentation += (
                "\n\n【多人说话注意】\n"
                "本段音频包含多人说话。切勿将不同说话人的台词合并到同一行。\n"
                "例如：「ありがとう。」和「こちらこそ。」如果分别是不同人说的，必须各自成行。"
            )
        else:
            system_prompt_segmentation += (
                "\n\n[Multiple speakers]\n"
                "This audio contains multiple speakers. Never merge different speakers' lines into one segment.\n"
                'For example, "Thank you." and "You\'re welcome." from different speakers must remain separate lines.'
            )
        _log_main_api("已注入多人说话提醒到分割提示词")

    # 4. 选择摘要用的系统提示词
    # 默认改为 UNIVERSAL
    system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_UNIVERSAL

    if detected_lang_code_for_prompt == 'ja':
        system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_JA
    elif detected_lang_code_for_prompt == 'zh':
        system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_ZH
    elif detected_lang_code_for_prompt == 'en':
        system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN
    elif detected_lang_code_for_prompt == 'ko': # 增加韩语逻辑
        system_prompt_summary_task = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_KO

    _log_main_api(f"分割任务选用的系统提示词语言: {detected_lang_code_for_prompt or 'Universal (Auto)'}")

    summary_text = ""
    if text_to_segment.strip():
        _log_main_api("尝试获取全文摘要...")
        summary_text_optional = _get_summary(
            api_key, text_to_segment, system_prompt_summary_task,
            custom_api_base_url_str, custom_model_name, effective_temperature,
            signals_forwarder=signals_forwarder,
            api_format=effective_api_format,  # 传递检测后的有效格式
            thinking_level=thinking_level
        )
        if summary_text_optional: summary_text = summary_text_optional; _log_main_api("成功获取到摘要。")
        else: _log_main_api("未能获取到摘要，将不带摘要继续进行分割。")
    else: _log_main_api("输入文本为空，跳过摘要获取。")

    all_segments: List[str] = []
    text_chunks = _split_text_into_chunks(text_to_segment, MAX_CHARS_PER_CHUNK, signals_forwarder)
    num_chunks = len(text_chunks)
    if num_chunks == 0: 
        if text_to_segment.strip(): text_chunks = [text_to_segment]; num_chunks = 1
        else: return []

    stats = {
        "direct_success": 0,
        "retry_success": 0,
        "split_recovery": 0,
        "fallback": 0,
    }

    def _parse_segments_from_response(data: dict, chunk_label: str) -> tuple[Optional[List[str]], str, str]:
        content = None
        finish_reason = "unknown"
        if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
           isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
            choice = data["choices"][0]
            content = choice.get("message", {}).get("content")
            finish_reason = choice.get("finish_reason", "unknown")
        elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
             isinstance(data["candidates"][0], dict) and \
             data["candidates"][0].get("content", {}).get("parts") and \
             isinstance(data["candidates"][0].get("content").get("parts"), list) and \
             len(data["candidates"][0].get("content").get("parts")) > 0:
            parts = data["candidates"][0]["content"]["parts"]
            content = _extract_gemini_text(parts)
            finish_reason = data["candidates"][0].get("finishReason", "unknown")

        if content is None or not content.strip():
            error_info = data.get('error', {})
            if not error_info and data.get("code") and data.get("message"):
                error_info = data
            error_type = error_info.get('type', error_info.get("status"))
            error_code_val = error_info.get('code')
            reason = f"响应内容为空或格式不符。类型: {error_type}, Code: {error_code_val}, 响应: {str(data)[:500]}"
            return None, finish_reason, reason

        raw_segments = [seg.strip() for seg in content.split('\n') if seg.strip()]
        if raw_segments:
            _log_main_api(f"{chunk_label} 成功获得 {len(raw_segments)} 个文本片段")
        preprocessed_segments = _preprocess_bracket_mixed_segments(raw_segments, _log_main_api)
        segments_from_chunk = _validate_and_fix_segments(preprocessed_segments, _log_main_api)
        if not segments_from_chunk:
            return None, finish_reason, "LLM 返回内容经清理后没有有效片段"
        return segments_from_chunk, finish_reason, ""

    def _segment_chunk_once(chunk: str, chunk_label: str) -> tuple[List[str], bool, str, bool]:
        user_content_with_summary = f"【全文摘要】:\n{summary_text}\n\n【当前文本块】:\n{chunk}" if summary_text else f"【当前文本块】:\n{chunk}"

        thinking_params, effective_temp_after_thinking, max_tokens_override = _build_thinking_params(
            effective_model, thinking_level, effective_api_format, effective_temperature
        )
        model_max_tokens = min(get_max_output_tokens(effective_model), 16384)

        try:
            if effective_api_format == app_config.API_FORMAT_GEMINI:
                gen_config = {"maxOutputTokens": model_max_tokens}
                if effective_temp_after_thinking is not None:
                    gen_config["temperature"] = effective_temp_after_thinking
                if "thinkingConfig" in thinking_params:
                    gen_config["thinkingConfig"] = thinking_params["thinkingConfig"]
                payload = {
                    "contents": [{"parts": [{"text": f"系统提示：{system_prompt_segmentation}\n\n用户输入：{user_content_with_summary}"}]}],
                    "generationConfig": gen_config
                }
                response = _post_json_with_retries(
                    f"{target_url}?key={api_key}", _log_main_api, chunk_label,
                    is_running_func=is_running, json=payload
                )
            elif effective_api_format == app_config.API_FORMAT_CLAUDE:
                max_tok = max_tokens_override if max_tokens_override else model_max_tokens
                payload = {
                    "model": effective_model,
                    "max_tokens": max_tok,
                    "messages": [{"role": "user", "content": f"系统提示：{system_prompt_segmentation}\n\n用户输入：{user_content_with_summary}"}]
                }
                if effective_temp_after_thinking is not None:
                    payload["temperature"] = effective_temp_after_thinking
                for k, v in thinking_params.items():
                    payload[k] = v
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01"
                }
                response = _post_json_with_retries(
                    target_url, _log_main_api, chunk_label,
                    is_running_func=is_running, headers=headers, json=payload
                )
            else:
                payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_segmentation}, {"role": "user", "content": user_content_with_summary}]}
                if _is_reasoning_model(effective_model):
                    payload["max_completion_tokens"] = model_max_tokens
                else:
                    max_tok = max_tokens_override if max_tokens_override else model_max_tokens
                    payload["max_tokens"] = max_tok
                    if effective_temp_after_thinking is not None:
                        payload["temperature"] = effective_temp_after_thinking
                for k, v in thinking_params.items():
                    if k != "thinkingConfig":
                        payload[k] = v
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                response = _post_json_with_retries(
                    target_url, _log_main_api, chunk_label,
                    is_running_func=is_running, headers=headers, json=payload
                )

            if response is None:
                return [], False, "请求未返回响应", False
            if not is_running():
                return [], False, "任务已取消", False

            retried = getattr(response, "_llm_retry_attempt", 1) > 1
            response.raise_for_status()
            data = response.json()
            if not is_running():
                return [], False, "任务已取消", retried

            segments_from_chunk, finish_reason, reason = _parse_segments_from_response(data, chunk_label)
            if segments_from_chunk is None:
                _log_main_api(f"错误: LLM API 对 {chunk_label} 的响应无有效片段: {reason}")
                return [], False, reason, retried
            _log_main_api(f"{chunk_label} 修正后获得 {len(segments_from_chunk)} 个片段。完成原因: {finish_reason}")
            if finish_reason == "length" or finish_reason == "MAX_TOKENS":
                _log_main_api(f"警告: {chunk_label} 的输出可能因为达到API的默认max_tokens限制而被截断。")
            return segments_from_chunk, True, finish_reason, retried

        except requests.exceptions.RequestException as e:
            error_details = ""
            status_code = 'N/A'
            if e.response is not None:
                status_code = e.response.status_code
                try:
                    err_json_data = e.response.json()
                    err_info_openai = err_json_data.get('error', {})
                    err_info_gemini = err_json_data if "message" in err_json_data and "code" in err_json_data else {}
                    message = err_info_openai.get('message', err_info_gemini.get('message', e.response.text))
                    err_type = err_info_openai.get('type', err_info_gemini.get('status', 'UnknownType'))
                    err_code = err_info_openai.get('code', err_info_gemini.get('code', 'UnknownCode'))
                    error_details = f": [{err_type}/{err_code}] {message}"
                except requests.exceptions.JSONDecodeError:
                    error_details = f": {e.response.text[:200]}"
            else:
                error_details = f": {str(e)}"
            reason = f"请求失败 (状态码: {status_code}, URL: {target_url}){error_details}"
            _log_main_api(f"错误: LLM API 对 {chunk_label} 的{reason}")
            return [], False, reason, False
        except Exception as e:
            reason = f"处理响应时发生未知错误 (URL: {target_url}): {e}"
            _log_main_api(f"错误: LLM API 对 {chunk_label} 的{reason}")
            _log_main_api(traceback.format_exc())
            return [], False, reason, False

    def _recover_chunk(chunk: str, chunk_label: str) -> List[str]:
        segments, ok, reason, retried = _segment_chunk_once(chunk, chunk_label)
        if ok:
            if retried:
                stats["retry_success"] += 1
            else:
                stats["direct_success"] += 1
            return segments

        if not is_running():
            return []

        if len(chunk) > LLM_SPLIT_RETRY_CHARS:
            _log_main_api(f"{chunk_label} 多次请求后仍失败，尝试切成更小文本块重新处理。原因: {reason}")
            sub_chunks = _split_text_into_chunks(chunk, LLM_SPLIT_RETRY_CHARS, signals_forwarder)
            if sub_chunks and len(sub_chunks) > 1:
                recovered: List[str] = []
                used_split = False
                for sub_idx, sub_chunk in enumerate(sub_chunks):
                    if not is_running():
                        return recovered
                    sub_label = f"{chunk_label}-{sub_idx + 1}/{len(sub_chunks)}"
                    sub_segments, sub_ok, sub_reason, _sub_retried = _segment_chunk_once(sub_chunk, sub_label)
                    if sub_ok:
                        used_split = True
                        recovered.extend(sub_segments)
                    else:
                        _log_main_api(f"{sub_label} 仍失败，使用本地规则兜底。原因: {sub_reason}")
                        fallback = _fallback_segment_text_locally(sub_chunk, _log_main_api)
                        stats["fallback"] += 1
                        recovered.extend(fallback)
                if used_split:
                    stats["split_recovery"] += 1
                return recovered

        _log_main_api(f"{chunk_label} 使用本地规则兜底，避免该段文本丢失。原因: {reason}")
        stats["fallback"] += 1
        return _fallback_segment_text_locally(chunk, _log_main_api)

    for i, chunk in enumerate(text_chunks):
        if not is_running():
            _log_main_api(f"处理块 {i+1}/{num_chunks} 前任务已取消。")
            return all_segments if all_segments else None
        _log_main_api(f"向 LLM API 发送块 {i+1}/{num_chunks} 进行分割 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_temperature})...")
        all_segments.extend(_recover_chunk(chunk, f"块 {i+1}/{num_chunks}"))
        if signals_forwarder and hasattr(signals_forwarder, 'llm_progress_signal') and hasattr(signals_forwarder.llm_progress_signal, 'emit'):
             signals_forwarder.llm_progress_signal.emit(int(((i + 1) / num_chunks) * 100))
        if num_chunks > 1 and i < num_chunks - 1:
            if not is_running():
                _log_main_api(f"处理完块 {i+1}/{num_chunks} 后任务已取消，不再延时。")
                return all_segments if all_segments else None
            time.sleep(0.5)
    if not all_segments and text_to_segment.strip():
        _log_main_api("所有块处理完毕，但未能从任何块中获取到有效的分割结果。")
        return None
    _log_main_api(
        f"LLM分割统计: 原始块={num_chunks}, 直接成功={stats['direct_success']}, "
        f"重试恢复={stats['retry_success']}, 拆分恢复={stats['split_recovery']}, "
        f"本地兜底={stats['fallback']}, 输出片段={len(all_segments)}"
    )
    _log_main_api(f"所有 {num_chunks} 个块处理完成。总共收集到 {len(all_segments)} 个片段。")
    return all_segments

# --- 测试连接函数 ---
def _preprocess_bracket_mixed_segments(segments: List[str], logger_func) -> List[str]:
    """
    预处理LLM分割结果，检测并修正括号内容混合的分割

    处理模式：
    - "(a)xxx(b)" -> "(a)", "xxx", "(b)"
    - "xxx(a)yyy" -> "xxx", "(a)", "yyy"
    - "(a)xxx" -> "(a)", "xxx"
    - "xxx(a)" -> "xxx", "(a)"

    Args:
        segments: LLM分割后的文本段落列表
        logger_func: 日志记录函数

    Returns:
        预处理后的文本段落列表
    """
    processed_segments = []

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # 检测括号内容混合的模式
        # 支持多种括号类型: (), （）, 【】, [], {}, <>
        bracket_patterns = [
            r'^([（\(【\[\{<][^）\)\】\]\}>]*[）\)】\]\}>])(.+)$',  # (a)xxx
            r'^(.+)([（\(【\[\{<][^）\)\】\]\}>]*[）\)】\]\}>])$',  # xxx(a)
            r'^([（\(【\[\{<][^）\)\】\]\}>]*[）\)】\]\}>])(.+)([（\(【\[\{<][^）\)\】\]\}>]*[）\)】\]\}>])$',  # (a)xxx(b)
        ]

        found_pattern = False
        pattern_matches = []

        # 检查各种模式
        for i, pattern in enumerate(bracket_patterns):
            match = re.match(pattern, segment)
            if match:
                pattern_matches = match.groups()
                found_pattern = True
                break

        if found_pattern and len(pattern_matches) >= 2:
            # 有括号混合，需要分离
            if len(pattern_matches) == 2:
                # (a)xxx 或 xxx(a) 模式
                part1, part2 = pattern_matches
                part1 = part1.strip()
                part2 = part2.strip()

                if part1: processed_segments.append(part1)
                if part2: processed_segments.append(part2)

            elif len(pattern_matches) == 3:
                # (a)xxx(b) 模式
                part1, middle, part3 = pattern_matches
                part1 = part1.strip()
                middle = middle.strip()
                part3 = part3.strip()

                if part1: processed_segments.append(part1)
                if middle: processed_segments.append(middle)
                if part3: processed_segments.append(part3)

            logger_func(f"文本片段优化: 自动分离混合内容")
        else:
            # 没有括号混合，直接添加
            processed_segments.append(segment)

    # 统计变化
    if len(processed_segments) != len(segments):
        logger_func(f"文本片段优化完成: {len(segments)} -> {len(processed_segments)} 个段落")

    return processed_segments


def _validate_and_fix_segments(segments: List[str], logger_func) -> List[str]:
    """
    验证并修正LLM分割结果，确保连续的括号内容被正确分离

    Args:
        segments: LLM分割后的文本段落列表
        logger_func: 日志记录函数

    Returns:
        修正后的文本段落列表
    """
    fixed_segments = []

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # 检查是否包含连续的括号内容
        # 支持多种括号类型: (), （）, 【】, [], {}, <>
        bracket_patterns = [
            r'([（\(][^）\)]*[）\)])([（\(][^）\)]*[）\)])+',  # 连续的全角或半角圆括号
            r'(【[^】]*】)(【[^】]*】)+',  # 连续的方头括号
            r'(\[[^\]]*\])(\[[^\]]*\])+',  # 连续的方括号
            r'(\{[^}]*\})(\{[^}]*\})+',  # 连续的花括号
            r'(<[^>]*>)(<[^>]*>)+',  # 连续的尖括号
        ]

        needs_splitting = False
        for pattern in bracket_patterns:
            if re.search(pattern, segment):
                needs_splitting = True
                break

        if needs_splitting:
            # 使用正则表达式分离连续的括号内容
            split_pattern = r'([^(（\【\[\{<]*?)([（\(][^）\)]*[）\)]|[【][^】]*[】]|[[][^\]]*[\]]|[{][^}]*[}]|[<][^>]*[>])'
            matches = re.findall(split_pattern, segment)

            if matches:
                for match in matches:
                    text_part = match[0].strip()
                    bracket_part = match[1].strip()
                    if text_part: fixed_segments.append(text_part)
                    if bracket_part: fixed_segments.append(bracket_part)
            else:
                # 备用分割方法
                simple_split_pattern = r'(?<=[）\)】\]\}>)(?=[（\(【\[\{<])'
                parts = re.split(simple_split_pattern, segment)
                for part in parts:
                    part = part.strip()
                    if part: fixed_segments.append(part)
        else:
            fixed_segments.append(segment)

    if len(fixed_segments) != len(segments):
        logger_func(f"连续括号内容分离完成: {len(segments)} -> {len(fixed_segments)} 个段落")

    return fixed_segments


def test_llm_connection(
    api_key: str,
    custom_api_base_url_str: Optional[str],
    custom_model_name: Optional[str],
    custom_temperature: Optional[float],
    signals_forwarder: Optional[Any] = None,
    api_format: Optional[str] = None  # 新增：API格式参数
) -> tuple[bool, str]:
    def _log_test_connection(message: str):
        # 简化日志输出，只输出重要信息
        if not message.startswith("第") and "DEBUG" not in message and "URL=" not in message:
            _log_api_message(message, signals_forwarder, prefix="[LLM API - Test Connection]")

    raw_url = custom_api_base_url_str.strip() if custom_api_base_url_str else ""
    effective_model = custom_model_name if custom_model_name else app_config.DEFAULT_LLM_MODEL_NAME
    test_temperature = custom_temperature if custom_temperature is not None else app_config.DEFAULT_LLM_TEMPERATURE

    # 输出测试开始信息
    _log_test_connection("开始测试LLM连接...")

    # 确定 API 格式（优先使用参数，其次自动检测）
    determined_format = api_format
    if determined_format == app_config.API_FORMAT_AUTO or determined_format is None:
        # 仅在 AUTO 模式下才根据域名猜测
        if "api.anthropic.com" in raw_url:
            determined_format = app_config.API_FORMAT_CLAUDE
        elif "generativelanguage.googleapis.com" in raw_url:
            determined_format = app_config.API_FORMAT_GEMINI
        else:
            # 默认使用 OpenAI 格式（兼容性最好）
            determined_format = app_config.API_FORMAT_OPENAI

    # 根据API格式选择测试方法
    if determined_format == app_config.API_FORMAT_CLAUDE:
        # Claude API - 使用专门的连接测试函数
        return _test_claude_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)
    elif determined_format == app_config.API_FORMAT_GEMINI:
        # Gemini API - 先验证API密钥，再验证模型
        return _test_gemini_connection(api_key, raw_url, effective_model, test_temperature, _log_test_connection)
    else:
        # OpenAI 兼容 API（包括 AUTO 模式默认）
        return _test_openai_compatible_connection(api_key, custom_api_base_url_str, effective_model, test_temperature, _log_test_connection)
