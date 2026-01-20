"""精灵图调试工具 - 详细显示精灵图加载状态"""
import pygame as pg
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.sprites import (
    load_sprite_image, 
    get_sprite_frames, 
    get_sprite_frame_count,
    UNIT_NAME_TO_SPRITE_FOLDER
)
from game.constants import UNIT_TYPES
from game.game import ORDER_KEYS

def main():
    pg.init()
    screen = pg.display.set_mode((1200, 800))
    pg.display.set_caption("精灵图调试工具")
    clock = pg.time.Clock()
    font = pg.font.SysFont("microsoftyaheimicrosoftyaheiui", 20)
    small_font = pg.font.SysFont("microsoftyaheimicrosoftyaheiui", 16)
    
    # 当前查看的单位索引
    current_unit_idx = 0
    animation_timer = 0.0
    current_animation = "idle"  # idle, walk, attack
    
    # 获取所有单位
    unit_names = [UNIT_TYPES[key].name for key in ORDER_KEYS]
    
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        animation_timer += dt
        
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    running = False
                elif event.key == pg.K_LEFT:
                    current_unit_idx = (current_unit_idx - 1) % len(unit_names)
                    animation_timer = 0.0
                elif event.key == pg.K_RIGHT:
                    current_unit_idx = (current_unit_idx + 1) % len(unit_names)
                    animation_timer = 0.0
                elif event.key == pg.K_1:
                    current_animation = "idle"
                    animation_timer = 0.0
                elif event.key == pg.K_2:
                    current_animation = "walk"
                    animation_timer = 0.0
                elif event.key == pg.K_3:
                    current_animation = "attack"
                    animation_timer = 0.0
        
        screen.fill((30, 30, 40))
        
        # 当前单位信息
        unit_name = unit_names[current_unit_idx]
        unit_key = ORDER_KEYS[current_unit_idx]
        unit_type = UNIT_TYPES[unit_key]
        
        # 标题
        title = font.render(f"当前单位: {unit_name} ({unit_key})", True, (255, 255, 100))
        screen.blit(title, (20, 20))
        
        # 精灵图文件夹
        folder_name = UNIT_NAME_TO_SPRITE_FOLDER.get(unit_name, "未知")
        folder_text = small_font.render(f"精灵图文件夹: assets/sprites/{folder_name}/", True, (200, 200, 200))
        screen.blit(folder_text, (20, 50))
        
        # 获取各动画的帧数
        idle_count = get_sprite_frame_count(unit_name, "idle")
        walk_count = get_sprite_frame_count(unit_name, "walk")
        attack_count = get_sprite_frame_count(unit_name, "attack")
        
        y = 80
        
        # 显示帧数信息
        def render_status(label, count, is_current=False):
            color = (0, 255, 100) if count > 0 else (255, 100, 100)
            if is_current:
                color = (255, 255, 0)
            status = "✓" if count > 0 else "✗"
            text = small_font.render(f"{status} {label}: {count} 帧", True, color)
            return text
        
        screen.blit(render_status("idle", idle_count, current_animation == "idle"), (20, y))
        y += 25
        screen.blit(render_status("walk", walk_count, current_animation == "walk"), (20, y))
        y += 25
        screen.blit(render_status("attack", attack_count, current_animation == "attack"), (20, y))
        y += 40
        
        # 显示当前动画
        anim_text = font.render(f"当前动画: {current_animation}", True, (150, 200, 255))
        screen.blit(anim_text, (20, y))
        y += 35
        
        # 获取当前动画的所有帧
        frames = get_sprite_frames(unit_name, current_animation)
        
        if frames:
            # 计算当前帧索引
            frame_idx = int(animation_timer * 8) % len(frames)
            current_frame = frames[frame_idx]
            
            # 显示帧信息
            frame_info = small_font.render(f"帧 {frame_idx + 1}/{len(frames)}", True, (180, 180, 180))
            screen.blit(frame_info, (20, y))
            y += 30
            
            # 显示原始尺寸
            orig_size = current_frame.get_size()
            size_text = small_font.render(f"原始尺寸: {orig_size[0]}x{orig_size[1]} px", True, (180, 180, 180))
            screen.blit(size_text, (20, y))
            y += 35
            
            # 绘制精灵图（多种尺寸）
            display_y = y
            
            # 1. 原始尺寸
            label1 = small_font.render("原始尺寸:", True, (150, 150, 150))
            screen.blit(label1, (20, display_y))
            screen.blit(current_frame, (20, display_y + 25))
            
            # 2. 2x 放大
            scaled_2x = pg.transform.scale(current_frame, (orig_size[0] * 2, orig_size[1] * 2))
            label2 = small_font.render("2x 放大:", True, (150, 150, 150))
            screen.blit(label2, (150, display_y))
            screen.blit(scaled_2x, (150, display_y + 25))
            
            # 3. 4x 放大
            scaled_4x = pg.transform.scale(current_frame, (orig_size[0] * 4, orig_size[1] * 4))
            label3 = small_font.render("4x 放大:", True, (150, 150, 150))
            screen.blit(label3, (350, display_y))
            screen.blit(scaled_4x, (350, display_y + 25))
            
            # 4. 翻转效果（面向左侧）
            flipped = pg.transform.flip(scaled_4x, True, False)
            label4 = small_font.render("翻转 (面向左):", True, (150, 150, 150))
            screen.blit(label4, (600, display_y))
            screen.blit(flipped, (600, display_y + 25))
            
            # 显示所有帧的缩略图
            thumb_y = display_y + 250
            thumb_label = small_font.render("所有帧:", True, (200, 200, 200))
            screen.blit(thumb_label, (20, thumb_y))
            thumb_y += 25
            
            thumb_x = 20
            for i, frame in enumerate(frames):
                thumb_size = 64
                thumb = pg.transform.scale(frame, (thumb_size, thumb_size))
                
                # 高亮当前帧
                if i == frame_idx:
                    pg.draw.rect(screen, (255, 255, 0), (thumb_x - 2, thumb_y - 2, thumb_size + 4, thumb_size + 4), 2)
                
                screen.blit(thumb, (thumb_x, thumb_y))
                
                # 帧编号
                num_text = small_font.render(str(i), True, (180, 180, 180))
                screen.blit(num_text, (thumb_x + thumb_size // 2 - 5, thumb_y + thumb_size + 5))
                
                thumb_x += thumb_size + 10
                if thumb_x > 1100:
                    thumb_x = 20
                    thumb_y += thumb_size + 30
        else:
            # 没有找到精灵图
            no_sprite_text = font.render("未找到精灵图文件", True, (255, 100, 100))
            screen.blit(no_sprite_text, (20, y))
            y += 40
            
            # 显示期望的文件路径
            expected_path = f"assets/sprites/{folder_name}/{current_animation}_0.png"
            path_text = small_font.render(f"期望路径: {expected_path}", True, (200, 100, 100))
            screen.blit(path_text, (20, y))
            y += 30
            
            hint_text = small_font.render("请确保精灵图文件在正确的位置", True, (200, 100, 100))
            screen.blit(hint_text, (20, y))
        
        # 控制提示
        hint_y = 750
        hints = [
            "← → : 切换单位",
            "1/2/3 : 切换动画 (idle/walk/attack)",
            "ESC : 退出",
        ]
        for hint in hints:
            hint_text = small_font.render(hint, True, (120, 120, 120))
            screen.blit(hint_text, (20, hint_y))
            hint_y += 20
        
        # 单位列表预览
        list_x = 900
        list_y = 50
        list_title = small_font.render("单位列表:", True, (180, 180, 180))
        screen.blit(list_title, (list_x, list_y))
        list_y += 25
        
        for i, name in enumerate(unit_names[:10]):  # 只显示前10个
            color = (255, 255, 100) if i == current_unit_idx else (150, 150, 150)
            prefix = "→ " if i == current_unit_idx else "  "
            list_text = small_font.render(f"{prefix}{name}", True, color)
            screen.blit(list_text, (list_x, list_y))
            list_y += 22
        
        pg.display.flip()
    
    pg.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()

