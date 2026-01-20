from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .campaign import CampaignState


def _stable_u32(text: str) -> int:
    """Stable 32-bit unsigned int derived from text (跨进程稳定，不受 PYTHONHASHSEED 影响)."""
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="little", signed=False)


@dataclass
class OneShotState:
    """一次性券/惩罚状态（M4/M5 会用到，M1 先集中收口字段）。"""

    next_shop_free_refresh_disabled: bool = False
    next_shop_free_refresh_bonus: int = 0
    next_shop_price_mult_once: float = 1.0
    # 新增：S3B 两次购买半价次数
    next_shop_discount_count: int = 0
    next_combo_reroll_once: bool = False
    next_combo_bias_once: bool = False
    # 新增：S2B Combo 候选位加成（如 4 选 1）
    next_combo_slot_bonus: int = 0


@dataclass
class ForgeState:
    """锻造相关状态（攻防分离版本）。"""

    offense_level_by_unit: Dict[str, int] = field(default_factory=dict)  # unit_key -> 攻击等级 0..5
    defense_level_by_unit: Dict[str, int] = field(default_factory=dict)  # unit_key -> 防御等级 0..5
    spawn_count_by_unit: Dict[str, int] = field(default_factory=dict)  # unit_key -> 出兵次数（用于默认目标）
    last_target_unit: Optional[str] = None
    last_direction: Optional[str] = None  # 上一次锻造的方向


@dataclass
class PrisonerMemoryState:
    """俘虏“记忆”状态（M3 会用到，M1 先收口）。"""

    joined_once: Dict[str, bool] = field(default_factory=dict)  # unit_key -> 是否曾归顺过（用于权重×2）
    executed_once: Dict[str, bool] = field(default_factory=dict)  # unit_key -> 是否曾处决过（用于权重×0）


@dataclass
class ComboState:
    """Combo 状态（M4 会实现，M1 先集中）。"""

    selected_cards: List[str] = field(default_factory=list)
    triggered_shop_once: bool = False
    triggered_event_once: bool = False
    triggered_elite_once: bool = False


