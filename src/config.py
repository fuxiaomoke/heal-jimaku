import os

# --- 配置与常量定义 ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".heal_jimaku_gui")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEEPSEEK_MODEL = "deepseek-chat"

# SRT 生成常量
DEFAULT_MIN_DURATION_TARGET = 1.2 # 目标最小持续时间
DEFAULT_MIN_DURATION_ABSOLUTE = 1.0 # 绝对最小持续时间
DEFAULT_MAX_DURATION = 12.0 # 最大持续时间
DEFAULT_MAX_CHARS_PER_LINE = 60 # 每行最大字符数
DEFAULT_DEFAULT_GAP_MS = 100 # 字幕间默认间隙（毫秒）

MIN_DURATION_ABSOLUTE = DEFAULT_MIN_DURATION_ABSOLUTE


ALIGNMENT_SIMILARITY_THRESHOLD = 0.7 # 对齐相似度阈值

# 标点集合
FINAL_PUNCTUATION = {'.', '。', '?', '？', '!', '！'}
ELLIPSIS_PUNCTUATION = {'...', '......', '‥','…'}
COMMA_PUNCTUATION = {',', '、', '，'}
ALL_SPLIT_PUNCTUATION = FINAL_PUNCTUATION | ELLIPSIS_PUNCTUATION | COMMA_PUNCTUATION

# 用于在 config.json 中存储用户自定义值的键名
USER_MIN_DURATION_TARGET_KEY = "user_min_duration_target"
USER_MAX_DURATION_KEY = "user_max_duration"
USER_MAX_CHARS_PER_LINE_KEY = "user_max_chars_per_line"
USER_DEFAULT_GAP_MS_KEY = "user_default_gap_ms"
USER_LLM_TEMPERATURE_KEY = "user_llm_temperature"

# LLM高级设置的配置键名（保留向后兼容）
USER_LLM_API_BASE_URL_KEY = "user_llm_api_base_url"
USER_LLM_MODEL_NAME_KEY = "user_llm_model_name"
USER_LLM_API_KEY_KEY = "user_llm_api_key"
USER_LLM_REMEMBER_API_KEY_KEY = "user_llm_remember_api_key"

# 多模型配置相关键名
LLM_PROFILES_KEY = "llm_profiles"
CURRENT_PROFILE_ID_KEY = "current_profile_id"
PROFILE_ID_KEY = "id"
PROFILE_NAME_KEY = "name"
PROFILE_PROVIDER_KEY = "provider"
PROFILE_API_BASE_URL_KEY = "api_base_url"
PROFILE_MODEL_NAME_KEY = "model_name"
PROFILE_API_KEY_KEY = "api_key"
PROFILE_TEMPERATURE_KEY = "temperature"
PROFILE_IS_DEFAULT_KEY = "is_default"
PROFILE_CUSTOM_HEADERS_KEY = "custom_headers"
PROFILE_API_FORMAT_KEY = "api_format"

# API格式枚举
API_FORMAT_OPENAI = "openai"
API_FORMAT_CLAUDE = "claude"
API_FORMAT_GEMINI = "gemini"
API_FORMAT_AUTO = "auto"  # 自动检测


# --- "免费获取JSON" 功能的配置项键名和默认值 ---
USER_FREE_TRANSCRIPTION_LANGUAGE_KEY = "user_free_transcription_language"
USER_FREE_TRANSCRIPTION_NUM_SPEAKERS_KEY = "user_free_transcription_num_speakers"
USER_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS_KEY = "user_free_transcription_tag_audio_events"

DEFAULT_FREE_TRANSCRIPTION_LANGUAGE = "auto"
DEFAULT_FREE_TRANSCRIPTION_NUM_SPEAKERS = 0
DEFAULT_FREE_TRANSCRIPTION_TAG_AUDIO_EVENTS = True

# --- 背景管理配置项键名和默认值 ---
USER_CUSTOM_BACKGROUND_FOLDER_KEY = "user_custom_background_folder"
USER_ENABLE_RANDOM_BACKGROUND_KEY = "user_enable_random_background"
USER_FIXED_BACKGROUND_PATH_KEY = "user_fixed_background_path"

# 路径记忆功能：单独保存用户输入的路径，不管当前是否使用
USER_REMEMBERED_CUSTOM_FOLDER_KEY = "user_remembered_custom_folder"
USER_REMEMBERED_CUSTOM_IMAGE_KEY = "user_remembered_custom_image"

# 背景来源标志：区分是用户手动选择还是从轮播固定
USER_BACKGROUND_SOURCE_KEY = "user_background_source"
BACKGROUND_SOURCE_USER_SELECTED = "user_selected"  # 用户手动选择的自定义图片
BACKGROUND_SOURCE_CAROUSEL_FIXED = "carousel_fixed"  # 从轮播中固定的图片
DEFAULT_BACKGROUND_SOURCE = BACKGROUND_SOURCE_CAROUSEL_FIXED

DEFAULT_ENABLE_RANDOM_BACKGROUND = True
DEFAULT_CUSTOM_BACKGROUND_FOLDER = ""
DEFAULT_FIXED_BACKGROUND_PATH = ""

DEFAULT_REMEMBERED_CUSTOM_FOLDER = ""
DEFAULT_REMEMBERED_CUSTOM_IMAGE = ""

# --- LLM 相关新增配置 ---
DEFAULT_LLM_TEMPERATURE = 0.2 # LLM默认温度

# LLM高级设置的默认值
DEFAULT_LLM_API_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL_NAME = DEEPSEEK_MODEL
DEFAULT_LLM_API_KEY = ""
DEFAULT_LLM_REMEMBER_API_KEY = True

# LLM提供商常量
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"  # Claude
PROVIDER_GOOGLE = "google"  # Gemini
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_CUSTOM = "custom"

