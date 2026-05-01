# bgm.py
"""BGM 管理：AI 选曲 + YouTube 下载。"""
import logging
import os

import yt_dlp
from rich.console import Console

from config import API_CONFIG, MI_API_KEY, MI_BASE_URL, MI_TEXT_MODEL

console = Console()
logger = logging.getLogger(__name__)

from openai import OpenAI

text_client = OpenAI(
    api_key=API_CONFIG["proxy_api_key"],
    base_url=API_CONFIG["proxy_base_url"],
)

_mimo_text_client: OpenAI | None = None
if MI_API_KEY:
    _mimo_text_client = OpenAI(api_key=MI_API_KEY, base_url=MI_BASE_URL)


def download_bgm_from_youtube(keyword: str, output_filename: str) -> str | None:
    """从 YouTube 下载免费 BGM。"""
    console.print(f"[yellow]  🌐 正在全网下载: '{keyword}'...[/yellow]")
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "outtmpl": f"assets/{output_filename}",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{keyword} copyright free ambient relax music"])
        return f"{output_filename}.mp3"
    except Exception:
        return None


def select_best_bgm(theme_name: str) -> str | None:
    """AI 音乐总监：从本地库选曲或全网下载。"""
    console.print("\n[bold cyan]🎧 正在呼叫 AI 音乐总监...[/bold cyan]")
    os.makedirs("assets", exist_ok=True)
    available_mp3s = [f for f in os.listdir("assets") if f.endswith(".mp3")]
    prompt = (
        f"主题：【{theme_name}】\n本地库：\n{available_mp3s}\n"
        "任务：如果有合适的只输出 LOCAL:名.mp3。如果不合适去网上找，只输出 DOWNLOAD:极简英文搜索词。"
    )
    try:
        ai_decision = None
        if _mimo_text_client is not None:
            try:
                resp = _mimo_text_client.chat.completions.create(
                    model=MI_TEXT_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                )
                ai_decision = resp.choices[0].message.content
            except Exception as e:
                logger.warning("MiMo LLM BGM 选曲失败，fallback: %s", e)
        if not ai_decision:
            response = text_client.chat.completions.create(
                model=API_CONFIG["text_model"],
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            ai_decision = response.choices[0].message.content
        ai_decision = ai_decision.strip().strip("'\"` ")
        if ai_decision.startswith("LOCAL:"):
            res = ai_decision.replace("LOCAL:", "").strip()
            if res in available_mp3s:
                return res
        elif ai_decision.startswith("DOWNLOAD:"):
            kw = ai_decision.replace("DOWNLOAD:", "").strip()
            res = download_bgm_from_youtube(kw, kw.replace(" ", "_").lower())
            if res:
                return res
        return None
    except Exception:
        return None
