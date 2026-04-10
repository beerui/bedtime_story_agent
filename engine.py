# engine.py
# 必须放在最顶部的猴子补丁 (解决 Pillow 与 moviepy 版本冲突)
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import os
import urllib.parse
import requests
import edge_tts
import numpy as np
import re
import time
import base64
import yt_dlp
import asyncio
from openai import OpenAI
from moviepy.editor import (
    ImageClip, VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, 
    concatenate_audioclips, CompositeVideoClip, TextClip
)
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.audio.fx.all import audio_loop, audio_fadein, audio_fadeout
import moviepy.video.fx.all as vfx
from rich.console import Console
from rich.panel import Panel

from config import API_CONFIG, PROTAGONIST, THEMES, TTS_SCRIPT_DIRECTIVE
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer

console = Console()

text_client = OpenAI(
    api_key=API_CONFIG["proxy_api_key"],
    base_url=API_CONFIG["proxy_base_url"]
)

# ==========================================
# 新增模块：全自动多平台封面生成与裁剪 (PIL)
# ==========================================
def generate_and_crop_cover(theme_name, output_dir):
    console.print("\n[bold cyan][封面车间] 正在生成全平台适配的专属视频封面...[/bold cyan]")
    theme_info = THEMES[theme_name]
    
    base_cover_path = os.path.join(output_dir, "Cover_Base_1920x1920.png")
    
    # 1. 生成 1920x1920 的超清正方形底图
    if not os.path.exists(base_cover_path):
        console.print("  -> 正在绘制 1920x1920 超清正方形底图...")
        # 提示词增加封面质感
        prompt = f"{theme_info['image_prompt']}, vivid colors, masterpiece, best quality, title screen background, highly detailed, 8k, no text, no watermark"
        image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1920&height=1920&nologo=true&seed=888"
        
        for attempt in range(4):
            try:
                response = requests.get(image_url, timeout=60)
                response.raise_for_status() 
                with open(base_cover_path, 'wb') as f: 
                    f.write(response.content)
                break
            except Exception as e:
                if attempt < 3: time.sleep(5)
                else: 
                    console.print(f"[red]  ❌ 封面底图生成失败。[/red]")
                    return
                    
    if not os.path.exists(base_cover_path): return

    # 2. 自动化裁剪流水线
    console.print("  -> 正在自动化裁剪多平台封面尺寸...")
    target_sizes = {
        "Cover_B站_西瓜_16v9.png": (1920, 1080),
        "Cover_抖音_视频号_9v16.png": (1080, 1920),
        "Cover_小红书_3v4.png": (1440, 1920)
    }
    
    try:
        with PIL.Image.open(base_cover_path) as img:
            orig_w, orig_h = img.size
            for filename, (target_w, target_h) in target_sizes.items():
                out_path = os.path.join(output_dir, filename)
                if os.path.exists(out_path): continue
                
                # 中心裁剪算法
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

# ==========================================
# 模块：视觉特效引擎 (降级用)
# ==========================================
def apply_ken_burns(image_path, duration, zoom_rate=0.15):
    console.print(f"    📹 正在应用降级方案 (Ken Burns推镜头)... (时长: {duration:.1f}秒)")
    clip = ImageClip(image_path).set_duration(duration)
    w, h = clip.size
    def zoom_filter(t): return 1 + zoom_rate * (t / duration)
    zoomed_clip = clip.resize(zoom_filter)
    final_clip = CompositeVideoClip([zoomed_clip.set_position('center')], size=(w, h))
    return final_clip.set_duration(duration)