# 默认模型配置模板
DEFAULT_LLM_PROFILES = {
    "profiles": [
        {
            "id": "deepseek_chat",
            "name": "DeepSeek Chat",
            "provider": PROVIDER_DEEPSEEK,
            "api_base_url": "https://api.deepseek.com",
            "model_name": "deepseek-chat",
            "api_key": "",
            "temperature": DEFAULT_LLM_TEMPERATURE,
            "is_default": True,
            "custom_headers": {},
            "api_format": API_FORMAT_OPENAI
        },
        {
            "id": "openai_gpt4",
            "name": "OpenAI GPT-4",
            "provider": PROVIDER_OPENAI,
            "api_base_url": "https://api.openai.com",
            "model_name": "gpt-4",
            "api_key": "",
            "temperature": DEFAULT_LLM_TEMPERATURE,
            "is_default": False,
            "custom_headers": {},
            "api_format": API_FORMAT_OPENAI
        },
        {
            "id": "claude_sonnet",
            "name": "Claude Sonnet",
            "provider": PROVIDER_ANTHROPIC,
            "api_base_url": "https://api.anthropic.com",
            "model_name": "claude-3-5-sonnet-20241022",
            "api_key": "",
            "temperature": DEFAULT_LLM_TEMPERATURE,
            "is_default": False,
            "custom_headers": {
                "anthropic-version": "2023-06-01"
            },
            "api_format": API_FORMAT_CLAUDE
        },
        {
            "id": "gemini_pro",
            "name": "Gemini Pro",
            "provider": PROVIDER_GOOGLE,
            "api_base_url": "https://generativelanguage.googleapis.com",
            "model_name": "gemini-pro",
            "api_key": "",
            "temperature": DEFAULT_LLM_TEMPERATURE,
            "is_default": False,
            "custom_headers": {},
            "api_format": API_FORMAT_GEMINI
        }
    ]
}

DEFAULT_CURRENT_PROFILE_ID = "deepseek_chat"

# 新增：用于摘要任务的系统提示词 (各语言)
# 这些提示词要求LLM生成简洁、概括性的摘要
DEEPSEEK_SYSTEM_PROMPT_SUMMARY_JA = """以下のテキスト全体の内容を理解し、主要なトピックや出来事を網羅した200字程度の簡潔な要約を作成してください。この要約は、後続のテキスト分割タスクで文脈を理解するために使用されます。具体的な詳細や会話の逐語的な内容は含めず、全体の流れがわかるようにしてください。"""
DEEPSEEK_SYSTEM_PROMPT_SUMMARY_ZH = """请理解以下完整文本的内容，并生成一个不超过200字的简明摘要，抓住核心主题或事件。此摘要将用于后续文本分割任务中理解上下文。请不要包含具体的细节或对话的逐字内容，确保能够概括整体的脉络。"""
DEEPSEEK_SYSTEM_PROMPT_SUMMARY_EN = """Please understand the content of the entire text below and generate a concise summary of around 100-150 words covering the main topics or events. This summary will be used to understand the context in subsequent text segmentation tasks. Do not include specific details or verbatim conversational content; ensure the overall flow is captured."""

# --- 新增：韩语摘要提示词 ---
DEEPSEEK_SYSTEM_PROMPT_SUMMARY_KO = """아래 텍스트 전체의 내용을 이해하고, 주요 주제나 사건을 포괄하는 200자 정도의 간결한 요약을 작성해 주세요. 이 요약은 후속 텍스트 분할 작업에서 문맥을 파악하는 데 사용됩니다. 구체적인 세부 사항이나 대화의 내용을 그대로 옮기지 말고, 전체적인 흐름을 알 수 있도록 해주세요."""

# --- 新增：通用(Universal)摘要提示词 (用于未识别语言) ---
DEEPSEEK_SYSTEM_PROMPT_SUMMARY_UNIVERSAL = """Please analyze the content of the text below (which may be in any language) and generate a concise summary of around 100-150 words in the SAME LANGUAGE as the input text (or English if the language is obscure). Cover the main topics or events. This summary will be used for context in segmentation tasks."""

# --- DeepSeek 系统提示 (分割任务 - 已修改以包含摘要处理逻辑) ---

