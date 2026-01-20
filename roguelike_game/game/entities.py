from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, List, Dict

import math

from .constants import SCREEN_WIDTH, LEFT_MARGIN, RIGHT_MARGIN


Side = str  # "left" | "right"


@dataclass
class UnitType:
    key: str
    name: str
    shape: str
    color: Tuple[int, int, int]
    cost: int
    hp: int
    speed: float
    damage: int
    cooldown: float
    range: float
    is_ranged: bool
    projectile_speed: float
    radius: int
    tags: List[str] = field(default_factory=list)  # 新增标签字段
    is_aoe: bool = False
    aoe_radius: float = 0.0
    is_healer: bool = False
    heal_amount: int = 0
    ignore_stop_when_enemy: bool = False
    prioritize_high_damage: bool = False
    intercept_radius: float = 0.0
    intercept_cooldown: float = 0.0
    is_buffer: bool = False
    buff_move_mult: float = 1.0
    buff_cooldown_mult: float = 1.0
    aura_radius: float = 0.0
    is_charger: bool = False
    knockback_factor: float = 0.0
    # 击退附带伤害倍率：仅在“本次攻击触发击退”时，对该次攻击命中的目标额外附加伤害
    # 例如 1.2 表示在正常伤害之外，再追加 0.2×damage 的“击退伤害”
    knockback_damage_mult: float = 1.0
    bonus_vs_charge_mult: float = 1.0
    charge_interrupt_stun: float = 0.0
    split_on_death: bool = False
    split_child_key: str | None = None
    split_children_count: int = 0
    projectile_slow_stack: int = 0
    projectile_slow_duration: float = 0.0
    frost_stun_cap: int = 0
    frost_stun_duration: float = 0.0
    # 行为扩展
    target_ranged_support_only: bool = False  # 只对远程/辅助类目标出手
    reflect_chance: float = 0.0               # 拦截时反弹几率（0~1）
    reflect_damage_ratio: float = 0.0         # 反弹伤害倍率（相对原弹）
    death_explode_radius: float = 0.0         # 死亡爆炸半径（>0 启用）
    death_explode_damage: int = 0             # 死亡爆炸伤害
    melee_stun_duration: float = 0.0          # 近战命中施加的眩晕时长（>0 启用）
    ranged_taken_mult: float = 1.0            # 受到远程来源的伤害倍率（投射物）
    invulnerable: bool = False                # 无敌：免疫一切伤害
    reflect_all_damage: bool = False          # 反弹：将受到的伤害反弹给攻击者
    lifesteal_ratio: float = 0.0              # 吸血：造成伤害按比例回复自身
    projectile_pierce: int = 0                # 自带穿透段数
    projectile_falloff: float = 0.0           # 自带穿透伤害衰减（0~1）
    ignite_radius: float = 0.0                # 点燃道路半径
    ignite_duration: float = 0.0              # 点燃持续时间
    ignite_dps: float = 0.0                   # 点燃每秒伤害
    ignite_on_attack: bool = False            # 点燃是否在攻击命中触发
    is_stealthed: bool = False                # 隐身：不会被锁定
    control_immune: bool = False              # 控制免疫
    first_hit_invuln_duration: float = 0.0    # 满级：首次受伤后无敌秒数
    passive_reflect_ratio: float = 0.0        # 满级：被伤害时反弹比例
    aoe_stun_radius: float = 0.0              # 满级：近战眩晕AOE半径
    heal_aoe_radius: float = 0.0              # 满级：治疗AOE半径
    reflect_heal_ratio: float = 0.0           # 满级：反弹成功回血比例
    aura_shield_ratio: float = 0.0            # 满级：光环护盾比例
    aura_shield_interval: float = 0.0         # 满级：光环护盾间隔
    aura_shield_duration: float = 0.0         # 满级：光环护盾持续
    stealth_in_own_half: bool = False         # 满级：己方半场隐身
    knockback_stun_threshold: int = 0         # 满级：击退触发阈值
    knockback_stun_duration: float = 0.0      # 满级：击退触发眩晕时长
    projectile_stun_aoe_radius: float = 0.0   # 满级：投射物眩晕AOE半径
    charge_rearm_time: float = 0.0            # 满级：冲锋再充能时间
    attack_animation_duration: float = 0.3    # 攻击动画持续时间（默认0.3s）
    suicide_on_attack: bool = False           # 是否攻击即自爆（攻击命中时直接死亡触发爆炸）


