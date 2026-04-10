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

from config import API_CONFIG, PROTAGONIST, THEMES

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
# 模块：图生视频大模型引擎 (智谱 CogVideoX)
# ==========================================
async def generate_ai_video(image_path, output_path):
    api_key = API_CONFIG.get("zhipu_api_key", "").strip()
    if not api_key: return None 
        
    if os.path.exists(output_path): return output_path 

    try:
        from zhipuai import ZhipuAI
        client = ZhipuAI(api_key=api_key)
        
        with open(image_path, "rb") as f:
            base64_img = base64.b64encode(f.read()).decode('utf-8')
            
        console.print(f"    🎬 唤醒 CogVideoX 生成动态视频: {os.path.basename(image_path)}...")
        response = await asyncio.to_thread(client.videos.generations, model="cogvideox", image_url=f"data:image/png;base64,{base64_img}")
        task_id = response.id
        
        while True:
            await asyncio.sleep(5) 
            result = await asyncio.to_thread(client.videos.retrieve_videos_result, id=task_id)
            status = result.task_status
            if status == "SUCCESS":
                video_url = result.video_result[0].url
                break
            elif status in ["FAIL", "FAILED"]:
                return None
                
        vid_data = await asyncio.to_thread(requests.get, video_url)
        with open(output_path, 'wb') as f: f.write(vid_data.content)
            
        console.print(f"[green]    ✅ 视频片段生动化完成: {os.path.basename(output_path)}[/green]")
        return output_path
    except Exception as e:
        console.print(f"[red]    ❌ 视频大模型调用异常: {e}。触发降级保护。[/red]")
        return None

# ==========================================
# 模块：AI 场景企划与音乐总监
# ==========================================
def generate_custom_theme(user_idea):
    user_idea = user_idea.encode('utf-8', 'ignore').decode('utf-8')
    prompt = f"你是一个睡眠冥想场景规划师。用户想法：【{user_idea}】。\n严格按3行格式输出：\n主题名：\n文案设定：\n画面提示词：(英文，包含 cinematic vertical view, relaxing)\n"
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
    outline = text_client.chat.completions.create(model=API_CONFIG["text_model"], messages=[{"role": "user", "content": f"心理学家。主题【{theme_name}】。写「三段式心理暗示大纲」。"}], stream=False).choices[0].message.content
    draft = text_client.chat.completions.create(model=API_CONFIG["text_model"], messages=[{"role": "user", "content": f"电台主播。大纲：\n{outline}\n要求：插入[环境音：xx]留白，以及[叹气]或[轻笑]增加呼吸感。"}], stream=False).choices[0].message.content
    final_story = text_client.chat.completions.create(model=API_CONFIG["text_model"], messages=[{"role": "user", "content": f"严苛主编。去AI味，电影感。保留原格式。初稿：\n{draft}"}], stream=False).choices[0].message.content

    with open(text_path, "w", encoding="utf-8") as f: f.write(final_story)
    return final_story

def generate_soothing_noise(output_path, duration=60):
    sr = 44100  
    noise = np.random.uniform(-1, 1, sr * duration)
    soothing_noise = np.convolve(noise, np.ones(150)/150, mode='same')
    clip = AudioArrayClip(np.vstack((soothing_noise, soothing_noise)).T, fps=sr)
    clip.write_audiofile(output_path, fps=sr, logger=None)
    return output_path

# ==========================================
# 模块：双引擎智能配音与字幕
# ==========================================
async def _synthesize_cosyvoice(text, output_path):
    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/text-to-speech/text-to-speech"
    # === 修复：删除了导致报错的 X-DashScope-WorkSpace ===
    headers = {"Authorization": f"Bearer {API_CONFIG['cosyvoice_api_key']}", "Content-Type": "application/json"}
    payload = {"model": "cosyvoice-v1", "input": {"text": text}, "parameters": {"voice": API_CONFIG["tts_voice"], "speech_rate": -15}}
    response = await asyncio.to_thread(requests.post, url, headers=headers, json=payload, timeout=30)
    if response.status_code == 200:
        with open(output_path, "wb") as f: f.write(response.content)
    else:
        raise Exception(f"CosyVoice API Error: {response.text}")