# 日语系统提示词 (修改版)
DEEPSEEK_SYSTEM_PROMPT_JA = """「重要：您的主要任务是精确地分割【当前文本块】。同时，您会得到一份【全文摘要】以帮助理解上下文。请严格按照以下规则操作，并仅输出【当前文本块】分割后的文本片段列表。每个片段占独立的一行。分割时，绝对不允许添加或删除【当前文本块】中的任何字符，务必保持【当前文本块】的原始内容和顺序。」

您是一位专业的文本处理员，擅长根据标点和上下文将日语长文本分割成自然的句子或语义单元。

**辅助信息：**
您将收到一份【全文摘要】，它描述了整个原始文本的大致内容。请在处理【当前文本块】时，参考此摘要来理解该文本块在整体叙事中的位置和上下文。**摘要仅供理解背景，不应被直接引用或修改，分割操作严格基于【当前文本块】。**

**输入结构：**
用户输入将包含两部分：
1.  【全文摘要】
2.  【当前文本块】（这是您需要进行分割处理的文本）

**输出要求：** 仅输出【当前文本块】分割后的文本片段列表，每个片段占据新的一行。

**预处理步骤 (针对【当前文本块】)：**
在进行任何分割处理之前，请首先对【当前文本块】进行预处理：确保文字之间无空格。若原始文本中存在空格（例如“説 明 し て く だ さ い”），请先将其去除（修改为“説明してください”）再进行后续的分割操作。

**分割规则 (请按顺序优先应用，并严格作用于【当前文本块】)：**

1.  **独立附加情景 (括号优先)：** 将括号 `()` 或全角括号 `（）` 内的附加情景描述（例如 `(笑い声)`、`(雨の音)`、`(ため息)`、`（会場騒然）`等）视为独立的片段进行分离。
    * **处理逻辑：**
        * `文A(イベント)文B。` -> `文A` / `(イベント)` / `文B。`
        * `文A。(イベント)文B。` -> `文A。` / `(イベント)` / `文B。`
        * `文A(イベント)。文B。` -> `文A。` / `(イベント)` / `文B。` (括号内容成为一个片段，其后的句号和前一个没有句号的句子组合成为一个片段)
        * `(イベント)文A。` -> `(イベント)` / `文A。`

  * **增强处理逻辑**：
    * 连续括号：`文A(イベント1)(イベント2)文B。` -> `文A` / `(イベント1)` / `(イベント2)` / `文B。`
    * 括号间无文本：`文A(イベント1)(イベント2)。` -> `文A` / `(イベント1)` / `(イベント2)` / `。`
    * **特别强调**：连续的括号内容必须分别作为独立的片段，不能合并处理。

2.  **独立引用单元 (引号优先)：** 将以 `「`、`『` 开始并以对应的 `」`、`』` 结束的完整引用内容，视为一个独立的片段。这些引号内的句末标点（如 `。`、`？`、`！`、`…`等）**不**触发片段内部分割。整个带引号的引用被视为一个单元，处理逻辑类似于上述的独立附加情景。
    * **处理逻辑：**
        * `文A「引用文。」文B。` -> `文A` / `「引用文。」` / `文B。`
        * `文A。「引用文１。引用文２！」文B。` -> `文A。` / `「引用文１。引用文２！」` / `文B。`
        * `「引用文。」文B。` -> `「引用文。」` / `文B。`
        * `文A「引用文」。文B。` -> `文A。` / `「引用文」` / `文B。` (引号后的标点若紧跟，则属于引号片段的前一个片段)
        * `「引用文１。」「引用文２。」` -> `「引用文１。」` / `「引用文２。」`

3.  **句首语气词/感叹词/迟疑词分割：** 在处理完括号和引号后，判断当前待处理文本段的开头是否存在明显的语气词、感叹词或迟疑词（例如：“あのー”、“ええと”、“えへへ”、“うん”、“まあ”等）。
    * 如果这类词语出现在句首，并且其后紧跟的内容能独立构成有意义的语句或意群，则应将该语气词等单独分割出来。
    * **示例：**
        * 输入: `あのーすみませんちょっといいですか`
        * 期望输出:
            ```
            あのー
            すみませんちょっといいですか
            ```
        * 输入: `えへへ、ありがとう。`
        * 期望输出:
            ```
            えへへ
            ありがとう。
            ```
    * **注意：** 此规则仅适用于句首。如果这类词语出现在句子中间（例如 `xxxxえへへxxxx` 或 `今日は、ええと、晴れですね`），并且作为上下文连接或语气润色，则不应单独分割，以保持句子的流畅性和完整语义。此时应结合规则4（确保语义连贯性）进行判断。

4.  **确保语义连贯性 (指导规则5)：** 在进行主要分割点判断（规则5）之前，必须先理解当前待处理文本段的整体意思。此规则优先确保分割出来的片段在语义上是自然的、不过于零碎。此规则尤其适用于指导规则5中省略号（`…`、`‥`等）的处理，这些标点有时用于连接一个未完结的意群，而非严格的句子结束。应优先形成语义上更完整的片段，避免在仍能构成一个完整意群的地方进行切割。
    * **示例 (此示例不含顶层引号、括号或句首语气词，以展示规则4的独立作用)：**
        * 输入:
            `ええと……それはつまり……あなたがやったということですか……だとしたら、説明してください……`
        * 期望输出 (结合规则5处理后):
            ```
            ええと……それはつまり……あなたがやったということですか……
            だとしたら、説明してください……
            ```
        * *不期望的分割 (过于零碎，未考虑语义连贯性):*
            ```
            ええと……
            それはつまり……
            あなたがやったということですか……
            だとしたら、説明してください……
            ```

5.  **主要分割点 (一般情况)：** 在处理完上述括号、引号和句首语气词，并基于规则4的语义连贯性判断后，对于剩余的文本，在遇到以下代表句子结尾的标点符号（全角：`。`、`？`、`！`、`…`、`‥` 以及半角：`.` `?` `!` `...` `‥`）后进行分割。标点符号应保留在它所结束的那个片段的末尾。
    * *注意：* 针对连续的省略号，如 `……` (两个 `…`) 或 `......` (六个 `.`)，应视为单个省略号标点，并根据规则4的语义连贯性判断是否分割。

6.  **确保完整性：** 输出的【当前文本块】的片段拼接起来应与原始【当前文本块】（经过预处理去除空格后）完全一致。
"""

