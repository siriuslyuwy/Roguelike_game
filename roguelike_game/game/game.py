from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Tuple

from .constants import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    LANE_COUNT,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    lane_y_positions,
    BASE_MAX_HP,
    BASES_TO_WIN,
    STARTING_RESOURCE,
    RESOURCE_PER_SEC,
    MAX_RESOURCE,
    UnitArchetypes,
    BOONS,
    SKILLS,
)
from .entities import UnitType, Unit, Projectile, Base, SkillMissile, Particle


@dataclass
class LaneHazard:
    lane: int
    side: str
    x: float
    radius: float
    duration: float
    dps: float
    max_duration: float = field(init=False)

    def tick(self, dt: float) -> None:
        self.duration -= dt

    def is_active(self) -> bool:
        return self.duration > 0.0

    def __post_init__(self):
        self.max_duration = max(self.duration, 0.0001)


def _mk_unit_type(key: str, cfg: dict) -> UnitType:
    return UnitType(
        key=key,
        name=cfg["name"],
        tags=cfg.get("tags", []),
        shape=cfg["shape"],
        color=cfg["color"],
        cost=cfg["cost"],
        hp=cfg["hp"],
        speed=cfg["speed"],
        damage=cfg["damage"],
        cooldown=cfg["cooldown"],
        range=cfg["range"],
        is_ranged=cfg["is_ranged"],
        projectile_speed=cfg["projectile_speed"],
        radius=cfg["radius"],
        is_aoe=cfg.get("is_aoe", False),
        aoe_radius=cfg.get("aoe_radius", 0.0),
        is_healer=cfg.get("is_healer", False),
        heal_amount=cfg.get("heal_amount", 0),
        ignore_stop_when_enemy=cfg.get("ignore_stop_when_enemy", False),
        prioritize_high_damage=cfg.get("prioritize_high_damage", False),
        intercept_radius=cfg.get("intercept_radius", 0.0),
        intercept_cooldown=cfg.get("intercept_cooldown", 0.0),
        is_buffer=cfg.get("is_buffer", False),
        buff_move_mult=cfg.get("buff_move_mult", 1.0),
        buff_cooldown_mult=cfg.get("buff_cooldown_mult", 1.0),
        aura_radius=cfg.get("aura_radius", 0.0),
        is_charger=cfg.get("is_charger", False),
        knockback_factor=cfg.get("knockback_factor", 0.0),
        knockback_damage_mult=cfg.get("knockback_damage_mult", 1.0),
        bonus_vs_charge_mult=cfg.get("bonus_vs_charge_mult", 1.0),
        charge_interrupt_stun=cfg.get("charge_interrupt_stun", 0.0),
        split_on_death=cfg.get("split_on_death", False),
        split_child_key=cfg.get("split_child_key"),
        split_children_count=cfg.get("split_children_count", 0),
        projectile_slow_stack=cfg.get("projectile_slow_stack", 0),
        projectile_slow_duration=cfg.get("projectile_slow_duration", 0.0),
        frost_stun_cap=cfg.get("frost_stun_cap", 0),
        frost_stun_duration=cfg.get("frost_stun_duration", 0.0),
        target_ranged_support_only=cfg.get("target_ranged_support_only", False),
        reflect_chance=cfg.get("reflect_chance", 0.0),
        reflect_damage_ratio=cfg.get("reflect_damage_ratio", 0.0),
        death_explode_radius=cfg.get("death_explode_radius", 0.0),
        death_explode_damage=cfg.get("death_explode_damage", 0),
        melee_stun_duration=cfg.get("melee_stun_duration", 0.0),
        ranged_taken_mult=cfg.get("ranged_taken_mult", 1.0),
        invulnerable=cfg.get("invulnerable", False),
        reflect_all_damage=cfg.get("reflect_all_damage", False),
        lifesteal_ratio=cfg.get("lifesteal_ratio", 0.0),
        projectile_pierce=cfg.get("projectile_pierce", 0),
        projectile_falloff=cfg.get("projectile_falloff", 0.0),
        ignite_radius=cfg.get("ignite_radius", 0.0),
        ignite_duration=cfg.get("ignite_duration", 0.0),
        ignite_dps=cfg.get("ignite_dps", 0.0),
        ignite_on_attack=cfg.get("ignite_on_attack", False),
        is_stealthed=cfg.get("is_stealthed", False),
        control_immune=cfg.get("control_immune", False),
        first_hit_invuln_duration=cfg.get("first_hit_invuln_duration", 0.0),
        passive_reflect_ratio=cfg.get("passive_reflect_ratio", 0.0),
        aoe_stun_radius=cfg.get("aoe_stun_radius", 0.0),
        heal_aoe_radius=cfg.get("heal_aoe_radius", 0.0),
        reflect_heal_ratio=cfg.get("reflect_heal_ratio", 0.0),
        aura_shield_ratio=cfg.get("aura_shield_ratio", 0.0),
        aura_shield_interval=cfg.get("aura_shield_interval", 0.0),
        aura_shield_duration=cfg.get("aura_shield_duration", 0.0),
        stealth_in_own_half=cfg.get("stealth_in_own_half", False),
        knockback_stun_threshold=cfg.get("knockback_stun_threshold", 0),
        knockback_stun_duration=cfg.get("knockback_stun_duration", 0.0),
        projectile_stun_aoe_radius=cfg.get("projectile_stun_aoe_radius", 0.0),
        charge_rearm_time=cfg.get("charge_rearm_time", 0.0),
        attack_animation_duration=cfg.get("attack_animation_duration", 0.3),
        suicide_on_attack=cfg.get("suicide_on_attack", False),
    )


UNIT_TYPES: Dict[str, UnitType] = {
    "Q": _mk_unit_type("Q", UnitArchetypes.CIRCLE),
    "W": _mk_unit_type("W", UnitArchetypes.SQUARE),
    "E": _mk_unit_type("E", UnitArchetypes.TRIANGLE),
    "R": _mk_unit_type("R", UnitArchetypes.HEXAGON),
    "A": _mk_unit_type("A", UnitArchetypes.PENTAGON),
    "S": _mk_unit_type("S", UnitArchetypes.DIAMOND),
    "D": _mk_unit_type("D", UnitArchetypes.STAR),
    "F": _mk_unit_type("F", UnitArchetypes.RHINO),
    "G": _mk_unit_type("G", UnitArchetypes.ASSASSIN),
    "H": _mk_unit_type("H", UnitArchetypes.INTERCEPTOR),
    "J": _mk_unit_type("J", UnitArchetypes.DRUMMER),
    "K": _mk_unit_type("K", UnitArchetypes.SPEARMAN),
    "L": _mk_unit_type("L", UnitArchetypes.FROST_ARCHER),
    "M": _mk_unit_type("M", UnitArchetypes.SPLITTER),
    "O": _mk_unit_type("O", UnitArchetypes.SPLITLING),
    "N": _mk_unit_type("N", UnitArchetypes.LIGHT_CAV),
}

ORDER_KEYS = ["Q", "W", "E", "R", "A", "S", "D", "F", "G", "H", "J", "K", "L", "M", "N"]

UNIT_LEVEL_STEP = 0.03
MAX_UNIT_LEVEL = 4

BLIND_FACE_RANGE = 32.0


@dataclass
class PlayerState:
    resource: float = STARTING_RESOURCE
    spawn_cooldowns: Dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in UNIT_TYPES.keys()})


