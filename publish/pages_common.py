"""publish/pages_common.py -- shared constants and form builders used by multiple page modules."""
import textwrap

from .core import PODCAST_DESC, PODCAST_TITLE, _esc


def _build_placeholder_html(base_url: str) -> str:
    site_url = (base_url or "").rstrip("/")
    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{PODCAST_TITLE} · 准备中</title>
    <meta name="description" content="{PODCAST_DESC}">
    <meta name="robots" content="noindex">
    <style>
      body {{
        background: #06061a; color: #d4d4e0;
        font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
        display: flex; align-items: center; justify-content: center;
        min-height: 100vh; margin: 0; padding: 20px; text-align: center;
      }}
      .wrap {{ max-width: 520px; }}
      h1 {{
        font-size: 1.8rem; margin-bottom: 20px;
        background: linear-gradient(135deg, #f0c27f, #7c6ff7);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      }}
      p {{ line-height: 1.8; color: #9a9ab0; margin-bottom: 14px; }}
      code {{
        background: rgba(255,255,255,0.06);
        padding: 2px 8px; border-radius: 6px;
        font-family: ui-monospace, "SF Mono", Menlo, monospace;
        color: #f0c27f;
      }}
      ol {{ text-align: left; color: #9a9ab0; line-height: 2; padding-left: 1.2em; }}
      .dot {{
        display: inline-block; width: 8px; height: 8px;
        background: #f0c27f; border-radius: 50%;
        animation: pulse 1.6s ease-in-out infinite alternate;
        margin-right: 6px; vertical-align: middle;
      }}
      @keyframes pulse {{ 0% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <h1>助眠电台 · 准备中</h1>
        <p><span class="dot"></span>站点已部署，但还没有节目内容。</p>
        <p>通常是因为生产环节没能产出音频。最常见原因：</p>
        <ol>
          <li><code>DASHSCOPE_API_KEY</code> 没配在 Secrets 里</li>
          <li>API 配额耗尽（<code>batch.py</code> 会降级到 edge-tts，但仍需 Qwen 生成文本）</li>
          <li>workflow 首次运行时 <code>content</code> 分支不存在（正常，下次会建立）</li>
        </ol>
        <p>查看 Actions 标签页最新一次运行的日志，定位失败的 step。</p>
      </div>
    </body>
    </html>
    """)


def _build_newsletter_form(m: dict, context: str = "page") -> str:
    n = ((m or {}).get("newsletter") or {})
    if not n.get("enabled") or not n.get("endpoint_url"):
        return ""

    title = n.get("title") or "每周收到一封"
    desc = n.get("description") or "每周一封精选助眠内容 + 新期提醒，任何时候可取消。"
    button_label = n.get("button_label") or "订阅"
    success_msg = n.get("success_message") or "订阅成功 · 请查收邮件确认"
    endpoint = n.get("endpoint_url")
    hidden_provider_fields = ""
    if "formsubmit.co" in endpoint:
        hidden_provider_fields = (
            '<input type="hidden" name="_subject" value="助眠电台 · 新订阅请求">'
            '<input type="hidden" name="_template" value="table">'
            '<input type="hidden" name="_captcha" value="false">'
        )
    form_id = f"newsletter-{context}"
    privacy_prefix = "../" if context == "episode" else ""
    return textwrap.dedent(f"""
    <section class="newsletter" aria-labelledby="{form_id}-title">
      <div class="nl-body">
        <h3 id="{form_id}-title" class="nl-title">{_esc(title)}</h3>
        <p class="nl-desc">{_esc(desc)}</p>
      </div>
      <form class="nl-form" method="POST" action="{_esc(endpoint)}"
            onsubmit="return onNewsletterSubmit(this, event)">
        <input type="email" name="email" required autocomplete="email"
               placeholder="you@example.com" aria-label="邮箱地址">
        <input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
        {hidden_provider_fields}
        <button type="submit" data-success="{_esc(success_msg)}">{_esc(button_label)}</button>
      </form>
      <p class="nl-consent">点击订阅即同意 <a href="{privacy_prefix}privacy.html">隐私政策</a>——我们发新节目通知，不出售邮箱，可随时退订。</p>
    </section>""")


_NEWSLETTER_JS = """
function onNewsletterSubmit(form, e) {
  if (window.trackEvent) window.trackEvent('Subscribe Email');
  return true;
}
"""

_NEWSLETTER_CSS = """
.newsletter {
  margin: 28px 0; padding: 18px 22px;
  background: linear-gradient(135deg, rgba(240,194,127,0.06), rgba(124,111,247,0.04));
  border: 1px solid rgba(240,194,127,0.2);
  border-radius: 14px;
  display: grid; gap: 10px;
}
.nl-title { font-size: 0.92rem; font-weight: 600; color: #f0c27f; letter-spacing: 0.02em; }
.nl-desc { font-size: 0.78rem; color: #9a9ab0; line-height: 1.6; }
.nl-form { display: flex; gap: 8px; flex-wrap: wrap; }
.nl-form input[type="email"] {
  flex: 1 1 200px; min-width: 180px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  color: #d4d4e0; padding: 8px 14px;
  border-radius: 18px; font-size: 0.82rem;
  font-family: inherit;
}
.nl-form input[type="email"]:focus {
  outline: none; border-color: rgba(124,111,247,0.5);
  background: rgba(255,255,255,0.07);
}
.nl-form button {
  padding: 8px 20px; border-radius: 18px;
  background: linear-gradient(135deg, #7c6ff7, #9b6ff7);
  border: none; color: #fff;
  font-size: 0.82rem; font-family: inherit; cursor: pointer;
  transition: transform 0.2s ease;
}
.nl-form button:hover { transform: translateY(-1px); }
.nl-consent {
  font-size: 0.68rem; color: #7a7a9a; line-height: 1.5;
  margin: 0;
}
.nl-consent a { color: #9a9ab0; text-decoration: underline; }
.nl-consent a:hover { color: #7c6ff7; }
"""
