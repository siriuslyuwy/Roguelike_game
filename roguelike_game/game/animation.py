from __future__ import annotations

from enum import Enum
from typing import Optional


class AnimationState(Enum):
    """动画状态枚举"""
    IDLE = "idle"      # 待机
    WALK = "walk"      # 走路
    ATTACK = "attack"  # 攻击


def get_animation_state(unit) -> str:
    """根据单位状态判断动画状态"""
    if not unit.alive:
        return "idle"
    
    # 判断是否在攻击（冷却中且冷却时间较短表示刚攻击完）
    attack_animation_duration = getattr(unit, 'attack_animation_duration', 0.3)
    is_attacking = (unit.cooldown_timer > 0 and 
                   unit.cooldown_timer < attack_animation_duration)
    
    if is_attacking:
        return "attack"
    
    # 判断是否在移动
    is_moving = getattr(unit, 'is_moving', False)
    if is_moving:
        return "walk"
    
    return "idle"