@dataclass
class Particle:
    x: float
    y: float
    radius: float
    timer: float
    duration: float
    color: Tuple[int, int, int]
    max_radius: float
    vx: float = 0.0
    vy: float = 0.0
    shape: str = "circle"  # "circle" | "line" | "ring" | "square"
    width: int = 0 # for ring or line width


@dataclass
class Projectile:
    x: float
    y: int
    speed: float
    damage: int
    lane: int
    side: Side
    aoe_radius: float = 0.0
    slow_stack: int = 0
    slow_duration: float = 0.0
    frost_stun_cap: int = 0
    frost_stun_duration: float = 0.0
    pierce: int = 0
    damage_falloff: float = 0.0
    active: bool = True
    owner: "Unit | None" = None
    visual_type: str = "default"  # "arrow" | "orb" | "bullet"
    trail_timer: float = 0.0

    def update(self, dt: float):
        if self.side == "left":
            self.x += self.speed * dt
        else:
            self.x -= self.speed * dt

        if self.x < 0 or self.x > SCREEN_WIDTH:
            self.active = False


@dataclass
class SkillMissile:
    side: Side
    lane: int
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    speed: float
    delay: float = 0.0
    arc_height: float = 50.0
    aoe_radius: float = 80.0
    state: str = "waiting"
    x: float = 0.0
    y: float = 0.0
    explosion_timer: float = 0.0
    explosion_duration: float = 0.24

    def __post_init__(self):
        self.x = self.start_x
        self.y = self.start_y

    def update(self, dt: float) -> bool:
        just_exploded = False
        if self.state == "done":
            return just_exploded

        if self.state == "waiting":
            self.delay -= dt
            if self.delay <= 0.0:
                self.state = "travel"
                if self.delay < 0.0:
                    excess = -self.delay
                    self.delay = 0.0
                    return self.update(excess)
            return just_exploded

        if self.state == "travel":
            direction = 1.0 if self.side == "left" else -1.0
            self.x += direction * self.speed * dt
            total_distance = abs(self.target_x - self.start_x)
            travelled = abs(self.x - self.start_x)
            progress = 0.0 if total_distance <= 0.0 else min(1.0, travelled / total_distance)
            eased = math.sin(progress * math.pi)
            self.y = self.start_y - eased * self.arc_height + (self.target_y - self.start_y) * progress
            if progress >= 1.0:
                self.x = self.target_x
                self.y = self.target_y
                self.state = "explode"
                self.explosion_timer = self.explosion_duration
                just_exploded = True
        elif self.state == "explode":
            self.explosion_timer -= dt
            if self.explosion_timer <= 0.0:
                self.state = "done"

        return just_exploded

    def is_finished(self) -> bool:
        return self.state == "done"


