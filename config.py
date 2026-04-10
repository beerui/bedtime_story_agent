# config.py

# ==========================================
# 1. API 接口与模型配置 (根据截图更新)
# ==========================================
API_CONFIG = {
    # 你的代理接口配置 (用于生成故事文本)
    "proxy_api_key": "sk-2pLECgqYxdzXnPXL1iCKwkoT2PR5SDTCBlzto19eqHfq7DOe", # 替换为你配置的 PROXY_API_KEY
    "proxy_base_url": "https://open-ai-anthropic-api--motou2021.replit.app/v1",
    "text_model": "claude-haiku-4-5",     # 截图中的模型，也可以换成 gpt-5-mini

    # 官方 OpenAI 配置 (用于生成图像，如果代理也支持画图，可以将上面的 key 填入这里)
    "image_api_key": "sk-2pLECgqYxdzXnPXL1iCKwkoT2PR5SDTCBlzto19eqHfq7DOe",

    # 新增：顶级情绪语音大模型配置 (阿里云 DashScope - CosyVoice)
    # 如果留空，系统将自动降级使用免费的微软 Edge-TTS
    "cosyvoice_api_key": "sk-5596d7a54f4f48e1a12cc7a7d176516a", # <-- 在这里填入阿里云的 API Key (例如: sk-xxxxxx)
    
    # 推荐的治愈系声音：
    # "longxiaochun" (龙小淳 - 极度温柔治愈的女声)
    # "longfeiye" (龙飞夜 - 沉稳磁性的深夜男声)
    "tts_voice": "longyue_v3",
    # [环境音：…] 在音轨上插入的静音秒数（后期可叠真实环境声）
    "tts_env_silence_seconds": 4.0,
}
# 视频总时长 (分钟)
TOTAL_VIDEO_MINUTES = 15

# True：不调用 assemble_pro_video（不压制 Final_Video_*.mp4）；仍会生成故事、配音、配图、AI 短片素材、封面等
SKIP_FINAL_VIDEO_RENDER = True

# 大模型写稿时遵守的「语音友好」标记，语义对齐 CosyVoice SSML（停顿≈<break>，留白≈长静音）
# 文档: https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language
TTS_SCRIPT_DIRECTIVE = """
【语音合成标记规范 — 必须严格遵守】
1) 句内短停顿：使用 [停顿]（约 0.8 秒），或 [停顿500ms]、[停顿1s]；时长范围 50ms～10s。
2) 场景留白：单独一行 [环境音：简短描述]（如雨声）。该段不朗读，仅插入静音轨。
3) 动态语气微调 (核心催眠技巧)：当你需要改变语气时，可以在句首使用以下三种专属标记之一（仅作用于当前句子）：
   - [慢速] ：使该句语速降低 20%，适合引导放松。
   - [轻声] ：使该句音量减弱，适合耳边呢喃。
   - [极弱] ：使该句语速极慢且音量极弱，适合即将入睡的尾声。
   - 示例：[极弱] 你…已经睡着了。[停顿1s] [极弱] 慢慢地…沉入梦乡。
4) 绝对禁止使用其他无法发音的括号提示（如 [极缓的语气]、(叹气)），系统无法识别。
5) 正常断句仍用中文标点 。！？，；换行表示段落气口。
""".strip()

# ==========================================
# 2. 内容配置 (品牌 IP 与主题)
# ==========================================
# 成人版建议去掉具象的卡通名字，直接用“你”或者不设置名字，增强代入感。
PROTAGONIST = "你" 