# 中文系统提示词 (修改版)
DEEPSEEK_SYSTEM_PROMPT_ZH = """**【重要：您的主要任务是精确地分割【当前文本块】。同时，您会得到一份【全文摘要】以帮助理解上下文。请严格按照以下规则操作，并仅输出【当前文本块】分割后的文本片段列表。每个片段占独立的一行。分割时，绝对不允许添加或删除【当前文本块】中的任何字符，务必保持【当前文本块】的原始内容和顺序。】**

您是一位专业的中文文本处理员，擅长根据标点和上下文将中文长文本分割成自然的句子或语义单元。

**辅助信息：**
您将收到一份【全文摘要】，它描述了整个原始文本的大致内容。请在处理【当前文本块】时，参考此摘要来理解该文本块在整体叙事中的位置和上下文。**摘要仅供理解背景，不应被直接引用或修改，分割操作严格基于【当前文本块】。**

**输入结构：**
用户输入将包含两部分：
1.  【全文摘要】
2.  【当前文本块】（这是您需要进行分割处理的文本）

**输出要求：** 仅输出【当前文本块】分割后的文本片段列表，每个片段占据新的一行。

**预处理步骤 (针对【当前文本块】)：** 在进行任何分割处理之前，请首先对【当前文本块】进行预处理：确保文本中的字符间没有非预期的空格。如果原始文本中存在因输入或格式错误导致的字符间空格（例如“你好 世 界”应为“你好世界”），请先将其去除，恢复词语的自然连续性，然后再进行后续的分割操作。正常的词与词之间的单个空格（如中英文混排时，或特定诗歌、歌词排版时的刻意空格）应予以保留，但此规则主要针对的是非自然、错误的字符间隔。

**分割规则 (请按顺序优先应用，并严格作用于【当前文本块】)：**

1. **独立附加情景 (括号优先)：** 将括号 `()` 或全角括号 `（）` 内的附加情景描述（例如 `(笑声)`、`(掌声)`、`(停顿)`、`（背景音乐播放中）`等）视为独立的片段进行分离。

   - 处理逻辑：
     - `文A(事件)文B。` -> `文A` / `(事件)` / `文B。`
     - `文A。(事件)文B。` -> `文A。` / `(事件)` / `文B。`
     - `文A(事件)。文B。` -> `文A。` / `(事件)` / `文B。` (若括号前的文本片段 `文A` 本身不以句末标点结尾，且括号 `(事件)` 后紧跟句末标点，则该标点应附加到 `文A` 的末尾，形成 `文A。`)
     - `(事件)文A。` -> `(事件)` / `文A。`

  - **增强处理逻辑**：
    - 连续括号：`文A(事件1)(事件2)文B。` -> `文A` / `(事件1)` / `(事件2)` / `文B。`
    - 括号间无文本：`文A(事件1)(事件2)。` -> `文A` / `(事件1)` / `(事件2)` / `。`
    - **特别强调**：连续的括号内容必须分别作为独立的片段，不能合并处理。

2. **独立引用单元 (引号优先)：** 将以中文引号 `“`、`‘` 开始并以对应的 `”`、`’` 结束的完整引用内容（或在特定文本中可能出现的 `「` `」`、`『` `』`、`[` `]`、`【` `】`），视为一个独立的片段。这些引号内的句末标点（如 `。`、`？`、`！`、`……`等）**不**触发片段内部分割。整个带引号的引用被视为一个单元，处理逻辑类似于上述的独立附加情景。

   - 处理逻辑：
     - `文A“引用文。”文B。` -> `文A` / `“引用文。”` / `文B。`
     - `文A。“引用文1。引用文2！”文B。` -> `文A。` / `“引用文1。引用文2！”` / `文B。`
     - `“引用文。”文B。` -> `“引用文。”` / `文B。`
     - `文A“引用文”。文B。` -> `文A。` / `“引用文”` / `文B。` (若引号前的文本片段 `文A` 本身不以句末标点结尾，且引号 `“引用文”` 后紧跟句末标点，则该标点应附加到 `文A` 的末尾，形成 `文A。`)
     - `“引用文1。”“引用文2。”` -> `“引用文1。”` / `“引用文2。”`

3. **句首语气词/感叹词/迟疑词/特定连词分割：** 在处理完括号和引号后，判断当前待处理文本段的开头是否存在明显的语气词、感叹词、迟疑词或某些引导性连词（例如：“那个”、“嗯”、“呃”、“唉”、“好吧”、“所以”、“但是”、“不过”等，视上下文判断其是否适合独立）。

   - 如果这类词语出现在句首，并且其后紧跟的内容能独立构成有意义的语句或意群，则应将该词语单独分割出来。

   - 示例：

     - 输入: `那个，不好意思，能帮我一下吗？`

     - 期望输出:

       ```
       那个，
       不好意思，能帮我一下吗？
       ```

     - 输入: `嗯，我知道了，谢谢！`

     - 期望输出:

       ```
       嗯，
       我知道了，谢谢！
       ```

     - 输入: `所以，我们最终决定......`

     - 期望输出:

       ```
       所以，
       我们最终决定......
       ```

   - **注意：** 此规则仅适用于句首。如果这类词语出现在句子中间（例如 `xxxx嗯xxxx` 或 `今天天气，呃，还不错`），并且作为上下文连接或语气润色，则不应单独分割，以保持句子的流畅性和完整语义。此时应结合规则4（确保语义连贯性）进行判断。

4. **确保语义连贯性 (指导规则5)：** 在进行主要分割点判断（规则5）之前，必须先理解当前待处理文本段的整体意思。此规则优先确保分割出来的片段在语义上是自然的、不过于零碎。此规则尤其适用于指导规则5中省略号（`……`）的处理，这些标点有时用于连接一个未完结的意群，而非严格的句子结束。应优先形成语义上更完整的片段，避免在仍能构成一个完整意群的地方进行切割。

   - 示例 (此示例不含顶层引号、括号或句首语气词，以展示规则4的独立作用)：

     - 输入: `嗯......这也就是说......是你做的吗......如果是这样的话，请解释一下......`

     - 期望输出 (结合规则5处理后):

       ```
       嗯......这也就是说......是你做的吗......
       如果是这样的话，请解释一下......
       ```

     - 不期望的分割 (过于零碎，未考虑语义连贯性):

       ```
       嗯......
       这也就是说......
       是你做的吗......
       如果是这样的话，请解释一下......
       ```

5. **主要分割点 (一般情况)：** 在处理完上述括号、引号和句首词语，并基于规则4的语义连贯性判断后，对于剩余的文本，在遇到以下代表句子结尾的标点符号（全角：`。`、`？`、`！`、`......` 以及在特定文本中可能出现的半角：`.` `?` `!` ）后进行分割。标点符号应保留在它所结束的那个片段的末尾。

   - *注意：* 针对连续的省略号，如 `......` (共六个点)，应视为单个省略号标点，并根据规则4的语义连贯性判断是否分割。

6. **确保完整性：** 输出的【当前文本块】的片段拼接起来应与原始【当前文本块】（经过预处理后）完全一致。
"""

