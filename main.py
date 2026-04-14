# main.py
import asyncio
import os
import sys
import time
from datetime import datetime
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from config import THEMES, SKIP_FINAL_VIDEO_RENDER, API_CONFIG
import engine

console = Console()


def _check_api_keys():
    """启动前校验必需的 API key，缺失时给出明确提示。"""
    key = (API_CONFIG.get("proxy_api_key") or "").strip()
    if not key:
        console.print(
            "[bold red]错误：未检测到任何 API Key。[/bold red]\n"
            "请在项目根目录的 .env 文件中填写 DASHSCOPE_API_KEY（推荐，一个 key 覆盖全部功能）。\n"
            "申请地址：https://dashscope.console.aliyun.com/\n"
            "参考 .env.example 中的格式。"
        )
        return False
    tts_key = (API_CONFIG.get("cosyvoice_api_key") or "").strip()
    if not tts_key:
        console.print(
            "[yellow]提示：语音 API Key 未配置，语音将使用免费的 edge-tts 降级方案。[/yellow]"
        )
    return True

async def process_story_and_audio(selected_theme, output_dir, target_words):
    story = await asyncio.to_thread(engine.generate_story, selected_theme, output_dir, target_words)
    voice_file, subtitles_info = await engine.generate_audio(story, output_dir)
    return voice_file, subtitles_info

async def process_images_and_videos(selected_theme, output_dir):
    image_files = await asyncio.to_thread(engine.generate_multi_images, selected_theme, output_dir)
    console.print("\n[bold yellow]🚀 正在将静态图片发送至 AI 视频大模型进行动态重构...[/bold yellow]")
    video_tasks = []
    for i, img_path in enumerate(image_files):
        video_out_path = os.path.join(output_dir, f"ai_video_{i+1}.mp4")
        video_tasks.append(engine.generate_ai_video(img_path, video_out_path))
        
    ai_video_files = await asyncio.gather(*video_tasks)
    return image_files, ai_video_files