THEMES = {
    "午夜慢车": {
        "story_prompt": "一列在午夜平稳行驶的绿皮火车，窗外是偶尔掠过的路灯和沉睡的田野。要求语言充满孤独但安全的氛围，带有催眠的节奏感，引导听众放下白天的焦虑，随着车厢的微微摇晃进入深度睡眠。",
        "image_prompt": "A cinematic vertical view from inside a dark, cozy sleeper train cabin at midnight, looking out the window at passing blurry lights, photorealistic, moody, relaxing, highly detailed.",
        "bgm_file": "train_night.mp3"  # 建议搭配：火车车厢内有节奏的“哐当”声
    },
    "雨夜山中小屋": {
        "story_prompt": "一个人呆在深山里的木屋中，外面下着淅淅沥沥的秋雨，屋内有一盏暖黄色的台灯。要求文案极其注重感官描写（雨声、木头的气味、被子的温度），用词克制、慵懒，带有极强的安全感。",
        "image_prompt": "A cinematic vertical view looking out a rainy window from inside a dark, cozy wooden cabin, dim warm lamp light, raindrops on glass, moody, photorealistic, serene atmosphere.",
        "bgm_file": "heavy_rain_roof.mp3" # 建议搭配：雨打在木屋顶或玻璃上的声音
    },
    "深夜无人咖啡馆": {
        "story_prompt": "一家开在城市角落的深夜咖啡馆，外面下着小雪。你是唯一的客人，看着窗外偶尔经过的车辆。引导听众把脑海中繁杂的思绪像窗外的雪花一样慢慢沉淀下来。",
        "image_prompt": "A cinematic vertical view from inside a dark, empty late-night cafe looking out at a quiet snowy city street, warm indoor lighting contrasting with cold blue streetlights, photorealistic, lofi aesthetic.",
        "bgm_file": "cafe_rain_lofi.mp3"  # 建议搭配：极其微弱的咖啡机待机声 + 窗外闷闷的街道底噪
    },
    "篝火与星空": {
        "story_prompt": "独自一人在空旷的峡谷里露营，面前是一堆燃烧的篝火，抬头是浩瀚的银河。要求语言深邃，通过对比宇宙的庞大与个人的渺小，帮助听众释然现实生活中的执念和压力。",
        "image_prompt": "A cinematic vertical view of a warm glowing campfire in a dark canyon, vast starry night sky above, hyper-realistic, majestic, deep and calming atmosphere.",
        "bgm_file": "campfire_crickets.mp3" # 建议搭配：柴火噼啪声 + 偶尔的风声
    },
    "深海独潜": {
        "story_prompt": "模拟一次极其缓慢、安全的深海下潜体验。随着光线慢慢变暗，周围只剩下自己平稳的呼吸声和偶尔游过的发光生物。加入身体扫描（Body Scan）的冥想引导，让听众感受身体各个部位的彻底放松和下沉。",
        "image_prompt": "A cinematic vertical underwater view descending into the deep ocean, faint bioluminescent creatures, dark tranquil blue waters, photorealistic, deeply calming and mysterious.",
        "bgm_file": "scuba_breathing.mp3"  # 建议搭配：深海缓慢的水流声 + 极其舒缓的呼吸声
    },
    # ==========================================
    # 3. 深度心理疗愈主题 (成人高级睡眠干预)
    # ==========================================

    "溪流落叶_认知解离": {
        # 心理学机制：ACT（接纳承诺疗法）中的认知解离。帮助大脑过度活跃（Overthinking）的人，把焦虑的念头具象化并抽离。
        "story_prompt": "基于心理学『认知解离』技术。引导听众想象自己坐在秋天宁静的溪水边。让听众把脑海中繁杂、焦虑的念头，想象成一片片落叶，轻轻放在溪水上，看着它们随波逐流、慢慢远去。语言极度舒缓、接纳，不评判任何情绪。",
        "image_prompt": "A cinematic vertical view of a tranquil forest stream in autumn, gentle water flow, golden and red leaves floating on the surface, soft lighting, photorealistic, deeply calming.",
        "bgm_file": "gentle_stream.mp3"  # 建议搭配：极其平缓的溪流声
    },
    
    "极光冰屋_安全岛": {
        # 心理学机制：创伤与压力治疗中的“安全岛（Safe Place Imagery）”。利用极致的内外反差，建立不可被外界打扰的绝对防御感。
        "story_prompt": "基于心理学『安全岛』技术。听众正躺在冰岛全封闭的厚重玻璃穹顶屋里，外面是零下三十度的风雪，屋内是极其温暖的被窝和恒温。强调外面的一切压力、工作、他人都绝对无法进入这个空间。在这里，唯一需要做的事就是休息。",
        "image_prompt": "A cinematic vertical view from inside a cozy warm glass igloo, looking up at a spectacular green aurora borealis in the night sky, thick warm blankets in foreground, photorealistic, ultimate safe and cozy aesthetic.",
        "bgm_file": "muffled_blizzard.mp3" # 建议搭配：极度沉闷、被隔绝的窗外风雪声（要闷，不能尖锐）
    },

    "阳光沙滩_自律训练": {
        # 心理学机制：自律训练法（Autogenic Training）。通过语言暗示四肢的“沉重感”和“温暖感”，直接诱发副交感神经活动，降低心率。
        "story_prompt": "基于心理学『自律训练法』与躯体扫描。听众正躺在傍晚余温未散的柔软沙滩上。使用极慢的语速，依次引导听众感受双脚、双腿、手臂、躯干像灌了铅一样沉重、完全陷入沙子里，并感受到夕阳照在皮肤上的微热感。彻底放弃对身体的控制。",
        "image_prompt": "A cinematic vertical view of a tranquil beach at late sunset, soft glowing warm light on the sand, point of view looking at the calm ocean horizon, highly detailed, peaceful.",
        "bgm_file": "slow_ocean_waves.mp3" # 建议搭配：极其缓慢、有节律的海浪拍岸声
    },

    "夏日午睡_怀旧退行": {
        # 心理学机制：心理退行（Regression）。唤起童年最无忧无虑的低心理负荷状态，卸下成年人的社会角色和责任疲惫。
        "story_prompt": "利用怀旧感引发心理放松。设定在一个无忧无虑的童年夏日午后，老风扇在转，知了在叫。暗示所有作业都已经写完，大人不在家，没有任何人会来催促你做任何事。给予听众“现在可以合法且彻底地浪费时间、安心睡去”的心理许可。",
        "image_prompt": "A cinematic vertical view of a dimly lit vintage room in summer, sunlight filtering through curtains, an old oscillating fan, nostalgic lofi aesthetic, deep relaxing shadows, photorealistic.",
        "bgm_file": "old_fan_cicadas.mp3" # 建议搭配：老式风扇转动的嗡嗡声 + 远处的知了声
    },
    # ==========================================
    # 4. 职场情绪共鸣与深夜治愈主题 (爆款流量密码)
    # ==========================================
    # 建议将主角设置为“朋友”或直接用“你”，拉近心理距离。

    "末班地铁_卸下伪装": {
        # 核心情绪：疲惫、孤独、都市漂泊感
        "story_prompt": "场景是深夜空荡荡的末班地铁。用第二人称'你'。描述车厢的摇晃、车窗玻璃上映出的疲惫面容。文案要替听众叹一口气，告诉他：'今天辛苦了，在这里你可以不用假装情绪稳定，不用回复任何人的消息。随着列车的行驶，把白天的烦恼都甩在身后吧。'",
        "image_prompt": "A cinematic vertical view from inside an empty subway train at night, warm dim lights, dark window reflecting city lights outside, lonely but peaceful atmosphere, photorealistic, lofi aesthetic.",
        "bgm_file": "subway_ride_night.mp3"  # 建议搭配：列车行驶有节奏的“哐当”声，极其催眠
    },

    "天台吹风_人际抽离": {
        # 核心情绪：心累、社交恐惧、逃离办公室政治
        "story_prompt": "场景是深夜无人的公司天台或楼道。用第二人称。吐槽白天办公室里的假笑、毫无意义的寒暄和复杂的人际关系。然后话锋一转，引导听众感受此刻夜晚的微风：'不用讨好任何人，做个不合群的人也没关系。深呼吸，把那些乌烟瘴气都吐出去。'",
        "image_prompt": "A cinematic vertical view looking down from a high office building rooftop at night, glowing city lights below, dark moody foreground, solitary and peaceful, photorealistic.",
        "bgm_file": "city_night_breeze.mp3"  # 建议搭配：高处呼啸的微风声 + 极其微弱遥远的城市车流底噪
    },

    "下班关机_反击上下级": {
        # 核心情绪：反内卷、拒绝PUA、找回自我价值
        "story_prompt": "场景是下班回到家，刚刚洗完一个热水澡。提到那个总是半夜发消息的领导，或是那些永远完不成的KPI。告诉听众：'工作只是谋生的工具，你的价值不需要由老板来定义。现在，关掉手机，不理会工作群的红点。你的私人时间，神圣不可侵犯。'",
        "image_prompt": "A cinematic vertical view of a cozy bedroom at night, a glowing desk lamp illuminating a closed laptop, a hot cup of tea steaming on the desk, deep shadows, safe and warm, highly detailed.",
        "bgm_file": "rain_and_tea.mp3"  # 建议搭配：窗外的绵绵细雨声，对比出屋内的温暖安全
    },

    "深夜食堂_疯狂吐槽": {
        # 核心情绪：黑色幽默、释然、生活烟火气
        "story_prompt": "场景是街角冒着热气的深夜关东煮小摊/面馆。以老朋友的口吻，用带着一点黑色幽默的语气，吐槽今天遇到的奇葩客户或离谱规定。在吐槽完之后，话锋变暖：'吃完这口热乎的，我们就把今天的倒霉事都翻篇吧。明天又是新的一天，先睡个好觉。'",
        "image_prompt": "A cinematic vertical view of a cozy glowing late-night food stall on a dark rainy street, steam rising from hot food, neon lights reflecting in puddles, cyberpunk/lofi chill vibe, photorealistic.",
        "bgm_file": "lofi_noodle_stall.mp3"  # 建议搭配：Lofi 慢摇节奏 + 煮汤的咕噜声/微弱的雨声
    }
}

CURRENT_THEME = "午夜慢车"