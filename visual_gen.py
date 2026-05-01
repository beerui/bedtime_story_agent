# visual_gen.py
"""视觉素材引擎：封面生成/裁剪、场景图、AI 视频、视频合成。"""
import asyncio
import os
import time
import urllib.parse

import PIL.Image
import requests
from moviepy.editor import (
    ImageClip,
    VideoFileClip,
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    concatenate_videoclips,
    TextClip,
)
from moviepy.audio.fx.all import audio_loop, audio_fadein, audio_fadeout
import moviepy.video.fx.all as vfx
from rich.console import Console
from rich.panel import Panel

from config import API_CONFIG, THEMES
from audio_gen import generate_soothing_noise, _resolve_bgm_path

console = Console()


def generate_and_crop_cover(theme_name: str, output_dir: str):
    """生成全平台适配的专属视频封面（1920x1920 底图 + 多尺寸裁剪）。"""
    console.print("\n[bold cyan][封面车间] 正在生成全平台适配的专属视频封面...[/bold cyan]")
    theme_info = THEMES[theme_name]

    base_cover_path = os.path.join(output_dir, "Cover_Base_1920x1920.png")

    if not os.path.exists(base_cover_path):
        console.print("  -> 正在绘制 1920x1920 超清正方形底图...")
        prompt = f"{theme_info['image_prompt']}, vivid colors, masterpiece, best quality, title screen background, highly detailed, 8k, no text, no watermark"
        image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1920&height=1920&nologo=true&seed=888"

        for attempt in range(4):
            try:
                response = requests.get(image_url, timeout=60)
                response.raise_for_status()
                with open(base_cover_path, "wb") as f:
                    f.write(response.content)
                break
            except Exception as e:
                if attempt < 3:
                    time.sleep(5)
                else:
                    console.print(f"[red]  ❌ 封面底图生成失败。[/red]")
                    return

    if not os.path.exists(base_cover_path):
        return

    console.print("  -> 正在自动化裁剪多平台封面尺寸...")
    target_sizes = {
        "Cover_B站_西瓜_16v9.png": (1920, 1080),
        "Cover_抖音_视频号_9v16.png": (1080, 1920),
        "Cover_小红书_3v4.png": (1440, 1920),
    }

    try:
        with PIL.Image.open(base_cover_path) as img:
            orig_w, orig_h = img.size
            for filename, (target_w, target_h) in target_sizes.items():
                out_path = os.path.join(output_dir, filename)
                if os.path.exists(out_path):
                    continue
                left = (orig_w - target_w) // 2
                upper = (orig_h - target_h) // 2
                right = left + target_w
                lower = upper + target_h
                cropped_img = img.crop((left, upper, right, lower))
                cropped_img.save(out_path)
                console.print(f"    ✂️ 裁剪完成: {filename}")
    except Exception as e:
        console.print(f"[red]  ❌ 图片裁剪失败: {e}[/red]")

    console.print("[green]  ✅ 全平台封面处理完毕！[/green]")


def apply_ken_burns(image_path: str, duration: float, zoom_rate: float = 0.15):
    """Ken Burns 推镜头降级方案。"""
    console.print(f"    📹 正在应用降级方案 (Ken Burns推镜头)... (时长: {duration:.1f}秒)")
    clip = ImageClip(image_path).set_duration(duration)
    w, h = clip.size

    def zoom_filter(t):
        return 1 + zoom_rate * (t / duration)

    zoomed_clip = clip.resize(zoom_filter)
    final_clip = CompositeVideoClip([zoomed_clip.set_position("center")], size=(w, h))
    return final_clip.set_duration(duration)


async def generate_ai_video(image_path: str, output_path: str):
    """调用阿里云通义万相生成 AI 视频（自动容错降级）。"""
    api_key = API_CONFIG.get("cosyvoice_api_key", "").strip()
    if not api_key:
        console.print("[yellow]    ⚠️ 未配置阿里云 API Key，跳过视频生成。[/yellow]")
        return None

    if os.path.exists(output_path):
        return output_path

    try:
        import dashscope
        from dashscope import VideoSynthesis

        dashscope.api_key = api_key

        console.print(f"    🎬 唤醒阿里云视频大模型: {os.path.basename(image_path)}...")

        def run_sdk():
            local_file_uri = f"file://{os.path.abspath(image_path)}"
            test_models = ["wanx2.1-i2v-plus", "wanx2.1-i2v-turbo", "wan2.6-i2v-flash"]

            for m in test_models:
                console.print(f"    -> 正在尝试提交通义万相模型: [bold]{m}[/bold]")
                rsp = VideoSynthesis.async_call(
                    model=m,
                    img_url=local_file_uri,
                    prompt="cinematic, highly detailed, slow motion, gentle wind, dynamic lighting, 4k",
                )

                if rsp.status_code == 200:
                    task_id = rsp.output.task_id
                    console.print(f"    [green]✅ 任务提交成功！(模型: {m}, Task ID: {task_id})[/green]")
                    console.print(f"    ⏳ 正在等待百炼服务器渲染，请稍候...")

                    while True:
                        time.sleep(5)
                        status_rsp = VideoSynthesis.fetch(task_id)
                        if status_rsp.status_code == 200:
                            status = status_rsp.output.task_status
                            if status == "SUCCEEDED":
                                return status_rsp.output.video_url
                            elif status in ["FAILED", "UNKNOWN"]:
                                error_msg = status_rsp.output.get("message", "未知错误")
                                console.print(f"    [dim]⚠️ {m} 服务端渲染失败 ({error_msg})，自动切换下一个模型...[/dim]")
                                break
                        else:
                            console.print(f"    [dim]⚠️ {m} 查询状态失败 ({status_rsp.message})，自动切换下一个模型...[/dim]")
                            break
                else:
                    console.print(f"    [dim]⚠️ {m} 提交失败 ({rsp.code}: {rsp.message})，尝试下一个...[/dim]")

            raise Exception("所有可用的视频模型均已尝试完毕且均告失败，请检查阿里云平台额度。")

        video_url = await asyncio.to_thread(run_sdk)

        console.print(f"    📥 渲染完成！正在下载视频到本地...")
        vid_data = await asyncio.to_thread(requests.get, video_url)
        with open(output_path, "wb") as f:
            f.write(vid_data.content)

        console.print(f"[green]    ✅ 视频片段生动化完成: {os.path.basename(output_path)}[/green]")
        return output_path

    except Exception as e:
        console.print(f"[red]    ❌ 阿里云视频大模型调用异常: {str(e)}[/red]")
        return None


