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

from langdetect import detect

# 默认系统提示词配置
DEFAULT_SYSTEM_PROMPT_FOR_SEGMENTATION = app_config.DEEPSEEK_SYSTEM_PROMPT_EN
DEFAULT_SYSTEM_PROMPT_FOR_SUMMARY = app_config.DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN

# 文本分块处理的最大字符数
MAX_CHARS_PER_CHUNK = 2800


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
    signals_forwarder: Optional[Any] = None
) -> Optional[str]:
    def _log_summary_api(message: str):
        _log_api_message(message, signals_forwarder, prefix="[LLM API - Summary]")

    target_url, effective_model = _parse_api_url_and_model(
        custom_api_base_url_str, custom_model_name,
        app_config.DEFAULT_LLM_API_BASE_URL, app_config.DEFAULT_LLM_MODEL_NAME
    )
    effective_summary_temperature = custom_temperature if custom_temperature is not None else 0.5

    _log_summary_api(f"向 LLM API 请求文本摘要 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_summary_temperature})...")

    # [FIX] 根据 API 格式构建请求 - 优先信任 api_format 参数
    # 注意：_get_summary 目前没有接收 api_format 参数，需要从 URL 推断或添加参数
    # 临时方案：通过 URL 判断，但优先级低于显式的 api_format
    if "generativelanguage.googleapis.com" in target_url:
        # Gemini API 使用不同的请求格式和认证方式
        payload = {
            "contents": [{"parts": [{"text": f"系统提示：{system_prompt_summary}\n\n用户输入：{full_text}"}]}],
            "generationConfig": {
                "temperature": effective_summary_temperature,
                "maxOutputTokens": 8192
            }
        }
        # Gemini API 使用 URL 参数传递 API key
        response = requests.post(f"{target_url}?key={api_key}", json=payload, timeout=180)
    else:
        # 其他 API 使用 OpenAI 兼容格式（包括 Claude，因为摘要任务可以用 system prompt）
        payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_summary}, {"role": "user", "content": full_text}]}
        if custom_temperature is not None: payload["temperature"] = effective_summary_temperature

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        response = requests.post(target_url, headers=headers, json=payload, timeout=180)

    try:
        response.raise_for_status(); data = response.json()
        content = None; finish_reason = "unknown"
        if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
           isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
            choice = data["choices"][0]; content = choice.get("message", {}).get("content"); finish_reason = choice.get("finish_reason", "unknown")
        elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
             isinstance(data["candidates"][0], dict) and \
             data["candidates"][0].get("content", {}).get("parts", [{}]) and \
             isinstance(data["candidates"][0].get("content").get("parts"), list) and \
             len(data["candidates"][0].get("content").get("parts")) > 0 and \
             isinstance(data["candidates"][0].get("content").get("parts")[0], dict) and \
             data["candidates"][0].get("content").get("parts")[0].get("text") is not None:
            content = data["candidates"][0].get("content").get("parts")[0].get("text"); finish_reason = data["candidates"][0].get("finishReason", "unknown")

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
    api_format: Optional[str] = None  # 新增：API格式参数
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
            signals_forwarder=signals_forwarder
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

    for i, chunk in enumerate(text_chunks):
        if not is_running(): _log_main_api(f"处理块 {i+1}/{num_chunks} 前任务已取消。"); return all_segments if all_segments else None 
        _log_main_api(f"向 LLM API 发送块 {i+1}/{num_chunks} 进行分割 (URL: {target_url}, 模型: {effective_model}, 温度: {effective_temperature})...")
        
        user_content_with_summary = f"【全文摘要】:\n{summary_text}\n\n【当前文本块】:\n{chunk}"
        if not summary_text: user_content_with_summary = f"【当前文本块】:\n{chunk}"

        # [FIX] 根据 API 格式构建请求 - 优先信任 api_format 参数而不是域名猜测
        # 这样可以正确支持 Gemini/Claude 的反向代理
        if api_format == app_config.API_FORMAT_GEMINI:
            # Gemini API 使用不同的请求格式和认证方式
            payload = {
                "contents": [{"parts": [{"text": f"系统提示：{system_prompt_segmentation}\n\n用户输入：{user_content_with_summary}"}]}],
                "generationConfig": {
                    "temperature": effective_temperature,
                    "maxOutputTokens": 8192
                }
            }
            # Gemini API 使用 URL 参数传递 API key（即使是代理也要这样）
            response = requests.post(f"{target_url}?key={api_key}", json=payload, timeout=180)
        elif api_format == app_config.API_FORMAT_CLAUDE:
            # Claude API 使用 /v1/messages 格式
            payload = {
                "model": effective_model,
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": f"系统提示：{system_prompt_segmentation}\n\n用户输入：{user_content_with_summary}"}]
            }
            if custom_temperature is not None: payload["temperature"] = effective_temperature

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": "2023-06-01"
            }
            response = requests.post(target_url, headers=headers, json=payload, timeout=180)
        else:
            # OpenAI 兼容格式 (默认格式，包括 AUTO 模式)
            payload = {"model": effective_model, "messages": [{"role": "system", "content": system_prompt_segmentation}, {"role": "user", "content": user_content_with_summary }]}
            if custom_temperature is not None: payload["temperature"] = effective_temperature

            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            response = requests.post(target_url, headers=headers, json=payload, timeout=180)

        try:
            if not is_running(): _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应接收后任务已取消。"); return all_segments if all_segments else None
            response.raise_for_status(); data = response.json()
            if not is_running(): _log_main_api(f"API 对块 {i+1}/{num_chunks} 响应解析后任务已取消。"); return all_segments if all_segments else None
            content = None; finish_reason = "unknown"
            if "choices" in data and data["choices"] and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
               isinstance(data["choices"][0], dict) and data["choices"][0].get("message", {}).get("content") is not None:
                choice = data["choices"][0]; content = choice.get("message", {}).get("content"); finish_reason = choice.get("finish_reason", "unknown")
            elif data.get("candidates") and isinstance(data["candidates"], list) and len(data["candidates"]) > 0 and \
                 isinstance(data["candidates"][0], dict) and \
                 data["candidates"][0].get("content", {}).get("parts", [{}]) and \
                 isinstance(data["candidates"][0].get("content").get("parts"), list) and \
                 len(data["candidates"][0].get("content").get("parts")) > 0 and \
                 isinstance(data["candidates"][0].get("content").get("parts")[0], dict) and \
                 data["candidates"][0].get("content").get("parts")[0].get("text") is not None:
                content = data["candidates"][0].get("content").get("parts")[0].get("text"); finish_reason = data["candidates"][0].get("finishReason", "unknown")

            if content is not None:
                raw_segments = [seg.strip() for seg in content.split('\n') if seg.strip()]
                segments_from_chunk = []

                # 处理分割结果
                if len(raw_segments) > 0:
                    _log_main_api(f"块 {i+1}/{num_chunks} 成功获得 {len(raw_segments)} 个文本片段")

                # 预处理：检测并修正括号内容混合的分割
                preprocessed_segments = _preprocess_bracket_mixed_segments(raw_segments, _log_main_api)

                # 验证并可能修正分割结果
                segments_from_chunk = _validate_and_fix_segments(preprocessed_segments, _log_main_api)

                all_segments.extend(segments_from_chunk)
                _log_main_api(f"块 {i+1}/{num_chunks} 修正后获得 {len(segments_from_chunk)} 个片段。完成原因: {finish_reason}")
                if finish_reason == "length" or finish_reason == "MAX_TOKENS":
                    _log_main_api(f"警告: 块 {i+1}/{num_chunks} 的输出可能因为达到API的默认max_tokens限制而被截断。")
            else: 
                error_info = data.get('error', {}); 
                if not error_info and data.get("code") and data.get("message"): error_info = data 
                error_msg = error_info.get('message', str(data)); error_type = error_info.get('type', error_info.get("status")); error_code_val = error_info.get('code')
                _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的响应格式错误或API返回错误。类型: {error_type}, Code: {error_code_val}, 消息: {str(data)[:500]}")
        except requests.exceptions.Timeout: _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的请求超时 (180秒)。URL: {target_url}")
        except requests.exceptions.RequestException as e: 
            error_details = ""; status_code = 'N/A'
            if e.response is not None:
                status_code = e.response.status_code
                try: 
                    err_json_data = e.response.json(); err_info_openai = err_json_data.get('error', {}); err_info_gemini = err_json_data if "message" in err_json_data and "code" in err_json_data else {}
                    message = err_info_openai.get('message', err_info_gemini.get('message', e.response.text)); err_type = err_info_openai.get('type', err_info_gemini.get('status', 'UnknownType')); err_code = err_info_openai.get('code', err_info_gemini.get('code', 'UnknownCode'))
                    error_details = f": [{err_type}/{err_code}] {message}"
                except requests.exceptions.JSONDecodeError: error_details = f": {e.response.text[:200]}"
            else: error_details = f": {str(e)}"
            _log_main_api(f"错误: LLM API 对块 {i+1}/{num_chunks} 的请求失败 (状态码: {status_code}, URL: {target_url}){error_details}")
        except Exception as e: _log_main_api(f"错误: 处理 LLM API 对块 {i+1}/{num_chunks} 的响应时发生未知错误 (URL: {target_url}): {e}"); _log_main_api(traceback.format_exc())
        if signals_forwarder and hasattr(signals_forwarder, 'llm_progress_signal') and hasattr(signals_forwarder.llm_progress_signal, 'emit'):
             signals_forwarder.llm_progress_signal.emit(int(((i + 1) / num_chunks) * 100))
        if num_chunks > 1 and i < num_chunks - 1:
            if not is_running(): _log_main_api(f"处理完块 {i+1}/{num_chunks} 后任务已取消，不再延时。"); return all_segments if all_segments else None
            time.sleep(0.5)
    if not all_segments and text_to_segment.strip(): _log_main_api("所有块处理完毕，但未能从任何块中获取到有效的分割结果。"); return None 
    _log_main_api(f"所有 {num_chunks} 个块处理完成。总共收集到 {len(all_segments)} 个片段。"); return all_segments

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