async def interactive_main():
    os.system('cls' if os.name == 'nt' else 'clear')
    console.print(Panel.fit("[bold magenta]✨ 深夜治愈系 - 视频全自动生产工厂 (AI视频 + 多平台封面) ✨[/bold magenta]"))
    
    mode = Prompt.ask("\n请选择操作模式: [1] 新建创作任务 [2] 恢复中断的任务", choices=["1", "2"], default="1")
    
    if mode == "2":
        folders = sorted([f for f in os.listdir("outputs") if os.path.isdir(os.path.join("outputs", f))], reverse=True)
        if not folders: return console.print("[red]没有可恢复的历史任务。[/red]")
        for i, f in enumerate(folders): console.print(f"[{i+1}] {f}")
        f_choice = Prompt.ask("请选择要恢复的项目序号", choices=[str(i+1) for i in range(len(folders))], default="1")
        selected_folder = folders[int(f_choice)-1]
        output_dir = os.path.join("outputs", selected_folder)
        selected_theme = selected_folder.split('_', 3)[3] if len(selected_folder.split('_', 3)) >= 4 else list(THEMES.keys())[0]
        if selected_theme not in THEMES: 
            THEMES[selected_theme] = {"story_prompt": "从历史任务恢复", "image_prompt": f"A cinematic view of {selected_theme}", "bgm_file": ""}
        target_words = 800
        total_minutes = int(Prompt.ask("请重新确认生成的视频【总时长】 (分钟)", default="10"))
        
    else:
        console.print("\n[bold]你想做什么类型的主题？[/bold]\n[1] 从经典主题库中选择\n[2] 告诉 AI 我的新想法，让它现场编一个新场景！")
        theme_source = Prompt.ask("请选择", choices=["1", "2"], default="1")
        if theme_source == "1":
            theme_choices = list(THEMES.keys())
            for i, theme in enumerate(theme_choices): console.print(f"[{i+1}] {theme}")
            selected_theme = theme_choices[int(Prompt.ask("\n请选择", choices=[str(i+1) for i in range(len(theme_choices))], default="1"))-1]
        else:
            selected_theme = engine.generate_custom_theme(Prompt.ask("\n[yellow]请简单描述你的想法[/yellow]"))

        target_words = int(Prompt.ask("请设置故事的【目标字数】 (例如 600)", default="800"))
        total_minutes = int(Prompt.ask("请设置视频的【总时长】 (分钟)", default="10"))
        output_dir = f"outputs/Story_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{selected_theme}"
        os.makedirs(output_dir, exist_ok=True)
        
    os.makedirs("assets", exist_ok=True) 
    
    console.print("\n[bold yellow]🚀 启动高并发超级管线！(图生视频、文案配音、选曲、做封面 同步进行...)[/bold yellow]")
    start_time = time.time()
    
    # ==========================================
    # 四大支线兵分四路，互不干扰并发执行
    # ==========================================
    task_visuals = process_images_and_videos(selected_theme, output_dir)
    task_bgm = asyncio.to_thread(engine.select_best_bgm, selected_theme)
    task_story_audio = process_story_and_audio(selected_theme, output_dir, target_words)
    # 新增并发任务：专属封面车间
    task_cover = asyncio.to_thread(engine.generate_and_crop_cover, selected_theme, output_dir)
    
    # 统一收网
    (image_files, ai_video_files), ai_selected_bgm, (voice_file, subtitles_info), _ = await asyncio.gather(
        task_visuals, task_bgm, task_story_audio, task_cover
    )
    
    # 最后一步：剪辑渲染包装（config.SKIP_FINAL_VIDEO_RENDER=True 时跳过）
    if SKIP_FINAL_VIDEO_RENDER:
        console.print(
            "\n[bold yellow]已跳过最终视频渲染（config.SKIP_FINAL_VIDEO_RENDER = True）。[/bold yellow]"
            "\n[dim]输出目录内仍有：story_draft、voice.mp3、scene_*.png、封面图及 ai_video_*.mp4（若有）等素材。[/dim]"
        )
    else:
        engine.assemble_pro_video(
            image_paths=image_files,
            ai_video_paths=ai_video_files,
            voice_path=voice_file,
            subtitles_info=subtitles_info,
            bgm_filename=ai_selected_bgm,
            total_minutes=total_minutes,
            theme_name=selected_theme,
            output_dir=output_dir,
        )

    end_time = time.time()
    if SKIP_FINAL_VIDEO_RENDER:
        done_msg = (
            "[bold green]管线任务完成（未压制正片）。输出文件夹已包含：\n"
            "1. 故事文稿与配音\n2. 配图与（可选）AI 视频片段\n3. B站 / 抖音 / 小红书封面\n\n"
            f"总耗时: {end_time - start_time:.2f} 秒\n"
            "[dim]需要 Final MP4 时将 config.SKIP_FINAL_VIDEO_RENDER 改为 False。[/dim][/bold green]"
        )
    else:
        done_msg = (
            f"[bold green]全部任务圆满完成！输出文件夹已包含：\n1. 高清正片 MP4\n2. B站封面 (16:9)\n"
            f"3. 抖音封面 (9:16)\n4. 小红书封面 (3:4)\n\n总耗时: {end_time - start_time:.2f} 秒[/bold green]"
        )
    console.print(Panel.fit(done_msg))

if __name__ == "__main__":
    import moviepy
    if int(moviepy.__version__.split('.')[0]) >= 2:
        console.print("[bold red]严重错误：检测到 moviepy 版本 >= 2.0。请安装 moviepy<2.0。[/bold red]")
    elif not _check_api_keys():
        sys.exit(1)
    else:
        try:
            asyncio.run(interactive_main())
        except KeyboardInterrupt:
            console.print("\n\n[bold green]🌙 收到中断指令，已安全终止任务。晚安，朋友！[/bold green]\n")
            sys.exit(0)