class Game:
    AI_MIN_RESOURCE_THRESHOLD = 110

    def __init__(
        self,
        player_keys: List[str] | None = None,
        player_skills: List[str] | None = None,
        ai_keys: List[str] | None = None,
        ai_skills: List[str] | None = None,
        ai_interval_mult: float = 1.0,
        boons: Dict[str, int] | None = None,
        left_base_hps: List[float] | None = None,
        right_base_hps: List[float] | None = None,
        modifiers: Dict[str, Any] | None = None,
        player_unit_levels: Dict[str, int] | None = None,
        left_forge: Dict[str, Tuple[int, int]] | None = None,
        left_forge_substat_mult: float = 1.0,
        ai_unit_levels: Dict[str, int] | None = None,
        right_forge: Dict[str, Tuple[int, int]] | None = None,
        right_forge_substat_mult: float = 1.0,
    ):
        self.modifiers: Dict[str, Any] = modifiers or {}
        self.left_base_hp_mult: float = max(0.0, float(self.modifiers.get("left_base_hp_mult", 1.0)))
        self.right_base_hp_mult: float = max(
            0.0, float(self.modifiers.get("right_base_hp_mult", self.modifiers.get("right_hp_mult", 1.0)))
        )
        self.right_hp_mult: float = max(0.0, float(self.modifiers.get("right_hp_mult", 1.0)))
        self.mirror_apply_right: bool = bool(self.modifiers.get("mirror_apply_right", False))

        self.lane_y = lane_y_positions()
        left_x = LEFT_MARGIN // 2 + 10
        right_x = SCREEN_WIDTH - (RIGHT_MARGIN // 2 + 10)

        # === 7条战线特色（对称生效）===
        # lane index 0..6 对应显示 1..7
        # - 1/7（0/6）侧翼：速度 +30%
        # - 2/6（1/5）持久：HP +25%，速度 -10%
        # - 3/5（2/4）爆发：对单位伤害倍率（近战 +25%，远程 +15%）；不影响撞基地结算
        # - 4（3）中线：原汁原味
        self.lane_group: List[str] = ["mid" for _ in range(LANE_COUNT)]
        if LANE_COUNT >= 7:
            self.lane_group[0] = "flank"
            self.lane_group[6] = "flank"
            self.lane_group[1] = "tank"
            self.lane_group[5] = "tank"
            self.lane_group[2] = "burst"
            self.lane_group[4] = "burst"
            self.lane_group[3] = "mid"

        self.lane_speed_mult: List[float] = [1.0 for _ in range(LANE_COUNT)]
        self.lane_hp_mult: List[float] = [1.0 for _ in range(LANE_COUNT)]
        self.lane_burst_melee_vs_unit_mult: List[float] = [1.0 for _ in range(LANE_COUNT)]
        self.lane_burst_ranged_vs_unit_mult: List[float] = [1.0 for _ in range(LANE_COUNT)]
        for i, g in enumerate(self.lane_group):
            if g == "flank":
                self.lane_speed_mult[i] = 1.30
            elif g == "tank":
                self.lane_speed_mult[i] = 0.90
                self.lane_hp_mult[i] = 1.25
            elif g == "burst":
                self.lane_burst_melee_vs_unit_mult[i] = 1.25
                self.lane_burst_ranged_vs_unit_mult[i] = 1.15
        
        # === 先初始化Combo变量，再使用它们 ===
        # 基础全局加成
        self.combo_kill_resource_bonus: float = float(self.modifiers.get("combo_kill_resource_bonus", 0.0))
        self.combo_base_hp_bonus: float = float(self.modifiers.get("combo_base_hp_bonus", 0.0))
        # 镜像侧Combo（仅右侧镜像使用）
        self.mirror_combo_kill_resource_bonus: float = float(self.modifiers.get("mirror_combo_kill_resource_bonus", 0.0))
        self.mirror_combo_base_hp_bonus: float = float(self.modifiers.get("mirror_combo_base_hp_bonus", 0.0))
        
        # Combo: 紧急加固 - 基地HP+50%
        left_base_bonus = float(self._combo_value("left", "combo_base_hp_bonus", 0.0) or 0.0)
        right_base_bonus = float(self._combo_value("right", "combo_base_hp_bonus", 0.0) or 0.0)
        base_hp_final_mult = self.left_base_hp_mult * (1.0 + left_base_bonus)
        right_base_final_mult = self.right_base_hp_mult * (1.0 + right_base_bonus)
        self.left_bases = [Base("left", BASE_MAX_HP * base_hp_final_mult, left_x, 16, 48) for _ in range(LANE_COUNT)]
        self.right_bases = [
            Base("right", BASE_MAX_HP * right_base_final_mult, right_x, 16, 48) for _ in range(LANE_COUNT)
        ]
        # 继承基地HP（若提供）
        if left_base_hps is not None:
            for i in range(min(LANE_COUNT, len(left_base_hps))):
                self.left_bases[i].hp = max(0.0, float(left_base_hps[i]))
        if right_base_hps is not None:
            for i in range(min(LANE_COUNT, len(right_base_hps))):
                self.right_bases[i].hp = max(0.0, float(right_base_hps[i]))

        # 每条战线的单位	records: List[Tuple[List[Unit], List[Unit]]]
        self.left_units: List[List[Unit]] = [[] for _ in range(LANE_COUNT)]
        self.right_units: List[List[Unit]] = [[] for _ in range(LANE_COUNT)]
        self.projectiles: List[Projectile] = []
        self.skill_missiles: List[SkillMissile] = []
        self.lane_hazards: List[LaneHazard] = []
        self.particles: List[Particle] = []

        self.left_infinite_resource: bool = bool(self.modifiers.get("left_infinite_resource", False))
        self.left_infinite_skill: bool = bool(self.modifiers.get("left_infinite_skill", False))
        self.bases_invulnerable: bool = bool(self.modifiers.get("bases_invulnerable", False))
        self.right_resource_mult: float = float(self.modifiers.get("right_resource_mult", 1.0))
        # 注意：right_resource_mult 仅影响“每秒回资源”，不再影响开局资源（避免把难度曲线耦合到开局爆发）
        self.right_start_resource_mult: float = float(self.modifiers.get("right_start_resource_mult", 1.0))
        self.right_res_cap: float = float(self.modifiers.get("right_res_cap", MAX_RESOURCE))
        self.ai_extra_spawn: int = int(self.modifiers.get("ai_extra_spawn", 0))
        self.ai_varied_units: bool = bool(self.modifiers.get("ai_varied_units", False))
        self.left_damage_mult: float = max(0.0, float(self.modifiers.get("left_damage_mult", 1.0)))
        self.right_damage_mult: float = max(0.0, float(self.modifiers.get("right_damage_mult", 1.0)))
        self.left_resource_rate_mult: float = float(self.modifiers.get("left_resource_rate_mult", 1.0))
        
        self.battle_time: float = 0.0  # 追踪战斗时长
        
        # 老兵祝福：英雄祭献（非Q单位属性加成）
        self.veteran_sacrifice_damage_mult: float = float(self.modifiers.get("veteran_sacrifice_damage_mult", 1.0))
        self.veteran_sacrifice_hp_mult: float = float(self.modifiers.get("veteran_sacrifice_hp_mult", 1.0))
        self.veteran_sacrifice_day_limit: int = int(self.modifiers.get("veteran_sacrifice_day_limit", 999))
        self.right_veteran_sacrifice_damage_mult: float = float(self.modifiers.get("right_veteran_sacrifice_damage_mult", 1.0))
        self.right_veteran_sacrifice_hp_mult: float = float(self.modifiers.get("right_veteran_sacrifice_hp_mult", 1.0))
        self.right_veteran_sacrifice_day_limit: int = int(self.modifiers.get("right_veteran_sacrifice_day_limit", 999))
        
        # 老兵祝福：教官光环
        self.veteran_mentor_q_hp_mult: float = float(self.modifiers.get("veteran_q_hp_mult", 1.0))
        self.veteran_mentor_q_damage_mult: float = float(self.modifiers.get("veteran_q_damage_mult", 1.0))
        self.veteran_mentor_atkspd_bonus: float = float(self.modifiers.get("veteran_mentor_atkspd_bonus", 0.0))
        self.veteran_mentor_damage_bonus: float = float(self.modifiers.get("veteran_mentor_damage_bonus", 0.0))
        self.right_veteran_mentor_q_hp_mult: float = float(self.modifiers.get("right_veteran_q_hp_mult", 1.0))
        self.right_veteran_mentor_q_damage_mult: float = float(self.modifiers.get("right_veteran_q_damage_mult", 1.0))
        self.right_veteran_mentor_atkspd_bonus: float = float(self.modifiers.get("right_veteran_mentor_atkspd_bonus", 0.0))
        self.right_veteran_mentor_damage_bonus: float = float(self.modifiers.get("right_veteran_mentor_damage_bonus", 0.0))
        
        # 老兵祝福：破釜沉舟
        self.veteran_q_free_cost: bool = bool(self.modifiers.get("veteran_q_free_cost", False))
        self.veteran_q_base_damage: int = int(self.modifiers.get("veteran_q_base_damage", 0))
        self.right_veteran_q_free_cost: bool = bool(self.modifiers.get("right_veteran_q_free_cost", False))
        self.right_veteran_q_base_damage: int = int(self.modifiers.get("right_veteran_q_base_damage", 0))
        
        # 战役天数（用于英雄祭献的day>=5判定）
        self.campaign_day: int = int(self.modifiers.get("campaign_day", 1))
        
        # 祝福：钢铁洪流
        self.left_cost_mult: float = float(self.modifiers.get("left_cost_mult", 1.0))
        self.left_cooldown_mult: float = float(self.modifiers.get("left_cooldown_mult", 1.0))
        self.right_cost_mult: float = float(self.modifiers.get("right_cost_mult", 1.0))
        self.right_cooldown_mult: float = float(self.modifiers.get("right_cooldown_mult", 1.0))
        
        # 祝福：掠夺者逻辑
        self.looter_gold_per_kill: float = 2.0  # 每击杀一个单位获得的金币
        self.looter_battle_gold_gained: float = 0.0  # 本场战斗通过击杀获得的金币
        self.looter_battle_gold_cap: float = 0.0  # 本场战斗击杀金币上限（将在战斗开始时设置）
        
        # 祝福：战术大师（技能消耗资源而非击杀数）
        self.tactical_master_mode: bool = bool(self.modifiers.get("tactical_master_mode", False))
        self._has_left_resource_amount_override: bool = "left_resource_amount" in self.modifiers
        self.left_resource_amount: float = float(
            self.modifiers.get("left_resource_amount", 999999 if self.left_infinite_resource else STARTING_RESOURCE)
        )
        
        # === Combo 系统变量（剩余部分） ===
        # 基础职能加成
        self.combo_tank_hp_bonus: float = float(self.modifiers.get("combo_tank_hp_bonus", 0.0))
        self.combo_dps_damage_bonus: float = float(self.modifiers.get("combo_dps_damage_bonus", 0.0))
        self.combo_support_heal_bonus: float = float(self.modifiers.get("combo_support_heal_bonus", 0.0))
        self.combo_control_duration_bonus: float = float(self.modifiers.get("combo_control_duration_bonus", 0.0))
        self.mirror_combo_tank_hp_bonus: float = float(self.modifiers.get("mirror_combo_tank_hp_bonus", 0.0))
        self.mirror_combo_dps_damage_bonus: float = float(self.modifiers.get("mirror_combo_dps_damage_bonus", 0.0))
        self.mirror_combo_support_heal_bonus: float = float(self.modifiers.get("mirror_combo_support_heal_bonus", 0.0))
        self.mirror_combo_control_duration_bonus: float = float(self.modifiers.get("mirror_combo_control_duration_bonus", 0.0))
        
        # 基础特性加成
        self.combo_aoe_radius_bonus: float = float(self.modifiers.get("combo_aoe_radius_bonus", 0.0))
        self.combo_melee_speed_bonus: float = float(self.modifiers.get("combo_melee_speed_bonus", 0.0))
        self.combo_ranged_atkspd_bonus: float = float(self.modifiers.get("combo_ranged_atkspd_bonus", 0.0))
        self.combo_ranged_range_bonus: float = float(self.modifiers.get("combo_ranged_range_bonus", 0.0))
        self.mirror_combo_aoe_radius_bonus: float = float(self.modifiers.get("mirror_combo_aoe_radius_bonus", 0.0))
        self.mirror_combo_melee_speed_bonus: float = float(self.modifiers.get("mirror_combo_melee_speed_bonus", 0.0))
        self.mirror_combo_ranged_atkspd_bonus: float = float(self.modifiers.get("mirror_combo_ranged_atkspd_bonus", 0.0))
        self.mirror_combo_ranged_range_bonus: float = float(self.modifiers.get("mirror_combo_ranged_range_bonus", 0.0))
        
        # 联动型Combo标记
        self.combo_firm_line: bool = bool(self.modifiers.get("combo_firm_line", False))
        self.combo_combined_arms: bool = bool(self.modifiers.get("combo_combined_arms", False))
        self.combo_dead_recruit: bool = bool(self.modifiers.get("combo_dead_recruit", False))
        self.combo_ice_shatter: bool = bool(self.modifiers.get("combo_ice_shatter", False))
        self.combo_counter_stance: bool = bool(self.modifiers.get("combo_counter_stance", False))
        self.combo_aura_resonance: bool = bool(self.modifiers.get("combo_aura_resonance", False))
        self.combo_overflow_shield: bool = bool(self.modifiers.get("combo_overflow_shield", False))
        self.combo_shock_armor: bool = bool(self.modifiers.get("combo_shock_armor", False))
        self.combo_emergency_protocol: bool = bool(self.modifiers.get("combo_emergency_protocol", False))
        self.combo_full_suppression: bool = bool(self.modifiers.get("combo_full_suppression", False))
        self.mirror_combo_firm_line: bool = bool(self.modifiers.get("mirror_combo_firm_line", False))
        self.mirror_combo_combined_arms: bool = bool(self.modifiers.get("mirror_combo_combined_arms", False))
        self.mirror_combo_dead_recruit: bool = bool(self.modifiers.get("mirror_combo_dead_recruit", False))
        self.mirror_combo_ice_shatter: bool = bool(self.modifiers.get("mirror_combo_ice_shatter", False))
        self.mirror_combo_counter_stance: bool = bool(self.modifiers.get("mirror_combo_counter_stance", False))
        self.mirror_combo_aura_resonance: bool = bool(self.modifiers.get("mirror_combo_aura_resonance", False))
        self.mirror_combo_overflow_shield: bool = bool(self.modifiers.get("mirror_combo_overflow_shield", False))
        self.mirror_combo_shock_armor: bool = bool(self.modifiers.get("mirror_combo_shock_armor", False))
        self.mirror_combo_emergency_protocol: bool = bool(self.modifiers.get("mirror_combo_emergency_protocol", False))
        self.mirror_combo_full_suppression: bool = bool(self.modifiers.get("mirror_combo_full_suppression", False))
        self.combo_spawn_cd_mult: float = float(self.modifiers.get("combo_spawn_cd_mult", 1.0))
        self.mirror_combo_spawn_cd_mult: float = float(self.modifiers.get("mirror_combo_spawn_cd_mult", 1.0))
        
        # 死士招募：追踪dps单位死亡数
        self.combo_dps_death_count: int = 0
        self.combo_next_spawn_free: bool = False
        
        # 应急协议：追踪已触发的基地（防止重复）
        self.combo_emergency_triggered_lanes: set[int] = set()

        self.left = PlayerState()
        self.right = PlayerState()

        if self.left_infinite_resource or self._has_left_resource_amount_override:
            self.left.resource = self.left_resource_amount
        # 开局资源倍率（可选）：用于测试/自由模式等；战役难度曲线应通过 right_resource_mult 控制回资源
        if self.right_start_resource_mult != 1.0:
            self.right.resource *= self.right_start_resource_mult
        self.right.resource = min(self.right_res_cap, self.right.resource)

        # 开局资源同步：双方均以基础 STARTING_RESOURCE (100) 开始
        # 抹除 AI 之前的 +50 优势，以降低第 1 关的非平衡性暴死率
        self.right.resource = min(self.right_res_cap, self.right.resource)

        # 配阵：玩家可用兵种与技能；AI 随机选择
        import random as _random
        self.player_order_keys: List[str] = player_keys if player_keys else ORDER_KEYS[:5]
        self.left_unit_levels: Dict[str, int] = {}
        if player_unit_levels:
            for key, lvl in player_unit_levels.items():
                if key in ORDER_KEYS:
                    self.left_unit_levels[key] = max(1, min(MAX_UNIT_LEVEL, int(lvl)))
        for key in self.player_order_keys:
            if key not in self.left_unit_levels:
                self.left_unit_levels[key] = 1
        self.player_unit_levels = self.left_unit_levels
        self.right_unit_levels: Dict[str, int] = {}
        if ai_unit_levels:
            for key, lvl in ai_unit_levels.items():
                if key in ORDER_KEYS:
                    self.right_unit_levels[key] = max(1, min(MAX_UNIT_LEVEL, int(lvl)))
        self._leveled_unit_cache: Dict[tuple[str, int], UnitType] = {}
        # M3：本场战斗统计（用于战役锻造/俘虏输入）
        self.battle_left_spawn_counts: Dict[str, int] = {}
        self.battle_right_spawn_counts: Dict[str, int] = {}
        self.battle_right_spawned_types: set[str] = set()
        # M3：锻造（只对玩家侧生效）
        self.left_forge: Dict[str, Tuple[str, int]] = left_forge or {}
        self.left_forge_substat_mult: float = max(0.0, float(left_forge_substat_mult))
        self.right_forge: Dict[str, Tuple[str, int]] = right_forge or {}
        self.right_forge_substat_mult: float = max(0.0, float(right_forge_substat_mult))
        if ai_keys:
            self.ai_order_keys = list(ai_keys)
        else:
            self.ai_order_keys = _random.sample(ORDER_KEYS, 5)
        if self.mirror_apply_right:
            for key in self.ai_order_keys:
                if key not in self.right_unit_levels:
                    self.right_unit_levels[key] = 1
        skill_keys = list(SKILLS.keys())
        default_skill = "spawn" if "spawn" in SKILLS else (skill_keys[0] if skill_keys else None)
        self.left_skill_types: List[str] = []
        # 注意：player_skills 传入空列表 [] 表示“明确不带技能”
        if player_skills is not None:
            for key in player_skills:
                if key in SKILLS and key not in self.left_skill_types:
                    self.left_skill_types.append(key)
                if len(self.left_skill_types) >= 3:
                    break
        elif default_skill:
            self.left_skill_types = [default_skill]
        self.right_skill_types: List[str] = []
        if ai_skills:
            for key in ai_skills:
                if key in SKILLS and key not in self.right_skill_types:
                    self.right_skill_types.append(key)
                if len(self.right_skill_types) >= 3:
                    break
        elif skill_keys:
            self.right_skill_types = [_random.choice(skill_keys)]
        self.left_threshold_mult: float = 1.0
        self.right_threshold_mult: float = 1.0
        self.left_skill_costs: Dict[str, int] = {}
        self.right_skill_costs: Dict[str, int] = {}
        self.left_kill_resource: int = 0
        self.right_kill_resource: int = 0

        self.selected_lane: int = 0
        self.selected_unit_idx: int = 0  # index into player_order_keys
        self.winner: str | None = None
        self._ai_timer: float = 0.0
        self.ai_interval_mult: float = ai_interval_mult
        self._ai_lane_last_unit: Dict[int, str] = {}

        # === 镜像Boss脚本 ===
        self.mirror_script: List[dict] = []
        self.mirror_script_idx: int = 0
        self.mirror_script_enabled: bool = False
        self.mirror_script_duration: float = 0.0
        self.mirror_script_cycle_start: float = 0.0
        self.disable_ai: bool = bool(self.modifiers.get("disable_ai", False))
        # 战斗计时器（秒）
        self.battle_time: float = 0.0
        # 胜负条件：允许按 modifiers 覆盖
        self.bases_to_win: int = int(self.modifiers.get("bases_to_win", BASES_TO_WIN))
        self.bases_to_win = max(1, min(self.bases_to_win, LANE_COUNT))

        # 增益卡设置（玩家左侧）
        self.boons: Dict[str, int] = boons or {}
        eco_stack = self.boons.get("boon_eco", 0)
        self.left_econ_mult = 1.0 + eco_stack * BOONS["boon_eco"]["econ_rate"]
        # M4：允许通过 modifiers 叠加经济倍率（Combo/事件等）
        if "left_econ_mult" in self.modifiers:
            self.left_econ_mult *= max(0.0, float(self.modifiers["left_econ_mult"]))
        self.left_res_cap = MAX_RESOURCE + eco_stack * BOONS["boon_eco"]["res_cap"]
        if "left_res_cap" in self.modifiers:
            self.left_res_cap = float(self.modifiers["left_res_cap"])
        if self.left_infinite_resource or self._has_left_resource_amount_override:
            self.left_res_cap = max(self.left_res_cap, self.left_resource_amount)
        hp_stack = self.boons.get("boon_hp", 0)
        self.left_hp_mult = 1.0 + hp_stack * BOONS["boon_hp"]["hp_mult"]
        # M4：允许通过 modifiers 叠加单位生命倍率（Combo等）
        if "left_hp_mult" in self.modifiers:
            self.left_hp_mult *= max(0.0, float(self.modifiers["left_hp_mult"]))
        sp_stack = self.boons.get("boon_speed_charge", 0)
        self.left_speed_mult = 1.0 + sp_stack * BOONS["boon_speed_charge"]["speed_mult"]
        self.left_knockback_bonus = sp_stack * BOONS["boon_speed_charge"]["knockback_bonus"]
        haste_stack = self.boons.get("boon_haste", 0)
        self.left_cd_mult = (BOONS["boon_haste"]["cd_mult"] ** haste_stack) if haste_stack > 0 else 1.0
        self.left_cd_floor = BOONS["boon_haste"]["cd_floor"]
        sh_stack = self.boons.get("boon_spawn_shield", 0)
        self.left_shield_pct = sh_stack * BOONS["boon_spawn_shield"]["shield_pct"]
        self.left_shield_dur = BOONS["boon_spawn_shield"]["shield_duration"] if sh_stack > 0 else 0.0
        # M4：全局单位速度/攻速倍率（Combo等）
        self.left_unit_speed_mult = max(0.0, float(self.modifiers.get("left_unit_speed_mult", 1.0)))
        self.left_unit_atkspd_mult = max(0.0, float(self.modifiers.get("left_unit_atkspd_mult", 1.0)))
        self.right_unit_speed_mult = max(0.0, float(self.modifiers.get("right_unit_speed_mult", 1.0)))
        self.right_unit_atkspd_mult = max(0.0, float(self.modifiers.get("right_unit_atkspd_mult", 1.0)))
        ref_stack = self.boons.get("boon_refund", 0)
        self.left_refund_rate = 0.0
        if ref_stack == 1:
            self.left_refund_rate = BOONS["boon_refund"]["refund_rate_first"]
        elif ref_stack >= 2:
            self.left_refund_rate = BOONS["boon_refund"]["refund_rate_second"]
        self.left_refund_limit = BOONS["boon_refund"]["limit_per_10s"] if ref_stack > 0 else 0
        self._refund_window_timer = 0.0
        self._refund_window_count = 0
        sk_stack = self.boons.get("boon_skill", 0)
        if sk_stack >= 1:
            self.left_threshold_mult *= BOONS["boon_skill"]["threshold_mult_first"]
        if sk_stack >= 2:
            self.left_threshold_mult *= BOONS["boon_skill"]["threshold_mult_next"]
        # M4: Combo 战术优化 (技能消耗-15%)
        if "left_skill_threshold_mult" in self.modifiers:
            self.left_threshold_mult *= float(self.modifiers["left_skill_threshold_mult"])
        fr_stack = self.boons.get("boon_frost", 0)
        self.left_frost_slow_extra = fr_stack * BOONS["boon_frost"]["slow_extra"]
        self.left_frost_stun_extra = fr_stack * BOONS["boon_frost"]["stun_extra"]
        pr_stack = self.boons.get("boon_pierce", 0)
        self.left_pierce_bonus = pr_stack * BOONS["boon_pierce"]["pierce_each"]
        self.left_pierce_falloff = BOONS["boon_pierce"]["falloff"] if pr_stack > 0 else 0.0
        pj_stack = self.boons.get("boon_proj_resist", 0)
        if pj_stack == 1:
            self.left_proj_reduce = BOONS["boon_proj_resist"]["reduction_first"]
        elif pj_stack >= 2:
            self.left_proj_reduce = BOONS["boon_proj_resist"]["reduction_second"]
        else:
            self.left_proj_reduce = 0.0

        self._refresh_skill_costs("left")
        self._refresh_skill_costs("right")

        # 技能状态计时器
        self.left_skill_damage_mult = 1.0
        self.left_skill_damage_timer = 0.0
        self.right_skill_damage_mult = 1.0
        self.right_skill_damage_timer = 0.0
        self.left_skill_speed_mult = 1.0
        self.left_skill_speed_timer = 0.0
        self.right_skill_speed_mult = 1.0
        self.right_skill_speed_timer = 0.0
        self.left_base_invuln_timer = [0.0 for _ in range(LANE_COUNT)]
        self.right_base_invuln_timer = [0.0 for _ in range(LANE_COUNT)]

        # 击杀与技能资源
        if self.left_infinite_skill:
            self.left_kill_resource = max(self.left_kill_resource, 0)

        self.recent_kills: int = 0

    def _refresh_skill_costs(self, side: str):
        if side == "left":
            skills = self.left_skill_types
            mult = self.left_threshold_mult
            store = self.left_skill_costs
        else:
            skills = self.right_skill_types
            mult = self.right_threshold_mult
            store = self.right_skill_costs
        store.clear()
        for key in skills:
            base = SKILLS.get(key, {}).get("cost", 0)
            store[key] = max(1, int(base * mult))

    def _get_skill_entry(self, side: str, slot: int | None) -> tuple[str | None, int]:
        if side == "left":
            skills = self.left_skill_types
            store = self.left_skill_costs
            mult = self.left_threshold_mult
        else:
            skills = self.right_skill_types
            store = self.right_skill_costs
            mult = self.right_threshold_mult
        if not skills:
            return None, 0
        idx = 0 if slot is None else slot
        if idx < 0 or idx >= len(skills):
            return None, 0
        key = skills[idx]
        cost = store.get(key)
        if cost is None:
            base = SKILLS.get(key, {}).get("cost", 0)
            cost = max(1, int(base * mult))
            store[key] = cost
        return key, cost

    def _get_unit_level(self, side: str, key: str) -> int:
        if side == "left":
            return max(1, min(MAX_UNIT_LEVEL, self.left_unit_levels.get(key, 1)))
        if self.mirror_apply_right:
            return max(1, min(MAX_UNIT_LEVEL, self.right_unit_levels.get(key, 1)))
        return 1

    def _combo_value(self, side: str, name: str, default: float | bool = 0.0):
        if side == "left":
            return getattr(self, name, default)
        if self.mirror_apply_right:
            return getattr(self, f"mirror_{name}", default)
        return default

    def _get_unit_type_with_level(self, side: str, key: str) -> UnitType | None:
        base = UNIT_TYPES.get(key)
        if not base:
            return None
        level = self._get_unit_level(side, key)
        # 先应用“兵种等级”加成
        if level <= 1:
            ut = base
        else:
            cache_key = (key, level)
            cached = self._leveled_unit_cache.get(cache_key)
            if cached:
                ut = cached
            else:
                # Lv2/Lv3: 每级+5%；Lv4: 与Lv3相同属性，仅额外解锁特效
                if level == 2:
                    mult = 1.05
                elif level >= 3:
                    mult = 1.10
                cooldown_mult = 1.0 / mult
                new_ut = replace(
                    base,
                    hp=max(1, int(round(base.hp * mult))),
                    damage=max(0, int(round(base.damage * mult))),
                    speed=base.speed * mult,
                    range=base.range * mult,
                    heal_amount=int(round(base.heal_amount * mult)),
                    projectile_speed=base.projectile_speed * mult,
                    cooldown=max(0.05, base.cooldown * cooldown_mult),
                    intercept_cooldown=base.intercept_cooldown * cooldown_mult,
                    aoe_radius=base.aoe_radius * mult,
                    intercept_radius=base.intercept_radius * mult,
                    death_explode_damage=int(round(base.death_explode_damage * mult)),
                    death_explode_radius=base.death_explode_radius * mult,
                    projectile_slow_duration=base.projectile_slow_duration * mult,
                    frost_stun_duration=base.frost_stun_duration * mult,
                    charge_interrupt_stun=base.charge_interrupt_stun * mult,
                    knockback_factor=base.knockback_factor * mult,
                    melee_stun_duration=base.melee_stun_duration * mult,
                )
                if level == MAX_UNIT_LEVEL:
                    self._apply_max_level_traits(key, new_ut)
                self._leveled_unit_cache[cache_key] = new_ut
                ut = new_ut

        # M3：锻造加成（攻防分离；镜像可映射到右侧）
        if side == "left" or (side == "right" and self.mirror_apply_right):
            forge_pool = self.left_forge if side == "left" else self.right_forge
            forge_substat_mult = self.left_forge_substat_mult if side == "left" else self.right_forge_substat_mult
            forge_data = forge_pool.get(key)
            if forge_data:
                offense_level, defense_level = forge_data
                offense_level = max(0, min(5, int(offense_level)))
                defense_level = max(0, min(5, int(defense_level)))
                
                forge_changes = {}
                
                # 攻击等级加成
                if offense_level > 0:
                    if offense_level == 1:
                        dmg_pct = 0.10
                        atkspd_pct = 0.03
                    elif offense_level == 2:
                        dmg_pct = 0.25
                        atkspd_pct = 0.07
                    elif offense_level == 3:
                        dmg_pct = 0.50
                        atkspd_pct = 0.12
                    elif offense_level == 4:
                        dmg_pct = 0.80
                        atkspd_pct = 0.15
                    else:  # 5级
                        dmg_pct = 1.20
                        atkspd_pct = 0.20
                    
                    atkspd_pct *= forge_substat_mult
                    forge_changes["damage"] = max(0, int(round(ut.damage * (1.0 + dmg_pct))))
                    forge_changes["cooldown"] = max(0.05, ut.cooldown / (1.0 + atkspd_pct))
                    if ut.intercept_cooldown > 0:
                        forge_changes["intercept_cooldown"] = max(0.0, ut.intercept_cooldown / (1.0 + atkspd_pct))
                
                # 防御等级加成
                if defense_level > 0:
                    if defense_level == 1:
                        hp_pct = 0.10
                        spd_pct = 0.03
                    elif defense_level == 2:
                        hp_pct = 0.25
                        spd_pct = 0.07
                    elif defense_level == 3:
                        hp_pct = 0.50
                        spd_pct = 0.12
                    elif defense_level == 4:
                        hp_pct = 0.80
                        spd_pct = 0.15
                    else:  # 5级
                        hp_pct = 1.20
                        spd_pct = 0.20
                    
                    spd_pct *= forge_substat_mult
                    forge_changes["hp"] = max(1, int(round(ut.hp * (1.0 + hp_pct))))
                    forge_changes["speed"] = ut.speed * (1.0 + spd_pct)
                
                if forge_changes:
                    ut = replace(ut, **forge_changes)
        
        # === Combo：基于标签的属性加成（镜像可映射到右侧） ===
        if side == "left" or (side == "right" and self.mirror_apply_right):
            unit_tags = ut.tags if hasattr(ut, 'tags') else []
            combo_changes = {}
            
            aoe_bonus = float(self._combo_value(side, "combo_aoe_radius_bonus", 0.0) or 0.0)
            melee_bonus = float(self._combo_value(side, "combo_melee_speed_bonus", 0.0) or 0.0)
            ranged_bonus = float(self._combo_value(side, "combo_ranged_range_bonus", 0.0) or 0.0)
            support_bonus = float(self._combo_value(side, "combo_support_heal_bonus", 0.0) or 0.0)
            control_bonus = float(self._combo_value(side, "combo_control_duration_bonus", 0.0) or 0.0)
            aura_resonance = bool(self._combo_value(side, "combo_aura_resonance", False))

            # AOE半径加成
            if "aoe" in unit_tags and aoe_bonus > 0:
                combo_changes["aoe_radius"] = ut.aoe_radius * (1.0 + aoe_bonus)
            
            # 移速加成（近战）
            if "melee" in unit_tags and melee_bonus > 0:
                combo_changes["speed"] = ut.speed * (1.0 + melee_bonus)
            
            # 射程加成（远程）
            if "ranged" in unit_tags and ranged_bonus > 0:
                combo_changes["range"] = ut.range * (1.0 + ranged_bonus)
            
            # 治疗量加成（support）
            if "support" in unit_tags and support_bonus > 0:
                combo_changes["heal_amount"] = int(round(ut.heal_amount * (1.0 + support_bonus)))
            
            # 控制时长加成（control）
            if "control" in unit_tags and control_bonus > 0:
                bonus = 1.0 + control_bonus
                if ut.melee_stun_duration > 0:
                    combo_changes["melee_stun_duration"] = ut.melee_stun_duration * bonus
                if ut.frost_stun_duration > 0:
                    combo_changes["frost_stun_duration"] = ut.frost_stun_duration * bonus
                if ut.projectile_slow_duration > 0:
                    combo_changes["projectile_slow_duration"] = ut.projectile_slow_duration * bonus
                if ut.charge_interrupt_stun > 0:
                    combo_changes["charge_interrupt_stun"] = ut.charge_interrupt_stun * bonus
            
            # 光环范围加成（support + buffer）
            if "support" in unit_tags and aura_resonance and getattr(ut, "is_buffer", False):
                combo_changes["aura_radius"] = ut.aura_radius * 1.30
            
            if combo_changes:
                ut = replace(ut, **combo_changes)

        return ut

    def _apply_max_level_traits(self, key: str, ut: UnitType) -> None:
        if key == "Q":  # 战士
            ut.first_hit_invuln_duration = 5.0
        elif key == "W":  # 盾卫
            ut.passive_reflect_ratio = 0.20
        elif key == "E":  # 大锤
            ut.aoe_stun_radius = max(ut.aoe_stun_radius, 48.0)
        elif key == "R":  # 狂战
            ut.lifesteal_ratio = max(ut.lifesteal_ratio, 0.20)
        elif key == "A":  # 牧师
            ut.heal_aoe_radius = max(ut.heal_aoe_radius, 120.0)
        elif key == "S":  # 弓手
            ut.projectile_pierce = max(ut.projectile_pierce, 1)
            if ut.projectile_falloff <= 0.0:
                ut.projectile_falloff = 0.3
        elif key == "D":  # 法师
            radius = max(ut.aoe_radius, 60.0)
            ut.ignite_radius = max(ut.ignite_radius, radius)
            ut.ignite_duration = max(ut.ignite_duration, 3.0)
            ut.ignite_dps = max(ut.ignite_dps, ut.damage * 0.6)
            ut.ignite_on_attack = True
        elif key == "F":  # 犀牛
            ut.knockback_stun_threshold = max(ut.knockback_stun_threshold, 4)
            ut.knockback_stun_duration = max(ut.knockback_stun_duration, 1.0)
        elif key == "G":  # 刺客
            ut.stealth_in_own_half = True
        elif key == "H":  # 破箭
            ut.reflect_heal_ratio = max(ut.reflect_heal_ratio, 0.08)
        elif key == "J":  # 鼓手
            ut.aura_shield_ratio = max(ut.aura_shield_ratio, 0.25)
            ut.aura_shield_interval = max(ut.aura_shield_interval, 10.0)
            ut.aura_shield_duration = max(ut.aura_shield_duration, 5.0)
        elif key == "K":  # 矛兵
            ut.control_immune = True
        elif key == "L":  # 冰弓
            ut.projectile_stun_aoe_radius = max(ut.projectile_stun_aoe_radius, 60.0)
        elif key == "M":  # 自爆车
            ut.ignite_radius = max(ut.ignite_radius, 70.0)
            ut.ignite_duration = max(ut.ignite_duration, 5.0)
            ut.ignite_dps = max(ut.ignite_dps, 35.0)
            ut.ignite_on_attack = False
        elif key == "N":  # 轻骑
            ut.charge_rearm_time = max(ut.charge_rearm_time, 2.0)

    def _apply_drummer_shield(self, source: Unit, allies: List[Unit]) -> None:
        ratio = max(0.0, source.unit_type.aura_shield_ratio)
        if ratio <= 0.0:
            return
        duration = max(0.0, source.unit_type.aura_shield_duration)
        if duration <= 0.0:
            duration = 3.0
        for ally in allies:
            if not ally.alive:
                continue
            if abs(ally.x - source.x) <= source.unit_type.aura_radius:
                max_hp = ally.max_hp if getattr(ally, "max_hp", 0.0) > 0.0 else float(ally.unit_type.hp)
                shield = max_hp * ratio
                if shield <= 0.0:
                    continue
                ally.shield_hp = max(0.0, ally.shield_hp) + shield
                ally.shield_timer = max(ally.shield_timer, duration)

    def _register_knockback(self, attacker: Unit, target: Unit | None) -> None:
        if target is None or not target.alive:
            return
        threshold = getattr(attacker.unit_type, "knockback_stun_threshold", 0)
        duration = getattr(attacker.unit_type, "knockback_stun_duration", 0.0)
        if threshold <= 0 or duration <= 0.0:
            return
        key = id(target)
        count = attacker.knockback_track.get(key, 0) + 1
        if count >= threshold:
            attacker.knockback_track[key] = 0
            if not target.unit_type.control_immune:
                target.stunned_timer = max(target.stunned_timer, duration)
        else:
            attacker.knockback_track[key] = count

    def _is_unit_targetable(self, seeker: Unit, candidate: Unit | None) -> bool:
        if candidate is None or not candidate.alive:
            return False
        if seeker.side != candidate.side:
            if candidate.unit_type.is_stealthed or getattr(candidate, "is_stealthed_dynamic", False):
                return False
        return True

    def _inflict_damage(
        self,
        target: Unit,
        amount: float,
        damage_type: str,
        source_unit: Unit | None = None,
        allow_reflect: bool = True,
    ) -> float:
        if amount <= 0.0 or not target.alive:
            return 0.0
        if target.unit_type.invulnerable:
            return 0.0
        if getattr(target, "invuln_timer", 0.0) > 0.0:
            return 0.0
        
        # === Combo：碎冰效应 - 对受控单位伤害+20% ===
        if source_unit and bool(self._combo_value(source_unit.side, "combo_ice_shatter", False)):
            if target.stunned_timer > 0 or target.frozen_timer > 0 or target.rooted_timer > 0:
                amount *= 1.20
        
        # === Combo：震荡铠甲 - tank受击时反击眩晕 ===
        if source_unit and damage_type == "melee" and bool(self._combo_value(target.side, "combo_shock_armor", False)):
            target_tags = target.unit_type.tags if hasattr(target.unit_type, 'tags') else []
            if "tank" in target_tags:
                import random
                if random.random() < 0.20:
                    if not source_unit.unit_type.control_immune:
                        source_unit.stunned_timer = max(source_unit.stunned_timer, 0.8)
        
        actual = target.take_damage(amount)
        if actual <= 0.0:
            return 0.0
        if (
            target.unit_type.first_hit_invuln_duration > 0.0
            and not target.max_level_first_hit_invuln_used
        ):
            target.max_level_first_hit_invuln_used = True
            target.invuln_timer = max(target.invuln_timer, target.unit_type.first_hit_invuln_duration)
        if source_unit is not None and source_unit.alive:
            lifesteal_ratio = max(0.0, source_unit.unit_type.lifesteal_ratio)
            if lifesteal_ratio > 0.0:
                source_unit.heal(actual * lifesteal_ratio)
            # 点燃道路
            if (
                source_unit.unit_type.ignite_on_attack
                and source_unit.unit_type.ignite_radius > 0.0
                and source_unit.unit_type.ignite_duration > 0.0
                and source_unit.unit_type.ignite_dps > 0.0
            ):
                self._create_ignite_hazard(
                    source_unit,
                    lane=target.lane,
                    center_x=target.x,
                )
        if (
            allow_reflect
            and target.unit_type.reflect_all_damage
            and source_unit is not None
            and source_unit.alive
        ):
            self._inflict_damage(source_unit, actual, damage_type, target, allow_reflect=False)
        elif (
            allow_reflect
            and target.unit_type.passive_reflect_ratio > 0.0
            and source_unit is not None
            and source_unit.alive
        ):
            reflect_amount = actual * target.unit_type.passive_reflect_ratio
            if reflect_amount > 0.0:
                self._inflict_damage(source_unit, reflect_amount, damage_type, target, allow_reflect=False)
        return actual

    def _create_ignite_hazard(self, source_unit: Unit, lane: int, center_x: float):
        radius = source_unit.unit_type.ignite_radius
        duration = source_unit.unit_type.ignite_duration
        dps = source_unit.unit_type.ignite_dps
        side_mult = self.left_damage_mult if source_unit.side == "left" else self.right_damage_mult
        if side_mult > 0.0:
            dps *= side_mult
        else:
            dps = 0.0
        if radius <= 0.0 or duration <= 0.0 or dps <= 0.0:
            return
        if lane < 0 or lane >= LANE_COUNT:
            return
        if center_x < 0 or center_x > SCREEN_WIDTH:
            center_x = max(0.0, min(float(center_x), float(SCREEN_WIDTH)))
        existing = None
        for hazard in self.lane_hazards:
            if hazard.side == source_unit.side and hazard.lane == lane:
                if abs(hazard.x - center_x) <= max(hazard.radius, radius):
                    existing = hazard
                    break
        if existing is not None:
            existing.x = center_x
            existing.radius = max(existing.radius, radius)
            existing.dps = max(existing.dps, dps)
            existing.duration = duration
            existing.max_duration = duration
            return
        hazard = LaneHazard(
            lane=lane,
            side=source_unit.side,
            x=center_x,
            radius=radius,
            duration=duration,
            dps=dps,
        )
        self.lane_hazards.append(hazard)

    def _tick_lane_hazards(self, lane: int, dt: float):
        if not self.lane_hazards:
            return
        for hazard in list(self.lane_hazards):
            if hazard.lane != lane:
                continue
            hazard.tick(dt)
            if not hazard.is_active():
                self.lane_hazards.remove(hazard)
                continue
            if hazard.lane < 0 or hazard.lane >= LANE_COUNT:
                self.lane_hazards.remove(hazard)
                continue
            victim_list = self.right_units[lane] if hazard.side == "left" else self.left_units[lane]
            for unit in victim_list:
                if not unit.alive:
                    continue
                if abs(unit.x - hazard.x) <= hazard.radius:
                    self._inflict_damage(unit, hazard.dps * dt, "hazard", None, allow_reflect=True)

    # 资源与冷却
    def _tick_economy(self, dt: float):
        for player in (self.left, self.right):
            if player is self.left:
                if self.left_infinite_resource:
                    continue
                cap = getattr(self, 'left_res_cap', MAX_RESOURCE)
                gain = RESOURCE_PER_SEC * getattr(self, 'left_econ_mult', 1.0) * self.left_resource_rate_mult * dt
                player.resource = min(cap, player.resource + gain)
            else:
                cap = getattr(self, 'right_res_cap', MAX_RESOURCE)
                gain = RESOURCE_PER_SEC * dt * self.right_resource_mult
                player.resource = min(cap, player.resource + gain)
            for k in list(player.spawn_cooldowns.keys()):
                if player.spawn_cooldowns[k] > 0:
                    player.spawn_cooldowns[k] -= dt

    def can_spawn(self, side: str, lane: int, key: str) -> bool:
        if key not in UNIT_TYPES:
            return False
        # 受配阵限制
        if side == "left" and key not in self.player_order_keys:
            return False
        if side == "right" and key not in self.ai_order_keys:
            return False
        unit_type = UNIT_TYPES[key]
        player = self.left if side == "left" else self.right
        if not (side == "left" and self.left_infinite_resource):
            cost = unit_type.cost
            # 钢铁洪流：费用减半
            if side == "left":
                cost = int(cost * self.left_cost_mult)
            elif self.mirror_apply_right:
                if key == "Q" and self.right_veteran_q_free_cost:
                    cost = 0
                else:
                    cost = int(cost * self.right_cost_mult)
            if player.resource < cost:
                return False
        if player.spawn_cooldowns[key] > 0:
            return False
        return 0 <= lane < LANE_COUNT

    def spawn_unit(self, side: str, lane: int, key: str):
        # 老兵祝福：英雄祭献 - 第5关起禁止部署Q
        if side == "left" and key == "Q" and self.campaign_day >= self.veteran_sacrifice_day_limit:
            return False
        if side == "right" and self.mirror_apply_right and key == "Q" and self.campaign_day >= self.right_veteran_sacrifice_day_limit:
            return False
        
        if not self.can_spawn(side, lane, key):
            return False
        unit_type = self._get_unit_type_with_level(side, key)
        if unit_type is None:
            return False
        y = self.lane_y[lane]
        if side == "left":
            base = self.left_bases[lane]
            x = base.x + base.width / 2 + unit_type.radius + 2
        else:
            base = self.right_bases[lane]
            x = base.x - base.width / 2 - unit_type.radius - 2
        # 计算单位属性（应用祝福加成）
        hp_mult = self.left_hp_mult if side == "left" else self.right_hp_mult
        damage_mult = 1.0
        
        if side == "left" or (side == "right" and self.mirror_apply_right):
            # 英雄祭献：非Q单位属性加成（由modifiers传入，默认+50%）
            if side == "left":
                sac_hp_mult = self.veteran_sacrifice_hp_mult
                sac_dmg_mult = self.veteran_sacrifice_damage_mult
                mentor_q_hp = self.veteran_mentor_q_hp_mult
                mentor_q_dmg = self.veteran_mentor_q_damage_mult
            else:
                sac_hp_mult = self.right_veteran_sacrifice_hp_mult
                sac_dmg_mult = self.right_veteran_sacrifice_damage_mult
                mentor_q_hp = self.right_veteran_mentor_q_hp_mult
                mentor_q_dmg = self.right_veteran_mentor_q_damage_mult
            if key != "Q" and sac_hp_mult > 1.0:
                hp_mult *= sac_hp_mult
                damage_mult *= sac_dmg_mult
            # 教官光环：Q的HP+75%/伤害-40%
            if key == "Q":
                hp_mult *= mentor_q_hp
                damage_mult *= mentor_q_dmg
            
            # === Combo：基于标签的加成 ===
            unit_tags = unit_type.tags if hasattr(unit_type, 'tags') else []
            
            # 职能加成
            tank_bonus = float(self._combo_value(side, "combo_tank_hp_bonus", 0.0) or 0.0)
            dps_bonus = float(self._combo_value(side, "combo_dps_damage_bonus", 0.0) or 0.0)
            if "tank" in unit_tags and tank_bonus > 0:
                hp_mult *= (1.0 + tank_bonus)
            if "dps" in unit_tags and dps_bonus > 0:
                damage_mult *= (1.0 + dps_bonus)
        
        # 创建单位实例（应用属性倍率）
        final_hp = float(unit_type.hp) * hp_mult * self.lane_hp_mult[lane]
        unit = Unit(
            unit_type=unit_type,
            side=side,
            lane=lane,
            x=float(x),
            y=y,
            hp=final_hp,
            max_hp=final_hp,
            attack_animation_duration=unit_type.attack_animation_duration,
        )
        # 存储伤害倍率（用于战斗计算）
        if damage_mult != 1.0:
            unit.temp_damage_multiplier = damage_mult
        # 初始化动画相关字段
        unit.last_x = float(x)
        if side == "left":
            self.left_units[lane].append(unit)
            self.battle_left_spawn_counts[key] = self.battle_left_spawn_counts.get(key, 0) + 1
            
            # 老兵祝福：破釜沉舟 - Q部署成本为0，但扣基地血
            cost = unit_type.cost
            if key == "Q" and self.veteran_q_free_cost:
                cost = 0
                if self.veteran_q_base_damage > 0 and lane < len(self.left_bases):
                    self.left_bases[lane].hp -= self.veteran_q_base_damage
            else:
                # 钢铁洪流：费用减半
                cost = int(cost * self.left_cost_mult)
            
            if not self.left_infinite_resource:
                # Combo：死士招募 - 免费部署标记
                if self.combo_next_spawn_free:
                    self.left.resource += cost  # 退款
                    self.combo_next_spawn_free = False
                else:
                    self.left.resource -= cost
            
            # 钢铁洪流：CD减半 + Combo：快速产线CD-15%
            base_cd = 0.15
            self.left.spawn_cooldowns[key] = base_cd * self.left_cooldown_mult * self.combo_spawn_cd_mult
            
            # 护盾
            if getattr(self, 'left_shield_pct', 0.0) > 0.0:
                unit.shield_hp = unit.unit_type.hp * self.left_shield_pct
                unit.shield_timer = getattr(self, 'left_shield_dur', 0.0)
        else:
            self.right_units[lane].append(unit)
            cost = unit_type.cost
            if self.mirror_apply_right:
                if key == "Q" and self.right_veteran_q_free_cost:
                    cost = 0
                    if self.right_veteran_q_base_damage > 0 and lane < len(self.right_bases):
                        self.right_bases[lane].hp -= self.right_veteran_q_base_damage
                else:
                    cost = int(cost * self.right_cost_mult)
            self.right.resource -= cost
            base_cd = 0.15
            if self.mirror_apply_right:
                self.right.spawn_cooldowns[key] = base_cd * self.right_cooldown_mult * self.mirror_combo_spawn_cd_mult
            else:
                self.right.spawn_cooldowns[key] = base_cd
            self.battle_right_spawned_types.add(key)
            self.battle_right_spawn_counts[key] = self.battle_right_spawn_counts.get(key, 0) + 1
        return True

    # AI：简单的随机出兵，偏向被压的战线
    def _ai_step(self, dt: float):
        if self.winner:
            return
        self._ai_timer -= dt
        if self._ai_timer > 0:
            return
        if self.right.resource < self.AI_MIN_RESOURCE_THRESHOLD:
            self._ai_timer = random.uniform(0.35, 0.9) * max(0.2, self.ai_interval_mult)
            return
        self._ai_timer = random.uniform(0.35, 0.9) * max(0.2, self.ai_interval_mult)

        # 评估压力：按每线最前沿左右距离（加入轻量规则：不往已爆基地送兵；对“明显推不动的堡垒线”降权）
        pressures: List[Tuple[float, int]] = []
        midline = SCREEN_WIDTH / 2.0
        for lane in range(LANE_COUNT):
            # 不往已爆基地（己方或对方）继续送兵
            if self.left_bases[lane].hp <= 0 or self.right_bases[lane].hp <= 0:
                continue

            left_units = self.left_units[lane]
            right_units = self.right_units[lane]

            # 空线前沿（非常关键）：
            # - 这里的 default 必须“不要比实际出兵口更靠前”，否则当玩家刚在该线出第一只兵时，
            #   left_front 可能从 default(更靠前) 变成 新单位 x(更靠后) —— 反而让 gap 变大，
            #   造成 AI 开局刻意避开玩家第一波所在战线（反直觉，且会导致玩家白送一路）。
            # - 因此，使用“基地口附近”作为空线前沿：保证加入单位只会让前沿更靠前，而不会倒退。
            left_front_default = float(self.left_bases[lane].x + self.left_bases[lane].width / 2 + 2)
            right_front_default = float(self.right_bases[lane].x - self.right_bases[lane].width / 2 - 2)
            left_front = max([u.x for u in left_units], default=left_front_default)
            right_front = min([u.x for u in right_units], default=right_front_default)

            gap = right_front - left_front
            metric = float(gap)

            # 防守紧急度：玩家前线越接近右侧基地，越优先防守该线
            danger = float(self.right_bases[lane].x) - float(left_front)
            if danger < 160:
                metric -= 160.0

            # “堡垒线”判定：玩家同线拥有前排高血 + 后排远程，且数量优势明显时，避免无脑喂兵
            # 注意：这不让 AI 变“聪明”，只是减少明显无效的送兵。
            if danger > 260 and left_front < midline + 40:
                left_count = sum(1 for u in left_units if u.alive)
                right_count = sum(1 for u in right_units if u.alive)
                # 前排：高血近战且接近前线
                left_frontline_tank = any(
                    u.alive
                    and (not u.unit_type.is_ranged)
                    and u.unit_type.hp >= 240
                    and (left_front - u.x) <= 70
                    for u in left_units
                )
                left_backline = sum(1 for u in left_units if u.alive and (u.unit_type.is_ranged or u.unit_type.is_healer))
                fortified = left_frontline_tank and left_backline >= 2 and left_count >= right_count + 2
                if fortified:
                    metric += 220.0

            pressures.append((metric, lane))

        if not pressures:
            return

        pressures.sort()  # metric 越小越优先
        _, lane_pick = pressures[0]

        lanes_to_try = [lane_pick]
        if self.ai_extra_spawn > 0:
            remaining = [
                idx
                for idx in range(LANE_COUNT)
                if idx != lane_pick and self.left_bases[idx].hp > 0 and self.right_bases[idx].hp > 0
            ]
            random.shuffle(remaining)
            lanes_to_try.extend(remaining[: self.ai_extra_spawn])

        for lane_try in lanes_to_try:
            candidates = [key for key in self.ai_order_keys if self.can_spawn("right", lane_try, key)]
            if not candidates:
                continue
            last_key = self._ai_lane_last_unit.get(lane_try)
            if len(candidates) > 1 and last_key in candidates:
                others = [k for k in candidates if k != last_key]
                if others:
                    candidates = others
            pick = random.choice(candidates)
            if self.spawn_unit("right", lane_try, pick):
                self._ai_lane_last_unit[lane_try] = pick

    # === 镜像Boss脚本调度 ===
    def set_mirror_script(self, script: List[dict] | None):
        self.mirror_script = list(script or [])
        self.mirror_script_idx = 0
        self.mirror_script_enabled = bool(self.mirror_script)
        self.mirror_script_cycle_start = 0.0
        self.mirror_script_duration = 0.0
        if self.mirror_script_enabled:
            max_t = 0.0
            for evt in self.mirror_script:
                try:
                    t = float((evt or {}).get("t", 0.0))
                except Exception:
                    t = 0.0
                if t > max_t:
                    max_t = t
            self.mirror_script_duration = max_t

    def _tick_mirror_script(self):
        if not self.mirror_script_enabled or self.winner:
            return
        if self.mirror_script_duration > 0.0 and self.mirror_script_idx >= len(self.mirror_script):
            local_time = self.battle_time - self.mirror_script_cycle_start
            cycles = int(local_time // self.mirror_script_duration)
            if cycles > 0:
                self.mirror_script_cycle_start += cycles * self.mirror_script_duration
            self.mirror_script_idx = 0
        local_time = self.battle_time - self.mirror_script_cycle_start
        while self.mirror_script_idx < len(self.mirror_script):
            evt = self.mirror_script[self.mirror_script_idx] or {}
            try:
                t = float(evt.get("t", 0.0))
            except Exception:
                t = 0.0
            if t > local_time:
                break
            evt_type = evt.get("type")
            lane = int(evt.get("lane", 0) or 0)
            if evt_type == "spawn":
                key = evt.get("unit")
                if key:
                    self.spawn_unit_free("right", lane, key)
            elif evt_type == "skill":
                skill_key = evt.get("skill")
                if skill_key:
                    self.cast_skill_forced("right", skill_key, lane, spawn_unit_key=evt.get("unit"))
            self.mirror_script_idx += 1

    def _tick_skill_effects(self, dt: float):
        if self.left_skill_damage_timer > 0.0:
            self.left_skill_damage_timer = max(0.0, self.left_skill_damage_timer - dt)
            if self.left_skill_damage_timer <= 0.0:
                self.left_skill_damage_mult = 1.0
        if self.right_skill_damage_timer > 0.0:
            self.right_skill_damage_timer = max(0.0, self.right_skill_damage_timer - dt)
            if self.right_skill_damage_timer <= 0.0:
                self.right_skill_damage_mult = 1.0
        if self.left_skill_speed_timer > 0.0:
            self.left_skill_speed_timer = max(0.0, self.left_skill_speed_timer - dt)
            if self.left_skill_speed_timer <= 0.0:
                self.left_skill_speed_mult = 1.0
        if self.right_skill_speed_timer > 0.0:
            self.right_skill_speed_timer = max(0.0, self.right_skill_speed_timer - dt)
            if self.right_skill_speed_timer <= 0.0:
                self.right_skill_speed_mult = 1.0
        for idx in range(LANE_COUNT):
            if self.left_base_invuln_timer[idx] > 0.0:
                self.left_base_invuln_timer[idx] = max(0.0, self.left_base_invuln_timer[idx] - dt)
            if self.right_base_invuln_timer[idx] > 0.0:
                self.right_base_invuln_timer[idx] = max(0.0, self.right_base_invuln_timer[idx] - dt)

    # 战斗推进
    def _combat_step(self, dt: float):
        self._tick_skill_effects(dt)
        # 单位移动与攻击
        for lane in range(LANE_COUNT):
            left_list = self.left_units[lane]
            right_list = self.right_units[lane]

            # 排序有助于减少碰撞对比
            left_list.sort(key=lambda u: u.x)
            right_list.sort(key=lambda u: u.x)

            # 冷却与状态计时，并重置临时加成
            for u in left_list + right_list:
                u.tick_cooldown(dt)
                if u.intercept_timer > 0:
                    u.intercept_timer -= dt
                # M4：Combo 可提供全局单位速度/攻速加成（叠在临时buff之前）
                if u.side == "left":
                    u.temp_speed_multiplier = self.left_unit_speed_mult
                    u.temp_cooldown_multiplier = 1.0 / max(0.0001, self.left_unit_atkspd_mult)
                    
                    # Combo：基于标签的攻速加成（远程）
                    unit_tags = u.unit_type.tags if hasattr(u.unit_type, 'tags') else []
                    ranged_bonus = float(self._combo_value(u.side, "combo_ranged_atkspd_bonus", 0.0) or 0.0)
                    if "ranged" in unit_tags and ranged_bonus > 0:
                        u.temp_cooldown_multiplier *= (1.0 - ranged_bonus)
                else:
                    if self.mirror_apply_right:
                        u.temp_speed_multiplier = self.right_unit_speed_mult
                        u.temp_cooldown_multiplier = 1.0 / max(0.0001, self.right_unit_atkspd_mult)
                    else:
                        u.temp_speed_multiplier = 1.0
                        u.temp_cooldown_multiplier = 1.0
                    if self.mirror_apply_right:
                        unit_tags = u.unit_type.tags if hasattr(u.unit_type, 'tags') else []
                        ranged_bonus = float(self._combo_value(u.side, "combo_ranged_atkspd_bonus", 0.0) or 0.0)
                        if "ranged" in unit_tags and ranged_bonus > 0:
                            u.temp_cooldown_multiplier *= (1.0 - ranged_bonus)
                # 战线被动：速度修正（对双方对称）
                if 0 <= u.lane < LANE_COUNT:
                    u.temp_speed_multiplier *= self.lane_speed_mult[u.lane]
            
            # === Combo：战线联动加成扫描 ===
            left_firm_line = bool(self._combo_value("left", "combo_firm_line", False))
            left_combined_arms = bool(self._combo_value("left", "combo_combined_arms", False))
            if left_firm_line or left_combined_arms:
                for u in left_list:
                    if not u.alive:
                        continue
                    unit_tags = u.unit_type.tags if hasattr(u.unit_type, 'tags') else []
                    
                    # 坚毅阵线：同线有tank+dps，两者伤害+15%
                    if left_firm_line and ("tank" in unit_tags or "dps" in unit_tags):
                        has_tank = any(u2.alive and "tank" in getattr(u2.unit_type, 'tags', []) for u2 in left_list)
                        has_dps = any(u2.alive and "dps" in getattr(u2.unit_type, 'tags', []) for u2 in left_list)
                        if has_tank and has_dps:
                            u.temp_damage_multiplier *= 1.15
                    
                    # 步炮协同：同线有melee+ranged，远程攻速+25%
                    if left_combined_arms and "ranged" in unit_tags:
                        has_melee = any(u2.alive and "melee" in getattr(u2.unit_type, 'tags', []) for u2 in left_list)
                        if has_melee:
                            u.temp_cooldown_multiplier *= 0.75  # 攻速+25% = CD x0.75
                if self.mirror_apply_right:
                    right_firm_line = bool(self._combo_value("right", "combo_firm_line", False))
                    right_combined_arms = bool(self._combo_value("right", "combo_combined_arms", False))
                    for u in right_list:
                        if not u.alive:
                            continue
                        unit_tags = u.unit_type.tags if hasattr(u.unit_type, 'tags') else []
                        if right_firm_line and ("tank" in unit_tags or "dps" in unit_tags):
                            has_tank = any(u2.alive and "tank" in getattr(u2.unit_type, 'tags', []) for u2 in right_list)
                            has_dps = any(u2.alive and "dps" in getattr(u2.unit_type, 'tags', []) for u2 in right_list)
                            if has_tank and has_dps:
                                u.temp_damage_multiplier *= 1.15
                        if right_combined_arms and "ranged" in unit_tags:
                            has_melee = any(u2.alive and "melee" in getattr(u2.unit_type, 'tags', []) for u2 in right_list)
                            if has_melee:
                                u.temp_cooldown_multiplier *= 0.75
            
            # === Combo：全线压制 - 检查是否有3+条线有友军 ===
            left_full_suppression = bool(self._combo_value("left", "combo_full_suppression", False))
            if left_full_suppression:
                active_lanes = sum(1 for l in range(LANE_COUNT) if any(u.alive for u in self.left_units[l]))
                if active_lanes >= 3:
                    for u in left_list:
                        if u.alive:
                            u.temp_damage_multiplier *= 1.15
                if self.mirror_apply_right:
                    right_full_suppression = bool(self._combo_value("right", "combo_full_suppression", False))
                    if right_full_suppression:
                        active_lanes_r = sum(1 for l in range(LANE_COUNT) if any(u.alive for u in self.right_units[l]))
                        if active_lanes_r >= 3:
                            for u in right_list:
                                if u.alive:
                                    u.temp_damage_multiplier *= 1.15

            midline = SCREEN_WIDTH / 2.0
            for u in left_list:
                stealth = u.unit_type.is_stealthed
                if u.unit_type.stealth_in_own_half:
                    stealth = stealth or (u.x <= midline)
                u.is_stealthed_dynamic = stealth
            for u in right_list:
                stealth = u.unit_type.is_stealthed
                if u.unit_type.stealth_in_own_half:
                    stealth = stealth or (u.x >= midline)
                u.is_stealthed_dynamic = stealth

            # 号手光环：同线增益
            for source in left_list:
                if source.unit_type.is_buffer:
                    if source.unit_type.aura_shield_ratio > 0.0 and source.unit_type.aura_shield_interval > 0.0:
                        source.shield_pulse_timer -= dt
                        if source.shield_pulse_timer <= 0.0:
                            source.shield_pulse_timer += source.unit_type.aura_shield_interval
                            self._apply_drummer_shield(source, left_list)
                    for ally in left_list:
                        if ally is source:
                            continue
                        if abs(ally.x - source.x) <= source.unit_type.aura_radius:
                            ally.temp_speed_multiplier *= source.unit_type.buff_move_mult
                            ally.temp_cooldown_multiplier *= source.unit_type.buff_cooldown_mult
                            if hasattr(ally, "ui_highlights"):
                                ally.ui_highlights.add("drummer")
            
            # 祝福：教官光环 - 老兵正后方的单位增益（攻速/伤害由modifiers决定）
            if self.veteran_mentor_atkspd_bonus > 0.0 or self.veteran_mentor_damage_bonus > 0.0:
                for veteran in left_list:
                    # 检查是否是老兵（key=="Q"）
                    if getattr(veteran.unit_type, "key", "") == "Q":
                        # 这个单位是老兵，检查后方的友军
                        for ally in left_list:
                            if ally is veteran:
                                continue
                            # 同一战线且在老兵后方（X坐标更小）
                            if ally.lane == veteran.lane and ally.x < veteran.x:
                                # 应用攻速buff（降低冷却时间）
                                if self.veteran_mentor_atkspd_bonus > 0.0:
                                    ally.temp_cooldown_multiplier *= (1.0 - self.veteran_mentor_atkspd_bonus)
                                # 应用伤害buff
                                if self.veteran_mentor_damage_bonus > 0.0:
                                    ally.temp_damage_multiplier *= (1.0 + self.veteran_mentor_damage_bonus)
                                if hasattr(ally, "ui_highlights"):
                                    ally.ui_highlights.add("veteran_mentor")
            if self.mirror_apply_right and (self.right_veteran_mentor_atkspd_bonus > 0.0 or self.right_veteran_mentor_damage_bonus > 0.0):
                for veteran in right_list:
                    if getattr(veteran.unit_type, "key", "") == "Q":
                        for ally in right_list:
                            if ally is veteran:
                                continue
                            if ally.lane == veteran.lane and ally.x > veteran.x:
                                if self.right_veteran_mentor_atkspd_bonus > 0.0:
                                    ally.temp_cooldown_multiplier *= (1.0 - self.right_veteran_mentor_atkspd_bonus)
                                if self.right_veteran_mentor_damage_bonus > 0.0:
                                    ally.temp_damage_multiplier *= (1.0 + self.right_veteran_mentor_damage_bonus)
                                if hasattr(ally, "ui_highlights"):
                                    ally.ui_highlights.add("veteran_mentor")
            for source in right_list:
                if source.unit_type.is_buffer:
                    if source.unit_type.aura_shield_ratio > 0.0 and source.unit_type.aura_shield_interval > 0.0:
                        source.shield_pulse_timer -= dt
                        if source.shield_pulse_timer <= 0.0:
                            source.shield_pulse_timer += source.unit_type.aura_shield_interval
                            self._apply_drummer_shield(source, right_list)
                    for ally in right_list:
                        if ally is source:
                            continue
                        if abs(ally.x - source.x) <= source.unit_type.aura_radius:
                            ally.temp_speed_multiplier *= source.unit_type.buff_move_mult
                            ally.temp_cooldown_multiplier *= source.unit_type.buff_cooldown_mult
                            if hasattr(ally, "ui_highlights"):
                                ally.ui_highlights.add("drummer")

            # 玩家全局增益（速度/冷却）
            left_speed_bonus = getattr(self, 'left_speed_mult', 1.0)
            if self.left_skill_speed_timer > 0.0:
                left_speed_bonus *= self.left_skill_speed_mult
            left_cd_bonus = getattr(self, 'left_cd_mult', 1.0)
            left_origei_active = (self.left_skill_speed_timer > 0.0) or (self.left_skill_damage_timer > 0.0)
            for u in left_list:
                u.temp_speed_multiplier *= left_speed_bonus
                u.temp_cooldown_multiplier *= left_cd_bonus
                # 冷却不低于下限倍率
                if self.left_cd_floor:
                    u.temp_cooldown_multiplier = max(self.left_cd_floor / max(1e-6, u.unit_type.cooldown), u.temp_cooldown_multiplier)
                if left_origei_active and hasattr(u, "ui_highlights"):
                    u.ui_highlights.add("origei")

            right_speed_bonus = 1.0
            if self.right_skill_speed_timer > 0.0:
                right_speed_bonus *= self.right_skill_speed_mult
            right_origei_active = (self.right_skill_speed_timer > 0.0) or (self.right_skill_damage_timer > 0.0)
            if right_speed_bonus != 1.0:
                for u in right_list:
                    u.temp_speed_multiplier *= right_speed_bonus
                    if right_origei_active and hasattr(u, "ui_highlights"):
                        u.ui_highlights.add("origei")
            elif right_origei_active:
                for u in right_list:
                    if hasattr(u, "ui_highlights"):
                        u.ui_highlights.add("origei")

            # 移动（若未进入射程卡住/或需要跟随前方友军则停下）
            for u in left_list:
                # 若最近敌人进入本单位射程，则停止推进
                enemy = self._find_closest_enemy(u, right_list)
                stop = False
                enemy_dist = abs(u.x - enemy.x) if enemy is not None else None
                effective_range = u.unit_type.range
                if enemy is not None and enemy_dist is not None and enemy_dist <= effective_range:
                    if not u.unit_type.ignore_stop_when_enemy:
                        stop = True
                    else:
                        # 刺客特例：仅对远程/辅助类进入射程时停下
                        if u.unit_type.target_ranged_support_only:
                            valid = (enemy.unit_type.is_ranged or enemy.unit_type.is_healer or enemy.unit_type.is_buffer or enemy.unit_type.intercept_radius > 0.0)
                            if valid:
                                stop = True
                # 奶妈/鼓手特殊停步
                if not stop and (u.unit_type.is_healer or u.unit_type.is_buffer):
                    # 奶妈：保持较短跟随间距
                    if u.unit_type.is_healer and not u.unit_type.is_buffer:
                        ahead = None
                        for a in left_list:
                            if a is u:
                                continue
                            if a.x > u.x:
                                ahead = a
                                break
                        if ahead is not None:
                            follow_gap = max(24.0, float(u.unit_type.radius) + 12.0)
                            if (ahead.x - u.x) <= follow_gap:
                                stop = True
                    # 鼓手：优先前方，其次身后等待
                    elif u.unit_type.is_buffer:
                        ahead = None
                        for a in left_list:
                            if a is u:
                                continue
                            if a.x > u.x:
                                ahead = a
                                break
                        if ahead is not None:
                            # 有前方友军：若超出光环半径则前进，否则停下
                            desired = float(u.unit_type.aura_radius)
                            if (ahead.x - u.x) <= desired:
                                stop = True
                        else:
                            # 无前方友军：若身后光环半径内有友军则等待
                            has_behind_in_aura = False
                            for b in reversed(left_list):
                                if b is u:
                                    continue
                                if b.x < u.x and (u.x - b.x) <= u.unit_type.aura_radius:
                                    has_behind_in_aura = True
                                    break
                            if has_behind_in_aura:
                                stop = True
                if not stop:
                    u.update_position(dt)

            for u in right_list:
                enemy = self._find_closest_enemy(u, left_list)
                stop = False
                enemy_dist = abs(u.x - enemy.x) if enemy is not None else None
                effective_range = u.unit_type.range
                if enemy is not None and enemy_dist is not None and enemy_dist <= effective_range:
                    if not u.unit_type.ignore_stop_when_enemy:
                        stop = True
                    else:
                        if u.unit_type.target_ranged_support_only:
                            valid = (enemy.unit_type.is_ranged or enemy.unit_type.is_healer or enemy.unit_type.is_buffer or enemy.unit_type.intercept_radius > 0.0)
                            if valid:
                                stop = True
                # 奶妈/鼓手特殊停步（右侧）
                if not stop and (u.unit_type.is_healer or u.unit_type.is_buffer):
                    # 奶妈：较短跟随间距
                    if u.unit_type.is_healer and not u.unit_type.is_buffer:
                        ahead = None
                        for a in reversed(right_list):
                            if a is u:
                                continue
                            if a.x < u.x:
                                ahead = a
                                break
                        if ahead is not None:
                            follow_gap = max(24.0, float(u.unit_type.radius) + 12.0)
                            if (u.x - ahead.x) <= follow_gap:
                                stop = True
                    # 鼓手：优先前方，其次身后等待
                    elif u.unit_type.is_buffer:
                        ahead = None
                        for a in reversed(right_list):
                            if a is u:
                                continue
                            if a.x < u.x:
                                ahead = a
                                break
                        if ahead is not None:
                            desired = float(u.unit_type.aura_radius)
                            if (u.x - ahead.x) <= desired:
                                stop = True
                        else:
                            has_behind_in_aura = False
                            for b in right_list:
                                if b is u:
                                    continue
                                if b.x > u.x and (b.x - u.x) <= u.unit_type.aura_radius:
                                    has_behind_in_aura = True
                                    break
                            if has_behind_in_aura:
                                stop = True
                if not stop:
                    u.update_position(dt)

            # 地形危害（燃烧等）
            self._tick_lane_hazards(lane, dt)

            # 攻击/治疗或发射投射物
            self._attack_phase(left_list, right_list, lane)
            self._attack_phase(right_list, left_list, lane)
            
            # 更新动画状态
            self._update_unit_animations(left_list, right_list, dt)

        # 投射物更新与命中
        for p in list(self.projectiles):
            p.update(dt)
            
            # 投射物拖尾特效
            p.trail_timer += dt
            if p.trail_timer >= 0.05:
                p.trail_timer = 0.0
                if p.visual_type == "arrow":
                    # 箭矢：微弱的流线
                    self.particles.append(Particle(
                        x=p.x, y=p.y, radius=1, timer=0, duration=0.15, color=(200, 200, 200), max_radius=0, shape="line", vx=0, vy=0
                    ))
                elif p.visual_type == "orb":
                    # 法球：漂浮的魔法粒子
                    self.particles.append(Particle(
                        x=p.x + random.uniform(-2, 2), 
                        y=p.y + random.uniform(-2, 2), 
                        radius=random.uniform(2, 4), 
                        timer=0, duration=0.3, 
                        color=(255, 100, 200) if p.side=="right" else (100, 200, 255), 
                        max_radius=0, shape="square",
                        vx=random.uniform(-10, 10), vy=random.uniform(-10, 10)
                    ))

            if not p.active:
                self.projectiles.remove(p)
                continue

            # 防空拦截：对方的拦截单位可消除投射物，且有概率反弹
            interceptors = self.right_units[p.lane] if p.side == "left" else self.left_units[p.lane]
            intercepted = False
            interceptor_unit = None
            for u in interceptors:
                if u.unit_type.intercept_radius > 0.0 and u.intercept_timer <= 0.0:
                    if abs(u.x - p.x) <= u.unit_type.intercept_radius:
                        u.intercept_timer = u.unit_type.intercept_cooldown
                        # 触发攻击动画（用于破箭反弹等视觉效果）
                        u.time_since_last_attack = 0.0
                        intercepted = True
                        interceptor_unit = u
                        break
            if intercepted:
                # 50% 概率反弹（按单位配置）
                if interceptor_unit and interceptor_unit.unit_type.reflect_chance > 0.0 and random.random() < interceptor_unit.unit_type.reflect_chance:
                    dmg_ratio = max(0.0, min(1.0, interceptor_unit.unit_type.reflect_damage_ratio))
                    reflect_dmg = max(1, int(p.damage * dmg_ratio))
                    self.projectiles.append(Projectile(
                        x=interceptor_unit.x,
                        y=interceptor_unit.y,
                        speed=p.speed * 0.9,
                        damage=reflect_dmg,
                        lane=p.lane,
                        side=interceptor_unit.side,
                        aoe_radius=0.0,
                        owner=interceptor_unit,
                    ))
                    if interceptor_unit.unit_type.reflect_heal_ratio > 0.0:
                        heal_amount = interceptor_unit.max_hp * interceptor_unit.unit_type.reflect_heal_ratio
                        interceptor_unit.heal(heal_amount)
                p.active = False
                self.projectiles.remove(p)
                continue

            enemies = self.right_units[p.lane] if p.side == "left" else self.left_units[p.lane]
            hit_index = None
            for idx, e in enumerate(enemies):
                if abs(e.x - p.x) <= 12:
                    hit_index = idx
                    break
            if hit_index is not None:
                # 伤害（对我方可减伤）
                damage = p.damage
                if p.side == "right":
                    damage = int(damage * (1.0 - getattr(self, 'left_proj_reduce', 0.0)))
                if p.aoe_radius > 0.0:
                    for e in enemies:
                        if not e.alive:
                            continue
                        if abs(e.x - p.x) <= p.aoe_radius:
                            eff = int(damage * getattr(e.unit_type, 'ranged_taken_mult', 1.0))
                            self._inflict_damage(e, eff, "projectile", p.owner)
                            self.spawn_hit_effect(e.x, e.y, 1 if p.side == "left" else -1)
                else:
                    tgt = enemies[hit_index]
                    eff = int(damage * getattr(tgt.unit_type, 'ranged_taken_mult', 1.0))
                    self._inflict_damage(tgt, eff, "projectile", p.owner)
                    # 命中特效
                    self.spawn_hit_effect(tgt.x, tgt.y, 1 if p.side == "left" else -1)
                # 寒冰减速/眩晕效果
                target = enemies[hit_index]
                if target.alive and p.slow_stack > 0 and not target.unit_type.control_immune:
                    target.slow_stacks = min(10, target.slow_stacks + p.slow_stack)
                    extra_slow = self.left_frost_slow_extra if p.side == "left" else 0.0
                    target.slow_decay_timer = max(target.slow_decay_timer, p.slow_duration + extra_slow)
                    extra_stun = self.left_frost_stun_extra if p.side == "left" else 0.0
                    if p.frost_stun_cap > 0 and target.slow_stacks >= p.frost_stun_cap and not target.was_stunned_by_frost:
                        stun_duration = p.frost_stun_duration + extra_stun
                        target.stunned_timer = max(target.stunned_timer, stun_duration)
                        if p.owner is not None:
                            aoe_radius = getattr(p.owner.unit_type, "projectile_stun_aoe_radius", 0.0)
                            if aoe_radius > 0.0:
                                for extra_unit in enemies:
                                    if extra_unit is target or not extra_unit.alive:
                                        continue
                                    if abs(extra_unit.x - target.x) <= aoe_radius and not extra_unit.unit_type.control_immune:
                                        extra_unit.stunned_timer = max(extra_unit.stunned_timer, stun_duration)
                        target.was_stunned_by_frost = True
                # 穿透：有剩余则继续飞行
                if p.pierce > 0:
                    p.pierce -= 1
                    p.damage = max(1, int(p.damage * (1.0 - p.damage_falloff)))
                    continue
                p.active = False
                self.projectiles.remove(p)
                continue

            # 击中对应战线的基地（到达边界即视作命中）
            if p.side == "left" and p.x >= self.right_bases[p.lane].x - 24:
                if (
                    self.right_bases[p.lane].hp > 0
                    and self.right_base_invuln_timer[p.lane] <= 0.0
                    and not self.bases_invulnerable
                ):
                    self.right_bases[p.lane].hp -= p.damage
                p.active = False
                self.projectiles.remove(p)
            elif p.side == "right" and p.x <= self.left_bases[p.lane].x + 24:
                if (
                    self.left_bases[p.lane].hp > 0
                    and self.left_base_invuln_timer[p.lane] <= 0.0
                    and not self.bases_invulnerable
                ):
                    self.left_bases[p.lane].hp -= p.damage
                p.active = False
                self.projectiles.remove(p)

        for missile in list(self.skill_missiles):
            prev_x = missile.x
            prev_state = missile.state
            exploded = missile.update(dt)
            if not exploded and prev_state == "travel":
                if missile.state == "travel":
                    enemies = self.right_units if missile.side == "left" else self.left_units
                    lane_units = [u for u in enemies[missile.lane] if u.alive]
                    if lane_units:
                        min_x = min(prev_x, missile.x)
                        max_x = max(prev_x, missile.x)
                        margin = 6.0
                        contact_unit = None
                        if missile.side == "left":
                            best_key = None
                            for unit in lane_units:
                                if (unit.x < min_x - margin) or (unit.x > max_x + margin):
                                    continue
                                priority = 0 if unit.x >= prev_x else 1
                                key = (priority, unit.x)
                                if best_key is None or key < best_key:
                                    best_key = key
                                    contact_unit = unit
                        else:
                            best_key = None
                            for unit in lane_units:
                                if (unit.x < min_x - margin) or (unit.x > max_x + margin):
                                    continue
                                priority = 0 if unit.x <= prev_x else 1
                                key = (priority, -unit.x)
                                if best_key is None or key < best_key:
                                    best_key = key
                                    contact_unit = unit
                        if contact_unit is not None:
                            missile.x = contact_unit.x
                            missile.y = contact_unit.y
                            missile.state = "explode"
                            missile.explosion_timer = missile.explosion_duration
                            exploded = True
            if exploded:
                self._resolve_boom_explosion(missile)
            if missile.is_finished():
                self.skill_missiles.remove(missile)

        # 统计击杀（仅统计因伤害导致 hp<=0 的死亡），并处理返还
        for lane in range(LANE_COUNT):
            left_dead_by_damage = sum(1 for u in self.left_units[lane] if (not u.alive) and u.hp <= 0)
            right_dead_by_damage = sum(1 for u in self.right_units[lane] if (not u.alive) and u.hp <= 0)
            if left_dead_by_damage:
                self.right_kill_resource += left_dead_by_damage
            if right_dead_by_damage:
                # Combo：战斗律动 - 击杀资源获取+20%
                kill_gain = right_dead_by_damage
                if self.combo_kill_resource_bonus > 0:
                    kill_gain = int(round(kill_gain * (1.0 + self.combo_kill_resource_bonus)))
                
                self.left_kill_resource += kill_gain
                self.recent_kills += right_dead_by_damage
                
                # 祝福：掠夺者逻辑 - 击杀给钱（带上限护栏）
                if self.looter_battle_gold_cap > 0:
                    gold_to_add = right_dead_by_damage * self.looter_gold_per_kill
                    if self.looter_battle_gold_gained + gold_to_add <= self.looter_battle_gold_cap:
                        self.looter_battle_gold_gained += gold_to_add
                    else:
                        # 已达上限，只添加到上限为止
                        gold_to_add = max(0.0, self.looter_battle_gold_cap - self.looter_battle_gold_gained)
                        self.looter_battle_gold_gained = self.looter_battle_gold_cap
                
                # 击杀返还资源（粗略按死亡单位cost计）
                if getattr(self, 'left_refund_rate', 0.0) > 0.0 and self.left_refund_limit > 0:
                    for u in self.right_units[lane]:
                        if (not u.alive) and u.hp <= 0 and self._refund_window_count < self.left_refund_limit:
                            refund = int(u.unit_type.cost * self.left_refund_rate)
                            if refund > 0:
                                self.left.resource = min(getattr(self, 'left_res_cap', MAX_RESOURCE), self.left.resource + refund)
                                self._refund_window_count += 1

        # 单位死亡清理与基地到达一次性伤害
        for lane in range(LANE_COUNT):
            # Combo：死士招募 - 统计左侧dps单位死亡
            if self.combo_dead_recruit:
                for u in list(self.left_units[lane]):
                    if not u.alive and u.hp <= 0:
                        unit_tags = u.unit_type.tags if hasattr(u.unit_type, 'tags') else []
                        if "dps" in unit_tags:
                            self.combo_dps_death_count += 1
                            if self.combo_dps_death_count >= 5:
                                self.combo_next_spawn_free = True
                                self.combo_dps_death_count = 0
            
            # 分裂体生成 / 死亡爆炸：记录死亡单位再清理
            left_spawn: List[Unit] = []
            right_spawn: List[Unit] = []
            for u in list(self.left_units[lane]):
                if not u.alive and u.hp <= 0 and u.unit_type.death_explode_radius > 0.0 and u.unit_type.death_explode_damage > 0:
                    # 左侧单位死亡爆炸，伤害右侧同线单位
                    self.spawn_explosion_effect(u.x, u.y, u.unit_type.death_explode_radius)
                    for e in self.right_units[lane]:
                        if abs(e.x - u.x) <= u.unit_type.death_explode_radius:
                            self._inflict_damage(e, u.unit_type.death_explode_damage, "death", u, allow_reflect=True)
                if (
                    not u.alive
                    and u.hp <= 0
                    and u.unit_type.ignite_duration > 0.0
                    and u.unit_type.ignite_dps > 0.0
                ):
                    self._create_ignite_hazard(u, lane, u.x)
                if not u.alive and u.hp <= 0 and u.unit_type.split_on_death and u.unit_type.split_child_key:
                    child_key = u.unit_type.split_child_key
                    count = max(1, u.unit_type.split_children_count)
                    for i in range(count):
                        self.spawn_unit_free("left", lane, child_key)
                        # 调整新生单位位置
                        self.left_units[lane][-1].x = u.x - 8 + i * 8
                        self.left_units[lane][-1].y = u.y
            for u in list(self.right_units[lane]):
                if not u.alive and u.hp <= 0 and u.unit_type.death_explode_radius > 0.0 and u.unit_type.death_explode_damage > 0:
                    self.spawn_explosion_effect(u.x, u.y, u.unit_type.death_explode_radius)
                    for e in self.left_units[lane]:
                        if abs(e.x - u.x) <= u.unit_type.death_explode_radius:
                            self._inflict_damage(e, u.unit_type.death_explode_damage, "death", u, allow_reflect=True)
                if (
                    not u.alive
                    and u.hp <= 0
                    and u.unit_type.ignite_duration > 0.0
                    and u.unit_type.ignite_dps > 0.0
                ):
                    self._create_ignite_hazard(u, lane, u.x)
                if not u.alive and u.hp <= 0 and u.unit_type.split_on_death and u.unit_type.split_child_key:
                    child_key = u.unit_type.split_child_key
                    count = max(1, u.unit_type.split_children_count)
                    for i in range(count):
                        self.spawn_unit_free("right", lane, child_key)
                        self.right_units[lane][-1].x = u.x + 8 - i * 8
                        self.right_units[lane][-1].y = u.y

            self.left_units[lane] = [u for u in self.left_units[lane] if u.alive]
            self.right_units[lane] = [u for u in self.right_units[lane] if u.alive]

            # 左侧到达右基地：方案 A 物理撞击逻辑
            for u in list(self.left_units[lane]):
                if u.x >= self.right_bases[lane].x - 24:
                    base_alive = self.right_bases[lane].hp > 0
                    if base_alive:
                        impact_mult = 1.0
                        unit_key = getattr(u.unit_type, "key", "")
                        if unit_key == "G":
                            impact_mult = 0.3
                        elif unit_key == "N":
                            impact_mult = 0.5
                        elif unit_key == "F":
                            impact_mult = 1.5
                        
                        dmg = max(1, int(round(u.hp * impact_mult)))

                        if self.bases_invulnerable:
                            u.hp = 0
                        elif self.right_base_invuln_timer[lane] <= 0.0:
                            self.right_bases[lane].hp -= dmg
                        else:
                            u.hp = 0
                    else:
                        # 返还生产资源
                        if self.left_infinite_resource:
                            self.left.resource = max(self.left.resource, self.left_resource_amount)
                        else:
                            cap = getattr(self, 'left_res_cap', MAX_RESOURCE)
                            refund = int(u.unit_type.cost * 0.5)
                            if refund > 0:
                                self.left.resource = min(cap, self.left.resource + refund)
                    u.alive = False
                    self.left_units[lane].remove(u)
            # 右侧到达左基地：方案 A 物理撞击逻辑
            for u in list(self.right_units[lane]):
                if u.x <= self.left_bases[lane].x + 24:
                    base_alive = self.left_bases[lane].hp > 0
                    if base_alive:
                        impact_mult = 1.0
                        unit_key = getattr(u.unit_type, "key", "")
                        if unit_key == "G":
                            impact_mult = 0.3
                        elif unit_key == "N":
                            impact_mult = 0.5
                        elif unit_key == "F":
                            impact_mult = 1.5
                        
                        dmg = max(1, int(round(u.hp * impact_mult)))

                        if self.bases_invulnerable:
                            u.hp = 0
                        elif self.left_base_invuln_timer[lane] <= 0.0:
                            self.left_bases[lane].hp -= dmg
                        else:
                            u.hp = 0
                    else:
                        cap = getattr(self, 'right_res_cap', MAX_RESOURCE)
                        refund = int(u.unit_type.cost * 0.5)
                        if refund > 0:
                            self.right.resource = min(cap, self.right.resource + refund)
                    u.alive = False
                    self.right_units[lane].remove(u)

        # === Combo：应急协议 - 基地爆炸给资源 ===
        if self.combo_emergency_protocol:
            for lane_idx in range(LANE_COUNT):
                if self.left_bases[lane_idx].hp <= 0 and lane_idx not in self.combo_emergency_triggered_lanes:
                    self.combo_emergency_triggered_lanes.add(lane_idx)
                    cap = getattr(self, 'left_res_cap', MAX_RESOURCE)
                    self.left.resource = min(cap, self.left.resource + 250)
        
        # 胜负判断
        left_destroyed = sum(1 for b in self.left_bases if b.hp <= 0)
        right_destroyed = sum(1 for b in self.right_bases if b.hp <= 0)
        if left_destroyed >= self.bases_to_win:
            self.winner = "right"
        elif right_destroyed >= self.bases_to_win:
            self.winner = "left"

    def _find_closest_enemy(self, unit: Unit, enemies: List[Unit]) -> Unit | None:
        if not enemies:
            return None
        # 对面最近的一个（忽略隐身单位）
        # 增加 12 像素的身后容差，防止因高速更新导致瞬间“穿过去”后失去目标
        BACK_TOLERANCE = 12.0
        
        if unit.side == "left":
            filtered = [e for e in enemies if self._is_unit_targetable(unit, e)]
            if not filtered:
                return None
            best = None
            min_dist = 9999.0
            for e in filtered:
                dist = e.x - unit.x
                if dist >= -BACK_TOLERANCE:
                    if dist < min_dist:
                        min_dist = dist
                        best = e
            return best or filtered[-1]
        else:
            filtered = [e for e in enemies if self._is_unit_targetable(unit, e)]
            if not filtered:
                return None
            best = None
            min_dist = 9999.0
            for e in reversed(filtered):
                dist = unit.x - e.x
                if dist >= -BACK_TOLERANCE:
                    if dist < min_dist:
                        min_dist = dist
                        best = e
            return best or filtered[0]

    def _attack_phase(self, attackers: List[Unit], defenders: List[Unit], lane: int):
        for u in attackers:
            if not u.can_attack():
                continue
            effective_range = u.unit_type.range
            damage_mult = self.left_damage_mult if u.side == "left" else self.right_damage_mult
            if u.side == "left" and self.left_skill_damage_timer > 0.0:
                damage_mult *= self.left_skill_damage_mult
            elif u.side == "right" and self.right_skill_damage_timer > 0.0:
                damage_mult *= self.right_skill_damage_mult
            # 治疗单位逻辑（优先处理）
            if u.unit_type.is_healer:
                allies = attackers
                healed = False
                aoe_radius = max(0.0, u.unit_type.heal_aoe_radius)
                if aoe_radius > 0.0:
                    for a in allies:
                        if not a.alive:
                            continue
                        if abs(a.x - u.x) <= aoe_radius:
                            max_hp = a.max_hp if getattr(a, "max_hp", 0.0) > 0.0 else float(a.unit_type.hp)
                            if a.hp < max_hp:
                                a.heal(u.unit_type.heal_amount)
                                healed = True
                else:
                    target = None
                    min_ratio = 1.0
                    for a in allies:
                        if a is u or not a.alive:
                            continue
                        if abs(a.x - u.x) <= u.unit_type.range:
                            ratio = a.hp / max(1.0, float(a.unit_type.hp))
                            if ratio < min_ratio:
                                min_ratio = ratio
                                target = a
                    if target is not None and min_ratio < 1.0:
                        target.heal(u.unit_type.heal_amount)
                        healed = True
                if healed:
                    u.cooldown_timer = u.unit_type.cooldown * u.temp_cooldown_multiplier
                    u.time_since_last_attack = 0.0
                continue

            # 战线被动：爆发线对“单位伤害”的额外倍率（对称）
            # 注意：这里只影响单位之间的攻击/投射物，不影响“撞基地按当前HP扣血”的结算。
            if 0 <= lane < LANE_COUNT:
                if u.unit_type.is_ranged:
                    damage_mult *= self.lane_burst_ranged_vs_unit_mult[lane]
                else:
                    damage_mult *= self.lane_burst_melee_vs_unit_mult[lane]

            enemy = self._find_closest_enemy(u, defenders)
            if enemy is None:
                continue
            dist = abs(u.x - enemy.x)
            if u.unit_type.is_ranged:
                if dist <= effective_range:
                    base_pierce = max(0, u.unit_type.projectile_pierce)
                    bonus_pierce = 0
                    bonus_falloff = 0.0
                    if u.side == "left":
                        bonus_pierce = max(0, getattr(self, 'left_pierce_bonus', 0))
                        bonus_falloff = max(0.0, getattr(self, 'left_pierce_falloff', 0.0)) if bonus_pierce > 0 else 0.0
                    total_pierce = base_pierce + bonus_pierce
                    falloff_components: List[float] = []
                    if base_pierce > 0 and u.unit_type.projectile_falloff > 0.0:
                        falloff_components.append(min(0.95, max(0.0, u.unit_type.projectile_falloff)))
                    if bonus_falloff > 0.0:
                        falloff_components.append(min(0.95, max(0.0, bonus_falloff)))
                    damage_falloff = 0.0
                    if falloff_components:
                        remain = 1.0
                        for val in falloff_components:
                            remain *= (1.0 - val)
                        damage_falloff = 1.0 - remain
                    # 发射投射物（含 AOE 半径）
                    proj_visual = "default"
                    # S: 弓手, L: 冰弓 -> 箭矢
                    unit_key = getattr(u.unit_type, "key", "")
                    if unit_key in ["S", "L"]:
                        proj_visual = "arrow"
                    # D: 法师 -> 法球
                    elif unit_key in ["D"]:
                        proj_visual = "orb"
                    
                    self.projectiles.append(
                        Projectile(
                            x=u.x,
                            y=u.y,
                            speed=u.unit_type.projectile_speed,
                            damage=max(1, int(u.unit_type.damage * damage_mult * getattr(u, 'temp_damage_multiplier', 1.0))),
                            lane=lane,
                            side=u.side,
                            aoe_radius=(u.unit_type.aoe_radius if u.unit_type.is_aoe else 0.0),
                            slow_stack=u.unit_type.projectile_slow_stack,
                            slow_duration=u.unit_type.projectile_slow_duration + (self.left_frost_slow_extra if u.side == "left" else 0.0),
                            frost_stun_cap=u.unit_type.frost_stun_cap,
                            frost_stun_duration=u.unit_type.frost_stun_duration + (self.left_frost_stun_extra if u.side == "left" else 0.0),
                            pierce=total_pierce,
                            damage_falloff=damage_falloff,
                            owner=u,
                            visual_type=proj_visual,
                        )
                    )
                    u.time_since_last_attack = 0.0
                    u.cooldown_timer = u.unit_type.cooldown * u.temp_cooldown_multiplier
            else:
                # 近战：选择目标
                candidates = [
                    e
                    for e in defenders
                    if self._is_unit_targetable(u, e) and abs(e.x - u.x) <= effective_range
                ]
                if u.unit_type.prioritize_high_damage and u.unit_type.melee_stun_duration <= 0.0:
                    # 原逻辑：优先高伤
                    if u.unit_type.target_ranged_support_only:
                        candidates = [
                            e
                            for e in candidates
                            if (
                                e.unit_type.is_ranged
                                or e.unit_type.is_healer
                                or e.unit_type.is_buffer
                                or e.unit_type.intercept_radius > 0.0
                            )
                        ]
                    if candidates:
                        enemy = max(candidates, key=lambda e: e.unit_type.damage)
                        dist = abs(u.x - enemy.x)
                elif u.unit_type.melee_stun_duration > 0.0:
                    # 游击：优先未被眩晕的近战，其次已被眩晕近战，否则退化为最近目标
                    melee_unstun = [e for e in candidates if (not e.unit_type.is_ranged) and e.stunned_timer <= 0.0]
                    melee_stun = [e for e in candidates if (not e.unit_type.is_ranged) and e.stunned_timer > 0.0]
                    pick_pool = melee_unstun or melee_stun or candidates
                    if pick_pool:
                        enemy = min(pick_pool, key=lambda e: abs(e.x - u.x))
                        dist = abs(u.x - enemy.x)
                if enemy is None:
                    continue
                if dist <= effective_range:
                    # 刺客：若仅对远程/辅助出手，则没有符合条件目标时不攻击
                    if u.unit_type.target_ranged_support_only:
                        valid = (enemy.unit_type.is_ranged or enemy.unit_type.is_healer or enemy.unit_type.is_buffer or enemy.unit_type.intercept_radius > 0.0)
                        if not valid:
                            # 寻找符合条件的最近目标
                            pool = [
                                e
                                for e in candidates
                                if (
                                    e.unit_type.is_ranged
                                    or e.unit_type.is_healer
                                    or e.unit_type.is_buffer
                                    or e.unit_type.intercept_radius > 0.0
                                )
                            ]
                            if not pool:
                                continue
                            enemy = min(pool, key=lambda e: abs(e.x - u.x))
                            dist = abs(u.x - enemy.x)
                            if dist > effective_range:
                                continue
                    dmg = max(1.0, u.unit_type.damage * damage_mult * getattr(u, 'temp_damage_multiplier', 1.0))
                    
                    # 自爆兵逻辑：攻击即死亡（触发死亡爆炸），不造成直接近战伤害（除非 damage > 0）
                    if u.unit_type.suicide_on_attack:
                        u.alive = False
                        u.hp = 0
                        # 如果配置了近战伤害（damage > 0），这里依然可以造成一次伤害，
                        # 但通常设计为 0，仅靠死亡爆炸造成伤害。
                        # 为防万一，这里不 return，让后面的伤害逻辑继续跑（如果是 damage=0 自然无伤）
                    
                    # 长矛克制冲锋
                    if enemy.unit_type.is_charger and u.unit_type.bonus_vs_charge_mult > 1.0:
                        dmg *= u.unit_type.bonus_vs_charge_mult
                        if u.unit_type.charge_interrupt_stun > 0 and not enemy.unit_type.control_immune:
                            enemy.stunned_timer = max(enemy.stunned_timer, u.unit_type.charge_interrupt_stun)

                    # 是否本次使用 AOE（轻骑首击或自身即为 AOE 单位）
                    use_aoe = u.unit_type.is_aoe and u.unit_type.aoe_radius > 0.0
                    if u.unit_type.is_charger and not getattr(u, 'first_charge_done', False):
                        # 首次冲锋：强制 AOE
                        use_aoe = True

                    # 是否本次攻击触发击退：Rhino 常驻；轻骑仅首击
                    should_knockback = u.unit_type.knockback_factor > 0.0 and (
                        (not u.unit_type.is_charger) or (not getattr(u, 'first_charge_done', False))
                    )

                    hit_targets = []
                    if use_aoe:
                        for e in defenders:
                            if not e.alive:
                                continue
                            if abs(e.x - u.x) <= max(u.unit_type.aoe_radius, u.unit_type.range):
                                self._inflict_damage(e, dmg, "melee", u)
                                hit_targets.append(e)
                    else:
                        self._inflict_damage(enemy, dmg, "melee", u)
                        hit_targets.append(enemy)

                    # 轻骑：击退附带伤害（仅在触发击退的那一下）
                    if should_knockback:
                        kb_mult = max(0.0, getattr(u.unit_type, "knockback_damage_mult", 1.0))
                        extra = dmg * max(0.0, kb_mult - 1.0)
                        if extra > 0.0:
                            for t in hit_targets:
                                if t is not None and t.alive:
                                    self._inflict_damage(t, extra, "knockback", u)
                    u.time_since_last_attack = 0.0
                    # 游击：对近战目标施加眩晕（单体）
                    stun_duration = u.unit_type.melee_stun_duration
                    if stun_duration > 0.0 and not enemy.unit_type.is_ranged:
                        if not enemy.unit_type.control_immune:
                            enemy.stunned_timer = max(enemy.stunned_timer, stun_duration)
                        if u.unit_type.aoe_stun_radius > 0.0:
                            radius = u.unit_type.aoe_stun_radius
                            for extra in defenders:
                                if extra is enemy or not extra.alive:
                                    continue
                                if abs(extra.x - enemy.x) <= radius and not extra.unit_type.control_immune:
                                    extra.stunned_timer = max(extra.stunned_timer, stun_duration)

                    # 击退逻辑：Rhino 常驻AOE；轻骑仅首击AOE
                    if should_knockback:
                        # 计算击退力度（基础×单位系数×全局系数×玩家加成）
                        base_speed = u.unit_type.speed * u.temp_speed_multiplier
                        factor = u.unit_type.knockback_factor
                        if u.side == "left":
                            factor *= (1.0 + getattr(self, 'left_knockback_bonus', 0.0))
                        k = base_speed * factor * 0.50

                        # 单位专属倍率：Rhino 2/3；轻骑首击 6.3x（在当前基础再翻倍）
                        if u.unit_type.is_charger and not getattr(u, 'first_charge_done', False):
                            unit_mult = 6.3
                        else:
                            # 非冲锋（Rhino 类）
                            unit_mult = 2.0 / 3.0
                        k *= unit_mult

                        # 选择击退目标：Rhino AOE；轻骑首击 AOE；否则单体（安全起见）
                        radius = max(u.unit_type.aoe_radius, u.unit_type.range)
                        kb_targets = []
                        if (not u.unit_type.is_charger) or (u.unit_type.is_charger and not getattr(u, 'first_charge_done', False)):
                            kb_targets = [e for e in defenders if abs(e.x - u.x) <= radius]
                            if not kb_targets and enemy is not None:
                                kb_targets = [enemy]
                        else:
                            kb_targets = [enemy] if enemy is not None else []

                        # 应用击退
                        if u.side == "left":
                            for e in kb_targets:
                                e.x += k
                        else:
                            for e in kb_targets:
                                e.x -= k

                        # 攻击者同步前进相同距离，保持接触身位
                        if kb_targets:
                            if u.side == "left":
                                u.x += k
                            else:
                                u.x -= k

                        if kb_targets and u.unit_type.knockback_stun_threshold > 0:
                            for kb_target in kb_targets:
                                self._register_knockback(u, kb_target)

                    # 轻骑标记首击已用
                    if u.unit_type.is_charger and not getattr(u, 'first_charge_done', False):
                        u.first_charge_done = True

                    u.cooldown_timer = u.unit_type.cooldown * u.temp_cooldown_multiplier

    def _update_unit_animations(self, left_list: List[Unit], right_list: List[Unit], dt: float):
        """更新所有单位的动画状态"""
        for unit in left_list + right_list:
            if not unit.alive:
                continue
            
            # 判断是否在移动（通过比较当前位置和上次位置）
            is_moving = abs(unit.x - unit.last_x) > 0.1
            unit.last_x = unit.x
            
            # 判断是否在攻击（距离上次攻击时间小于动画时长）
            attack_animation_duration = getattr(unit, 'attack_animation_duration', 0.3)
            is_attacking = unit.time_since_last_attack < attack_animation_duration
            
            # 更新动画状态
            if is_attacking:
                unit.animation_state = "attack"
                unit.animation_timer = unit.time_since_last_attack
            elif is_moving:
                unit.animation_state = "walk"
                unit.animation_timer += dt
            else:
                unit.animation_state = "idle"
                unit.animation_timer += dt

    def _tick_particles(self, dt: float):
        for p in list(self.particles):
            p.timer += dt
            # 物理运动更新
            if p.vx != 0 or p.vy != 0:
                p.x += p.vx * dt
                p.y += p.vy * dt
                
            if p.timer >= p.duration:
                self.particles.remove(p)
            else:
                # 半径动画
                progress = p.timer / p.duration
                
                if p.shape == "ring":
                    # 环形：快速扩散
                    p.radius = p.max_radius * (0.2 + 0.8 * math.pow(progress, 0.5))
                elif p.shape == "line":
                    # 线条：可能会缩短
                    pass
                else:
                    # 圆形/方形：默认线性增长或呼吸
                    p.radius = p.max_radius * (0.3 + 0.7 * math.pow(progress, 0.5))

    def spawn_explosion_effect(self, x: float, y: float, radius: float, color: Tuple[int, int, int] = (255, 140, 0)):
        # 主爆炸波 (Shockwave)
        self.particles.append(Particle(
            x=x,
            y=y,
            radius=5.0,
            timer=0.0,
            duration=0.4,
            max_radius=radius * 1.2,
            color=color,
            shape="ring",
            width=3
        ))
        # 核心闪光 (Core Flash)
        self.particles.append(Particle(
            x=x,
            y=y,
            radius=5.0,
            timer=0.0,
            duration=0.2,
            max_radius=radius * 0.6,
            color=(255, 255, 200),
            shape="circle"
        ))
        # 飞溅碎片 (Debris)
        for _ in range(6):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(50, 150)
            self.particles.append(Particle(
                x=x,
                y=y,
                radius=random.uniform(2, 4),
                timer=0.0,
                duration=random.uniform(0.3, 0.6),
                max_radius=0, # 不用
                color=color,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                shape="square"
            ))

    def spawn_hit_effect(self, x: float, y: float, direction_sign: int, color: Tuple[int, int, int] = (255, 255, 255)):
        # 命中溅射：向反方向飞溅
        for _ in range(3):
            angle = random.uniform(-0.5, 0.5) # 弧度
            # 如果原本向右打(direction_sign=1)，粒子向左飞(-1)
            base_dir = -direction_sign 
            vx_base = base_dir * random.uniform(50, 120)
            vy_base = random.uniform(-50, 50)
            self.particles.append(Particle(
                x=x,
                y=y,
                radius=random.uniform(1.5, 3.0),
                timer=0.0,
                duration=0.25,
                max_radius=0,
                color=color,
                vx=vx_base,
                vy=vy_base,
                shape="line" # 火花/碎片线条
            ))

    # 外部驱动入口
    def update(self, dt: float):
        self.recent_kills = 0
        # 更新战斗计时器（仅在战斗未结束时）
        if self.winner is None:
            self.battle_time += dt
        if self.winner:
            return
        self._tick_economy(dt)
        self._tick_mirror_script()
        if not self.disable_ai:
            self._ai_step(dt)
        self._combat_step(dt)
        self._tick_particles(dt)

    def reset(self):
        self.__init__(
            list(self.player_order_keys),
            list(self.left_skill_types),
            list(self.ai_order_keys),
            list(self.right_skill_types),
            self.ai_interval_mult,
            self.boons,
            modifiers=self.modifiers,
            player_unit_levels=dict(self.left_unit_levels),
        )

    # 技能：全线出兵（按当前选择兵种），不消耗资源
    def can_cast_skill(self, side: str, slot: int | None = None) -> bool:
        if self.winner:
            return False
        skill_key, cost = self._get_skill_entry(side, slot)
        if not skill_key:
            return False
        if side == "left" and self.left_infinite_skill:
            return True
        if side == "left":
            # 祝福：战术大师 - 技能消耗资源而非击杀数
            if self.tactical_master_mode:
                return self.left.resource >= cost
            return self.left_kill_resource >= cost
        return self.right_kill_resource >= cost

    def _resolve_skill_lane(self, side: str, skill_type: str) -> int:
        cfg = SKILLS.get(skill_type)
        if not cfg or cfg.get("target") != "lane":
            return 0
        if side == "left":
            return max(0, min(LANE_COUNT - 1, self.selected_lane))
        if skill_type == "guardian":
            lane_source = self.right_units if side == "right" else self.left_units
        else:
            lane_source = self.left_units if side == "right" else self.right_units
        counts = [sum(1 for u in lane_units if u.alive) for lane_units in lane_source]
        best_lane = 0
        if counts:
            best_lane = max(range(len(counts)), key=lambda idx: counts[idx])
        return best_lane

    def _spawn_boom_salvo(self, side: str, lane: int):
        base = self.left_bases[lane] if side == "left" else self.right_bases[lane]
        start_x = base.x + base.width / 2 + 8 if side == "left" else base.x - base.width / 2 - 8
        lane_y = self.lane_y[lane]
        flight_y = lane_y - 18
        enemy_lists = self.right_units if side == "left" else self.left_units
        enemy_base = self.right_bases[lane] if side == "left" else self.left_bases[lane]
        alive_enemies = [u for u in enemy_lists[lane] if u.alive]
        if alive_enemies:
            if side == "left":
                front = max(u.x for u in alive_enemies)
                limit = enemy_base.x - 60
                target_x_base = min(front, limit)
            else:
                front = min(u.x for u in alive_enemies)
                limit = enemy_base.x + 60
                target_x_base = max(front, limit)
        else:
            if side == "left":
                target_x_base = enemy_base.x - 110
            else:
                target_x_base = enemy_base.x + 110

        spread = 24.0
        for idx in range(3):
            offset = (idx - 1) * spread
            target_x = target_x_base + offset
            if side == "left":
                target_x = min(target_x, enemy_base.x - 40)
            else:
                target_x = max(target_x, enemy_base.x + 40)
            missile = SkillMissile(
                side=side,
                lane=lane,
                start_x=start_x,
                start_y=flight_y,
                target_x=target_x,
                target_y=flight_y,
                speed=820.0,
                delay=0.12 * idx,
                arc_height=0.0,
                aoe_radius=44.0,
            )
            self.skill_missiles.append(missile)

    def _resolve_boom_explosion(self, missile: SkillMissile):
        targets = self.right_units if missile.side == "left" else self.left_units
        radius = max(0.0, missile.aoe_radius)
        for unit in list(targets[missile.lane]):
            if unit.alive and abs(unit.x - missile.x) <= radius:
                self._inflict_damage(unit, 150, "skill", None, allow_reflect=True)
        # 炸点爆炸特效
        self.spawn_explosion_effect(missile.x, missile.y, max(36.0, radius), (255, 140, 80))

    def cast_skill(self, side: str, slot: int | None = None):
        if not self.can_cast_skill(side, slot):
            return False
        skill_type, cost = self._get_skill_entry(side, slot)
        if not skill_type:
            return False
        cfg = SKILLS.get(skill_type)
        if not cfg:
            return False
        lane = self._resolve_skill_lane(side, skill_type)
        lane = max(0, min(LANE_COUNT - 1, lane))
        allies = self.left_units if side == "left" else self.right_units
        enemies = self.right_units if side == "left" else self.left_units

        if skill_type == "spawn":
            key = self.player_order_keys[self.selected_unit_idx] if side == "left" else random.choice(self.ai_order_keys)
            for lane_idx in range(LANE_COUNT):
                self.spawn_unit_free(side, lane_idx, key)
                # 出兵冲击波（基地口）
                base = self.left_bases[lane_idx] if side == "left" else self.right_bases[lane_idx]
                self.spawn_explosion_effect(base.x, self.lane_y[lane_idx], 26, (140, 220, 255))
        elif skill_type == "frost_ray":
            # 冰霜射线视觉：蓝色光束
            base_y = self.lane_y[lane]
            # 生成一排粒子模拟光束
            start_x = self.left_bases[lane].x if side == "left" else self.right_bases[lane].x
            end_x = self.right_bases[lane].x if side == "left" else self.left_bases[lane].x
            step = 20
            steps = int(abs(end_x - start_x) / step)
            direction = 1 if side == "left" else -1
            
            for i in range(steps):
                px = start_x + i * step * direction
                self.particles.append(Particle(
                    x=px, y=base_y, radius=random.uniform(6, 12), 
                    timer=0, duration=0.5, color=(100, 220, 255), max_radius=0,
                    shape="square", vx=0, vy=0
                ))
                # 少量飞溅
                if random.random() < 0.3:
                    self.particles.append(Particle(
                        x=px, y=base_y + random.uniform(-10, 10), radius=3, 
                        timer=0, duration=0.8, color=(200, 240, 255), max_radius=0,
                        shape="line", vx=random.uniform(-20, 20), vy=random.uniform(-50, 50)
                    ))

            for u in enemies[lane]:
                if not u.unit_type.control_immune:
                    u.stunned_timer = max(u.stunned_timer, 4.0)
        elif skill_type == "death_ray":
            # 死亡射线视觉：红色混乱光束
            base_y = self.lane_y[lane]
            start_x = self.left_bases[lane].x if side == "left" else self.right_bases[lane].x
            end_x = self.right_bases[lane].x if side == "left" else self.left_bases[lane].x
            step = 15
            steps = int(abs(end_x - start_x) / step)
            direction = 1 if side == "left" else -1
            
            for i in range(steps):
                px = start_x + i * step * direction
                # 主光束粒子
                self.particles.append(Particle(
                    x=px, y=base_y + random.uniform(-5, 5), radius=random.uniform(4, 8), 
                    timer=0, duration=0.4, color=(255, 50, 50), max_radius=0,
                    shape="circle", vx=0, vy=0
                ))
                # 混乱线条
                if random.random() < 0.5:
                    self.particles.append(Particle(
                        x=px, y=base_y, radius=random.uniform(2, 5), 
                        timer=0, duration=0.6, color=(200, 0, 0), max_radius=0,
                        shape="line", vx=random.uniform(-100, 100), vy=random.uniform(-100, 100)
                    ))

            for u in enemies[lane]:
                u.alive = False
                u.hp = 0
                # 死亡爆炸效果
                self.spawn_explosion_effect(u.x, u.y, 30, (200, 50, 50))
        elif skill_type == "boom":
            self._spawn_boom_salvo(side, lane)
        elif skill_type == "guardian":
            for u in allies[lane]:
                shield = u.unit_type.hp * 0.5
                u.shield_hp = max(0.0, u.shield_hp) + shield
                u.shield_timer = float("inf")
                # 护盾涟漪
                self.particles.append(Particle(
                    x=u.x, y=u.y, radius=6, timer=0, duration=0.35,
                    max_radius=30, color=(120, 220, 255), shape="ring", width=3
                ))
                self.particles.append(Particle(
                    x=u.x, y=u.y, radius=4, timer=0, duration=0.5,
                    max_radius=10, color=(200, 255, 255), shape="circle"
                ))
        elif skill_type == "black_hole":
            mid = (self.left_bases[lane].x + self.right_bases[lane].x) / 2.0
            base_y = self.lane_y[lane]
            
            # 黑洞特效：吸入粒子
            for _ in range(20):
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(20, 60)
                px = mid + math.cos(angle) * dist
                py = base_y + math.sin(angle) * dist
                # 速度指向中心
                speed = random.uniform(60, 120)
                vx = -math.cos(angle) * speed
                vy = -math.sin(angle) * speed
                
                self.particles.append(Particle(
                    x=px, y=py, radius=random.uniform(2, 4),
                    timer=0, duration=0.6, color=(100, 0, 150), max_radius=0,
                    shape="square", vx=vx, vy=vy
                ))
            # 中心奇点
            self.particles.append(Particle(
                x=mid, y=base_y, radius=10,
                timer=0, duration=0.8, color=(0, 0, 0), max_radius=20,
                shape="ring", width=2, vx=0, vy=0
            ))
            # 闪光
            self.particles.append(Particle(
                x=mid, y=base_y, radius=15,
                timer=0, duration=0.2, color=(200, 100, 255), max_radius=5,
                shape="circle", vx=0, vy=0
            ))

            for u in enemies[lane]:
                u.x = mid
                if not u.unit_type.control_immune:
                    u.rooted_timer = max(u.rooted_timer, 3.0)
        elif skill_type == "windfall":
            player = self.left if side == "left" else self.right
            cap = getattr(self, 'left_res_cap', MAX_RESOURCE) if side == "left" else MAX_RESOURCE
            player.resource = min(cap, player.resource + 300)
            # 金币飞溅
            for _ in range(24):
                px = 120 + random.uniform(-60, 60)
                py = 70 + random.uniform(-20, 20)
                vx = random.uniform(-30, 30)
                vy = random.uniform(20, 80)
                self.particles.append(Particle(
                    x=px, y=py, radius=random.uniform(2, 4), timer=0, duration=0.8,
                    max_radius=0, color=(255, 210, 80), shape="square", vx=vx, vy=vy
                ))
            self.spawn_explosion_effect(140, 80, 28, (255, 220, 120))
        elif skill_type == "gotcha":
            if side == "left":
                self.left_base_invuln_timer[lane] = max(self.left_base_invuln_timer[lane], 5.0)
                base_x = self.left_bases[lane].x
                base_y = self.lane_y[lane]
                self.spawn_explosion_effect(base_x, base_y, 34, (100, 200, 255))
                for u in enemies[lane]:
                    if u.x <= base_x + 24:
                        u.hp = 0
                        u.alive = False
            else:
                self.right_base_invuln_timer[lane] = max(self.right_base_invuln_timer[lane], 5.0)
                base_x = self.right_bases[lane].x
                base_y = self.lane_y[lane]
                self.spawn_explosion_effect(base_x, base_y, 34, (255, 120, 180))
                for u in enemies[lane]:
                    if u.x >= base_x - 24:
                        u.hp = 0
                        u.alive = False
        elif skill_type == "origei":
            if side == "left":
                self.left_skill_damage_mult = 1.5
                self.left_skill_damage_timer = max(self.left_skill_damage_timer, 8.0)
                self.left_skill_speed_mult = 1.5
                self.left_skill_speed_timer = max(self.left_skill_speed_timer, 8.0)
                color = (120, 220, 255)
            else:
                self.right_skill_damage_mult = 1.5
                self.right_skill_damage_timer = max(self.right_skill_damage_timer, 8.0)
                self.right_skill_speed_mult = 1.5
                self.right_skill_speed_timer = max(self.right_skill_speed_timer, 8.0)
                color = (255, 140, 120)
            # 全军强化冲击波
            mid_x = SCREEN_WIDTH / 2
            mid_y = SCREEN_HEIGHT * 0.45
            self.spawn_explosion_effect(mid_x, mid_y, 80, color)
            for lane_idx in range(LANE_COUNT):
                base = self.left_bases[lane_idx] if side == "left" else self.right_bases[lane_idx]
                self.particles.append(Particle(
                    x=base.x, y=self.lane_y[lane_idx], radius=6, timer=0, duration=0.45,
                    max_radius=46, color=color, shape="ring", width=3
                ))
                # 跑道粒子
                for _ in range(8):
                    self.particles.append(Particle(
                        x=base.x, y=self.lane_y[lane_idx], radius=3, timer=0, duration=0.5,
                        max_radius=0, color=color, shape="line",
                        vx=random.uniform(60, 140) * (1 if side == "left" else -1),
                        vy=random.uniform(-40, 40)
                    ))
        else:
            return False
        if side == "left":
            if not self.left_infinite_skill:
                # 祝福：战术大师 - 技能消耗资源而非击杀数
                if self.tactical_master_mode:
                    self.left.resource = max(0, self.left.resource - cost)
                else:
                    self.left_kill_resource = max(0, self.left_kill_resource - cost)
        else:
            self.right_kill_resource = max(0, self.right_kill_resource - cost)
        return True

    # 镜像Boss：强制施法（不检查技能栏/资源/CD，直接按指定lane生效）
    def cast_skill_forced(self, side: str, skill_type: str, lane: int, spawn_unit_key: str | None = None) -> bool:
        if self.winner:
            return False
        if not skill_type:
            return False
        cfg = SKILLS.get(skill_type)
        if not cfg:
            return False
        lane = max(0, min(LANE_COUNT - 1, int(lane)))
        allies = self.left_units if side == "left" else self.right_units
        enemies = self.right_units if side == "left" else self.left_units

        if skill_type == "spawn":
            if spawn_unit_key:
                key = spawn_unit_key
            else:
                key = self.player_order_keys[self.selected_unit_idx] if side == "left" else (self.ai_order_keys[0] if self.ai_order_keys else None)
            if not key:
                return False
            for lane_idx in range(LANE_COUNT):
                self.spawn_unit_free(side, lane_idx, key)
                base = self.left_bases[lane_idx] if side == "left" else self.right_bases[lane_idx]
                self.spawn_explosion_effect(base.x, self.lane_y[lane_idx], 26, (140, 220, 255))
        elif skill_type == "frost_ray":
            base_y = self.lane_y[lane]
            start_x = self.left_bases[lane].x if side == "left" else self.right_bases[lane].x
            end_x = self.right_bases[lane].x if side == "left" else self.left_bases[lane].x
            step = 20
            steps = int(abs(end_x - start_x) / step)
            direction = 1 if side == "left" else -1
            for i in range(steps):
                px = start_x + i * step * direction
                self.particles.append(Particle(
                    x=px, y=base_y, radius=random.uniform(6, 12),
                    timer=0, duration=0.5, color=(100, 220, 255), max_radius=0,
                    shape="square", vx=0, vy=0
                ))
                if random.random() < 0.3:
                    self.particles.append(Particle(
                        x=px, y=base_y + random.uniform(-10, 10), radius=3,
                        timer=0, duration=0.8, color=(200, 240, 255), max_radius=0,
                        shape="line", vx=random.uniform(-20, 20), vy=random.uniform(-50, 50)
                    ))
            for u in enemies[lane]:
                if not u.unit_type.control_immune:
                    u.stunned_timer = max(u.stunned_timer, 4.0)
        elif skill_type == "death_ray":
            base_y = self.lane_y[lane]
            start_x = self.left_bases[lane].x if side == "left" else self.right_bases[lane].x
            end_x = self.right_bases[lane].x if side == "left" else self.left_bases[lane].x
            step = 15
            steps = int(abs(end_x - start_x) / step)
            direction = 1 if side == "left" else -1
            for i in range(steps):
                px = start_x + i * step * direction
                self.particles.append(Particle(
                    x=px, y=base_y + random.uniform(-5, 5), radius=random.uniform(4, 8),
                    timer=0, duration=0.4, color=(255, 50, 50), max_radius=0,
                    shape="circle", vx=0, vy=0
                ))
                if random.random() < 0.5:
                    self.particles.append(Particle(
                        x=px, y=base_y, radius=random.uniform(2, 5),
                        timer=0, duration=0.6, color=(200, 0, 0), max_radius=0,
                        shape="line", vx=random.uniform(-100, 100), vy=random.uniform(-100, 100)
                    ))
            for u in enemies[lane]:
                u.alive = False
                u.hp = 0
                self.spawn_explosion_effect(u.x, u.y, 30, (200, 50, 50))
        elif skill_type == "boom":
            self._spawn_boom_salvo(side, lane)
        elif skill_type == "guardian":
            for u in allies[lane]:
                shield = u.unit_type.hp * 0.5
                u.shield_hp = max(0.0, u.shield_hp) + shield
                u.shield_timer = float("inf")
                self.particles.append(Particle(
                    x=u.x, y=u.y, radius=6, timer=0, duration=0.35,
                    max_radius=30, color=(120, 220, 255), shape="ring", width=3
                ))
                self.particles.append(Particle(
                    x=u.x, y=u.y, radius=4, timer=0, duration=0.5,
                    max_radius=10, color=(200, 255, 255), shape="circle"
                ))
        elif skill_type == "black_hole":
            mid = (self.left_bases[lane].x + self.right_bases[lane].x) / 2.0
            base_y = self.lane_y[lane]
            for _ in range(20):
                angle = random.uniform(0, 2 * math.pi)
                dist = random.uniform(20, 60)
                px = mid + math.cos(angle) * dist
                py = base_y + math.sin(angle) * dist
                speed = random.uniform(60, 120)
                vx = -math.cos(angle) * speed
                vy = -math.sin(angle) * speed
                self.particles.append(Particle(
                    x=px, y=py, radius=random.uniform(2, 4),
                    timer=0, duration=0.6, color=(100, 0, 150), max_radius=0,
                    shape="square", vx=vx, vy=vy
                ))
            self.particles.append(Particle(
                x=mid, y=base_y, radius=10,
                timer=0, duration=0.8, color=(0, 0, 0), max_radius=20,
                shape="ring", width=2, vx=0, vy=0
            ))
            self.particles.append(Particle(
                x=mid, y=base_y, radius=15,
                timer=0, duration=0.2, color=(200, 100, 255), max_radius=5,
                shape="circle", vx=0, vy=0
            ))
            for u in enemies[lane]:
                u.x = mid
                if not u.unit_type.control_immune:
                    u.rooted_timer = max(u.rooted_timer, 3.0)
        elif skill_type == "windfall":
            player = self.left if side == "left" else self.right
            cap = getattr(self, 'left_res_cap', MAX_RESOURCE) if side == "left" else MAX_RESOURCE
            player.resource = min(cap, player.resource + 300)
            for _ in range(24):
                px = 120 + random.uniform(-60, 60)
                py = 70 + random.uniform(-20, 20)
                vx = random.uniform(-30, 30)
                vy = random.uniform(20, 80)
                self.particles.append(Particle(
                    x=px, y=py, radius=random.uniform(2, 4), timer=0, duration=0.8,
                    max_radius=0, color=(255, 210, 80), shape="square", vx=vx, vy=vy
                ))
            self.spawn_explosion_effect(140, 80, 28, (255, 220, 120))
        elif skill_type == "gotcha":
            if side == "left":
                self.left_base_invuln_timer[lane] = max(self.left_base_invuln_timer[lane], 5.0)
                base_x = self.left_bases[lane].x
                base_y = self.lane_y[lane]
                self.spawn_explosion_effect(base_x, base_y, 34, (100, 200, 255))
                for u in enemies[lane]:
                    if u.x <= base_x + 24:
                        u.hp = 0
                        u.alive = False
            else:
                self.right_base_invuln_timer[lane] = max(self.right_base_invuln_timer[lane], 5.0)
                base_x = self.right_bases[lane].x
                base_y = self.lane_y[lane]
                self.spawn_explosion_effect(base_x, base_y, 34, (255, 120, 180))
                for u in enemies[lane]:
                    if u.x >= base_x - 24:
                        u.hp = 0
                        u.alive = False
        elif skill_type == "origei":
            if side == "left":
                self.left_skill_damage_mult = 1.5
                self.left_skill_damage_timer = max(self.left_skill_damage_timer, 8.0)
                self.left_skill_speed_mult = 1.5
                self.left_skill_speed_timer = max(self.left_skill_speed_timer, 8.0)
                color = (120, 220, 255)
            else:
                self.right_skill_damage_mult = 1.5
                self.right_skill_damage_timer = max(self.right_skill_damage_timer, 8.0)
                self.right_skill_speed_mult = 1.5
                self.right_skill_speed_timer = max(self.right_skill_speed_timer, 8.0)
                color = (255, 140, 120)
            mid_x = SCREEN_WIDTH / 2
            mid_y = SCREEN_HEIGHT * 0.45
            self.spawn_explosion_effect(mid_x, mid_y, 80, color)
            for lane_idx in range(LANE_COUNT):
                base = self.left_bases[lane_idx] if side == "left" else self.right_bases[lane_idx]
                self.particles.append(Particle(
                    x=base.x, y=self.lane_y[lane_idx], radius=6, timer=0, duration=0.45,
                    max_radius=46, color=color, shape="ring", width=3
                ))
                for _ in range(8):
                    self.particles.append(Particle(
                        x=base.x, y=self.lane_y[lane_idx], radius=3, timer=0, duration=0.5,
                        max_radius=0, color=color, shape="line",
                        vx=random.uniform(60, 140) * (1 if side == "left" else -1),
                        vy=random.uniform(-40, 40)
                    ))
        else:
            return False
        return True

    def spawn_unit_free(self, side: str, lane: int, key: str):
        if key not in UNIT_TYPES or not (0 <= lane < LANE_COUNT):
            return False
        unit_type = self._get_unit_type_with_level(side, key)
        if unit_type is None:
            return False
        y = self.lane_y[lane]
        if side == "left":
            base = self.left_bases[lane]
            x = base.x + base.width / 2 + unit_type.radius + 2
        else:
            base = self.right_bases[lane]
            x = base.x - base.width / 2 - unit_type.radius - 2
        hp_mult = self.left_hp_mult if side == "left" else 1.0
        max_hp = float(unit_type.hp) * hp_mult * self.lane_hp_mult[lane]
        unit = Unit(
            unit_type=unit_type,
            side=side,
            lane=lane,
            x=float(x),
            y=y,
            hp=max_hp,
            max_hp=max_hp,
            attack_animation_duration=unit_type.attack_animation_duration,
        )
        if side == "left":
            self.left_units[lane].append(unit)
        else:
            self.right_units[lane].append(unit)
        return True