# ==========================================
# 模块：图生视频大模型引擎 (阿里云通义万相 真·自动容错降级版)
# ==========================================
async def generate_ai_video(image_path, output_path):
    api_key = API_CONFIG.get("cosyvoice_api_key", "").strip()
    if not api_key: 
        console.print("[yellow]    ⚠️ 未配置阿里云 API Key，跳过视频生成。[/yellow]")
        return None 
        
    if os.path.exists(output_path): return output_path 

    try:
        import dashscope
        from dashscope import VideoSynthesis
        dashscope.api_key = api_key
        
        console.print(f"    🎬 唤醒阿里云视频大模型: {os.path.basename(image_path)}...")
        
        def run_sdk():
            local_file_uri = f"file://{os.path.abspath(image_path)}"
            
            # 【核心修复】：使用官方确认支持当前 SDK img_url 参数的经典稳定模型
            # 按照 画质优先 -> 性价比优先 的顺序自动轮询
            test_models = ["wanx2.1-i2v-plus", "wanx2.1-i2v-turbo", "wan2.6-i2v-flash"]
            
            for m in test_models:
                console.print(f"    -> 正在尝试提交通义万相模型: [bold]{m}[/bold]")
                rsp = VideoSynthesis.async_call(
                    model=m,
                    img_url=local_file_uri,
                    prompt="cinematic, highly detailed, slow motion, gentle wind, dynamic lighting, 4k"
                )
                
                if rsp.status_code == 200:
                    task_id = rsp.output.task_id
                    console.print(f"    [green]✅ 任务提交成功！(模型: {m}, Task ID: {task_id})[/green]")
                    console.print(f"    ⏳ 正在等待百炼服务器渲染，请稍候...")
                    
                    # 轮询状态
                    import time
                    while True:
                        time.sleep(5) 
                        status_rsp = VideoSynthesis.fetch(task_id)
                        if status_rsp.status_code == 200:
                            status = status_rsp.output.task_status
                            if status == 'SUCCEEDED':
                                return status_rsp.output.video_url
                            elif status in ['FAILED', 'UNKNOWN']:
                                error_msg = status_rsp.output.get('message', '未知错误')
                                # 【核心修复】：拦截异步报错！不抛出异常，而是 break 跳出 while 循环，去尝试下一个模型
                                console.print(f"    [dim]⚠️ {m} 服务端渲染失败 ({error_msg})，自动切换下一个模型...[/dim]")
                                break 
                        else:
                            console.print(f"    [dim]⚠️ {m} 查询状态失败 ({status_rsp.message})，自动切换下一个模型...[/dim]")
                            break
                else:
                    console.print(f"    [dim]⚠️ {m} 提交失败 ({rsp.code}: {rsp.message})，尝试下一个...[/dim]")
                    
            # 如果所有的模型都轮询完了还是失败，才真正抛出异常触发降级保护
            raise Exception("所有可用的视频模型均已尝试完毕且均告失败，请检查阿里云平台额度。")

        video_url = await asyncio.to_thread(run_sdk)
        
        console.print(f"    📥 渲染完成！正在下载视频到本地...")
        vid_data = await asyncio.to_thread(requests.get, video_url)
        with open(output_path, 'wb') as f: 
            f.write(vid_data.content)
            
        console.print(f"[green]    ✅ 视频片段生动化完成: {os.path.basename(output_path)}[/green]")
        return output_path

    except Exception as e:
        console.print(f"[red]    ❌ 阿里云视频大模型调用异常: {str(e)}[/red]")
        return None

# ==========================================
# 模块：AI 场景企划与音乐总监
# ==========================================
def generate_custom_theme(user_idea):
    user_idea = user_idea.encode('utf-8', 'ignore').decode('utf-8')
    prompt = (
        f"你是一个睡眠冥想场景规划师。用户想法：【{user_idea}】。\n\n{TTS_SCRIPT_DIRECTIVE}\n\n"
        "「文案设定」需写成适合口播的设定，并在设定中体现会在成稿里使用的 [环境音：]、[停顿] 等节奏设计。\n"
        "严格按3行格式输出：\n主题名：\n文案设定：\n画面提示词：(英文，包含 cinematic vertical view, relaxing)\n"
    )
    response = text_client.chat.completions.create(model=API_CONFIG["text_model"], messages=[{"role": "user", "content": prompt}], stream=False)
    result_text = response.choices[0].message.content.strip()
    
    new_theme_name, new_story_prompt, new_image_prompt = "未命名自定义主题", f"关于{user_idea}的场景。要求温柔舒缓。", f"A cinematic vertical view of {user_idea}, relaxing, highly detailed, 4k."
    for line in result_text.split('\n'):
        line = line.strip().replace('**', '')
        if "主题名" in line: new_theme_name = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif "文案设定" in line: new_story_prompt = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif "画面提示词" in line: new_image_prompt = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            
    console.print(f"[green]  ✨ 新主题研发成功：【{new_theme_name}】[/green]")
    THEMES[new_theme_name] = {"story_prompt": new_story_prompt, "image_prompt": new_image_prompt, "bgm_file": ""}
    return new_theme_name

