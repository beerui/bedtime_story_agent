#!/usr/bin/env python3
"""从已生产内容生成播客订阅源和深色主题在线播放器。

将 outputs/ 目录中的音频、字幕、元数据打包为：
  site/index.html  — 深色助眠主题播放器（睡眠定时、字幕同步）
  site/feed.xml    — Podcast RSS 2.0 订阅源（兼容 Apple Podcasts / Spotify）

用法:
    python3 publish.py                      # 生成到 site/
    python3 publish.py --serve              # 生成 + 启动本地服务器 + 打开浏览器
    python3 publish.py --base-url URL       # 设置音频 URL 前缀（用于公网部署）
"""
import argparse
import datetime
import http.server
import json
import os
import struct
import textwrap
import threading
import webbrowser
import xml.etree.ElementTree as ET
from email.utils import formatdate
from pathlib import Path

OUTPUTS_DIR = Path(__file__).parent / "outputs"
SITE_DIR = Path(__file__).parent / "site"

PODCAST_TITLE = "助眠电台 · Bedtime Story Agent"
PODCAST_DESC = "全自动 AI 助眠音频——从文字到可发布的成品，每一期都是独一无二的深度睡眠旅程。"
PODCAST_AUTHOR = "Bedtime Story Agent"
PODCAST_LANG = "zh-cn"
PODCAST_CATEGORY = "Health &amp; Fitness"


# ---------------------------------------------------------------------------
# MP3 duration estimation (no external deps)
# ---------------------------------------------------------------------------

_MP3_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MP3_SAMPLE_RATES_V1 = [44100, 48000, 32000, 0]


def _estimate_mp3_duration(filepath: str) -> int:
    """Estimate MP3 duration in seconds by reading frame headers.
    Falls back to file-size estimate at 128 kbps."""
    size = os.path.getsize(filepath)
    try:
        with open(filepath, "rb") as f:
            header_bytes = f.read(4096)
        # skip ID3v2 tag if present
        offset = 0
        if header_bytes[:3] == b"ID3":
            tag_size = (
                (header_bytes[6] & 0x7F) << 21
                | (header_bytes[7] & 0x7F) << 14
                | (header_bytes[8] & 0x7F) << 7
                | (header_bytes[9] & 0x7F)
            )
            offset = 10 + tag_size
            with open(filepath, "rb") as f:
                f.seek(offset)
                header_bytes = f.read(4)
        else:
            header_bytes = header_bytes[:4]
            for i in range(min(len(header_bytes) - 1, 4096)):
                if header_bytes[i] == 0xFF and (header_bytes[i + 1] & 0xE0) == 0xE0:
                    header_bytes = header_bytes[i : i + 4]
                    break

        if len(header_bytes) >= 4 and header_bytes[0] == 0xFF and (header_bytes[1] & 0xE0) == 0xE0:
            bitrate_idx = (header_bytes[2] >> 4) & 0x0F
            sr_idx = (header_bytes[2] >> 2) & 0x03
            bitrate = _MP3_BITRATES_V1_L3[bitrate_idx] * 1000
            if bitrate > 0:
                return int(size * 8 / bitrate)
    except Exception:
        pass
    # fallback: assume 128 kbps
    return int(size * 8 / 128000)


# ---------------------------------------------------------------------------
# Episode scanning
# ---------------------------------------------------------------------------

def scan_episodes(outputs_dir: Path) -> list[dict]:
    """Scan outputs/ and return episode metadata sorted newest-first."""
    episodes = []
    if not outputs_dir.is_dir():
        return episodes

    for folder in sorted(outputs_dir.iterdir(), reverse=True):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        audio = folder / "final_audio.mp3"
        if not audio.is_file():
            continue

        # metadata
        meta = {}
        meta_path = folder / "metadata.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # story draft
        draft = folder / "story_draft.txt"
        draft_text = ""
        word_count = 0
        if draft.is_file():
            draft_text = draft.read_text(encoding="utf-8")
            word_count = len(draft_text)

        # SRT subtitles
        srt_path = folder / "subtitles.srt"
        srt_text = ""
        if srt_path.is_file():
            srt_text = srt_path.read_text(encoding="utf-8")

        # extract theme from folder name: Batch_YYYYMMDD_HHMMSS_主题
        parts = folder.name.split("_", 3)
        theme = parts[3] if len(parts) >= 4 else folder.name

        # timestamp from folder name
        try:
            ts = datetime.datetime.strptime(
                f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S"
            )
        except (ValueError, IndexError):
            ts = datetime.datetime.fromtimestamp(audio.stat().st_mtime)

        duration = _estimate_mp3_duration(str(audio))

        episodes.append(
            {
                "folder": folder.name,
                "theme": theme,
                "title": meta.get("title", theme),
                "description": meta.get("description_xiaoyuzhou", meta.get("description_ximalaya", "")),
                "tags": meta.get("tags", []),
                "audio_path": str(audio.relative_to(outputs_dir.parent)),
                "audio_size": audio.stat().st_size,
                "duration": duration,
                "word_count": word_count,
                "draft": draft_text[:500],
                "srt": srt_text,
                "timestamp": ts,
                "pub_date": formatdate(ts.timestamp(), localtime=True),
            }
        )
    return episodes


