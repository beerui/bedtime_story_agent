"""publish/pages_legal.py -- legal, FAQ, about, sitemap, and robots generators."""
import html as html_mod
import json
import textwrap

from .core import (
    PODCAST_TITLE,
    _THEME_CATEGORIES,
    _THEMES,
    _breadcrumb_jsonld,
    _episode_slug,
    _esc,
)
from .pwa import _pwa_head
from .pages_common import (
    _NEWSLETTER_CSS,
    _NEWSLETTER_JS,
    _build_newsletter_form,
)
from .pages import _build_analytics_head


# ---------------------------------------------------------------------------
# Legal pages
# ---------------------------------------------------------------------------

def _legal_page_template(title: str, body_html: str, monetization: dict, base_url: str,
                          slug: str, breadcrumb_label: str) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/{slug}.html" if site_url else f"{slug}.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)
    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        (breadcrumb_label, ""),
    ])
    contact_email = ((m.get("social") or {}).get("contact_email") or "").strip() or "hello@bedtime.local"

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(title)} · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="{_esc(title)} — 助眠电台的{_esc(breadcrumb_label)}声明">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{_esc(title)}">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary">
    {breadcrumb_jsonld}
    {_pwa_head("")}
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.85;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 1.6rem; margin: 18px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .updated {{ color: var(--dim); font-size: 0.78rem; margin-bottom: 32px; }}
    h2 {{
      font-size: 1rem; font-weight: 600;
      margin: 28px 0 10px; color: var(--text);
      border-left: 3px solid var(--accent); padding-left: 10px;
    }}
    p {{ color: var(--text); margin-bottom: 14px; font-size: 0.92rem; }}
    ul, ol {{ padding-left: 22px; margin-bottom: 14px; }}
    li {{ color: var(--text); margin-bottom: 6px; font-size: 0.9rem; }}
    a {{ color: var(--accent); }}
    code {{
      background: rgba(255,255,255,0.06); padding: 1px 6px;
      border-radius: 5px; font-family: ui-monospace, Menlo, monospace;
      color: var(--warm); font-size: 0.86em;
    }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 0.82rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>{_esc(title)}</h1>
        <p class="updated">最后更新：2026-04-17</p>
        {body_html}
        <div class="footer">
          <a href="index.html">首页</a>
          <a href="about.html">关于</a>
          <a href="faq.html">FAQ</a>
          <a href="privacy.html">隐私</a>
          <a href="terms.html">条款</a>
          <a href="mailto:{_esc(contact_email)}">联系</a>
        </div>
      </div>
    </body>
    </html>
    """)


def generate_privacy_page(monetization: dict, base_url: str) -> str:
    m = monetization or {}
    contact_email = ((m.get("social") or {}).get("contact_email") or "").strip() or "hello@bedtime.local"
    n = (m.get("newsletter") or {})
    a = (m.get("analytics") or {})
    has_newsletter = bool(n.get("enabled") and n.get("endpoint_url"))
    has_analytics = bool(
        a.get("plausible_domain") or a.get("umami_website_id") or a.get("google_analytics_id")
    )

    body = f"""
        <h2>1. 我们收集什么</h2>
        <p>这个站点是一个静态生成的助眠音频站点，<strong>默认不收集任何个人身份信息</strong>。具体到各功能：</p>
        <ul>
          <li><strong>音频播放</strong>：浏览器本地播放，不上传任何收听记录到服务器。「继续收听」位置记忆只存在你设备的 <code>localStorage</code>，不离开你浏览器。</li>
          { '<li><strong>邮件订阅</strong>：你主动填写邮箱时，邮箱地址通过表单提交到我们配置的第三方服务（FormSubmit / Buttondown / Formspark 等），仅用于发送新节目通知。我们不出售、不与第三方共享你的邮箱用于其它目的。</li>' if has_newsletter else '<li><strong>邮件订阅</strong>：未启用。</li>' }
          { '<li><strong>分析埋点</strong>：使用第三方分析服务（Plausible / Umami / GA4 三选一）记录匿名访问统计——访问页面 / 播放事件 / 分享点击等聚合行为，<em>不</em>记录 IP / 设备指纹 / 个人身份。</li>' if has_analytics else '<li><strong>分析埋点</strong>：未启用，没有任何访问跟踪。</li>' }
        </ul>
        <h2>2. Cookie 与本地存储</h2>
        <p>站点本身<strong>不设置任何 Cookie</strong>。使用 <code>localStorage</code> 仅为本地功能（继续收听位置、用户偏好），数据从不离开你设备。</p>
        <p>如果启用了 Plausible / Umami（隐私友好）则不写 Cookie；GA4 启用时由 Google 写入分析 Cookie，受 Google 隐私政策约束。</p>
        <h2>3. 数据如何使用</h2>
        <ul>
          <li>邮件订阅地址：仅发送新节目通知 + 偶尔的精选内容</li>
          <li>聚合访问数据：用于改进哪些主题受欢迎、哪些页面跳出率高</li>
          <li>本地播放位置：让你下次回来能从离开的地方继续听</li>
        </ul>
        <h2>4. 第三方服务</h2>
        <p>站点托管在 GitHub Pages。音频文件、HTML、RSS 全部从 GitHub 服务器加载。订阅按钮跳转到 Apple Podcasts / Spotify / 小宇宙 等第三方播放器（受其各自隐私政策约束）。</p>
        <h2>5. 你的权利</h2>
        <p>你有权：</p>
        <ul>
          <li>退订邮件——任何邮件底部都有取消订阅链接</li>
          <li>清除本地数据——浏览器设置里清 <code>localStorage</code> / Cookie 即可</li>
          <li>查询/删除我们持有的关于你的数据——发邮件到 <a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a></li>
        </ul>
        <h2>6. 联系</h2>
        <p>关于隐私的任何问题，发邮件到 <a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a>，我们 7 天内回复。</p>
    """
    return _legal_page_template("隐私政策", body, monetization, base_url, "privacy", "隐私政策")


def generate_terms_page(monetization: dict, base_url: str) -> str:
    m = monetization or {}
    contact_email = ((m.get("social") or {}).get("contact_email") or "").strip() or "hello@bedtime.local"
    body = f"""
        <h2>1. 内容性质</h2>
        <p>本站全部音频内容由 <strong>AI 生成</strong>（文本：阿里云通义千问；语音：CosyVoice / edge-tts），背景音乐多为程序生成的棕噪声。剧本经过基于心理学（ACT 认知解离、安全岛意象、自律训练等）框架的提示词工程产出。</p>
        <p>详细生产流程公开在<a href="about.html">关于页</a>。</p>
        <h2>2. 不构成医疗建议</h2>
        <p><strong>本站不是医疗服务，不构成医学诊断或治疗建议。</strong>助眠音频不能替代专业医生对失眠、焦虑、抑郁等健康问题的诊治。</p>
        <p>如果你有持续 4 周以上的失眠、严重情绪困扰、或自伤念头，<strong>请及时联系精神科医生或拨打心理援助热线</strong>（北京 010-82951332，上海 021-63798990，全国 400-161-9995）。</p>
        <h2>3. 内容许可</h2>
        <p>站点代码采用 <a href="https://github.com/beerui/bedtime_story_agent/blob/main/LICENSE">MIT 许可</a> 开源。AI 生成的音频/文稿采用 <a href="https://creativecommons.org/licenses/by-nc/4.0/" target="_blank" rel="noopener">CC BY-NC 4.0</a>：</p>
        <ul>
          <li>个人收听 / 朋友圈分享 / 用作冥想课素材</li>
          <li>二次创作（剪辑、加字幕、双语翻译）需注明出处</li>
          <li>商业用途（包装成付费课程、培训卖钱）需联系我们获得书面授权</li>
          <li>训练 AI 模型——AI-generated content 不应被反喂回 AI 训练</li>
        </ul>
        <h2>4. 使用限制</h2>
        <ul>
          <li>不要在驾驶 / 操作机械时收听——音频会让你困倦</li>
          <li>未成年人收听需家长陪同（部分主题涉及成年人压力如裁员/分手等）</li>
          <li>使用降噪耳机时控制音量在 60 分贝以内</li>
        </ul>
        <h2>5. 服务可用性</h2>
        <p>站点免费提供，按"现状"提供，不保证 100% 可用。可能因 GitHub Pages 维护、CDN 故障或我们调整暂时不可访问。订阅 RSS 可在大多数情况下离线收听已下载的期。</p>
        <h2>6. 修改条款</h2>
        <p>我们可能更新本条款。重大改动会通过 RSS feed item 或邮件通知。继续使用即视为接受新条款。</p>
        <h2>7. 联系</h2>
        <p>关于条款的任何问题：<a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a></p>
    """
    return _legal_page_template("使用条款", body, monetization, base_url, "terms", "使用条款")


# ---------------------------------------------------------------------------
# generate_faq_page
# ---------------------------------------------------------------------------

def generate_faq_page(monetization: dict, base_url: str) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/faq.html" if site_url else "faq.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("FAQ", ""),
    ])

    qa_pairs = [
        ("这些助眠故事是 AI 生成的吗？能信吗？",
         "是。剧本由 Qwen 大模型生成，分三轮（大纲 → 扩写 → 润色），每篇完成后走 5 维 100 分制质量评估，低于 70 自动按反馈重写一次。每个主题都有明确的心理学锚点（痛点 / 技术 / 目标状态）注入 prompt——不是随机生成，而是按专业框架产出。生产流程完全透明，见关于页。"),
        ("真的能帮我入睡吗？依据是什么？",
         "基于循证心理学技术：ACT 认知解离（停止反刍思维）、Safe Place Imagery（安全岛意象）、Autogenic Training（自律训练法诱发副交感神经）、Body Scan（躯体扫描）、心理退行（回到低心理负荷的童年状态）。每一类主题对应一种技术。音频用韵律弧线引擎把语速从 1.0 渐变到 0.55，音量从 1.0 降到 0.3，模拟真人催眠师的节奏变化。"),
        ("一集多长合适？",
         "推荐 10-15 分钟。每个主题都声明了 ideal_duration_min（见主题页）：快速放松类 10 分钟，完整身体扫描类 15 分钟，情绪共鸣类 11 分钟。入睡前听 1-2 集即可。"),
        ("怎么订阅到播客 App？",
         "首页订阅区可以一键：Apple Podcasts 用 podcasts:// 协议直接唤起本机播客 App 订阅，无需提交目录；Spotify / 小宇宙 / Overcast / Bilibili 等按钮会跳到对应页面（如已配置）；RSS 按钮直接复制 feed 地址到任何播客 App。"),
        ("为什么不同主题用不同声音？",
         "每个主题在 THEME_VOICE_MAP 匹配了合适的音色：男声沉稳用于职场/AI 焦虑/失业类（像过来人陪伴），女声温柔用于情感疗愈类（承接情绪）。TTS 优先使用阿里 CosyVoice（自然度高），配额耗尽自动降级到免费的 edge-tts（微软语音）。"),
        ("你们怎么挣钱？",
         "透明披露（详见关于页）：打赏（一次性小额）、联盟商品推广（睡眠相关耳塞/眼罩/白噪音机，你不会多花钱）、品牌赞助位（出现会明确标注）、未来的会员内容（长版/无 BGM 纯人声版）。所有变现位都不会影响内容的心理学质量。"),
        ("可以用手机听吗？会耗流量吗？",
         "可以。音频是标准 MP3，每期 3-5MB。推荐订阅到 Apple Podcasts / Pocket Casts 等 App 并在 WiFi 下预下载，出门时离线听不耗流量。网页播放器也支持 SRT 字幕跟读。"),
        ("节目什么时候更新？",
         "北京时间每天 07:05 自动生产并部署一期新节目。18 个主题会在配置的 cron 触发时随机选（可以把 --themes 改成固定名单做连续主题）。RSS/小宇宙/Apple Podcasts 订阅会自动推送新期。"),
        ("如何给反馈或建议？",
         "联系邮箱见关于页。也欢迎在 GitHub 源码仓库开 issue（项目完全开源）。建议特别关注：哪个主题最帮助你入睡、哪个阶段（引入/深入/尾声）最有效——这些数据会指导后续主题设计。"),
    ]

    faq_jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qa_pairs
        ],
    }

    qa_html = "".join(
        f'<details class="qa"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>'
        for q, a in qa_pairs
    )

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>常见问题 · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="关于 AI 生成、心理学依据、订阅、变现、节目时长的常见问题解答。">
    <meta name="keywords" content="助眠 常见问题,AI 生成 助眠,助眠 心理学,播客 订阅,失眠 FAQ">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="常见问题 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="AI 生成可信吗？心理学依据是什么？怎么订阅？变现怎么做？">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    <script type="application/ld+json">{json.dumps(faq_jsonld, ensure_ascii=False)}</script>
    {breadcrumb_jsonld}
    {_pwa_head("")}
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.85;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 1.8rem; margin: 18px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 0.95rem; margin-bottom: 32px; }}
    .qa {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 0; margin-bottom: 12px;
      transition: all 0.2s ease;
    }}
    .qa[open] {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.25);
    }}
    .qa summary {{
      cursor: pointer; padding: 14px 18px;
      font-size: 0.92rem; font-weight: 600;
      list-style: none; position: relative;
      padding-right: 44px;
    }}
    .qa summary::-webkit-details-marker {{ display: none; }}
    .qa summary::after {{
      content: '+'; position: absolute; right: 18px; top: 50%;
      transform: translateY(-50%); color: var(--accent); font-size: 1.2rem;
      transition: transform 0.3s ease;
    }}
    .qa[open] summary::after {{ transform: translateY(-50%) rotate(45deg); }}
    .qa p {{
      padding: 0 18px 16px; color: var(--text);
      font-size: 0.87rem; line-height: 1.8;
    }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 0.82rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>常见问题</h1>
        <p class="lede">AI 生成的助眠音频需要回答的真实问题——透明比安慰更能建立信任。</p>
        {qa_html}
        <div class="footer">
          <a href="index.html">首页</a>
          <a href="about.html">关于</a>
          <a href="themes.html">全部主题</a>
          <a href="privacy.html">隐私</a>
          <a href="terms.html">条款</a>
          <a href="feed.xml">RSS</a>
        </div>
      </div>
    </body>
    </html>
    """)


