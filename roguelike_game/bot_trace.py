"""
单局/单场战斗 Trace（无渲染）：
- 用于“校准 AI”：观察 bot 出兵节奏 vs 敌方出兵节奏
- 输出 trace.jsonl（JSON Lines）：battle_start / snapshot / battle_end

用法示例（PowerShell，仓库根目录执行）：
    py roguelike_game/bot_trace.py --seed 2000 --plan standard_comp --out runs_trace
    py roguelike_game/bot_trace.py --seed 2000 --plan standard_comp --out runs_trace --player-k 3 --enemy-k 4

输出：
    runs_trace/<timestamp>_seedXXXX_planYYYY/trace.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

# 兼容运行方式：
# - 从仓库根目录执行：py roguelike_game/bot_trace.py
# - 从 roguelike_game 目录执行：py bot_trace.py
_BASE_DIR = Path(__file__).resolve().parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from game.constants import CAMPAIGN_BATTLE_NODE_TYPES, CAMPAIGN_PARAMS  # noqa: E402
from game.game import Game, ORDER_KEYS  # noqa: E402

from sim_run import BUILD_PLANS, DEFAULT_RUN, MidBattleBot, SimRunner  # noqa: E402


def _now_tag() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# ============================================================
# ✅ 快速修改入口（点 Run 直接跑）
# - 不带命令行参数时会使用这里的 DEFAULT_TRACE。
# - seed=None 表示随机；也可以填固定数值（例如 1500）。
# ============================================================
DEFAULT_TRACE: dict = {
    "seed": None,
    "plan": "standard_comp",
    "out": "runs_trace",
    "snapshot_interval_sec": 1.0,
    # ✅ 仅用于 trace：强制覆盖双方兵种池的“数量”（不改战役/主程序逻辑）
    # - player_k：我方可用兵种数量（影响 MidBattleBot 的操作复杂度）
    # - enemy_k：敌方兵种池数量（影响 AI 出兵多样性）
    "player_k": 5,
    "enemy_k": 5,
}


def _resolve_seed(seed_opt: int | None) -> int:
    if seed_opt is None:
        return int(random.randint(1, 2_000_000_000))
    return int(seed_opt)


# === 临时：英文显示名（用于 trace 可读性）===
# 说明：当前仓库里 UnitType.name 是中文；正式做中英双语时建议把 i18n 做到 constants / resources 中。
UNIT_KEY_TO_EN: dict[str, str] = {
    "Q": "Warrior",
    "W": "Shieldbearer",
    "E": "Hammer",
    "R": "Berserker",
    "A": "Priest",
    "S": "Archer",
    "D": "Mage",
    "F": "Rhino",
    "G": "Assassin",
    "H": "Interceptor",
    "J": "Drummer",
    "K": "Spearman",
    "L": "Frost Archer",
    "M": "Bomber",
    "N": "Light Cavalry",
    "O": "Splitling",
}


def _unit_en(key: str) -> str:
    k = str(key or "")
    return UNIT_KEY_TO_EN.get(k, k)


def _keys_to_en(keys: list[str]) -> list[str]:
    return [_unit_en(k) for k in (keys or [])]


def _counts_to_en(counts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in (counts or {}).items():
        out[_unit_en(str(k))] = int(v or 0)
    return out


def _alive_counts_by_lane(game: Game, side: str) -> list[int]:
    lanes = game.left_units if side == "left" else game.right_units
    out: list[int] = []
    for lane in range(len(lanes)):
        out.append(int(sum(1 for u in lanes[lane] if getattr(u, "alive", False))))
    return out


def _base_hps(game: Game, side: str) -> list[float]:
    bases = game.left_bases if side == "left" else game.right_bases
    return [float(getattr(b, "hp", 0.0)) for b in bases]


def _write_jsonl(fp, obj: dict[str, Any]) -> None:
    fp.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(int(lo), min(int(hi), int(v)))


def trace_one_battle(
    *,
    seed: int,
    plan: str,
    out_root: Path,
    snapshot_interval_sec: float,
    player_k: int,
    enemy_k: int,
) -> Path:
    sim = SimRunner(seed=seed, bot_tier="mid", build_plan_id=plan)
    state = sim.run.state
    assert state is not None

    # 选第一个战斗节点：沿着默认选路推进，直到遇到 battle node
    node = None
    nid = None
    for _ in range(32):
        nid = sim._choose_next_node(state)
        if nid is None:
            break
        state.move_to_node(nid)
        node = state.nodes.get(nid)
        if node and node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            break
    if (nid is None) or (node is None) or (node.node_type not in CAMPAIGN_BATTLE_NODE_TYPES):
        raise RuntimeError("未找到可追踪的战斗节点（battle node）。")

    total_campaign_stages = len(CAMPAIGN_PARAMS["ai_pool_sizes"])
    stage_idx = state.difficulty_index(node.node_type, total_campaign_stages)
    stage_idx = max(0, min(stage_idx, total_campaign_stages - 1))

    ai_pool = sim._campaign_node_enemy_units(state, node.node_id, total_campaign_stages)
    interval = CAMPAIGN_PARAMS["ai_interval_mult"][stage_idx]
    # === 覆盖双方兵种池数量（仅 trace 用）===
    # 说明：
    # - 不影响战役/主程序；只用于快速观察“多兵种时 bot 的出兵表现”
    # - 使用可复现 RNG：同 seed + 同参数 → 同一套双方兵种
    trace_rng = sim.run.fork_rng(f"trace_pool:p{int(player_k)}:e{int(enemy_k)}")
    all_keys = list(ORDER_KEYS)
    if not all_keys:
        raise RuntimeError("ORDER_KEYS 为空，无法抽取兵种池。")
    pk = _clamp_int(int(player_k), 1, len(all_keys))
    ek = _clamp_int(int(enemy_k), 1, len(all_keys))

    player_units = trace_rng.sample(all_keys, k=pk)
    enemy_units = trace_rng.sample(all_keys, k=ek)

    sim.run.units = list(player_units)
    sim.run.unit_levels = {k: 1 for k in sim.run.units}
    player_levels = {k: max(1, sim.run.unit_levels.get(k, 1)) for k in sim.run.units}

    ai_pool = list(enemy_units)
    modifiers = sim._battle_modifiers(node.node_type, state.day)

    game = Game(
        sim.run.units,
        sim.run.skills,
        ai_keys=ai_pool,
        ai_interval_mult=interval,
        boons={},  # 战役内移除 boon
        left_base_hps=sim.run.saved_left_base_hps,
        modifiers=modifiers,
        player_unit_levels=player_levels,
        left_forge=sim._build_left_forge_payload(),
        left_forge_substat_mult=sim._forge_substat_mult(),
    )
    sim.run.saved_left_base_hps = None

    bot_rng = sim.run.fork_rng("battle_bot")
    bot = MidBattleBot(bot_rng)

    run_dir = out_root / f"{_now_tag()}_seed{seed}_plan{plan}"
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "trace.jsonl"

    dt_step = float(DEFAULT_RUN.get("battle_dt", 0.10))
    max_time = float(DEFAULT_RUN.get("battle_max_time_sec", 180.0))
    wall_limit = float(DEFAULT_RUN.get("battle_wall_time_sec", 2.5))

    with trace_path.open("w", encoding="utf-8") as f:
        _write_jsonl(
            f,
            {
                "ev": "battle_start",
                "seed": int(seed),
                "plan": str(plan),
                "node_id": int(node.node_id),
                "node_type": str(node.node_type),
                "day": int(state.day),
                "stage_idx": int(stage_idx),
                "dt": float(dt_step),
                "max_time": float(max_time),
                "wall_limit": float(wall_limit),
                # 保留 key（稳定ID）+ 增加英文名（可读）
                "player_units_keys": list(sim.run.units),
                "player_units_en": _keys_to_en(list(sim.run.units)),
                "player_unit_levels": dict(player_levels),
                "player_skills": list(sim.run.skills),
                "enemy_pool_keys": list(ai_pool),
                "enemy_pool_en": _keys_to_en(list(ai_pool)),
                "ai_interval_mult": float(interval),
                "modifiers": dict(modifiers),
            },
        )

        t = 0.0
        next_snap = 0.0
        wall_start = time.perf_counter()
        timed_out = False
        while (not game.winner) and t < max_time:
            if wall_limit > 0 and (time.perf_counter() - wall_start) > wall_limit:
                timed_out = True
                break

            bot.step(game, dt_step)
            game.update(dt_step)
            t += dt_step

            if t + 1e-9 >= next_snap:
                left_counts = dict(getattr(game, "battle_left_spawn_counts", {}) or {})
                right_counts = dict(getattr(game, "battle_right_spawn_counts", {}) or {})
                player_keys = list(getattr(game, "player_order_keys", []) or [])
                ai_keys = list(getattr(game, "ai_order_keys", []) or [])
                _write_jsonl(
                    f,
                    {
                        "ev": "snapshot",
                        "t": round(float(t), 3),
                        "winner": str(game.winner or ""),
                        "left_base_hps": _base_hps(game, "left"),
                        "right_base_hps": _base_hps(game, "right"),
                        "left_alive_by_lane": _alive_counts_by_lane(game, "left"),
                        "right_alive_by_lane": _alive_counts_by_lane(game, "right"),
                        "left_resource": float(getattr(game.left, "resource", 0.0)),
                        "right_resource": float(getattr(game.right, "resource", 0.0)),
                        "left_spawn_counts_keys": left_counts,
                        "left_spawn_counts_en": _counts_to_en(left_counts),
                        "right_spawn_counts_keys": right_counts,
                        "right_spawn_counts_en": _counts_to_en(right_counts),
                        "right_spawned_types_keys": sorted(list(getattr(game, "battle_right_spawned_types", set()) or set())),
                        "right_spawned_types_en": _keys_to_en(
                            sorted(list(getattr(game, "battle_right_spawned_types", set()) or set()))
                        ),
                        "player_order_keys": player_keys,
                        "player_order_en": _keys_to_en(player_keys),
                        "ai_order_keys": ai_keys,
                        "ai_order_en": _keys_to_en(ai_keys),
                    },
                )
                next_snap += max(0.05, float(snapshot_interval_sec))

        _write_jsonl(
            f,
            {
                "ev": "battle_end",
                "t": round(float(getattr(game, "battle_time", t) or t), 3),
                "winner": str(game.winner or ""),
                "timed_out": bool(timed_out),
                "left_base_hps_end": _base_hps(game, "left"),
                "right_base_hps_end": _base_hps(game, "right"),
                "left_spawn_counts_keys": dict(getattr(game, "battle_left_spawn_counts", {}) or {}),
                "left_spawn_counts_en": _counts_to_en(dict(getattr(game, "battle_left_spawn_counts", {}) or {})),
                "right_spawn_counts_keys": dict(getattr(game, "battle_right_spawn_counts", {}) or {}),
                "right_spawn_counts_en": _counts_to_en(dict(getattr(game, "battle_right_spawn_counts", {}) or {})),
            },
        )

    return trace_path


def main() -> int:
    ap = argparse.ArgumentParser(prog="bot_trace.py", description="单局/单场战斗 Trace（无渲染）")
    ap.add_argument("--seed", type=int, default=DEFAULT_TRACE["seed"], help="随机种子；不填则随机")
    ap.add_argument(
        "--plan",
        type=str,
        default=str(DEFAULT_TRACE["plan"]),
        choices=BUILD_PLANS,
        help="BuildPlan（影响走图偏好/商店偏好）",
    )
    ap.add_argument("--out", type=str, default=str(DEFAULT_TRACE["out"]), help="输出目录")
    ap.add_argument(
        "--snapshot-interval-sec",
        type=float,
        default=float(DEFAULT_TRACE["snapshot_interval_sec"]),
        help="快照间隔（秒），建议 1.0",
    )
    ap.add_argument(
        "--player-k",
        type=int,
        default=int(DEFAULT_TRACE.get("player_k", 1)),
        help="我方兵种数量（trace 专用，默认 1）",
    )
    ap.add_argument(
        "--enemy-k",
        type=int,
        default=int(DEFAULT_TRACE.get("enemy_k", 1)),
        help="敌方兵种数量（trace 专用，默认 1）",
    )
    args = ap.parse_args()

    seed = _resolve_seed(getattr(args, "seed", None))
    out_root = Path(str(args.out))
    out_root.mkdir(parents=True, exist_ok=True)

    p = trace_one_battle(
        seed=int(seed),
        plan=str(args.plan),
        out_root=out_root,
        snapshot_interval_sec=float(args.snapshot_interval_sec),
        player_k=int(getattr(args, "player_k", DEFAULT_TRACE.get("player_k", 1)) or 1),
        enemy_k=int(getattr(args, "enemy_k", DEFAULT_TRACE.get("enemy_k", 1)) or 1),
    )
    print(f"[trace] seed={seed} wrote: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


