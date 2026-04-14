# debug.py
import asyncio
import os
import sys
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

import engine
from config import THEMES

console = Console()

# 创建一个专用的测试输出文件夹
DEBUG_DIR = "outputs/DEBUG_TEST"
os.makedirs(DEBUG_DIR, exist_ok=True)

async def debug_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    console.print(Panel.fit("[bold green]🛠️ Bedtime Story 模块化单步调试工具 🛠️[/bold green]"))
    console.print("请选择要单独调试的模块：")
    console.print("[1] 📝 仅测试【剧本生成】 (检查大模型 Agent 效果)")
    console.print("[2] 🎙️ 仅测试【语音合成】 (读取 debug 文件夹里的 story_draft.txt)")
    console.print("[3] 🖼️ 仅测试【单图生成】 (检查 Pollinations 画图)")
    console.print("[4] 🎬 仅测试【AI 视频】 (读取 debug 文件夹里的 scene_1.png，测试智谱 API)")
    console.print("[5] 退出")
    
    choice = Prompt.ask("\n请输入选项", choices=["1", "2", "3", "4", "5"], default="5")
    
    theme_name = "午夜慢车" # 默认使用测试主题
    
    if choice == "1":
        console.print("\n[bold]📝 开始测试：剧本生成[/bold]")
        story = engine.generate_story(theme_name, DEBUG_DIR, 500)
        console.print("\n[bold green]✅ 剧本生成成功！内容如下：[/bold green]")
        console.print(story)
        
    elif choice == "2":
        console.print("\n[bold]🎙️ 开始测试：语音合成[/bold]")
        story_path = os.path.join(DEBUG_DIR, "story_draft.txt")
        if not os.path.exists(story_path):
            console.print("[red]❌ 找不到 story_draft.txt，请先运行 [1] 生成剧本，或手动在 outputs/DEBUG_TEST 里建一个。[/red]")
            return
            
        with open(story_path, "r", encoding="utf-8") as f:
            story = f.read()
            
        # 强制删除已有的 voice.mp3 以确保重新生成
        voice_path = os.path.join(DEBUG_DIR, "voice.mp3")
        if os.path.exists(voice_path): os.remove(voice_path)
            
        voice_file, subtitles = await engine.generate_audio(story, DEBUG_DIR)
        if voice_file:
            console.print(f"\n[bold green]✅ 语音生成成功！保存在: {voice_file}[/bold green]")
            
    elif choice == "3":
        console.print("\n[bold]🖼️ 开始测试：单图生成[/bold]")
        img_path = os.path.join(DEBUG_DIR, "scene_1.png")
        if os.path.exists(img_path): os.remove(img_path)
        
        images = engine.generate_multi_images(theme_name, DEBUG_DIR)
        if images:
            console.print(f"\n[bold green]✅ 图片生成成功！保存在: {images[0]}[/bold green]")

    elif choice == "4":
        console.print("\n[bold]🎬 开始测试：智谱 AI 视频生成[/bold]")
        img_path = os.path.join(DEBUG_DIR, "scene_1.png")
        vid_path = os.path.join(DEBUG_DIR, "ai_video_1.mp4")
        
        if not os.path.exists(img_path):
            console.print("[red]❌ 找不到 scene_1.png，请先运行 [3] 生成图片，或手动放一张进去。[/red]")
            return
            
        if os.path.exists(vid_path): os.remove(vid_path)
            
        console.print(f"正在读取 {img_path} 发送至 API...")
        video_file = await engine.generate_ai_video(img_path, vid_path)
        
        if video_file:
            console.print(f"\n[bold green]✅ 视频生成成功！保存在: {video_file}[/bold green]")
        else:
            console.print("\n[bold red]❌ 视频生成失败！请查看上方打印的详细报错堆栈。[/bold red]")
            
    elif choice == "5":
        sys.exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(debug_menu())
    except KeyboardInterrupt:
        console.print("\n[yellow]已退出调试。[/yellow]")