async def generate_audio(text, output_dir):
    voice_path = os.path.join(output_dir, "voice.mp3")
    console.print("\n[bold cyan][音频车间] 正在进行精准分段录制...[/bold cyan]")
    
    use_pro_voice = bool(API_CONFIG.get("cosyvoice_api_key", "").strip())
    
    parts = re.split(r'(\[.*?\]|【.*?】|\(.*?\)|（.*?）)', text)
    audio_clips, temp_files, subtitles_info = [], [], []
    current_time = 0.0
    fallback_voice = "zh-CN-XiaoxiaoNeural"
    
    for i, part in enumerate(parts):
        part = part.strip()
        if not part: continue
        is_sfx = bool(re.match(r'^(\[环境音.*?\]|【环境音.*?】)$', part))
        
        if not is_sfx:
            sub_sentences = re.split(r'([。！？!?\n]+)', part)
            combined_sentences = [sub_sentences[j] + sub_sentences[j+1] for j in range(0, len(sub_sentences)-1, 2) if j+1 < len(sub_sentences)]
            if len(sub_sentences) % 2 != 0 and sub_sentences[-1]: combined_sentences.append(sub_sentences[-1])
            
            for j, sub_sentence in enumerate(combined_sentences):
                clean_text = sub_sentence.replace('**', '').replace('*', '').replace('---', '').strip()
                if not re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', clean_text): continue
                
                temp_path = os.path.join(output_dir, f"temp_voice_{i}_{j}.mp3")
                
                try:
                    if use_pro_voice: await _synthesize_cosyvoice(clean_text, temp_path)
                    else:
                        edge_clean_text = re.sub(r'\[.*?\]|【.*?】', '', clean_text)
                        if not edge_clean_text.strip(): continue
                        await edge_tts.Communicate(edge_clean_text, fallback_voice, rate="-10%", pitch="-2Hz").save(temp_path)
                except Exception as e:
                    continue
                
                try:
                    clip = AudioFileClip(temp_path)
                    audio_clips.append(clip)
                    temp_files.append(temp_path)
                    sub_text_clean = re.sub(r'\[.*?\]|【.*?】', '', clean_text).strip()
                    subtitles_info.append({"text": sub_text_clean, "start": current_time, "duration": clip.duration})
                    current_time += clip.duration
                except Exception as e:
                    continue
        else:
            sr = 44100
            audio_clips.append(AudioArrayClip(np.zeros((int(sr * 4), 2)), fps=sr))
            current_time += 4.0

    if not audio_clips: return None, []
    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(voice_path, logger=None)
    for c in audio_clips: c.close()
    for tf in temp_files:
        try: os.remove(tf)
        except: pass
    return voice_path, subtitles_info

# ==========================================
# 模块：图生图底图生成器
# ==========================================
def generate_multi_images(theme_name, output_dir):
    console.print("\n[bold cyan][视觉车间] 正在生成静态高质感背景图...[/bold cyan]")
    theme_info = THEMES[theme_name]
    saved_images = []
    for i, modifier in enumerate(["late evening lighting", "deep night, dark and moody", "midnight, very dark, cinematic shadows"]):
        output_filename = os.path.join(output_dir, f"scene_{i+1}.png")
        if os.path.exists(output_filename):
            saved_images.append(output_filename)
            continue
        image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(f'{theme_info['image_prompt']}, {modifier}, 4k')}?width=1024&height=1792&nologo=true&seed={i*999}"
        for attempt in range(4):
            try:
                response = requests.get(image_url, timeout=60)
                response.raise_for_status() 
                with open(output_filename, 'wb') as f: f.write(response.content)
                saved_images.append(output_filename)
                time.sleep(3) 
                break
            except Exception as e:
                if attempt < 3: time.sleep(5)
                else: break
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