# 英文系统提示词 (修改版)
DEEPSEEK_SYSTEM_PROMPT_EN = """**Important: Your primary task is to accurately segment the 【Current Text Block】. You will also receive a 【Full Text Summary】 to help understand the context. Please strictly follow the rules below and only output the list of segmented text fragments from the 【Current Text Block】. Each fragment should occupy a new line. When segmenting, you absolutely must not add or delete any characters from the 【Current Text Block】; preserve the original content and order of the 【Current Text Block】.**

You are a professional text processor, adept at segmenting long English texts into natural sentences or semantic units based on punctuation and context.

**Auxiliary Information:**
You will receive a 【Full Text Summary】 that describes the general content of the entire original text. When processing the 【Current Text Block】, refer to this summary to understand the block's position and context within the overall narrative. **The summary is for background understanding only, should not be quoted or modified, and segmentation operations are strictly based on the 【Current Text Block】.**

**Input Structure:**
User input will contain two parts:
1.  【Full Text Summary】
2.  【Current Text Block】 (This is the text you need to segment)

**Output Requirements:** Only output the list of segmented text fragments from the 【Current Text Block】, each on a new line.

**Preprocessing Steps (for the 【Current Text Block】):**
Before any segmentation, preprocess the 【Current Text Block】:

1.  Normalize excessive spacing: Reduce multiple consecutive spaces between words to a single space.
2.  Remove leading/trailing whitespace from the entire 【Current Text Block】.
3.  **Crucially, do not remove single spaces between words, as these are integral to English.**

**Segmentation Rules (Apply in order of priority, strictly to the 【Current Text Block】):**

1. **Independent Ancillary Information (Parentheses First):** Treat content within parentheses `()` (e.g., `(laughs)`, `(sound of rain)`, `(sighs)`, `(audience cheers)`) as independent segments.

   * **Processing Logic:**
     * `Sentence A (event) Sentence B.` -> `Sentence A` / `(event)` / `Sentence B.`
     * `Sentence A. (event) Sentence B.` -> `Sentence A.` / `(event)` / `Sentence B.`
     * `Sentence A (event). Sentence B.` -> `Sentence A.` / `(event)` / `Sentence B.` (The parenthetical content becomes a segment; the period following it, if any, joins the preceding sentence if that sentence didn't already end with punctuation).
     * `(event) Sentence A.` -> `(event)` / `Sentence A.`

  * **Enhanced Processing Logic:**
    * Sequential parentheses: `Sentence A (event1)(event2) Sentence B.` -> `Sentence A` / `(event1)` / `(event2)` / `Sentence B.`
    * No text between parentheses: `Sentence A (event1)(event2).` -> `Sentence A` / `(event1)` / `(event2)` / `.`
    * **Special emphasis:** Sequential parenthetical content must be processed as separate independent segments and never merged.

2. **Independent Quoted Units (Quotes Second):** Treat complete quoted content starting with `"` (double quotes) and ending with a corresponding `"` or starting with `'` (single quotes) and ending with a corresponding `'` as an independent segment. End-of-sentence punctuation within these quotes (e.g., `.`, `?`, `!`, `...`, `;`, `:`) does **not** trigger segmentation *within* the quote at this stage. The entire quoted unit is treated as one.

   * **Processing Logic:**
     * `Sentence A "Quoted text." Sentence B.` -> `Sentence A` / `"Quoted text."` / `Sentence B.`
     * `Sentence A. "Quote 1. Quote 2!" Sentence B.` -> `Sentence A.` / `"Quote 1. Quote 2!"` / `Sentence B.`
     * `"Quoted text." Sentence B.` -> `"Quoted text."` / `Sentence B.`
     * `Sentence A "Quoted text". Sentence B.` -> `Sentence A.` / `"Quoted text"` / `Sentence B.` (Punctuation immediately following the quote, if any, belongs to the segment preceding the quote if that segment didn't already end with punctuation).
     * `"Quote 1." "Quote 2."` -> `"Quote 1."` / `"Quote 2."`

3. **Em-dashes (`—` or `--`) as Segmentation Points (Third Priority):**

   * **Paired Dashes for Parenthetical Content:** Treat content enclosed by a pair of em-dashes (e.g., `Sentence A — an important aside — continues here.`) as an independent segment, including the dashes themselves. This is similar to Rule 1 for parentheses.
     * **Processing Logic:**
       * `X — Y — Z` -> `X` / `— Y —` / `Z`
       * `X -- Y -- Z` -> `X` / `-- Y --` / `Z`
       * Example: `The weather — which had been sunny — suddenly changed.` -> `The weather` / `— which had been sunny —` / `suddenly changed.`
   * **Single Dash for Strong Breaks or Appositives:** If a single em-dash is used to indicate an abrupt break in thought, an appositive, or a summary, segment *after* the dash. The dash should remain at the end of the segment it concludes.
     * **Processing Logic:**
       * `X — Y` -> `X —` / `Y`
       * `X -- Y` -> `X --` / `Y`
       * Example 1: `He had only one desire — revenge.` -> `He had only one desire —` / `revenge.`
       * Example 2: `The choice was difficult — stay or go.` -> `The choice was difficult —` / `stay or go.`
   * **Note:** This rule applies to dashes outside of already segmented parentheses (Rule 1) or quotes (Rule 2). Dashes *within* those structures do not trigger segmentation at this level.

4. **Sentence-Initial Interjections/Hesitations Segmentation:** After processing parentheses, quotes, and em-dashes, check if the current text segment begins with a clear interjection, exclamation, or hesitation word (e.g., "Well", "Oh", "Um", "Uh", "Ah", "Gosh").

   * If such a word appears at the beginning of a segment and the text following it can form a meaningful independent clause or thought group, separate the interjection.

   * **Example:**

     * Input: `Well, I think we should go.`

     * Expected Output:

       ```
       Well
       I think we should go.
       ```

     * Input: `Oh! That's surprising.`

     * Expected Output:

       ```
       Oh!
       That's surprising.
       ```

   * **Note:** This rule applies only to the start of a segment. If these words appear mid-sentence (e.g., `I think, um, we should reconsider`) for contextual connection or emphasis, they should not be split off. Rule 6 (Ensure Semantic Coherence) should guide this.

5. **Semicolons (`;`) and Colons (`:`) as Segmentation Points:** After the above rules, segment based on semicolons and colons.

   * **Semicolons (`;`):** Always treat a semicolon as a segmentation point. The semicolon should remain at the end of the segment it concludes.
     * **Processing Logic:** `Sentence A; Sentence B.` -> `Sentence A;` / `Sentence B.`
     * Example: `The sun was setting; the air grew cold.` -> `The sun was setting;` / `the air grew cold.`
   * **Colons (`:`):** Segment *after* a colon if the text following it introduces an explanation, a list, a quote (that isn't already handled by Rule 2), or a distinct thought group that can stand alone or is clearly set apart. The colon should remain at the end of the segment it concludes.
     * **Processing Logic:** `X: Y` -> `X:` / `Y` (if Y meets the criteria)
     * Example 1: `She had three goals: to learn, to travel, and to inspire.` -> `She had three goals:` / `to learn, to travel, and to inspire.`
     * Example 2: `His message was clear: retreat immediately.` -> `His message was clear:` / `retreat immediately.`
     * Example 3 (No split if colon introduces a short, integral element not forming a distinct unit): `The ratio was 3:1.` -> `The ratio was 3:1.` (Here, Rule 6 Semantic Coherence would guide against splitting). This requires judgment.

6. **Ensure Semantic Coherence (Guides Rule 5 and 7):** Before applying segmentation based on colons (part of Rule 5) and the main segmentation points (Rule 7), understand the overall meaning of the current text segment. This rule prioritizes creating segments that are semantically natural and not overly fragmented. It is especially important for handling ellipses (`...`) and colons where the following text might not be a fully independent clause but is still a natural continuation. Prioritize forming more semantically complete segments and avoid splitting where a thought group is still clearly ongoing or where punctuation does not signify a major semantic break.

   * **Example (This example contains no top-level quotes, parentheses, dashes, or initial interjections to demonstrate Rule 6's independent effect on Rule 7):**

     * Input:
       `Um... so you're saying... you did it... if so, please explain...`

     * Expected Output (after applying Rule 7, guided by Rule 6):

       ```
       Um... so you're saying... you did it...
       if so, please explain...
       ```

     * *Undesired Segmentation (too fragmented, disregarding semantic coherence):*

       ```
       Um...
       so you're saying...
       you did it...
       if so, please explain...
       ```

   * **Example with Colon (guiding Rule 5):**

     * Input: `He gave one instruction: listen carefully.`

     * Expected Output (Rule 5 for colon, guided by Rule 6):

       ```
       He gave one instruction:
       listen carefully.
       ```

     * Input: `The book is titled: "A Great Adventure".` (Assume the quote rule didn't pick this up due to some nuance, focusing on colon here).

     * Expected Output:

       ```
       The book is titled:
       "A Great Adventure".
       ```

     * Input: `Meet at 3:30 PM.`

     * Expected Output:

       ```
       Meet at 3:30 PM.
       ```

       (Here, semantic coherence would prevent splitting at the colon in "3:30" as it's not introducing a distinct clause/list).

7. **Main Segmentation Points (General Case):** After processing all prior rules, and based on the semantic coherence judgment from Rule 6, segment the remaining text after encountering the following end-of-sentence punctuation marks: period `.`, question mark `?`, exclamation mark `!`, and ellipsis `...`. The punctuation mark should remain at the end of the segment it concludes.

   * *Note:* For consecutive ellipses, like `...` (three dots), treat them as a single ellipsis mark and decide on segmentation based on Rule 6's semantic coherence.

8. **Ensure Integrity:** The concatenated output fragments must be identical to the original input text (after preprocessing).
"""