@dataclass
class CampaignRunState:
    """
    战役 Run 的所有“局内状态”集中在这里（M1目标）：
    - 让 main.py 不再散落大量 campaign_* 局部变量
    - 为 M2/M5 的结算链与存档打基础（seed/一次性券/经营状态）
    """

    # === 核心进度/地图 ===
    state: Optional[CampaignState] = None
    cursor_node_id: Optional[int] = None
    current_node_id: Optional[int] = None
    map_scroll: float = 0.0

    # === 经营/展示信息 ===
    message: str = ""
    event_message: str = ""

    # === 队伍/成长 ===
    units: List[str] = field(default_factory=list)
    unit_levels: Dict[str, int] = field(default_factory=dict)
    skills: List[str] = field(default_factory=list)
    # 开局第1槽（用于“弱势开局补偿”等长期跟踪，不随队伍变动而改变）
    primary_unit: str = ""

    # 旧系统（boon）M2 会替换掉；M1 先保留以不破坏现有可玩性
    boons: Dict[str, int] = field(default_factory=dict)

    # === 商店 ===
    shop_items: List[dict] = field(default_factory=list)
    shop_cursor: int = 0
    shop_message: str = ""
    shop_node_id: Optional[int] = None
    # 进过多少次商店（用于"弱势开局：第一次商店全场折扣"等一次性规则）
    shops_visited: int = 0
    # 当前商店的价格乘区（保证刷新也沿用同一 price_mult）
    shop_price_mult_current: float = 1.0
    shop_free_refresh_left: int = 0
    shop_refresh_paid_count: int = 0
    shop_donated: bool = False
    shop_robbery_confirm: bool = False
    # 本周目抢劫次数：用于“商店格子永久减少”（通过随机封锁实现）
    shop_robbery_count: int = 0
    
    # === 事件 ===
    # 进过多少次事件（用于 Combo 触发条件）
    events_visited: int = 0
    # 新增：用于处理需要"二次点击选择"的事件上下文和动作
    event_pending_action: Optional[str] = None  # "upgrade_2", "forge_3", "delete_unit", "delete_skill" 等
    event_pending_target: Optional[str] = None  # 记录第一个选中的目标（用于 D3A）

    # 购买锻造器：临时把锻造界面当作"服务"，结束后回到 shop（而不是进入俘虏）
    forge_return_mode: str = "campaign_prisoners"
    forge_force_free_retarget: bool = False  # 本次锻造是否免改锻费（商店"超级锻造器"）

    # === 奖励三选一（旧链路）===
    reward_options: List[str] = field(default_factory=list)
    reward_idx: int = 0

    # === M2：战斗胜利结算链（主干） ===
    postbattle_summary: str = ""  # “胜利结算页”展示文本（含金币/时间奖励等）
    postbattle_node_type: str = ""  # 本场战斗节点类型（combat/elite/boss）
    pending_finish_run: bool = False  # 若为 boss 胜利，结算链走完进入 victory

    blessing_taken: bool = False  # 全局仅一次
    blessing_options: List[str] = field(default_factory=list)  # 占位：4选1候选
    blessing_idx: int = 0
    blessing_selected: Optional[str] = None

    # === M4.1：里程碑式发放计数/标记 ===
    nonbattle_cleared_count: int = 0  # 已完成的非战斗节点次数（shop/event/rest/其他非战斗）
    elite_victory_once: bool = False  # 是否曾战胜过精英（用于第3张 Combo）
    weak_start_combo_given: bool = False  # 弱兵种开局是否已提前获得Combo1（用于跳过第3场战斗后的Combo1）
    
    # 记录哪些里程碑已经发放过，支持不按顺序触发
    milestone_battle3_claimed: bool = False
    milestone_shop_event_claimed: bool = False
    milestone_elite_win_claimed: bool = False

    # === M3：锻造/俘虏 交互状态 ===
    last_battle_enemy_types: List[str] = field(default_factory=list)  # 本关敌方“实际出过的兵种种类集合”T（去重后存列表）
    last_battle_ai_types: List[str] = field(default_factory=list)  # 本关敌方 AI 池（fallback：若实际出兵为空）

    forge_selected_unit: Optional[str] = None
    forge_selected_dir: str = "offense"  # "offense" | "defense"
    forge_result_message: str = ""
    forge_done: bool = False  # 本关锻造是否已执行（防误触重复锻造）
    forge_default_unit: Optional[str] = None
    forge_default_reason: str = ""

    prisoner_queue: List[str] = field(default_factory=list)  # 本关俘虏列表（单位key）
    prisoner_idx: int = 0  # 当前处理第几个俘虏
    prisoner_action_idx: int = 0  # 0归顺/1处决/2放归
    prisoner_message: str = ""
    prisoners_inited: bool = False  # 避免“先显示无俘虏，按一下又出现”的视觉/逻辑错位

    # === 战斗继承状态 ===
    saved_left_base_hps: Optional[List[float]] = None

    # === 通关统计 ===
    total_time: float = 0.0
    battle_times: List[float] = field(default_factory=list)
    last_battle_time: float = 0.0

    # === 镜像Boss（只记录Boss战）===
    mirror_snapshot: Dict[str, object] = field(default_factory=dict)
    mirror_script: List[dict] = field(default_factory=list)
    mirror_last_updated: float = 0.0
    
    # === 难度/惩罚机制 ===
    timeout_penalty_coeff: float = 1.0  # 战斗超时累积惩罚系数（敌方强化）
    timeout_win: bool = False  # 本场战斗是否因超时判胜（用于镜像Boss刷新抑制）

    # === 新体系占位（M1 先收口字段） ===
    reputation: int = 0
    oneshot: OneShotState = field(default_factory=OneShotState)
    forge: ForgeState = field(default_factory=ForgeState)
    prisoners: PrisonerMemoryState = field(default_factory=PrisonerMemoryState)
    combo: ComboState = field(default_factory=ComboState)
    battle_gold_mult: float = 1.0  # Combo/祝福可改
    prisoner_gold_mult: float = 1.0  # 影响处决/放归金币收益

    # === M4：Combo 选择界面状态 ===
    combo_options: List[str] = field(default_factory=list)
    combo_idx: int = 0
    combo_context: str = ""  # "shop" | "event" | "elite"
    combo_pending_node_id: Optional[int] = None  # elite 时用于回到战斗入口

    # === M4：事件 A/B 界面状态 ===
    event_template_id: str = ""
    event_title: str = ""
    event_desc: str = ""
    event_option_a: str = ""
    event_option_b: str = ""
    event_choice_idx: int = 0  # 0=A, 1=B
    event_node_id: Optional[int] = None
    recent_event_templates: List[str] = field(default_factory=list)  # 轻量防重复（最近2次）

    # === RNG/seed（为 M5 存档做准备）===
    seed: int = 0
    rng_step: int = 0

    def ensure_seed(self) -> int:
        if self.seed == 0:
            self.seed = random.randint(1, 2**31 - 1)
        return self.seed

    def fork_rng(self, tag: str) -> random.Random:
        """
        生成一个可复现的 RNG（用于商店/事件/俘虏/Combo候选等）。
        注意：不使用内置 hash，避免不同进程/不同 PYTHONHASHSEED 导致不一致。
        """
        base = self.ensure_seed()
        salt = _stable_u32(f"{tag}:{self.rng_step}")
        self.rng_step += 1
        return random.Random((base ^ salt) & 0x7FFFFFFF)