def generate_multi_images(theme_name: str, output_dir: str) -> list[str]:
    """生成静态高质感背景图（单图模式）。"""
    console.print("\n[bold cyan][视觉车间] 正在生成静态高质感背景图(单图模式)...[/bold cyan]")
    theme_info = THEMES[theme_name]

    output_filename = os.path.join(output_dir, "scene_1.png")
    saved_images = []

    if os.path.exists(output_filename):
        saved_images.append(output_filename)
        return saved_images

    pollination_prompt = f"{theme_info['image_prompt']}, 4k"
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(pollination_prompt)}?width=1024&height=1792&nologo=true&seed=999"

    for attempt in range(4):
        try:
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(output_filename, "wb") as f:
                f.write(response.content)
            saved_images.append(output_filename)
            console.print(f"  ✅ 场景图生成成功！")
            break
        except Exception as e:
            if attempt < 3:
                time.sleep(5)
            else:
                console.print(f"[red]  ❌ 图片生成失败: {e}[/red]")
                break

    return saved_images


def assemble_pro_video(
    image_paths: list[str],
    ai_video_paths: list[str],
    voice_path: str,
    subtitles_info: list[dict],
    bgm_filename: str | None,
    total_minutes: int,
    theme_name: str,
    output_dir: str,
):
    """最终剪辑包装：视频混音 + 字幕 + 渲染。"""
    if not image_paths:
        console.print("[bold red]无背景素材，取消合成。[/bold red]")
        return
    console.print(f"\n[bold cyan][最终剪辑] 正在进行视频混音与电影级视觉压制...[/bold cyan]")
    total_seconds = total_minutes * 60
    output_path = os.path.join(output_dir, f"Final_Video_{theme_name}.mp4")

    voice_clip = AudioFileClip(voice_path)

    _bgm_resolved = _resolve_bgm_path(bgm_filename)
    if _bgm_resolved:
        bgm_clip = AudioFileClip(_bgm_resolved)
    else:
        fb_bgm = "assets/auto_generated_noise.mp3"
        if not os.path.exists(fb_bgm):
            generate_soothing_noise(fb_bgm, 60)
        bgm_clip = AudioFileClip(fb_bgm)

    looped_bgm = audio_loop(bgm_clip, duration=total_seconds).volumex(0.35).fx(audio_fadein, 5).fx(audio_fadeout, 10)
    final_audio = CompositeAudioClip([looped_bgm, voice_clip.set_start(2)])

    duration_per_image = total_seconds / len(image_paths)
    video_clips = []

    for i, img_path in enumerate(image_paths):
        vid_path = ai_video_paths[i] if i < len(ai_video_paths) else None

        if vid_path and os.path.exists(vid_path):
            console.print(f"    🎬 应用视频无缝循环逻辑...")
            raw_clip = VideoFileClip(vid_path).resize(newsize=(1024, 1792))
            clip = raw_clip.fx(vfx.loop, duration=duration_per_image)
        else:
            clip = apply_ken_burns(img_path, duration=duration_per_image, zoom_rate=0.15)

        if i > 0:
            clip = clip.crossfadein(2)
        video_clips.append(clip)

    final_video = concatenate_videoclips(video_clips, method="compose").set_audio(final_audio)

    console.print("  -> 正在压制电影级字幕...")
    font_path = "Arial"
    for fp in ["/mnt/c/Windows/Fonts/msyh.ttc", "/mnt/c/Windows/Fonts/simhei.ttf", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "font.ttf"]:
        if os.path.exists(fp):
            font_path = fp
            break

    text_clips = []
    for sub in subtitles_info:
        raw_text = sub["text"].strip("。！？!?\n ")
        if not raw_text:
            continue
        wrapped_text = "\n".join([raw_text[j : j + 14] for j in range(0, len(raw_text), 14)])
        try:
            txt_clip = TextClip(wrapped_text, font=font_path, fontsize=65, color="white", stroke_color="black", stroke_width=2, align="center")
            txt_clip = txt_clip.set_position(("center", "center")).set_start(sub["start"] + 2.0).set_duration(sub["duration"]).crossfadein(0.3).crossfadeout(0.3)
            text_clips.append(txt_clip)
        except Exception:
            break

    if text_clips:
        final_video = CompositeVideoClip([final_video] + text_clips)

    console.print("[bold cyan][渲染中] 开始渲染最终视频，请稍候...[/bold cyan]")
    final_video.write_videofile(output_path, fps=12, codec="libx264", audio_codec="aac", logger=None)
    console.print(Panel.fit(f"[bold green]🎉 真·视觉大片渲染完成！已保存在: {output_dir}[/bold green]"))