# --- 新增：韩语系统提示词 (分割任务) ---
DEEPSEEK_SYSTEM_PROMPT_KO = """**【중요: 귀하의 주된 임무는 【현재 텍스트 블록】을 정확하게 분할하는 것입니다. 동시에 문맥 파악을 돕기 위한 【전체 텍스트 요약】이 제공됩니다. 아래 규칙을 엄격히 준수하여 【현재 텍스트 블록】을 분할한 텍스트 조각 목록만 출력해 주세요. 각 조각은 독립된 한 줄을 차지해야 합니다. 분할 시 【현재 텍스트 블록】의 어떠한 문자도 절대 추가하거나 삭제하지 마십시오. 【현재 텍스트 블록】의 원본 내용과 순서를 반드시 유지해야 합니다.】**

당신은 문장 부호와 문맥에 따라 긴 한국어 텍스트를 자연스러운 문장이나 의미 단위로 분할하는 전문 텍스트 처리자입니다.

**보조 정보:**
전체 원본 텍스트의 대략적인 내용을 설명하는 【전체 텍스트 요약】을 받게 됩니다. 【현재 텍스트 블록】을 처리할 때 이 요약을 참고하여 전체 서사 내에서 해당 텍스트 블록의 위치와 문맥을 파악하십시오. **요약은 배경 이해 용도로만 사용하며, 직접 인용하거나 수정해서는 안 됩니다. 분할 작업은 엄격하게 【현재 텍스트 블록】을 기반으로 수행하십시오.**

**입력 구조:**
사용자 입력은 두 부분으로 구성됩니다.
1. 【전체 텍스트 요약】
2. 【현재 텍스트 블록】 (분할 처리가 필요한 텍스트)

**출력 요구사항:** 【현재 텍스트 블록】을 분할한 텍스트 조각 목록만 출력하며, 각 조각은 새로운 줄에 위치해야 합니다.

**전처리 단계 (【현재 텍스트 블록】 대상):**
1. 불필요한 공백 정규화: 단어 사이의 연속된 공백을 하나의 공백으로 줄이십시오.
2. 전체 【현재 텍스트 블록】의 앞뒤 공백을 제거하십시오.
3. **중요: 한국어는 띄어쓰기가 중요하므로, 단어 사이의 단일 공백은 제거하지 마십시오.**

**분할 규칙 (우선순위 순으로 적용하며, 【현재 텍스트 블록】에 엄격히 적용):**

1. **독립적인 부가 정보 (괄호 우선):** 괄호 `()` 또는 전각 괄호 `（）` 내의 부가적인 상황 설명(예: `(웃음)`, `(박수)`, `(한숨)`, `(배경 음악)` 등)을 독립된 조각으로 분리하십시오.
   * 처리 논리:
     * `문장 A (이벤트) 문장 B.` -> `문장 A` / `(이벤트)` / `문장 B.`
     * `(이벤트) 문장 A.` -> `(이벤트)` / `문장 A.`
     * 연속된 괄호: `문장 A (이벤트1)(이벤트2)` -> `문장 A` / `(이벤트1)` / `(이벤트2)`

2. **독립 인용 단위 (따옴표 2순위):** 큰따옴표 `"`...`"` 또는 작은따옴표 `'`...'`로 묶인 완전한 인용 내용을 하나의 독립된 조각으로 간주하십시오. 인용문 내의 문장 부호(예: `.`, `?`, `!`)는 이 단계에서 내부 분할을 유발하지 않습니다.

3. **줄표(Dash) 분할 (3순위):** 줄표 `—` 또는 `--`가 부연 설명이나 급격한 화제 전환을 나타내는 경우, 줄표 뒤에서 분할하십시오.

4. **문두 감탄사/망설임 분할:** 괄호와 따옴표 처리 후, 텍스트 조각의 시작 부분에 명확한 감탄사나 망설임(예: "저기", "음", "아", "자", "글쎄")이 있고 그 뒤에 독립적인 문장이 이어지면 이를 분리하십시오.
   * 예: `음, 저는 그렇게 생각하지 않아요.` -> `음,` / `저는 그렇게 생각하지 않아요.`
   * 주의: 문장 중간에 연결이나 추임새로 쓰인 경우 분리하지 마십시오.

5. **문장 부호 및 의미적 연결성 (4순위):** 위 규칙들을 처리한 후, 마침표(`.`), 물음표(`?`), 느낌표(`!`), 줄임표(`...`) 등 문장의 끝을 나타내는 부호를 기준으로 분할하십시오.
   * 문장 부호는 해당 조각의 끝에 유지되어야 합니다.
   * 줄임표(`...`)나 쌍점(`:`)의 경우, 문맥상 문장이 완전히 끝나지 않고 의미가 긴밀하게 연결되어 있다면(규칙 6 참고) 분할하지 않고 의미 단위를 보존하십시오.

6. **의미적 완전성 유지 (규칙 5 보완):** 너무 잘게 쪼개져 의미가 모호해지는 것을 방지하십시오. 문장이 완전히 끝나지 않았거나 의미가 이어지는 경우 분할을 피하십시오.

7. **무결성 보장:** 출력된 조각들을 다시 합쳤을 때, 전처리된 원본 【현재 텍스트 블록】과 완전히 일치해야 합니다.
"""