# ---------------------------------------------------------------------------
# generate_about_page
# ---------------------------------------------------------------------------

def generate_about_page(monetization: dict, base_url: str) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/about.html" if site_url else "about.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("关于", ""),
    ])

    cat_sections: list[str] = []
    by_cat: dict[str, list[str]] = {}
    for name, cfg in (_THEMES or {}).items():
        by_cat.setdefault(cfg.get("category", "其他"), []).append(name)
    for cat_key, cat_cfg in (_THEME_CATEGORIES or {}).items():
        names = by_cat.get(cat_key, [])
        if not names:
            continue
        label = cat_cfg.get("label", cat_key)
        desc = cat_cfg.get("description", "")
        theme_list = "、".join(names)
        cat_sections.append(f"""
        <section class="cat">
          <h3>{_esc(label)} · {len(names)} 期</h3>
          <p class="cat-desc">{_esc(desc)}</p>
          <p class="cat-themes">{_esc(theme_list)}</p>
        </section>""")

    reveal_parts = []
    don = m.get("donation") or {}
    if don.get("enabled"):
        reveal_parts.append(f"<li>打赏（{_esc(don.get('label', '自愿'))}）— 一次性小额资助电台运营</li>")
    spon = m.get("sponsor_slot") or {}
    if spon.get("enabled"):
        reveal_parts.append("<li>品牌赞助 — 每期开头/结尾可能出现的品牌提及，会明确标注「赞助」字样</li>")
    aff = m.get("affiliates") or {}
    if aff.get("enabled"):
        reveal_parts.append("<li>联盟推荐 — 助眠相关商品（眼罩/白噪音机/耳塞等），通过链接购买你不会多花钱但电台会拿到一点分成</li>")
    prem = m.get("premium") or {}
    if prem.get("enabled"):
        reveal_parts.append("<li>会员内容 — 部分长版/无 BGM 纯人声版将对付费会员开放</li>")
    reveal_html = ""
    if reveal_parts:
        reveal_html = f"""
        <section class="trust">
          <h2>透明变现披露</h2>
          <p>我们相信助眠内容的本质是信任——所以你有权知道我们怎么挣钱：</p>
          <ul>{''.join(reveal_parts)}</ul>
          <p class="trust-note">所有变现位都不会影响内容本身的心理学质量。联盟商品是我们自己也会用的。</p>
        </section>"""

    contact_email = ((m.get("social") or {}).get("contact_email") or "").strip()
    contact_html = ""
    if contact_email:
        contact_html = f'<p class="contact">有建议或合作意向？<a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a></p>'

    newsletter_html = _build_newsletter_form(m, context="about")

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>关于 · {PODCAST_TITLE}</title>
    <meta name="description" content="助眠电台的设计理念、18 个主题 4 大分类的心理学基础、AI 生成流程透明披露、变现模式披露。">
    <meta name="keywords" content="助眠电台,关于,心理学,ACT,安全岛,韵律弧线,AI生成,催眠,冥想">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="关于 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="4 大分类 18 个主题的心理学基础 + 生产流程透明披露">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {breadcrumb_jsonld}
    {_pwa_head("")}
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.85;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 60px 20px 100px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 2rem; margin: 16px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 1.02rem; margin-bottom: 40px; }}
    h2 {{
      font-size: 1.15rem; font-weight: 600;
      margin: 40px 0 14px; color: var(--text);
      border-left: 3px solid var(--accent); padding-left: 12px;
    }}
    h3 {{ font-size: 1rem; font-weight: 600; margin: 20px 0 8px; color: var(--warm); }}
    p {{ color: var(--text); margin-bottom: 14px; font-size: 0.95rem; }}
    ul {{ padding-left: 20px; margin-bottom: 16px; }}
    li {{ color: var(--text); margin-bottom: 8px; font-size: 0.92rem; }}
    .cat {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px 20px; margin-bottom: 14px;
    }}
    .cat-desc {{ font-size: 0.88rem; color: var(--dim); margin-bottom: 8px; }}
    .cat-themes {{ font-size: 0.82rem; color: var(--warm); margin: 0; }}
    .process {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px; margin-top: 10px;
    }}
    .process ol {{ counter-reset: step; padding-left: 0; list-style: none; }}
    .process li {{
      position: relative; padding-left: 36px; counter-increment: step;
    }}
    .process li::before {{
      content: counter(step);
      position: absolute; left: 0; top: 0;
      width: 24px; height: 24px; border-radius: 50%;
      background: rgba(124,111,247,0.18); color: var(--accent);
      display: flex; align-items: center; justify-content: center;
      font-size: 0.75rem; font-weight: 600;
    }}
    .trust {{
      background: linear-gradient(135deg, rgba(240,194,127,0.06), rgba(124,111,247,0.04));
      border: 1px solid rgba(240,194,127,0.2);
      border-radius: 12px; padding: 20px 24px;
    }}
    .trust-note {{ color: var(--dim); font-size: 0.85rem; margin-top: 10px; }}
    .contact {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border); color: var(--dim);
    }}
    .contact a {{ color: var(--accent); }}
    {_NEWSLETTER_CSS}
    code {{
      background: rgba(255,255,255,0.06); padding: 1px 7px;
      border-radius: 5px; font-family: ui-monospace, Menlo, monospace;
      color: var(--warm); font-size: 0.88em;
    }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>关于助眠电台</h1>
        <p class="lede">用 AI 写稿、真人级韵律合成、心理学技术引导——每晚 10 分钟，把脑子里的白天声音关小。</p>
        <h2>这是什么</h2>
        <p>一个按主题批量生产的助眠音频电台。每一期由三轮 LLM 写稿（大纲 → 扩写 → 润色）+ 质量评分 + 低分自动重写组成；语音用韵律弧线引擎控制语速、音量、停顿从正常逐渐降到接近呢喃的状态；再叠上匹配的 BGM 和可选的双耳节拍。</p>
        <h2>4 大主题分类</h2>
        <p>18 个主题按「这对谁有用」分 4 类。每个主题都有明确的<strong>痛点 / 心理或感官技术 / 目标状态</strong>三要素——不是随便想一个场景。</p>
        {''.join(cat_sections)}
        <h2>韵律弧线引擎</h2>
        <p>普通 TTS 全篇匀速。我们用 Prosody Curve 分三段控制节奏：</p>
        <ul>
          <li><strong>引入段（前 30%）</strong>：<code>speed=1.0, vol=1.0, pause=0.3s</code> — 自然语速承认感受</li>
          <li><strong>深入段（30-70%）</strong>：<code>speed=0.82, vol=0.85, pause=0.6s</code> — 引导放松</li>
          <li><strong>尾声段（后 30%）</strong>：<code>speed=0.55, vol=0.3, pause=2.0s</code> — 接近呢喃、带入睡眠</li>
        </ul>
        <p>内联标记 <code>[慢速]</code>/<code>[轻声]</code>/<code>[极弱]</code> 是乘法叠加在曲线上——同一个标记越靠近尾声效果越强。</p>
        <h2>AI 生成流程透明披露</h2>
        <p>每期剧本的质量闭环：</p>
        <div class="process">
          <ol>
            <li><strong>大纲生成</strong>：把主题的 pain_point / technique / emotional_target 注入 prompt，LLM 输出三段式心理暗示大纲</li>
            <li><strong>扩写成稿</strong>：按目标字数扩写，必须具体承认痛点画面（禁止笼统「今天辛苦了」）</li>
            <li><strong>主编润色</strong>：去 AI 腔、禁用排比/反问/说教/集体措辞，保留所有韵律标记</li>
            <li><strong>质量评估</strong>：5 维各 20 分（催眠感 / 感官描写 / 节奏标记 / 去 AI 腔 / 痛点对齐）</li>
            <li><strong>低分重写</strong>：评分 &lt;70 自动按评审反馈重写一次，再次评分</li>
          </ol>
        </div>
        {reveal_html}
        <h2>技术栈</h2>
        <p>开源自治——<a href="https://github.com/beerui/bedtime_story_agent" target="_blank" rel="noopener" style="color:var(--accent)">GitHub 源码</a>。文本用 Qwen（通义千问），语音用 CosyVoice（配额耗尽自动降级 edge-tts），封面用 Pillow 生成，站点是纯 HTML/CSS/JS 无任何框架。</p>
        {newsletter_html}
        {contact_html}
      </div>
      <script>
      {_NEWSLETTER_JS}
      </script>
    </body>
    </html>
    """)


# ---------------------------------------------------------------------------
# generate_sitemap + generate_robots
# ---------------------------------------------------------------------------

def generate_sitemap(episodes: list[dict], base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    urls: list[str] = []
    homepage = f"{base}/" if base else "./"
    urls.append(f"""  <url>
    <loc>{homepage}</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""")
    for ep in episodes:
        loc = f"{base}/episodes/{_episode_slug(ep)}.html" if base else f"episodes/{_episode_slug(ep)}.html"
        lastmod = ep["timestamp"].strftime("%Y-%m-%d")
        folder = _episode_slug(ep)
        image_blocks = []
        for rel in (f"og/{folder}.png", f"covers/{folder}.png", f"scenes/{folder}.png"):
            img_loc = f"{base}/{rel}" if base else rel
            cap = (ep.get("title") or ep.get("theme") or "").strip()
            cap_x = html_mod.escape(cap, quote=False)
            image_blocks.append(
                f"""    <image:image>
      <image:loc>{img_loc}</image:loc>
      <image:caption>{cap_x}</image:caption>
    </image:image>"""
            )
        images_xml = "\n".join(image_blocks)
        urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
{images_xml}
  </url>""")
    cat_keys_used: set[str] = set()
    for ep in episodes:
        k = (_THEMES.get(ep["theme"]) or {}).get("category")
        if k:
            cat_keys_used.add(k)
    for ck in cat_keys_used:
        cloc = f"{base}/category/{ck}.html" if base else f"category/{ck}.html"
        urls.append(f"""  <url>
    <loc>{cloc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")
        floc = f"{base}/feed/{ck}.xml" if base else f"feed/{ck}.xml"
        urls.append(f"""  <url>
    <loc>{floc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>""")
    for theme_name, theme_cfg in (_THEMES or {}).items():
        if not theme_cfg.get("category"):
            continue
        tloc = f"{base}/theme/{theme_name}.html" if base else f"theme/{theme_name}.html"
        urls.append(f"""  <url>
    <loc>{tloc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.65</priority>
  </url>""")
    if _THEMES and _THEME_CATEGORIES:
        themes_loc = f"{base}/themes.html" if base else "themes.html"
        urls.append(f"""  <url>
    <loc>{themes_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
    about_loc = f"{base}/about.html" if base else "about.html"
    urls.append(f"""  <url>
    <loc>{about_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    faq_loc = f"{base}/faq.html" if base else "faq.html"
    urls.append(f"""  <url>
    <loc>{faq_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    stats_loc = f"{base}/stats.html" if base else "stats.html"
    urls.append(f"""  <url>
    <loc>{stats_loc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.5</priority>
  </url>""")
    for legal in ("privacy.html", "terms.html"):
        lloc = f"{base}/{legal}" if base else legal
        urls.append(f"""  <url>
    <loc>{lloc}</loc>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>""")
    body = "\n".join(urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
{body}
</urlset>
"""


def generate_robots(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    sitemap_url = f"{base}/sitemap.xml" if base else "sitemap.xml"
    return f"""User-agent: *
Allow: /

Sitemap: {sitemap_url}
"""
