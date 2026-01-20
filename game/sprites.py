from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import pygame as pg


# 兵种名称（中文）到文件夹名的映射
UNIT_NAME_TO_SPRITE_FOLDER: Dict[str, str] = {
    "战士": "warrior",
    "盾卫": "shield",
    "游击": "scout",
    "狂战": "berserker",
    "牧师": "medic",
    "弓手": "archer",
    "法师": "mage",
    "犀牛": "rhino",
    "刺客": "assassin",
    "破箭": "interceptor",
    "鼓手": "drummer",
    "矛兵": "spearman",
    "冰弓": "frost_archer",
    "自爆车": "exploder",
    "轻骑": "light_cavalry",
}


@lru_cache(maxsize=128)
def load_sprite_image(unit_name: str, animation_state: str, frame: int) -> Optional[pg.Surface]:
    """
    加载精灵图
    
    Args:
        unit_name: 兵种名称（中文，如 "法师"）
        animation_state: 动画状态（"idle", "walk", "attack"）
        frame: 帧索引（从 0 开始）
    
    Returns:
        加载的图片 Surface，如果不存在则返回 None
    """
    folder_name = UNIT_NAME_TO_SPRITE_FOLDER.get(unit_name)
    if not folder_name:
        return None
    
    # 构建相对路径文件名
    filename = f"{animation_state}_{frame}.png"
    
    # 尝试多个可能的根目录
    possible_roots = [
        # 1. 当前工作目录
        ".",
        # 2. 相对于 main.py (假设 sprites.py 在 game/ 下，main.py 在上一级)
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    
    filepath = None
    for root in possible_roots:
        candidate = os.path.join(root, "assets", "sprites", folder_name, filename)
        if os.path.exists(candidate):
            filepath = candidate
            break
    
    if not filepath:
        # print(f"[DEBUG] Sprite not found in any path: assets/sprites/{folder_name}/{filename}")
        return None
    
    try:
        image = pg.image.load(filepath).convert_alpha()
        return image
    except Exception as e:
        print(f"[DEBUG] Failed to load sprite {filepath}: {e}")
        return None


def get_sprite_frames(unit_name: str, animation_state: str) -> List[pg.Surface]:
    """
    获取指定兵种和动画状态的所有帧
    
    Args:
        unit_name: 兵种名称（中文）
        animation_state: 动画状态
    
    Returns:
        所有可用帧的列表
    """
    frames = []
    frame_idx = 0
    while True:
        img = load_sprite_image(unit_name, animation_state, frame_idx)
        if img is None:
            break
        frames.append(img)
        frame_idx += 1
    return frames


def get_sprite_frame_count(unit_name: str, animation_state: str) -> int:
    """
    获取指定兵种和动画状态的帧数
    
    Args:
        unit_name: 兵种名称（中文）
        animation_state: 动画状态
    
    Returns:
        帧数
    """
    count = 0
    while load_sprite_image(unit_name, animation_state, count) is not None:
        count += 1
    return count


def get_current_sprite_frame(
    unit_name: str,
    animation_state: str,
    animation_timer: float,
    fps: float = 8.0,
) -> Optional[pg.Surface]:
    """
    根据动画计时器获取当前应该显示的精灵图帧
    
    Args:
        unit_name: 兵种名称（中文）
        animation_state: 动画状态
        animation_timer: 动画计时器（累计时间）
        fps: 动画播放速度（每秒帧数）
    
    Returns:
        当前帧的 Surface，如果不存在则返回 None
    """
    frame_count = get_sprite_frame_count(unit_name, animation_state)
    if frame_count == 0:
        return None
    
    # 根据计时器计算当前帧索引（循环播放）
    frame_index = int(animation_timer * fps) % frame_count
    
    return load_sprite_image(unit_name, animation_state, frame_index)