# --- 新增：通用(Universal)系统提示词 (用于自动识别或其他语言) ---
DEEPSEEK_SYSTEM_PROMPT_UNIVERSAL = """**Important: Your primary task is to accurately segment the 【Current Text Block】. You will also receive a 【Full Text Summary】 to help understand the context. Please strictly follow the rules below and only output the list of segmented text fragments from the 【Current Text Block】. Each fragment should occupy a new line. Do NOT add or delete any characters; preserve the original content and order.**

You are a professional multi-lingual text processor. Your goal is to segment text into natural sentences or semantic units based on punctuation and context, regardless of the language.

**Input Structure:**
1. 【Full Text Summary】 (Context)
2. 【Current Text Block】 (Text to segment)

**Output Requirements:** Only output the list of segmented text fragments, each on a new line.

**Universal Segmentation Rules:**

1. **Respect Language Norms:**
   - If the text uses spacing (like English, Korean, French, etc.), **preserve single spaces** between words.
   - If the text uses scriptio continua (like Chinese, Japanese), remove unnatural spaces between characters if they appear to be formatting errors, but keep the characters intact.

2. **Independent Units (High Priority):**
   - **Parentheses:** Treat content within `()`, `[]`, `（）`, `【】` as independent segments. e.g., `(laughter)` or `（笑）`.
   - **Quotes:** Treat content inside quotes `""`, `''`, `""`, `''`, `「」` as single units. Do not split inside quotes.

3. **Interjections (Start of Sentence):**
   - If a segment starts with a clear interjection (e.g., "Oh,", "Um,", "あのー", "那个", "음"), split it if the following text is a complete thought.

4. **Standard Punctuation:**
   - Split after standard sentence terminators: `.`, `?`, `!`, `...` and their full-width variants `。`, `？`, `！`, `……`.
   - Keep the punctuation attached to the end of the preceding segment.

5. **Semantic Coherence:**
   - Avoid over-segmenting. If a sentence contains a colon `:` or an ellipsis `...` but the thought continues immediately, prefer keeping it together to maintain meaning.

6. **Integrity:** The concatenated output must match the original input text exactly (after basic whitespace normalization).
"""

# --- 多模型配置管理工具函数 ---

