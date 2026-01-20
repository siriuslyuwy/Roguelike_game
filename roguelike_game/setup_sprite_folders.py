"""自动创建所有单位的精灵图文件夹结构"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.sprites import UNIT_NAME_TO_SPRITE_FOLDER

def create_sprite_folders():
    """创建所有单位的精灵图文件夹"""
    base_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "sprites")
    
    # 确保 assets/sprites 目录存在
    os.makedirs(base_dir, exist_ok=True)
    
    print("[*] 开始创建精灵图文件夹结构...")
    print(f"[*] 基础目录: {os.path.abspath(base_dir)}")
    print("-" * 60)
    
    created_count = 0
    existing_count = 0
    
    for unit_name, folder_name in UNIT_NAME_TO_SPRITE_FOLDER.items():
        folder_path = os.path.join(base_dir, folder_name)
        
        if os.path.exists(folder_path):
            print(f"[OK] {unit_name:8s} ({folder_name:20s}) - 已存在")
            existing_count += 1
        else:
            os.makedirs(folder_path, exist_ok=True)
            print(f"[+] {unit_name:8s} ({folder_name:20s}) - 已创建")
            created_count += 1
        
        # 创建一个 README.txt 说明文件
        readme_path = os.path.join(folder_path, "README.txt")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(f"{unit_name} 精灵图文件夹\n")
                f.write("=" * 40 + "\n\n")
                f.write("请在此文件夹中放置以下精灵图文件：\n\n")
                f.write("待机动画 (idle):\n")
                f.write("  - idle_0.png\n")
                f.write("  - idle_1.png (可选)\n")
                f.write("  - idle_2.png (可选)\n\n")
                f.write("行走动画 (walk):\n")
                f.write("  - walk_0.png\n")
                f.write("  - walk_1.png\n")
                f.write("  - walk_2.png\n")
                f.write("  - walk_3.png (可选)\n\n")
                f.write("攻击动画 (attack):\n")
                f.write("  - attack_0.png\n")
                f.write("  - attack_1.png\n")
                f.write("  - attack_2.png (可选)\n\n")
                f.write("要求：\n")
                f.write("  - 尺寸: 48×48 像素\n")
                f.write("  - 格式: PNG (透明背景)\n")
                f.write("  - 颜色模式: RGBA\n\n")
                f.write("详见 sprite.md 文档。\n")
    
    print("-" * 60)
    print(f"[*] 完成！")
    print(f"   - 新建文件夹: {created_count} 个")
    print(f"   - 已存在文件夹: {existing_count} 个")
    print(f"   - 总计: {created_count + existing_count} 个")
    print()
    print("[*] 接下来:")
    print("   1. 为每个单位创建精灵图文件 (参考 sprite.md)")
    print("   2. 使用 'py sprite_debug.py' 验证精灵图")
    print("   3. 使用 'py main.py' 在游戏中查看效果")
    print()

def check_sprite_status():
    """检查所有单位的精灵图状态"""
    base_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "sprites")
    
    print("\n" + "=" * 60)
    print("[*] 精灵图状态检查")
    print("=" * 60)
    
    for unit_name, folder_name in UNIT_NAME_TO_SPRITE_FOLDER.items():
        folder_path = os.path.join(base_dir, folder_name)
        
        if not os.path.exists(folder_path):
            print(f"[X] {unit_name:8s} - 文件夹不存在")
            continue
        
        # 检查各种动画文件
        idle_count = 0
        walk_count = 0
        attack_count = 0
        
        for i in range(10):  # 最多检查 10 帧
            if os.path.exists(os.path.join(folder_path, f"idle_{i}.png")):
                idle_count += 1
            else:
                break
        
        for i in range(10):
            if os.path.exists(os.path.join(folder_path, f"walk_{i}.png")):
                walk_count += 1
            else:
                break
        
        for i in range(10):
            if os.path.exists(os.path.join(folder_path, f"attack_{i}.png")):
                attack_count += 1
            else:
                break
        
        total = idle_count + walk_count + attack_count
        
        if total == 0:
            print(f"[ ] {unit_name:8s} - 无精灵图")
        elif total < 3:
            print(f"[~] {unit_name:8s} - 部分完成 (idle:{idle_count} walk:{walk_count} attack:{attack_count})")
        else:
            print(f"[V] {unit_name:8s} - 已完成 (idle:{idle_count} walk:{walk_count} attack:{attack_count})")
    
    print("=" * 60)

if __name__ == "__main__":
    create_sprite_folders()
    check_sprite_status()

