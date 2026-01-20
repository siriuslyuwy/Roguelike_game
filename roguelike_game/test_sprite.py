"""测试精灵图加载的脚本"""
import pygame as pg
import sys
import os

# 添加 game 模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.sprites import load_sprite_image, get_sprite_frames

def main():
    pg.init()
    screen = pg.display.set_mode((800, 600))
    pg.display.set_caption("精灵图测试")
    clock = pg.time.Clock()
    font = pg.font.SysFont(None, 24)
    
    # 测试加载战士的 idle_0.png
    warrior_idle_0 = load_sprite_image("战士", "idle", 0)
    
    # 测试获取所有帧
    idle_frames = get_sprite_frames("战士", "idle")
    walk_frames = get_sprite_frames("战士", "walk")
    attack_frames = get_sprite_frames("战士", "attack")
    
    running = True
    frame_index = 0
    animation_timer = 0.0
    
    while running:
        dt = clock.tick(60) / 1000.0
        animation_timer += dt
        
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    running = False
        
        screen.fill((40, 40, 50))
        
        # 显示加载信息
        y_offset = 20
        
        # 测试结果
        if warrior_idle_0:
            text = font.render(f"✓ 成功加载 idle_0.png (尺寸: {warrior_idle_0.get_size()})", True, (0, 255, 0))
            screen.blit(text, (20, y_offset))
            y_offset += 30
            
            # 显示精灵图（原始大小）
            screen.blit(warrior_idle_0, (20, y_offset))
            
            # 显示放大版本
            scaled = pg.transform.scale(warrior_idle_0, (96, 96))
            screen.blit(scaled, (100, y_offset))
            
            y_offset += 120
        else:
            text = font.render("✗ 未能加载 idle_0.png", True, (255, 0, 0))
            screen.blit(text, (20, y_offset))
            y_offset += 30
        
        # 显示帧数信息
        text = font.render(f"idle 帧数: {len(idle_frames)}", True, (255, 255, 255))
        screen.blit(text, (20, y_offset))
        y_offset += 30
        
        text = font.render(f"walk 帧数: {len(walk_frames)}", True, (255, 255, 255))
        screen.blit(text, (20, y_offset))
        y_offset += 30
        
        text = font.render(f"attack 帧数: {len(attack_frames)}", True, (255, 255, 255))
        screen.blit(text, (20, y_offset))
        y_offset += 30
        
        # 如果有 idle 帧，播放动画
        if idle_frames:
            frame_index = int(animation_timer * 8) % len(idle_frames)
            current_frame = idle_frames[frame_index]
            scaled_frame = pg.transform.scale(current_frame, (96, 96))
            
            text = font.render(f"动画播放 (帧 {frame_index}/{len(idle_frames)-1}):", True, (255, 255, 255))
            screen.blit(text, (20, y_offset))
            y_offset += 30
            
            screen.blit(scaled_frame, (20, y_offset))
        
        # 提示信息
        hint = font.render("按 ESC 退出", True, (150, 150, 150))
        screen.blit(hint, (20, 550))
        
        pg.display.flip()
    
    pg.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()