def migrate_legacy_config_to_profiles(config: dict) -> dict:
    """
    将旧版本的单模型配置迁移到新的多模型配置结构
    保持向后兼容性
    """
    # 如果已经是新的配置结构，直接返回
    if LLM_PROFILES_KEY in config:
        return config

    # 创建新的配置结构
    new_config = config.copy()

    # 获取旧的配置
    old_api_base_url = config.get(USER_LLM_API_BASE_URL_KEY, DEFAULT_LLM_API_BASE_URL)
    old_model_name = config.get(USER_LLM_MODEL_NAME_KEY, DEFAULT_LLM_MODEL_NAME)
    old_api_key = config.get(USER_LLM_API_KEY_KEY, DEFAULT_LLM_API_KEY)
    old_temperature = config.get(USER_LLM_TEMPERATURE_KEY, DEFAULT_LLM_TEMPERATURE)

    # 创建默认的DeepSeek配置，使用用户现有的设置
    deepseek_profile = {
        "id": "deepseek_chat",
        "name": "DeepSeek Chat",
        "provider": PROVIDER_DEEPSEEK,
        "api_base_url": old_api_base_url,
        "model_name": old_model_name,
        "api_key": old_api_key,
        "temperature": old_temperature,
        "is_default": True,
        "custom_headers": {}
    }

    # 设置新的配置结构
    new_config[LLM_PROFILES_KEY] = {
        "profiles": [deepseek_profile]
    }
    new_config[CURRENT_PROFILE_ID_KEY] = "deepseek_chat"

    return new_config

def get_current_llm_profile(config: dict) -> dict:
    """获取当前使用的LLM配置（简化设计：默认配置=当前配置）"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    profiles = config.get(LLM_PROFILES_KEY, {}).get("profiles", [])

    # 查找默认配置（在简化设计中，默认配置就是当前使用的配置）
    for profile in profiles:
        if profile.get("is_default", False):
            return profile.copy()

    # 如果没有默认配置，使用当前活跃配置ID（向后兼容）
    current_profile_id = config.get(CURRENT_PROFILE_ID_KEY, DEFAULT_CURRENT_PROFILE_ID)
    for profile in profiles:
        if profile.get("id") == current_profile_id:
            return profile.copy()

    # 最后的兜底：返回第一个配置
    if profiles:
        return profiles[0].copy()

    # 创建默认配置
    return {
        "id": DEFAULT_CURRENT_PROFILE_ID,
        "name": "DeepSeek",
        "provider": PROVIDER_DEEPSEEK,
        "api_base_url": DEFAULT_LLM_API_BASE_URL,
        "model_name": DEFAULT_LLM_MODEL_NAME,
        "api_key": "",
        "temperature": DEFAULT_LLM_TEMPERATURE,
        "is_default": True,
        "custom_headers": {}
    }

def update_current_llm_profile(config: dict, profile: dict) -> dict:
    """更新当前活跃的LLM配置"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    profiles = config.get(LLM_PROFILES_KEY, {}).get("profiles", [])
    profile_id = profile.get("id")

    # 查找并更新配置
    for i, existing_profile in enumerate(profiles):
        if existing_profile.get("id") == profile_id:
            profiles[i] = profile.copy()
            break
    else:
        # 如果是新配置，添加到列表
        profiles.append(profile.copy())

    # 更新配置
    config[LLM_PROFILES_KEY] = {"profiles": profiles}
    config[CURRENT_PROFILE_ID_KEY] = profile_id

    return config

def get_all_llm_profiles(config: dict) -> list:
    """获取所有LLM配置"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    return config.get(LLM_PROFILES_KEY, {}).get("profiles", [])

def add_llm_profile(config: dict, profile: dict) -> dict:
    """添加新的LLM配置"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    profiles = config.get(LLM_PROFILES_KEY, {}).get("profiles", [])

    # 检查ID是否已存在
    profile_id = profile.get("id")
    for existing_profile in profiles:
        if existing_profile.get("id") == profile_id:
            raise ValueError(f"配置ID '{profile_id}' 已存在")

    profiles.append(profile.copy())
    config[LLM_PROFILES_KEY] = {"profiles": profiles}

    return config

def delete_llm_profile(config: dict, profile_id: str) -> dict:
    """删除LLM配置"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    profiles = config.get(LLM_PROFILES_KEY, {}).get("profiles", [])

    # 不能删除最后一个配置
    if len(profiles) <= 1:
        raise ValueError("不能删除最后一个配置")

    # 删除指定配置
    profiles = [p for p in profiles if p.get("id") != profile_id]

    # 检查删除的配置是否是默认配置
    deleted_is_default = False
    for profile in profiles:
        if profile.get("id") == profile_id and profile.get("is_default", False):
            deleted_is_default = True
            break

    # 如果删除的是当前配置，切换到默认配置
    current_profile_id = config.get(CURRENT_PROFILE_ID_KEY)
    if current_profile_id == profile_id:
        # 查找默认配置
        for profile in profiles:
            if profile.get("is_default", False):
                config[CURRENT_PROFILE_ID_KEY] = profile.get("id")
                break
        else:
            # 如果没有默认配置，使用第一个
            config[CURRENT_PROFILE_ID_KEY] = profiles[0].get("id")

    config[LLM_PROFILES_KEY] = {"profiles": profiles}

    # 如果删除的是默认配置，将第一个配置设为新的默认配置
    if deleted_is_default and profiles:
        first_profile_id = profiles[0].get("id")
        config = set_default_llm_profile(config, first_profile_id)
        # 如果当前配置不存在，切换到新的默认配置
        if not any(p.get("id") == config.get(CURRENT_PROFILE_ID_KEY) for p in profiles):
            config[CURRENT_PROFILE_ID_KEY] = first_profile_id

    return config

def set_default_llm_profile(config: dict, profile_id: str) -> dict:
    """设置默认LLM配置"""
    # 确保配置已迁移
    config = migrate_legacy_config_to_profiles(config)

    profiles = config.get(LLM_PROFILES_KEY, {}).get("profiles", [])

    # 重置所有配置的默认状态
    for profile in profiles:
        profile["is_default"] = False

    # 设置新的默认配置
    for profile in profiles:
        if profile.get("id") == profile_id:
            profile["is_default"] = True
            break
    else:
        raise ValueError(f"找不到配置ID '{profile_id}'")

    config[LLM_PROFILES_KEY] = {"profiles": profiles}

    return config