def download_bgm_from_youtube(keyword, output_filename):
    console.print(f"[yellow]  🌐 正在全网下载: '{keyword}'...[/yellow]")
    ydl_opts = {'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}], 'outtmpl': f'assets/{output_filename}', 'noplaylist': True, 'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([f"ytsearch1:{keyword} copyright free ambient relax music"])
        return f"{output_filename}.mp3"
    except Exception as e: return None

def select_best_bgm(theme_name):
    console.print("\n[bold cyan]🎧 正在呼叫 AI 音乐总监...[/bold cyan]")
    os.makedirs("assets", exist_ok=True)
    available_mp3s = [f for f in os.listdir("assets") if f.endswith(".mp3")]
    prompt = f"主题：【{theme_name}】\n本地库：\n{available_mp3s}\n任务：如果有合适的只输出 LOCAL:名.mp3。如果不合适去网上找，只输出 DOWNLOAD:极简英文搜索词。"
    try:
        response = text_client.chat.completions.create(model=API_CONFIG["text_model"], messages=[{"role": "user", "content": prompt}], stream=False)
        ai_decision = response.choices[0].message.content.strip().strip('\'"` ')
        if ai_decision.startswith("LOCAL:"):
            res = ai_decision.replace("LOCAL:", "").strip()
            if res in available_mp3s: return res
        elif ai_decision.startswith("DOWNLOAD:"):
            kw = ai_decision.replace("DOWNLOAD:", "").strip()
            res = download_bgm_from_youtube(kw, kw.replace(" ", "_").lower())
            if res: return res
        return None
    except: return None

# ==========================================
# 模块：多 Agent 深度剧本引擎
# ==========================================
def generate_story(theme_name, output_dir, target_words):
    text_path = os.path.join(output_dir, "story_draft.txt")
    if os.path.exists(text_path):
        with open(text_path, "r", encoding="utf-8") as f: return f.read()

    theme_info = THEMES[theme_name]
    theme_brief = theme_info.get("story_prompt", "")
    spec = TTS_SCRIPT_DIRECTIVE
    outline = text_client.chat.completions.create(
        model=API_CONFIG["text_model"],
        messages=[{"role": "user", "content": (
            f"你是睡眠冥想心理学家。主题【{theme_name}】。\n"
            f"主题氛围要求：{theme_brief}\n\n{spec}\n\n"
            "请写「三段式心理暗示大纲」：起—承—合；大纲里可标注计划在何处用 [环境音：] 与 [停顿]。"
        )}],
        stream=False,
    ).choices[0].message.content
    draft = text_client.chat.completions.create(
        model=API_CONFIG["text_model"],
        messages=[{"role": "user", "content": (
            f"你是深夜电台主播，声音要慢、稳、催眠感。\n{spec}\n\n"
            f"根据大纲扩写成完整口播稿（约 {target_words} 字量级）：\n{outline}\n\n"
            "必须实际写出 [环境音：…]、[停顿] 或 [停顿500ms]/[停顿1s] 等标记，位置要自然；禁止 [叹气][轻笑] 等会被念出来的方括号拟声词。"
        )}],
        stream=False,
    ).choices[0].message.content
    final_story = text_client.chat.completions.create(
        model=API_CONFIG["text_model"],
        messages=[{"role": "user", "content": (
            f"你是严苛主编：去掉 AI 腔与说教感，增强电影感与感官描写。\n{spec}\n\n"
            "保留初稿中所有 [环境音：]、[停顿…] 标记，不得删除或改成自然语言描述；可微调措辞与标点。\n\n初稿：\n"
            f"{draft}"
        )}],
        stream=False,
    ).choices[0].message.content

    with open(text_path, "w", encoding="utf-8") as f: f.write(final_story)
    return final_story

def generate_soothing_noise(output_path, duration=60):
    sr = 44100  
    noise = np.random.uniform(-1, 1, sr * duration)
    soothing_noise = np.convolve(noise, np.ones(150)/150, mode='same')
    clip = AudioArrayClip(np.vstack((soothing_noise, soothing_noise)).T, fps=sr)
    clip.write_audiofile(output_path, fps=sr, logger=None)
    return output_path


def _cosyvoice_model_for_voice(voice_name: str) -> str:
    """音色与 CosyVoice 模型须同代，否则 API 418。参见百炼文档。"""
    vn = (voice_name or "").lower()
    if "v2" in vn:
        return "cosyvoice-v2"
    if vn == "longanyang" or "_v3" in vn or vn.endswith("v3") or "v3" in vn:
        return "cosyvoice-v3-flash"
    return "cosyvoice-v1"


def _silence_seconds_for_markup(part: str):
    """解析 [环境音：…]、[停顿…]；返回静音时长（秒），非此类标记返回 None。"""
    p = part.strip()
    if re.match(r"^(\[环境音[^\]]*\]|【环境音[^】]*】)$", p):
        return float(API_CONFIG.get("tts_env_silence_seconds", 4.0))
    if p in ("[停顿]", "【停顿】"):
        return 0.8
    m = re.match(r"^\[停顿(\d+)ms\]$", p) or re.match(r"^【停顿(\d+)ms】$", p)
    if m:
        ms = int(m.group(1))
        ms = max(50, min(10000, ms))
        return ms / 1000.0
    m = re.match(r"^\[停顿(\d+(?:\.\d+)?)s\]$", p) or re.match(r"^【停顿(\d+(?:\.\d+)?)s】$", p)
    if m:
        sec = float(m.group(1))
        return max(0.05, min(10.0, sec))
    return None

# ==========================================
# 模块：阿里云 DashScope SDK 语音合成底层 (tts_v2 终极修复版)
# ==========================================
async def _synthesize_cosyvoice(text, output_path, speed=1.0):
    dashscope.api_key = API_CONFIG.get('cosyvoice_api_key', '')
    
    def run_sdk():
        # v2 版本的正确用法：实例化对象，直接传入参数
        synthesizer = SpeechSynthesizer(
            model='cosyvoice-v3-flash', # 模型版本
            voice=API_CONFIG.get('tts_voice', 'longxiaochun'),
            speech_rate=speed           # 语速参数
        )
        
        # 直接调用 call，v2 版本会直接返回干净的音频 bytes 流！
        audio_data = synthesizer.call(text)
        
        if audio_data:
            with open(output_path, 'wb') as f:
                f.write(audio_data)
        else:
            raise Exception("CosyVoice 返回了空的音频数据")

    # 包装为异步防止阻塞
    await asyncio.to_thread(run_sdk)

async def generate_audio(text, output_dir):
    voice_path = os.path.join(output_dir, "voice.mp3")
    console.print("\n[bold cyan][音频车间] 正在进行精准分段录制 (抛弃 SSML，启用物理混音)...[/bold cyan]")
    
    use_pro_voice = bool(API_CONFIG.get("cosyvoice_api_key", "").strip())
    
    # 工具：智能解析停顿秒数
    def parse_pause(tag):
        if "环境音" in tag: return 4.0
        m = re.search(r'停顿\s*([0-9.]+)\s*(s|ms|秒)', tag, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if m.group(2).lower() == 'ms': return val / 1000.0
            return val
        if "停顿" in tag: return 1.0
        return None

    # 1. 词法解析
    tokens = []
    for m in re.finditer(r'(\[.*?\]|【.*?】|\(.*?\)|（.*?）)|([^\[\]【】()（）]+)', text):
        tag = m.group(1)
        txt = m.group(2)
        if tag:
            t = tag.strip()
            # 记录语气参数，不生成任何 SSML
            if t in ("[慢速]", "【慢速】"):
                tokens.append({"type": "prosody", "speed": 0.8, "vol": 1.0, "raw": tag})
            elif t in ("[轻声]", "【轻声】"):
                tokens.append({"type": "prosody", "speed": 1.0, "vol": 0.4, "raw": tag})
            elif t in ("[极弱]", "【极弱】"):
                tokens.append({"type": "prosody", "speed": 0.6, "vol": 0.2, "raw": tag})
            else:
                sec = parse_pause(t)
                if sec is not None:
                    tokens.append({"type": "break", "sec": sec, "raw": tag})
        elif txt:
            sub_sentences = re.split(r'([。！？!?\n]+)', txt)
            for j in range(0, len(sub_sentences) - 1, 2):
                sent = sub_sentences[j] + sub_sentences[j+1]
                if sent.strip(): tokens.append({"type": "text", "text": sent.strip()})
            if len(sub_sentences) % 2 != 0 and sub_sentences[-1].strip():
                tokens.append({"type": "text", "text": sub_sentences[-1].strip()})

    # 2. 组装区块
    blocks = []
    current_speed = 1.0
    current_vol = 1.0
    
    for token in tokens:
        if token["type"] == "prosody":
            current_speed = token["speed"]
            current_vol = token["vol"]
        elif token["type"] == "break":
            blocks.append({"type": "pure_break", "sec": token["sec"], "raw": token["raw"]})
        elif token["type"] == "text":
            clean = token["text"].replace('**', '').replace('*', '').replace('---', '').strip()
            if re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', clean):
                blocks.append({"type": "speech", "text": clean, "speed": current_speed, "vol": current_vol})
                # 【核心修复】：读完这句话，立刻将大模型的状态重置为正常 [原音]，互不干扰！
                current_speed = 1.0
                current_vol = 1.0

    # 3. 合成与拼接
    audio_clips, temp_files, subtitles_info = [], [], []
    current_time = 0.0
    
    for i, block in enumerate(blocks):
        if block["type"] == "pure_break":
            sec = block["sec"]
            console.print(f"  ⏸️ 独立留白: '{block['raw']}' ({sec:.2f}s)")
            sr = 44100
            audio_clips.append(AudioArrayClip(np.zeros((int(sr * sec), 2)), fps=sr))
            current_time += sec
            continue

        sub_text_clean = block["text"]
        speed = block["speed"]
        vol = block["vol"]
        
        console.print(f"  🎙️ [速:{speed}, 音:{vol}]: {sub_text_clean[:15]}...")
        temp_path = os.path.join(output_dir, f"temp_voice_{i}.mp3")

        try:
            if use_pro_voice:
                # 仅传文本和 speed 参数，完全避开 SSML 坑
                await _synthesize_cosyvoice(sub_text_clean, temp_path, speed=speed)
            else:
                await edge_tts.Communicate(sub_text_clean, "zh-CN-XiaoxiaoNeural", rate="-10%").save(temp_path)
        except Exception as e:
            console.print(f"[red]  ❌ 语音合成失败，跳过该句: {e}[/red]")
            continue

        try:
            clip = AudioFileClip(temp_path)
            
            # 【物理降维打击】：压低音量
            if vol < 1.0:
                clip = clip.volumex(vol) 
                
            # ==========================================
            # 🎧 【核心听觉修复：消除数字硬切】
            # ==========================================
            # 根据这段音频的长短，动态计算淡入淡出时间
            # 极短的淡入(0.1s)消除起爆音，舒缓的淡出(0.4s)保留呼吸尾音
            fade_in_time = min(0.1, clip.duration / 3)
            fade_out_time = min(0.4, clip.duration / 3)
            
            clip = clip.fx(audio_fadein, fade_in_time).fx(audio_fadeout, fade_out_time)
            # ==========================================
                
            audio_clips.append(clip)
            temp_files.append(temp_path)
            subtitles_info.append({"text": sub_text_clean, "start": current_time, "duration": clip.duration})
            current_time += clip.duration
        except Exception as e:
            console.print(f"[red]  ❌ 读取音频片段失败: {e}[/red]")
            continue

    if not audio_clips:
        console.print("[bold red]❌ 严重错误：剧本中没有提取到任何有效语音！[/bold red]")
        return None, []
        
    console.print("  -> 正在拼接音频时间轴...")
    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(voice_path, logger=None)
    
    for c in audio_clips: c.close()
    for tf in temp_files:
        try: os.remove(tf)
        except: pass
    return voice_path, subtitles_info

# ==========================================
# 模块：图生图底图生成器 (修改为：只生成1张图片)
# ==========================================
def generate_multi_images(theme_name, output_dir):
    console.print("\n[bold cyan][视觉车间] 正在生成静态高质感背景图(单图模式)...[/bold cyan]")
    theme_info = THEMES[theme_name]
    
    output_filename = os.path.join(output_dir, f"scene_1.png")
    saved_images = []
    
    if os.path.exists(output_filename):
        saved_images.append(output_filename)
        return saved_images

    # 移除了时间修饰词循环，只生成一张主图
    pollination_prompt = f"{theme_info['image_prompt']}, 4k"
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(pollination_prompt)}?width=1024&height=1792&nologo=true&seed=999"
    
    for attempt in range(4):
        try:
            response = requests.get(image_url, timeout=60)
            response.raise_for_status() 
            with open(output_filename, 'wb') as f: 
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

# ==========================================
# 模块：终极剪辑包装 (修复无缝循环 + 运镜 + 字幕)
# ==========================================
def assemble_pro_video(image_paths, ai_video_paths, voice_path, subtitles_info, bgm_filename, total_minutes, theme_name, output_dir):
    if not image_paths: return console.print("[bold red]无背景素材，取消合成。[/bold red]")
    console.print(f"\n[bold cyan][最终剪辑] 正在进行视频混音与电影级视觉压制...[/bold cyan]")
    total_seconds = total_minutes * 60
    output_path = os.path.join(output_dir, f"Final_Video_{theme_name}.mp4")

    voice_clip = AudioFileClip(voice_path)
    if bgm_filename and os.path.exists(f"assets/{bgm_filename}"): bgm_clip = AudioFileClip(f"assets/{bgm_filename}")
    else:
        fb_bgm = "assets/auto_generated_noise.mp3"
        if not os.path.exists(fb_bgm): generate_soothing_noise(fb_bgm, 60)
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
            # 引入 vfx.loop 延长时长，并加上 crossfadein 实现伪无缝感
            clip = raw_clip.fx(vfx.loop, duration=duration_per_image)
        else:
            clip = apply_ken_burns(img_path, duration=duration_per_image, zoom_rate=0.15)
            
        if i > 0: clip = clip.crossfadein(2) # 统一转场
        video_clips.append(clip)
        
    final_video = concatenate_videoclips(video_clips, method="compose").set_audio(final_audio)
    
    console.print("  -> 正在压制电影级字幕...")
    font_path = "Arial"
    for fp in ["/mnt/c/Windows/Fonts/msyh.ttc", "/mnt/c/Windows/Fonts/simhei.ttf", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "font.ttf"]:
        if os.path.exists(fp): font_path = fp; break

    text_clips = []
    for sub in subtitles_info:
        raw_text = sub["text"].strip("。！？!?\n ")
        if not raw_text: continue
        wrapped_text = "\n".join([raw_text[j:j+14] for j in range(0, len(raw_text), 14)])
        try:
            txt_clip = TextClip(wrapped_text, font=font_path, fontsize=65, color='white', stroke_color='black', stroke_width=2, align='center')
            txt_clip = txt_clip.set_position(('center', 'center')).set_start(sub["start"] + 2.0).set_duration(sub["duration"]).crossfadein(0.3).crossfadeout(0.3)
            text_clips.append(txt_clip)
        except: break
            
    if text_clips: final_video = CompositeVideoClip([final_video] + text_clips)
    
    console.print("[bold cyan][渲染中] 开始渲染最终视频，请稍候...[/bold cyan]")
    final_video.write_videofile(output_path, fps=12, codec="libx264", audio_codec="aac", logger=None)
    console.print(Panel.fit(f"[bold green]🎉 真·视觉大片渲染完成！已保存在: {output_dir}[/bold green]"))