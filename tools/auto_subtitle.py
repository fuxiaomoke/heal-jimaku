#!/usr/bin/env python3
"""
自动字幕生成工具 - 命令行版本

独立的命令行工具，实现视频自动生成字幕的完整流程：
1. 视频音频提取 → OGG 编码 → 28分钟分割
2. ElevenLabs Web 批量转录 → JSON 合并
3. LLM 优化 → SRT 生成

使用示例:
    python tools/auto_subtitle.py video.mp4
    python tools/auto_subtitle.py video.mp4 --language ja
    python tools/auto_subtitle.py video.mp4 --llm-api-key sk-xxx

作者: fuxiaomoke
版本: 0.2.2.0
"""

import sys
import os
import argparse
import json

# 添加项目根目录和 src 目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 从 src 导入配置模块
import config as app_config

# 从 tools.core 导入字幕生成流程
from tools.core.subtitle_pipeline import SubtitlePipeline


def load_config():
    """加载配置文件（复用 GUI 的配置）"""
    if not os.path.exists(app_config.CONFIG_FILE):
        return {}
    
    try:
        with open(app_config.CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"警告: 加载配置文件失败: {e}")
        return {}


def save_config(config_data):
    """保存配置文件"""
    try:
        if not os.path.exists(app_config.CONFIG_DIR):
            os.makedirs(app_config.CONFIG_DIR, exist_ok=True)
        
        with open(app_config.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告: 保存配置文件失败: {e}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='视频自动生成字幕工具（复用 GUI 配置）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本使用（使用已保存的配置）
  python tools/auto_subtitle.py video.mp4

  # 指定语言
  python tools/auto_subtitle.py video.mp4 --language ja

  # 使用 ElevenLabs API Key（推荐）
  python tools/auto_subtitle.py video.mp4 --elevenlabs-api-key YOUR_KEY

  # 完整配置示例
  python tools/auto_subtitle.py video.mp4 \\
    --llm-api-key sk-xxx \\
    --elevenlabs-api-key el-xxx \\
    --language ja

支持的语言: zh (中文), ja (日文), en (英文), ko (韩文)

注意: 
  - 工具会自动读取 GUI 保存的配置（~/.heal_jimaku/config/config.json）
  - ElevenLabs 免费版已失效，建议使用 API Key
        """
    )
    
    # 必需参数
    parser.add_argument(
        'video',
        help='视频文件路径（支持 mp4, mkv, avi, webm 等格式）'
    )
    
    parser.add_argument(
        '--llm-api-key',
        help='LLM API Key（可选，不指定则使用配置文件中的）'
    )
    
    parser.add_argument(
        '--elevenlabs-api-key',
        help='ElevenLabs API Key（用于音频转录，可选）'
    )
    
    # 可选参数
    parser.add_argument(
        '--api-url',
        default='https://api.deepseek.com/v1/chat/completions',
        help='LLM API 地址（默认: DeepSeek）'
    )
    
    parser.add_argument(
        '--model',
        default='deepseek-chat',
        help='LLM 模型名称（默认: deepseek-chat）'
    )
    
    parser.add_argument(
        '--language',
        choices=['zh', 'ja', 'en', 'ko'],
        help='目标语言（可选，不指定则自动检测）'
    )
    
    parser.add_argument(
        '--max-duration',
        type=int,
        default=1680,
        help='音频分割最大时长（秒，默认: 1680 = 28分钟）'
    )
    
    parser.add_argument(
        '--temperature',
        type=float,
        default=0.3,
        help='LLM 温度参数（默认: 0.3）'
    )
    
    args = parser.parse_args()
    
    # 验证输入文件
    if not os.path.exists(args.video):
        print(f"错误: 文件不存在: {args.video}")
        sys.exit(1)
    
    # 加载配置文件
    saved_config = load_config()
    
    # 获取当前 LLM 配置
    current_profile = app_config.get_current_llm_profile(saved_config)
    
    # 构建配置（命令行参数优先，否则使用配置文件）
    llm_api_key = args.llm_api_key or current_profile.get('api_key', '')
    api_url = args.api_url if args.api_url != 'https://api.deepseek.com/v1/chat/completions' else current_profile.get('api_base_url', args.api_url)
    model = args.model if args.model != 'deepseek-chat' else current_profile.get('model_name', args.model)
    temperature = args.temperature if args.temperature != 0.3 else current_profile.get('temperature', args.temperature)
    
    # 获取 ElevenLabs API Key（命令行参数 > 配置文件）
    elevenlabs_api_key = args.elevenlabs_api_key or saved_config.get(app_config.USER_ELEVENLABS_API_KEY_KEY, '')
    
    # 验证 LLM API Key
    if not llm_api_key:
        print("错误: 未找到 LLM API Key")
        print("请使用以下方式之一提供 LLM API Key:")
        print("  1. 在 GUI 中保存 API Key")
        print("  2. 使用 --llm-api-key 参数")
        sys.exit(1)
    
    config = {
        'llm_api_key': llm_api_key,
        'llm_api_url': api_url,
        'llm_model': model,
        'language': args.language,
        'max_chunk_duration': args.max_duration,
        'temperature': temperature,
        'elevenlabs_api_key': elevenlabs_api_key  # 添加 ElevenLabs API Key
    }
    
    # 显示使用的配置
    print(f"使用配置:")
    print(f"  LLM API URL: {api_url}")
    print(f"  LLM 模型: {model}")
    print(f"  LLM 温度: {temperature}")
    if elevenlabs_api_key:
        print(f"  ElevenLabs API Key: {elevenlabs_api_key[:10]}...{elevenlabs_api_key[-4:]}")
    else:
        print(f"  ElevenLabs: 使用免费版（可能失效）")
    if args.language:
        print(f"  语言: {args.language}")
    print()
    
    # 执行流程
    try:
        pipeline = SubtitlePipeline(config)
        srt_path = pipeline.process_video(args.video)
        
        print(f"\n" + "=" * 60)
        print(f"OK: 字幕已生成: {srt_path}")
        print("=" * 60)
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(130)
        
    except Exception as e:
        print(f"\n\nError: 处理失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 处理 Windows 命令行编码问题
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    main()