# ---------------------------------------------------------------------------
# RSS feed generation
# ---------------------------------------------------------------------------

def generate_rss(episodes: list[dict], base_url: str) -> str:
    """Generate a Podcast RSS 2.0 XML feed."""
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("content", CONTENT_NS)

    rss = ET.Element("rss", version="2.0")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "description").text = PODCAST_DESC
    ET.SubElement(channel, "language").text = PODCAST_LANG
    ET.SubElement(channel, "link").text = base_url or "https://example.com"
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = PODCAST_AUTHOR
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "no"
    cat = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    cat.set("text", "Health & Fitness")

    for ep in episodes:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "description").text = ep["description"]
        ET.SubElement(item, "pubDate").text = ep["pub_date"]

        audio_url = f"{base_url}/{ep['audio_path']}" if base_url else ep["audio_path"]
        enc = ET.SubElement(item, "enclosure")
        enc.set("url", audio_url)
        enc.set("length", str(ep["audio_size"]))
        enc.set("type", "audio/mpeg")

        dur = ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
        m, s = divmod(ep["duration"], 60)
        dur.text = f"{m}:{s:02d}"

        ET.SubElement(item, "guid", isPermaLink="false").text = ep["folder"]

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")


# ---------------------------------------------------------------------------
# HTML player generation
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def generate_html(episodes: list[dict]) -> str:
    """Generate a self-contained dark-themed HTML player page."""

    episode_cards = []
    for i, ep in enumerate(episodes):
        tags_html = "".join(f'<span class="tag">{t}</span>' for t in ep["tags"][:4])
        desc_short = ep["description"][:120] + "…" if len(ep["description"]) > 120 else ep["description"]
        srt_attr = f' data-srt="{ep["srt"][:3000]}"' if ep["srt"] else ""

        episode_cards.append(f"""
      <article class="episode" data-audio="../{ep['audio_path']}"{srt_attr}>
        <div class="ep-header">
          <span class="ep-theme">{ep['theme']}</span>
          <span class="ep-meta">{ep['word_count']} 字 · {_fmt_duration(ep['duration'])}</span>
        </div>
        <h3 class="ep-title">{ep['title']}</h3>
        <p class="ep-desc">{desc_short}</p>
        <div class="ep-tags">{tags_html}</div>
        <button class="play-btn" onclick="togglePlay(this, {i})">
          <svg class="icon-play" viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>
          <svg class="icon-pause" viewBox="0 0 24 24" style="display:none"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
        </button>
      </article>""")

    cards_html = "\n".join(episode_cards)
    total_eps = len(episodes)
    total_dur = sum(e["duration"] for e in episodes)

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>助眠电台</title>
    <style>
    :root {{
      --bg-deep: #06061a;
      --bg-card: rgba(255,255,255,0.04);
      --bg-card-hover: rgba(255,255,255,0.07);
      --border: rgba(255,255,255,0.08);
      --text: #d4d4e0;
      --text-dim: #7a7a9a;
      --accent: #7c6ff7;
      --accent-glow: rgba(124,111,247,0.3);
      --warm: #f0c27f;
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
      background: var(--bg-deep);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
      transition: opacity 2s ease;
    }}
    body.dimmed {{ opacity: 0.3; }}

    /* --- starfield --- */
    .stars {{
      position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none;
    }}
    .stars span {{
      position: absolute; border-radius: 50%; background: #fff;
      animation: twinkle var(--dur) ease-in-out infinite alternate;
    }}
    @keyframes twinkle {{ 0% {{ opacity: 0.1; }} 100% {{ opacity: var(--peak); }} }}

    /* --- layout --- */
    .container {{
      position: relative; z-index: 1;
      max-width: 680px; margin: 0 auto; padding: 60px 20px 120px;
    }}
    header {{ text-align: center; margin-bottom: 48px; }}
    header h1 {{
      font-size: 1.8rem; font-weight: 700;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    header p {{ color: var(--text-dim); margin-top: 8px; font-size: 0.9rem; }}
    .stats {{
      display: flex; justify-content: center; gap: 24px; margin-top: 16px;
      font-size: 0.8rem; color: var(--text-dim);
    }}
    .stats b {{ color: var(--warm); font-weight: 600; }}

    /* --- episode card --- */
    .episode {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 16px; padding: 24px; margin-bottom: 16px;
      position: relative; transition: all 0.3s ease;
      cursor: default;
    }}
    .episode:hover {{ background: var(--bg-card-hover); border-color: rgba(124,111,247,0.2); }}
    .episode.active {{ border-color: var(--accent); box-shadow: 0 0 24px var(--accent-glow); }}
    .ep-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .ep-theme {{
      font-size: 0.75rem; color: var(--accent); background: rgba(124,111,247,0.12);
      padding: 2px 10px; border-radius: 20px;
    }}
    .ep-meta {{ font-size: 0.75rem; color: var(--text-dim); }}
    .ep-title {{ font-size: 1.05rem; font-weight: 600; line-height: 1.5; margin-bottom: 6px; }}
    .ep-desc {{ font-size: 0.85rem; color: var(--text-dim); line-height: 1.6; margin-bottom: 10px; }}
    .ep-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .tag {{
      font-size: 0.7rem; color: var(--text-dim); background: rgba(255,255,255,0.05);
      padding: 2px 8px; border-radius: 10px;
    }}
    .play-btn {{
      position: absolute; right: 24px; top: 50%; transform: translateY(-50%);
      width: 48px; height: 48px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), #9b6ff7);
      border: none; cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: all 0.3s ease; box-shadow: 0 4px 16px var(--accent-glow);
    }}
    .play-btn:hover {{ transform: translateY(-50%) scale(1.08); }}
    .play-btn svg {{ width: 20px; height: 20px; fill: #fff; }}
    .icon-play {{ margin-left: 2px; }}

    /* --- bottom player bar --- */
    .player-bar {{
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 10;
      background: rgba(10,10,30,0.95); backdrop-filter: blur(20px);
      border-top: 1px solid var(--border);
      padding: 0; transform: translateY(100%); transition: transform 0.4s ease;
    }}
    .player-bar.show {{ transform: translateY(0); }}
    .progress-wrap {{
      height: 4px; background: rgba(255,255,255,0.06); cursor: pointer; position: relative;
    }}
    .progress-wrap:hover {{ height: 6px; }}
    .progress-fill {{
      height: 100%; background: linear-gradient(90deg, var(--accent), var(--warm));
      width: 0%; transition: width 0.2s linear; border-radius: 0 2px 2px 0;
    }}
    .player-inner {{
      display: flex; align-items: center; padding: 12px 20px; gap: 16px;
      max-width: 680px; margin: 0 auto;
    }}
    .player-info {{ flex: 1; min-width: 0; }}
    .player-title {{ font-size: 0.85rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .player-time {{ font-size: 0.7rem; color: var(--text-dim); margin-top: 2px; }}
    .player-subtitle {{
      font-size: 0.8rem; color: var(--warm); margin-top: 4px;
      min-height: 1.2em; transition: opacity 0.5s ease;
    }}
    .player-controls {{ display: flex; align-items: center; gap: 12px; }}
    .ctrl-btn {{
      background: none; border: none; cursor: pointer; color: var(--text); padding: 4px;
      opacity: 0.7; transition: opacity 0.2s;
    }}
    .ctrl-btn:hover {{ opacity: 1; }}
    .ctrl-btn svg {{ width: 18px; height: 18px; fill: currentColor; }}

    /* sleep timer dropdown */
    .timer-wrap {{ position: relative; }}
    .timer-menu {{
      position: absolute; bottom: 100%; right: 0; margin-bottom: 8px;
      background: rgba(20,20,50,0.97); border: 1px solid var(--border);
      border-radius: 12px; padding: 8px 0; display: none; min-width: 130px;
    }}
    .timer-menu.show {{ display: block; }}
    .timer-opt {{
      display: block; width: 100%; text-align: left; padding: 8px 16px;
      background: none; border: none; color: var(--text); font-size: 0.8rem;
      cursor: pointer;
    }}
    .timer-opt:hover {{ background: rgba(255,255,255,0.06); }}
    .timer-opt.active {{ color: var(--warm); }}
    .timer-badge {{
      font-size: 0.6rem; color: var(--warm); background: rgba(240,194,127,0.15);
      padding: 1px 6px; border-radius: 8px; margin-left: 4px;
    }}

    @media (max-width: 600px) {{
      .container {{ padding: 40px 16px 140px; }}
      .episode {{ padding: 18px; padding-right: 70px; }}
      .play-btn {{ width: 40px; height: 40px; right: 16px; }}
      header h1 {{ font-size: 1.4rem; }}
    }}
    </style>
    </head>
    <body>

    <div class="stars" id="stars"></div>

    <div class="container">
      <header>
        <h1>助眠电台</h1>
        <p>AI 生成 · 韵律弧线催眠 · 每期独一无二</p>
        <div class="stats">
          <span><b>{total_eps}</b> 期节目</span>
          <span><b>{_fmt_duration(total_dur)}</b> 总时长</span>
        </div>
      </header>

      <main id="episodes">
        {cards_html}
      </main>
    </div>

    <!-- bottom player -->
    <div class="player-bar" id="playerBar">
      <div class="progress-wrap" id="progressWrap" onclick="seek(event)">
        <div class="progress-fill" id="progressFill"></div>
      </div>
      <div class="player-inner">
        <div class="player-info">
          <div class="player-title" id="playerTitle">—</div>
          <div class="player-time"><span id="curTime">0:00</span> / <span id="totalTime">0:00</span></div>
          <div class="player-subtitle" id="playerSub"></div>
        </div>
        <div class="player-controls">
          <div class="timer-wrap">
            <button class="ctrl-btn" onclick="toggleTimerMenu()" title="睡眠定时">
              <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><polyline points="12,7 12,12 16,14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
              <span class="timer-badge" id="timerBadge" style="display:none"></span>
            </button>
            <div class="timer-menu" id="timerMenu">
              <button class="timer-opt" onclick="setSleepTimer(0)">关闭</button>
              <button class="timer-opt" onclick="setSleepTimer(15)">15 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(30)">30 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(45)">45 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(60)">60 分钟</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <audio id="audio" preload="metadata"></audio>

    <script>
    // --- Starfield ---
    (function() {{
      const c = document.getElementById('stars');
      for (let i = 0; i < 80; i++) {{
        const s = document.createElement('span');
        const size = Math.random() * 2 + 1;
        s.style.cssText = `left:${{Math.random()*100}}%;top:${{Math.random()*100}}%;width:${{size}}px;height:${{size}}px;--dur:${{2+Math.random()*4}}s;--peak:${{0.3+Math.random()*0.7}}`;
        c.appendChild(s);
      }}
    }})();

    // --- Audio state ---
    const audio = document.getElementById('audio');
    const episodes = document.querySelectorAll('.episode');
    let currentIdx = -1;
    let srtCues = [];
    let sleepTimerId = null;
    let sleepRemaining = 0;

    function fmtTime(s) {{
      s = Math.floor(s);
      const m = Math.floor(s / 60);
      return m + ':' + String(s % 60).padStart(2, '0');
    }}

    function togglePlay(btn, idx) {{
      if (currentIdx === idx && !audio.paused) {{
        audio.pause();
        showPauseState(idx, false);
        return;
      }}
      if (currentIdx !== idx) {{
        // load new episode
        const ep = episodes[idx];
        audio.src = ep.dataset.audio;
        document.getElementById('playerTitle').textContent = ep.querySelector('.ep-title').textContent;
        document.getElementById('playerBar').classList.add('show');
        srtCues = parseSRT(ep.dataset.srt || '');
        // deactivate previous
        if (currentIdx >= 0) {{
          episodes[currentIdx].classList.remove('active');
          showPauseState(currentIdx, false);
        }}
        ep.classList.add('active');
        currentIdx = idx;
      }}
      audio.play();
      showPauseState(idx, true);
    }}

    function showPauseState(idx, playing) {{
      const btn = episodes[idx].querySelector('.play-btn');
      btn.querySelector('.icon-play').style.display = playing ? 'none' : 'block';
      btn.querySelector('.icon-pause').style.display = playing ? 'block' : 'none';
    }}

    // --- Progress ---
    audio.addEventListener('timeupdate', () => {{
      if (!audio.duration) return;
      const pct = (audio.currentTime / audio.duration) * 100;
      document.getElementById('progressFill').style.width = pct + '%';
      document.getElementById('curTime').textContent = fmtTime(audio.currentTime);
      document.getElementById('totalTime').textContent = fmtTime(audio.duration);
      // subtitle
      const sub = document.getElementById('playerSub');
      const cue = srtCues.find(c => audio.currentTime >= c.start && audio.currentTime <= c.end);
      sub.textContent = cue ? cue.text : '';
    }});

    audio.addEventListener('ended', () => {{
      showPauseState(currentIdx, false);
      // auto-play next
      if (currentIdx < episodes.length - 1) {{
        togglePlay(null, currentIdx + 1);
      }}
    }});

    function seek(e) {{
      if (!audio.duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    }}

    // --- SRT parser ---
    function parseSRT(text) {{
      if (!text) return [];
      const cues = [];
      const blocks = text.trim().split(/\\n\\n+/);
      for (const block of blocks) {{
        const lines = block.split('\\n');
        if (lines.length < 3) continue;
        const times = lines[1].match(/(\\d+):(\\d+):(\\d+)[,.](\\d+)\\s*-->\\s*(\\d+):(\\d+):(\\d+)[,.](\\d+)/);
        if (!times) continue;
        const start = +times[1]*3600 + +times[2]*60 + +times[3] + +times[4]/1000;
        const end = +times[5]*3600 + +times[6]*60 + +times[7] + +times[8]/1000;
        cues.push({{ start, end, text: lines.slice(2).join(' ') }});
      }}
      return cues;
    }}

    // --- Sleep timer ---
    function toggleTimerMenu() {{
      document.getElementById('timerMenu').classList.toggle('show');
    }}

    function setSleepTimer(minutes) {{
      document.getElementById('timerMenu').classList.remove('show');
      const badge = document.getElementById('timerBadge');

      if (sleepTimerId) {{ clearInterval(sleepTimerId); sleepTimerId = null; }}

      if (minutes === 0) {{
        badge.style.display = 'none';
        document.body.classList.remove('dimmed');
        return;
      }}

      sleepRemaining = minutes * 60;
      badge.style.display = 'inline';
      badge.textContent = minutes + 'm';

      sleepTimerId = setInterval(() => {{
        sleepRemaining--;
        const m = Math.ceil(sleepRemaining / 60);
        badge.textContent = m + 'm';

        // dim at 20% remaining
        if (sleepRemaining < minutes * 60 * 0.2) {{
          document.body.classList.add('dimmed');
        }}

        if (sleepRemaining <= 0) {{
          clearInterval(sleepTimerId);
          sleepTimerId = null;
          audio.pause();
          if (currentIdx >= 0) showPauseState(currentIdx, false);
          badge.style.display = 'none';
          // keep dimmed — user is hopefully asleep
        }}
      }}, 1000);
    }}

    // close timer menu on outside click
    document.addEventListener('click', (e) => {{
      if (!e.target.closest('.timer-wrap')) {{
        document.getElementById('timerMenu').classList.remove('show');
      }}
    }});
    </script>
    </body>
    </html>
    """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="生成播客站点（播放器 + RSS 订阅源）")
    parser.add_argument("--base-url", default="", help="音频 URL 前缀（公网部署时使用）")
    parser.add_argument("--serve", action="store_true", help="生成后启动本地 HTTP 服务器并打开浏览器")
    parser.add_argument("--port", type=int, default=8888, help="本地服务器端口（默认 8888）")
    args = parser.parse_args()

    episodes = scan_episodes(OUTPUTS_DIR)
    if not episodes:
        print("outputs/ 中没有找到可用的音频内容。先运行 python3 batch.py --count 1 --audio-only")
        return

    # create site/
    SITE_DIR.mkdir(exist_ok=True)

    # generate HTML player
    html = generate_html(episodes)
    html_path = SITE_DIR / "index.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[OK] 播放器 → {html_path}")

    # generate RSS feed
    rss = generate_rss(episodes, args.base_url)
    rss_path = SITE_DIR / "feed.xml"
    rss_path.write_text(rss, encoding="utf-8")
    print(f"[OK] RSS 订阅源 → {rss_path}")

    print(f"\n共 {len(episodes)} 期节目已发布。")

    if args.serve:
        # serve from project root so audio paths resolve correctly
        os.chdir(SITE_DIR.parent)
        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.HTTPServer(("", args.port), handler)
        url = f"http://localhost:{args.port}/site/"
        print(f"\n服务器已启动: {url}")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止。")
            server.shutdown()
    else:
        print(f"\n本地预览: cd {SITE_DIR.parent} && python3 -m http.server 8888")
        print(f"然后打开: http://localhost:8888/site/")


if __name__ == "__main__":
    main()
