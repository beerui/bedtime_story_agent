# config.py
import os


def _load_local_env(env_path=".env"):
    """轻量加载 .env，避免引入额外依赖。"""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            os.environ.setdefault(key, value)


_load_local_env()

# DashScope 是国内服务，代理（尤其 SOCKS）会导致 WebSocket/SSL 错误。
# 如果目标 API 是 DashScope，清除代理环境变量。
_base_url = os.getenv("PROXY_BASE_URL", "dashscope.aliyuncs.com")
if "dashscope" in _base_url:
    for _pvar in ("http_proxy", "https_proxy", "all_proxy",
                  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.pop(_pvar, None)

# macOS Python SSL 证书修复：使用 certifi 的 CA bundle
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("WEBSOCKET_CLIENT_CA_BUNDLE", certifi.where())
except ImportError:
    pass

# ==========================================
# 1. API 接口与模型配置（敏感信息全部从 .env 读取）
# ==========================================
# 统一使用阿里云 DashScope：一个 API key 同时覆盖文本(Qwen)、语音(CosyVoice)、视频(Wan2.x)
_dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()

API_CONFIG = {
    # 文本生成：优先使用独立配置，否则自动复用 DashScope key + Qwen
    "proxy_api_key": os.getenv("PROXY_API_KEY", "").strip() or _dashscope_key,
    "proxy_base_url": os.getenv(
        "PROXY_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ).strip(),
    "text_model": os.getenv("TEXT_MODEL", "qwen-plus").strip(),
    # 官方 OpenAI 配置 (用于生成图像)
    "image_api_key": os.getenv("IMAGE_API_KEY", "").strip(),
    # 阿里云 DashScope - CosyVoice / Wan2.x 视频
    "cosyvoice_api_key": os.getenv("COSYVOICE_API_KEY", "").strip() or _dashscope_key,
    # 推荐音色：longxiaochun / longfeiye / longyue_v3 等
    # 声音克隆：将此值设为参考音频的 HTTP URL（需先开通 DashScope 克隆权限）
    "tts_voice": os.getenv("TTS_VOICE", "longyue_v3").strip(),
    # [环境音：…] 在音轨上插入的静音秒数（后期可叠真实环境声）
    "tts_env_silence_seconds": float(os.getenv("TTS_ENV_SILENCE_SECONDS", "4.0")),
    # MiMo TTS 开关（设为 "mimo" 启用 MiMo TTS 作为首选引擎）
    "tts_engine": os.getenv("TTS_ENGINE", "cosyvoice").strip().lower(),
}

# ==========================================
# 1b. MiMo 配置（TTS + LLM）
# ==========================================
MI_API_KEY = os.getenv("MI_API_KEY", "").strip()
MI_BASE_URL = os.getenv("MI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1").strip()
MI_TEXT_MODEL = os.getenv("MI_TEXT_MODEL", "mimo-v2.5").strip()

# 预置音色列表（mimo-v2.5-tts 模型）
MIMO_PRESET_VOICES = {
    "冰糖": "bingtang",
    "茉莉": "moli",
    "苏打": "suda",
    "白桦": "baihua",
}

# 主题到 MiMo 音色的映射（未列出的主题使用 DEFAULT_VOICE）
THEME_MIMO_VOICE_MAP = {
    "末班地铁_卸下伪装": "苏打",
    "天台吹风_人际抽离": "苏打",
    "下班关机_反击上下级": "苏打",
    "深夜食堂_疯狂吐槽": "白桦",
    "深海独潜": "苏打",
    "失业缓冲期_职业空窗": "苏打",
    "AI焦虑夜_数字排毒": "苏打",
    "相亲过后_接纳单身": "茉莉",
    "父母渐老_生命的重量": "冰糖",
    "分手那晚_安静告别": "苏打",
}

# 六段式风格模板（progress 区间 → user content 风格指令）
MIMO_STYLE_TEMPLATES = [
    {
        "range": [0.0, 0.15],
        "style": "自然平静的语调，正常语速，清晰温暖，像在轻声讲故事",
    },
    {
        "range": [0.15, 0.30],
        "style": "稍微放慢语速，声音温暖柔和，带有安抚感",
    },
    {
        "range": [0.30, 0.50],
        "style": "轻柔缓慢的低语，逐渐放松，声音变得柔和",
    },
    {
        "range": [0.50, 0.70],
        "style": "缓慢低沉的耳边呢喃，声音越来越轻，像在耳边说话",
    },
    {
        "range": [0.70, 0.85],
        "style": "极轻极慢的催眠低语，慵懒欲睡，几乎听不见的声音",
    },
    {
        "range": [0.85, 1.00],
        "style": "几乎听不见的气声，像在梦中呢喃，极度缓慢轻柔",
    },
]

# 内联标记 → MiMo 音频标签映射
MIMO_AUDIO_TAGS = {
    "慢速": "缓慢",
    "轻声": "轻声",
    "极弱": "极轻低语",
}
# 视频总时长 (分钟)
TOTAL_VIDEO_MINUTES = int(os.getenv("TOTAL_VIDEO_MINUTES", "15"))

# True：不调用 assemble_pro_video（不压制 Final_Video_*.mp4）；仍会生成故事、配音、配图、AI 短片素材、封面等
SKIP_FINAL_VIDEO_RENDER = os.getenv("SKIP_FINAL_VIDEO_RENDER", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# edge-tts 中文音色表（CosyVoice 不可用时的降级选择）
EDGE_TTS_VOICES = {
    "female_gentle": "zh-CN-XiaoxiaoNeural",      # 女声，温柔（默认）
    "female_warm": "zh-CN-XiaoyiNeural",           # 女声，温暖
    "male_calm": "zh-CN-YunxiNeural",              # 男声，沉稳
    "male_deep": "zh-CN-YunjianNeural",            # 男声，低沉
}
EDGE_TTS_DEFAULT = os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural").strip()

# 主题到推荐音色的映射（未列出的主题使用 EDGE_TTS_DEFAULT）
THEME_VOICE_MAP = {
    # 职场情绪共鸣：男声更有「一起熬夜的兄弟」质感
    "末班地铁_卸下伪装": "zh-CN-YunxiNeural",
    "天台吹风_人际抽离": "zh-CN-YunxiNeural",
    "下班关机_反击上下级": "zh-CN-YunxiNeural",
    "深夜食堂_疯狂吐槽": "zh-CN-YunjianNeural",
    "深海独潜": "zh-CN-YunxiNeural",
    # 时代痛点（2026）：按情绪基调匹配音色
    "失业缓冲期_职业空窗": "zh-CN-YunxiNeural",     # 男声沉稳，像过来人
    "AI焦虑夜_数字排毒": "zh-CN-YunxiNeural",        # 男声，科技感但共情
    "相亲过后_接纳单身": "zh-CN-XiaoyiNeural",       # 女声温暖，像朋友
    "父母渐老_生命的重量": "zh-CN-XiaoxiaoNeural",   # 女声温柔，承接情绪
    "分手那晚_安静告别": "zh-CN-YunxiNeural",        # 男声陪伴感
}

# 大模型写稿时遵守的「语音友好」标记，语义对齐 CosyVoice SSML（停顿≈<break>，留白≈长静音）
# 文档: https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language
TTS_SCRIPT_DIRECTIVE = """
【语音合成标记规范 — 必须严格遵守】
1) 句内短停顿：使用 [停顿]（约 0.8 秒），或 [停顿500ms]、[停顿1s]；时长范围 50ms～10s。
2) 场景留白：单独一行 [环境音：简短描述]（如雨声）。该段不朗读，仅插入静音轨。
3) 动态语气微调 (核心催眠技巧)：当你需要改变语气时，可以在句首使用以下三种专属标记之一（仅作用于当前句子）：
   - [慢速] ：使该句语速额外降低 20%，适合引导放松。
   - [轻声] ：使该句音量额外减弱，适合耳边呢喃。
   - [极弱] ：使该句语速额外降低 30% 且音量额外减弱 70%，适合即将入睡的尾声。
   - 示例：[极弱] 你…已经睡着了。[停顿1s] [极弱] 慢慢地…沉入梦乡。
4) 阶段标记（必须使用）：在稿件对应位置插入阶段标记，用于全局韵律控制：
   - [阶段：引入] — 放在正文最开头
   - [阶段：深入] — 放在情绪开始沉浸的转折处
   - [阶段：尾声] — 放在准备引导入睡的段落开头
5) 绝对禁止使用其他无法发音的括号提示（如 [极缓的语气]、(叹气)），系统无法识别。
6) 正常断句仍用中文标点 。！？，；换行表示段落气口。

【全篇节奏结构 — 必须遵守】
- 引入段（前 30%）：正常句长 15-25 字，自然口语节奏，每 2-3 句用一个 [停顿]。
- 深入段（30%-70%）：句长渐短 10-18 字，[停顿] 频率增加，开始出现 [环境音：] 留白。
- 尾声段（后 30%）：极短句 5-12 字，大量 [停顿1s] 和 [停顿2s]，可用 [慢速]、[轻声]、[极弱]。
  最后 3-5 句必须极短，每句之间用 [停顿2s] 以上分隔。
""".strip()

# ==========================================
# 2. 内容配置（品牌 IP 与主题）
# ==========================================
# 成人版去掉具象的卡通名字，直接用"你"或不设名字，增强代入感。
PROTAGONIST = "你"

# ------------------------------------------------------------------
# 主题设计原则（2026-04 更新）：
#   每个主题必须回答三个问题——
#     1) 听众在搜索什么关键词时会找到我？  → search_keywords（SEO 资产）
#     2) 听众此刻的具体痛点是什么？       → pain_point（情绪定位）
#     3) 我用什么心理/感官技术帮他入睡？   → technique（专业背书）
#   只有这三者对齐，主题才不是"乱写"的，而是一个可被搜到、可被认同、可有效果的产品。
#
# 字段契约：
#   story_prompt  (str)      — LLM 写稿的核心指令，engine.py 直接读取
#   image_prompt  (str)      — 场景图生成的英文提示词
#   bgm_file      (str)      — 推荐 BGM 文件名（assets/bgm/ 下实际有的文件才会混音）
#   category      (str)      — 主题分类 key，见 THEME_CATEGORIES
#   pain_point    (str)      — 一句话描述听众此刻在感受什么
#   technique     (str)      — 使用的心理学/感官技术
#   search_keywords  list[str]  — SEO 关键词（单期页 <meta keywords> 会使用）
#   ideal_duration_min  int — 推荐时长（分钟），batch.py 可据此调字数
#   emotional_target (str)   — 听完后希望达到的情绪状态
# ------------------------------------------------------------------

THEMES = {
    # ==================================================================
    # A. 自然场景解压（nature_relax）— 低门槛、高搜索量、通用受众
    # ==================================================================
    "午夜慢车": {
        "story_prompt": "一列在午夜平稳行驶的绿皮火车，窗外是偶尔掠过的路灯和沉睡的田野。要求语言充满孤独但安全的氛围，带有催眠的节奏感，引导听众放下白天的焦虑，随着车厢的微微摇晃进入深度睡眠。",
        "image_prompt": "A cinematic vertical view from inside a dark, cozy sleeper train cabin at midnight, looking out the window at passing blurry lights, photorealistic, moody, relaxing, highly detailed.",
        "bgm_file": "train_night.mp3",
        "category": "nature_relax",
        "pain_point": "脑子停不下来，越躺越清醒",
        "technique": "节律性外部刺激（车厢摇晃+哐当声）带动身体进入副交感状态",
        "search_keywords": ["午夜火车", "绿皮车 助眠", "哄睡故事", "失眠 听什么", "催眠 故事"],
        "ideal_duration_min": 12,
        "emotional_target": "被温柔地带走的抽离感"
    },
    "雨夜山中小屋": {
        "story_prompt": "一个人呆在深山里的木屋中，外面下着淅淅沥沥的秋雨，屋内有一盏暖黄色的台灯。要求文案极其注重感官描写（雨声、木头的气味、被子的温度），用词克制、慵懒，带有极强的安全感。",
        "image_prompt": "A cinematic vertical view looking out a rainy window from inside a dark, cozy wooden cabin, dim warm lamp light, raindrops on glass, moody, photorealistic, serene atmosphere.",
        "bgm_file": "heavy_rain_roof.mp3",
        "category": "nature_relax",
        "pain_point": "外界太吵，想躲进一个只有自己的地方",
        "technique": "多感官包裹（雨声+木屋气味+被子温度）建立庇护感",
        "search_keywords": ["雨夜 助眠", "木屋 ASMR", "下雨 故事", "雨声 入睡", "安全感 冥想"],
        "ideal_duration_min": 12,
        "emotional_target": "被安全地包裹住的沉重感"
    },
    "深夜无人咖啡馆": {
        "story_prompt": "一家开在城市角落的深夜咖啡馆，外面下着小雪。你是唯一的客人，看着窗外偶尔经过的车辆。引导听众把脑海中繁杂的思绪像窗外的雪花一样慢慢沉淀下来。",
        "image_prompt": "A cinematic vertical view from inside a dark, empty late-night cafe looking out at a quiet snowy city street, warm indoor lighting contrasting with cold blue streetlights, photorealistic, lofi aesthetic.",
        "bgm_file": "cafe_rain_lofi.mp3",
        "category": "nature_relax",
        "pain_point": "白天人多太累，想一个人安静待一会",
        "technique": "冷暖对比（外冷内暖）+ 比喻沉淀（思绪→雪花）",
        "search_keywords": ["深夜咖啡馆", "lofi 助眠", "独处 放松", "下雪 故事", "都市孤独"],
        "ideal_duration_min": 10,
        "emotional_target": "与世界微妙分离、但不孤单"
    },
    "篝火与星空": {
        "story_prompt": "独自一人在空旷的峡谷里露营，面前是一堆燃烧的篝火，抬头是浩瀚的银河。要求语言深邃，通过对比宇宙的庞大与个人的渺小，帮助听众释然现实生活中的执念和压力。",
        "image_prompt": "A cinematic vertical view of a warm glowing campfire in a dark canyon, vast starry night sky above, hyper-realistic, majestic, deep and calming atmosphere.",
        "bgm_file": "campfire_crickets.mp3",
        "category": "nature_relax",
        "pain_point": "琐事压垮，急需把自己从小事里拔出来",
        "technique": "宇宙尺度对照（Cosmic Perspective）消解日常执念",
        "search_keywords": ["星空 助眠", "篝火 冥想", "露营 故事", "释怀 放松", "银河 催眠"],
        "ideal_duration_min": 14,
        "emotional_target": "渺小但安宁的敬畏感"
    },
    "深海独潜": {
        "story_prompt": "模拟一次极其缓慢、安全的深海下潜体验。随着光线慢慢变暗，周围只剩下自己平稳的呼吸声和偶尔游过的发光生物。加入身体扫描（Body Scan）的冥想引导，让听众感受身体各个部位的彻底放松和下沉。",
        "image_prompt": "A cinematic vertical underwater view descending into the deep ocean, faint bioluminescent creatures, dark tranquil blue waters, photorealistic, deeply calming and mysterious.",
        "bgm_file": "scuba_breathing.mp3",
        "category": "nature_relax",
        "pain_point": "身体绷着睡不着，需要被引导放松每一处",
        "technique": "Body Scan 躯体扫描 + 缓慢下潜隐喻身体沉入床垫",
        "search_keywords": ["身体扫描", "深海 冥想", "body scan", "躯体放松", "潜水 助眠"],
        "ideal_duration_min": 15,
        "emotional_target": "身体完全交付给床铺的沉重感"
    },

    # ==================================================================
    # B. 循证心理技术（clinical_technique）— 有理论基础，付费转化潜力高
    # ==================================================================
    "溪流落叶_认知解离": {
        "story_prompt": "基于心理学『认知解离』技术。引导听众想象自己坐在秋天宁静的溪水边。让听众把脑海中繁杂、焦虑的念头，想象成一片片落叶，轻轻放在溪水上，看着它们随波逐流、慢慢远去。语言极度舒缓、接纳，不评判任何情绪。",
        "image_prompt": "A cinematic vertical view of a tranquil forest stream in autumn, gentle water flow, golden and red leaves floating on the surface, soft lighting, photorealistic, deeply calming.",
        "bgm_file": "gentle_stream.mp3",
        "category": "clinical_technique",
        "pain_point": "想东想西停不下来，负面念头反复纠缠",
        "technique": "ACT 认知解离（Cognitive Defusion）：把念头与自我分离",
        "search_keywords": ["认知解离", "ACT", "停止反刍思维", "焦虑 冥想", "胡思乱想 睡不着"],
        "ideal_duration_min": 13,
        "emotional_target": "看着念头来去而不被卷入的旁观感"
    },
    "极光冰屋_安全岛": {
        "story_prompt": "基于心理学『安全岛』技术。听众正躺在冰岛全封闭的厚重玻璃穹顶屋里，外面是零下三十度的风雪，屋内是极其温暖的被窝和恒温。强调外面的一切压力、工作、他人都绝对无法进入这个空间。在这里，唯一需要做的事就是休息。",
        "image_prompt": "A cinematic vertical view from inside a cozy warm glass igloo, looking up at a spectacular green aurora borealis in the night sky, thick warm blankets in foreground, photorealistic, ultimate safe and cozy aesthetic.",
        "bgm_file": "muffled_blizzard.mp3",
        "category": "clinical_technique",
        "pain_point": "有解不开的事，觉得自己随时会被什么击中",
        "technique": "Safe Place Imagery（安全岛意象）：创伤/焦虑情境下的心理庇护",
        "search_keywords": ["安全岛", "safe place", "创伤后放松", "PTSD 睡眠", "极光 冥想"],
        "ideal_duration_min": 13,
        "emotional_target": "世界被挡在外面的绝对安全感"
    },
    "阳光沙滩_自律训练": {
        "story_prompt": "基于心理学『自律训练法』与躯体扫描。听众正躺在傍晚余温未散的柔软沙滩上。使用极慢的语速，依次引导听众感受双脚、双腿、手臂、躯干像灌了铅一样沉重、完全陷入沙子里，并感受到夕阳照在皮肤上的微热感。彻底放弃对身体的控制。",
        "image_prompt": "A cinematic vertical view of a tranquil beach at late sunset, soft glowing warm light on the sand, point of view looking at the calm ocean horizon, highly detailed, peaceful.",
        "bgm_file": "slow_ocean_waves.mp3",
        "category": "clinical_technique",
        "pain_point": "四肢紧绷、肩颈僵硬，身体不放松没法睡",
        "technique": "Autogenic Training 自律训练 + 沉重/温暖暗示",
        "search_keywords": ["自律训练", "自体训练法", "肌肉放松", "沙滩 催眠", "身体沉重"],
        "ideal_duration_min": 14,
        "emotional_target": "手脚像灌铅一样沉沉陷下的释放感"
    },
    "夏日午睡_怀旧退行": {
        "story_prompt": "利用怀旧感引发心理放松。设定在一个无忧无虑的童年夏日午后，老风扇在转，知了在叫。暗示所有作业都已经写完，大人不在家，没有任何人会来催促你做任何事。给予听众'现在可以合法且彻底地浪费时间、安心睡去'的心理许可。",
        "image_prompt": "A cinematic vertical view of a dimly lit vintage room in summer, sunlight filtering through curtains, an old oscillating fan, nostalgic lofi aesthetic, deep relaxing shadows, photorealistic.",
        "bgm_file": "old_fan_cicadas.mp3",
        "category": "clinical_technique",
        "pain_point": "成人责任太重，渴望卸下所有身份",
        "technique": "心理退行（Regression）：回到前责任期的放松状态",
        "search_keywords": ["童年回忆", "午睡 助眠", "怀旧 放松", "卸下压力", "夏天 故事"],
        "ideal_duration_min": 11,
        "emotional_target": "可以心安理得地什么都不做的许可感"
    },

    # ==================================================================
    # C. 情绪共鸣夜（emotional_resonance）— 职场/都市情绪急救，爆款流量
    # ==================================================================
    "末班地铁_卸下伪装": {
        "story_prompt": "场景是深夜空荡荡的末班地铁。用第二人称'你'。描述车厢的摇晃、车窗玻璃上映出的疲惫面容。文案要替听众叹一口气，告诉他：'今天辛苦了，在这里你可以不用假装情绪稳定，不用回复任何人的消息。随着列车的行驶，把白天的烦恼都甩在身后吧。'",
        "image_prompt": "A cinematic vertical view from inside an empty subway train at night, warm dim lights, dark window reflecting city lights outside, lonely but peaceful atmosphere, photorealistic, lofi aesthetic.",
        "bgm_file": "subway_ride_night.mp3",
        "category": "emotional_resonance",
        "pain_point": "假装了一天，想卸下表情",
        "technique": "共情叹息 + 第二人称亲密陪伴",
        "search_keywords": ["末班地铁", "加班 回家", "都市 孤独", "上班累", "深夜 通勤"],
        "ideal_duration_min": 10,
        "emotional_target": "被看见的松弛感"
    },
    "天台吹风_人际抽离": {
        "story_prompt": "场景是深夜无人的公司天台或楼道。用第二人称。吐槽白天办公室里的假笑、毫无意义的寒暄和复杂的人际关系。然后话锋一转，引导听众感受此刻夜晚的微风：'不用讨好任何人，做个不合群的人也没关系。深呼吸，把那些乌烟瘴气都吐出去。'",
        "image_prompt": "A cinematic vertical view looking down from a high office building rooftop at night, glowing city lights below, dark moody foreground, solitary and peaceful, photorealistic.",
        "bgm_file": "city_night_breeze.mp3",
        "category": "emotional_resonance",
        "pain_point": "社交疲惫，讨好累了",
        "technique": "吐槽-接纳-身体呼吸三段式情绪引导",
        "search_keywords": ["社交疲惫", "社恐", "办公室 人际", "讨好型人格", "不合群"],
        "ideal_duration_min": 10,
        "emotional_target": "可以做自己、不用讨好的空旷感"
    },
    "下班关机_反击上下级": {
        "story_prompt": "场景是下班回到家，刚刚洗完一个热水澡。提到那个总是半夜发消息的领导，或是那些永远完不成的KPI。告诉听众：'工作只是谋生的工具，你的价值不需要由老板来定义。现在，关掉手机，不理会工作群的红点。你的私人时间，神圣不可侵犯。'",
        "image_prompt": "A cinematic vertical view of a cozy bedroom at night, a glowing desk lamp illuminating a closed laptop, a hot cup of tea steaming on the desk, deep shadows, safe and warm, highly detailed.",
        "bgm_file": "rain_and_tea.mp3",
        "category": "emotional_resonance",
        "pain_point": "领导 PUA、消息炸群、界限被踩",
        "technique": "工作与自我价值解耦（内在价值论）",
        "search_keywords": ["反内卷", "拒绝 加班", "上司 PUA", "下班不回消息", "工作界限"],
        "ideal_duration_min": 11,
        "emotional_target": "关机一刻的神圣主权感"
    },
    "深夜食堂_疯狂吐槽": {
        "story_prompt": "场景是街角冒着热气的深夜关东煮小摊/面馆。以老朋友的口吻，用带着一点黑色幽默的语气，吐槽今天遇到的奇葩客户或离谱规定。在吐槽完之后，话锋变暖：'吃完这口热乎的，我们就把今天的倒霉事都翻篇吧。明天又是新的一天，先睡个好觉。'",
        "image_prompt": "A cinematic vertical view of a cozy glowing late-night food stall on a dark rainy street, steam rising from hot food, neon lights reflecting in puddles, cyberpunk/lofi chill vibe, photorealistic.",
        "bgm_file": "lofi_noodle_stall.mp3",
        "category": "emotional_resonance",
        "pain_point": "今天太离谱，不吐一顿睡不着",
        "technique": "黑色幽默释放 + 热食身体安慰",
        "search_keywords": ["深夜食堂", "吐槽 解压", "奇葩同事", "烟火气", "深夜 治愈"],
        "ideal_duration_min": 11,
        "emotional_target": "笑着把烂事翻篇的释然"
    },

    # ==================================================================
    # D. 时代痛点疗愈（zeitgeist_2026）— 搜索热度持续攀升的 2026 当下情绪
    # ==================================================================
    "失业缓冲期_职业空窗": {
        "story_prompt": "场景是一个裁员后或主动辞职的平常下午，你回到家，工位的杂物还散落在地上没有整理。用第二人称，温柔地告诉他：'空窗期不是失败，是换气口。简历可以明天再改，猎头的消息可以明天再回。现在，把简历放进抽屉，关上灯，允许自己什么都不做。你不是只有一个职位，你还是你。'引导慢呼吸，用物理动作（拉上窗帘/深呼吸）标记「今天结束了」。",
        "image_prompt": "A cinematic vertical view of a quiet afternoon apartment, a closed laptop on a desk with soft late-afternoon light, peaceful and grounded atmosphere, photorealistic.",
        "bgm_file": "afternoon_quiet.mp3",
        "category": "zeitgeist_2026",
        "pain_point": "裁员/空窗期的自我否定和未来不确定",
        "technique": "自我价值与职业角色解耦 + 物理锚点标记（简历入抽屉）",
        "search_keywords": ["裁员 焦虑", "失业 失眠", "职业空窗", "中年危机", "被辞退 怎么办"],
        "ideal_duration_min": 12,
        "emotional_target": "允许自己暂停的心安感"
    },
    "AI焦虑夜_数字排毒": {
        "story_prompt": "场景是关掉所有屏幕、断网一晚的卧室。用第二人称，承认听众的恐惧：'AI 每周都有新版本，你很怕被甩下。'然后引导：'但你现在握住的床单，感觉得到每一根棉线的纹理——这是任何 AI 都没办法替你经历的。你的身体、你的痛觉、你被风吹到脸上的感觉，就是你无法被复制的那部分。'引导听众把手机放远、深呼吸、回到身体。",
        "image_prompt": "A cinematic vertical view of a dark bedroom with a phone face-down on a nightstand, soft bedside lamp glow, hand resting on soft cotton sheets, photorealistic, grounding atmosphere.",
        "bgm_file": "offline_night.mp3",
        "category": "zeitgeist_2026",
        "pain_point": "被 AI 取代焦虑 + 数字过载",
        "technique": "具身化（Embodiment）锚定：用触觉/本体感将注意力拉回身体",
        "search_keywords": ["AI 焦虑", "被 AI 取代", "数字排毒", "关机 入睡", "科技焦虑"],
        "ideal_duration_min": 11,
        "emotional_target": "我是有身体的人、不可被替代的归属感"
    },
    "相亲过后_接纳单身": {
        "story_prompt": "场景是一次相亲后，你回到家，脱掉高跟鞋或皮鞋，瘫在沙发上。用第二人称（性别中立），替听众叹息：'被评判了一小时，被父母追问一整周，累得比上班还累。'然后温柔地说：'你不是在市场上的一件商品。你的价值不在于有没有合适的对象。今晚，把所有亲戚群静音，把自我评分卸下，一个人好好睡一觉——这是你欠自己的。'",
        "image_prompt": "A cinematic vertical view of a cozy living room at night, shoes kicked off by a sofa, soft warm lamp, empty but peaceful, photorealistic.",
        "bgm_file": "home_alone_night.mp3",
        "category": "zeitgeist_2026",
        "pain_point": "相亲/催婚的被评判感、被物化感",
        "technique": "去商品化自我叙事 + 家庭期待与个人价值解耦",
        "search_keywords": ["相亲 失败", "催婚 压力", "单身 焦虑", "过年 被催婚", "婚恋 焦虑"],
        "ideal_duration_min": 11,
        "emotional_target": "卸下被评价身份的松弛"
    },
    "父母渐老_生命的重量": {
        "story_prompt": "场景是收到父母体检报告或家里电话后的深夜。第二人称温柔承认：'你今天第一次意识到，你的父母在变老——比你想象的快。'不回避恐惧，但引导听众回到可控的动作：'你不能让时间停下，但你可以明天打一个电话，可以周末回去吃一顿饭。今晚先睡好，这件事需要你有力气。'用节律呼吸让情绪沉淀。",
        "image_prompt": "A cinematic vertical view of an evening kitchen table, a half-drunk cup of tea, a phone face-down, soft window light, emotionally rich and grounding atmosphere, photorealistic.",
        "bgm_file": "quiet_evening.mp3",
        "category": "zeitgeist_2026",
        "pain_point": "父母健康问题/衰老带来的存在焦虑",
        "technique": "情绪承认 + 可控动作锚定（打电话/回家）",
        "search_keywords": ["父母 生病", "父母 变老", "家人 担心", "尽孝 焦虑", "中年 家庭"],
        "ideal_duration_min": 12,
        "emotional_target": "带着脆弱但踏实的睡眠"
    },
    "分手那晚_安静告别": {
        "story_prompt": "场景是分手当晚的卧室。不回避痛，用第二人称承认：'你心里有一个洞，现在不想被劝好。'引导听众不要急着屏蔽对方/删除聊天记录，而是把那些回忆轻轻放在一边：'不用今晚就翻篇，但今晚先合上它。像合上一本你看过很多遍、终于要放回书架的书。'缓慢呼吸，引导身体先于心先睡着。",
        "image_prompt": "A cinematic vertical view of a dim bedroom at night, a single lamp, a closed book on the nightstand, blurred photo frame face-down, photorealistic, emotionally heavy but peaceful.",
        "bgm_file": "gentle_rain_room.mp3",
        "category": "zeitgeist_2026",
        "pain_point": "刚分手/失恋的情绪溢出",
        "technique": "不回避情绪 + 象征性「合上」动作（不删、但先合上）",
        "search_keywords": ["失恋 睡不着", "分手 当晚", "情伤 助眠", "感情 难受", "失恋 故事"],
        "ideal_duration_min": 13,
        "emotional_target": "身体先放下、心暂缓的释然"
    }
}


# ==========================================
# 2b. 主题分类（UI 过滤 / SEO 分组用，不影响生成）
# ==========================================
THEME_CATEGORIES = {
    "nature_relax": {
        "label": "自然场景解压",
        "description": "低门槛、通用受众的自然场景。无需心理学前置理解，听众只要「放松」即可。",
        "seo_keywords": ["助眠故事", "白噪音", "ASMR", "自然声", "睡前放松"]
    },
    "clinical_technique": {
        "label": "循证心理技术",
        "description": "基于 ACT/CBT-I/正念的临床级睡眠干预技术。适合反刍思维、创伤、慢性失眠者。",
        "seo_keywords": ["失眠疗法", "认知解离", "正念冥想", "安全岛", "躯体扫描", "ACT"]
    },
    "emotional_resonance": {
        "label": "情绪共鸣夜",
        "description": "职场/都市情绪急救。用吐槽-接纳-放下的三段式结构释放当天积累的压力。",
        "seo_keywords": ["职场焦虑", "加班 助眠", "情绪释放", "都市孤独", "下班 放松"]
    },
    "zeitgeist_2026": {
        "label": "时代痛点疗愈",
        "description": "2026 当下爆发式增长的搜索热词对应场景：裁员 / AI 焦虑 / 相亲压力 / 父母健康 / 失恋。",
        "seo_keywords": ["裁员 焦虑", "AI 焦虑", "催婚 压力", "父母 健康", "失恋 助眠"]
    }
}


# 加载动态生成的自定义主题
_custom_themes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_themes.json")
if os.path.exists(_custom_themes_path):
    try:
        import json as _json
        with open(_custom_themes_path, "r", encoding="utf-8") as _f:
            _custom = _json.load(_f)
        THEMES.update(_custom)
    except Exception:
        pass

CURRENT_THEME = "午夜慢车"

# ==========================================
# 4. 韵律弧线配置 (Prosody Curve)
# ==========================================
PROSODY_CURVES = {
    "hypnotic": {
        "speed":  [(0.0, 1.0), (0.3, 0.9), (0.7, 0.75), (1.0, 0.55)],
        "volume": [(0.0, 1.0), (0.5, 0.85), (0.8, 0.6),  (1.0, 0.3)],
        "pause":  [(0.0, 0.3), (0.5, 0.6),  (0.8, 1.2),  (1.0, 2.0)],
    },
}
CURRENT_PROSODY_CURVE = "hypnotic"
# trigger rebuild 2026年 5月 1日 星期五 23时42分07秒 CST
