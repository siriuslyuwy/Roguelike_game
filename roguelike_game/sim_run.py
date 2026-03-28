"""
整局 Run 批量模拟（无渲染）：
- 均匀 BuildPlan（玩家侧）
- 中 Bot 作为平衡基准
- 输出 episodes.csv / summary.json / report.md / diff.md

用法示例（PowerShell）：
    py roguelike_game/sim_run.py --batch 200 --seed 1000 --out runs --name "2025-12-27平衡" --note "改了兵种Q/W数值+商店价格"

说明：
- 你可以直接点 Run 运行本文件：**若不带命令行参数，会使用文件顶部的 DEFAULT_RUN 配置**（方便你快速改参数/改测试名）。
- 也可以用命令行参数覆盖 DEFAULT_RUN（适合做脚本化批量跑）。
- `--name` 会写入 `summary.json/report.md`，并参与输出目录命名，便于你持续迭代与对比。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# 兼容运行方式：
# - 从仓库根目录执行：py roguelike_game/sim_run.py
# - 从 roguelike_game 目录执行：py sim_run.py
_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from game.campaign import CampaignState, generate_campaign_map
from game.constants import (
    BASE_MAX_HP,
    CAMPAIGN_BATTLE_NODE_TYPES,
    CAMPAIGN_ENEMY_DAMAGE_GROWTH,
    CAMPAIGN_ENEMY_HP_GROWTH,
    CAMPAIGN_PARAMS,
    AI_RESOURCE_GROWTH_START_STAGE,
    AI_RESOURCE_GROWTH_PER_STAGE,
    AI_RESOURCE_CAP_GROWTH_PER_STAGE,
    EVENT_GOLD_LARGE,
    EVENT_GOLD_MED,
    EVENT_GOLD_SMALL,
    FORGE_RETARGET_BASE_COST,
    FORGE_RETARGET_PER_LEVEL_COST,
    FORGE_LEVEL_4_SUCCESS_RATE,
    FORGE_LEVEL_5_SUCCESS_RATE,
    LANE_COUNT,
    PRISONER_EXECUTE_GOLD,
    PRISONER_RELEASE_GOLD,
    PRISONER_REP_GAIN,
    PRISONER_REP_LOSS,
    REPUTATION_MAX,
    REPUTATION_MIN,
    SHOP_ITEM_PRICE_HIGH,
    SHOP_ITEM_PRICE_LOW,
    SHOP_ITEM_PRICE_MED,
    SHOP_REFRESH_BASE_COST,
    SKILL_ORDER,
    SKILLS,
    BLESSINGS,
    COMBO_CARDS,
    BLESSING_TRIGGER_BATTLE_COUNT,
    COMBO1_TRIGGER_BATTLE_COUNT,
    MAX_RESOURCE,
)
from game.game import Game, MAX_UNIT_LEVEL, ORDER_KEYS, UNIT_TYPES
from game.run_state import CampaignRunState
from game.save_system import delete_autosave, load_autosave, save_autosave, mirror_profile_path


BUILD_PLANS: List[str] = [
    "standard_comp",
    "aoe_clear",
    "rush_push",
    "econ_snowball",
    "skills_online",
    "forge_growth",
    "prisoner_growth",
    "defensive_counter",
    "elite_greed",
    "random_thematic",
]

# ============================================================
# ✅ 快速修改入口（点 Run 直接跑）
# 你只需要改这里的 DEFAULT_RUN，就能快速换测试参数和测试名称。
# 命令行传参会覆盖这里的默认值。
# ============================================================
DEFAULT_RUN: dict = {
    # 跑多少局（建议：200 / 500 / 1000）
    "batch": 500,
    # base seed（每局 = seed + i）
    "seed": 1000,
    # 输出目录（会在里面生成一个带时间戳的子目录）
    "out": "runs",
    # ✅ 测试名称（会写进 report/summary，并进入输出目录名）
    "name": "2025-12-30平衡",
    # ✅ 备注（可留空）
    "note": "教官光环bug修复",
    # 目前只实现了 mid
    "bot": "mid",
    # === 性能/安全阈值（防止某些局卡太久）===
    # 单场战斗的“模拟时间上限”（秒）。达到就强制结算（与手玩一致：判定为“敌方撤退”，玩家惨胜，并加强后续难度）。
    "battle_max_time_sec": 300.0,
    # 每次 game.update 的 dt（越大越快，但精度更低；推荐 0.08~0.2）
    "battle_dt": 0.10,
    # 单场战斗的“真实运行耗时上限”（秒）。
    # 说明：保留 walltime 作为“防卡死”阈值，但当触发 walltime 时，胜负结算仍与手玩一致（强制结算为胜利并叠加后续难度惩罚），避免“没跑满300秒就判负”。
    "battle_wall_time_sec": 60,
    # 每隔多少局打印一次进度
    "progress_every": 10,
}


def _now_tag() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _try_git_version() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        if not out:
            return None
        # dirty?
        dirty = False
        try:
            s = subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True)
            dirty = bool(s.strip())
        except Exception:
            dirty = False
        return f"git:{out}{' dirty' if dirty else ''}"
    except Exception:
        return None


def _clamp_reputation(rep: int) -> int:
    return max(REPUTATION_MIN, min(REPUTATION_MAX, int(rep)))


def _rep_segment(rep: int) -> str:
    if rep > 10:
        return "saint"
    if rep < -10:
        return "demon"
    return "lord"


def _percentile(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return float(ys[0])
    q = max(0.0, min(1.0, float(q)))
    pos = q * (len(ys) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(ys[lo])
    t = pos - lo
    return float(ys[lo] * (1 - t) + ys[hi] * t)


def _mean(xs: List[float]) -> float:
    return float(statistics.mean(xs)) if xs else 0.0


def _safe_json_loads(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _sum_base_hp(bases: Iterable[Any]) -> float:
    return float(sum(max(0.0, float(b.hp)) for b in bases))


def _count_destroyed(bases: Iterable[Any]) -> int:
    return int(sum(1 for b in bases if float(b.hp) <= 0.0))


def _build_mirror_snapshot_from_run(run: CampaignRunState, build_plan_id: str = "") -> dict:
    return {
        "version": 1,
        "units": list(run.units or []),
        "unit_levels": dict(run.unit_levels or {}),
        "skills": list(run.skills or []),
        "boons": dict(run.boons or {}),
        "combo": list(run.combo.selected_cards or []),
        "blessing": run.blessing_selected,
        "forge_offense": dict(run.forge.offense_level_by_unit or {}),
        "forge_defense": dict(run.forge.defense_level_by_unit or {}),
        "primary_unit": str(getattr(run, "primary_unit", "") or ""),
        "reputation": int(getattr(run, "reputation", 0) or 0),
        "build_plan": str(build_plan_id or ""),
    }


def _render_mirror_report_md(stats: dict, meta: dict) -> str:
    def _join(xs: list) -> str:
        xs = [str(x) for x in (xs or []) if str(x)]
        return "|".join(xs) if xs else "-"

    def _fmt_levels(d: dict) -> str:
        items = [(str(k), int(v)) for k, v in (d or {}).items()]
        items.sort(key=lambda x: x[0])
        return ", ".join(f"{k}:{v}" for k, v in items) if items else "-"

    def _fmt_forge(off: dict, dfn: dict) -> str:
        keys = sorted(set(list((off or {}).keys()) + list((dfn or {}).keys())))
        parts = []
        for k in keys:
            o = int((off or {}).get(k, 0) or 0)
            d = int((dfn or {}).get(k, 0) or 0)
            if o <= 0 and d <= 0:
                continue
            parts.append(f"{k}:o{o}/d{d}")
        return ", ".join(parts) if parts else "-"

    lines: list[str] = []
    lines.append("# 镜像Boss批量测试报告")
    lines.append("")
    lines.append(f"- 生成时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 批量局数: {stats.get('total_runs', 0)}")
    lines.append(f"- Boss遇到次数: {stats.get('boss_encounters', 0)}")
    lines.append(f"- Boss胜利次数: {stats.get('boss_wins', 0)}")
    lines.append(f"- 镜像刷新次数: {stats.get('mirror_updates', 0)}")
    lines.append(f"- 镜像刷新率: {stats.get('update_rate', 0.0):.4f}")
    lines.append(f"- 镜像Boss遭遇率: {stats.get('mirror_encounter_rate', 0.0):.4f}")
    lines.append(f"- 镜像Boss胜率(玩家): {stats.get('mirror_win_rate', 0.0):.4f}")
    lines.append(f"- 最后镜像脚本长度: {stats.get('last_mirror_script_len', 0)}")
    lines.append(f"- 最后镜像更新时间: {stats.get('last_mirror_updated', 0.0)}")
    lines.append("")
    lines.append("## 镜像Boss列表（按刷新顺序）")
    lines.append("")

    history = stats.get("mirror_history") or []
    if not history:
        lines.append("> 无镜像Boss刷新记录")
    else:
        for item in history:
            idx = int(item.get("idx", 0) or 0)
            run_index = int(item.get("run_index", 0) or 0)
            build_plan = str(item.get("build_plan", "") or "")
            script_len = int(item.get("script_len", 0) or 0)
            runs_since = int(item.get("runs_since_update", 0) or 0)
            mirror_enc_since = int(item.get("mirror_encounters_since_update", 0) or 0)
            snap = item.get("snapshot") or {}

            lines.append(f"### #{idx} 刷新于第 {run_index} 局")
            lines.append("")
            lines.append(f"- 刷新间隔(局数): {runs_since}")
            lines.append(f"- 刷新间隔(镜像挑战次数): {mirror_enc_since}")
            lines.append(f"- build_plan: {build_plan}")
            lines.append(f"- 镜像脚本长度: {script_len}")
            lines.append("")
            lines.append("| 项目 | 值 |")
            lines.append("|---|---|")
            lines.append(f"| 祝福 | {snap.get('blessing', '') or '-'} |")
            lines.append(f"| Combo | {_join(snap.get('combo') or [])} |")
            lines.append(f"| 技能 | {_join(snap.get('skills') or [])} |")
            lines.append(f"| 兵种 | {_join(snap.get('units') or [])} |")
            lines.append(f"| 兵种等级 | {_fmt_levels(snap.get('unit_levels') or {})} |")
            lines.append(f"| 兵种锻造 | {_fmt_forge(snap.get('forge_offense') or {}, snap.get('forge_defense') or {})} |")
            lines.append("")

    lines.append("## 参数")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| name | {meta.get('name','')} |")
    lines.append(f"| seed_base | {meta.get('seed_base','')} |")
    lines.append(f"| bot_tier | {meta.get('bot_tier','')} |")
    lines.append(f"| battle_max_time_sec | {meta.get('battle_max_time_sec','')} |")
    lines.append(f"| battle_dt | {meta.get('battle_dt','')} |")
    lines.append(f"| battle_wall_time_sec | {meta.get('battle_wall_time_sec','')} |")
    lines.append("")
    return "\n".join(lines)


@dataclass
class EpisodeResult:
    version: str
    run_id: str
    seed: int
    bot_tier: str
    build_plan_id: str
    win: int
    reached_layer: int
    total_time_sec: float
    gold_end: int
    shop_refresh_count: int
    shop_spent: int
    event_net: int
    units_count: int
    avg_unit_level: float
    skills_count: int
    combo_count: int
    base_hp_sum_end: float
    bases_destroyed_left: int
    bases_destroyed_right: int
    battle_timeout: int = 0
    # 达到 battle_max_time_sec（模拟时长上限）但未分胜负
    battle_time_limit_hit: int = 0
    # 结算规则（测试用）：时间打满时，按“本场净基地伤害优势”判定是否通过（见 SimRunner._run_battle）
    battle_hold_pass: int = 0
    # === 关键系统状态（用于分组报表）===
    blessing_selected: str = ""
    skills: str = ""  # 以 "|" 拼接，便于 CSV 阅读
    combos: str = ""  # 以 "|" 拼接
    units: str = ""   # 以 "|" 拼接（最终拥有的兵种key）
    unit_levels_json: str = ""  # JSON：{unit_key: level}
    forge_levels_json: str = ""  # JSON：{unit_key: level}
    forge_dirs_json: str = ""  # JSON：{unit_key: "offense"/"defense"}
    forge_max_level: int = 0
    forge_total_levels: int = 0
    # 出兵次数（整局累计）
    spawn_counts_json: str = ""  # JSON：{unit_key: count}
    spawn_total: int = 0
    # === 兵种口径（用于你想要的 15 兵种表）===
    starting_units: str = ""  # 开局兵种（按槽位顺序），用 "|" 拼接
    primary_unit: str = ""  # 本局"首选兵种"=开局第1槽
    dominant_unit: str = ""  # 本局"最多出兵次数兵种"（若全为0则为空）
    second_dominant_unit: str = ""  # 第二多出兵兵种
    third_dominant_unit: str = ""  # 第三多出兵兵种
    unit_acquire_layers_json: str = ""  # JSON：{unit_key: layer}（获得该兵种时的层数）
    # === 路线 / 行为日志（轻量，便于反推"为什么死/为什么难"）===
    day_end: int = 0
    steps_total: int = 0
    node_counts_json: str = ""  # JSON：{node_type: count}
    path_json: str = ""  # JSON：[{layer:int, day:int, type:str}]
    shop_actions_json: str = ""  # JSON：[{action:str, ...}] action=refresh/buy/skip
    event_actions_json: str = ""  # JSON：[{template:str, choice:int, seg:str, gold_delta:int}]
    milestone_json: str = ""  # JSON：{blessing:{...}, combos:[...]}（含触发战斗数/天数/原因）
    # === 敌方兵种信息（最后一场战斗）===
    last_enemy_pool: str = ""  # 敌方可用兵种池，以 "|" 拼接
    last_enemy_spawned: str = ""  # 敌方实际出兵的兵种（去重），以 "|" 拼接
    # === 镜像Boss统计 ===
    boss_encounter: int = 0
    mirror_encounter: int = 0
    mirror_win: int = 0
    mirror_blessing: str = ""
    mirror_build_plan: str = ""


class MidBattleBot:
    """
    中 Bot：不追求最优，但具备最低限度的"前排后排 + 补崩线 + AOE反聚怪 + 技能救急"。
    
    祝福适配：
    - 钢铁洪流 (steel_tide): 强制高频暴兵模式，不等待攒钱，降低前排要求
    - 教官光环 (veteran_mentor): 优先用战士替代其他坦克
    """

    def __init__(
        self,
        rng,
        blessing: str = "",
        campaign_state=None,
        record_event: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.rng = rng
        self._spawn_timer = 0.0
        self._skill_timer = 0.0
        self._last_lane: int | None = None
        self._same_lane_streak: int = 0
        self.blessing = blessing  # 祝福ID
        self.campaign_state = campaign_state  # 战役状态（用于获取金币等信息）
        
        # === 进攻等待机制：先选目标兵种，资源不足时等待（仅非紧急情况）===
        self._pending_spawn_key: str | None = None  # 等待出的目标兵种
        self._pending_lane: int | None = None  # 等待出兵的目标lane
        self._pending_start_time: float = 0.0  # 开始等待的时间（用于超时检测）

        # === 出兵多样性跟踪（用于 steel_tide 等“高频暴兵”模式，避免同线连出导致纯战流雪崩）===
        self._last_spawn_key_by_lane: dict[int, str | None] = {i: None for i in range(LANE_COUNT)}
        self._same_spawn_key_streak_by_lane: dict[int, int] = {i: 0 for i in range(LANE_COUNT)}
        
        # === 基地HP历史记录（用于判断"5秒内是否掉血"）===
        self._base_hp_history: dict[int, list[tuple[float, float]]] = {
            i: [] for i in range(LANE_COUNT)
        }  # {lane_id: [(battle_time, hp), ...]}
        self._base_hp_check_interval = 0.1  # 每0.1秒记录一次
        self._base_hp_check_timer = 0.0
        self._record_event_fn = record_event

    def step(self, game: Game, dt: float) -> None:
        if game.winner:
            return
        self._spawn_timer -= dt
        self._skill_timer -= dt
        self._base_hp_check_timer -= dt

        # 基地HP记录：每 0.1s 记录一次（用于判断"5秒内是否掉血"）
        if self._base_hp_check_timer <= 0.0:
            self._base_hp_check_timer = self._base_hp_check_interval
            self._update_base_hp_history(game)

        # 技能：每 0.35s 尝试一次（避免连点）
        if self._skill_timer <= 0.0:
            self._skill_timer = 0.35
            self._try_cast_skill(game)

        # 出兵：每 0.01s 尝试一次（极小间隔，仅防止递归溢出）
        if self._spawn_timer <= 0.0:
            self._spawn_timer = 0.01
            self._try_spawn(game)

    def _record_spawn(self, lane: int, key: str) -> None:
        """记录本 Bot 本次在某 lane 的出兵，用于“同线连出惩罚”类策略。"""
        if lane < 0 or lane >= LANE_COUNT:
            return
        k = str(key or "")
        last = self._last_spawn_key_by_lane.get(lane)
        if last == k:
            self._same_spawn_key_streak_by_lane[lane] = int(self._same_spawn_key_streak_by_lane.get(lane, 0) or 0) + 1
        else:
            self._last_spawn_key_by_lane[lane] = k
            self._same_spawn_key_streak_by_lane[lane] = 1

    def _lane_threat(self, game: Game, lane: int) -> float:
        """
        威胁值：越大越危险（敌人越多、越近、数量优势越大）。
        空线威胁值 = 0。
        """
        if game.left_bases[lane].hp <= 0 or game.right_bases[lane].hp <= 0:
            return -1e9  # 已爆基地，威胁值最小（不选）
        
        left_base_x = float(game.left_bases[lane].x)
        right_units = [u for u in game.right_units[lane] if u.alive]
        
        # 空线：威胁值 = 0
        if not right_units:
            return 0.0
        
        # === 基础威胁值：每个敌人贡献威胁值 ===
        threat = 0.0
        left_count = sum(1 for u in game.left_units[lane] if u.alive)
        
        for u in right_units:
            # 计算距离（敌人越近，威胁值越高）
            distance = float(u.x - left_base_x)
            # 距离越近，威胁值越高：使用 (1000 - distance) 作为基础，最小为 0
            proximity_bonus = max(0.0, 1000.0 - distance) / 10.0  # 归一化到合理范围
            
            # 单位类型威胁值
            if u.unit_type.is_ranged:
                # 远程单位威胁值减少 25%
                unit_threat = proximity_bonus * 0.75
            else:
                # 近战单位：基础威胁值
                unit_threat = proximity_bonus
            
            threat += unit_threat
        
        # === 数量劣势惩罚：敌人数量优势越大，威胁值越高 ===
        if left_count > 0:
            ratio = float(len(right_units)) / float(left_count)
            if ratio >= 2.0:  # 敌人数量是玩家的 2 倍或更多
                threat += 200.0  # 大幅增加威胁值
            elif ratio >= 1.5:  # 敌人数量是玩家的 1.5 倍
                threat += 100.0
        
        # === 远距离衰减：远距离敌人威胁值降低 ===
        FAR_DISTANCE_THRESHOLD = 500.0
        far_units = [u for u in right_units if (u.x - left_base_x) > FAR_DISTANCE_THRESHOLD]
        if far_units:
            far_ratio = float(len(far_units)) / float(len(right_units))
            # 远距离单位威胁值衰减：近战减半，远程再减 25%
            far_threat_reduction = 0.0
            for u in far_units:
                if u.unit_type.is_ranged:
                    far_threat_reduction += 0.25  # 远程再减 25%
                else:
                    far_threat_reduction += 0.5  # 近战减半
            threat *= (1.0 - far_threat_reduction * far_ratio)
        
        return threat

    def _update_base_hp_history(self, game: Game) -> None:
        """
        定期记录每条线的基地HP，用于判断"5秒内是否掉血"。
        只保留最近5秒的记录。
        """
        battle_time = getattr(game, "battle_time", 0.0)
        HISTORY_WINDOW = 5.0  # 保留5秒历史
        
        for lane in range(LANE_COUNT):
            current_hp = float(game.left_bases[lane].hp)
            
            # 添加当前记录
            self._base_hp_history[lane].append((battle_time, current_hp))
            
            # 清理超过5秒的旧记录
            cutoff_time = battle_time - HISTORY_WINDOW
            self._base_hp_history[lane] = [
                (t, hp) for t, hp in self._base_hp_history[lane]
                if t >= cutoff_time
            ]

    def _has_base_taken_damage_recently(self, game: Game, lane: int, window: float = 5.0) -> bool:
        """
        判断指定lane的基地在最近window秒内是否掉过血。
        
        Args:
            game: 游戏对象
            lane: 战线编号
            window: 时间窗口（秒），默认5秒
        
        Returns:
            True: 最近window秒内掉过血
            False: 没有掉血或历史记录不足
        """
        if lane not in self._base_hp_history:
            return False
        
        history = self._base_hp_history[lane]
        if len(history) < 2:
            return False  # 历史记录不足，无法判断
        
        battle_time = getattr(game, "battle_time", 0.0)
        cutoff_time = battle_time - window
        
        # 找到window内最早和最新的HP记录
        recent_records = [(t, hp) for t, hp in history if t >= cutoff_time]
        if len(recent_records) < 2:
            return False
        
        # 比较最早和最新的HP
        earliest_hp = recent_records[0][1]
        latest_hp = recent_records[-1][1]
        
        # 如果HP下降了，说明掉血了
        return latest_hp < earliest_hp

    def _lane_attack_opportunity(self, game: Game, lane: int) -> float:
        """进攻机会：越小越值得推进（己方前线越接近敌方基地）。"""
        if game.left_bases[lane].hp <= 0 or game.right_bases[lane].hp <= 0:
            return 1e9
        right_base_x = float(game.right_bases[lane].x)
        left_units = [u for u in game.left_units[lane] if u.alive]
        left_front = max((u.x for u in left_units), default=float(game.left_bases[lane].x + 40))
        return float(right_base_x - left_front)

    def _is_lane_urgent(self, game: Game, lane: int) -> bool:
        """
        判断指定 lane 是否紧急（需要立即出兵，不能等待）。
        
        改进后的紧急条件：
        1. 基地在最近5秒内掉过血（而非绝对值判断）
        2. 被反推：敌人数量 > 我方数量 且 敌人 >= 2（不包括等于）
        3. 威胁值 >= 250（提高阈值，让等待机制有更多发挥空间）
        """
        if lane < 0 or lane >= LANE_COUNT:
            return False
        if game.left_bases[lane].hp <= 0:
            return False
        
        enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
        friendly_alive = sum(1 for u in game.left_units[lane] if u.alive)
        
        # === 条件1：基地在最近5秒内掉过血 ===
        if self._has_base_taken_damage_recently(game, lane, window=5.0):
            return True
        
        # === 条件2：被反推（敌 > 我，且敌人至少2个）===
        if friendly_alive > 0 and enemy_alive > friendly_alive and enemy_alive >= 2:
            return True
        
        # === 条件3：威胁值过高（阈值提高到250）===
        threat = self._lane_threat(game, lane)
        if threat >= 250.0:  # 原140 -> 250
            return True
        
        return False
    
    def _pick_lane(self, game: Game) -> int:
        """
        选线策略（中 Bot）：
        - 有明显危险时：优先补崩线（防守）
        - 否则：倾向开空线/薄弱线推进（进攻）
        - 加入分散机制：避免长期只在一条线对冲导致“时间打满平局”
        """
        # 仅考虑双方基地都还在的 lane
        active_lanes: List[int] = [
            lane
            for lane in range(LANE_COUNT)
            if game.left_bases[lane].hp > 0 and game.right_bases[lane].hp > 0
        ]
        if not active_lanes:
            return 0

        # 先构建 threats 列表（用于防守模式及权重）
        threats: List[Tuple[float, int]] = [(self._lane_threat(game, lane), lane) for lane in active_lanes]
        threat_by_lane: dict[int, float] = {lane: float(th) for th, lane in threats}

        # === 开局护栏：对齐 AI 起手线，避免“第一波没对上导致白送一路” ===
        # 当双方场上都还没有任何单位时，所有 lane 的 opp/威胁评分通常完全对称；
        # 此时本 Bot 会在 top3 里随机，容易与 AI 的 tie-break 不一致。
        # AI 在对称局面下倾向选择“最小 lane index”，所以这里镜像该规则。
        total_left_alive = sum(1 for l in range(LANE_COUNT) for u in game.left_units[l] if u.alive)
        total_right_alive = sum(1 for l in range(LANE_COUNT) for u in game.right_units[l] if u.alive)
        if total_left_alive == 0 and total_right_alive == 0:
            return int(min(lane for _th, lane in threats))

        # === 关键护栏 0：提前预警（极高优先级）===
        # 目标：基地血要跨 20 层继承时，“没掉血再救”会太迟。
        # - 当某条线我方空线（friendly=0）但敌方已经形成推进（enemy>=2 且 threat 足够高）时，
        #   立刻回防补兵，避免被“偷线/收割”诱导而白送基地血。
        EARLY_DEFEND_THREAT = 140.0  # 低于 DEFEND_THRESHOLD(200)，用于提前回防
        EARLY_DEFEND_ENEMY_MIN = 2

        early_urgent: List[Tuple[float, int]] = []
        for lane in active_lanes:
            enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
            friendly_alive = sum(1 for u in game.left_units[lane] if u.alive)
            if friendly_alive != 0:
                continue
            if enemy_alive < EARLY_DEFEND_ENEMY_MIN:
                continue
            th = float(threat_by_lane.get(lane, 0.0))
            if th >= EARLY_DEFEND_THREAT:
                # 越小越急：威胁越大 / 敌人越多 → 越优先（数值要强势压过进攻逻辑）
                score = -th - enemy_alive * 50.0
                # 轻微滞回：如果刚才已经在这条线，降低来回抖动
                if self._last_lane is not None and lane == self._last_lane:
                    score -= 30.0
                early_urgent.append((score, lane))
        if early_urgent:
            early_urgent.sort()
            return int(early_urgent[0][1])

        # === 关键护栏 1：正在掉血/被反推的线，优先救（避免“打一半就走，基地被反堆”） ===
        # 触发条件（任一满足）：
        # - 我方基地已经掉血且该线仍有敌人存活
        # - 我方场上有单位但敌人数量已追平/反超（说明正在被反推），需要续兵顶住
        BASE_MAX = float(BASE_MAX_HP)
        urgent: List[Tuple[float, int]] = []
        for lane in active_lanes:
            left_base_hp = float(game.left_bases[lane].hp)
            enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
            friendly_alive = sum(1 for u in game.left_units[lane] if u.alive)
            if (left_base_hp < BASE_MAX and enemy_alive > 0) or (friendly_alive > 0 and enemy_alive >= friendly_alive and enemy_alive >= 2):
                # 越小越急：优先救血量更低/敌人更多/威胁更高的线
                th = float(threat_by_lane.get(lane, 0.0))
                urgency = left_base_hp - enemy_alive * 45.0 - th * 1.6
                # 若该线已经掉血，进一步提高救线权重（更符合“续航优先”）
                if left_base_hp < BASE_MAX:
                    urgency -= 90.0
                urgent.append((urgency, lane))
        if urgent:
            urgent.sort()
            return int(urgent[0][1])

        # === 关键护栏 2：有机会“收割残血基地”，就持续投入直到推爆 ===
        # 典型问题：Bot 先在某线占到优势但没推爆就切走，结果被 AI 反推。
        # 这里让 Bot 在满足“己方已站住 + 敌方该线缺人 + 基地已残”的情况下优先 finish。
        COMMIT_RIGHT_BASE_HP = 260.0
        commit: List[Tuple[float, int]] = []
        for lane in active_lanes:
            enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
            friendly_alive = sum(1 for u in game.left_units[lane] if u.alive)
            right_base_hp = float(game.right_bases[lane].hp)
            if friendly_alive > 0 and enemy_alive == 0 and right_base_hp < COMMIT_RIGHT_BASE_HP:
                # 越小越优先：基地越残越先收割
                commit.append((right_base_hp, lane))
        if commit:
            commit.sort()
            return int(commit[0][1])

        # === 威胁值排序：越大越危险 ===
        threats.sort(reverse=True)  # 降序：威胁值最大的在前
        max_threat, _danger_lane = threats[0]
        
        # === 防守模式判断：威胁值 > 阈值时进入防守模式 ===
        DEFEND_THRESHOLD = 200.0  # 威胁值超过此值，进入防守模式
        defend_mode = bool(max_threat > DEFEND_THRESHOLD)
        
        # === 判断"战线稳住"：检查是否有正在交战的线且防守压力不大 ===
        has_stable_lanes = False
        if not defend_mode:
            # 检查是否有正在交战的线（有己方单位）
            for lane in range(LANE_COUNT):
                if game.left_bases[lane].hp <= 0 or game.right_bases[lane].hp <= 0:
                    continue
                left_alive = sum(1 for u in game.left_units[lane] if u.alive)
                right_alive = sum(1 for u in game.right_units[lane] if u.alive)
                # 有己方单位，且威胁值不高（能顶住）
                if left_alive > 0 and self._lane_threat(game, lane) < DEFEND_THRESHOLD * 0.6:
                    has_stable_lanes = True
                    break

        if defend_mode:
            # === 防守模式：优先防守威胁值最大的线 ===
            top = threats[: min(3, len(threats))]
            if self._last_lane is not None and self._same_lane_streak >= 8 and len(top) >= 2:
                alt = [lane for _th, lane in top if lane != self._last_lane]
                pick = alt[0] if alt else top[0][1]
            else:
                lanes = [lane for _th, lane in top]
                weights = [max(1.0, float(th)) for th, _lane in top]  # 威胁值越大，权重越高；至少为1.0避免全0
                pick = self.rng.choices(lanes, weights=weights, k=1)[0]
        else:
            # === 进攻模式：优先去空线偷残血基地 ===
            # 如果战线稳住，优先去空线偷塔
            empty_lanes: List[Tuple[float, int]] = []
            for lane in range(LANE_COUNT):
                if game.left_bases[lane].hp <= 0 or game.right_bases[lane].hp <= 0:
                    continue
                enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
                if enemy_alive == 0:  # 敌方没有单位
                    # 按敌方基地血量排序：血量越少越优先
                    base_hp = float(game.right_bases[lane].hp)
                    empty_lanes.append((base_hp, lane))
            
            # 如果有空线且战线稳住，优先选择空线中基地血量最少的
            if empty_lanes and has_stable_lanes:
                empty_lanes.sort()  # 按基地血量升序
                pick = empty_lanes[0][1]
            else:
                # 否则使用原来的进攻逻辑
                scored: List[Tuple[float, int]] = []
                for lane in active_lanes:
                    opp = self._lane_attack_opportunity(game, lane)
                    enemy_alive = sum(1 for u in game.right_units[lane] if u.alive)
                    friendly_alive = sum(1 for u in game.left_units[lane] if u.alive)
                    s = float(opp) + enemy_alive * 120.0 + friendly_alive * 35.0
                    # 分散惩罚：仅在“没有推进/没有对抗压力”时生效，避免中途切线导致被反推
                    if self._last_lane is not None and lane == self._last_lane and self._same_lane_streak >= 6:
                        if enemy_alive == 0 and float(game.right_bases[lane].hp) >= 320.0:
                            s += 320.0
                    scored.append((s, lane))
                scored.sort()
                top = scored[: min(3, len(scored))]
                lanes = [lane for _s, lane in top]
                weights = [1.0 / max(60.0, float(s)) for s, _lane in top]
                pick = self.rng.choices(lanes, weights=weights, k=1)[0]

        if self._last_lane is None or pick != self._last_lane:
            self._last_lane = int(pick)
            self._same_lane_streak = 0
        else:
            self._same_lane_streak += 1
        return int(pick)

    def _try_spawn(self, game: Game) -> None:
        if not game.player_order_keys:
            return
        
        blessing = self.blessing
        is_steel_tide = (blessing == "steel_tide")

        # --- 祝福适配：工具函数（必须放在pending/空线逻辑之前，避免被提前return绕开） ---
        def is_buffer_key(k: str) -> bool:
            ut = UNIT_TYPES.get(k)
            return bool(ut) and bool(getattr(ut, "is_buffer", False))

        def is_tank(k: str) -> bool:
            """
            坦克判定（用于Bot出兵策略，而非数值平衡）：
            - 优先使用 tags（策划标记）；
            - 兼容旧数据：无tag时用HP阈值，但在 steel_tide 下放宽阈值。
            """
            ut = UNIT_TYPES.get(k)
            if not ut:
                return False
            # 排除远程/治疗/增益
            if ut.is_ranged or ut.is_healer or getattr(ut, "is_buffer", False):
                return False
            # 排除0伤害单位
            if float(getattr(ut, "damage", 0)) <= 0:
                return False

            if "tank" in getattr(ut, "tags", []):
                return True

            hp_threshold = 100 if is_steel_tide else 200
            return float(getattr(ut, "hp", 0.0)) >= float(hp_threshold)

        def is_back(k: str) -> bool:
            ut = UNIT_TYPES.get(k)
            # 把增益也视为后排/支援（但会被下面“同线仅 1 个增益”规则约束）
            return bool(ut) and (ut.is_ranged or ut.is_healer or getattr(ut, "is_buffer", False))

        def is_aoe(k: str) -> bool:
            ut = UNIT_TYPES.get(k)
            return bool(ut) and bool(getattr(ut, "is_aoe", False))
        
        # === 祝福：破釜沉舟 - 应急触发免费战士 ===
        if blessing == "veteran_last_stand":
            # 遍历所有战线，检查是否有需要应急出免费战士的情况
            for check_lane in range(LANE_COUNT):
                if game.left_bases[check_lane].hp <= 0:
                    continue
                left_count = sum(1 for u in game.left_units[check_lane] if u.alive)
                right_count = sum(1 for u in game.right_units[check_lane] if u.alive)
                # 应急条件：敌>我 且 金币不够出普通战士 且 基地血量>30
                if right_count > left_count and game.left.resource < 65 and game.left_bases[check_lane].hp > 30:
                    # 尝试强制部署战士（会自动扣基地血）
                    if "warrior" in game.player_order_keys:
                        game.spawn_unit("left", check_lane, "warrior")
                        return  # 应急出了一个就返回，下次再判断
        
        # === 检查是否有等待中的目标单位（进攻等待机制）===
        # steel_tide：核心玩法是“高频暴兵”，等待机制会严重降智（且会绕开后续适配逻辑），因此直接禁用
        if is_steel_tide:
            self._pending_spawn_key = None
            self._pending_lane = None
            self._pending_start_time = 0.0
        elif self._pending_spawn_key is not None and self._pending_lane is not None:
            # 检查等待是否应该被打断
            is_urgent = self._is_lane_urgent(game, self._pending_lane)
            battle_time = getattr(game, "battle_time", 0.0)
            
            # 打断条件：目标lane变紧急 或 等待超时（>2秒，避免死等）
            if is_urgent or (battle_time - self._pending_start_time) > 2.0:
                # 清除等待状态，回退到旧逻辑
                self._pending_spawn_key = None
                self._pending_lane = None
                self._pending_start_time = 0.0
            else:
                # 尝试出等待的目标单位
                if game.can_spawn("left", self._pending_lane, self._pending_spawn_key):
                    if game.spawn_unit("left", self._pending_lane, self._pending_spawn_key):
                        if self._record_event_fn:
                            self._record_event_fn(
                                {
                                    "t": float(getattr(game, "battle_time", 0.0)),
                                    "type": "spawn",
                                    "lane": int(self._pending_lane),
                                    "unit": str(self._pending_spawn_key),
                                }
                            )
                        # 成功出兵，清除等待状态
                        self._pending_spawn_key = None
                        self._pending_lane = None
                        self._pending_start_time = 0.0
                        return
                # 资源/CD还不够，继续等待
                return
        
        lane = self._pick_lane(game)

        # 检查是否是空线（敌方没有单位）
        right_units = [u for u in game.right_units[lane] if u.alive]
        is_empty_lane = len(right_units) == 0

        # === 空线偷塔：选择费用最低的近战兵 ===
        if is_empty_lane:
            # 先收集“当前能出的”候选
            keys_can = [k for k in game.player_order_keys if game.can_spawn("left", lane, k)]
            if not keys_can:
                return

            # 统计该线己方现状（用于 steel_tide 下避免“纯近战空线偷塔”导致的纯战流雪崩）
            left_alive = [u for u in game.left_units[lane] if u.alive]
            melee_alive = sum(
                1
                for u in left_alive
                if (not u.unit_type.is_ranged)
                and (not u.unit_type.is_healer)
                and (not getattr(u.unit_type, "is_buffer", False))
                and float(getattr(u.unit_type, "damage", 0)) > 0
            )
            back_alive = sum(
                1
                for u in left_alive
                if (u.unit_type.is_ranged or u.unit_type.is_healer or getattr(u.unit_type, "is_buffer", False))
            )
            support_alive = sum(1 for u in left_alive if bool(getattr(u.unit_type, "is_buffer", False)))

            # 候选池：按费用排序（便宜优先）
            def cost_of(k: str) -> float:
                ut = UNIT_TYPES.get(k)
                return float(getattr(ut, "cost", 99999))

            melee_keys = [k for k in keys_can if is_tank(k)]
            # back_keys：优先“非buffer的远程/治疗”，只有在本线没有增益单位时才允许buffer进池
            back_keys = []
            for k in keys_can:
                if not is_back(k):
                    continue
                if is_buffer_key(k) and support_alive >= 1:
                    continue
                back_keys.append(k)

            melee_keys.sort(key=cost_of)
            back_keys.sort(key=cost_of)

            if is_steel_tide:
                # steel_tide：空线也要尽快形成“前排+后排”结构
                # - 已有近战但缺后排：优先补后排
                # - 否则：优先补近战（便宜、能推线）
                if melee_alive >= 1 and back_alive <= 0 and back_keys:
                    pick = back_keys[0]
                elif melee_keys:
                    pick = melee_keys[0]
                elif back_keys:
                    pick = back_keys[0]
                else:
                    pick = sorted(keys_can, key=cost_of)[0]
            else:
                # 标准模式：空线偷塔选最便宜近战
                if melee_keys:
                    pick = melee_keys[0]
                else:
                    pick = sorted(keys_can, key=cost_of)[0]

            ok = game.spawn_unit("left", lane, pick)
            if ok and self._record_event_fn:
                self._record_event_fn(
                    {
                        "t": float(getattr(game, "battle_time", 0.0)),
                        "type": "spawn",
                        "lane": int(lane),
                        "unit": str(pick),
                    }
                )
            # steel_tide：空线偷塔也会高频出兵，纳入连出统计
            if ok and is_steel_tide:
                self._record_spawn(lane, pick)
            return

        # === 正常交战线的选兵逻辑 ===
        # 统计该线己方"前排/后排/增益"
        # 重要：增益单位（如鼓手）不应计入前排；且同一条线同时只能存在 1 个增益单位
        left_units = [u for u in game.left_units[lane] if u.alive]
        tank_count = sum(
            1
            for u in left_units
            if (not u.unit_type.is_ranged)
            and (not u.unit_type.is_healer)
            and (not getattr(u.unit_type, "is_buffer", False))
            and float(getattr(u.unit_type, "damage", 0)) > 0
        )
        back_count = sum(
            1
            for u in left_units
            if (u.unit_type.is_ranged or u.unit_type.is_healer or getattr(u.unit_type, "is_buffer", False))
        )
        support_alive = sum(1 for u in left_units if bool(getattr(u.unit_type, "is_buffer", False)))

        # 估计敌方密度（用于 AOE 权重）
        density = len(right_units)
        short_leg = sum(1 for u in right_units if u.unit_type.speed <= 90)

        # === 判断是否紧急：紧急时用旧逻辑（立即出能出的），非紧急时用新逻辑（先选目标再等待）===
        is_urgent = self._is_lane_urgent(game, lane)
        
        # === 祝福适配：钢铁洪流强制进入"高频暴兵"模式 ===
        if is_steel_tide:
            is_urgent = True  # 强制使用"立即出能出的"逻辑，不等待攒钱

        pick: Optional[str] = None
        
        if is_urgent:
            # === 紧急模式：旧逻辑，立即出能出的单位 ===
            keys_all = list(game.player_order_keys)
            self.rng.shuffle(keys_all)
            keys = [k for k in keys_all if game.can_spawn("left", lane, k)]
            if not keys:
                return

            # 规则：同一条线不应叠加多个增益单位
            if support_alive >= 1 or tank_count <= 0:
                non_buffer_keys = [k for k in keys if not bool(getattr(UNIT_TYPES.get(k), "is_buffer", False))]
                if non_buffer_keys:
                    keys = non_buffer_keys

            # === 钢铁洪流专属逻辑：高频暴兵 + 多样性护栏 ===
            if is_steel_tide:
                # 目标：模拟人类 steel_tide 的“数量优势”，但避免同线无限连出同兵种导致纯战流雪崩。
                # 策略：
                # - 每条线尽快补齐“前排 + 后排骨架”：没有前排先出前排；有前排但没后排则补后排
                # - 同线连续出同一个兵种达到阈值后，优先换别的（若有可选）
                melee_keys = [k for k in keys if is_tank(k)]
                back_keys = [k for k in keys if is_back(k)]

                need_melee = tank_count < 1
                need_back = (tank_count >= 1) and (back_count < 1)

                if need_melee and melee_keys:
                    pool = melee_keys
                elif need_back and back_keys:
                    pool = back_keys
                else:
                    # 平衡：有骨架后，优先出“当前能出”的任意单位，但仍保留轻微前排倾向
                    pool = keys
                    if melee_keys and self.rng.random() < 0.55:
                        pool = melee_keys

                # 同线连出惩罚：连续出同一兵种>=4 次，若有替代则避开它
                last_k = self._last_spawn_key_by_lane.get(lane)
                streak = int(self._same_spawn_key_streak_by_lane.get(lane, 0) or 0)
                if last_k and streak >= 4 and len(pool) >= 2:
                    alt = [k for k in pool if k != last_k]
                    if alt:
                        pool = alt

                pick = pool[0]
            else:
                # 标准逻辑：前排不足先补
                if tank_count < max(1, back_count):
                    tanks = [k for k in keys if is_tank(k)]
                    pick = tanks[0] if tanks else None
                else:
                    # AOE 倾向
                    if density >= 4 or short_leg >= 3:
                        aoes = [k for k in keys if is_aoe(k)]
                        if aoes:
                            pick = aoes[0]
                    if pick is None:
                        backs = [k for k in keys if is_back(k)]
                        pick = backs[0] if backs else None
                if pick is None:
                    pick = keys[0]
        else:
            # === 进攻模式：新逻辑，先选目标单位（不过滤can_spawn），资源不足时等待 ===
            keys_all = list(game.player_order_keys)
            self.rng.shuffle(keys_all)
            
            # 规则：同一条线不应叠加多个增益单位（先过滤buffer）
            if support_alive >= 1 or tank_count <= 0:
                non_buffer_keys = [k for k in keys_all if not bool(getattr(UNIT_TYPES.get(k), "is_buffer", False))]
                if non_buffer_keys:
                    keys_all = non_buffer_keys
            
            # 先确定意图类别，从该类别里选目标（不检查can_spawn）
            target_pool: List[str] = []
            
            # 动态调整前排需求比例（钢铁洪流下更宽松）
            min_tank_ratio = 0.5 if is_steel_tide else 1.0  # 钢铁洪流：前排:后排=1:2即可
            
            if tank_count < max(1, int(back_count * min_tank_ratio)):
                # 需要前排：从所有前排单位里选（包括出不起的）
                target_pool = [k for k in keys_all if is_tank(k)]
            else:
                # AOE 倾向（钢铁洪流下提高阈值，因为双方都是人海）
                density_threshold = 6 if is_steel_tide else 4
                if density >= density_threshold or short_leg >= 3:
                    target_pool = [k for k in keys_all if is_aoe(k)]
                if not target_pool:
                    target_pool = [k for k in keys_all if is_back(k)]
            
            if not target_pool:
                target_pool = keys_all
            
            if target_pool:
                pick = target_pool[0]  # 已经shuffle过，直接取第一个
            else:
                return
            
            # 检查目标单位是否能立即出
            if game.can_spawn("left", lane, pick):
                # 能出就立即出
                pass
            else:
                # 不能出：进入等待状态
                battle_time = getattr(game, "battle_time", 0.0)
                self._pending_spawn_key = pick
                self._pending_lane = lane
                self._pending_start_time = battle_time
                return  # 等待，下次再尝试
        
        # === 祝福：教官光环 - 坦克替换为战士 ===
        if blessing == "veteran_mentor" and pick and pick != "warrior":
            pick_ut = UNIT_TYPES.get(pick)
            if pick_ut:
                # 判断是否是坦克单位（使用统一的is_tank判定）
                is_tank_unit = is_tank(pick)
                # 如果选中的是坦克，且战士可用，则替换为战士
                if is_tank_unit and "warrior" in game.player_order_keys and game.can_spawn("left", lane, "warrior"):
                    pick = "warrior"

        ok = game.spawn_unit("left", lane, pick)
        if ok and self._record_event_fn:
            self._record_event_fn(
                {
                    "t": float(getattr(game, "battle_time", 0.0)),
                    "type": "spawn",
                    "lane": int(lane),
                    "unit": str(pick),
                }
            )
        if ok and is_steel_tide:
            self._record_spawn(lane, pick)

    def _try_cast_skill(self, game: Game) -> None:
        # 按槽遍历，找到能放的
        if not getattr(game, "left_skill_types", None):
            return
        
        blessing = self.blessing
        
        # 找"最危险的线"用于 lane 技能
        pressures = [(self._lane_threat(game, lane), lane) for lane in range(LANE_COUNT)]
        pressures.sort()
        danger_lane = pressures[0][1]
        danger = pressures[0][0]

        # 粗略判断敌方密度（用于黑洞/轰炸）
        right_dense = len([u for u in game.right_units[danger_lane] if u.alive])
        def _cast_and_record(slot_idx: int, skill_key: str, lane: int) -> bool:
            if game.cast_skill("left", slot_idx):
                if self._record_event_fn:
                    payload = {
                        "t": float(getattr(game, "battle_time", 0.0)),
                        "type": "skill",
                        "lane": int(lane),
                        "skill": str(skill_key),
                    }
                    if skill_key == "spawn":
                        payload["unit"] = str(game.player_order_keys[0]) if game.player_order_keys else ""
                    self._record_event_fn(payload)
                return True
            return False

        # === 祝福：战术大师 - 放宽技能使用条件 ===
        # 只要劣势（敌>我）且敌人>=2，就尝试放技能
        is_tactical_master = (blessing == "tactical_master")
        if is_tactical_master:
            left_alive = sum(1 for u in game.left_units[danger_lane] if u.alive)
            right_alive = sum(1 for u in game.right_units[danger_lane] if u.alive)
            if right_alive >= 2 and right_alive > left_alive:
                # 处于劣势，尝试放任意可用技能
                for slot, sk in enumerate(list(getattr(game, "left_skill_types", []) or [])):
                    if game.can_cast_skill("left", slot):
                        if _cast_and_record(slot, sk, danger_lane):
                            return
        
        # 简单优先级：救急 > 控场/清杂 > 其他
        for slot, sk in enumerate(list(getattr(game, "left_skill_types", []) or [])):
            if not game.can_cast_skill("left", slot):
                continue
            if sk in ("gotcha", "guardian") and danger < 180:
                if _cast_and_record(slot, sk, danger_lane):
                    return
            if sk in ("black_hole", "boom") and right_dense >= 4:
                if _cast_and_record(slot, sk, danger_lane):
                    return
            if sk == "frost_ray" and right_dense >= 3:
                if _cast_and_record(slot, sk, danger_lane):
                    return
            # origei：己方单位多时开
            if sk == "origei":
                total_left = sum(1 for lane in range(LANE_COUNT) for u in game.left_units[lane] if u.alive)
                if total_left >= 10:
                    if _cast_and_record(slot, sk, danger_lane):
                        return


# === 战略克制与阵容识别常量 ===
STRATEGIC_COUNTERS = {
    "assassin": {"archer", "mage", "frost_archer", "priest"},  # 刺客 -> 远程
    "interceptor": {"archer", "mage", "frost_archer", "priest"},  # 破箭 -> 远程
    "rhino": {"assassin", "interceptor"},            # 犀牛 -> 反制切后/拦截
    "light_cavalry": {"assassin", "interceptor"},            # 轻骑 -> 反制切后/拦截
    "spearman": {"rhino", "light_cavalry"},            # 矛兵 -> 停住冲锋
}
RANGED_SET = {"archer", "mage", "frost_archer", "priest"}
# 辅助/拦截/治疗：低直接输出或功能性单位
SUPPORT_SET = {"priest", "drummer", "interceptor"}


class SimRunner:
    def __init__(self, *, seed: int, bot_tier: str, build_plan_id: str, run_state: CampaignRunState | None = None) -> None:
        # 追踪获得新兵种的时机（层数）
        self._unit_acquire_layers: dict[str, int] = {}
        self.seed = int(seed)
        self.bot_tier = bot_tier
        self.build_plan_id = build_plan_id
        if run_state is not None:
            self.run = run_state
        else:
            self.run = CampaignRunState()
            self.run.seed = self.seed
            self.run.rng_step = 0
        # 开局兵种：每局随机抽 1 个，后续通过商店/俘虏逐步解锁（更贴近真实玩家开局）
        # 但为了避免“开局抽到功能性单位导致体验/测试口径失真”，这里限制开局池：
        # - 只允许近战（非远程）
        # - 排除治疗/增益（priest/drummer）
        # - 排除破箭（interceptor：基本无攻击，且强依赖对面远程）
        # 老兵主角模式：开局强制锁定战士（warrior）
        self.run.units = ["warrior"]
        self.run.unit_levels = {"warrior": 1}
        self._starting_units = ["warrior"]
        self._primary_unit = "warrior"
        self.run.primary_unit = "warrior"

        # 记录获得第1个兵种（老兵）的层数
        self._unit_acquire_layers = {"warrior": 0}
        self.run.skills = []  # 战役开局无技能（与 main.py 一致）
        self.run.boons = {}
        self.run.battle_gold_mult = 1.0
        self.run.prisoner_gold_mult = 1.0
        self.run.reputation = 0

        map_rng = self.run.fork_rng("map")
        self.run.state = generate_campaign_map(map_rng)
        self.run.state.gold = 0
        self.run.state.battle_count = 0
        self.run.cursor_node_id = self.run.state.ensure_cursor()

        # 初始化轨迹/日志（需要在 _choose_combo 之前初始化，因为它会访问 _milestone）
        self._shop_spent = 0
        self._shop_refresh_total = 0
        self._event_net = 0
        self._run_spawn_counts: dict[str, int] = {}
        # === 轨迹/日志（盘内累积，盘末一次性序列化）===
        self._path_steps: list[dict[str, Any]] = []
        self._node_counts: dict[str, int] = {}
        self._shop_actions: list[dict[str, Any]] = []
        self._event_actions: list[dict[str, Any]] = []
        self._milestone: dict[str, Any] = {"blessing": None, "combos": []}
        self._last_boss_recording: list[dict] = []
        self._last_boss_mirror_active: bool = False
        self._last_boss_mirror_blessing: str = ""
        self._last_boss_mirror_build_plan: str = ""

        # 老兵主角模式：开局固定为战士，无需弱势补偿
        self.run.weak_start_combo_given = False

    # === Combo ===
    def _combo_tags_of_selected(self) -> set[str]:
        tags: set[str] = set()
        for cid in self.run.combo.selected_cards:
            cfg = COMBO_CARDS.get(cid, {})
            for t in cfg.get("tags", []):
                tags.add(str(t))
        return tags

    def _roll_combo_options(self) -> list[str]:
        rng = self.run.fork_rng(f"combo:{self.run.combo_context or 'unknown'}")
        owned = set(self.run.combo.selected_cards or [])
        all_ids = [cid for cid in list(COMBO_CARDS.keys()) if cid not in owned]
        rng.shuffle(all_ids)
        if not all_ids:
            return []
        selected_tags = self._combo_tags_of_selected()
        options: list[str] = []
        if selected_tags:
            related = [cid for cid in all_ids if selected_tags.intersection(set(COMBO_CARDS.get(cid, {}).get("tags", [])))]
            if related:
                options.append(rng.choice(related))
        while len(options) < 3 and all_ids:
            pick = rng.choice(all_ids)
            all_ids = [x for x in all_ids if x != pick]
            if pick not in options:
                options.append(pick)
        return options[:3]

    def _apply_combo_card(self, cid: str) -> None:
        if cid in self.run.combo.selected_cards:
            return
        self.run.combo.selected_cards.append(cid)
        # 特殊效果处理
        if cid == "combo_war_funding":
            self.run.battle_gold_mult = 1.2
        elif cid == "combo_prisoner_bounty":
            self.run.prisoner_gold_mult = 1.2

    # === Shop ===
    def _current_unit_level(self, key: str) -> int:
        return max(0, min(MAX_UNIT_LEVEL, int(self.run.unit_levels.get(key, 0) or 0)))

    def _set_unit_level(self, key: str, level: int) -> None:
        clamped = max(0, min(MAX_UNIT_LEVEL, int(level)))
        if clamped <= 0:
            self.run.unit_levels.pop(key, None)
            if key in self.run.units:
                self.run.units.remove(key)
            return
        self.run.unit_levels[key] = clamped
        if key not in self.run.units:
            self.run.units.append(key)
            # 记录获得该兵种时的层数（商店购买）
            if key not in self._unit_acquire_layers:
                current_layer = getattr(self.run.state, "current_layer", 0) or 0
                self._unit_acquire_layers[key] = int(current_layer)

    def _roll_shop_items(self, price_mult: float = 1.0) -> list[dict]:
        rng = self.run.fork_rng("shop_items")
        
        # 计算兵种上限（精兵简政为3，其他为5）
        max_units = 3 if self.run.blessing_selected == "elite_simplicity" else 5

        def price(base: int) -> int:
            mult = max(0.0, float(price_mult))
            if self.run.blessing_selected == "direct_invest":
                mult *= 0.9
            return max(0, int(math.ceil(base * mult)))

        items: list[dict] = []

        unit_candidates = [
            k
            for k in ORDER_KEYS
            if (self._current_unit_level(k) < MAX_UNIT_LEVEL)
            and not (self._current_unit_level(k) == 0 and len(self.run.units) >= max_units)
        ]
        
        # 过滤：战士Q默认不能在商店出现（除非选了不屈之志）
        if self.run.blessing_selected != "veteran_unyielding":
            unit_candidates = [k for k in unit_candidates if k != "warrior"]
        
        rng.shuffle(unit_candidates)
        for _ in range(2):
            if unit_candidates:
                uk = unit_candidates.pop()
                ut = UNIT_TYPES.get(uk)
                nm = ut.name if ut else uk
                cur = self._current_unit_level(uk)
                label = f"{nm} 升级" if cur > 0 else f"{nm} 解锁"
                items.append(
                    {
                        "type": "unit",
                        "payload": uk,
                        "sold": False,
                        "price": price(SHOP_ITEM_PRICE_MED),
                        "name": label,
                        "desc": "立即解锁/升1级",
                    }
                )

        # 技能位未满时，商店刷新 **必定至少出现 1 个技能**
        skill_cap = 3 + (1 if "combo_skill_slot" in self.run.combo.selected_cards else 0)
        if len(self.run.skills) < skill_cap:
            skills = [k for k in SKILL_ORDER if k not in self.run.skills]
            rng.shuffle(skills)
            if skills:
                sk = skills[0]
                cfg = SKILLS.get(sk, {})
                items.append(
                    {
                        "type": "skill",
                        "payload": sk,
                        "sold": False,
                        "price": price(SHOP_ITEM_PRICE_HIGH),
                        "name": f"技能：{cfg.get('name', sk)}",
                        "desc": cfg.get("desc", ""),
                    }
                )

        items.append(
            {
                "type": "forge_device",
                "payload": "normal",
                "sold": False,
                "price": price(SHOP_ITEM_PRICE_LOW),
                "name": "普通锻造器",
                "desc": "立即进行一次锻造（结束后回到商店）",
            }
        )

        while len(items) < 4:
            items.append({"type": "empty", "sold": False, "price": 0, "name": "空", "desc": ""})

        # 若未来扩展导致 items>4：强制保留 1 个 skill（当技能位未满且存在可用 skill）
        must_keep_skill = (len(self.run.skills) < skill_cap) and any(it.get("type") == "skill" for it in items)
        if len(items) <= 4:
            rng.shuffle(items)
            return items[:4]

        skill_items = [it for it in items if it.get("type") == "skill"]
        other_items = [it for it in items if it.get("type") != "skill"]
        rng.shuffle(skill_items)
        rng.shuffle(other_items)
        picked: list[dict] = []
        if must_keep_skill and skill_items:
            picked.append(skill_items.pop())
        pool = other_items + skill_items
        rng.shuffle(pool)
        picked.extend(pool[: max(0, 4 - len(picked))])
        while len(picked) < 4:
            picked.append({"type": "empty", "sold": False, "price": 0, "name": "空", "desc": ""})
        rng.shuffle(picked)
        return picked[:4]

    def _shop_visit(self) -> None:
        # 处理一次性券：free refresh disabled/bonus/price mult
        base_free = 1
        if self.run.oneshot.next_shop_free_refresh_disabled:
            base_free = 0
            self.run.oneshot.next_shop_free_refresh_disabled = False
        bonus = max(0, int(self.run.oneshot.next_shop_free_refresh_bonus))
        self.run.oneshot.next_shop_free_refresh_bonus = 0
        self.run.shop_free_refresh_left = base_free + bonus

        price_mult = float(self.run.oneshot.next_shop_price_mult_once or 1.0)
        self.run.oneshot.next_shop_price_mult_once = 1.0

        # 老兵主角模式：无弱势开局补偿
        self.run.shops_visited = int(getattr(self.run, "shops_visited", 0) or 0) + 1
        self.run.shop_price_mult_current = float(price_mult)

        self.run.shop_refresh_paid_count = 0
        self.run.shop_donated = False
        self.run.shop_robbery_confirm = False

        items = self._roll_shop_items(price_mult)

        # 简化：中 Bot 每次进店最多刷新 2 次；允许同一间店内连续购买，避免“金币闲置过多”
        refresh_limit = 2
        buy_limit = 3
        buys = 0
        while True:
            bought = False
            # 购买策略（推荐方案落地）：
            # - 未拿到首个技能前：以“至少 1 个技能”为目标，能买则必买；买不起则不乱花钱（存到下次商店）
            # - 拿到首个技能后：仅 skill build 才允许继续买技能；非 skill build 限购 1 个
            is_skill_build = self.build_plan_id in ("skills_online",)
            min_skills = 1
            max_skills = 2 if is_skill_build else 1
            need_first_skill = len(self.run.skills) < min_skills

            # 当前商店里技能的实际价格（受 price_mult / blessing 影响）
            skill_price_in_shop: int | None = None
            for it in items:
                if it.get("type") == "skill" and not it.get("sold"):
                    try:
                        skill_price_in_shop = int(it.get("price", 0) or 0)
                    except Exception:
                        skill_price_in_shop = None
                    break
            primary = str(getattr(self.run, "primary_unit", "") or "")

            # 先买一个最优 item
            ranked = list(items)
            blessing = getattr(self.run, "blessing_selected", "")
            
            def score(it: dict) -> float:
                if it.get("sold"):
                    return -1e9
                t = it.get("type")
                p = int(it.get("price", 0) or 0)
                if p > int(self.run.state.gold):
                    return -1e6
                
                # === 祝福：匠人精神 - 新兵种优先级最高（因为没有俘虏系统） ===
                if blessing == "craftsman_spirit" and t == "unit":
                    uk = str(it.get("payload") or "")
                    cur = self._current_unit_level(uk)
                    if cur == 0:  # 未拥有的兵种
                        return 10000.0  # 最高优先级
                
                # === 祝福：精兵简政 - 第二个名额必须锁定远程 ===
                if blessing == "elite_simplicity" and t == "unit":
                    uk = str(it.get("payload") or "")
                    cur = self._current_unit_level(uk)
                    # 只有战士时，强制选远程
                    if len(self.run.units) == 1 and cur == 0:
                        ut = UNIT_TYPES.get(uk)
                        if ut and ut.is_ranged and uk in {"archer", "mage", "frost_archer"}:  # 弓手/法师/冰弓
                            return 9000.0  # 高优先级
                        else:
                            return -1e6  # 非远程直接排除

                # === 祝福：教官光环 - 调整购买倾向 ===
                if blessing == "veteran_mentor" and t == "unit":
                    uk = str(it.get("payload") or "")
                    ut = UNIT_TYPES.get(uk)
                    cur = self._current_unit_level(uk)

                    # 战士升级：高优先级（确保战士够肉）
                    if uk == "warrior":
                        if cur == 1:  # Lv1→2 是质变
                            return 8000.0
                        elif cur == 2:  # Lv2→3 锦上添花
                            return 6000.0

                    # 远程/DPS单位：次优先级（享受攻速buff）
                    if ut and (ut.is_ranged or "dps" in getattr(ut, "tags", [])):
                        return 7000.0 - (cur * 500)

                    # 其他坦克：降低优先级（会被替换成战士）
                    if ut and "tank" in getattr(ut, "tags", []) and uk != "warrior":
                        return 3000.0
                
                # 目标：至少买到 1 个技能。但弱化"攒钱"限制，因为商店频繁，第一次买不起第二次基本能买得起。
                if need_first_skill:
                    if t == "skill":
                        return 5000.0  # 能买则必买（覆盖目标）
                    # 永远不亏的物品：锻造器和已有兵种升级，允许购买（不检查"攒技能钱"）
                    if t == "forge_device":
                        return 200.0 if self.build_plan_id in ("forge_growth",) else 80.0
                    if t == "unit":
                        uk = str(it.get("payload") or "")
                        cur = self._current_unit_level(uk)
                        # 已有兵种升级：永远不亏，允许购买
                        if cur > 0:
                            return 700.0 - cur * 60.0
                    # 买不起技能时：允许买一次"主力兵种升级"，用来提高存活率
                    if t == "unit" and skill_price_in_shop is not None and int(self.run.state.gold) < int(skill_price_in_shop):
                        uk = str(it.get("payload") or "")
                        cur = self._current_unit_level(uk)
                        if uk == primary and int(cur) == 1:
                            return 2500.0
                    # 弱化限制：只要保留 50% 技能价格即可（因为商店频繁，不需要严格攒钱）
                    if skill_price_in_shop is not None:
                        gold_after = int(self.run.state.gold) - p
                        # 从"必须保留完整技能价格"改为"保留25%技能价格"
                        if gold_after < int(skill_price_in_shop * 0.2):
                            return -1e6
                if t == "skill":
                    # 达到首个技能后：非技能流不再买技能；技能流最多买到 max_skills
                    if len(self.run.skills) >= max_skills:
                        return -1e6
                    if not is_skill_build:
                        return -1e6
                    return 900.0
                if t == "unit":
                    uk = str(it.get("payload"))
                    cur = self._current_unit_level(uk)
                    # 优先补未满级
                    base = 700.0 - cur * 60.0
                    return base
                if t == "forge_device":
                    return 200.0 if self.build_plan_id in ("forge_growth",) else 80.0
                return 0.0
            ranked.sort(key=score, reverse=True)
            best = ranked[0] if ranked else None
            if best and score(best) > 0:
                price = int(best.get("price", 0) or 0)
                if price <= int(self.run.state.gold):
                    self.run.state.gold -= price
                    self._shop_spent += price
                    best["sold"] = True
                    bought = True
                    buys += 1
                    self._shop_actions.append(
                        {
                            "action": "buy",
                            "type": str(best.get("type") or ""),
                            "payload": str(best.get("payload") or ""),
                            "price": int(price),
                            "gold_after": int(self.run.state.gold),
                            "day": int(self.run.state.day),
                            "battle_count": int(self.run.state.battle_count),
                        }
                    )
                    if best["type"] == "skill":
                        sk = str(best["payload"])
                        if sk not in self.run.skills:
                            self.run.skills.append(sk)
                    elif best["type"] == "unit":
                        uk = str(best["payload"])
                        cur = self._current_unit_level(uk)
                        new_level = cur + 1 if cur > 0 else 1
                        self._set_unit_level(uk, new_level)
                    elif best["type"] == "forge_device":
                        # 购买后立刻执行一次锻造（并回到商店）
                        self._forge_step(from_shop=True)

            if bought:
                # 达到单店购买上限后离店；否则继续在本店选下一件（不刷新）
                if buys >= buy_limit:
                    break
                continue

            # 尝试刷新
            if refresh_limit <= 0:
                break
            
            # === 祝福：贪婪契约 - 禁止付费刷新，只用免费刷新和半价买货 ===
            
            # 没拿到首个技能前：如果买不起技能，刷新也没意义（技能必出），直接存钱离店
            if need_first_skill and skill_price_in_shop is not None and int(self.run.state.gold) < int(skill_price_in_shop):
                break
            if self.run.shop_free_refresh_left > 0:
                self.run.shop_free_refresh_left -= 1
                items = self._roll_shop_items(price_mult)
                refresh_limit -= 1
                self._shop_actions.append(
                    {
                        "action": "refresh",
                        "mode": "free",
                        "cost": 0,
                        "day": int(self.run.state.day),
                        "battle_count": int(self.run.state.battle_count),
                    }
                )
                continue

            # 付费刷新：n 次递增
            n = self.run.shop_refresh_paid_count + 1
            cost = SHOP_REFRESH_BASE_COST * n
            if self.run.blessing_selected == "direct_invest":
                cost = int(math.ceil(cost * 1.2))
            if self.run.state.gold < cost:
                break
            self.run.state.gold -= cost
            self._shop_spent += cost
            self.run.shop_refresh_paid_count += 1
            self._shop_refresh_total += 1
            items = self._roll_shop_items(price_mult)
            refresh_limit -= 1
            self._shop_actions.append(
                {
                    "action": "refresh",
                    "mode": "paid",
                    "cost": int(cost),
                    "gold_after": int(self.run.state.gold),
                    "day": int(self.run.state.day),
                    "battle_count": int(self.run.state.battle_count),
                }
            )

    # === Event ===
    def _event_pick(self) -> str:
        rng = self.run.fork_rng("event_pick")
        templates = ["E1", "E2", "E3", "E4", "E5", "E6"]
        recent = set((self.run.recent_event_templates or [])[-2:])
        candidates = [t for t in templates if t not in recent] or templates[:]
        tid = rng.choice(candidates)
        self.run.event_template_id = tid
        self.run.recent_event_templates.append(tid)
        self.run.recent_event_templates = self.run.recent_event_templates[-2:]
        return tid

    def _event_apply_choice(self, choice_idx: int) -> None:
        tid = self.run.event_template_id or self._event_pick()
        seg = _rep_segment(self.run.reputation)
        rng = self.run.fork_rng(f"event:{tid}:{seg}")
        gold_delta = 0

        if tid == "E1":
            if seg == "saint":
                if choice_idx == 0:
                    self.run.oneshot.next_shop_price_mult_once = 0.9
                else:
                    gold_delta -= EVENT_GOLD_SMALL
                    self.run.oneshot.next_shop_free_refresh_bonus += 1
            elif seg == "demon":
                if choice_idx == 0:
                    gold_delta += EVENT_GOLD_MED
                    self.run.oneshot.next_shop_free_refresh_disabled = True
                else:
                    gold_delta -= EVENT_GOLD_LARGE
                    self.run.oneshot.next_shop_price_mult_once = 0.75
            else:
                if choice_idx == 0:
                    gold_delta -= EVENT_GOLD_SMALL
                else:
                    if rng.random() < 0.5:
                        pass
                    else:
                        gold_delta -= EVENT_GOLD_MED

        elif tid == "E3":
            if seg == "demon":
                if choice_idx == 0:
                    gold_delta -= EVENT_GOLD_MED
                    self.run.oneshot.next_combo_bias_once = True
                else:
                    self.run.oneshot.next_combo_reroll_once = True
                    self.run.oneshot.next_shop_price_mult_once = 1.25
            elif seg == "saint":
                if choice_idx == 0:
                    gold_delta -= EVENT_GOLD_MED
                    self.run.oneshot.next_combo_reroll_once = True
                else:
                    gold_delta += EVENT_GOLD_SMALL
            else:
                if choice_idx == 0:
                    gold_delta -= EVENT_GOLD_SMALL
                    self.run.oneshot.next_combo_reroll_once = True
                else:
                    if rng.random() < 0.5:
                        self.run.oneshot.next_combo_reroll_once = True
                    else:
                        pass
        else:
            if choice_idx == 0:
                gold_delta += EVENT_GOLD_SMALL
            else:
                if rng.random() < 0.5:
                    pass
                else:
                    gold_delta -= EVENT_GOLD_MED

        self.run.state.gold = max(0, int(self.run.state.gold) + int(gold_delta))
        self._event_net += int(gold_delta)
        self._event_actions.append(
            {
                "template": str(tid),
                "choice": int(choice_idx),
                "seg": str(seg),
                "gold_delta": int(gold_delta),
                "gold_after": int(self.run.state.gold),
                "day": int(self.run.state.day),
                "battle_count": int(self.run.state.battle_count),
            }
        )

    def _event_visit(self) -> None:
        # 追踪事件访问次数（用于 Combo 触发条件）
        self.run.events_visited = int(getattr(self.run, "events_visited", 0) or 0) + 1
        
        self._event_pick()
        # 中 Bot：默认选择 A；若 build 偏经济/技能且 A 亏太多时可选 B（这里先简单）
        choice = 0
        self._event_apply_choice(choice)

    # === Forge ===
    def _forge_substat_mult(self) -> float:
        if self.run.blessing_selected == "logistics_stable":
            return 0.8
        return 1.0

    def _forge_retarget_cost(self, is_retarget: bool, target_unit: str | None = None) -> int:
        """改锻费用：基于目标兵种的总锻造等级定价（与 main.py 保持一致）"""
        if not is_retarget or not target_unit:
            return 0
        # 计算目标兵种的总锻造等级（攻+防）
        off_lvl = self.run.forge.offense_level_by_unit.get(target_unit, 0)
        def_lvl = self.run.forge.defense_level_by_unit.get(target_unit, 0)
        total_level = off_lvl + def_lvl
        
        # 基础费用 + 每个等级增加的费用
        base = FORGE_RETARGET_BASE_COST + (total_level * FORGE_RETARGET_PER_LEVEL_COST)
        
        # 祝福：军械拨款 → 费用更便宜（-30%）
        if self.run.blessing_selected == "arms_grant":
            base = int(math.ceil(base * 0.7))
        # Combo：锻造工会 → 改锻费用 -20%
        if "combo_forge_discount" in self.run.combo.selected_cards:
            base = int(math.ceil(base * 0.8))
        return base

    def _forge_next_success_chance(self, next_level: int) -> float:
        # 基础：1级100%，2级50%，3级25%，4级25%（匠人精神），5级10%（匠人精神）
        if next_level <= 1:
            p = 1.0
        elif next_level == 2:
            p = 0.5
        elif next_level == 3:
            p = 0.25
        elif next_level == 4:
            p = FORGE_LEVEL_4_SUCCESS_RATE if self.run.blessing_selected == "craftsman_spirit" else 0.0
        elif next_level == 5:
            p = FORGE_LEVEL_5_SUCCESS_RATE if self.run.blessing_selected == "craftsman_spirit" else 0.0
        else:
            p = 0.0
        
        # 祝福：不屈之志 - 非战士成功率减半（这里不实现，已在main.py实现）
        # 祝福：匠人精神 - 成功率100%
        if self.run.blessing_selected == "craftsman_spirit":
            p = 1.0
        
        return max(0.0, min(1.0, float(p)))

    def _forge_default_target(self) -> str | None:
        if not self.run.units:
            return None
        # 老兵主角模式：除非拿了"不屈之志"，否则锻造名单排除战士（Q）
        forge_candidates = self.run.units
        if self.run.blessing_selected != "veteran_unyielding":
            forge_candidates = [k for k in self.run.units if k != "warrior"]
        if not forge_candidates:
            return None
        counts = self.run.forge.spawn_count_by_unit
        min_count = min(counts.get(k, 0) for k in forge_candidates)
        ties = [k for k in forge_candidates if counts.get(k, 0) == min_count]
        if len(ties) == 1:
            return ties[0]
        last = self.run.forge.last_target_unit
        if last in ties and len(ties) > 1:
            candidates = [k for k in ties if k != last]
        else:
            candidates = ties
        rng = self.run.fork_rng("forge_default_tie")
        return rng.choice(candidates)

    def _forge_step(self, from_shop: bool = False) -> None:
        blessing = getattr(self.run, "blessing_selected", "")
        target = self._forge_default_target()
        if not target:
            return
        
        # Bot简化策略：优先攻击，除非攻击已满级
        max_level = 5 if blessing == "craftsman_spirit" else 3
        off_lvl = int(self.run.forge.offense_level_by_unit.get(target, 0))
        def_lvl = int(self.run.forge.defense_level_by_unit.get(target, 0))
        
        # === 祝福：不屈之志 - 优先把战士锻到满级 ===
        if blessing == "veteran_unyielding" and target == "warrior":
            # 优先攻击满，再防御满
            if off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        # === 祝福：匠人精神 - 优先冲高等级 ===
        elif blessing == "craftsman_spirit":
            # 哪个等级更高就优先冲哪个
            if off_lvl >= def_lvl and off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        # === 默认逻辑：优先攻击 ===
        else:
            if off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        
        next_lvl = cur_lvl + 1
        p = self._forge_next_success_chance(next_lvl)
        rng = self.run.fork_rng(f"forge:{target}:{chosen_dir}:{next_lvl}")
        ok = rng.random() < p
        if ok:
            if chosen_dir == "offense":
                self.run.forge.offense_level_by_unit[target] = next_lvl
            else:
                self.run.forge.defense_level_by_unit[target] = next_lvl
        self.run.forge.last_target_unit = target
        self.run.forge.last_direction = chosen_dir

    def _forge_step_random(self) -> None:
        """随机选择一个可锻造兵种，执行一次锻造。"""
        blessing = getattr(self.run, "blessing_selected", "")
        if not self.run.units:
            return
        candidates = list(self.run.units)
        if blessing != "veteran_unyielding":
            candidates = [k for k in candidates if k != "warrior"]
        if not candidates:
            return
        rng = self.run.fork_rng("forge_random_target")
        target = rng.choice(candidates)
        
        # Bot简化策略：优先攻击，除非攻击已满级
        max_level = 5 if blessing == "craftsman_spirit" else 3
        off_lvl = int(self.run.forge.offense_level_by_unit.get(target, 0))
        def_lvl = int(self.run.forge.defense_level_by_unit.get(target, 0))
        
        # === 祝福：不屈之志 - 优先把战士锻到满级 ===
        if blessing == "veteran_unyielding" and target == "warrior":
            if off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        # === 祝福：匠人精神 - 优先冲高等级 ===
        elif blessing == "craftsman_spirit":
            if off_lvl >= def_lvl and off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        else:
            if off_lvl < max_level:
                chosen_dir = "offense"
                cur_lvl = off_lvl
            elif def_lvl < max_level:
                chosen_dir = "defense"
                cur_lvl = def_lvl
            else:
                self.run.forge.last_target_unit = target
                return
        
        next_lvl = cur_lvl + 1
        p = self._forge_next_success_chance(next_lvl)
        rng = self.run.fork_rng(f"forge_random:{target}:{chosen_dir}:{next_lvl}")
        ok = rng.random() < p
        if ok:
            if chosen_dir == "offense":
                self.run.forge.offense_level_by_unit[target] = next_lvl
            else:
                self.run.forge.defense_level_by_unit[target] = next_lvl
        self.run.forge.last_target_unit = target
        self.run.forge.last_direction = chosen_dir

    # === Prisoners / Blessing ===
    def _init_prisoners_for_battle(self, ai_pool: list[str], enemy_spawned: list[str]) -> None:
        self.run.prisoner_queue = []
        self.run.prisoner_idx = 0
        self.run.prisoner_action_idx = 0
        self.run.prisoner_message = ""
        
        # === 祝福：匠人精神 - 取消俘虏环节 ===
        if self.run.blessing_selected == "craftsman_spirit":
            self.run.prisoners_inited = True
            return

        rng = self.run.fork_rng("prisoners")
        base_set = enemy_spawned[:] if enemy_spawned else list(ai_pool)
        base_set = [k for k in base_set if k in ORDER_KEYS]
        
        # 过滤：默认情况下战士Q不能通过俘虏获得（除非选了不屈之志）
        if self.run.blessing_selected != "veteran_unyielding":
            base_set = [k for k in base_set if k != "warrior"]
        
        rng.shuffle(base_set)
        k_num = 2

        pool: list[tuple[str, float]] = []
        for uk in base_set:
            w = 1.0
            if self.run.prisoners.joined_once.get(uk):
                w *= 2.0
            if self.run.prisoners.executed_once.get(uk):
                w *= 0.0
            pool.append((uk, w))
        pool = [(uk, w) for uk, w in pool if w > 0]
        if not pool:
            self.run.prisoners_inited = True
            return

        # 祝福：战地募兵官 → 若敌方出现你未拥有兵种，俘虏优先包含其中1个
        if self.run.blessing_selected == "recruit_officer":
            unseen = [uk for uk, _ in pool if uk not in self.run.units]
            if unseen:
                pick = rng.choice(unseen)
                self.run.prisoner_queue.append(pick)
                pool = [(uk, w) for uk, w in pool if uk != pick]

        while len(self.run.prisoner_queue) < k_num and pool:
            items = [uk for uk, _ in pool]
            weights = [w for _, w in pool]
            pick = rng.choices(items, weights=weights, k=1)[0]
            self.run.prisoner_queue.append(pick)
            pool = [(uk, w) for uk, w in pool if uk != pick]

        self.run.prisoners_inited = True

    def _process_prisoners(self) -> None:
        # 计算兵种上限（精兵简政为3，其他为5）
        max_units = 3 if self.run.blessing_selected == "elite_simplicity" else 5
        
        while self.run.prisoner_idx < len(self.run.prisoner_queue):
            uk = self.run.prisoner_queue[self.run.prisoner_idx]
            # 中 Bot：优先"补全兵种/升级"，否则放归（稳定）——让 build 测试更偏战斗策略而不是刷钱
            if uk not in self.run.units and len(self.run.units) < max_units:
                action = 0
            elif uk in self.run.units and self._current_unit_level(uk) < MAX_UNIT_LEVEL:
                action = 0
            else:
                action = 2

            if action == 0:
                if uk not in self.run.units:
                    if len(self.run.units) >= max_units:
                        self.run.state.gold += PRISONER_RELEASE_GOLD
                    else:
                        self.run.units.append(uk)
                        self.run.unit_levels[uk] = 1
                        # 记录获得该兵种时的层数
                        if uk not in self._unit_acquire_layers:
                            current_layer = getattr(self.run.state, "current_layer", 0) or 0
                            self._unit_acquire_layers[uk] = int(current_layer)
                else:
                    cur = int(self.run.unit_levels.get(uk, 1))
                    if cur < MAX_UNIT_LEVEL:
                        extra_cost = 20 if self.run.blessing_selected == "prisoner_ledger" else 0
                        if extra_cost and self.run.state.gold >= extra_cost:
                            self.run.state.gold -= extra_cost
                            self._shop_spent += extra_cost
                        self.run.unit_levels[uk] = min(MAX_UNIT_LEVEL, cur + 1)
                self.run.prisoners.joined_once[uk] = True
            elif action == 1:
                self.run.prisoners.executed_once[uk] = True
                gold = PRISONER_EXECUTE_GOLD
                if self.run.blessing_selected == "thrifty":
                    gold = int(math.floor(gold * 0.8))
                if self.run.blessing_selected == "iron_discipline":
                    gold = int(math.ceil(gold * 1.25))
                gold = int(math.ceil(gold * float(getattr(self.run, "prisoner_gold_mult", 1.0) or 1.0)))
                self.run.state.gold += gold
                rep_delta = -PRISONER_REP_LOSS
                if self.run.blessing_selected == "mercy":
                    rep_delta -= 1
                self.run.reputation = _clamp_reputation(self.run.reputation + rep_delta)
            else:
                gold = PRISONER_RELEASE_GOLD
                if self.run.blessing_selected == "thrifty":
                    gold = int(math.ceil(gold * 1.25))
                if self.run.blessing_selected == "iron_discipline":
                    gold = int(math.floor(gold * 0.85))
                if self.run.blessing_selected == "prisoner_ledger":
                    gold += 30
                gold = int(math.ceil(gold * float(getattr(self.run, "prisoner_gold_mult", 1.0) or 1.0)))
                self.run.state.gold += gold
                rep_delta = +PRISONER_REP_GAIN
                if self.run.blessing_selected == "mercy":
                    rep_delta += 1
                self.run.reputation = _clamp_reputation(self.run.reputation + rep_delta)

            self.run.prisoner_idx += 1

    def _maybe_pick_blessing(self) -> bool:
        """返回是否本次触发并选择了祝福。"""
        if not self.run.state:
            return False
        if (self.run.state.battle_count >= int(BLESSING_TRIGGER_BATTLE_COUNT)) and (not self.run.blessing_taken):
            rng = self.run.fork_rng("blessing")
            pool = list(BLESSINGS.keys())
            rng.shuffle(pool)
            options = pool[:4] if len(pool) >= 4 else pool[:]
            # 中 Bot：均匀随机选一个（避免偏差，利于测 build）
            if options:
                pick = rng.choice(options)
                self.run.blessing_selected = pick
                self.run.blessing_taken = True
                if not self._milestone.get("blessing"):
                    self._milestone["blessing"] = {
                        "id": str(pick),
                        "battle_count": int(self.run.state.battle_count),
                        "day": int(self.run.state.day),
                    }
                
                # === 祝福：不屈意志 - 开局奖励 ===
                if pick == "veteran_unyielding":
                    # 战士升至2级
                    self.run.unit_levels["warrior"] = 2
                    # 攻击锻造+2
                    self.run.forge.offense_level_by_unit["warrior"] = 2
                    # 防御锻造+2
                    self.run.forge.defense_level_by_unit["warrior"] = 2
                
                # === 祝福：匠人精神 - 赠送 3 次随机锻造 ===
                if pick == "craftsman_spirit":
                    for _ in range(3):
                        self._forge_step_random()
                
                # === 祝福：掠夺者逻辑 - 立即获得金币 ===
                if pick == "looter_logic":
                    self.run.state.gold = int(getattr(self.run.state, "gold", 0) or 0) + 200
                
                return True
        return False

    # === Battle ===
    def _campaign_node_enemy_units(self, state: CampaignState, node_id: int, total_campaign_stages: int) -> list[str]:
        node = state.nodes.get(node_id)
        if not node:
            return []
        if node.node_type not in CAMPAIGN_BATTLE_NODE_TYPES or node.cleared:
            return []
        stage_idx = state.difficulty_index(node.node_type, total_campaign_stages)
        stage_idx = max(0, min(stage_idx, len(CAMPAIGN_PARAMS["ai_pool_sizes"]) - 1))
        ai_k = CAMPAIGN_PARAMS["ai_pool_sizes"][stage_idx]
        ai_k = max(1, min(ai_k, len(ORDER_KEYS)))
        base_seed = getattr(node, "ai_seed", node.node_id * 131)
        seed = (base_seed << 7) ^ (state.battle_count + 1) ^ (stage_idx << 11)
        rng = self.run.fork_rng(f"enemy_pool:{seed}")
        
        # 第0层禁止出现战士(warrior)、犀牛(rhino)、自爆车(exploder) - 避免开局过难
        available_keys = list(ORDER_KEYS)
        if node.layer_index == 0:
            available_keys = [k for k in ORDER_KEYS if k not in ("warrior", "rhino", "exploder")]
            ai_k = min(ai_k, len(available_keys))
        
        if ai_k >= len(available_keys):
            return list(available_keys)
        return rng.sample(available_keys, ai_k)

    def _battle_modifiers(self, node_type: str, day: int) -> dict[str, Any]:
        enemy_damage_mult = 1.0
        enemy_hp_mult = 1.0
        current_day = max(1, int(day))
        enemy_damage_mult += (current_day - 1) * CAMPAIGN_ENEMY_DAMAGE_GROWTH
        enemy_hp_mult += (current_day - 1) * CAMPAIGN_ENEMY_HP_GROWTH
        if node_type == "elite":
            enemy_damage_mult += 0.15
        # 与 main.py 一致：叠加“超时惨胜惩罚系数”（使后续敌方更强）
        penalty_coeff = float(getattr(self.run, "timeout_penalty_coeff", 1.0) or 1.0)
        modifiers: dict[str, Any] = {
            "right_damage_mult": enemy_damage_mult * penalty_coeff,
            "right_hp_mult": enemy_hp_mult * penalty_coeff,
            "right_base_hp_mult": enemy_hp_mult * penalty_coeff,
            "campaign_day": day,  # 传递天数给Game用于祝福判定
        }

        # ============================================================
        # ✅ 祝福落地（与 main.py 保持一致）
        # 说明：
        # - 这里负责把“战斗内会影响数值/规则”的祝福写入 modifiers
        # - MidBattleBot 的出兵逻辑只负责“操作倾向”，不负责数值落地
        # ============================================================
        blessing = str(self.run.blessing_selected or "")

        if blessing == "veteran_mentor":
            # 教官光环：老兵HP+60%/伤害-40%，正后方单位+6%攻速+6%伤害
            modifiers["veteran_q_hp_mult"] = 1.60
            modifiers["veteran_q_damage_mult"] = 0.60
            modifiers["veteran_mentor_atkspd_bonus"] = 0.06
            modifiers["veteran_mentor_damage_bonus"] = 0.06
        elif blessing == "veteran_sacrifice":
            # 英雄祭献：5关后禁用Q，其他单位+50%
            modifiers["veteran_sacrifice_hp_mult"] = 1.5
            modifiers["veteran_sacrifice_damage_mult"] = 1.5
            modifiers["veteran_sacrifice_day_limit"] = 5 if current_day >= 5 else 999
        elif blessing == "elite_simplicity":
            # 精兵简政：全属性+30%
            modifiers["left_damage_mult"] = float(modifiers.get("left_damage_mult", 1.0)) * 1.30
            modifiers["left_hp_mult"] = float(modifiers.get("left_hp_mult", 1.0)) * 1.30
            modifiers["left_unit_speed_mult"] = float(modifiers.get("left_unit_speed_mult", 1.0)) * 1.30
            modifiers["left_unit_atkspd_mult"] = float(modifiers.get("left_unit_atkspd_mult", 1.0)) * 1.30
        elif blessing == "steel_tide":
            # 钢铁洪流：费用/CD减半，HP/伤害-25%
            modifiers["left_cost_mult"] = 0.5
            modifiers["left_cooldown_mult"] = 0.5
            modifiers["left_damage_mult"] = float(modifiers.get("left_damage_mult", 1.0)) * 0.75
            modifiers["left_hp_mult"] = float(modifiers.get("left_hp_mult", 1.0)) * 0.75
        elif blessing == "veteran_last_stand":
            # 破釜沉舟：战士部署费为0，扣基地5点血
            modifiers["veteran_q_free_cost"] = True
            modifiers["veteran_q_base_damage"] = 5
        elif blessing == "tactical_master":
            # 战术大师：技能消耗资源而非击杀数
            modifiers["tactical_master_mode"] = True
        elif blessing == "looter_logic":
            # 掠夺者逻辑：全局金币获取+50%
            modifiers["left_gold_mult"] = 1.5
        elif blessing == "ring_of_destiny":
            # 宿命之环：名声联动（前期更高，后期递减）
            rep = int(getattr(self.run.state, "reputation", 0) or 0)
            abs_rep = abs(rep)
            bonus = 0.0
            if abs_rep > 0:
                bonus += min(abs_rep, 5) * 0.04
                if abs_rep > 5:
                    bonus += min(abs_rep - 5, 5) * 0.02
                if abs_rep > 10:
                    bonus += (abs_rep - 10) * 0.01
            if rep > 0:
                # 圣人路线：攻速加成
                modifiers["left_unit_atkspd_mult"] = float(modifiers.get("left_unit_atkspd_mult", 1.0)) * (1.0 + bonus)
            elif rep < 0:
                # 暴君路线：伤害加成
                modifiers["left_damage_mult"] = float(modifiers.get("left_damage_mult", 1.0)) * (1.0 + bonus)

        # 传递战役天数（用于英雄祭献的day>=5判定）
        modifiers["campaign_day"] = current_day

        # Combo 落地：与main.py保持一致
        combos = self.run.combo.selected_cards
        
        # 基础职能加成 (combo 1-4)
        if "combo_heavy_armor" in combos:
            modifiers["combo_tank_hp_bonus"] = 0.25
        if "combo_sharpened_blades" in combos:
            modifiers["combo_dps_damage_bonus"] = 0.20
        if "combo_medical_kit" in combos:
            modifiers["combo_support_heal_bonus"] = 0.35
        if "combo_disruption" in combos:
            modifiers["combo_control_duration_bonus"] = 0.35
        
        # 基础特性加成 (combo 5-8)
        if "combo_heavy_payload" in combos:
            modifiers["combo_aoe_radius_bonus"] = 0.40
        if "combo_rapid_advance" in combos:
            modifiers["combo_melee_speed_bonus"] = 0.20
        if "combo_light_crossbow" in combos:
            modifiers["combo_ranged_atkspd_bonus"] = 0.15
        if "combo_far_sight" in combos:
            modifiers["combo_ranged_range_bonus"] = 0.15
        
        # 基础全局加成 (combo 9-12)
        if "combo_fortification" in combos:
            modifiers["combo_base_hp_bonus"] = 0.50
        
        # 联动型Combo标记
        if "combo_firm_line" in combos:
            modifiers["combo_firm_line"] = True
        if "combo_combined_arms" in combos:
            modifiers["combo_combined_arms"] = True
        if "combo_dead_recruit" in combos:
            modifiers["combo_dead_recruit"] = True
        if "combo_ice_shatter" in combos:
            modifiers["combo_ice_shatter"] = True
        if "combo_counter_stance" in combos:
            modifiers["combo_counter_stance"] = True
        if "combo_aura_resonance" in combos:
            modifiers["combo_aura_resonance"] = True
        if "combo_overflow_shield" in combos:
            modifiers["combo_overflow_shield"] = True
        if "combo_logistics" in combos:
            modifiers["left_cost_mult"] = float(modifiers.get("left_cost_mult", 1.0)) * 0.9
        if "combo_fast_production" in combos:
            modifiers["combo_spawn_cd_mult"] = 0.85
        if "combo_shock_armor" in combos:
            modifiers["combo_shock_armor"] = True
        if "combo_emergency_protocol" in combos:
            modifiers["combo_emergency_protocol"] = True
        if "combo_full_suppression" in combos:
            modifiers["combo_full_suppression"] = True
        
        return modifiers

    def _apply_combo_modifiers(self, combos: list[str], modifiers: dict, prefix: str = "", apply_cost_modifiers: bool = True) -> None:
        def k(name: str) -> str:
            return f"{prefix}{name}"

        if "combo_heavy_armor" in combos:
            modifiers[k("combo_tank_hp_bonus")] = 0.25
        if "combo_sharpened_blades" in combos:
            modifiers[k("combo_dps_damage_bonus")] = 0.20
        if "combo_medical_kit" in combos:
            modifiers[k("combo_support_heal_bonus")] = 0.35
        if "combo_disruption" in combos:
            modifiers[k("combo_control_duration_bonus")] = 0.35
        if "combo_heavy_payload" in combos:
            modifiers[k("combo_aoe_radius_bonus")] = 0.40
        if "combo_rapid_advance" in combos:
            modifiers[k("combo_melee_speed_bonus")] = 0.20
        if "combo_light_crossbow" in combos:
            modifiers[k("combo_ranged_atkspd_bonus")] = 0.15
        if "combo_far_sight" in combos:
            modifiers[k("combo_ranged_range_bonus")] = 0.15
        if "combo_fortification" in combos:
            modifiers[k("combo_base_hp_bonus")] = 0.50
        if "combo_firm_line" in combos:
            modifiers[k("combo_firm_line")] = True
        if "combo_combined_arms" in combos:
            modifiers[k("combo_combined_arms")] = True
        if "combo_dead_recruit" in combos:
            modifiers[k("combo_dead_recruit")] = True
        if "combo_ice_shatter" in combos:
            modifiers[k("combo_ice_shatter")] = True
        if "combo_counter_stance" in combos:
            modifiers[k("combo_counter_stance")] = True
        if "combo_aura_resonance" in combos:
            modifiers[k("combo_aura_resonance")] = True
        if "combo_overflow_shield" in combos:
            modifiers[k("combo_overflow_shield")] = True
        if "combo_shock_armor" in combos:
            modifiers[k("combo_shock_armor")] = True
        if "combo_emergency_protocol" in combos:
            modifiers[k("combo_emergency_protocol")] = True
        if "combo_full_suppression" in combos:
            modifiers[k("combo_full_suppression")] = True
        if apply_cost_modifiers:
            if prefix == "mirror_":
                if "combo_logistics" in combos:
                    modifiers["right_cost_mult"] = float(modifiers.get("right_cost_mult", 1.0)) * 0.9
                if "combo_fast_production" in combos:
                    modifiers["mirror_combo_spawn_cd_mult"] = 0.85
            else:
                if "combo_logistics" in combos:
                    modifiers["left_cost_mult"] = float(modifiers.get("left_cost_mult", 1.0)) * 0.9
                if "combo_fast_production" in combos:
                    modifiers["combo_spawn_cd_mult"] = 0.85

    def _apply_mirror_blessing_modifiers(self, snapshot: dict, modifiers: dict) -> None:
        blessing = snapshot.get("blessing") or ""
        reputation = int(snapshot.get("reputation", 0) or 0)
        if blessing == "veteran_mentor":
            modifiers["right_veteran_q_hp_mult"] = 1.60
            modifiers["right_veteran_q_damage_mult"] = 0.60
            modifiers["right_veteran_mentor_atkspd_bonus"] = 0.06
            modifiers["right_veteran_mentor_damage_bonus"] = 0.06
        elif blessing == "veteran_sacrifice":
            modifiers["right_veteran_sacrifice_hp_mult"] = 1.5
            modifiers["right_veteran_sacrifice_damage_mult"] = 1.5
            modifiers["right_veteran_sacrifice_day_limit"] = 5
        elif blessing == "elite_simplicity":
            modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * 1.30
            modifiers["right_hp_mult"] = float(modifiers.get("right_hp_mult", 1.0)) * 1.30
            modifiers["right_unit_speed_mult"] = float(modifiers.get("right_unit_speed_mult", 1.0)) * 1.30
            modifiers["right_unit_atkspd_mult"] = float(modifiers.get("right_unit_atkspd_mult", 1.0)) * 1.30
        elif blessing == "steel_tide":
            modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * 0.75
            modifiers["right_hp_mult"] = float(modifiers.get("right_hp_mult", 1.0)) * 0.75
            modifiers["right_cost_mult"] = float(modifiers.get("right_cost_mult", 1.0)) * 0.5
            modifiers["right_cooldown_mult"] = float(modifiers.get("right_cooldown_mult", 1.0)) * 0.5
        elif blessing == "veteran_last_stand":
            modifiers["right_veteran_q_free_cost"] = True
            modifiers["right_veteran_q_base_damage"] = 5
        elif blessing == "ring_of_destiny":
            if reputation > 0:
                modifiers["right_unit_atkspd_mult"] = float(modifiers.get("right_unit_atkspd_mult", 1.0)) * (1.0 + reputation * 0.015)
            elif reputation < 0:
                modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * (1.0 + abs(reputation) * 0.015)

    def _build_forge_payload_from_snapshot(self, snapshot: dict) -> dict[str, tuple[int, int]]:
        units = list(snapshot.get("units") or [])
        offense = snapshot.get("forge_offense") or {}
        defense = snapshot.get("forge_defense") or {}
        payload: dict[str, tuple[int, int]] = {}
        for uk in units:
            off_lvl = int(offense.get(uk, 0) or 0)
            def_lvl = int(defense.get(uk, 0) or 0)
            if off_lvl > 0 or def_lvl > 0:
                payload[uk] = (off_lvl, def_lvl)
        return payload

    def _run_battle(self, node_id: int) -> tuple[bool, float, dict[str, Any]]:
        state = self.run.state
        assert state is not None
        node = state.nodes[node_id]
        total_campaign_stages = len(CAMPAIGN_PARAMS["ai_pool_sizes"])
        stage_idx = state.difficulty_index(node.node_type, total_campaign_stages)
        stage_idx = max(0, min(stage_idx, total_campaign_stages - 1))
        ai_pool = self._campaign_node_enemy_units(state, node_id, total_campaign_stages)
        if not ai_pool:
            ai_k = CAMPAIGN_PARAMS["ai_pool_sizes"][stage_idx]
            ai_k = max(1, min(ai_k, len(ORDER_KEYS)))
            rng = self.run.fork_rng("enemy_pool_fallback")
            ai_pool = rng.sample(ORDER_KEYS, ai_k)
        interval = CAMPAIGN_PARAMS["ai_interval_mult"][stage_idx]
        player_levels = {k: max(1, self.run.unit_levels.get(k, 1)) for k in self.run.units}
        modifiers = self._battle_modifiers(node.node_type, state.day)
        mirror_snapshot = dict(self.run.mirror_snapshot or {})
        mirror_script = list(self.run.mirror_script or [])
        mirror_active = bool(node.node_type == "boss" and mirror_snapshot and mirror_script)

        # === AI 资源渐进增长（非镜像Boss）===
        # 目标：开局资源不变；从第5关开始给 AI 回资源一个线性增长，用于平衡关卡难度。
        if not mirror_active:
            stage_num = int(stage_idx) + 1  # 第1关=1
            start_stage = int(AI_RESOURCE_GROWTH_START_STAGE)
            if stage_num >= start_stage:
                steps = stage_num - start_stage + 1  # 第5关 steps=1
                res_mult = 1.0 + float(AI_RESOURCE_GROWTH_PER_STAGE) * float(steps)
                cap_mult = 1.0 + float(AI_RESOURCE_CAP_GROWTH_PER_STAGE) * float(steps)
                modifiers["right_resource_mult"] = float(res_mult)
                modifiers["right_res_cap"] = int(MAX_RESOURCE * cap_mult)

        mirror_ai_unit_levels: dict[str, int] | None = None
        mirror_right_forge: dict[str, tuple[int, int]] | None = None
        mirror_right_forge_substat_mult = 1.0
        if mirror_active:
            mirror_units = list(mirror_snapshot.get("units") or [])
            if mirror_units:
                ai_pool = mirror_units
            mirror_ai_unit_levels = dict(mirror_snapshot.get("unit_levels") or {})
            mirror_right_forge = self._build_forge_payload_from_snapshot(mirror_snapshot)
            if mirror_snapshot.get("blessing") == "logistics_stable":
                mirror_right_forge_substat_mult = 0.8
            modifiers["bases_to_win"] = LANE_COUNT
            modifiers["disable_ai"] = True
            modifiers["mirror_apply_right"] = True
            modifiers["right_damage_mult"] = 1.0
            modifiers["right_hp_mult"] = 1.0
            modifiers["right_base_hp_mult"] = 1.0
            modifiers["right_unit_speed_mult"] = 1.0
            modifiers["right_unit_atkspd_mult"] = 1.0
            self._apply_mirror_blessing_modifiers(mirror_snapshot, modifiers)
            self._apply_combo_modifiers(list(mirror_snapshot.get("combo") or []), modifiers, prefix="mirror_", apply_cost_modifiers=True)

        game = Game(
            self.run.units,
            self.run.skills,
            ai_keys=ai_pool,
            ai_interval_mult=interval,
            boons={},  # 战役内移除 boon
            left_base_hps=self.run.saved_left_base_hps,
            modifiers=modifiers,
            player_unit_levels=player_levels,
            left_forge=self._build_left_forge_payload(),
            left_forge_substat_mult=self._forge_substat_mult(),
            ai_unit_levels=mirror_ai_unit_levels,
            right_forge=mirror_right_forge,
            right_forge_substat_mult=mirror_right_forge_substat_mult,
        )
        if mirror_active:
            game.set_mirror_script(mirror_script)
        self.run.saved_left_base_hps = None

        bot_rng = self.run.fork_rng("battle_bot")
        mirror_recording: list[dict] = []
        record_fn = mirror_recording.append if node.node_type == "boss" else None
        bot = MidBattleBot(
            bot_rng,
            blessing=self.run.blessing_selected,
            campaign_state=self.run.state,
            record_event=record_fn,
        )
        if node.node_type == "boss":
            self._last_boss_recording = mirror_recording
            self._last_boss_mirror_active = mirror_active
            self._last_boss_mirror_blessing = str(mirror_snapshot.get("blessing") or "")
            self._last_boss_mirror_build_plan = str(mirror_snapshot.get("build_plan") or "")

        # 本场“基地总血量”起始快照：用于时间打满时的代理胜负判定（本场净基地伤害）
        start_left_hp_sum = _sum_base_hp(game.left_bases)
        start_right_hp_sum = _sum_base_hp(game.right_bases)

        max_time = float(DEFAULT_RUN.get("battle_max_time_sec", 180.0))
        dt_step = float(DEFAULT_RUN.get("battle_dt", 0.10))
        wall_limit = float(DEFAULT_RUN.get("battle_wall_time_sec", 2.5))
        t = 0.0
        wall_start = time.perf_counter()
        timed_out = False  # walltime 触发（真实耗时上限）
        time_limit_hit = False  # simtime 触发（模拟时长上限）
        while (not game.winner) and t < max_time:
            if wall_limit > 0 and (time.perf_counter() - wall_start) > wall_limit:
                timed_out = True
                break
            bot.step(game, dt_step)
            game.update(dt_step)
            t += dt_step

        if (not timed_out) and (not game.winner) and t >= max_time:
            time_limit_hit = True

        left_destroyed = _count_destroyed(game.left_bases)
        right_destroyed = _count_destroyed(game.right_bases)
        left_hp_sum = _sum_base_hp(game.left_bases)
        right_hp_sum = _sum_base_hp(game.right_bases)
        # ===========================
        # ✅ 胜负判定：与手玩（main.py）保持一致
        # - 正常：依赖 game.winner
        # - 若达到 300s 仍未分胜负：判定为“敌方撤退”，玩家惨胜（强制胜利），并加强后续难度
        # - walltime（真实耗时上限）触发时：同样走该“强制结算”分支，避免“没跑满300秒就判负”
        # ===========================
        forced_timeout = bool(timed_out or time_limit_hit)
        hold_pass = False  # 旧逻辑保留字段（用于报表兼容），但不再参与胜负判定
        if forced_timeout and (not game.winner):
            # 让 battle_time 语义对齐“打满时限”
            try:
                game.battle_time = float(max_time)
            except Exception:
                pass
            game.winner = "left"

            # main.py：超时惩罚系数（破得越多惩罚越低）
            penalty = max(0.0, 0.04 - 0.01 * float(right_destroyed))
            try:
                self.run.timeout_penalty_coeff = float(getattr(self.run, "timeout_penalty_coeff", 1.0) or 1.0) + float(penalty)
            except Exception:
                # 保底：不让统计/结算崩掉
                pass

        # 注意：即使 walltime 触发也不按失败处理；失败只来自 game.winner == "right"
        success = bool(game.winner == "left")
        battle_time = float(getattr(game, "battle_time", t) or t)

        # 战斗统计：出兵次数（用于锻造默认目标）、敌方实际出兵集合T
        battle_counts = getattr(game, "battle_left_spawn_counts", {}) or {}
        self.run.forge.spawn_count_by_unit = {k: int(battle_counts.get(k, 0)) for k in (self.run.units or [])}
        # 整局累计出兵次数
        for uk, c in battle_counts.items():
            try:
                self._run_spawn_counts[str(uk)] = int(self._run_spawn_counts.get(str(uk), 0)) + int(c or 0)
            except Exception:
                pass
        enemy_set = getattr(game, "battle_right_spawned_types", set()) or set()
        enemy_types = sorted(list(enemy_set))

        # 保存基地 HP 继承
        if success:
            self.run.saved_left_base_hps = [float(b.hp) for b in game.left_bases]

        extra = {
            "enemy_pool": list(ai_pool),
            "enemy_spawned": enemy_types,
            "bases_destroyed_left": left_destroyed,
            "bases_destroyed_right": right_destroyed,
            "base_hp_sum_end": left_hp_sum,
            "battle_timeout": 1 if timed_out else 0,
            "battle_time_limit_hit": 1 if time_limit_hit else 0,
            "battle_hold_pass": 1 if hold_pass else 0,
        }
        return success, battle_time, extra

    def _build_left_forge_payload(self) -> dict[str, tuple[int, int]]:
        """返回锻造数据：unit_key -> (攻击等级, 防御等级)"""
        payload: dict[str, tuple[int, int]] = {}
        for uk in self.run.units:
            off_lvl = self.run.forge.offense_level_by_unit.get(uk, 0)
            def_lvl = self.run.forge.defense_level_by_unit.get(uk, 0)
            if off_lvl > 0 or def_lvl > 0:
                payload[uk] = (int(off_lvl), int(def_lvl))
        return payload

    def _battle_reward_amount(self) -> int:
        assert self.run.state is not None
        # 等价于 CampaignState.battle_reward_amount
        base = self.run.state.battle_reward_amount()
        return int(base)

    def _finalize_battle(self, node_id: int, success: bool, battle_time: float) -> None:
        assert self.run.state is not None
        node = self.run.state.nodes.get(node_id)
        if success and node and node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            base_reward = self._battle_reward_amount()
            # 时间奖励：复用 main.py 的三档（写死在 main.py），这里先用同数值
            # 1分钟内 +120，2分钟内 +60，3分钟内 +30
            time_bonus = 0
            if battle_time > 0:
                if battle_time <= 60.0:
                    time_bonus = 120
                elif battle_time <= 120.0:
                    time_bonus = 60
                elif battle_time <= 180.0:
                    time_bonus = 30
            total = base_reward + time_bonus
            mult = float(getattr(self.run, "battle_gold_mult", 1.0) or 1.0)
            total = int(math.ceil(total * max(0.0, mult)))
            self.run.state.gold += total
            self.run.state.mark_battle_completed()
            if node.node_type == "elite":
                self.run.elite_victory_once = True

        if node:
            self.run.state.mark_node_cleared(node.node_id)

    def _choose_combo(self, context: str, pending_node_id: int | None = None) -> None:
        self.run.combo_context = context
        self.run.combo_pending_node_id = pending_node_id
        before = len(self.run.combo.selected_cards or [])
        options = self._roll_combo_options()
        if not options:
            return

        # BuildPlan：均匀随机下，选择策略“主题倾向 + 少量随机”
        plan_tags: set[str] = set()
        if self.build_plan_id in ("econ_snowball",):
            plan_tags = {"经济"}
        elif self.build_plan_id in ("skills_online",):
            plan_tags = {"技能"}
        elif self.build_plan_id in ("forge_growth",):
            plan_tags = {"锻造"}
        elif self.build_plan_id in ("prisoner_growth",):
            plan_tags = {"俘虏"}
        elif self.build_plan_id in ("elite_greed",):
            plan_tags = {"战斗"}
        elif self.build_plan_id in ("aoe_clear", "rush_push", "standard_comp"):
            plan_tags = {"战斗"}

        rng = self.run.fork_rng(f"combo_pick:{context}")
        scored: list[tuple[float, str]] = []
        for cid in options:
            tags = set(COMBO_CARDS.get(cid, {}).get("tags", []) or [])
            s = 0.0
            if plan_tags and tags.intersection(plan_tags):
                s += 2.0
            s += rng.random() * 0.25
            scored.append((s, cid))
        scored.sort(reverse=True)
        pick = scored[0][1]
        # 一次性重抽券：极简实现——如果有券且 pick 不匹配 plan_tags，则重抽一次
        if self.run.oneshot.next_combo_reroll_once and plan_tags:
            tags = set(COMBO_CARDS.get(pick, {}).get("tags", []) or [])
            if not tags.intersection(plan_tags):
                self.run.oneshot.next_combo_reroll_once = False
                options = self._roll_combo_options()
                if options:
                    pick = options[0]
        self._apply_combo_card(pick)
        after = len(self.run.combo.selected_cards or [])
        if after > before:
            self._milestone["combos"].append(
                {
                    "id": str(pick),
                    "reason": str(context),
                    "battle_count": int(self.run.state.battle_count if self.run.state else 0),
                    "day": int(self.run.state.day if self.run.state else 0),
                    "idx": int(after),  # 第几张（1..）
                }
            )

    def _count_nonbattle_if_applicable(self, node) -> None:
        if not node:
            return
        if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            return
        self.run.nonbattle_cleared_count = int(getattr(self.run, "nonbattle_cleared_count", 0) or 0) + 1

    def _milestone_combo_reason(self) -> str:
        if not self.run.state:
            return "unknown"
        bc = int(self.run.state.battle_count or 0)
        shops = int(getattr(self.run, "shops_visited", 0) or 0)
        events = int(getattr(self.run, "events_visited", 0) or 0)
        elite_once = bool(getattr(self.run, "elite_victory_once", False))
        nsel = len(self.run.combo.selected_cards or [])
        
        if nsel <= 0 and bc >= int(COMBO1_TRIGGER_BATTLE_COUNT):
            return "battle3"
        if nsel <= 1 and shops >= 1 and events >= 1:
            return "shop_event"
        if nsel <= 2 and elite_once:
            return "elite_win"
        return "unknown"

    def _maybe_award_milestone_rewards(self) -> None:
        """模拟模式下自动选择祝福/Combo；允许一次性连发（等价于玩家连续确认几次界面）。"""
        # 安全阀：防止未来规则变更导致死循环
        for _ in range(16):
            if not self.run.state:
                return
            bc = int(self.run.state.battle_count or 0)
            shops = int(getattr(self.run, "shops_visited", 0) or 0)
            events = int(getattr(self.run, "events_visited", 0) or 0)
            elite_once = bool(getattr(self.run, "elite_victory_once", False))
            nsel = len(self.run.combo.selected_cards or [])

            # 祝福优先
            if (not self.run.blessing_taken) and (bc >= int(BLESSING_TRIGGER_BATTLE_COUNT)):
                if self._maybe_pick_blessing():
                    continue

            # Combo1（槽位A）：累计 3 场战斗胜利
            if nsel < 1 and bc >= int(COMBO1_TRIGGER_BATTLE_COUNT):
                if getattr(self.run, "weak_start_combo_given", False):
                    # 弱兵种开局：跳过Combo1，直接进入Combo2逻辑
                    pass
                else:
                    self._choose_combo("battle3", pending_node_id=None)
                    continue

            # Combo2（槽位B）：至少进过 1 次商店且 1 次事件
            if nsel < 2 and shops >= 1 and events >= 1:
                self._choose_combo("shop_event", pending_node_id=None)
                continue

            # Combo3（槽位C）：首次击败精英
            if nsel < 3 and elite_once:
                self._choose_combo("elite_win", pending_node_id=None)
                continue

            return
        return

    def _choose_next_node(self, state: CampaignState) -> int | None:
        # 仅向前推进：优先从当前 active_node 的 connections 中选下一层未清节点
        if state.active_node_id is None:
            candidates = [nid for nid in state.layers[0]]
        else:
            cur = state.nodes.get(state.active_node_id)
            if not cur:
                return None
            candidates = [nid for nid in cur.connections if nid in state.nodes]
            # 若为空（极少），fallback 到可用节点
            if not candidates:
                candidates = state.available_nodes()

        candidates = [nid for nid in candidates if (nid in state.nodes and (not state.nodes[nid].cleared))]
        if not candidates:
            return None

        # 打分：build 倾向 + 生存护栏
        rng = self.run.fork_rng("path_pick")
        scored: list[tuple[float, int]] = []
        # 估计“状态”：基地平均血量
        base_hp_ratio = 1.0
        if self.run.saved_left_base_hps:
            base_hp_ratio = float(sum(self.run.saved_left_base_hps) / (LANE_COUNT * BASE_MAX_HP))
        for nid in candidates:
            node = state.nodes[nid]
            t = node.node_type
            s = 0.0
            # 基础分：提高商店优先级（至少高于事件）
            base = {"shop": 2.5, "event": 2.0, "elite": 1.5, "rest": 1.0, "combat": 1.0, "boss": 3.0}.get(t, 0.8)
            s += base

            # --- 2. 战前观察逻辑：克制关系与阵容缺陷 ---
            if t in ("combat", "elite"):
                total_campaign_stages = len(CAMPAIGN_PARAMS["ai_pool_sizes"])
                enemy_pool = self._campaign_node_enemy_units(state, nid, total_campaign_stages) or []
                enemy_set = set(enemy_pool)
                my_units = set(self.run.units or [])

                if enemy_set:
                    # A. 天敌克制 (Strategic Counters)
                    plus = 0
                    for e in enemy_set:
                        if any(e in STRATEGIC_COUNTERS.get(u, set()) for u in my_units):
                            plus += 1
                    minus = 0
                    for u in my_units:
                        if any(u in STRATEGIC_COUNTERS.get(e, set()) for e in enemy_set):
                            minus += 1
                    
                    counter_delta = 0.1 * float(plus - minus)
                    s += max(-0.5, min(0.5, counter_delta))

                    # B. 识别阵容缺陷 (Weakness Detection)
                    # 缺陷 1: AI 几乎没有直接输出单位 (送分关)
                    if all(u in SUPPORT_SET for u in enemy_set):
                        s += 1.2
                    
                    # 检查构筑健康度：至少有一近战一远程
                    bot_has_melee = any(u not in RANGED_SET and u not in SUPPORT_SET for u in my_units)
                    bot_has_ranged = any(u in {"archer", "mage", "frost_archer"} for u in my_units)

                    if bot_has_melee and bot_has_ranged:
                        # 缺陷 2: AI 全是远程 (缺乏坦克)
                        if all(u in RANGED_SET or u in SUPPORT_SET for u in enemy_set):
                            s += 0.4
                        # 缺陷 3: AI 全是近战 (缺乏手长效率)
                        elif all(u not in {"archer", "mage", "frost_archer"} for u in enemy_set):
                            s += 0.3

            # 仅处理“没钱买东西”的情况：金币低于最低商品价时，降低去商店的倾向
            gold_now = int(getattr(state, "gold", 0) or 0)
            if t == "shop" and gold_now < int(SHOP_ITEM_PRICE_LOW):
                s -= 1.2
            # 祝福倾向：够钱时优先走商店
            blessing = str(getattr(self.run, "blessing_selected", "") or "")
            if t == "shop" and gold_now >= int(SHOP_ITEM_PRICE_LOW):
                if blessing == "tactical_master":
                    s += 1.6
                elif blessing == "looter_logic":
                    s += 1.8
            # build 倾向
            if self.build_plan_id == "econ_snowball":
                s += 2.0 if t == "shop" else (0.5 if t == "event" else 0.0)
            elif self.build_plan_id == "skills_online":
                s += 2.0 if t == "shop" else 0.0
            elif self.build_plan_id == "forge_growth":
                s += 1.3 if t == "shop" else 0.0
            elif self.build_plan_id == "prisoner_growth":
                s += 0.6 if t in ("combat", "elite") else 0.0
            elif self.build_plan_id == "elite_greed":
                s += 2.0 if t == "elite" else 0.0
            elif self.build_plan_id == "defensive_counter":
                s += 2.0 if t == "rest" else 0.0
            # 生存护栏：血量低时偏休整/商店
            if base_hp_ratio < 0.55:
                if t == "rest":
                    s += 3.0
                elif t == "shop":
                    s += 1.0
                elif t == "elite":
                    s -= 1.0
            s += rng.random() * 0.35
            scored.append((s, nid))
        scored.sort(reverse=True)
        return scored[0][1]

    def run_one(self) -> EpisodeResult:
        assert self.run.state is not None
        state = self.run.state

        reached_layer = 0
        total_time = 0.0
        last_battle_extra: dict[str, Any] = {}
        boss_encounter = 0
        mirror_encounter = 0
        mirror_win = 0
        mirror_blessing = ""
        mirror_build_plan = ""

        # 从第一层开始一路推到 boss
        steps = 0
        while steps < 2000:
            steps += 1
            # 选择下一节点并移动（会增加 day）
            nid = self._choose_next_node(state)
            if nid is None:
                break
            state.move_to_node(nid)
            node = state.nodes[nid]
            reached_layer = max(reached_layer, int(node.layer_index))
            # 更新当前层数到 state（供兵种获取追踪使用）
            self.run.state.current_layer = reached_layer
            # 路线记录
            self._path_steps.append({"layer": int(node.layer_index), "day": int(state.day), "type": str(node.node_type)})
            self._node_counts[str(node.node_type)] = int(self._node_counts.get(str(node.node_type), 0) or 0) + 1

            # 节点处理
            if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
                success, battle_time, extra = self._run_battle(node.node_id)
                if node.node_type == "boss":
                    boss_encounter = 1
                    mirror_encounter = 1 if getattr(self, "_last_boss_mirror_active", False) else 0
                    mirror_win = 1 if (mirror_encounter and success) else 0
                    mirror_blessing = str(getattr(self, "_last_boss_mirror_blessing", "") or "")
                    mirror_build_plan = str(getattr(self, "_last_boss_mirror_build_plan", "") or "")
                total_time += max(0.0, float(battle_time))
                last_battle_extra = extra
                if not success:
                    # 失败即 run 结束
                    break

                # 战斗胜利结算（金币 + 标记清除）
                self._finalize_battle(node.node_id, True, battle_time)

                # 战后锻造（固定进入一次）
                self._forge_step(from_shop=False)

                # 俘虏生成与处理
                self._init_prisoners_for_battle(extra.get("enemy_pool", []), extra.get("enemy_spawned", []))
                self._process_prisoners()
                self._maybe_award_milestone_rewards()

                # boss 胜利则结束
                if node.node_type == "boss":
                    break
                continue

            if node.node_type == "shop":
                self._shop_visit()
                state.mark_node_cleared(node.node_id)
                self._count_nonbattle_if_applicable(node)
                self._maybe_award_milestone_rewards()
                continue

            if node.node_type == "event":
                self._event_visit()
                state.mark_node_cleared(node.node_id)
                self._count_nonbattle_if_applicable(node)
                self._maybe_award_milestone_rewards()
                continue

            if node.node_type == "rest":
                self.run.saved_left_base_hps = [float(BASE_MAX_HP) for _ in range(LANE_COUNT)]
                state.mark_node_cleared(node.node_id)
                self._count_nonbattle_if_applicable(node)
                self._maybe_award_milestone_rewards()
                continue

            # 其他节点：直接清除
            state.mark_node_cleared(node.node_id)
            self._count_nonbattle_if_applicable(node)
            self._maybe_award_milestone_rewards()

        # 通关口径：路径上的 boss 被清除即视为胜利
        win = 0
        if state.active_node_id is not None:
            n = state.nodes.get(state.active_node_id)
            if n and n.node_type == "boss" and n.cleared:
                win = 1

        units_count = len(self.run.units)
        avg_lvl = 0.0
        if units_count:
            avg_lvl = sum(int(self.run.unit_levels.get(k, 0) or 0) for k in self.run.units) / units_count

        # 若未进行过战斗，基地数据给满血
        base_hp_sum = float(last_battle_extra.get("base_hp_sum_end", LANE_COUNT * BASE_MAX_HP))
        destroyed_left = int(last_battle_extra.get("bases_destroyed_left", 0))
        destroyed_right = int(last_battle_extra.get("bases_destroyed_right", 0))
        battle_timeout = int(last_battle_extra.get("battle_timeout", 0))
        battle_time_limit_hit = int(last_battle_extra.get("battle_time_limit_hit", 0))
        battle_hold_pass = int(last_battle_extra.get("battle_hold_pass", 0))
        
        # 提取敌方兵种信息（最后一场战斗）
        enemy_pool_list = list(last_battle_extra.get("enemy_pool", []))
        enemy_spawned_list = list(last_battle_extra.get("enemy_spawned", []))

        # 系统状态快照（用于报表）
        blessing_selected = str(self.run.blessing_selected or "")
        skills_list = list(self.run.skills or [])
        combo_list = list(self.run.combo.selected_cards or [])
        units_list = list(self.run.units or [])
        unit_levels = {str(k): int(self.run.unit_levels.get(k, 0) or 0) for k in units_list}
        
        # 修复：ForgeState 使用 offense_level_by_unit 和 defense_level_by_unit
        forge_levels = {}
        forge_dirs = {}
        for k in units_list:
            off = int(self.run.forge.offense_level_by_unit.get(k, 0) or 0)
            dfn = int(self.run.forge.defense_level_by_unit.get(k, 0) or 0)
            total = off + dfn
            if total > 0:
                forge_levels[str(k)] = total
                # 记录哪个方向等级更高（用于报表展示）
                if off > dfn:
                    forge_dirs[str(k)] = "offense"
                elif dfn > off:
                    forge_dirs[str(k)] = "defense"
                else:
                    forge_dirs[str(k)] = str(self.run.forge.last_direction or "offense")
        
        forge_max_level = max([0] + list(forge_levels.values()))
        forge_total_levels = int(sum(forge_levels.values())) if forge_levels else 0
        spawn_counts = {k: int(v) for k, v in (self._run_spawn_counts or {}).items() if int(v) > 0}
        spawn_total = int(sum(spawn_counts.values())) if spawn_counts else 0

        def join_tokens(xs: list[str]) -> str:
            xs = [str(x) for x in xs if x]
            return "|".join(xs)

        # 计算出兵排名（前3名）：按出兵次数降序，ties 按 ORDER_KEYS 顺序
        dominant_unit = ""
        second_dominant_unit = ""
        third_dominant_unit = ""
        if self._run_spawn_counts:
            # 按出兵次数排序（降序），ties时按ORDER_KEYS顺序
            sorted_units = sorted(
                [(k, int(self._run_spawn_counts.get(k, 0) or 0)) for k in ORDER_KEYS],
                key=lambda x: (-x[1], ORDER_KEYS.index(x[0]))
            )
            # 取前3名
            if len(sorted_units) >= 1 and sorted_units[0][1] > 0:
                dominant_unit = sorted_units[0][0]
            if len(sorted_units) >= 2 and sorted_units[1][1] > 0:
                second_dominant_unit = sorted_units[1][0]
            if len(sorted_units) >= 3 and sorted_units[2][1] > 0:
                third_dominant_unit = sorted_units[2][0]

        return EpisodeResult(
            version="",
            run_id="",
            seed=self.seed,
            bot_tier=self.bot_tier,
            build_plan_id=self.build_plan_id,
            win=int(win),
            reached_layer=int(reached_layer),
            total_time_sec=float(total_time),
            gold_end=int(state.gold),
            shop_refresh_count=int(self._shop_refresh_total),
            shop_spent=int(self._shop_spent),
            event_net=int(self._event_net),
            units_count=int(units_count),
            avg_unit_level=float(avg_lvl),
            skills_count=int(len(self.run.skills)),
            combo_count=int(len(self.run.combo.selected_cards)),
            base_hp_sum_end=float(base_hp_sum),
            bases_destroyed_left=int(destroyed_left),
            bases_destroyed_right=int(destroyed_right),
            battle_timeout=int(battle_timeout),
            battle_time_limit_hit=int(battle_time_limit_hit),
            battle_hold_pass=int(battle_hold_pass),
            blessing_selected=blessing_selected,
            skills=join_tokens(skills_list),
            combos=join_tokens(combo_list),
            units=join_tokens(units_list),
            unit_levels_json=json.dumps(unit_levels, ensure_ascii=False, separators=(",", ":")),
            forge_levels_json=json.dumps(forge_levels, ensure_ascii=False, separators=(",", ":")),
            forge_dirs_json=json.dumps(forge_dirs, ensure_ascii=False, separators=(",", ":")),
            forge_max_level=int(forge_max_level),
            forge_total_levels=int(forge_total_levels),
            spawn_counts_json=json.dumps(spawn_counts, ensure_ascii=False, separators=(",", ":")),
            spawn_total=int(spawn_total),
            starting_units=join_tokens(getattr(self, "_starting_units", []) or []),
            primary_unit=str(getattr(self, "_primary_unit", "") or ""),
            dominant_unit=str(dominant_unit or ""),
            second_dominant_unit=str(second_dominant_unit or ""),
            third_dominant_unit=str(third_dominant_unit or ""),
            unit_acquire_layers_json=json.dumps(self._unit_acquire_layers or {}, ensure_ascii=False, separators=(",", ":")),
            day_end=int(getattr(state, "day", 0) or 0),
            steps_total=int(steps),
            node_counts_json=json.dumps(self._node_counts or {}, ensure_ascii=False, separators=(",", ":")),
            path_json=json.dumps(self._path_steps or [], ensure_ascii=False, separators=(",", ":")),
            shop_actions_json=json.dumps(self._shop_actions or [], ensure_ascii=False, separators=(",", ":")),
            event_actions_json=json.dumps(self._event_actions or [], ensure_ascii=False, separators=(",", ":")),
            milestone_json=json.dumps(self._milestone or {}, ensure_ascii=False, separators=(",", ":")),
            last_enemy_pool=join_tokens(enemy_pool_list),
            last_enemy_spawned=join_tokens(list(set(enemy_spawned_list))),  # 去重
            boss_encounter=int(boss_encounter),
            mirror_encounter=int(mirror_encounter),
            mirror_win=int(mirror_win),
            mirror_blessing=str(mirror_blessing or ""),
            mirror_build_plan=str(mirror_build_plan or ""),
        )


def _write_episodes_csv(path: Path, episodes: List[EpisodeResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(EpisodeResult.__dataclass_fields__.keys())
    # Windows / Excel 友好：写入 UTF-8 BOM，避免中文列名/内容乱码
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for ep in episodes:
            w.writerow({k: getattr(ep, k) for k in fields})


def _summarize(episodes: List[EpisodeResult], meta: dict) -> dict:
    wins = [ep.win for ep in episodes]
    boss_encounters = [ep.boss_encounter for ep in episodes]
    reached = [float(ep.reached_layer) for ep in episodes]
    gold_end = [float(ep.gold_end) for ep in episodes]
    base_hp_end = [float(ep.base_hp_sum_end) for ep in episodes]
    refresh = [float(ep.shop_refresh_count) for ep in episodes]
    timeouts = [float(ep.battle_timeout) for ep in episodes]
    time_limit_hits = [float(ep.battle_time_limit_hit) for ep in episodes]
    hold_passes = [float(ep.battle_hold_pass) for ep in episodes]

    def _agg(eps: List[EpisodeResult]) -> dict[str, Any]:
        if not eps:
            return {"n": 0, "win_rate": 0.0, "reached_mean": 0.0, "gold_end_mean": 0.0}
        return {
            "n": len(eps),
            "win_rate": _mean([float(e.boss_encounter) for e in eps]),
            "reached_mean": _mean([float(e.reached_layer) for e in eps]),
            "gold_end_mean": _mean([float(e.gold_end) for e in eps]),
            "battle_time_limit_hit_rate": _mean([float(e.battle_time_limit_hit) for e in eps]),
            "battle_hold_pass_rate": _mean([float(e.battle_hold_pass) for e in eps]),
        }

    # === 分组统计：技能 / Combo / 祝福 / 兵种 / 锻造 ===
    by_skill: dict[str, dict[str, Any]] = {}
    for sk in list(SKILL_ORDER) or list(SKILLS.keys()):
        eps = [e for e in episodes if (sk and sk in (e.skills or "").split("|"))]
        by_skill[sk] = _agg(eps)

    by_combo: dict[str, dict[str, Any]] = {}
    for cid in list(COMBO_CARDS.keys()):
        eps = [e for e in episodes if (cid and cid in (e.combos or "").split("|"))]
        by_combo[cid] = _agg(eps)

    by_blessing: dict[str, dict[str, Any]] = {}
    for bid in list(BLESSINGS.keys()):
        eps = [e for e in episodes if (e.blessing_selected == bid)]
        by_blessing[bid] = _agg(eps)

    # 兵种：最终拥有/以及达到 >=2 级
    by_unit_owned: dict[str, dict[str, Any]] = {}
    by_unit_lvl2: dict[str, dict[str, Any]] = {}
    for uk in list(ORDER_KEYS):
        eps_owned = [e for e in episodes if (uk and uk in (e.units or "").split("|"))]
        by_unit_owned[uk] = _agg(eps_owned)
        eps_lvl2: List[EpisodeResult] = []
        for e in episodes:
            try:
                lv = int(json.loads(e.unit_levels_json or "{}").get(uk, 0) or 0)
            except Exception:
                lv = 0
            if lv >= 2:
                eps_lvl2.append(e)
        by_unit_lvl2[uk] = _agg(eps_lvl2)

    # 兵种：首槽(primary) / 使用过(spawn>0) / 第2/3多出兵
    by_unit_primary: dict[str, dict[str, Any]] = {}
    by_unit_used: dict[str, dict[str, Any]] = {}
    by_unit_dominant: dict[str, dict[str, Any]] = {}
    by_unit_second_dominant: dict[str, dict[str, Any]] = {}
    by_unit_third_dominant: dict[str, dict[str, Any]] = {}
    for uk in list(ORDER_KEYS):
        by_unit_primary[uk] = _agg([e for e in episodes if (e.primary_unit or "") == uk])
        by_unit_dominant[uk] = _agg([e for e in episodes if (e.dominant_unit or "") == uk])
        by_unit_second_dominant[uk] = _agg([e for e in episodes if (e.second_dominant_unit or "") == uk])
        by_unit_third_dominant[uk] = _agg([e for e in episodes if (e.third_dominant_unit or "") == uk])
        eps_used: List[EpisodeResult] = []
        for e in episodes:
            try:
                d = json.loads(e.spawn_counts_json or "{}")
                c = float(d.get(uk, 0) or 0)
            except Exception:
                c = 0.0
            if c > 0:
                eps_used.append(e)
        by_unit_used[uk] = _agg(eps_used)

    # 锻造：按 max_level 分桶
    by_forge_max: dict[str, dict[str, Any]] = {}
    for bucket in [0, 1, 2, 3]:
        eps = [e for e in episodes if int(e.forge_max_level) == bucket]
        by_forge_max[str(bucket)] = _agg(eps)

    # 出兵次数：每个兵种（出兵>0 的子集表现 + 出兵次数均值）
    by_unit_spawned: dict[str, dict[str, Any]] = {}
    spawn_avg: dict[str, float] = {}
    spawn_p50: dict[str, float] = {}
    for uk in list(ORDER_KEYS):
        counts: List[float] = []
        eps_spawned: List[EpisodeResult] = []
        for e in episodes:
            try:
                d = json.loads(e.spawn_counts_json or "{}")
                c = float(d.get(uk, 0) or 0)
            except Exception:
                c = 0.0
            counts.append(c)
            if c > 0:
                eps_spawned.append(e)
        spawn_avg[uk] = float(_mean(counts))
        spawn_p50[uk] = float(_percentile(counts, 0.50))
        by_unit_spawned[uk] = _agg(eps_spawned)

    by_build: dict[str, dict[str, Any]] = {}
    for plan in BUILD_PLANS:
        eps = [ep for ep in episodes if ep.build_plan_id == plan]
        if not eps:
            continue
        by_build[plan] = {
            "n": len(eps),
            "win_rate": _mean([float(e.win) for e in eps]),
            "reached_mean": _mean([float(e.reached_layer) for e in eps]),
            "gold_end_mean": _mean([float(e.gold_end) for e in eps]),
        }

    overall = {
        "n": len(episodes),
        "win_rate": _mean([float(b) for b in boss_encounters]),
        "reached_mean": _mean(reached),
        "reached_p50": _percentile(reached, 0.50),
        "reached_p90": _percentile(reached, 0.90),
        "reached_max": float(max(reached)) if reached else 0.0,
        "gold_end_mean": _mean(gold_end),
        "gold_end_p10": _percentile(gold_end, 0.10),
        "gold_end_p90": _percentile(gold_end, 0.90),
        "shop_refresh_mean": _mean(refresh),
        "base_hp_sum_end_mean": _mean(base_hp_end),
        "battle_timeout_rate": _mean(timeouts),
        "battle_time_limit_hit_rate": _mean(time_limit_hits),
        "battle_hold_pass_rate": _mean(hold_passes),
    }

    # === 分布：死亡/到达层数（用于 report 新增直方图）===
    reached_layer_counts: dict[str, int] = defaultdict(int)
    death_layer_counts: dict[str, int] = defaultdict(int)
    for e in episodes:
        try:
            li = int(float(getattr(e, "reached_layer", 0) or 0))
        except Exception:
            li = 0
        reached_layer_counts[str(li)] += 1
        if not bool(getattr(e, "win", 0) or 0):
            death_layer_counts[str(li)] += 1
    total_deaths = int(len(episodes) - sum(int(bool(w)) for w in wins))

    coverage = {
        "avg_skills_count": _mean([float(e.skills_count) for e in episodes]),
        "avg_combo_count": _mean([float(e.combo_count) for e in episodes]),
        "avg_units_count": _mean([float(e.units_count) for e in episodes]),
        "avg_forge_max_level": _mean([float(e.forge_max_level) for e in episodes]),
        "avg_forge_total_levels": _mean([float(e.forge_total_levels) for e in episodes]),
        "blessing_pick_rate": _mean([1.0 if (e.blessing_selected or "") else 0.0 for e in episodes]),
        "avg_spawn_total": _mean([float(e.spawn_total) for e in episodes]),
        # 路线
        "avg_day_end": _mean([float(getattr(e, "day_end", 0) or 0) for e in episodes]),
        "avg_steps_total": _mean([float(getattr(e, "steps_total", 0) or 0) for e in episodes]),
        # 里程碑触发时刻（仅对触发过的样本）
        "blessing_battle_mean": _mean(
            [
                float(json.loads(e.milestone_json or "{}").get("blessing", {}).get("battle_count", 0) or 0)
                for e in episodes
                if (json.loads(e.milestone_json or "{}").get("blessing") is not None)
            ]
        ),
    }

    # 节点类型计数聚合（均值）
    node_types = ["combat", "elite", "boss", "shop", "event", "rest"]
    node_count_mean: dict[str, float] = {}
    for t in node_types:
        vals: list[float] = []
        for e in episodes:
            try:
                d = json.loads(getattr(e, "node_counts_json", "") or "{}")
                vals.append(float(d.get(t, 0) or 0))
            except Exception:
                vals.append(0.0)
        node_count_mean[t] = float(_mean(vals))

    # 商店/事件细节聚合（购买类型、事件模板分布、事件选项分布）
    shop_buy_type_counts: dict[str, int] = defaultdict(int)
    shop_buy_payload_counts: dict[str, int] = defaultdict(int)  # 仅对 skill/unit/forge_device 记录 payload 频次（粗略）
    shop_refresh_free = 0
    shop_refresh_paid = 0
    event_template_counts: dict[str, int] = defaultdict(int)
    event_choice_counts: dict[str, int] = defaultdict(int)  # "0"/"1"
    event_seg_counts: dict[str, int] = defaultdict(int)
    milestone_combo_reason_counts: dict[str, int] = defaultdict(int)
    milestone_combo_battle_by_idx: dict[str, list[int]] = defaultdict(list)  # "1"/"2"/"3" -> [battle_count...]

    for e in episodes:
        # shop actions
        try:
            acts = json.loads(getattr(e, "shop_actions_json", "") or "[]") or []
        except Exception:
            acts = []
        for a in acts:
            if not isinstance(a, dict):
                continue
            if a.get("action") == "refresh":
                if a.get("mode") == "free":
                    shop_refresh_free += 1
                elif a.get("mode") == "paid":
                    shop_refresh_paid += 1
            elif a.get("action") == "buy":
                t = str(a.get("type") or "")
                p = str(a.get("payload") or "")
                if t:
                    shop_buy_type_counts[t] += 1
                if t in ("skill", "unit", "forge_device") and p:
                    shop_buy_payload_counts[f"{t}:{p}"] += 1

        # event actions
        try:
            evs = json.loads(getattr(e, "event_actions_json", "") or "[]") or []
        except Exception:
            evs = []
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            tid = str(ev.get("template") or "")
            if tid:
                event_template_counts[tid] += 1
            event_choice_counts[str(int(ev.get("choice", 0) or 0))] += 1
            seg = str(ev.get("seg") or "")
            if seg:
                event_seg_counts[seg] += 1

        # milestone
        try:
            ms = json.loads(getattr(e, "milestone_json", "") or "{}") or {}
        except Exception:
            ms = {}
        for c in (ms.get("combos") or []):
            if not isinstance(c, dict):
                continue
            reason = str(c.get("reason") or "")
            if reason:
                milestone_combo_reason_counts[reason] += 1
            idx = str(int(c.get("idx", 0) or 0))
            bc = int(c.get("battle_count", 0) or 0)
            if idx in ("1", "2", "3") and bc > 0:
                milestone_combo_battle_by_idx[idx].append(bc)

    return {
        "meta": meta,
        "overall": overall,
        "coverage": coverage,
        "distribution": {
            "reached_layer_counts": dict(reached_layer_counts),
            "death_layer_counts": dict(death_layer_counts),
            "total_deaths": int(total_deaths),
        },
        "route": {
            "node_count_mean": dict(node_count_mean),
        },
        "shop_detail": {
            "refresh_free_total": int(shop_refresh_free),
            "refresh_paid_total": int(shop_refresh_paid),
            "buy_type_counts": dict(shop_buy_type_counts),
            "buy_payload_counts": dict(shop_buy_payload_counts),
        },
        "event_detail": {
            "template_counts": dict(event_template_counts),
            "choice_counts": dict(event_choice_counts),
            "seg_counts": dict(event_seg_counts),
        },
        "milestone_detail": {
            "combo_reason_counts": dict(milestone_combo_reason_counts),
            "combo_battle_mean_by_idx": {
                k: float(_mean([float(x) for x in xs])) if xs else 0.0 for k, xs in milestone_combo_battle_by_idx.items()
            },
        },
        "by_build_plan": by_build,
        "by_skill": by_skill,
        "by_combo": by_combo,
        "by_blessing": by_blessing,
        "by_unit_owned": by_unit_owned,
        "by_unit_lvl2plus": by_unit_lvl2,
        "by_unit_primary": by_unit_primary,
        "by_unit_used": by_unit_used,
        "by_unit_dominant": by_unit_dominant,
        "by_unit_second_dominant": by_unit_second_dominant,
        "by_unit_third_dominant": by_unit_third_dominant,
        "by_forge_max_level": by_forge_max,
        "by_unit_spawned": by_unit_spawned,
        "unit_spawn_avg": spawn_avg,
        "unit_spawn_p50": spawn_p50,
    }


def _render_report_md(summary: dict, episodes: List[EpisodeResult]) -> str:
    """生成新格式的报告：聚合关键洞察，原始数据放入附录"""
    meta = summary.get("meta", {})
    overall = summary.get("overall", {})
    coverage = summary.get("coverage", {}) or {}
    by_build = summary.get("by_build_plan", {}) or {}
    by_skill = summary.get("by_skill", {}) or {}
    by_combo = summary.get("by_combo", {}) or {}
    by_blessing = summary.get("by_blessing", {}) or {}
    by_unit_owned = summary.get("by_unit_owned", {}) or {}
    by_unit_lvl2 = summary.get("by_unit_lvl2plus", {}) or {}
    by_unit_primary = summary.get("by_unit_primary", {}) or {}
    by_unit_used = summary.get("by_unit_used", {}) or {}
    by_unit_dominant = summary.get("by_unit_dominant", {}) or {}
    by_unit_second_dominant = summary.get("by_unit_second_dominant", {}) or {}
    by_unit_third_dominant = summary.get("by_unit_third_dominant", {}) or {}
    by_forge_max = summary.get("by_forge_max_level", {}) or {}
    by_unit_spawned = summary.get("by_unit_spawned", {}) or {}
    unit_spawn_avg = summary.get("unit_spawn_avg", {}) or {}
    unit_spawn_p50 = summary.get("unit_spawn_p50", {}) or {}
    route = summary.get("route", {}) or {}
    shop_detail = summary.get("shop_detail", {}) or {}
    event_detail = summary.get("event_detail", {}) or {}
    milestone_detail = summary.get("milestone_detail", {}) or {}
    dist = summary.get("distribution", {}) or {}

    lines: List[str] = []
    lines.append("# 测试报告（整局 Run）")
    lines.append("")
    lines.append("## 基本信息")
    lines.append(f"- **版本**: **{meta.get('version','')}**")
    lines.append(f"- **运行ID**: **{meta.get('run_id','')}**")
    if meta.get("name"):
        lines.append(f"- **测试名称**: **{meta.get('name','')}**")
    lines.append(f"- **局数(batch)**: **{meta.get('batch','')}**")
    lines.append(f"- **Bot档位**: **{meta.get('bot_tier','')}**")
    lines.append(f"- **Build分配**: **{meta.get('build_mode','')}**")
    if meta.get("note"):
        lines.append(f"- **备注**: {meta.get('note')}")
    if meta.get("battle_dt") is not None:
        lines.append(f"- **战斗dt**: {meta.get('battle_dt')}")
    if meta.get("battle_wall_time_sec") is not None:
        lines.append(f"- **战斗真实耗时上限(秒)**: {meta.get('battle_wall_time_sec')}")
    if meta.get("battle_max_time_sec") is not None:
        lines.append(f"- **战斗模拟时长上限(秒)**: {meta.get('battle_max_time_sec')}")
    lines.append("")
    lines.append("## 总览指标")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---:|")
    key_labels = [
        ("win_rate", "见到Boss概率"),
        ("reached_mean", "到达层数均值"),
        ("reached_p50", "到达层数P50"),
        ("reached_p90", "到达层数P90"),
        ("reached_max", "到达层数最大值"),
        ("gold_end_mean", "最终金币均值"),
        ("gold_end_p10", "最终金币P10"),
        ("gold_end_p90", "最终金币P90"),
        ("shop_refresh_mean", "商店付费刷新均值"),
        ("base_hp_sum_end_mean", "最终基地总HP均值"),
        ("battle_timeout_rate", "战斗超时率"),
        ("battle_time_limit_hit_rate", "战斗打满时限率"),
        ("battle_hold_pass_rate", "打满时限按“本场净基地伤害优势”→判过关率"),
    ]
    for key, label in key_labels:
        val = overall.get(key, 0)
        try:
            if key == "reached_max":
                # 最大值显示为整数
                lines.append(f"| {label} ({key}) | {int(float(val))} |")
            else:
                lines.append(f"| {label} ({key}) | {float(val):.4f} |")
        except Exception:
            lines.append(f"| {label} ({key}) | {val} |")

    lines.append("")
    lines.append("## 系统覆盖（是否“跑起来”）")
    lines.append("")
    lines.append("| 项目 | 数值 |")
    lines.append("|---|---:|")
    for k, label in [
        ("avg_units_count", "平均解锁兵种数(本局最终)"),
        ("avg_skills_count", "平均技能数量"),
        ("avg_combo_count", "平均Combo张数"),
        ("blessing_pick_rate", "祝福触发率(拿到任意祝福)"),
        ("avg_forge_max_level", "平均锻造最高等级"),
        ("avg_forge_total_levels", "平均锻造总等级(各兵种等级求和)"),
        ("avg_spawn_total", "平均总出兵次数(整局累计)"),
        ("avg_day_end", "平均天数(day_end)"),
        ("avg_steps_total", "平均步数(节点数)"),
        ("blessing_battle_mean", "祝福触发战斗数均值(仅触发样本)"),
    ]:
        v = coverage.get(k, 0)
        try:
            lines.append(f"| {label} ({k}) | {float(v):.4f} |")
        except Exception:
            lines.append(f"| {label} ({k}) | {v} |")
    lines.append("")
    
    # ============================================================
    # 新增：逻辑健康度预警面板
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## 🚨 逻辑健康度预警面板 (Logic Health Dashboard)")
    lines.append("")
    lines.append("> **目的**: 快速识别出兵逻辑是否出现\"雪崩\"征兆")
    lines.append("")
    
    # 计算预警指标
    global_avg_reached = float(overall.get("reached_mean", 0.0))
    global_win_rate = float(overall.get("win_rate", 0.0))
    n_total = int(overall.get("n", 0))
    
    # 战士占比 >80% 的局数
    high_warrior_eps = []
    pure_warrior_layers = []
    layer_0_deaths = 0
    
    for ep in episodes:
        try:
            spawn_counts = json.loads(ep.spawn_counts_json) if ep.spawn_counts_json else {}
            q_spawn = spawn_counts.get("warrior", 0)
            total_spawn = sum(spawn_counts.values())
            if total_spawn > 0:
                q_pct = (q_spawn / total_spawn) * 100
                if q_pct > 80:
                    high_warrior_eps.append(ep)
                    pure_warrior_layers.append(ep.reached_layer)
            if ep.reached_layer == 0 and not ep.win:
                layer_0_deaths += 1
        except:
            continue
    
    high_warrior_rate = (len(high_warrior_eps) / n_total * 100) if n_total > 0 else 0
    pure_warrior_avg_layer = sum(pure_warrior_layers) / len(pure_warrior_layers) if pure_warrior_layers else 0
    layer_0_death_rate = (layer_0_deaths / n_total * 100) if n_total > 0 else 0
    avg_units_count = float(coverage.get("avg_units_count", 0.0))
    
    # 破箭数据
    h_owned_rate = 0
    h_win_contrib = 0
    if "interceptor" in by_unit_owned:
        h_data = by_unit_owned["interceptor"]
        h_owned_rate = (h_data.get("n", 0) / n_total * 100) if n_total > 0 else 0
        h_win_rate = float(h_data.get("win_rate", 0.0))
        h_win_contrib = (h_win_rate - global_win_rate) * 100
    
    battle_time_limit_rate = float(overall.get("battle_time_limit_hit_rate", 0.0)) * 100
    
    lines.append("| 预警指标 | 数值 | 阈值 | 状态 |")
    lines.append("|---|---:|---:|:---|")
    
    # 战士占比预警
    warrior_status = "🔴 **严重异常**" if high_warrior_rate > 70 else ("🟡 偏高" if high_warrior_rate > 30 else "✅ 正常")
    lines.append(f"| **战士占比 >80% 的局数比例** | **{high_warrior_rate:.1f}%** ({len(high_warrior_eps)}/{n_total}) | <30% | {warrior_status} |")
    
    # 纯战流平均层数
    pure_warrior_status = "🔴 **严重异常**" if pure_warrior_avg_layer < 4.0 else ("🟡 偏低" if pure_warrior_avg_layer < 6.0 else "✅ 正常")
    lines.append(f"| **纯战流(81-100%)平均层数** | **{pure_warrior_avg_layer:.2f}** | >4.0 | {pure_warrior_status} |")
    
    # Layer 0 死亡率
    l0_status = "🔴 **严重异常**" if layer_0_death_rate > 20 else ("🟡 偏高" if layer_0_death_rate > 10 else "✅ 正常")
    lines.append(f"| **Layer 0 死亡率** | **{layer_0_death_rate:.1f}%** | <10% | {l0_status} |")
    
    # 平均解锁兵种数
    units_status = "🟡 偏低" if avg_units_count < 3.5 else "✅ 正常"
    lines.append(f"| **平均解锁兵种数** | {avg_units_count:.2f} | >3.5 | {units_status} |")
    
    # 破箭拥有率 vs 胜率贡献
    if h_owned_rate > 0:
        h_status = "🟡 资源浪费" if h_win_contrib < -2 else "✅ 正常"
        lines.append(f"| **破箭拥有率 vs 胜率贡献** | {h_owned_rate:.1f}% / {h_win_contrib:+.1f}% | 负贡献<5% | {h_status} |")
    
    # 战斗打满时限率
    time_limit_status = "🟡 输出不足" if battle_time_limit_rate > 15 else "✅ 正常"
    lines.append(f"| **战斗打满时限率** | {battle_time_limit_rate:.1f}% | <15% | {time_limit_status} |")
    
    lines.append("")
    lines.append("**📌 核心问题诊断**:")
    
    issues = []
    if high_warrior_rate > 70:
        pure_warrior_win_rate = sum(1 for ep in high_warrior_eps if ep.win) / len(high_warrior_eps) if high_warrior_eps else 0
        issues.append(f"1. **\"战士陷阱\"**: {high_warrior_rate:.1f}% 的局陷入\"纯战流\"（战士占比 >80%），这些局的通关率为 **{pure_warrior_win_rate*100:.1f}%**，平均层数仅 **{pure_warrior_avg_layer:.2f}**")
    
    if layer_0_death_rate > 20:
        issues.append(f"2. **\"首日猝死\"**: {layer_0_death_rate:.0f}% 的局在 Layer 0 就失败，说明初期数值或出兵逻辑极其脆弱")
    
    if avg_units_count < 3.5:
        # 计算通关局平均兵种数
        win_eps = [ep for ep in episodes if ep.win]
        win_avg_units = sum(ep.units_count for ep in win_eps) / len(win_eps) if win_eps else 0
        issues.append(f"3. **多样性崩溃**: 平均仅解锁 {avg_units_count:.1f} 个兵种，而通关局平均需要 {win_avg_units:.1f}+ 个兵种配合")
    
    if not issues:
        issues.append("✅ 未发现严重问题")
    
    for issue in issues:
        lines.append(issue)
    
    lines.append("")
    lines.append("---")
    lines.append("")

    # === 死亡层数分布（更直观定位"卡关层"）===
    total_deaths = int(dist.get("total_deaths", 0) or 0)
    death_counts = dist.get("death_layer_counts", {}) or {}
    if n_total > 0:
        max_layer = int(float(overall.get("reached_max", 0.0) or 0.0))
        win_count = sum(1 for ep in episodes if ep.win)
        
        lines.append("## 死亡层数分布")
        lines.append("")
        lines.append("> 说明：**当层死亡率** = 该层死亡数 / 到达该层的总人数；**过层后通关率** = 通关总数 / 通过该层的人数")
        lines.append("")
        lines.append("| 层数 | 死亡局数 | 当层死亡率 | 过层后通关率 |")
        lines.append("|---:|---:|---:|---:|")
        
        current_reached = n_total
        for layer in range(0, max_layer + 1):
            deaths = int(death_counts.get(str(layer), 0) or 0)
            death_rate = (deaths / current_reached) if current_reached > 0 else 0.0
            
            # 过了这层的人数 = 当前到达人数 - 在这层死掉的人数
            passed_count = current_reached - deaths
            win_rate_after = (win_count / passed_count) if passed_count > 0 else 0.0
            
            lines.append(f"| {layer} | {deaths} | {death_rate*100:.1f}% | {win_rate_after*100:.1f}% |")
            
            current_reached = passed_count  # 为下一层更新到达人数
        lines.append("")

    lines.append("## 各BuildPlan表现（按见到Boss概率排序）")
    lines.append("")
    rows = []
    for plan, s in by_build.items():
        rows.append((float(s.get("win_rate", 0.0)), plan, s))
    rows.sort(reverse=True)
    lines.append("| BuildPlan | 样本数(n) | 见到Boss概率(win_rate) | 到达层数均值 | 最终金币均值 |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, plan, s in rows:
        lines.append(
            f"| {plan} | {int(s.get('n',0))} | {float(s.get('win_rate',0.0)):.4f} | {float(s.get('reached_mean',0.0)):.3f} | {float(s.get('gold_end_mean',0.0)):.3f} |"
        )
    lines.append("")
    
    # ============================================================
    # 辅助函数定义
    # ============================================================
    def _unit_label(uk: str) -> str:
        ut = UNIT_TYPES.get(uk)
        if ut and getattr(ut, "name", None):
            return f"{ut.name} ({uk})"
        return str(uk)

    def _skill_label(sk: str) -> str:
        cfg = SKILLS.get(sk, {}) or {}
        nm = cfg.get("name")
        return f"{nm} ({sk})" if nm else str(sk)

    def _combo_label(cid: str) -> str:
        cfg = COMBO_CARDS.get(cid, {}) or {}
        nm = cfg.get("name")
        return f"{nm} ({cid})" if nm else str(cid)

    def _blessing_label(bid: str) -> str:
        cfg = BLESSINGS.get(bid, {}) or {}
        nm = cfg.get("name")
        return f"{nm} ({bid})" if nm else str(bid)

    def _remap_keys(data: dict, mapper) -> dict:
        out: dict = {}
        for k, v in (data or {}).items():
            out[mapper(str(k))] = v
        return out

    def _top_table(title: str, data: dict, *, key_name: str) -> None:
        # 只展示样本数>0的项；按 reached_mean 次序展示（更利于"难度曲线"定位）
        rows = []
        for k, s in (data or {}).items():
            n = int(s.get("n", 0) or 0)
            if n <= 0:
                continue
            rows.append((float(s.get("reached_mean", 0.0) or 0.0), k, s))
        rows.sort(reverse=True)
        lines.append(f"## {title}（按到达层数均值排序，仅展示 n>0）")
        lines.append("")
        lines.append(f"| {key_name} | 样本数(n) | 见到Boss概率 | 到达层数均值 | 最终金币均值 |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, k, s in rows:  # 取消[:15]限制，显示所有数据
            lines.append(
                f"| {k} | {int(s.get('n',0))} | {float(s.get('win_rate',0.0)):.4f} | {float(s.get('reached_mean',0.0)):.3f} | {float(s.get('gold_end_mean',0.0)):.3f} |"
            )
        lines.append("")

    # ============================================================
    # 新增：兵种综合表现大盘 + 其他新章节
    # ============================================================
    
    # 将原有的详细表格移到附录，这里先生成新的聚合表格
    lines.append("## 🎯 兵种综合表现大盘 (Unit Master Dashboard)")
    lines.append("")
    lines.append(f"> **全局基准**: 平均层数 **{global_avg_reached:.2f}** | 见到Boss概率 **{global_win_rate*100:.2f}%**")
    lines.append("> **核心洞察**: 将\"拥有率\"、\"获得时机\"、\"场均表现\"和\"胜率贡献\"整合，快速识别强力兵种与陷阱兵种")
    lines.append("")
    lines.append("| 兵种 | 拥有率 | 场均出兵次数 | 平均获得层数 | 拥有时层数均值 | 拥有时见Boss率 | 胜率贡献 | 综合评级 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|:---|")
    
    # 计算每个兵种的综合数据
    unit_master_data = []
    for uk in ORDER_KEYS:
        if uk == "warrior":  # 战士单独处理
            continue
        
        owned_data = by_unit_owned.get(uk, {})
        n_owned = owned_data.get("n", 0)
        if n_owned == 0:
            continue
        
        ownership_rate = (n_owned / n_total * 100) if n_total > 0 else 0
        avg_spawn = unit_spawn_avg.get(uk, 0.0)
        
        # 获得层数
        unit_acquire_layers = []
        for ep in episodes:
            try:
                acquire_dict = json.loads(ep.unit_acquire_layers_json or "{}")
                if uk in acquire_dict:
                    unit_acquire_layers.append(int(acquire_dict[uk]))
            except:
                pass
        avg_acquire_layer = sum(unit_acquire_layers) / len(unit_acquire_layers) if unit_acquire_layers else 0
        
        # 拥有时的表现
        owned_avg_reached = float(owned_data.get("reached_mean", 0.0))
        owned_win_rate = float(owned_data.get("win_rate", 0.0))
        
        # 胜率贡献
        win_contrib = (owned_win_rate - global_win_rate) * 100
        
        # 综合评级
        if win_contrib > 10:
            rating = "⭐⭐⭐ 核心大腿"
        elif win_contrib > 7:
            rating = "⭐⭐⭐ 强力输出"
        elif win_contrib > 4:
            rating = "⭐⭐ 稳定增强"
        elif win_contrib > 0:
            rating = "⭐ 轻微增强"
        elif win_contrib > -2:
            rating = "⚠️ 需体系配合"
        else:
            rating = "❌ 当前废件"
        
        unit_master_data.append((win_contrib, uk, ownership_rate, avg_spawn, avg_acquire_layer, owned_avg_reached, owned_win_rate, rating))
    
    # 按胜率贡献排序
    unit_master_data.sort(reverse=True)
    
    for win_contrib, uk, ownership_rate, avg_spawn, avg_acquire_layer, owned_avg_reached, owned_win_rate, rating in unit_master_data:
        label = _unit_label(uk)
        arrow = " ↑" if win_contrib > 5 else (" ↓" if win_contrib < -2 else "")
        lines.append(f"| {label} | {ownership_rate:.1f}% | {avg_spawn:.1f} | {avg_acquire_layer:.1f} | {owned_avg_reached:.2f} | {owned_win_rate*100:.1f}% | **{win_contrib:+.1f}%**{arrow} | {rating} |")
    
    # 战士单独一行
    q_owned_data = by_unit_owned.get("warrior", {})
    q_avg_spawn = unit_spawn_avg.get("warrior", 0.0)
    q_avg_reached = float(q_owned_data.get("reached_mean", 0.0))
    q_win_rate = float(q_owned_data.get("win_rate", 0.0))
    lines.append(f"| {_unit_label('Q')} | 100.0% | {q_avg_spawn:.1f} | 0.0 | {q_avg_reached:.2f} | {q_win_rate*100:.1f}% | -- | 🔰 基石/待优化 |")
    
    lines.append("")
    lines.append("**📊 关键发现**:")
    
    # 找出三大腿
    top_3 = [uk for _, uk, *_ in unit_master_data[:3]]
    if top_3:
        top_3_labels = [_unit_label(uk) for uk in top_3]
        top_3_ownership = [ownership_rate for _, _, ownership_rate, *_ in unit_master_data[:3]]
        lines.append(f"- **\"核心大腿\"组合**: {', '.join(top_3_labels[:2])} 的胜率贡献最高，但拥有率仅 {min(top_3_ownership):.0f}-{max(top_3_ownership):.0f}%，说明 Bot 获取频率不足")
    
    # 找出陷阱兵种
    trap_units = [(uk, win_contrib, ownership_rate) for win_contrib, uk, ownership_rate, *_ in unit_master_data if win_contrib < -2 and ownership_rate > 10]
    if trap_units:
        for uk, win_contrib, ownership_rate in trap_units[:1]:
            lines.append(f"- **{_unit_label(uk)}陷阱**: {ownership_rate:.1f}% 的拥有率，但胜率贡献 {win_contrib:.1f}%，属于\"拿了不用\"的资源浪费")
    
    # 战士困境
    if q_avg_spawn > 100:
        lines.append(f"- **战士困境**: 作为基石兵种，100% 拥有但场均出兵 {q_avg_spawn:.1f} 次（占比过高），需要更多多样性")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 这些表用于"定位强弱/是否系统生效"
    _top_table("技能表现", _remap_keys(by_skill, _skill_label), key_name="技能")
    _top_table("Combo表现", _remap_keys(by_combo, _combo_label), key_name="Combo")
    _top_table("祝福表现", _remap_keys(by_blessing, _blessing_label), key_name="祝福")
    
    # 兵种相关表格已整合到"兵种综合表现大盘"和"兵种边际增益深度报告"，以下冗余表格已删除：
    # - 兵种：最终拥有（数据已在大盘中）
    # - 兵种：达到Lv2+（数据已在边际增益报告中）
    # - 兵种：作为首槽（目前只有战士，无意义）
    # - 兵种：使用过（与最终拥有高度重合）
    # - 兵种：作为第二/三多出兵（样本量不足，干扰项）

    # === 路线统计 ===
    lines.append("## 路线统计（节点构成均值）")
    lines.append("")
    lines.append("| 节点类型 | 平均次数 |")
    lines.append("|---|---:|")
    node_mean = (route.get("node_count_mean") or {}) if isinstance(route, dict) else {}
    for t in ["combat", "elite", "boss", "shop", "event", "rest"]:
        lines.append(f"| {t} | {float(node_mean.get(t, 0.0) or 0.0):.3f} |")
    lines.append("")

    # === 商店细节 ===
    lines.append("## 商店细节（聚合）")
    lines.append("")
    free_r = int(shop_detail.get("refresh_free_total", 0) or 0)
    paid_r = int(shop_detail.get("refresh_paid_total", 0) or 0)
    lines.append(f"- **刷新总次数**: free={free_r}, paid={paid_r}")
    buy_type_counts = shop_detail.get("buy_type_counts", {}) or {}
    lines.append("")
    lines.append("| 购买类型 | 次数 |")
    lines.append("|---|---:|")
    for k, v in sorted(((str(k), int(v or 0)) for k, v in buy_type_counts.items()), key=lambda x: x[1], reverse=True)[:15]:
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # === 事件细节 ===
    lines.append("## 事件细节（聚合）")
    lines.append("")
    tc = event_detail.get("template_counts", {}) or {}
    cc = event_detail.get("choice_counts", {}) or {}
    sc = event_detail.get("seg_counts", {}) or {}
    lines.append("| 事件模板 | 次数 |")
    lines.append("|---|---:|")
    for k, v in sorted(((str(k), int(v or 0)) for k, v in tc.items()), key=lambda x: x[1], reverse=True)[:20]:
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("| 选项 | 次数 |")
    lines.append("|---|---:|")
    for k, v in sorted(((str(k), int(v or 0)) for k, v in cc.items()), key=lambda x: x[0]):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("| 声望段位(seg) | 次数 |")
    lines.append("|---|---:|")
    for k, v in sorted(((str(k), int(v or 0)) for k, v in sc.items()), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # === 兵种获得时机统计 ===
    # 已删除：兵种获得时机表（平均获得层数已在"兵种综合表现大盘"中展示）
    
    # 保留数据收集逻辑供其他地方使用
    unit_acquire_data: dict[str, list[int]] = {}
    for e in episodes:
        try:
            acquire_dict = json.loads(e.unit_acquire_layers_json or "{}")
            for uk, layer in acquire_dict.items():
                if uk not in unit_acquire_data:
                    unit_acquire_data[uk] = []
                unit_acquire_data[uk].append(int(layer))
        except Exception:
            pass
    
    # === 里程碑奖励细节 ===
    lines.append("## 里程碑奖励（触发原因/触发战斗数）")
    lines.append("")
    rc = milestone_detail.get("combo_reason_counts", {}) or {}
    lines.append("| Combo触发原因(reason) | 次数 |")
    lines.append("|---|---:|")
    for k, v in sorted(((str(k), int(v or 0)) for k, v in rc.items()), key=lambda x: x[1], reverse=True)[:20]:
        lines.append(f"| {k} | {v} |")
    lines.append("")
    bm = milestone_detail.get("combo_battle_mean_by_idx", {}) or {}
    lines.append("| 第N张Combo | 触发战斗数均值 |")
    lines.append("|---:|---:|")
    for idx in ["1", "2", "3"]:
        lines.append(f"| {idx} | {float(bm.get(idx, 0.0) or 0.0):.3f} |")
    lines.append("")

    lines.append("## 锻造：最高等级分桶")
    lines.append("")
    lines.append("| forge_max_level | 样本数(n) | 见到Boss概率 | 到达层数均值 | 最终金币均值 | 打满时限率 |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for bucket in ["0", "1", "2", "3"]:
        s = by_forge_max.get(bucket, {}) or {}
        n = int(s.get("n", 0) or 0)
        if n <= 0:
            continue
        lines.append(
            f"| {bucket} | {n} | {float(s.get('win_rate',0.0)):.4f} | {float(s.get('reached_mean',0.0)):.3f} | {float(s.get('gold_end_mean',0.0)):.3f} | {float(s.get('battle_time_limit_hit_rate',0.0)):.4f} |"
        )
    lines.append("")

    # 出兵次数影响（兵种）
    # 已删除：出兵次数对表现的影响表（场均出兵次数已在"兵种综合表现大盘"中展示）
    
    # ============================================================
    # 新增章节：战士专题、兵种边际增益、兵种获取时机、出兵频率分析
    # ============================================================
    
    # === 3.0 战士专题：基石稳定性分析 ===
    lines.append("## 3.0 战士专题：基石稳定性分析 (Warrior Baseline Analysis)")
    lines.append("")
    lines.append("> 战士 (Q) 作为开局必带兵种，本节分析其投入产出比与队伍占比的关系")
    lines.append("")
    
    # A. 战士出兵占比分布
    lines.append("### A. 战士出兵占比分布 (Warrior Saturation Distribution)")
    lines.append("")
    lines.append("| 战士占比区间 | 样本数(n) | 通关率 | 到达层数均值 | 核心问题指向 |")
    lines.append("|---|---:|---:|---:|:---|")
    
    # 统计每个区间的数据
    warrior_bins = [
        (0, 20, "0-20% (极简流)"),
        (21, 40, "21-40% (精锐流)"),
        (41, 60, "41-60% (混编流)"),
        (61, 80, "61-80% (人海流)"),
        (81, 100, "81-100% (纯战流)"),
    ]
    
    for min_pct, max_pct, label in warrior_bins:
        bin_episodes = []
        for ep in episodes:
            try:
                spawn_counts = json.loads(ep.spawn_counts_json) if ep.spawn_counts_json else {}
                q_spawn = spawn_counts.get("warrior", 0)
                total_spawn = sum(spawn_counts.values())
                if total_spawn > 0:
                    q_pct = (q_spawn / total_spawn) * 100
                    if min_pct <= q_pct <= max_pct:
                        bin_episodes.append(ep)
            except:
                continue
        
        n = len(bin_episodes)
        if n > 0:
            win_count = sum(1 for ep in bin_episodes if ep.win)
            win_rate = win_count / n
            avg_reached = sum(ep.reached_layer for ep in bin_episodes) / n
            
            # 判断表现
            if win_rate > 0.15 or avg_reached > 10:
                assessment = "✓ 表现优异"
            elif win_rate > 0.05 or avg_reached > 7:
                assessment = "表现良好"
            elif avg_reached > 5:
                assessment = "配比失衡"
            else:
                assessment = "缺乏多样性/克制手段？"
            
            lines.append(f"| {label} | {n} | {win_rate*100:.2f}% | {avg_reached:.2f} | {assessment} |")
        else:
            lines.append(f"| {label} | 0 | -- | -- | 无样本 |")
    
    lines.append("")
    
    # B. 战士成长审计
    lines.append("### B. 战士成长审计 (Warrior Growth by Stage)")
    lines.append("")
    lines.append("| 阶段 | 战士平均等级 | 战士平均锻造数 | 阶段存活率 | 战士出兵占比 |")
    lines.append("|---|---:|---:|---:|---:|")
    
    stages = [
        (0, 5, "前期 (0-5层)"),
        (6, 10, "中期 (6-10层)"),
        (11, 15, "后期 (11-15层)"),
        (16, 20, "终局 (16-20层)"),
    ]
    
    for min_layer, max_layer, stage_label in stages:
        stage_episodes = [ep for ep in episodes if min_layer <= ep.reached_layer <= max_layer]
        n = len(stage_episodes)
        
        if n > 0:
            # 解析 JSON 字段
            total_q_level = 0
            total_q_forge = 0
            total_q_spawn = 0
            total_all_spawn = 0
            
            for ep in stage_episodes:
                try:
                    unit_levels = json.loads(ep.unit_levels_json) if ep.unit_levels_json else {}
                    forge_levels = json.loads(ep.forge_levels_json) if ep.forge_levels_json else {}
                    spawn_counts = json.loads(ep.spawn_counts_json) if ep.spawn_counts_json else {}
                    
                    total_q_level += unit_levels.get("warrior", 1)
                    total_q_forge += forge_levels.get("warrior", 0)
                    total_q_spawn += spawn_counts.get("warrior", 0)
                    total_all_spawn += sum(spawn_counts.values())
                except:
                    continue
            
            avg_q_level = total_q_level / n
            avg_q_forge = total_q_forge / n
            survival_rate = n / len(episodes)
            q_spawn_pct = (total_q_spawn / total_all_spawn * 100) if total_all_spawn > 0 else 0
            
            lines.append(f"| {stage_label} | {avg_q_level:.2f} | {avg_q_forge:.2f} | {survival_rate*100:.2f}% | {q_spawn_pct:.1f}% |")
        else:
            lines.append(f"| {stage_label} | -- | -- | 0.00% | -- |")
    
    lines.append("")
    
    # C. 战士-战术适配度
    lines.append("### C. 战士-战术适配度 (Warrior Synergy Lift)")
    lines.append("")
    lines.append("> 战士作为核心时，搭配以下兵种/系统后的表现提升")
    lines.append("")
    lines.append("| 搭配系统 | 样本数(n) | 层数提升 | 通关率提升 | 评价 |")
    lines.append("|---|---:|---:|---:|:---|")
    
    # 全局基准
    global_avg_reached = overall.get("reached_mean", 0)
    global_win_rate = overall.get("win_rate", 0)
    
    # 统计战士+其他兵种的表现
    for uk in ORDER_KEYS:
        if uk == "warrior":
            continue
        
        # 找到同时拥有warrior和uk的局（units 是用 | 分隔的字符串）
        synergy_episodes = [ep for ep in episodes if "warrior" in ep.units.split("|") and uk in ep.units.split("|")]
        n = len(synergy_episodes)
        
        if n >= 5:  # 至少5个样本才显示
            avg_reached = sum(ep.reached_layer for ep in synergy_episodes) / n
            win_count = sum(1 for ep in synergy_episodes if ep.win)
            win_rate = win_count / n
            
            reached_lift = avg_reached - global_avg_reached
            win_rate_lift = (win_rate - global_win_rate) * 100
            
            if reached_lift > 3 or win_rate_lift > 5:
                assessment = "显著增强"
            elif reached_lift > 1 or win_rate_lift > 2:
                assessment = "轻微增强"
            elif reached_lift < -1 or win_rate_lift < -2:
                assessment = "负面影响"
            else:
                assessment = "影响不明显"
            
            lines.append(f"| 战士 + {_unit_label(uk)} | {n} | {reached_lift:+.2f} | {win_rate_lift:+.1f}% | {assessment} |")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # === 3.1 兵种边际增益深度报告 ===
    lines.append("## 3.1 兵种边际增益深度报告 (Unit Incremental Value)")
    lines.append("")
    lines.append(f"> **全局基准**：平均层数 **{global_avg_reached:.2f}** | 见到Boss概率 **{global_win_rate*100:.2f}%**")
    lines.append("> *注：增益项为 (该条件下均值 - 全局均值)，+号表示表现优于大盘*")
    lines.append("")
    lines.append("| 兵种 | 样本(n) | 拥有增益 (层数/胜率) | 1→2级增益 | 2→3级增益 | 3→4级增益 | 锻造增益 |")
    lines.append("|---|---:|:---|:---|:---|:---|:---|")
    
    for uk in ORDER_KEYS:
        # 拥有该兵种的增益（units 是用 | 分隔的字符串）
        owned_eps = [ep for ep in episodes if uk in ep.units.split("|")]
        n_owned = len(owned_eps)
        
        if n_owned > 0:
            owned_avg = sum(ep.reached_layer for ep in owned_eps) / n_owned
            owned_win = sum(1 for ep in owned_eps if ep.win) / n_owned
            owned_lift_reached = owned_avg - global_avg_reached
            owned_lift_win = (owned_win - global_win_rate) * 100
            
            # 升级增益
            def calc_level_lift(level):
                lvl_eps = []
                for ep in owned_eps:
                    try:
                        unit_levels = json.loads(ep.unit_levels_json) if ep.unit_levels_json else {}
                        if unit_levels.get(uk, 1) >= level:
                            lvl_eps.append(ep)
                    except:
                        continue
                
                if len(lvl_eps) >= 3:
                    lvl_avg = sum(ep.reached_layer for ep in lvl_eps) / len(lvl_eps)
                    lvl_win = sum(1 for ep in lvl_eps if ep.win) / len(lvl_eps)
                    return f"+{lvl_avg - global_avg_reached:.1f} / {(lvl_win - global_win_rate)*100:+.1f}%"
                return "--"
            
            lv2_lift = calc_level_lift(2)
            lv3_lift = calc_level_lift(3)
            lv4_lift = calc_level_lift(4)
            
            # 锻造增益
            forge_eps = []
            for ep in owned_eps:
                try:
                    forge_levels = json.loads(ep.forge_levels_json) if ep.forge_levels_json else {}
                    if forge_levels.get(uk, 0) > 0:
                        forge_eps.append(ep)
                except:
                    continue
            
            if len(forge_eps) >= 3:
                forge_avg = sum(ep.reached_layer for ep in forge_eps) / len(forge_eps)
                forge_win = sum(1 for ep in forge_eps if ep.win) / len(forge_eps)
                forge_lift = f"+{forge_avg - global_avg_reached:.1f} / {(forge_win - global_win_rate)*100:+.1f}%"
            else:
                forge_lift = "--"
            
            owned_str = f"+{owned_lift_reached:.1f} / {owned_lift_win:+.1f}%" if uk != "warrior" else "--"
            
            lines.append(f"| {_unit_label(uk)} | {n_owned} | {owned_str} | {lv2_lift} | {lv3_lift} | {lv4_lift} | {forge_lift} |")
    
    lines.append("")
    
    # === 3.2 兵种获取时机分析 ===
    lines.append("## 3.2 兵种获取时机分析 (Unit Acquisition Timing)")
    lines.append("")
    lines.append("> 追踪 Bot 在哪一层获得了第 N 个兵种，用于评估\"强迫消费\"逻辑的有效性")
    lines.append("")
    lines.append("| 里程碑 | 平均获得层数 | 样本数(n) | 中位数(P50) | 最早 | 最晚 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    
    # 统计每个里程碑
    for milestone_idx in range(1, 6):
        milestone_layers = []
        for ep in episodes:
            try:
                unit_acquire_layers = json.loads(ep.unit_acquire_layers_json) if ep.unit_acquire_layers_json else {}
                if len(unit_acquire_layers) >= milestone_idx:
                    layers = sorted(unit_acquire_layers.values())
                    if len(layers) >= milestone_idx:
                        milestone_layers.append(layers[milestone_idx - 1])
            except:
                continue
        
        if milestone_layers:
            avg_layer = sum(milestone_layers) / len(milestone_layers)
            median_layer = sorted(milestone_layers)[len(milestone_layers) // 2]
            min_layer = min(milestone_layers)
            max_layer = max(milestone_layers)
            n = len(milestone_layers)
            
            lines.append(f"| 第 {milestone_idx} 个兵种 | {avg_layer:.2f} | {n} | {median_layer} | {min_layer} | {max_layer} |")
        else:
            lines.append(f"| 第 {milestone_idx} 个兵种 | -- | 0 | -- | -- | -- |")
    
    lines.append("")
    
    # === 3.3 出兵频率与兵种使用率分析 ===
    lines.append("## 3.3 出兵频率与兵种使用率 (Spawn Frequency Analysis)")
    lines.append("")
    lines.append("> 分析每层战斗中的平均出兵数，以及各兵种的实际使用率")
    lines.append("")
    
    # A. 每层平均出兵数
    lines.append("### A. 每层平均出兵数")
    lines.append("")
    lines.append("| 层数区间 | 平均总出兵数 | 战士出兵数 | 其他兵种出兵数 | 战士占比 |")
    lines.append("|---|---:|---:|---:|---:|")
    
    layer_ranges = [
        (0, 2, "0-2 层"),
        (3, 5, "3-5 层"),
        (6, 10, "6-10 层"),
        (11, 15, "11-15 层"),
        (16, 20, "16-20 层"),
    ]
    
    for min_layer, max_layer, range_label in layer_ranges:
        range_episodes = [ep for ep in episodes if min_layer <= ep.reached_layer <= max_layer]
        
        if range_episodes:
            total_spawns = 0
            q_spawns = 0
            
            for ep in range_episodes:
                try:
                    spawn_counts = json.loads(ep.spawn_counts_json) if ep.spawn_counts_json else {}
                    total_spawns += sum(spawn_counts.values())
                    q_spawns += spawn_counts.get("warrior", 0)
                except:
                    continue
            
            other_spawns = total_spawns - q_spawns
            avg_total = total_spawns / len(range_episodes)
            avg_q = q_spawns / len(range_episodes)
            avg_other = other_spawns / len(range_episodes)
            q_pct = (q_spawns / total_spawns * 100) if total_spawns > 0 else 0
            
            lines.append(f"| {range_label} | {avg_total:.1f} | {avg_q:.1f} | {avg_other:.1f} | {q_pct:.1f}% |")
        else:
            lines.append(f"| {range_label} | -- | -- | -- | -- |")
    
    lines.append("")
    
    # B. 兵种实际出兵率
    # 已删除：兵种实际出兵率表（场均出兵次数已在"兵种综合表现大盘"中展示）
    
    # ============================================================
    # 附录：原始详细数据表（供深度分析使用）
    # ============================================================
    lines.append("---")
    lines.append("")
    # 附录：原始数据表已删除
    # 所有兵种相关的核心数据已整合到"兵种综合表现大盘"和"兵种边际增益深度报告"中
    
    # ============================================================
    # 策划总结与建议
    # ============================================================
    lines.append("---")
    lines.append("")
    lines.append("## 💡 策划总结与建议")
    lines.append("")
    lines.append("### 核心问题诊断")
    lines.append("")
    
    # 根据数据生成诊断
    if high_warrior_rate > 70:
        lines.append(f"1. **\"战士陷阱\"导致的胜率雪崩**:")
        lines.append(f"   - {high_warrior_rate:.1f}% 的局陷入\"纯战流\"（战士占比 >80%），这些局的通关率为 0%")
        lines.append(f"   - 出兵逻辑存在严重的\"战士权重过高\"问题")
        lines.append("")
    
    if layer_0_death_rate > 20:
        lines.append(f"2. **\"首日猝死\"现象**:")
        lines.append(f"   - Layer 0 死亡率高达 {layer_0_death_rate:.0f}%，前 3 层累计死亡率可能超过 50%")
        lines.append(f"   - 初期数值或出兵逻辑极其脆弱")
        lines.append("")
    
    if avg_units_count < 3.5:
        win_eps = [ep for ep in episodes if ep.win]
        win_avg_units = sum(ep.units_count for ep in win_eps) / len(win_eps) if win_eps else 0
        lines.append(f"3. **多样性不足**:")
        lines.append(f"   - 平均仅解锁 {avg_units_count:.1f} 个兵种，而通关局平均需要 {win_avg_units:.1f}+ 个兵种配合")
        
        # 找出"三大腿"
        top_3_units = [(uk, ownership_rate) for _, uk, ownership_rate, *_ in unit_master_data[:3]]
        if top_3_units:
            top_3_str = "、".join([_unit_label(uk) for uk, _ in top_3_units])
            lines.append(f"   - \"三大腿\"（{top_3_str}）的拥有率仅 {min(o for _, o in top_3_units):.0f}-{max(o for _, o in top_3_units):.0f}%，远低于其价值")
        lines.append("")
    
    lines.append("### 逻辑优化建议")
    lines.append("")
    lines.append("1. **引入\"多样性惩罚\"机制**:")
    lines.append("   - 当同一兵种连续产出超过 N 个时，动态调低其权重")
    lines.append("   - 或强制检查是否有其他已解锁单位可产出")
    lines.append("")
    lines.append("2. **优化兵种获取优先级**:")
    
    # 找出高价值兵种
    high_value_units = [(uk, win_contrib) for win_contrib, uk, *_ in unit_master_data if win_contrib > 10]
    if high_value_units:
        high_value_str = "、".join([_unit_label(uk) for uk, _ in high_value_units[:3]])
        lines.append(f"   - 提高\"{high_value_str}\"等高价值兵种的商店出现率或购买权重")
    
    # 找出低价值兵种
    low_value_units = [(uk, win_contrib) for win_contrib, uk, *_ in unit_master_data if win_contrib < -2]
    if low_value_units:
        low_value_str = "、".join([_unit_label(uk) for uk, _ in low_value_units[:2]])
        lines.append(f"   - 降低\"{low_value_str}\"等负收益兵种的购买权重")
    lines.append("")
    
    lines.append("3. **调整升级策略**:")
    lines.append("   - 优先多个兵种 Lv2 而非单个 Lv3")
    lines.append("   - 避免升级\"战士\"到 Lv2（可能存在负收益）")
    lines.append("")
    lines.append("4. **增加\"出兵熵值\"监控**:")
    lines.append("   - 在报告中增加\"出兵熵值\"指标（0-1），低于 0.3 时自动标红报警")
    lines.append("   - 用于实时监控出兵逻辑是否陷入\"单一种群过载\"")
    lines.append("")
    
    return "\n".join(lines)


def _find_latest_summary(out_dir: Path) -> Path | None:
    if not out_dir.exists():
        return None
    candidates = []
    for p in out_dir.glob("*/summary.json"):
        candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _render_diff_md(prev: dict, cur: dict) -> str:
    def g(summary: dict, key: str) -> float:
        return float(summary.get("overall", {}).get(key, 0.0) or 0.0)

    lines: List[str] = []
    lines.append("# 测试对比（Diff）")
    lines.append("")
    lines.append(f"- **上一份**: **{prev.get('meta', {}).get('run_id','')}**（{prev.get('meta', {}).get('version','')}）")
    if prev.get("meta", {}).get("name"):
        lines.append(f"  - 名称: {prev.get('meta', {}).get('name','')}")
    lines.append(f"- **本次**: **{cur.get('meta', {}).get('run_id','')}**（{cur.get('meta', {}).get('version','')}）")
    if cur.get("meta", {}).get("name"):
        lines.append(f"  - 名称: {cur.get('meta', {}).get('name','')}")
    lines.append("")
    lines.append("| 指标 | 上一份 | 本次 | 变化(delta) |")
    lines.append("|---|---:|---:|---:|")
    for k in ["win_rate", "reached_p50", "reached_p90", "gold_end_p10", "gold_end_p90", "shop_refresh_mean", "base_hp_sum_end_mean"]:
        a = g(prev, k)
        b = g(cur, k)
        label = {
            "win_rate": "见到Boss概率",
            "reached_p50": "到达层数P50",
            "reached_p90": "到达层数P90",
            "gold_end_p10": "最终金币P10",
            "gold_end_p90": "最终金币P90",
            "shop_refresh_mean": "商店付费刷新均值",
            "base_hp_sum_end_mean": "最终基地总HP均值",
        }.get(k, k)
        lines.append(f"| {label} ({k}) | {a:.4f} | {b:.4f} | {(b-a):+.4f} |")

    # by build plan diff（win_rate）
    pb = prev.get("by_build_plan", {}) or {}
    cb = cur.get("by_build_plan", {}) or {}
    lines.append("")
    lines.append("## 各BuildPlan见到Boss概率变化（win_rate delta）")
    lines.append("")
    lines.append("| BuildPlan | 上一份 | 本次 | 变化(delta) |")
    lines.append("|---|---:|---:|---:|")
    for plan in BUILD_PLANS:
        a = float(pb.get(plan, {}).get("win_rate", 0.0) or 0.0)
        b = float(cb.get(plan, {}).get("win_rate", 0.0) or 0.0)
        if plan in pb or plan in cb:
            lines.append(f"| {plan} | {a:.4f} | {b:.4f} | {(b-a):+.4f} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="sim_run.py",
        description="整局 Run 批量模拟（无渲染），用于平衡回归与Build覆盖测试。",
        epilog='示例：py roguelike_game/sim_run.py --batch 200 --seed 1000 --out runs --name "平衡v1" --note "改了兵种Q/W数值+商店价格"',
    )
    ap.add_argument("--batch", type=int, default=int(DEFAULT_RUN.get("batch", 200)), help="本次跑多少局（建议：200/500/1000）")
    ap.add_argument("--seed", type=int, default=int(DEFAULT_RUN.get("seed", 1000)), help="base seed；每局会在此基础上 +i")
    ap.add_argument("--name", type=str, default=str(DEFAULT_RUN.get("name", "test")), help="本次测试名称（会写入报告并进入输出目录名）")
    ap.add_argument("--bot", type=str, default=str(DEFAULT_RUN.get("bot", "mid")), choices=["mid"])
    ap.add_argument("--out", type=str, default=str(DEFAULT_RUN.get("out", "runs")), help="输出目录（默认 runs/）")
    ap.add_argument("--note", type=str, default=str(DEFAULT_RUN.get("note", "")), help="可选：额外备注（会写入报告）")
    ap.add_argument("--battle-max-time-sec", type=float, default=float(DEFAULT_RUN.get("battle_max_time_sec", 180.0)))
    ap.add_argument("--battle-dt", type=float, default=float(DEFAULT_RUN.get("battle_dt", 0.10)))
    ap.add_argument("--battle-wall-time-sec", type=float, default=float(DEFAULT_RUN.get("battle_wall_time_sec", 2.5)))
    ap.add_argument("--progress-every", type=int, default=int(DEFAULT_RUN.get("progress_every", 10)))
    ap.add_argument("--new-save", action="store_true", help="批量测试前删除 autosave（新档）")
    ap.add_argument("--report-mirror", dest="report_mirror", action="store_true", default=True, help="输出镜像Boss统计报告（默认开）")
    ap.add_argument("--no-report-mirror", dest="report_mirror", action="store_false", help="关闭镜像Boss统计报告")
    args = ap.parse_args()

    print("[sim] 启动批量测试...")
    print(f"[sim] 配置: batch={args.batch}, bot={args.bot}, report_mirror={getattr(args, 'report_mirror', True)}")

    base_seed = int(args.seed)
    batch = max(1, int(args.batch))
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    # 固定测试存档目录：每次测试独立的大档（不影响真实存档）
    test_save_dir = (out_root / "_sim_save").resolve()
    os.environ["SEVENLINES_SAVE_DIR"] = str(test_save_dir)
    delete_autosave()
    try:
        p = mirror_profile_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass
    if bool(getattr(args, "new_save", False)):
        delete_autosave()

    version = _try_git_version() or f"build:{_now_tag()}"
    run_id = _now_tag()
    build_mode = "uniform"
    test_name = str(args.name).strip()
    safe_name = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in test_name)[:80] or "test"

    # 将 CLI 覆盖写回 DEFAULT_RUN（供战斗环节读取阈值）
    DEFAULT_RUN["battle_max_time_sec"] = float(args.battle_max_time_sec)
    DEFAULT_RUN["battle_dt"] = float(args.battle_dt)
    DEFAULT_RUN["battle_wall_time_sec"] = float(args.battle_wall_time_sec)
    DEFAULT_RUN["progress_every"] = int(args.progress_every)

    prev_path = _find_latest_summary(out_root)

    # 默认使用“单一大档”镜像Boss测试
    episodes, mirror_stats = _run_mirror_boss_test(batch, base_seed, args, version, run_id)

    boss_encounters = mirror_stats["boss_encounters"]
    boss_wins = mirror_stats["boss_wins"]
    mirror_updates = mirror_stats["mirror_updates"]
    last_mirror_updated = mirror_stats["last_mirror_updated"]

    run_dir = out_root / f"{run_id}_{safe_name}_{version.replace(':','-').replace(' ','_')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    episodes_csv = run_dir / "episodes.csv"
    _write_episodes_csv(episodes_csv, episodes)

    meta = {
        "version": version,
        "run_id": run_id,
        "name": test_name,
        "batch": batch,
        "seed_base": base_seed,
        "bot_tier": args.bot,
        "build_mode": build_mode,
        "note": args.note or "",
        "battle_max_time_sec": float(DEFAULT_RUN.get("battle_max_time_sec", 0.0)),
        "battle_dt": float(DEFAULT_RUN.get("battle_dt", 0.0)),
        "battle_wall_time_sec": float(DEFAULT_RUN.get("battle_wall_time_sec", 0.0)),
    }
    summary = _summarize(episodes, meta)
    # Windows 友好：utf-8-sig 方便直接用记事本/Excel 打开
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    (run_dir / "report.md").write_text(_render_report_md(summary, episodes), encoding="utf-8-sig")
    if bool(getattr(args, "report_mirror", True)):
        mirror_history = list(mirror_stats.get("mirror_history") or [])
        last_script_len = 0
        cur_state = load_autosave()
        if cur_state:
            last_script_len = len(cur_state.mirror_script or [])
            if last_mirror_updated is None:
                last_mirror_updated = float(cur_state.mirror_last_updated or 0.0)
        mirror_encounters = sum(int(ep.mirror_encounter) for ep in episodes)
        mirror_wins = sum(int(ep.mirror_win) for ep in episodes)
        mirror_encounter_rate = (mirror_encounters / batch) if batch else 0.0
        mirror_win_rate = (mirror_wins / mirror_encounters) if mirror_encounters else 0.0
        by_blessing: dict[str, dict[str, int]] = {}
        by_build: dict[str, dict[str, int]] = {}
        for ep in episodes:
            if not int(getattr(ep, "mirror_encounter", 0) or 0):
                continue
            blessing = str(getattr(ep, "mirror_blessing", "") or "unknown")
            build = str(getattr(ep, "mirror_build_plan", "") or "unknown")
            by_blessing.setdefault(blessing, {"n": 0, "wins": 0})
            by_build.setdefault(build, {"n": 0, "wins": 0})
            by_blessing[blessing]["n"] += 1
            by_blessing[blessing]["wins"] += int(getattr(ep, "mirror_win", 0) or 0)
            by_build[build]["n"] += 1
            by_build[build]["wins"] += int(getattr(ep, "mirror_win", 0) or 0)

        def _rank_hardest(d: dict[str, dict[str, int]]) -> list[dict]:
            rows: list[tuple[float, int, str]] = []
            for k, v in (d or {}).items():
                n = int(v.get("n", 0) or 0)
                if n <= 0:
                    continue
                win_rate = float(v.get("wins", 0) or 0) / n
                rows.append((win_rate, n, str(k)))
            rows.sort()
            out: list[dict] = []
            for win_rate, n, name in rows[:10]:
                out.append({"name": name, "encounters": n, "win_rate": win_rate})
            return out

        mirror_stats = {
            "total_runs": batch,
            "boss_encounters": boss_encounters,
            "boss_wins": boss_wins,
            "mirror_updates": mirror_updates,
            "update_rate": (mirror_updates / batch) if batch else 0.0,
            "mirror_encounter_rate": mirror_encounter_rate,
            "mirror_win_rate": mirror_win_rate,
            "last_mirror_script_len": last_script_len,
            "last_mirror_updated": float(last_mirror_updated or 0.0),
            "mirror_blessing_hardest": _rank_hardest(by_blessing),
            "mirror_build_hardest": _rank_hardest(by_build),
            "mirror_history": mirror_history,
        }
        (run_dir / "report_mirror.md").write_text(_render_mirror_report_md(mirror_stats, meta), encoding="utf-8-sig")
        print(f"[mirror] boss_encounters={boss_encounters} boss_wins={boss_wins} mirror_updates={mirror_updates}")

    if prev_path and prev_path.parent != run_dir:
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            diff_md = _render_diff_md(prev, summary)
            (run_dir / "diff.md").write_text(diff_md, encoding="utf-8-sig")
        except Exception:
            pass

    print(f"[sim] done: {batch} episodes")
    print(f"[sim] out: {run_dir}")
    return 0

def _run_mirror_boss_test(batch: int, base_seed: int, args, version: str, run_id: str):
    """在一个共享的存档中连续测试，看Bot能击败几次自己的镜像Boss"""
    episodes: List[EpisodeResult] = []

    # 共享镜像状态（每次测试内部持续刷新）
    shared_run_state = load_autosave() or CampaignRunState()

    boss_encounters = 0
    boss_wins = 0
    mirror_updates = 0
    last_mirror_updated = None
    mirror_history: list[dict] = []
    runs_since_update = 0
    mirror_encounters_since_update = 0

    # 在同一个存档中连续进行batch次测试
    for i in range(batch):
        plan = BUILD_PLANS[i % len(BUILD_PLANS)]
        seed = base_seed + i

        # 每局使用全新run_state，仅继承镜像数据（避免跨局状态污染）
        run_state = CampaignRunState()
        run_state.mirror_snapshot = dict(shared_run_state.mirror_snapshot or {})
        run_state.mirror_script = list(shared_run_state.mirror_script or [])
        run_state.mirror_last_updated = float(shared_run_state.mirror_last_updated or 0.0)
        run_state.seed = seed
        run_state.rng_step = 0

        sim = SimRunner(seed=seed, bot_tier=args.bot, build_plan_id=plan, run_state=run_state)
        ep = sim.run_one()
        runs_since_update += 1
        if int(getattr(ep, "mirror_encounter", 0) or 0):
            mirror_encounters_since_update += 1

        node_counts = _safe_json_loads(ep.node_counts_json)
        if int(node_counts.get("boss", 0) or 0) > 0:
            boss_encounters += 1

        if int(ep.win) == 1:
            boss_wins += 1
            # 在同一个存档中更新镜像
            snapshot = _build_mirror_snapshot_from_run(sim.run, build_plan_id=plan)
            script = list(getattr(sim, "_last_boss_recording", []) or [])
            shared_run_state.mirror_snapshot = snapshot
            shared_run_state.mirror_script = script
            shared_run_state.mirror_last_updated = time.time()
            save_autosave(shared_run_state)  # 保存累积的进度
            mirror_updates += 1
            last_mirror_updated = shared_run_state.mirror_last_updated
            mirror_history.append(
                {
                    "idx": int(mirror_updates),
                    "run_index": int(i + 1),
                    "seed": int(seed),
                    "build_plan": str(plan),
                    "script_len": int(len(script)),
                    "runs_since_update": int(runs_since_update),
                    "mirror_encounters_since_update": int(mirror_encounters_since_update),
                    "snapshot": snapshot,
                }
            )
            runs_since_update = 0
            mirror_encounters_since_update = 0

        ep.version = version
        ep.run_id = run_id
        episodes.append(ep)

        every = max(1, int(DEFAULT_RUN.get("progress_every", 10)))
        if every and ((i + 1) % every == 0 or (i + 1) == batch):
            print(f"[mirror] progress: {i+1}/{batch}, boss_wins={boss_wins}, mirror_updates={mirror_updates}")

    mirror_stats = {
        "boss_encounters": boss_encounters,
        "boss_wins": boss_wins,
        "mirror_updates": mirror_updates,
        "last_mirror_updated": last_mirror_updated,
        "mirror_history": mirror_history,
    }

    return episodes, mirror_stats


def _run_traditional_test(batch: int, base_seed: int, args, version: str, run_id: str):
    """传统测试：每局独立运行"""
    episodes: List[EpisodeResult] = []
    boss_encounters = 0
    boss_wins = 0
    mirror_updates = 0
    last_mirror_updated = None

    for i in range(batch):
        plan = BUILD_PLANS[i % len(BUILD_PLANS)]
        seed = base_seed + i
        sim = SimRunner(seed=seed, bot_tier=args.bot, build_plan_id=plan)
        ep = sim.run_one()
        node_counts = _safe_json_loads(ep.node_counts_json)
        if int(node_counts.get("boss", 0) or 0) > 0:
            boss_encounters += 1
        if int(ep.win) == 1:
            boss_wins += 1
            if bool(getattr(args, "report_mirror", True)):
                run_state = load_autosave() or CampaignRunState()
                run_state.mirror_snapshot = _build_mirror_snapshot_from_run(sim.run)
                run_state.mirror_script = []
                run_state.mirror_last_updated = time.time()
                save_autosave(run_state)
                mirror_updates += 1
                last_mirror_updated = run_state.mirror_last_updated
        ep.version = version
        ep.run_id = run_id
        episodes.append(ep)
        every = max(1, int(DEFAULT_RUN.get("progress_every", 10)))
        if every and ((i + 1) % every == 0 or (i + 1) == batch):
            print(f"[sim] progress: {i+1}/{batch}")

    mirror_stats = {
        "boss_encounters": boss_encounters,
        "boss_wins": boss_wins,
        "mirror_updates": mirror_updates,
        "last_mirror_updated": last_mirror_updated,
    }

    return episodes, mirror_stats


if __name__ == "__main__":
    raise SystemExit(main())