@dataclass
class Unit:
    unit_type: UnitType
    side: Side
    lane: int
    x: float
    y: int
    hp: float
    max_hp: float = 0.0
    cooldown_timer: float = 0.0
    frozen_timer: float = 0.0
    intercept_timer: float = 0.0
    stunned_timer: float = 0.0
    slow_stacks: int = 0
    slow_decay_timer: float = 0.0
    was_stunned_by_frost: bool = False
    temp_speed_multiplier: float = 1.0
    temp_cooldown_multiplier: float = 1.0
    temp_damage_multiplier: float = 1.0
    shield_hp: float = 0.0
    shield_timer: float = 0.0
    rooted_timer: float = 0.0
    alive: bool = True
    first_charge_done: bool = False
    ui_highlights: set[str] = field(default_factory=set)
    invuln_timer: float = 0.0
    max_level_first_hit_invuln_used: bool = False
    knockback_track: Dict[int, int] = field(default_factory=dict)
    shield_pulse_timer: float = 0.0
    time_since_last_attack: float = 0.0
    is_stealthed_dynamic: bool = False
    # 动画相关字段
    animation_state: str = "idle"  # "idle" | "walk" | "attack"
    animation_timer: float = 0.0
    last_x: float = 0.0  # 用于判断是否在移动
    attack_animation_duration: float = 0.3  # 攻击动画持续时间

    def __post_init__(self):
        if self.max_hp <= 0.0:
            self.max_hp = self.hp
        if self.shield_pulse_timer <= 0.0:
            self.shield_pulse_timer = max(0.0, self.unit_type.aura_shield_interval)

    def update_position(self, dt: float):
        if self.frozen_timer > 0 or self.stunned_timer > 0 or self.rooted_timer > 0:
            return
        direction = 1.0 if self.side == "left" else -1.0
        slow_mult = max(0.2, 1.0 - 0.1 * self.slow_stacks)
        speed = self.unit_type.speed * self.temp_speed_multiplier * slow_mult
        self.x += direction * speed * dt

    def in_melee(self, enemy: "Unit") -> bool:
        return abs(self.x - enemy.x) <= self.unit_type.range

    def can_attack(self) -> bool:
        return (
            self.cooldown_timer <= 0.0
            and self.frozen_timer <= 0.0
            and self.stunned_timer <= 0.0
        )

    def tick_cooldown(self, dt: float):
        if self.unit_type.control_immune:
            self.frozen_timer = 0.0
            self.stunned_timer = 0.0
            self.rooted_timer = 0.0
            self.slow_stacks = 0
            self.slow_decay_timer = 0.0
        if self.cooldown_timer > 0.0:
            self.cooldown_timer -= dt
        if self.frozen_timer > 0.0:
            self.frozen_timer -= dt
        if self.stunned_timer > 0.0:
            self.stunned_timer -= dt
        if self.slow_decay_timer > 0.0:
            self.slow_decay_timer -= dt
            if self.slow_decay_timer <= 0.0 and self.slow_stacks > 0:
                self.slow_stacks -= 1
        if self.shield_timer > 0.0:
            self.shield_timer -= dt
        if self.rooted_timer > 0.0:
            self.rooted_timer -= dt
            if self.rooted_timer < 0.0:
                self.rooted_timer = 0.0
        if self.invuln_timer > 0.0:
            self.invuln_timer = max(0.0, self.invuln_timer - dt)
        self.time_since_last_attack += dt
        if self.unit_type.is_charger and self.unit_type.charge_rearm_time > 0.0:
            if self.first_charge_done and self.time_since_last_attack >= self.unit_type.charge_rearm_time:
                self.first_charge_done = False

    def take_damage(self, dmg: float) -> float:
        if dmg <= 0.0 or not self.alive:
            return 0.0
        remaining = dmg
        if self.shield_timer > 0.0 and self.shield_hp > 0.0:
            absorb = min(self.shield_hp, remaining)
            self.shield_hp -= absorb
            remaining -= absorb
        if remaining <= 0.0:
            return 0.0
        self.hp -= remaining
        if self.hp <= 0:
            self.alive = False
        return remaining

    def heal(self, amount: float):
        if amount <= 0.0 or not self.alive:
            return
        max_hp = self.max_hp if self.max_hp > 0.0 else float(self.unit_type.hp)
        self.hp = min(max_hp, self.hp + amount)


@dataclass
class Base:
    side: Side
    hp: float
    x: int
    width: int
    height: int

    @property
    def rect(self):
        # 返回 (left, top, right, bottom) 绘制时由 UI 使用
        left = self.x - self.width // 2
        right = self.x + self.width // 2
        top = 0
        bottom = self.height
        return left, top, right, bottom


