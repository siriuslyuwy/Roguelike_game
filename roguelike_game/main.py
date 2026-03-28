from __future__ import annotations

import sys
import traceback
import pygame as pg
import math
import time

from game.constants import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    CAMPAIGN_PARAMS,
    CAMPAIGN_ENEMY_DAMAGE_GROWTH,
    CAMPAIGN_ENEMY_HP_GROWTH,
    AI_RESOURCE_GROWTH_START_STAGE,
    AI_RESOURCE_GROWTH_PER_STAGE,
    AI_RESOURCE_CAP_GROWTH_PER_STAGE,
    BOONS,
    SKILL_ORDER,
    SKILLS,
    MAX_RESOURCE,
    BASE_MAX_HP,
    LANE_COUNT,
    CAMPAIGN_BATTLE_NODE_TYPES,
    CAMPAIGN_NODE_DISPLAY,
    TOP_UI_HEIGHT,
    BOTTOM_MARGIN,
    FORGE_RETARGET_BASE_COST,
    FORGE_RETARGET_PER_LEVEL_COST,
    FORGE_LEVEL_4_BONUS,
    FORGE_LEVEL_5_BONUS,
    FORGE_LEVEL_4_SUCCESS_RATE,
    FORGE_LEVEL_5_SUCCESS_RATE,
    PRISONER_RELEASE_GOLD,
    PRISONER_EXECUTE_GOLD,
    PRISONER_REP_GAIN,
    PRISONER_REP_LOSS,
    REPUTATION_MIN,
    REPUTATION_MAX,
    BLESSINGS,
    SHOP_REFRESH_BASE_COST,
    SHOP_ITEM_PRICE_LOW,
    SHOP_ITEM_PRICE_MED,
    SHOP_ITEM_PRICE_HIGH,
    SHOP_DONATE_GOLD_COST,
    SHOP_DONATE_REP_GAIN,
    SHOP_ROB_GOLD_GAIN,
    SHOP_ROB_REP_LOSS,
    EVENT_GOLD_SMALL,
    EVENT_GOLD_MED,
    EVENT_GOLD_LARGE,
    COMBO_CARDS,
    BLESSING_TRIGGER_BATTLE_COUNT,
    COMBO1_TRIGGER_BATTLE_COUNT,
    CAMPAIGN_BASE_GOLD,
    CAMPAIGN_GOLD_INCREMENT,
)
from game.campaign import CampaignState, generate_campaign_map, MAP_LAYER_GAP
from game.game import Game, ORDER_KEYS, UNIT_TYPES
from game.run_state import CampaignRunState
from game.save_system import (
    autosave_exists,
    delete_autosave,
    load_autosave,
    save_autosave,
    load_mirror_profile,
    save_mirror_profile,
)
from game.ui import (
    draw_world,
    draw_menu,
    draw_encyclopedia,
    draw_loadout,
    draw_reward_picker,
    draw_boon_select,
    draw_campaign_map,
    draw_campaign_shop,
    draw_campaign_shop_v2,
    draw_campaign_event,
    draw_campaign_event_choice,
    draw_campaign_event_unit_select,
    draw_campaign_event_skill_select,
    draw_campaign_victory,
    draw_campaign_defeat,
    draw_campaign_postbattle_summary,
    draw_campaign_forge,
    draw_campaign_prisoners,
    draw_campaign_blessing_select,
    draw_campaign_combo_select,
    draw_settings,
    draw_pause_menu,
)
from game.font import get_font
from game.audio import AudioManager
from game.localization import get_lang, set_lang, tr
import random

# 战斗时间奖励阈值（秒, 金币）——可按需求调整
CAMPAIGN_TIME_REWARD_TIERS = [
    (60.0, 120),   # 1 分钟内通关奖励
    (120.0, 60),  # 2 分钟内通关奖励
    (180.0, 30),  # 3 分钟内通关奖励
]


def run():
    try:
        pg.init()
        
        # 虚拟分辨率（游戏逻辑分辨率）
        VIRTUAL_WIDTH = SCREEN_WIDTH
        VIRTUAL_HEIGHT = SCREEN_HEIGHT
        
        # 初始窗口大小（可以是逻辑分辨率的一半、一倍或其他）
        window_width = VIRTUAL_WIDTH
        window_height = VIRTUAL_HEIGHT
        
        # 创建真实显示窗口（支持调整大小）
        screen = pg.display.set_mode((window_width, window_height), pg.RESIZABLE)
        
        # 创建虚拟画布（所有游戏内容绘制在此）
        canvas = pg.Surface((VIRTUAL_WIDTH, VIRTUAL_HEIGHT))
        
        pg.display.set_caption(str(tr("几何大战 - 7 战线", "Geometry War - 7 Lanes")))
        clock = pg.time.Clock()
        font = get_font(18)
        
        # 音频管理器
        audio_manager = AudioManager()

        # 设置相关状态
        resolutions = [
            (1280, 720),
            (1366, 768),
            (1440, 900),
            (1600, 900),
            (1920, 1080),
            (2560, 1440),
        ]
        # 尝试匹配当前分辨率到列表中，如果没有则加入
        if (window_width, window_height) not in resolutions:
            resolutions.append((window_width, window_height))
            resolutions.sort()
        
        current_res_idx = 0
        try:
            current_res_idx = resolutions.index((window_width, window_height))
        except ValueError:
            pass
            
        settings_cursor = 0  # 0: 分辨率, 1: 全屏, 2: BGM, 3: SFX, 4: 语言
        settings_return_mode = "menu"
        is_fullscreen = False
        
        pause_cursor = 0
        paused_from_mode = "menu"
        time_scale = 1.0  # 战斗倍速控制

        # 局外配阵：默认前 5 个兵种 + 默认技能
        loadout_units = ORDER_KEYS[:5]
        loadout_unit_levels: dict[str, int] = {k: 1 for k in loadout_units}
        default_skill = SKILL_ORDER[0] if SKILL_ORDER else (next(iter(SKILLS.keys()), None))
        loadout_skills = [default_skill] if default_skill else []
        game = Game(loadout_units, loadout_skills, player_unit_levels=loadout_unit_levels)
        mode = "menu"  # menu | encyclopedia | game | campaign_loadout | campaign_battle | campaign_postbattle_summary | campaign_forge | campaign_prisoners | campaign_blessing_select | campaign_combo_select | campaign_event_choice | campaign_victory | campaign_defeat | free_loadout | free_boons | free_battle | campaign_map | campaign_shop | settings
        encyclopedia_scroll = 0
        # 肉鸽状态
        MAX_UNIT_LEVEL = 4

        # === 战役 Run：M1 起，所有战役局内状态集中在 CampaignRunState ===
        campaign_run: CampaignRunState | None = None
        mirror_recording: list[dict] = []
        mirror_recording_enabled: bool = False

        def _autosave_now() -> None:
            nonlocal campaign_run
            if campaign_run and campaign_run.state:
                save_autosave(campaign_run)

        def _start_new_campaign() -> None:
            """开始新战役（Demo：单自动档）。"""
            nonlocal mode, campaign_run, loadout_cursor, loadout_focus, loadout_skill_idx
            profile = load_mirror_profile()
            last_mirror_snapshot = dict(profile.get("mirror_snapshot") or {})
            last_mirror_script = list(profile.get("mirror_script") or [])
            last_mirror_updated = float(profile.get("mirror_last_updated", 0.0) or 0.0)
            delete_autosave()
            reset_campaign_run()
            campaign_run = CampaignRunState()
            campaign_run.units = []
            campaign_run.unit_levels = {}
            campaign_run.skills.clear()
            # M4：战役开局无技能；技能只能在商店购买
            loadout_cursor = 0
            loadout_focus = "units"
            loadout_skill_idx = 0
            campaign_run.boons = {}
            campaign_run.reward_options = []
            campaign_run.saved_left_base_hps = None
            campaign_run.mirror_snapshot = last_mirror_snapshot
            campaign_run.mirror_script = last_mirror_script
            campaign_run.mirror_last_updated = last_mirror_updated
            mode = "campaign_loadout"

        loadout_cursor = 0
        loadout_focus = "units"  # units | skill
        loadout_skill_idx = 0
        # 自由模式
        free_units: list[str] = []
        free_unit_levels: dict[str, int] = {}
        free_boons: dict[str, int] = {}
        boon_cursor = 0
        free_skills: list[str] = [default_skill] if default_skill else []
        total_campaign_stages = len(CAMPAIGN_PARAMS["ai_pool_sizes"])
        
        # 通关统计
        # （已迁移到 CampaignRunState）

        SHOP_ITEM_COST = 250
        SHOP_REFRESH_COST = 50

        def _format_duration(seconds: float) -> str:
            total = max(0, int(seconds))
            return f"{total // 60:02d}:{total % 60:02d}"

        def _current_unit_level(key: str) -> int:
            if not campaign_run:
                return 0
            return max(0, min(MAX_UNIT_LEVEL, campaign_run.unit_levels.get(key, 0)))

        def _set_unit_level(key: str, level: int) -> None:
            if not campaign_run:
                return
            clamped = max(0, min(MAX_UNIT_LEVEL, level))
            if clamped <= 0:
                if key in campaign_run.unit_levels:
                    campaign_run.unit_levels.pop(key, None)
                if key in campaign_run.units:
                    campaign_run.units.remove(key)
                return
            campaign_run.unit_levels[key] = clamped
            if key not in campaign_run.units:
                campaign_run.units.append(key)

        def campaign_option_pools() -> tuple[list[str], list[str], list[str]]:
            units: list[str] = []
            if not campaign_run:
                return [], [], []
            unit_cap_reached = len(campaign_run.units) >= _max_unit_count()
            for key in ORDER_KEYS:
                cur_level = _current_unit_level(key)
                if cur_level >= MAX_UNIT_LEVEL:
                    continue
                if cur_level == 0 and unit_cap_reached:
                    continue
                units.append(key)
            # M4 起：战役内移除 boon；技能改为商店购买（此处不再提供奖励池）
            return units, [], []

        def build_campaign_reward_pool() -> tuple[list[str], list[str], list[str], list[str]]:
            remaining_units, remaining_skills, boon_candidates = campaign_option_pools()
            pool: list[str] = []
            pool.extend(remaining_units)
            pool.extend(remaining_skills)
            pool.extend(boon_candidates)
            return pool, remaining_units, remaining_skills, boon_candidates

        def generate_campaign_reward_options(limit: int) -> list[str]:
            pool, remaining_units, remaining_skills, boon_candidates = build_campaign_reward_pool()
            if not pool:
                return []
            limit = max(0, min(limit, len(pool)))
            options: list[str] = []

            # 计算权重：已解锁的兵种概率+50%
            def _get_weight(key: str) -> float:
                if key in ORDER_KEYS:
                    cur_level = _current_unit_level(key)
                    if cur_level > 0:  # 已解锁的兵种
                        return 1.5  # +50%概率
                return 1.0  # 未解锁的兵种或其他选项

            def _weighted_choice(items: list[str], exclude: set[str]) -> str | None:
                if not items:
                    return None
                valid_items = [item for item in items if item not in exclude]
                if not valid_items:
                    return None
                weights = [_get_weight(item) for item in valid_items]
                return random.choices(valid_items, weights=weights)[0]

            def _try_add(category: list[str]) -> None:
                nonlocal options
                if not category or len(options) >= limit:
                    return
                pick = _weighted_choice(category, set(options))
                if pick:
                    options.append(pick)

            _try_add(remaining_skills)
            _try_add(boon_candidates)
            _try_add(remaining_units)

            remaining_pool = [opt for opt in pool if opt not in options]
            while len(options) < limit and remaining_pool:
                pick = _weighted_choice(remaining_pool, set(options))
                if pick:
                    options.append(pick)
                    remaining_pool = [opt for opt in remaining_pool if opt != pick]
                else:
                    break
            return options

        def roll_campaign_shop_items() -> list[dict]:
            pool, _, _, _ = build_campaign_reward_pool()
            if not pool:
                return [{"key": None, "sold": False} for _ in range(4)]
            count = min(4, len(pool))
            
            # 计算权重：已解锁的兵种概率+50%
            def _get_weight(key: str) -> float:
                if key in ORDER_KEYS:
                    cur_level = _current_unit_level(key)
                    if cur_level > 0:  # 已解锁的兵种
                        return 1.5  # +50%概率
                return 1.0  # 未解锁的兵种或其他选项
            
            if len(pool) <= count:
                picks = pool[:]
                random.shuffle(picks)
            else:
                # 使用加权随机选择（不重复）
                picks = []
                remaining_pool = pool[:]
                for _ in range(count):
                    if not remaining_pool:
                        break
                    weights = [_get_weight(key) for key in remaining_pool]
                    pick = random.choices(remaining_pool, weights=weights, k=1)[0]
                    picks.append(pick)
                    remaining_pool.remove(pick)
            
            items = [{"key": key, "sold": False} for key in picks]
            while len(items) < 4:
                items.append({"key": None, "sold": False})
            return items

        def apply_campaign_purchase(key: str) -> tuple[bool, str]:
            if not campaign_run:
                return False, "战役尚未开始"
            if key in SKILLS:
                cfg = SKILLS.get(key, {})
                if key in campaign_run.skills:
                    return False, "已拥有该技能"
                # M4：默认上限 3，可被 Combo 提升到 4
                skill_cap = 3 + (1 if "combo_skill_slot" in campaign_run.combo.selected_cards else 0)
                if len(campaign_run.skills) >= skill_cap:
                    return False, "技能栏位已满"
                campaign_run.skills.append(key)
                return True, f"获得技能：{cfg.get('name', key)}"
            if key in ORDER_KEYS:
                cur_level = _current_unit_level(key)
                ut = UNIT_TYPES.get(key)
                name = ut.name if ut else key
                if cur_level >= MAX_UNIT_LEVEL:
                    return False, f"{name} 已达最高等级"
                if cur_level == 0 and len(campaign_run.units) >= _max_unit_count():
                    return False, "兵种列表已达上限"
                new_level = cur_level + 1 if cur_level > 0 else 1
                _set_unit_level(key, new_level)
                if cur_level == 0:
                    return True, f"获得兵种：{name} (Lv{new_level})"
                return True, f"{name} 等级提升至 Lv{new_level}"
            return False, "未知商品"

        def _rep_segment(rep: int) -> str:
            if rep > 10:
                return "saint"
            if rep < -10:
                return "demon"
            return "lord"

        def _combo_tags_of_selected() -> set[str]:
            tags: set[str] = set()
            for cid in campaign_run.combo.selected_cards if campaign_run else []:
                cfg = COMBO_CARDS.get(cid, {})
                for t in cfg.get("tags", []):
                    tags.add(str(t))
            return tags

        def _roll_combo_options() -> list[str]:
            """生成 3 张候选，尽量与已有体系标签相关（轻量保底）。"""
            if not campaign_run:
                return []
            rng = campaign_run.fork_rng(f"combo:{campaign_run.combo_context or 'unknown'}")
            # 重要：排除已拥有的 Combo，避免出现“选了但张数不变→里程碑反复触发”的死循环/体验问题
            owned = set(campaign_run.combo.selected_cards or [])
            all_ids = [cid for cid in list(COMBO_CARDS.keys()) if cid not in owned]
            rng.shuffle(all_ids)
            if not all_ids:
                return []
            selected_tags = _combo_tags_of_selected()
            options: list[str] = []
            if selected_tags:
                # 先塞一个相关标签（若存在）
                related = [cid for cid in all_ids if selected_tags.intersection(set(COMBO_CARDS.get(cid, {}).get("tags", [])))]
                if related:
                    options.append(rng.choice(related))
            while len(options) < 3 and all_ids:
                pick = rng.choice(all_ids)
                all_ids = [x for x in all_ids if x != pick]
                if pick not in options:
                    options.append(pick)
            return options[:3]

        def _apply_combo_card(card_id: str) -> str:
            if not campaign_run:
                return ""
            if card_id in campaign_run.combo.selected_cards:
                return "已拥有该 Combo"
            campaign_run.combo.selected_cards.append(card_id)
            # 落地一些简单效果（M4先做“可感知且低风险”的参数）
            # 特殊效果处理
            if card_id == "combo_war_funding":
                campaign_run.battle_gold_mult = 1.2
            elif card_id == "combo_prisoner_bounty":
                campaign_run.prisoner_gold_mult = 1.2
            
            return f"获得 Combo：{COMBO_CARDS.get(card_id, {}).get('name', card_id)}"

        def _combo_enter(context: str, pending_node_id: int | None = None) -> None:
            nonlocal mode
            if not campaign_run:
                return
            campaign_run.combo_context = context
            campaign_run.combo_pending_node_id = pending_node_id
            campaign_run.combo_options = _roll_combo_options()
            campaign_run.combo_idx = 0
            mode = "campaign_combo_select"

        def _blessing_enter() -> None:
            nonlocal mode
            if not campaign_run:
                return
            rng = campaign_run.fork_rng("blessing")
            pool = list(BLESSINGS.keys())
            rng.shuffle(pool)
            campaign_run.blessing_options = pool[:4] if len(pool) >= 4 else pool[:]
            campaign_run.blessing_idx = 0
            mode = "campaign_blessing_select"

        def _milestone_combo_reason() -> str:
            """返回一个用于 UI/seed 的 context key（battle3/shop_event/elite_win）。"""
            if not campaign_run or not campaign_run.state:
                return "unknown"
            bc = int(campaign_run.state.battle_count or 0)
            shops = int(getattr(campaign_run, "shops_visited", 0) or 0)
            events = int(getattr(campaign_run, "events_visited", 0) or 0)
            elite_once = bool(getattr(campaign_run, "elite_victory_once", False))
            
            # 支持独立触发：检查哪些条件满足且未发放过
            if not campaign_run.milestone_battle3_claimed and bc >= int(COMBO1_TRIGGER_BATTLE_COUNT):
                return "battle3"
            if not campaign_run.milestone_shop_event_claimed and shops >= 1 and events >= 1:
                return "shop_event"
            if not campaign_run.milestone_elite_win_claimed and elite_once:
                return "elite_win"
            return "unknown"

        def _maybe_enter_milestone_rewards() -> bool:
            """
            里程碑发放（三个独立条件触发）：
            - 祝福：首战后一次
            - Combo1（槽位A）：累计 3 场战斗胜利
            - Combo2（槽位B）：至少进过 1 次商店且 1 次事件
            - Combo3（槽位C）：首次击败精英
            返回：是否已切换到其他界面（祝福/Combo 选择）。
            """
            nonlocal mode
            if not campaign_run or not campaign_run.state:
                return False

            bc = int(campaign_run.state.battle_count or 0)
            shops = int(getattr(campaign_run, "shops_visited", 0) or 0)
            events = int(getattr(campaign_run, "events_visited", 0) or 0)
            elite_once = bool(getattr(campaign_run, "elite_victory_once", False))
            nsel = len(campaign_run.combo.selected_cards or [])

            # 1) 祝福优先（避免同一时刻弹多个）
            if (not campaign_run.blessing_taken) and (bc >= int(BLESSING_TRIGGER_BATTLE_COUNT)):
                _blessing_enter()
                return True

            # 2) Combo 里程碑（三个独立条件触发，解除 nsel 顺序限制）
            # 槽位 A：累计 3 场战斗胜利
            if not campaign_run.milestone_battle3_claimed and bc >= int(COMBO1_TRIGGER_BATTLE_COUNT):
                # 标记已发放（防止重复触发）
                campaign_run.milestone_battle3_claimed = True
                # 弱兵种开局已提前获得Combo1，跳过
                if getattr(campaign_run, "weak_start_combo_given", False):
                    # 弱兵种开局：跳过Combo1，继续检查后续里程碑
                    pass
                else:
                    _combo_enter("battle3", pending_node_id=None)
                    return True

            # 槽位 B：至少进过 1 次商店且 1 次事件
            if not campaign_run.milestone_shop_event_claimed and shops >= 1 and events >= 1:
                campaign_run.milestone_shop_event_claimed = True
                _combo_enter("shop_event", pending_node_id=None)
                return True

            # 槽位 C：首次击败精英
            if not campaign_run.milestone_elite_win_claimed and elite_once:
                campaign_run.milestone_elite_win_claimed = True
                _combo_enter("elite_win", pending_node_id=None)
                return True

            return False

        def _count_nonbattle_if_applicable(node_id: int) -> None:
            """在节点被清除时调用：若该节点是非战斗节点，则累计一次。"""
            if not campaign_run or not campaign_run.state:
                return
            node = campaign_run.state.nodes.get(node_id)
            if not node:
                return
            if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
                return
            campaign_run.nonbattle_cleared_count = int(getattr(campaign_run, "nonbattle_cleared_count", 0) or 0) + 1

        def _shop_enter(node_id: int) -> None:
            """进入商店（已通过 Combo 检查后）。"""
            nonlocal mode
            if not campaign_run or not campaign_run.state:
                return
            campaign_run.shop_node_id = node_id
            campaign_run.shop_cursor = 0
            campaign_run.shop_message = ""
            campaign_run.shop_donated = False
            campaign_run.shop_robbery_confirm = False
            campaign_run.shop_refresh_paid_count = 0

            # 一次性券结算：free refresh disabled / bonus / price mult
            base_free = 1
            if campaign_run.oneshot.next_shop_free_refresh_disabled:
                base_free = 0
                campaign_run.oneshot.next_shop_free_refresh_disabled = False
            bonus = max(0, int(campaign_run.oneshot.next_shop_free_refresh_bonus))
            campaign_run.oneshot.next_shop_free_refresh_bonus = 0
            campaign_run.shop_free_refresh_left = base_free + bonus
            # 价格乘区（一次性）
            price_mult = float(campaign_run.oneshot.next_shop_price_mult_once or 1.0)
            campaign_run.oneshot.next_shop_price_mult_once = 1.0

            # 弱势开局补偿（方案B升级版）：若开局为弱势首槽，则"第一次商店"全场商品 7 折
            weak_start_units = {"maul", "rhino", "assassin", "light_cavalry", "exploder"}
            primary = str(getattr(campaign_run, "primary_unit", "") or "")
            if int(getattr(campaign_run, "shops_visited", 0) or 0) <= 0 and primary in weak_start_units:
                price_mult *= 0.7
            campaign_run.shops_visited = int(getattr(campaign_run, "shops_visited", 0) or 0) + 1
            campaign_run.shop_price_mult_current = float(price_mult)

            campaign_run.shop_items = _roll_shop_items(price_mult)
            # 光标尽量落在可用格子上（避免一进店就选到封锁格）
            for i, it in enumerate(list(campaign_run.shop_items or [])[:4]):
                if isinstance(it, dict) and it.get("locked"):
                    continue
                campaign_run.shop_cursor = int(i)
                break
            mode = "campaign_shop"

        def _roll_shop_items(price_mult: float = 1.0) -> list[dict]:
            if not campaign_run:
                return [{"type": "empty", "sold": False, "price": 0, "name": "空", "desc": ""} for _ in range(4)]
            rng = campaign_run.fork_rng("shop_items")

            def apply_shop_lock_penalty(items: list[dict]) -> list[dict]:
                """
                抢劫惩罚：本周目商店“永久减格”。
                实现方式：仍生成4个商品，但根据抢劫次数随机封锁若干格（locked=True）。
                关键约束：若玩家尚未获得任何技能，则不会封锁技能格（确保“第一技能”逻辑不被破坏）。
                """
                if not campaign_run:
                    return items
                try:
                    robbery_n = int(getattr(campaign_run, "shop_robbery_count", 0) or 0)
                except Exception:
                    robbery_n = 0
                lock_n = max(0, min(int(robbery_n), 4))

                # 清理旧标记（防止刷新/复用时残留）
                for it in items:
                    if isinstance(it, dict):
                        it.pop("locked", None)
                        it.pop("lock_reason", None)

                if lock_n <= 0:
                    return items

                must_keep_skill = len(getattr(campaign_run, "skills", []) or []) <= 0

                def _eligible(idx: int) -> bool:
                    if idx < 0 or idx >= len(items):
                        return False
                    it = items[idx]
                    if not isinstance(it, dict):
                        return False
                    t = str(it.get("type") or "")
                    if must_keep_skill and t == "skill":
                        return False
                    return True

                # 为了让惩罚“有效”，尽量不要封住 empty / sold（它们本身就不是有效选项）
                def _cand(priority: str) -> list[int]:
                    out: list[int] = []
                    for i in range(min(4, len(items))):
                        if not _eligible(i):
                            continue
                        it = items[i]
                        t = str(it.get("type") or "")
                        sold = bool(it.get("sold"))
                        if priority == "unsold_nonempty":
                            if (not sold) and t != "empty":
                                out.append(i)
                        elif priority == "unsold_any":
                            if not sold:
                                out.append(i)
                        else:  # any
                            out.append(i)
                    return out

                pool = _cand("unsold_nonempty") or _cand("unsold_any") or _cand("any")
                if not pool:
                    return items

                lock_n = min(lock_n, len(pool))
                lock_rng = campaign_run.fork_rng("shop_locks")
                lock_idxs = lock_rng.sample(pool, k=int(lock_n))
                for i in lock_idxs:
                    if isinstance(items[i], dict):
                        items[i]["locked"] = True
                        items[i]["lock_reason"] = "robbery"
                return items

            def price(base: int) -> int:
                mult = max(0.0, float(price_mult))
                # 祝福：定向投资 → 购买价 -10%
                if campaign_run and campaign_run.blessing_selected == "direct_invest":
                    mult *= 0.9
                return max(0, int(math.ceil(base * mult)))

            items: list[dict] = []

            # 1. 兵种升级/解锁（最多2个）
            unit_candidates = [k for k in ORDER_KEYS if (_current_unit_level(k) < MAX_UNIT_LEVEL) and not (_current_unit_level(k) == 0 and len(campaign_run.units) >= _max_unit_count())]
            if campaign_run.blessing_selected != "veteran_unyielding":
                unit_candidates = [k for k in unit_candidates if k != "warrior"]
            rng.shuffle(unit_candidates)
            for _ in range(2):
                if unit_candidates:
                    uk = unit_candidates.pop()
                    ut = UNIT_TYPES.get(uk)
                    nm = ut.name if ut else uk
                    cur = _current_unit_level(uk)
                    label = f"{nm} 升级" if cur > 0 else f"{nm} 解锁"
                    items.append({"type": "unit", "payload": uk, "sold": False, "price": price(SHOP_ITEM_PRICE_MED), "name": label, "desc": "立即解锁/升1级"})

            # 2. 技能购买（最多1个）
            skill_cap = 3 + (1 if "combo_skill_slot" in campaign_run.combo.selected_cards else 0)
            if len(campaign_run.skills) < skill_cap:
                skills = [k for k in SKILL_ORDER if k not in campaign_run.skills]
                rng.shuffle(skills)
                if skills:
                    sk = skills.pop()
                    cfg = SKILLS.get(sk, {})
                    items.append({"type": "skill", "payload": sk, "sold": False, "price": price(SHOP_ITEM_PRICE_HIGH), "name": f"技能：{cfg.get('name', sk)}", "desc": cfg.get("desc", "")})

            # 3. 填充锻造器，确保永远是4个商品，不出现“空位”
            while len(items) < 4:
                items.append({"type": "forge_device", "payload": "normal", "sold": False, "price": price(SHOP_ITEM_PRICE_LOW), "name": "普通锻造器", "desc": "立即进行一次锻造（结束后回到商店）"})

            rng.shuffle(items)
            items = items[:4]
            return apply_shop_lock_penalty(items)

        def _event_enter(node_id: int) -> None:
            """根据声望概率抽取池子（60/40/20权重），并生成事件文案。"""
            nonlocal mode
            if not campaign_run or not campaign_run.state:
                return

            campaign_run.event_node_id = node_id
            campaign_run.event_choice_idx = 0
            # 记录事件访问次数
            campaign_run.events_visited = int(getattr(campaign_run, "events_visited", 0) or 0) + 1
            
            # 1. 确定当前身份段位
            seg = _rep_segment(campaign_run.reputation)
            rng = campaign_run.fork_rng("event_pool_pick")
            
            # 2. 核心权重逻辑：圣人 (S:60%, M:40%), 恶魔 (D:60%, M:40%), 君主 (M:60%, S:20%, D:20%)
            if seg == "saint":
                pool_type = rng.choices(["S", "M"], weights=[0.6, 0.4])[0]
            elif seg == "demon":
                pool_type = rng.choices(["D", "M"], weights=[0.6, 0.4])[0]
            else: # lord
                pool_type = rng.choices(["M", "S", "D"], weights=[0.6, 0.2, 0.2])[0]

            # 3. 从对应池子抽取 TID (1-4)
            templates = [f"{pool_type}{i}" for i in range(1, 5)]
            recent = set((campaign_run.recent_event_templates or [])[-2:])
            candidates = [t for t in templates if t not in recent] or templates[:]
            tid = rng.choice(candidates)

            campaign_run.event_template_id = tid
            campaign_run.recent_event_templates.append(tid)
            campaign_run.recent_event_templates = campaign_run.recent_event_templates[-2:]

            # 4. 设置标题与文案
            titles = {
                "S1": "洗礼与牺牲", "S2": "孤本与转机", "S3": "铁砧与节制", "S4": "名望的价值",
                "M1": "皇家征召", "M2": "学院赞助", "M3": "工坊巡视", "M4": "外交立场",
                "D1": "血肉祭坛", "D2": "洗劫集市", "D3": "禁忌重铸", "D4": "恶魔招募"
            }
            campaign_run.event_title = f"{titles.get(tid, tid)}"
            identity_names = {"saint": "圣人", "lord": "君主", "demon": "恶魔"}
            campaign_run.event_desc = f"身份：{identity_names[seg]} (声望 {campaign_run.reputation})"

            # 5. 生成 A/B 选项文案
            _setup_detailed_event_text(tid)
            mode = "campaign_event_choice"

        def _setup_detailed_event_text(tid: str):
            """定义 12 个事件的具体文案"""
            # --- 圣人池 (S) ---
            if tid == "S1":
                campaign_run.event_option_a = "A：洗礼（免费：出击最少单位等级+1）"
                campaign_run.event_option_b = "B：牺牲（所有金币归零[需>100]：随机两单位等级+2）"
            elif tid == "S2":
                campaign_run.event_option_a = "A：孤本（支付金币：获取高阶技能）"
                campaign_run.event_option_b = "B：转机（免费：Combo重抽券x2且候选变为4项）"
            elif tid == "S3":
                campaign_run.event_option_a = "A：圣化铁砧（免费：随机一单位攻防各+1）"
                campaign_run.event_option_b = "B：节制（免费：下次商店前2件商品5折）"
            elif tid == "S4":
                campaign_run.event_option_a = "A：名望变现（名声-3：获得300金币）"
                campaign_run.event_option_b = "B：坚守正道（名声+1：无金币奖励）"
            
            # --- 君主池 (M) ---
            elif tid == "M1":
                campaign_run.event_option_a = "A：皇家征召（支付150金：从二者选一解锁）"
                campaign_run.event_option_b = "B：补助（不解锁：获得50金币）"
            elif tid == "M2":
                campaign_run.event_option_a = "A：学院赞助（支付200金：获得一随机技能）"
                campaign_run.event_option_b = "B：税收（获得80金币）"
            elif tid == "M3":
                campaign_run.event_option_a = "A：工坊巡视（支付80金：提升指定单位攻击等级）"
                campaign_run.event_option_b = "B：经验总结（免费：两随机单位等级+1）"
            elif tid == "M4":
                campaign_run.event_option_a = "A：外交表态（支付100金：名声+2）"
                campaign_run.event_option_b = "B：变卖物资（名声-2：获得150金币）"

            # --- 恶魔池 (D) ---
            elif tid == "D1":
                campaign_run.event_option_a = "A：血肉祭坛（解散指定兵种：随机获一技能）"
                campaign_run.event_option_b = "B：强制进化（免费：直接获得一随机新兵种）"
            elif tid == "D2":
                campaign_run.event_option_a = "A：洗劫（名声-5：获得400金币）"
                campaign_run.event_option_b = "B：放下屠刀（花光金币：名声直接+10并再发圣人事件）"
            elif tid == "D3":
                campaign_run.event_option_a = "A：禁忌重铸（随机一单位锻造归零：指定一单位攻防升至3级）"
                campaign_run.event_option_b = "B：知识荒废（删除指定技能：获得300金币）"
            elif tid == "D4":
                campaign_run.event_option_a = "A：恶魔招募（免费：随机补满所有兵种空位）"
                campaign_run.event_option_b = "B：无事发生（离开）"

        def _apply_event_choice(choice_idx: int) -> str:
            """结算事件A/B，处理锻造、兵种、技能逻辑。"""
            nonlocal mode
            if not campaign_run or not campaign_run.state:
                return ""

            tid = campaign_run.event_template_id
            rng = campaign_run.fork_rng(f"event:{tid}")
            gold_delta = 0
            rep_delta = 0
            msg = ""

            # === 圣人池 (S1-S4) ===
            if tid == "S1":
                if choice_idx == 0:  # A: 洗礼（免费升级出击最少单位）
                    if not campaign_run.units:
                        msg = "洗礼：没有可升级的兵种"
                    else:
                        target = min(campaign_run.units, key=lambda uk: campaign_run.forge.spawn_count_by_unit.get(uk, 0))
                        cur_level = _current_unit_level(target)
                        if cur_level < MAX_UNIT_LEVEL:
                            _set_unit_level(target, cur_level + 1)
                            ut = UNIT_TYPES.get(target)
                            msg = f"洗礼：{ut.name if ut else target} 等级提升至 Lv{cur_level + 1}"
                        else:
                            msg = f"洗礼：{UNIT_TYPES.get(target).name if UNIT_TYPES.get(target) else target} 已达最高等级"
                else:  # B: 牺牲（花光金币升2级）
                    if campaign_run.state.gold < 100:
                        msg = "牺牲：金币不足（需要至少100金）"
                    else:
                        campaign_run.state.gold = 0
                        # 随机两个兵种升级
                        upgradeable = [uk for uk in campaign_run.units if _current_unit_level(uk) < MAX_UNIT_LEVEL]
                        if len(upgradeable) >= 2:
                            targets = rng.sample(upgradeable, 2)
                        elif len(upgradeable) == 1:
                            targets = upgradeable * 2  # 同一个升两次
                        else:
                            msg = "牺牲：没有可升级的兵种"
                            return msg
                        for target in targets:
                            cur_level = _current_unit_level(target)
                            _set_unit_level(target, cur_level + 1)
                        msg = f"牺牲：散尽家财，{len(set(targets))}个兵种获得质变"

            elif tid == "S2":
                if choice_idx == 0:  # A: 孤本（支付金币获技能）
                    if campaign_run.state.gold < 200:
                        msg = "孤本：金币不足（需要200金）"
                    else:
                        available_skills = [sk for sk in SKILLS.keys() if sk not in campaign_run.skills]
                        skill_cap = 3 + (1 if "combo_skill_slot" in campaign_run.combo.selected_cards else 0)
                        if len(campaign_run.skills) >= skill_cap:
                            msg = "孤本：技能栏位已满"
                        elif not available_skills:
                            msg = "孤本：已学会所有技能"
                        else:
                            campaign_run.state.gold -= 200
                            target_skill = rng.choice(available_skills)
                            campaign_run.skills.append(target_skill)
                            msg = f"孤本：习得技能【{SKILLS[target_skill]['name']}】"
                else:  # B: 转机（Combo重抽券x2且候选变4项）
                    campaign_run.oneshot.next_combo_reroll_once = True
                    campaign_run.oneshot.next_combo_slot_bonus = 1  # 候选+1（3变4）
                    msg = "转机：获得2张Combo重抽券，且下次候选变为4项"

            elif tid == "S3":
                if choice_idx == 0:  # A: 圣化铁砧（随机一单位攻防+1）
                    if not campaign_run.units:
                        msg = "圣化铁砧：没有可锻造的兵种"
                    else:
                        target = rng.choice(campaign_run.units)
                        campaign_run.forge.offense_level_by_unit[target] = min(5, campaign_run.forge.offense_level_by_unit.get(target, 0) + 1)
                        campaign_run.forge.defense_level_by_unit[target] = min(5, campaign_run.forge.defense_level_by_unit.get(target, 0) + 1)
                        ut = UNIT_TYPES.get(target)
                        msg = f"圣化铁砧：{ut.name if ut else target} 攻防各+1"
                else:  # B: 节制（下次商店前2件商品5折）
                    campaign_run.oneshot.next_shop_discount_count = 2
                    msg = "节制：获得圣恩券（下次商店前2件商品5折）"

            elif tid == "S4":
                if choice_idx == 0:  # A: 名望变现
                    gold_delta = 300
                    rep_delta = -3
                    msg = "名望变现：获得300金币，但名声受损"
                else:  # B: 坚守正道
                    rep_delta = 1
                    msg = "坚守正道：名声略有提升"

            # === 君主池 (M1-M4) ===
            elif tid == "M1":
                if choice_idx == 0:  # A: 皇家征召（支付150金：从二者选一解锁）
                    if campaign_run.state.gold < 150:
                        msg = "皇家征召：金币不足（需要150金）"
                    else:
                        locked = [uk for uk in ORDER_KEYS if uk not in campaign_run.units]
                        if not locked or len(campaign_run.units) >= _max_unit_count():
                            msg = "皇家征召：兵种列表已满或无可解锁兵种"
                        else:
                            campaign_run.state.gold -= 150
                            # 2选1
                            count = min(2, len(locked))
                            targets = rng.sample(locked, count)
                            campaign_run.event_pending_action = "royal_summon_choice"
                            campaign_run.event_candidates = targets
                            mode = "campaign_event_unit_select"
                            msg = "皇家征召：请选择要解锁的兵种..."
                            return msg
                else:  # B: 补助
                    gold_delta = 50
                    msg = "补助：获得50金币"

            elif tid == "M2":
                if choice_idx == 0:  # A: 学院赞助（支付200金获技能）
                    if campaign_run.state.gold < 200:
                        msg = "学院赞助：金币不足（需要200金）"
                    else:
                        available_skills = [sk for sk in SKILLS.keys() if sk not in campaign_run.skills]
                        skill_cap = 3 + (1 if "combo_skill_slot" in campaign_run.combo.selected_cards else 0)
                        if len(campaign_run.skills) >= skill_cap:
                            msg = "学院赞助：技能栏位已满"
                        elif not available_skills:
                            msg = "学院赞助：已学会所有技能"
                        else:
                            campaign_run.state.gold -= 200
                            target_skill = rng.choice(available_skills)
                            campaign_run.skills.append(target_skill)
                            msg = f"学院赞助：习得技能【{SKILLS[target_skill]['name']}】"
                else:  # B: 税收
                    gold_delta = 80
                    msg = "税收：获得80金币"

            elif tid == "M3":
                if choice_idx == 0:  # A: 工坊巡视（支付80金提升攻击等级）
                    if campaign_run.state.gold < 80:
                        msg = "工坊巡视：金币不足（需要80金）"
                    elif not campaign_run.units:
                        msg = "工坊巡视：没有可锻造的兵种"
                    else:
                        campaign_run.state.gold -= 80
                        target = rng.choice(campaign_run.units)
                        campaign_run.forge.offense_level_by_unit[target] = min(5, campaign_run.forge.offense_level_by_unit.get(target, 0) + 1)
                        ut = UNIT_TYPES.get(target)
                        msg = f"工坊巡视：{ut.name if ut else target} 攻击等级+1"
                else:  # B: 经验总结（免费两随机单位等级+1）
                    if len(campaign_run.units) == 0:
                        msg = "经验总结：没有可升级的兵种"
                    else:
                        upgradeable = [uk for uk in campaign_run.units if _current_unit_level(uk) < MAX_UNIT_LEVEL]
                        if not upgradeable:
                            msg = "经验总结：所有兵种已达最高等级"
                        else:
                            count = min(2, len(upgradeable))
                            targets = rng.sample(upgradeable, count)
                            for target in targets:
                                cur_level = _current_unit_level(target)
                                _set_unit_level(target, cur_level + 1)
                            msg = f"经验总结：{count}个兵种等级提升"

            elif tid == "M4":
                if choice_idx == 0:  # A: 外交表态（支付100金名声+2）
                    if campaign_run.state.gold < 100:
                        msg = "外交表态：金币不足（需要100金）"
                    else:
                        campaign_run.state.gold -= 100
                        rep_delta = 2
                        msg = "外交表态：名声提升"
                else:  # B: 变卖物资
                    gold_delta = 150
                    rep_delta = -2
                    msg = "变卖物资：获得150金币，但名声受损"

            # === 恶魔池 (D1-D4) ===
            elif tid == "D1":
                if choice_idx == 0:  # A: 血肉祭坛（解散指定兵种获技能）
                    # 需要跳转到选兵界面
                    campaign_run.event_pending_action = "delete_unit_for_skill"
                    mode = "campaign_event_unit_select"
                    msg = "血肉祭坛：请选择要献祭的兵种..."
                    return msg
                else:  # B: 强制进化（免费获随机新兵种）
                    locked = [uk for uk in ORDER_KEYS if uk not in campaign_run.units]
                    if not locked or len(campaign_run.units) >= _max_unit_count():
                        msg = "强制进化：兵种列表已满或无可解锁兵种"
                    else:
                        target = rng.choice(locked)
                        _set_unit_level(target, 1)
                        ut = UNIT_TYPES.get(target)
                        msg = f"强制进化：获得兵种【{ut.name if ut else target}】"

            elif tid == "D2":
                if choice_idx == 0:  # A: 洗劫（名声-5获400金）
                    gold_delta = 400
                    rep_delta = -5
                    msg = "洗劫：获得400金币，名声大幅下降"
                else:  # B: 放下屠刀（花光金币名声+11并再发圣人事件）
                    campaign_run.state.gold = 0
                    campaign_run.reputation = 11
                    msg = "放下屠刀：散尽家财，名声重归圣洁。奇迹发生了..."
                    # 核心：不关闭界面，原地刷新
                    _event_enter(campaign_run.event_node_id)
                    return msg

            elif tid == "D3":
                if choice_idx == 0:  # A: 禁忌重铸（随机一单位锻造归零，指定一单位升3级）
                    if not campaign_run.units:
                        msg = "禁忌重铸：没有可操作的兵种"
                    else:
                        # 随机归零一个
                        victim = rng.choice(campaign_run.units)
                        campaign_run.forge.offense_level_by_unit[victim] = 0
                        campaign_run.forge.defense_level_by_unit[victim] = 0
                        # 需要跳转选择受益者
                        campaign_run.event_pending_action = "forge_to_3"
                        campaign_run.event_pending_target = victim
                        mode = "campaign_event_unit_select"
                        ut = UNIT_TYPES.get(victim)
                        msg = f"禁忌重铸：{ut.name if ut else victim} 锻造归零，请选择受益者..."
                        return msg
                else:  # B: 知识荒废（删除指定技能获300金）
                    if not campaign_run.skills:
                        msg = "知识荒废：没有可删除的技能"
                    else:
                        # 需要跳转到选技能界面
                        campaign_run.event_pending_action = "delete_skill_for_gold"
                        mode = "campaign_event_skill_select"
                        msg = "知识荒废：请选择要遗忘的技能..."
                        return msg

            elif tid == "D4":
                if choice_idx == 0:  # A: 恶魔招募（随机补满所有兵种空位）
                    max_count = _max_unit_count()
                    locked = [uk for uk in ORDER_KEYS if uk not in campaign_run.units]
                    slots_left = max_count - len(campaign_run.units)
                    if slots_left <= 0:
                        msg = "恶魔招募：兵种列表已满"
                    elif not locked:
                        msg = "恶魔招募：已解锁所有兵种"
                    else:
                        to_add = min(slots_left, len(locked))
                        new_units = rng.sample(locked, to_add)
                        for uk in new_units:
                            _set_unit_level(uk, 1)
                        msg = f"恶魔招募：强征{to_add}个兵种入伍"
                else:  # B: 无事发生
                    msg = "无事发生：你离开了"

            # 应用金币和名声变化
            # 祝福：掠夺者逻辑 - 全局金币+50%
            if campaign_run.blessing_selected == "looter_logic" and gold_delta > 0:
                gold_delta = int(gold_delta * 1.5)
            
            campaign_run.state.gold = max(0, campaign_run.state.gold + gold_delta)
            campaign_run.reputation = max(REPUTATION_MIN, min(REPUTATION_MAX, campaign_run.reputation + rep_delta))
            return msg

        def _execute_event_pending_action(selected_unit: str) -> str:
            """执行事件中的待处理动作（选兵后）"""
            if not campaign_run:
                return ""
            
            action = campaign_run.event_pending_action
            msg = ""
            
            if action == "delete_unit_for_skill":
                # D1A: 删除兵种获得技能
                if selected_unit in campaign_run.units:
                    campaign_run.units.remove(selected_unit)
                    if selected_unit in campaign_run.unit_levels:
                        del campaign_run.unit_levels[selected_unit]
                    # 随机获得技能
                    available_skills = [sk for sk in SKILLS.keys() if sk not in campaign_run.skills]
                    skill_cap = 3 + (1 if "combo_skill_slot" in campaign_run.combo.selected_cards else 0)
                    if len(campaign_run.skills) >= skill_cap:
                        msg = f"血肉祭坛：献祭了{UNIT_TYPES.get(selected_unit).name if UNIT_TYPES.get(selected_unit) else selected_unit}，但技能栏已满"
                    elif not available_skills:
                        msg = f"血肉祭坛：献祭了{UNIT_TYPES.get(selected_unit).name if UNIT_TYPES.get(selected_unit) else selected_unit}，但已学会所有技能"
                    else:
                        rng = campaign_run.fork_rng("event_skill_grant")
                        target_skill = rng.choice(available_skills)
                        campaign_run.skills.append(target_skill)
                        ut = UNIT_TYPES.get(selected_unit)
                        msg = f"血肉祭坛：献祭{ut.name if ut else selected_unit}，习得【{SKILLS[target_skill]['name']}】"
            
            elif action == "forge_to_3":
                # D3A: 指定兵种锻造升至3级
                victim = campaign_run.event_pending_target
                # 这里选择攻还是防，简化为随机或让玩家再选，这里我们简化为攻防都升到3
                campaign_run.forge.offense_level_by_unit[selected_unit] = 3
                campaign_run.forge.defense_level_by_unit[selected_unit] = 3
                ut_victim = UNIT_TYPES.get(victim)
                ut_target = UNIT_TYPES.get(selected_unit)
                msg = f"禁忌重铸：{ut_victim.name if ut_victim else victim}锻造归零，{ut_target.name if ut_target else selected_unit}攻防直升3级"
            
            elif action == "royal_summon_choice":
                # M1A: 皇家征召 2选1
                _set_unit_level(selected_unit, 1)
                ut = UNIT_TYPES.get(selected_unit)
                msg = f"皇家征召：解锁兵种【{ut.name if ut else selected_unit}】"
                if hasattr(campaign_run, "event_candidates"):
                    campaign_run.event_candidates = []
            
            # 清理状态
            campaign_run.event_pending_action = None
            campaign_run.event_pending_target = None
            return msg

        def _execute_event_skill_action(selected_skill: str) -> str:
            """执行事件中的待处理动作（选技能后）"""
            if not campaign_run:
                return ""
            
            action = campaign_run.event_pending_action
            msg = ""
            
            if action == "delete_skill_for_gold":
                # D3B: 删除技能获得300金
                if selected_skill in campaign_run.skills:
                    campaign_run.skills.remove(selected_skill)
                    campaign_run.state.gold += 300
                    msg = f"知识荒废：遗忘【{SKILLS[selected_skill]['name']}】，获得300金币"
            
            # 清理状态
            campaign_run.event_pending_action = None
            return msg

        def reset_campaign_run() -> None:
            nonlocal campaign_run
            campaign_run = None

        def handle_non_battle_node(node_id: int) -> None:
            nonlocal mode, campaign_run
            if not campaign_run or not campaign_run.state:
                return
            node = campaign_run.state.nodes.get(node_id)
            if not node or node.cleared:
                return
            if node.node_type == "shop":
                _shop_enter(node.node_id)
                return
            if node.node_type == "event":
                _event_enter(node.node_id)
                return
            if node.node_type == "rest":
                campaign_run.saved_left_base_hps = [float(BASE_MAX_HP) for _ in range(LANE_COUNT)]
                campaign_run.state.mark_node_cleared(node_id)
                _count_nonbattle_if_applicable(node_id)
                campaign_run.message = "休整：基地恢复至满血"
                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                _autosave_now()
                _maybe_enter_milestone_rewards()
                return
            # 其他非战斗节点：暂时直接清除
            campaign_run.state.mark_node_cleared(node_id)
            _count_nonbattle_if_applicable(node_id)
            campaign_run.message = "特殊节点：敬请期待"
            campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
            _autosave_now()
            _maybe_enter_milestone_rewards()

        def finalize_campaign_battle(success: bool, battle_time: float = 0.0) -> None:
            nonlocal mode, campaign_run, mirror_recording, mirror_recording_enabled
            if not campaign_run:
                mode = "menu"
                return
            if not campaign_run.state or campaign_run.current_node_id is None:
                mode = "campaign_map" if success else "menu"
                return
            node = campaign_run.state.nodes.get(campaign_run.current_node_id)
            reward_msg = ""
            node_type = node.node_type if node else ""
            
            # 记录战斗时间并给予时间奖励
            if success and node and node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
                recorded_time = max(0.0, battle_time)
                if recorded_time > 0:
                    campaign_run.battle_times.append(recorded_time)
                    campaign_run.total_time += recorded_time

                base_reward = campaign_run.state.battle_reward_amount()
                time_bonus = 0
                if recorded_time > 0:
                    for threshold, bonus in CAMPAIGN_TIME_REWARD_TIERS:
                        if recorded_time <= threshold:
                            time_bonus = bonus
                            break

                total_reward = base_reward + time_bonus
                # M4：Combo 可能影响战斗金币奖励
                mult = float(getattr(campaign_run, "battle_gold_mult", 1.0) or 1.0)
                total_reward = int(math.ceil(total_reward * max(0.0, mult)))
                
                campaign_run.state.gold += total_reward
                campaign_run.state.mark_battle_completed()
                # 里程碑：首次精英胜利标记（用于第3张 Combo）
                if node_type == "elite":
                    campaign_run.elite_victory_once = True

                time_detail = f"（用时 {_format_duration(recorded_time)}）" if recorded_time > 0 else ""
                if time_bonus > 0:
                    reward_msg = f"战斗奖励：获得 {base_reward} 金 + 时间奖励 {time_bonus} 金{time_detail}"
                else:
                    reward_msg = f"战斗奖励：获得 {base_reward} 金{time_detail}"
                
            # M2：不再直接回地图/旧奖励界面，而是进入固定结算链
            if node:
                campaign_run.state.mark_node_cleared(node.node_id)
            campaign_run.current_node_id = None
            campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
            campaign_run.postbattle_summary = reward_msg or ("战斗胜利！" if success else "战斗结束。")
            campaign_run.postbattle_node_type = node_type
            campaign_run.pending_finish_run = bool(node_type == "boss" and success)
            if success and node_type == "boss":
                if not bool(getattr(campaign_run, "timeout_win", False)):
                    campaign_run.mirror_snapshot = _build_mirror_snapshot()
                    campaign_run.mirror_script = list(mirror_recording or [])
                    campaign_run.mirror_last_updated = time.time()
                    save_mirror_profile(
                        campaign_run.mirror_snapshot,
                        campaign_run.mirror_script,
                        campaign_run.mirror_last_updated,
                    )
                    _autosave_now()
            mirror_recording_enabled = False
            mode = "campaign_postbattle_summary" if success else "menu"
            campaign_run.last_battle_time = 0.0

        def _clamp_reputation(rep: int) -> int:
            return max(REPUTATION_MIN, min(REPUTATION_MAX, int(rep)))
        
        def _max_unit_count() -> int:
            """获取本局最大兵种数量限制"""
            if not campaign_run:
                return 5
            if campaign_run.blessing_selected == "elite_simplicity":
                return 3
            return 5

        def _forge_substat_mult() -> float:
            # 祝福：后勤稳固 → 副属性-20%
            if campaign_run and campaign_run.blessing_selected == "logistics_stable":
                return 0.8
            return 1.0

        def _build_left_forge_payload() -> dict[str, tuple[int, int]]:
            """返回锻造数据：unit_key -> (攻击等级, 防御等级)"""
            if not campaign_run:
                return {}
            payload: dict[str, tuple[int, int]] = {}
            for uk in campaign_run.units:
                off_lvl = campaign_run.forge.offense_level_by_unit.get(uk, 0)
                def_lvl = campaign_run.forge.defense_level_by_unit.get(uk, 0)
                if off_lvl > 0 or def_lvl > 0:
                    payload[uk] = (int(off_lvl), int(def_lvl))
            return payload

        def _build_forge_payload_from_snapshot(snapshot: dict) -> dict[str, tuple[int, int]]:
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

        def _apply_combo_modifiers(combos: list[str], modifiers: dict, prefix: str = "", apply_cost_modifiers: bool = True) -> None:
            def k(name: str) -> str:
                return f"{prefix}{name}"
            # 基础职能加成 (combo 1-4)
            if "combo_heavy_armor" in combos:
                modifiers[k("combo_tank_hp_bonus")] = 0.25
            if "combo_sharpened_blades" in combos:
                modifiers[k("combo_dps_damage_bonus")] = 0.20
            if "combo_medical_kit" in combos:
                modifiers[k("combo_support_heal_bonus")] = 0.35
            if "combo_disruption" in combos:
                modifiers[k("combo_control_duration_bonus")] = 0.35
            # 基础特性加成 (combo 5-8)
            if "combo_heavy_payload" in combos:
                modifiers[k("combo_aoe_radius_bonus")] = 0.40
            if "combo_rapid_advance" in combos:
                modifiers[k("combo_melee_speed_bonus")] = 0.20
            if "combo_light_crossbow" in combos:
                modifiers[k("combo_ranged_atkspd_bonus")] = 0.15
            if "combo_far_sight" in combos:
                modifiers[k("combo_ranged_range_bonus")] = 0.15
            # 基础全局加成 (combo 9-12)
            if "combo_fortification" in combos:
                modifiers[k("combo_base_hp_bonus")] = 0.50
            # 联动型Combo标记 (在Game中处理)
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
                if "combo_logistics" in combos:
                    modifiers["left_cost_mult"] = float(modifiers.get("left_cost_mult", 1.0)) * 0.9
                if "combo_skill_optimization" in combos:
                    modifiers["left_skill_threshold_mult"] = 0.85

        def _apply_mirror_blessing_modifiers(snapshot: dict, modifiers: dict) -> None:
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
            elif blessing == "elite_simplicity":
                modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * 1.30
                modifiers["right_hp_mult"] = float(modifiers.get("right_hp_mult", 1.0)) * 1.30
                modifiers["right_unit_speed_mult"] = float(modifiers.get("right_unit_speed_mult", 1.0)) * 1.30
                modifiers["right_unit_atkspd_mult"] = float(modifiers.get("right_unit_atkspd_mult", 1.0)) * 1.30
            elif blessing == "steel_tide":
                modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * 0.75
                modifiers["right_hp_mult"] = float(modifiers.get("right_hp_mult", 1.0)) * 0.75
            elif blessing == "ring_of_destiny":
                if reputation > 0:
                    modifiers["right_unit_atkspd_mult"] = float(modifiers.get("right_unit_atkspd_mult", 1.0)) * (1.0 + reputation * 0.015)
                elif reputation < 0:
                    modifiers["right_damage_mult"] = float(modifiers.get("right_damage_mult", 1.0)) * (1.0 + abs(reputation) * 0.015)

        def _build_mirror_snapshot() -> dict:
            if not campaign_run:
                return {}
            return {
                "version": 1,
                "units": list(campaign_run.units or []),
                "unit_levels": dict(campaign_run.unit_levels or {}),
                "skills": list(campaign_run.skills or []),
                "boons": dict(campaign_run.boons or {}),
                "combo": list(campaign_run.combo.selected_cards or []),
                "blessing": campaign_run.blessing_selected,
                "forge_offense": dict(campaign_run.forge.offense_level_by_unit or {}),
                "forge_defense": dict(campaign_run.forge.defense_level_by_unit or {}),
                "primary_unit": str(getattr(campaign_run, "primary_unit", "") or ""),
                "reputation": int(getattr(campaign_run, "reputation", 0) or 0),
            }

        def _forge_default_target() -> tuple[str | None, str]:
            """返回(默认目标, 原因文案)"""
            if not campaign_run:
                return None, ""
            if not campaign_run.units:
                return None, "无可用兵种"
            
            # 过滤：默认情况下战士warrior不能锻造（除非选了不屈之志）
            forgeable = campaign_run.units
            if campaign_run.blessing_selected != "veteran_unyielding":
                forgeable = [k for k in forgeable if k != "warrior"]
            
            if not forgeable:
                return None, "无可锻造的兵种"
            
            counts = campaign_run.forge.spawn_count_by_unit
            min_count = min(counts.get(k, 0) for k in forgeable)
            ties = [k for k in forgeable if counts.get(k, 0) == min_count]
            if len(ties) == 1:
                return ties[0], f"因出兵次数最少（{min_count}）"
            # 平局：优先选"上一次锻造未选中的兵种"
            last = campaign_run.forge.last_target_unit
            if last in ties and len(ties) > 1:
                candidates = [k for k in ties if k != last]
            else:
                candidates = ties
            rng = campaign_run.fork_rng("forge_default_tie")
            pick = rng.choice(candidates)
            return pick, f"因出兵次数相同（最少={min_count}），随机挑选"

        def _forge_retarget_cost(is_retarget: bool, target_unit: str | None = None) -> int:
            """改锻费用：基于目标兵种的总锻造等级定价"""
            if not campaign_run or not is_retarget or not target_unit:
                return 0
            # 计算目标兵种的总锻造等级（攻+防）
            off_lvl = campaign_run.forge.offense_level_by_unit.get(target_unit, 0)
            def_lvl = campaign_run.forge.defense_level_by_unit.get(target_unit, 0)
            total_level = off_lvl + def_lvl
            
            # 基础费用 + 每个等级增加的费用
            base = FORGE_RETARGET_BASE_COST + (total_level * FORGE_RETARGET_PER_LEVEL_COST)
            
            # 祝福：军械拨款 → 费用更便宜（-30%）
            if campaign_run.blessing_selected == "arms_grant":
                base = int(math.ceil(base * 0.7))
            # Combo：锻造工会 → 改锻费用 -20%
            if "combo_forge_discount" in campaign_run.combo.selected_cards:
                base = int(math.ceil(base * 0.8))
            return base

        def _forge_next_success_chance(next_level: int, target_unit: str | None = None) -> float:
            # 基础：1级100%，2级50%，3级25%，4级25%（匠人精神），5级10%（匠人精神）
            if next_level <= 1:
                p = 1.0
            elif next_level == 2:
                p = 0.5
            elif next_level == 3:
                p = 0.25
            elif next_level == 4:
                p = FORGE_LEVEL_4_SUCCESS_RATE if campaign_run and campaign_run.blessing_selected == "craftsman_spirit" else 0.0
            elif next_level == 5:
                p = FORGE_LEVEL_5_SUCCESS_RATE if campaign_run and campaign_run.blessing_selected == "craftsman_spirit" else 0.0
            else:
                p = 0.0
            
            if not campaign_run:
                return p
            
            # 祝福：匠人精神 → 成功率100%
            if campaign_run.blessing_selected == "craftsman_spirit":
                p = 1.0
            
            return max(0.0, min(1.0, p))

        def _init_prisoners_for_battle() -> None:
            """进入俘虏界面前生成本关俘虏队列，避免 UI/输入错位。"""
            if not campaign_run or not campaign_run.state:
                    return
            
            # 匠人精神祝福：取消俘虏环节
            if campaign_run.blessing_selected == "craftsman_spirit":
                campaign_run.prisoner_queue = []
                campaign_run.prisoner_idx = 0
                campaign_run.prisoners_inited = True
                return
            
            campaign_run.prisoner_queue = []
            campaign_run.prisoner_idx = 0
            campaign_run.prisoner_action_idx = 0
            campaign_run.prisoner_message = ""

            # 优先：敌方实际出兵集合；fallback：本关 AI 池（用于"至少1个"的体验）
            raw = campaign_run.last_battle_enemy_types if campaign_run.last_battle_enemy_types else campaign_run.last_battle_ai_types
            T = [k for k in raw if k in ORDER_KEYS]
            Tset = list(dict.fromkeys(T))  # 去重保序
            
            # 过滤：默认情况下战士warrior不能通过俘虏升级（除非选了不屈之志）
            if campaign_run.blessing_selected != "veteran_unyielding":
                Tset = [k for k in Tset if k != "warrior"]
            
            # 过滤：已满级的兵种不出现在俘虏系统（避免浪费选择）
            # 只针对“已拥有且已满级”的情况；未解锁兵种不受影响（仍可作为新兵种俘获）
            Tset = [k for k in Tset if _current_unit_level(k) < MAX_UNIT_LEVEL]

            executed = campaign_run.prisoners.executed_once
            joined = campaign_run.prisoners.joined_once
            disable_join_weight = (campaign_run.blessing_selected == "discipline_cleanup")

            pool: list[tuple[str, float]] = []
            for uk in Tset:
                if executed.get(uk):
                    continue
                w = 1.0
                if joined.get(uk) and not disable_join_weight:
                    w *= 2.0
                pool.append((uk, w))

            # 下限：除非“全部都处决过”，否则至少生成1个；若 pool 为空则说明确实无可俘虏
            if not pool:
                campaign_run.prisoners_inited = True
                return

            t_len = len(pool)
            k_num = min(3, max(1, int(math.ceil(t_len / 3.0))))
            if campaign_run.blessing_selected == "discipline_cleanup":
                k_num = min(3, k_num + 1)

            rng = campaign_run.fork_rng("prisoners")
            # 祝福：战地募兵官 → 优先包含一个“未拥有且在敌方出现过”的兵种（若存在）
            if campaign_run.blessing_selected == "recruit_officer":
                unseen = [uk for uk, _ in pool if uk not in campaign_run.units]
                if unseen:
                    pick = rng.choice(unseen)
                    campaign_run.prisoner_queue.append(pick)
                    pool = [(uk, w) for uk, w in pool if uk != pick]

            while len(campaign_run.prisoner_queue) < k_num and pool:
                items = [uk for uk, _ in pool]
                weights = [w for _, w in pool]
                pick = rng.choices(items, weights=weights, k=1)[0]
                campaign_run.prisoner_queue.append(pick)
                pool = [(uk, w) for uk, w in pool if uk != pick]

            campaign_run.prisoners_inited = True

        def campaign_map_max_scroll() -> float:
            if not campaign_run or not campaign_run.state:
                return 0.0
            layer_count = len(campaign_run.state.layers)
            if layer_count <= 1:
                return 0.0
            visible_height = SCREEN_HEIGHT - (TOP_UI_HEIGHT + 80) - (BOTTOM_MARGIN + 160)
            total_height = (layer_count - 1) * MAP_LAYER_GAP
            return max(0.0, total_height - visible_height + 80)

        def _campaign_node_enemy_units(state: CampaignState, node_id: int) -> list[str]:
            if not state:
                return []
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
            rng = random.Random(seed)
            
            # 第0层禁止出现战士(warrior)、犀牛(rhino)、自爆车(exploder) - 避免开局过难
            available_keys = list(ORDER_KEYS)
            if node.layer_index == 0:
                available_keys = [k for k in ORDER_KEYS if k not in ("warrior", "rhino", "exploder")]
                ai_k = min(ai_k, len(available_keys))
            
            if ai_k >= len(available_keys):
                return list(available_keys)
            return rng.sample(available_keys, ai_k)

        def _enter_campaign_battle(node_id: int) -> None:
            """从地图/Combo回流进入战斗。"""
            nonlocal mode, game, mirror_recording, mirror_recording_enabled
            if not campaign_run or not campaign_run.state:
                return
            node = campaign_run.state.nodes.get(node_id)
            if not node or node.cleared:
                return
            if node.node_type not in CAMPAIGN_BATTLE_NODE_TYPES:
                return
            mirror_recording_enabled = bool(node.node_type == "boss")
            mirror_recording = []
            stage_idx = campaign_run.state.difficulty_index(node.node_type, total_campaign_stages)
            stage_idx = max(0, min(stage_idx, total_campaign_stages - 1))
            ai_pool = _campaign_node_enemy_units(campaign_run.state, node.node_id)
            if not ai_pool:
                ai_k = CAMPAIGN_PARAMS["ai_pool_sizes"][stage_idx]
                ai_k = max(1, min(ai_k, len(ORDER_KEYS)))
                ai_pool = random.sample(ORDER_KEYS, ai_k)
            interval = CAMPAIGN_PARAMS["ai_interval_mult"][stage_idx]
            mirror_snapshot: dict = {}
            mirror_script: list[dict] = []
            mirror_active = False
            mirror_ai_unit_levels: dict[str, int] | None = None
            mirror_right_forge: dict[str, tuple[int, int]] | None = None
            mirror_right_forge_substat_mult = 1.0
            campaign_run.timeout_win = False
            if node.node_type == "boss":
                mirror_snapshot = dict(getattr(campaign_run, "mirror_snapshot", {}) or {})
                mirror_script = list(getattr(campaign_run, "mirror_script", []) or [])
                if mirror_snapshot and mirror_script:
                    mirror_units = list(mirror_snapshot.get("units") or [])
                    if mirror_units:
                        ai_pool = mirror_units
                    mirror_ai_unit_levels = dict(mirror_snapshot.get("unit_levels") or {})
                    mirror_right_forge = _build_forge_payload_from_snapshot(mirror_snapshot)
                    if mirror_snapshot.get("blessing") == "logistics_stable":
                        mirror_right_forge_substat_mult = 0.8
                    mirror_active = True
            player_levels = {k: max(1, campaign_run.unit_levels.get(k, 1)) for k in campaign_run.units}
            enemy_damage_mult = 1.0
            enemy_hp_mult = 1.0
            current_day = max(1, campaign_run.state.day)
            day_damage_growth = (current_day - 1) * CAMPAIGN_ENEMY_DAMAGE_GROWTH
            day_hp_growth = (current_day - 1) * CAMPAIGN_ENEMY_HP_GROWTH
            enemy_damage_mult += day_damage_growth
            enemy_hp_mult += day_hp_growth
            if node.node_type == "elite":
                enemy_damage_mult += 0.15
            if mirror_active:
                enemy_damage_mult = 1.0
                enemy_hp_mult = 1.0
            
            # 应用超时惩罚系数
            penalty_coeff = getattr(campaign_run, "timeout_penalty_coeff", 1.0)
            if mirror_active:
                penalty_coeff = 1.0
            modifiers = {
                "right_damage_mult": enemy_damage_mult * penalty_coeff,
                "right_hp_mult": enemy_hp_mult * penalty_coeff,
                "right_base_hp_mult": enemy_hp_mult * penalty_coeff,
                "active_combos": list(campaign_run.combo.selected_cards),
                "active_blessing": campaign_run.blessing_selected,
            }

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
            
            # 祝福落地
            blessing = campaign_run.blessing_selected
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
                if current_day >= 5:
                    modifiers["veteran_sacrifice_day_limit"] = 5
                else:
                    modifiers["veteran_sacrifice_day_limit"] = 999
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
                # 宿命之环：名声联动（1点名声=1.5%数值）
                rep = int(getattr(campaign_run.state, "reputation", 0) or 0)
                if rep > 0:
                    # 圣人路线：攻速加成
                    modifiers["left_unit_atkspd_mult"] = float(modifiers.get("left_unit_atkspd_mult", 1.0)) * (1.0 + rep * 0.015)
                elif rep < 0:
                    # 暴君路线：伤害加成
                    modifiers["left_damage_mult"] = float(modifiers.get("left_damage_mult", 1.0)) * (1.0 + abs(rep) * 0.015)
            
            if mirror_active:
                modifiers["bases_to_win"] = LANE_COUNT
                modifiers["disable_ai"] = True
                modifiers["mirror_apply_right"] = True
                modifiers["right_damage_mult"] = 1.0
                modifiers["right_hp_mult"] = 1.0
                modifiers["right_base_hp_mult"] = 1.0
                modifiers["right_unit_speed_mult"] = 1.0
                modifiers["right_unit_atkspd_mult"] = 1.0
                _apply_mirror_blessing_modifiers(mirror_snapshot, modifiers)
                _apply_combo_modifiers(list(mirror_snapshot.get("combo") or []), modifiers, prefix="mirror_", apply_cost_modifiers=False)
            
            # 传递战役天数（用于英雄祭献的day>=5判定）
            modifiers["campaign_day"] = current_day
            
            # Combo 落地：基础加成通过modifiers传递给Game
            combos = campaign_run.combo.selected_cards
            _apply_combo_modifiers(list(combos or []), modifiers, prefix="", apply_cost_modifiers=True)

            game = Game(
                campaign_run.units,
                campaign_run.skills,
                ai_keys=ai_pool,
                ai_interval_mult=interval,
                boons={},  # M4：战役内移除 boon
                left_base_hps=campaign_run.saved_left_base_hps,
                modifiers=modifiers,
                player_unit_levels=player_levels,
                left_forge=_build_left_forge_payload(),
                left_forge_substat_mult=_forge_substat_mult(),
                ai_unit_levels=mirror_ai_unit_levels,
                right_forge=mirror_right_forge,
                right_forge_substat_mult=mirror_right_forge_substat_mult,
            )
            if mirror_active:
                game.set_mirror_script(mirror_script)
            
            # 祝福：掠夺者逻辑 - 设置本场战斗金币上限
            if campaign_run.blessing_selected == "looter_logic":
                from game.constants import CAMPAIGN_BASE_GOLD, CAMPAIGN_GOLD_INCREMENT
                base_gold = CAMPAIGN_BASE_GOLD + current_day * CAMPAIGN_GOLD_INCREMENT
                game.looter_battle_gold_cap = base_gold * 1.5
            
            campaign_run.saved_left_base_hps = None
            campaign_run.current_node_id = node.node_id
            campaign_run.message = ""
            campaign_run.last_battle_enemy_types = []
            campaign_run.last_battle_ai_types = list(ai_pool)
            mode = "campaign_battle"
        
        running = True
        while running:
            dt = clock.tick(FPS) / 1000.0

            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.VIDEORESIZE:
                    # 处理窗口大小改变
                    if not is_fullscreen:
                        window_width, window_height = event.w, event.h
                        screen = pg.display.set_mode((window_width, window_height), pg.RESIZABLE)
                
                elif event.type == pg.KEYDOWN:
                    # 全局全屏切换
                    if event.key == pg.K_F11:
                        is_fullscreen = not is_fullscreen
                        if is_fullscreen:
                            info = pg.display.Info()
                            window_width, window_height = info.current_w, info.current_h
                            screen = pg.display.set_mode((window_width, window_height), pg.FULLSCREEN)
                        else:
                            window_width, window_height = VIRTUAL_WIDTH, VIRTUAL_HEIGHT
                            screen = pg.display.set_mode((window_width, window_height), pg.RESIZABLE)
                    
                    if mode == "menu":
                        if event.key == pg.K_ESCAPE:
                            running = False
                        elif event.key == pg.K_1:
                            # 正常模式（原肉鸽）
                            _start_new_campaign()
                        elif event.key == pg.K_2:
                            # 进入百科
                            mode = "encyclopedia"
                            settings_return_mode = "menu" # 百科按ESC默认回上一级，这里简单处理回主菜单
                        elif event.key == pg.K_3:
                            # 自由模式
                            free_units = []
                            free_unit_levels = {}
                            free_boons = {}
                            free_skills = []
                            loadout_cursor = 0
                            loadout_focus = "units"
                            loadout_skill_idx = 0
                            mode = "free_loadout"
                        elif event.key == pg.K_4:
                            mode = "settings"
                            settings_cursor = 0
                            settings_return_mode = "menu"
                        elif event.key == pg.K_5:
                            # 继续游戏（自动档）
                            rs = load_autosave() if autosave_exists() else None
                            if rs and rs.state:
                                campaign_run = rs
                                if not campaign_run.mirror_snapshot or not campaign_run.mirror_script:
                                    profile = load_mirror_profile()
                                    campaign_run.mirror_snapshot = dict(profile.get("mirror_snapshot") or {})
                                    campaign_run.mirror_script = list(profile.get("mirror_script") or [])
                                    campaign_run.mirror_last_updated = float(
                                        profile.get("mirror_last_updated", 0.0) or 0.0
                                    )
                                mode = "campaign_map"
                    elif mode == "settings":
                        if event.key == pg.K_ESCAPE:
                            mode = settings_return_mode
                        elif event.key == pg.K_UP:
                            settings_cursor = (settings_cursor - 1) % 5
                        elif event.key == pg.K_DOWN:
                            settings_cursor = (settings_cursor + 1) % 5
                        elif event.key in (pg.K_LEFT, pg.K_RIGHT):
                            if settings_cursor == 0: # 分辨率
                                direction = -1 if event.key == pg.K_LEFT else 1
                                current_res_idx = (current_res_idx + direction) % len(resolutions)
                            elif settings_cursor == 1: # 全屏
                                is_fullscreen = not is_fullscreen
                            elif settings_cursor == 2: # BGM Volume
                                direction = -0.1 if event.key == pg.K_LEFT else 0.1
                                audio_manager.set_bgm_volume(audio_manager.bgm_volume + direction)
                            elif settings_cursor == 3: # SFX Volume
                                direction = -0.1 if event.key == pg.K_LEFT else 0.1
                                audio_manager.set_sfx_volume(audio_manager.sfx_volume + direction)
                            elif settings_cursor == 4:  # 语言
                                next_lang = "en" if get_lang() == "zh" else "zh"
                                set_lang(next_lang)
                                pg.display.set_caption(str(tr("几何大战 - 7 战线", "Geometry War - 7 Lanes")))
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            # 应用设置 (仅分辨率和全屏需要确认)
                            if settings_cursor == 0:
                                target_w, target_h = resolutions[current_res_idx]
                                if not is_fullscreen:
                                    window_width, window_height = target_w, target_h
                                    screen = pg.display.set_mode((window_width, window_height), pg.RESIZABLE)
                            elif settings_cursor == 1:
                                is_fullscreen = not is_fullscreen
                                if is_fullscreen:
                                    info = pg.display.Info()
                                    window_width, window_height = info.current_w, info.current_h
                                    screen = pg.display.set_mode((window_width, window_height), pg.FULLSCREEN)
                                else:
                                    target_w, target_h = resolutions[current_res_idx]
                                    window_width, window_height = target_w, target_h
                                    screen = pg.display.set_mode((window_width, window_height), pg.RESIZABLE)
                            elif settings_cursor == 4:
                                next_lang = "en" if get_lang() == "zh" else "zh"
                                set_lang(next_lang)
                                pg.display.set_caption(str(tr("几何大战 - 7 战线", "Geometry War - 7 Lanes")))
                    elif mode == "pause_menu":
                        if event.key == pg.K_ESCAPE:
                            mode = paused_from_mode
                        elif event.key == pg.K_UP:
                            pause_cursor = (pause_cursor - 1) % 4
                        elif event.key == pg.K_DOWN:
                            pause_cursor = (pause_cursor + 1) % 4
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if pause_cursor == 0: # 继续游戏
                                mode = paused_from_mode
                            elif pause_cursor == 1: # 回到主菜单
                                reset_campaign_run()
                                mode = "menu"
                            elif pause_cursor == 2: # 设置
                                mode = "settings"
                                settings_cursor = 0
                                settings_return_mode = "pause_menu"
                            elif pause_cursor == 3: # 百科
                                mode = "encyclopedia"
                                settings_return_mode = "pause_menu" # 借用变量
                    elif mode == "encyclopedia":
                        # Esc 返回主页
                        if event.key == pg.K_ESCAPE:
                            mode = settings_return_mode if settings_return_mode else "menu"
                            encyclopedia_scroll = 0
                        elif event.key == pg.K_UP:
                            encyclopedia_scroll = max(0, encyclopedia_scroll - 40)
                        elif event.key == pg.K_DOWN:
                            encyclopedia_scroll = encyclopedia_scroll + 40
                    elif mode == "game":
                        if event.key == pg.K_ESCAPE:
                            paused_from_mode = "game"
                            mode = "pause_menu"
                            pause_cursor = 0
                        # 切换倍速
                        elif event.key == pg.K_p:
                            if time_scale == 1.0: time_scale = 2.0
                            elif time_scale == 2.0: time_scale = 3.0
                            else: time_scale = 1.0
                        # 上下选择战线
                        elif event.key == pg.K_UP:
                            game.selected_lane = max(0, game.selected_lane - 1)
                        elif event.key == pg.K_DOWN:
                            game.selected_lane = min(len(game.lane_y) - 1, game.selected_lane + 1)
                        # 左右选择兵种
                        elif event.key == pg.K_LEFT:
                            game.selected_unit_idx = (game.selected_unit_idx - 1) % len(game.player_order_keys)
                        elif event.key == pg.K_RIGHT:
                            game.selected_unit_idx = (game.selected_unit_idx + 1) % len(game.player_order_keys)
                        # 空格出兵
                        elif event.key == pg.K_SPACE:
                            key = game.player_order_keys[game.selected_unit_idx]
                            game.spawn_unit("left", game.selected_lane, key)
                        # 技能
                        elif event.key == pg.K_q:
                            game.cast_skill("left", 0)
                        elif event.key == pg.K_w:
                            game.cast_skill("left", 1)
                        elif event.key == pg.K_e:
                            game.cast_skill("left", 2)
                    elif mode == "campaign_battle":
                        if event.key == pg.K_ESCAPE:
                            paused_from_mode = "campaign_battle"
                            mode = "pause_menu"
                            pause_cursor = 0
                        # 切换倍速
                        elif event.key == pg.K_p:
                            if time_scale == 1.0: time_scale = 2.0
                            elif time_scale == 2.0: time_scale = 3.0
                            else: time_scale = 1.0
                        elif event.key == pg.K_UP:
                            game.selected_lane = max(0, game.selected_lane - 1)
                        elif event.key == pg.K_DOWN:
                            game.selected_lane = min(len(game.lane_y) - 1, game.selected_lane + 1)
                        elif event.key == pg.K_LEFT:
                            game.selected_unit_idx = (game.selected_unit_idx - 1) % len(game.player_order_keys)
                        elif event.key == pg.K_RIGHT:
                            game.selected_unit_idx = (game.selected_unit_idx + 1) % len(game.player_order_keys)
                        elif event.key == pg.K_SPACE:
                            key = game.player_order_keys[game.selected_unit_idx]
                            if game.spawn_unit("left", game.selected_lane, key):
                                if mirror_recording_enabled:
                                    mirror_recording.append({
                                        "t": float(getattr(game, "battle_time", 0.0)),
                                        "type": "spawn",
                                        "lane": int(game.selected_lane),
                                        "unit": str(key),
                                    })
                        elif event.key == pg.K_q:
                            if game.cast_skill("left", 0):
                                if mirror_recording_enabled:
                                    skill_key, _ = game._get_skill_entry("left", 0)
                                    payload = {
                                        "t": float(getattr(game, "battle_time", 0.0)),
                                        "type": "skill",
                                        "lane": int(game.selected_lane),
                                        "skill": str(skill_key),
                                    }
                                    if skill_key == "spawn":
                                        payload["unit"] = str(game.player_order_keys[game.selected_unit_idx])
                                    mirror_recording.append(payload)
                        elif event.key == pg.K_w:
                            if game.cast_skill("left", 1):
                                if mirror_recording_enabled:
                                    skill_key, _ = game._get_skill_entry("left", 1)
                                    payload = {
                                        "t": float(getattr(game, "battle_time", 0.0)),
                                        "type": "skill",
                                        "lane": int(game.selected_lane),
                                        "skill": str(skill_key),
                                    }
                                    if skill_key == "spawn":
                                        payload["unit"] = str(game.player_order_keys[game.selected_unit_idx])
                                    mirror_recording.append(payload)
                        elif event.key == pg.K_e:
                            if game.cast_skill("left", 2):
                                if mirror_recording_enabled:
                                    skill_key, _ = game._get_skill_entry("left", 2)
                                    payload = {
                                        "t": float(getattr(game, "battle_time", 0.0)),
                                        "type": "skill",
                                        "lane": int(game.selected_lane),
                                        "skill": str(skill_key),
                                    }
                                    if skill_key == "spawn":
                                        payload["unit"] = str(game.player_order_keys[game.selected_unit_idx])
                                    mirror_recording.append(payload)
                    elif mode == "campaign_shop":
                        if not campaign_run or not campaign_run.state:
                            mode = "menu"
                            continue
                        total_slots = len(campaign_run.shop_items) if campaign_run.shop_items else 0
                        # 抢劫弹框确认模式：打开弹框后只接受“确认/取消”，屏蔽其他商店操作
                        if getattr(campaign_run, "shop_robbery_confirm", False):
                            if event.key in (pg.K_ESCAPE, pg.K_x, pg.K_BACKSPACE):
                                campaign_run.shop_robbery_confirm = False
                                campaign_run.shop_message = "已取消抢劫"
                            elif event.key in (pg.K_RETURN, pg.K_SPACE):
                                # 确认抢劫：立刻结束本次商店
                                campaign_run.shop_robbery_confirm = False
                                campaign_run.state.gold += SHOP_ROB_GOLD_GAIN
                                campaign_run.reputation = _clamp_reputation(campaign_run.reputation - SHOP_ROB_REP_LOSS)
                                campaign_run.oneshot.next_shop_free_refresh_disabled = True
                                prev_n = int(getattr(campaign_run, "shop_robbery_count", 0) or 0)
                                campaign_run.shop_robbery_count = prev_n + 1
                                n_eff = min(int(getattr(campaign_run, "shop_robbery_count", 0) or 0), 4)
                                delta_eff = 1 if prev_n < 4 else 0
                                campaign_run.shop_message = (
                                    f"抢劫成功：+{SHOP_ROB_GOLD_GAIN}金，声望-{SHOP_ROB_REP_LOSS}；"
                                    f"以后商店货物选项减少{delta_eff}（累计：{n_eff}，上限4；随机封锁{n_eff}格）；"
                                    f"下次商店无免费刷新"
                                )
                                if campaign_run.shop_node_id is not None:
                                    campaign_run.state.mark_node_cleared(campaign_run.shop_node_id)
                                    _count_nonbattle_if_applicable(campaign_run.shop_node_id)
                                    campaign_run.shop_node_id = None
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                campaign_run.message = campaign_run.shop_message
                                campaign_run.shop_items = []
                                _autosave_now()
                                if not _maybe_enter_milestone_rewards():
                                    mode = "campaign_map"
                            # 已处理弹框按键，不继续走普通商店按键链路
                            continue

                        if event.key == pg.K_ESCAPE:
                            if campaign_run.shop_node_id is not None:
                                campaign_run.state.mark_node_cleared(campaign_run.shop_node_id)
                                _count_nonbattle_if_applicable(campaign_run.shop_node_id)
                                campaign_run.shop_node_id = None
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                campaign_run.message = campaign_run.shop_message or "离开商店"
                            campaign_run.shop_items = []
                            campaign_run.shop_message = ""
                            _autosave_now()
                            if not _maybe_enter_milestone_rewards():
                                mode = "campaign_map"
                        elif event.key == pg.K_LEFT and total_slots:
                            campaign_run.shop_cursor = (campaign_run.shop_cursor - 1) % total_slots
                        elif event.key == pg.K_RIGHT and total_slots:
                            campaign_run.shop_cursor = (campaign_run.shop_cursor + 1) % total_slots
                        elif event.key == pg.K_UP and total_slots:
                            campaign_run.shop_cursor = (campaign_run.shop_cursor - 2) % total_slots
                        elif event.key == pg.K_DOWN and total_slots:
                            campaign_run.shop_cursor = (campaign_run.shop_cursor + 2) % total_slots
                        elif event.key == pg.K_d:
                            # 捐赠：每次进店最多1次
                            if campaign_run.shop_donated:
                                campaign_run.shop_message = "本次已捐赠过"
                            elif campaign_run.state.gold < SHOP_DONATE_GOLD_COST:
                                campaign_run.shop_message = f"金币不足，需要 {SHOP_DONATE_GOLD_COST} 金"
                            else:
                                campaign_run.state.gold -= SHOP_DONATE_GOLD_COST
                                campaign_run.reputation = _clamp_reputation(campaign_run.reputation + SHOP_DONATE_REP_GAIN)
                                campaign_run.shop_donated = True
                                campaign_run.shop_message = f"捐赠成功：-{SHOP_DONATE_GOLD_COST}金，声望+{SHOP_DONATE_REP_GAIN}"
                        elif event.key == pg.K_x:
                            # 抢劫：弹框确认（Enter确认/Esc取消）
                            prev_n = int(getattr(campaign_run, "shop_robbery_count", 0) or 0)
                            next_eff = min(prev_n + 1, 4)
                            delta_eff = 1 if prev_n < 4 else 0
                            campaign_run.shop_robbery_confirm = True
                            campaign_run.shop_message = (
                                f"确认抢劫：+{SHOP_ROB_GOLD_GAIN}金，声望-{SHOP_ROB_REP_LOSS}；"
                                f"以后商店货物选项减少{delta_eff}（累计：{next_eff}，上限4；随机封锁{next_eff}格）；"
                                f"下次商店无免费刷新"
                            )
                        elif event.key in (pg.K_RETURN, pg.K_SPACE) and total_slots:
                            entry = campaign_run.shop_items[campaign_run.shop_cursor]
                            if not entry:
                                campaign_run.shop_message = "该位置暂无商品"
                            elif entry.get("locked"):
                                campaign_run.shop_message = "该位置已被封锁（因抢劫惩罚）"
                            elif entry.get("type") == "empty":
                                campaign_run.shop_message = "该位置暂无商品"
                            elif entry.get("sold"):
                                campaign_run.shop_message = "该商品已售出"
                            else:
                                price = int(entry.get("price", 0) or 0)
                                if campaign_run.state.gold < price:
                                    campaign_run.shop_message = f"金币不足，需要 {price} 金"
                                else:
                                    itype = entry.get("type")
                                    payload = entry.get("payload")
                                    if itype in ("unit", "skill"):
                                        ok, msg = apply_campaign_purchase(str(payload))
                                        if ok:
                                            campaign_run.state.gold -= price
                                            entry["sold"] = True
                                            campaign_run.shop_message = f"{msg}（- {price} 金，剩余 {campaign_run.state.gold}）"
                                        else:
                                            campaign_run.shop_message = msg
                                    elif itype == "forge_device":
                                        campaign_run.state.gold -= price
                                        entry["sold"] = True
                                        # 商店锻造：结束后回到商店
                                        d, reason = _forge_default_target()
                                        campaign_run.forge_default_unit = d
                                        campaign_run.forge_default_reason = reason
                                        campaign_run.forge_selected_unit = d
                                        campaign_run.forge_done = False
                                        campaign_run.forge_result_message = ""
                                        campaign_run.forge_return_mode = "campaign_shop"
                                        campaign_run.forge_force_free_retarget = False
                                        mode = "campaign_forge"
                                    else:
                                        campaign_run.shop_message = "未知商品"
                        elif event.key == pg.K_r:
                            if campaign_run.shop_free_refresh_left > 0:
                                campaign_run.shop_free_refresh_left -= 1
                                campaign_run.shop_items = _roll_shop_items(float(getattr(campaign_run, "shop_price_mult_current", 1.0) or 1.0))
                                # 光标尽量落在可用格子上
                                campaign_run.shop_cursor = 0
                                for i, it in enumerate(list(campaign_run.shop_items or [])[:4]):
                                    if isinstance(it, dict) and it.get("locked"):
                                        continue
                                    campaign_run.shop_cursor = int(i)
                                    break
                                campaign_run.shop_message = f"已刷新（免费剩余 {campaign_run.shop_free_refresh_left} 次）"
                            else:
                                n = campaign_run.shop_refresh_paid_count + 1
                                cost = SHOP_REFRESH_BASE_COST * n
                                # 祝福：定向投资 → 刷新费+20%
                                if campaign_run.blessing_selected == "direct_invest":
                                    cost = int(math.ceil(cost * 1.2))
                                if campaign_run.state.gold < cost:
                                    campaign_run.shop_message = f"金币不足，刷新需 {cost} 金"
                                else:
                                    campaign_run.state.gold -= cost
                                    campaign_run.shop_refresh_paid_count += 1
                                    campaign_run.shop_message = f"已刷新（- {cost} 金，剩余 {campaign_run.state.gold}）"
                                    
                                    campaign_run.shop_items = _roll_shop_items(float(getattr(campaign_run, "shop_price_mult_current", 1.0) or 1.0))
                                    # 光标尽量落在可用格子上
                                    campaign_run.shop_cursor = 0
                                    for i, it in enumerate(list(campaign_run.shop_items or [])[:4]):
                                        if isinstance(it, dict) and it.get("locked"):
                                            continue
                                        campaign_run.shop_cursor = int(i)
                                        break
                    elif mode == "campaign_map":
                        # 进入地图/读档后：若已达成里程碑但尚未选择，则在任意非退出按键时补弹窗
                        if event.key != pg.K_ESCAPE:
                            if _maybe_enter_milestone_rewards():
                                continue
                        if event.key == pg.K_ESCAPE:
                            reset_campaign_run()
                            mode = "menu"
                        elif event.key in (pg.K_LEFT, pg.K_UP):
                            if campaign_run and campaign_run.state:
                                campaign_run.cursor_node_id = campaign_run.state.move_cursor(-1)
                        elif event.key in (pg.K_RIGHT, pg.K_DOWN):
                            if campaign_run and campaign_run.state:
                                campaign_run.cursor_node_id = campaign_run.state.move_cursor(1)
                        elif event.key == pg.K_PAGEUP:
                            max_scroll = campaign_map_max_scroll()
                            if campaign_run:
                                campaign_run.map_scroll = max(0.0, campaign_run.map_scroll - 100.0)
                        elif event.key == pg.K_PAGEDOWN:
                            max_scroll = campaign_map_max_scroll()
                            if campaign_run:
                                campaign_run.map_scroll = min(max_scroll, campaign_run.map_scroll + 100.0)
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if campaign_run and campaign_run.state and campaign_run.cursor_node_id is not None:
                                node = campaign_run.state.nodes.get(campaign_run.cursor_node_id)
                                available = campaign_run.state.available_nodes()
                                if not node or campaign_run.cursor_node_id not in available:
                                    continue
                                moved = campaign_run.state.move_to_node(node.node_id)
                                campaign_run.cursor_node_id = campaign_run.state.cursor_node_id or node.node_id
                                node_display = CAMPAIGN_NODE_DISPLAY.get(node.node_type, node.node_type)
                                # 如果节点已被清除，仅更新光标与提示
                                if node.cleared:
                                    if moved:
                                        campaign_run.message = f"已移动至已通关的{node_display}节点"
                                    else:
                                        campaign_run.message = f"已停留在已通关的{node_display}节点"
                                    continue
                                if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
                                    _enter_campaign_battle(node.node_id)
                                else:
                                    handle_non_battle_node(node.node_id)
                                    if campaign_run and campaign_run.state:
                                        campaign_run.cursor_node_id = campaign_run.state.cursor_node_id
                    elif mode == "campaign_victory":
                        if event.key == pg.K_ESCAPE:
                            delete_autosave()
                            reset_campaign_run()
                            mode = "menu"
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            _start_new_campaign()
                    elif mode == "campaign_defeat":
                        if event.key == pg.K_ESCAPE:
                            delete_autosave()
                            reset_campaign_run()
                            mode = "menu"
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            _start_new_campaign()
                    elif mode == "free_loadout":
                        cols = 6
                        total = len(ORDER_KEYS)
                        rows = (total - 1) // cols + 1
                        if event.key == pg.K_ESCAPE:
                            mode = "menu"
                        elif event.key == pg.K_TAB:
                            loadout_focus = "skill" if loadout_focus == "units" else "units"
                        elif event.key == pg.K_UP:
                            if loadout_focus == "units":
                                loadout_cursor = max(0, loadout_cursor - cols)
                        elif event.key == pg.K_DOWN:
                            if loadout_focus == "units":
                                loadout_cursor = min(total - 1, loadout_cursor + cols)
                        elif event.key == pg.K_LEFT:
                            if loadout_focus == "units":
                                loadout_cursor = (loadout_cursor - 1 + total) % total
                            else:
                                if SKILL_ORDER:
                                    loadout_skill_idx = (loadout_skill_idx - 1) % len(SKILL_ORDER)
                        elif event.key == pg.K_RIGHT:
                            if loadout_focus == "units":
                                loadout_cursor = (loadout_cursor + 1) % total
                            else:
                                if SKILL_ORDER:
                                    loadout_skill_idx = (loadout_skill_idx + 1) % len(SKILL_ORDER)
                        elif event.key == pg.K_SPACE:
                            if loadout_focus == "units":
                                k = ORDER_KEYS[loadout_cursor]
                                current_level = free_unit_levels.get(k, 0)
                                if current_level == 0:
                                    free_units = free_units + [k]
                                    free_unit_levels[k] = 1
                                elif current_level < MAX_UNIT_LEVEL:
                                    free_unit_levels[k] = current_level + 1
                                else:
                                    free_units = [x for x in free_units if x != k]
                                    free_unit_levels.pop(k, None)
                            else:
                                if SKILL_ORDER:
                                    skill_key = SKILL_ORDER[loadout_skill_idx]
                                    if skill_key in free_skills:
                                        free_skills = [s for s in free_skills if s != skill_key]
                                    elif len(free_skills) < 3:
                                        free_skills = free_skills + [skill_key]
                        elif event.key == pg.K_RETURN:
                            # 进入增益选择
                            boon_cursor = 0
                            mode = "free_boons"
                    elif mode == "free_boons":
                        keys = list(BOONS.keys())
                        if event.key == pg.K_ESCAPE:
                            mode = "free_loadout"
                        elif event.key == pg.K_UP:
                            boon_cursor = max(0, boon_cursor - 1)
                        elif event.key == pg.K_DOWN:
                            boon_cursor = min(len(keys) - 1, boon_cursor + 1)
                        elif event.key == pg.K_LEFT:
                            bid = keys[boon_cursor]
                            cur = free_boons.get(bid, 0)
                            if cur > 0:
                                free_boons[bid] = cur - 1
                                if free_boons[bid] == 0:
                                    free_boons.pop(bid)
                        elif event.key == pg.K_RIGHT or event.key == pg.K_SPACE:
                            bid = keys[boon_cursor]
                            cur = free_boons.get(bid, 0)
                            mx = BOONS[bid]["max"]
                            if cur < mx:
                                free_boons[bid] = cur + 1
                        elif event.key == pg.K_RETURN:
                            # 开局：AI 使用全兵种，玩家资源回复倍率 100x
                            ai_pool = list(ORDER_KEYS)
                            modifiers = {
                                "left_resource_rate_mult": 100.0,
                                "left_res_cap": MAX_RESOURCE * 100,
                                "left_infinite_skill": True,
                                "bases_invulnerable": True,
                                "right_resource_mult": 3.0,
                                "right_start_resource_mult": 3.0,
                                "right_res_cap": MAX_RESOURCE * 3,
                                "ai_extra_spawn": 2,
                                "ai_varied_units": True,
                            }
                            player_keys = free_units if free_units else ORDER_KEYS[:5]
                            player_levels = {k: max(1, free_unit_levels.get(k, 1)) for k in player_keys}
                            game = Game(
                                player_keys,
                                free_skills if free_skills else ([default_skill] if default_skill else []),
                                ai_keys=ai_pool,
                                ai_interval_mult=1.0,
                                boons=free_boons,
                                modifiers=modifiers,
                                player_unit_levels=player_levels,
                            )
                            mode = "free_battle"
                    elif mode == "free_battle":
                        if event.key == pg.K_ESCAPE:
                            paused_from_mode = "free_battle"
                            mode = "pause_menu"
                            pause_cursor = 0
                        # 切换倍速
                        elif event.key == pg.K_p:
                            if time_scale == 1.0: time_scale = 2.0
                            elif time_scale == 2.0: time_scale = 3.0
                            else: time_scale = 1.0
                        elif event.key == pg.K_UP:
                            game.selected_lane = max(0, game.selected_lane - 1)
                        elif event.key == pg.K_DOWN:
                            game.selected_lane = min(len(game.lane_y) - 1, game.selected_lane + 1)
                        elif event.key == pg.K_LEFT:
                            game.selected_unit_idx = (game.selected_unit_idx - 1) % len(game.player_order_keys)
                        elif event.key == pg.K_RIGHT:
                            game.selected_unit_idx = (game.selected_unit_idx + 1) % len(game.player_order_keys)
                        elif event.key == pg.K_SPACE:
                            key = game.player_order_keys[game.selected_unit_idx]
                            game.spawn_unit("left", game.selected_lane, key)
                        elif event.key == pg.K_q:
                            game.cast_skill("left", 0)
                        elif event.key == pg.K_w:
                            game.cast_skill("left", 1)
                        elif event.key == pg.K_e:
                            game.cast_skill("left", 2)
                    elif mode == "campaign_loadout":
                        # M4：战役配装仅选 1 个兵种；不选技能（技能仅商店购买）
                        cols = 6
                        total = len(ORDER_KEYS)
                        if event.key == pg.K_ESCAPE:
                            mode = "menu"
                        elif event.key == pg.K_UP:
                            loadout_cursor = max(0, loadout_cursor - cols)
                        elif event.key == pg.K_DOWN:
                            loadout_cursor = min(total - 1, loadout_cursor + cols)
                        elif event.key == pg.K_LEFT:
                            loadout_cursor = (loadout_cursor - 1 + total) % total
                        elif event.key == pg.K_RIGHT:
                            loadout_cursor = (loadout_cursor + 1) % total
                        elif event.key == pg.K_SPACE:
                            k = ORDER_KEYS[loadout_cursor]
                            if campaign_run:
                                if k in campaign_run.units:
                                    _set_unit_level(k, 0)
                                else:
                                    # 只允许选 1 个：先清空再选中
                                    for existing in list(campaign_run.units):
                                        _set_unit_level(existing, 0)
                                    _set_unit_level(k, 1)
                        elif event.key == pg.K_RETURN:
                            if campaign_run and len(campaign_run.units) >= 1:
                                # 记录开局第1槽（弱势开局补偿/统计等使用）
                                if not getattr(campaign_run, "primary_unit", ""):
                                    try:
                                        campaign_run.primary_unit = str(campaign_run.units[0])
                                    except Exception:
                                        campaign_run.primary_unit = ""
                                # 地图生成使用可复现 RNG：便于 seed 回归测试与复盘
                                rng = campaign_run.fork_rng("map") if campaign_run else random.Random()
                                campaign_run.state = generate_campaign_map(rng)
                                campaign_run.state.gold = 0
                                campaign_run.state.battle_count = 0
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                campaign_run.current_node_id = None
                                
                                # 弱兵种开局补偿：第一场战斗前给予Combo卡
                                weak_start_units = {"maul", "rhino", "assassin", "light_cavalry", "exploder"}  # 大锤、犀牛、刺客、轻骑、自爆车
                                primary = str(getattr(campaign_run, "primary_unit", "") or "")
                                if primary in weak_start_units:
                                    # 标记：弱兵种开局已提前获得Combo1
                                    campaign_run.weak_start_combo_given = True
                                    campaign_run.milestone_battle3_claimed = True  # 同步标记里程碑已发放
                                    # 进入Combo选择界面（用户交互选择）
                                    _combo_enter("weak_start", pending_node_id=None)
                                    # 注意：这里会直接进入 combo_select 模式，用户选择后才会继续
                                else:
                                    campaign_run.weak_start_combo_given = False
                                    campaign_run.milestone_battle3_claimed = False
                                campaign_run.message = ""
                                campaign_run.saved_left_base_hps = None
                                # 进入地图时默认定位到底部，便于自下而上推进
                                campaign_run.map_scroll = campaign_map_max_scroll()
                                _autosave_now()
                                mode = "campaign_map"
                    elif mode == "campaign_reward":
                        # M2 起：不再从战斗胜利进入此界面，保留为旧兼容/调试入口
                        if event.key in (pg.K_ESCAPE, pg.K_RETURN, pg.K_SPACE):
                            mode = "campaign_map"
                    elif mode == "campaign_event":
                        if event.key in (pg.K_ESCAPE, pg.K_RETURN, pg.K_SPACE):
                            # 返回地图，保留事件提示为地图底部消息
                            if campaign_run and campaign_run.state:
                                campaign_run.message = campaign_run.event_message or campaign_run.message
                                campaign_run.event_message = ""
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                available = campaign_run.state.available_nodes()
                                if not campaign_run.state.battle_nodes_remaining() and not available:
                                    campaign_run.message = campaign_run.message or "恭喜通关！按 Esc 返回主菜单"
                            _autosave_now()
                            mode = "campaign_map"
                    elif mode == "campaign_event_choice":
                        if not campaign_run or not campaign_run.state:
                            mode = "menu"
                            continue
                        if event.key == pg.K_LEFT:
                            campaign_run.event_choice_idx = 0
                        elif event.key == pg.K_RIGHT:
                            campaign_run.event_choice_idx = 1
                        elif event.key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
                            old_tid = campaign_run.event_template_id
                            msg = _apply_event_choice(campaign_run.event_choice_idx)
                            # 如果mode已经被_apply_event_choice改变（如跳转到选兵界面），则不继续处理
                            if mode != "campaign_event_choice":
                                continue
                            
                            # 判定是否为原地刷新（如 D2 放下屠刀）
                            if old_tid == "D2" and campaign_run.event_template_id != "D2":
                                continue

                            if campaign_run.event_node_id is not None:
                                campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                campaign_run.event_node_id = None
                            campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                            campaign_run.message = msg
                            _autosave_now()
                            if not _maybe_enter_milestone_rewards():
                                mode = "campaign_map"
                    elif mode == "campaign_event_unit_select":
                        # 处理事件中的选兵逻辑
                        if not campaign_run or not campaign_run.units:
                            mode = "campaign_map"
                            continue
                        if event.key == pg.K_ESCAPE:
                            # 取消选择，返回地图
                            campaign_run.event_pending_action = None
                            campaign_run.event_pending_target = None
                            if campaign_run.event_node_id is not None:
                                campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                campaign_run.event_node_id = None
                            mode = "campaign_map"
                        elif event.key in [pg.K_1, pg.K_2, pg.K_3, pg.K_4, pg.K_5]:
                            idx = event.key - pg.K_1
                            candidates = getattr(campaign_run, "event_candidates", [])
                            if candidates:
                                if idx < len(candidates):
                                    selected_unit = candidates[idx]
                                    msg = _execute_event_pending_action(selected_unit)
                                    if campaign_run.event_node_id is not None:
                                        campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                        _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                        campaign_run.event_node_id = None
                                    campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                    campaign_run.message = msg
                                    _autosave_now()
                                    if not _maybe_enter_milestone_rewards():
                                        mode = "campaign_map"
                            elif idx < len(campaign_run.units):
                                selected_unit = campaign_run.units[idx]
                                msg = _execute_event_pending_action(selected_unit)
                                if campaign_run.event_node_id is not None:
                                    campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                    _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                    campaign_run.event_node_id = None
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                campaign_run.message = msg
                                _autosave_now()
                                if not _maybe_enter_milestone_rewards():
                                    mode = "campaign_map"
                    elif mode == "campaign_event_skill_select":
                        # 处理事件中的选技能逻辑
                        if not campaign_run or not campaign_run.skills:
                            mode = "campaign_map"
                            continue
                        if event.key == pg.K_ESCAPE:
                            campaign_run.event_pending_action = None
                            if campaign_run.event_node_id is not None:
                                campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                campaign_run.event_node_id = None
                            mode = "campaign_map"
                        elif event.key in [pg.K_1, pg.K_2, pg.K_3, pg.K_4]:
                            idx = event.key - pg.K_1
                            if idx < len(campaign_run.skills):
                                selected_skill = campaign_run.skills[idx]
                                msg = _execute_event_skill_action(selected_skill)
                                if campaign_run.event_node_id is not None:
                                    campaign_run.state.mark_node_cleared(campaign_run.event_node_id)
                                    _count_nonbattle_if_applicable(campaign_run.event_node_id)
                                    campaign_run.event_node_id = None
                                campaign_run.cursor_node_id = campaign_run.state.ensure_cursor()
                                campaign_run.message = msg
                                _autosave_now()
                                if not _maybe_enter_milestone_rewards():
                                    mode = "campaign_map"
                    elif mode == "campaign_postbattle_summary":
                        if event.key in (pg.K_ESCAPE, pg.K_RETURN, pg.K_SPACE):
                            # 进入锻造前固定默认目标（避免 UI 显示与执行时随机不一致）
                            if campaign_run:
                                d, reason = _forge_default_target()
                                campaign_run.forge_default_unit = d
                                campaign_run.forge_default_reason = reason
                                campaign_run.forge_selected_unit = d
                            mode = "campaign_forge"
                    elif mode == "campaign_forge":
                        if not campaign_run or not campaign_run.state:
                            mode = "menu"
                            continue
                        # 初始化默认选择
                        default_unit = campaign_run.forge_default_unit
                        if event.key == pg.K_TAB:
                            campaign_run.forge_selected_dir = "defense" if campaign_run.forge_selected_dir == "offense" else "offense"
                        elif event.key in (pg.K_UP, pg.K_w):
                            campaign_run.forge_selected_dir = "offense"
                        elif event.key in (pg.K_DOWN, pg.K_s):
                            campaign_run.forge_selected_dir = "defense"
                        elif event.key in (pg.K_LEFT, pg.K_a):
                            if campaign_run.units:
                                idx = campaign_run.units.index(campaign_run.forge_selected_unit) if campaign_run.forge_selected_unit in campaign_run.units else 0
                                idx = (idx - 1) % len(campaign_run.units)
                                campaign_run.forge_selected_unit = campaign_run.units[idx]
                        elif event.key in (pg.K_RIGHT, pg.K_d):
                            if campaign_run.units:
                                idx = campaign_run.units.index(campaign_run.forge_selected_unit) if campaign_run.forge_selected_unit in campaign_run.units else 0
                                idx = (idx + 1) % len(campaign_run.units)
                                campaign_run.forge_selected_unit = campaign_run.units[idx]
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if campaign_run.forge_done:
                                # 购买锻造器：锻造结束后回到商店
                                if campaign_run.forge_return_mode == "campaign_shop":
                                    campaign_run.forge_return_mode = "campaign_prisoners"
                                    mode = "campaign_shop"
                                else:
                                    _init_prisoners_for_battle()
                                    mode = "campaign_prisoners"
                                continue
                            target = campaign_run.forge_selected_unit or default_unit
                            if not target:
                                campaign_run.forge_result_message = "没有可锻造的兵种"
                                campaign_run.forge_done = True
                                continue
                            # 默认目标免费；改锻需付费
                            is_retarget = (default_unit is not None) and (target != default_unit)
                            cost = _forge_retarget_cost(is_retarget, target)
                            if is_retarget:
                                if campaign_run.forge_force_free_retarget:
                                    cost = 0
                                if campaign_run.state.gold < cost:
                                    campaign_run.forge_result_message = f"金币不足，改锻需 {cost} 金"
                                    continue
                                campaign_run.state.gold -= cost
                            
                            # 判断战士锻造权限
                            if target == "warrior" and campaign_run.blessing_selected != "veteran_unyielding":
                                campaign_run.forge_result_message = "战士无法锻造（需要【不屈之志】祝福）"
                                campaign_run.forge_done = True
                                continue
                            
                            # 获取当前选择的方向和该方向的等级
                            chosen_dir = campaign_run.forge_selected_dir
                            if chosen_dir == "offense":
                                cur_lvl = int(campaign_run.forge.offense_level_by_unit.get(target, 0))
                            else:
                                cur_lvl = int(campaign_run.forge.defense_level_by_unit.get(target, 0))
                            
                            max_forge_level = 5 if campaign_run.blessing_selected == "craftsman_spirit" else 3
                            if cur_lvl >= max_forge_level:
                                campaign_run.forge_result_message = f"{chosen_dir}锻造已满级（{max_forge_level}级）"
                                campaign_run.forge.last_target_unit = target
                                campaign_run.forge.last_direction = chosen_dir
                                campaign_run.forge_done = True
                                continue
                            
                            next_lvl = cur_lvl + 1
                            p = _forge_next_success_chance(next_lvl, target)
                            rng = campaign_run.fork_rng(f"forge:{target}:{chosen_dir}:{next_lvl}")
                            ok = rng.random() < p
                            if ok:
                                if chosen_dir == "offense":
                                    campaign_run.forge.offense_level_by_unit[target] = next_lvl
                                else:
                                    campaign_run.forge.defense_level_by_unit[target] = next_lvl
                                campaign_run.forge_result_message = f"锻造成功：{target} → {chosen_dir} {next_lvl}级"
                            else:
                                campaign_run.forge_result_message = f"锻造失败：仍保持 {chosen_dir} {cur_lvl}级（不降级）"
                            campaign_run.forge.last_target_unit = target
                            campaign_run.forge.last_direction = chosen_dir
                            campaign_run.forge_done = True
                    elif mode == "campaign_prisoners":
                        if not campaign_run or not campaign_run.state:
                            mode = "menu"
                            continue
                        if not campaign_run.prisoners_inited:
                            _init_prisoners_for_battle()

                        # 俘虏处理输入
                        if event.key == pg.K_LEFT:
                            campaign_run.prisoner_action_idx = (campaign_run.prisoner_action_idx - 1) % 3
                        elif event.key == pg.K_RIGHT:
                            campaign_run.prisoner_action_idx = (campaign_run.prisoner_action_idx + 1) % 3
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if campaign_run.prisoner_idx >= len(campaign_run.prisoner_queue):
                                # 全部处理完：先检查里程碑奖励（祝福/Combo），否则回地图/通关
                                if _maybe_enter_milestone_rewards():
                                    continue
                                campaign_run.message = campaign_run.postbattle_summary or campaign_run.message
                                if campaign_run.pending_finish_run:
                                    mode = "campaign_victory"
                                else:
                                    _autosave_now()
                                    mode = "campaign_map"
                                continue

                            uk = campaign_run.prisoner_queue[campaign_run.prisoner_idx]
                            action = campaign_run.prisoner_action_idx  # 0归顺/1处决/2放归

                            if action == 0:
                                # 归顺：获取/升级兵种
                                if uk not in campaign_run.units:
                                    if len(campaign_run.units) >= _max_unit_count():
                                        # 达到上限：给补偿金币（避免白选）
                                        campaign_run.state.gold += PRISONER_RELEASE_GOLD
                                        campaign_run.prisoner_message = f"已达兵种上限，改为补偿 {PRISONER_RELEASE_GOLD} 金"
                                    else:
                                        campaign_run.units.append(uk)
                                        campaign_run.unit_levels[uk] = 1
                                        campaign_run.prisoner_message = f"归顺成功：获得兵种 {uk}（Lv1）"
                                else:
                                    # 已拥有：升级
                                    cur = int(campaign_run.unit_levels.get(uk, 1))
                                    if cur >= MAX_UNIT_LEVEL:
                                        campaign_run.prisoner_message = f"{uk} 已满级，归顺无效"
                                    else:
                                        # 祝福：战俘账本 → 升级需额外花费少量金币
                                        extra_cost = 0
                                        if campaign_run.blessing_selected == "prisoner_ledger":
                                            extra_cost = 20
                                        if extra_cost and campaign_run.state.gold < extra_cost:
                                            campaign_run.prisoner_message = f"金币不足，升级需额外 {extra_cost} 金"
                                            continue
                                        if extra_cost:
                                            campaign_run.state.gold -= extra_cost
                                        campaign_run.unit_levels[uk] = cur + 1
                                        campaign_run.prisoner_message = f"归顺成功：{uk} 升至 Lv{cur+1}"
                                campaign_run.prisoners.joined_once[uk] = True
                            elif action == 1:
                                # 处决：本run移除 + 立即收益
                                campaign_run.prisoners.executed_once[uk] = True
                                gold = PRISONER_EXECUTE_GOLD
                                if campaign_run.blessing_selected == "thrifty":
                                    gold = int(math.floor(gold * 0.8))
                                if campaign_run.blessing_selected == "iron_discipline":
                                    gold = int(math.ceil(gold * 1.25))
                                gold = int(math.ceil(gold * float(getattr(campaign_run, "prisoner_gold_mult", 1.0) or 1.0)))
                                campaign_run.state.gold += gold
                                rep_delta = -PRISONER_REP_LOSS
                                if campaign_run.blessing_selected == "mercy":
                                    rep_delta -= 1
                                campaign_run.reputation = _clamp_reputation(campaign_run.reputation + rep_delta)
                                campaign_run.prisoner_message = f"处决：+{gold}金，声望 {rep_delta}"
                            else:
                                # 放归：金币 + 声望
                                gold = PRISONER_RELEASE_GOLD
                                if campaign_run.blessing_selected == "thrifty":
                                    gold = int(math.ceil(gold * 1.25))
                                if campaign_run.blessing_selected == "iron_discipline":
                                    gold = int(math.floor(gold * 0.85))
                                if campaign_run.blessing_selected == "prisoner_ledger":
                                    gold += 30
                                gold = int(math.ceil(gold * float(getattr(campaign_run, "prisoner_gold_mult", 1.0) or 1.0)))
                                campaign_run.state.gold += gold
                                rep_delta = +PRISONER_REP_GAIN
                                if campaign_run.blessing_selected == "mercy":
                                    rep_delta += 1
                                campaign_run.reputation = _clamp_reputation(campaign_run.reputation + rep_delta)
                                campaign_run.prisoner_message = f"放归：+{gold}金，声望 +{rep_delta}"

                            campaign_run.prisoner_idx += 1
                            campaign_run.prisoner_action_idx = 0
                    elif mode == "campaign_blessing_select":
                        if not campaign_run:
                            mode = "menu"
                            continue
                        if event.key == pg.K_LEFT and campaign_run.blessing_options:
                            campaign_run.blessing_idx = (campaign_run.blessing_idx - 1) % len(campaign_run.blessing_options)
                        elif event.key == pg.K_RIGHT and campaign_run.blessing_options:
                            campaign_run.blessing_idx = (campaign_run.blessing_idx + 1) % len(campaign_run.blessing_options)
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if campaign_run.blessing_options:
                                campaign_run.blessing_selected = campaign_run.blessing_options[campaign_run.blessing_idx]
                                campaign_run.blessing_taken = True
                                bless_name = BLESSINGS.get(campaign_run.blessing_selected, {}).get("name", campaign_run.blessing_selected)
                                campaign_run.message = f"已选择祝福：{bless_name}"
                                
                                # === 祝福：不屈意志 - 开局奖励 ===
                                if campaign_run.blessing_selected == "veteran_unyielding":
                                    # 战士升至2级
                                    campaign_run.unit_levels["warrior"] = 2
                                    # 攻击锻造+2
                                    campaign_run.forge.offense_level_by_unit["warrior"] = 2
                                    # 防御锻造+2
                                    campaign_run.forge.defense_level_by_unit["warrior"] = 2
                            
                            if campaign_run.pending_finish_run:
                                mode = "campaign_victory"
                            else:
                                _autosave_now()
                                mode = "campaign_map"
                    elif mode == "campaign_combo_select":
                        if not campaign_run or not campaign_run.state:
                            mode = "menu"
                            continue
                        if event.key == pg.K_LEFT and campaign_run.combo_options:
                            campaign_run.combo_idx = (campaign_run.combo_idx - 1) % len(campaign_run.combo_options)
                        elif event.key == pg.K_RIGHT and campaign_run.combo_options:
                            campaign_run.combo_idx = (campaign_run.combo_idx + 1) % len(campaign_run.combo_options)
                        elif event.key == pg.K_r:
                            # 一次性重抽券：允许本次界面重抽一次候选
                            if campaign_run.oneshot.next_combo_reroll_once:
                                campaign_run.oneshot.next_combo_reroll_once = False
                                campaign_run.combo_options = _roll_combo_options()
                                campaign_run.combo_idx = 0
                                campaign_run.message = "已使用重抽券：候选已重抽"
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if not campaign_run.combo_options:
                                _autosave_now()
                                mode = "campaign_map"
                                continue
                            cid = campaign_run.combo_options[campaign_run.combo_idx]
                            msg = _apply_combo_card(cid)
                            campaign_run.message = msg
                            ctx = campaign_run.combo_context
                            pending = campaign_run.combo_pending_node_id
                            campaign_run.combo_context = ""
                            campaign_run.combo_pending_node_id = None
                            if ctx == "shop" and pending is not None:
                                campaign_run.combo.triggered_shop_once = True
                                _shop_enter(pending)
                            elif ctx == "event" and pending is not None:
                                campaign_run.combo.triggered_event_once = True
                                _event_enter(pending)
                            elif ctx == "elite" and pending is not None:
                                campaign_run.combo.triggered_elite_once = True
                                _enter_campaign_battle(pending)
                            else:
                                _autosave_now()
                            mode = "campaign_map"
                elif event.type == pg.MOUSEWHEEL:
                    if mode == "encyclopedia":
                        # y>0 向上滚
                        encyclopedia_scroll = max(0, encyclopedia_scroll - event.y * 60)
                    elif mode == "campaign_map":
                        max_scroll = campaign_map_max_scroll()
                        if campaign_run:
                            campaign_run.map_scroll = campaign_run.map_scroll - event.y * 60.0
                            campaign_run.map_scroll = max(0.0, min(max_scroll, campaign_run.map_scroll))

            # === 绘制阶段 ===
            # 所有内容先绘制到虚拟画布 canvas 上
            
            if mode == "game":
                game.update(dt * time_scale)
                draw_world(canvas, game, font)
                if game.winner:
                    mode = "menu"
            elif mode == "campaign_battle":
                game.update(dt * time_scale)
                draw_world(canvas, game, font)

                # 手动模式超时处理：判定为“敌方撤退”，玩家惨胜
                if not game.winner and game.battle_time >= 300.0:
                    game.winner = "left"
                    right_destroyed = sum(1 for b in game.right_bases if b.hp <= 0)
                    penalty = max(0.0, 0.04 - 0.01 * right_destroyed)
                    if campaign_run:
                        campaign_run.timeout_win = True
                        campaign_run.timeout_penalty_coeff = getattr(campaign_run, "timeout_penalty_coeff", 1.0) + penalty

                if game.winner:
                    if game.winner == "left":
                        if not campaign_run:
                            reset_campaign_run()
                            mode = "menu"
                            continue
                        campaign_run.last_battle_time = game.battle_time
                        # 胜利：先保存基地HP，然后落地战斗结果并进入 M2 结算链
                        campaign_run.saved_left_base_hps = [b.hp for b in game.left_bases]
                        # M3：结算本场战斗统计（出兵次数、敌方出兵种类集合T）
                        battle_counts = getattr(game, "battle_left_spawn_counts", {}) or {}
                        # 口径修正：出兵次数按“单场战斗”统计（未出兵视为0）
                        campaign_run.forge.spawn_count_by_unit = {k: int(battle_counts.get(k, 0)) for k in (campaign_run.units or [])}
                        enemy_set = getattr(game, "battle_right_spawned_types", set()) or set()
                        campaign_run.last_battle_enemy_types = sorted(list(enemy_set))
                        # M3：为本关锻造/俘虏重置交互状态
                        campaign_run.forge_done = False
                        campaign_run.forge_result_message = ""
                        campaign_run.prisoner_queue = []
                        campaign_run.prisoner_idx = 0
                        campaign_run.prisoner_action_idx = 0
                        campaign_run.prisoner_message = ""
                        campaign_run.prisoners_inited = False
                        finalize_campaign_battle(True, campaign_run.last_battle_time)
                    else:
                        # 失败：进入失败结算页，方便测试与复盘（按 Esc/回车返回主菜单）
                        mode = "campaign_defeat"
            elif mode == "free_battle":
                game.update(dt * time_scale)
                draw_world(canvas, game, font)
                if game.winner:
                    mode = "menu"
            elif mode == "menu":
                draw_menu(canvas, font, has_autosave=autosave_exists())
            elif mode == "settings":
                draw_settings(
                    canvas, 
                    font, 
                    current_res_idx, 
                    resolutions, 
                    is_fullscreen, 
                    audio_manager.bgm_volume, 
                    audio_manager.sfx_volume, 
                    settings_cursor,
                    get_lang(),
                )
            elif mode == "pause_menu":
                # 绘制游戏背景（暂停时显示当前游戏画面）
                # 注意：这里需要先画游戏画面，再画暂停菜单
                # 但是由于 update 循环中 paused 时不更新游戏逻辑，所以画面是静止的
                # 我们可以直接重用上一帧的 game.draw_world 逻辑，或者简单点，
                # 因为我们每一帧都会重新 fill，所以这里需要手动再次调用 draw_world
                # 必须保证 paused_from_mode 是有效的游戏模式
                if paused_from_mode in ["game", "campaign_battle", "free_battle"]:
                    draw_world(canvas, game, font)
                draw_pause_menu(canvas, font, pause_cursor)
            elif mode == "encyclopedia":
                draw_encyclopedia(canvas, font, encyclopedia_scroll)
            
            elif mode == "campaign_map":
                enemy_preview_map: dict[int, list[str]] | None = None
                if campaign_run and campaign_run.state:
                    enemy_preview_map = {}
                    for node_id, node in campaign_run.state.nodes.items():
                        if node.node_type not in CAMPAIGN_BATTLE_NODE_TYPES or node.cleared:
                            continue
                        enemy_preview_map[node_id] = _campaign_node_enemy_units(campaign_run.state, node_id)
                draw_campaign_map(
                    canvas,
                    font,
                    campaign_run.state if campaign_run else None,
                    campaign_run.cursor_node_id if campaign_run else None,
                    campaign_run.message if campaign_run else "",
                    campaign_run.map_scroll if campaign_run else 0.0,
                    enemy_preview_map,
                )
            elif mode == "campaign_shop":
                draw_campaign_shop_v2(canvas, font, campaign_run)
            elif mode == "campaign_loadout":
                draw_loadout(
                    canvas,
                    font,
                    campaign_run.units if campaign_run else [],
                    campaign_run.unit_levels if campaign_run else {},
                    loadout_cursor,
                    loadout_focus,
                    loadout_skill_idx,
                    campaign_run.skills if campaign_run else [],
                    max_units=1,
                    max_skills=0,
                )
            elif mode == "campaign_reward":
                if not campaign_run or not campaign_run.reward_options:
                    finalize_campaign_battle(True, campaign_run.last_battle_time if campaign_run else 0.0)
                else:
                    draw_reward_picker(
                        canvas,
                        font,
                        campaign_run.reward_options,
                        campaign_run.reward_idx,
                        campaign_run.unit_levels,
                    )
            elif mode == "campaign_postbattle_summary":
                draw_campaign_postbattle_summary(canvas, font, campaign_run)
            elif mode == "campaign_forge":
                draw_campaign_forge(canvas, font, campaign_run)
            elif mode == "campaign_prisoners":
                draw_campaign_prisoners(canvas, font, campaign_run)
            elif mode == "campaign_blessing_select":
                draw_campaign_blessing_select(canvas, font, campaign_run)
            elif mode == "campaign_event":
                draw_campaign_event(canvas, font, campaign_run.event_message if campaign_run else "")
            elif mode == "campaign_event_choice":
                draw_campaign_event_choice(canvas, font, campaign_run)
            elif mode == "campaign_event_unit_select":
                draw_campaign_event_unit_select(canvas, font, campaign_run)
            elif mode == "campaign_event_skill_select":
                draw_campaign_event_skill_select(canvas, font, campaign_run)
            elif mode == "campaign_combo_select":
                draw_campaign_combo_select(canvas, font, campaign_run)
            elif mode == "free_loadout":
                draw_loadout(canvas, font, free_units, free_unit_levels, loadout_cursor, loadout_focus, loadout_skill_idx, free_skills, max_units=0, max_skills=3)
            elif mode == "free_boons":
                draw_boon_select(canvas, font, free_boons, boon_cursor)
            elif mode == "campaign_victory":
                draw_campaign_victory(canvas, font, campaign_run)
            elif mode == "campaign_defeat":
                draw_campaign_defeat(canvas, font, campaign_run)

            # 绘制倍速提示
            if mode in ["game", "campaign_battle", "free_battle"] and time_scale > 1.0:
                speed_surf = font.render(f"SPEED: {time_scale:.1f}x", True, (255, 220, 0))
                canvas.blit(speed_surf, (VIRTUAL_WIDTH - speed_surf.get_width() - 20, 10))

            # === 音频更新 ===
            if mode in ["campaign_battle", "free_battle", "game", "pause_menu", "settings", "encyclopedia"]:
                # 暂停/设置/百科菜单中保持 BGM 播放，但不更新游戏逻辑音效
                if not audio_manager.bgm_playing:
                    audio_manager.play_bgm()
                
                if mode in ["campaign_battle", "free_battle", "game"]:
                    # 统计敌人数量
                    current_enemy_count = 0
                    if game and hasattr(game, "right_units"):
                        current_enemy_count = sum(len(lane) for lane in game.right_units)
                    
                    # 获取击杀数 (从上一帧 game.update 中)
                    kills = getattr(game, "recent_kills", 0)
                    
                    audio_manager.update(dt, current_enemy_count, kills)
            else:
                if audio_manager.bgm_playing:
                    audio_manager.stop_bgm()
            
            # === 最终缩放与显示 ===
            # 计算缩放比例（保持宽高比，Letterboxing）
            scale_w = window_width / VIRTUAL_WIDTH
            scale_h = window_height / VIRTUAL_HEIGHT
            scale = min(scale_w, scale_h)
            
            new_w = int(VIRTUAL_WIDTH * scale)
            new_h = int(VIRTUAL_HEIGHT * scale)
            
            # 如果比例不是 1.0，进行缩放
            if scale != 1.0:
                # 使用 smoothscale 可能在低分辨率下模糊，但在高分屏下更好
                # 对于像素风格，scale (邻近插值) 更锐利，但如果不是整数倍可能会有像素抖动
                # 这里使用 scale 保持锐利度
                scaled_surf = pg.transform.scale(canvas, (new_w, new_h))
            else:
                scaled_surf = canvas

            # 计算居中偏移
            x_offset = (window_width - new_w) // 2
            y_offset = (window_height - new_h) // 2
            
            # 绘制黑边背景和游戏画面
            screen.fill((0, 0, 0))
            screen.blit(scaled_surf, (x_offset, y_offset))

            pg.display.flip()

        pg.quit()
        sys.exit(0)
    except Exception:
        # 捕获所有异常并写入 crash.log，同时打印到控制台
        error_msg = traceback.format_exc()
        print("GAME CRASHED:")
        print(error_msg)
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write(error_msg)
        # 尝试弹窗提示（可选）
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "游戏发生崩溃，错误日志已保存至 crash.log", "Error", 0x10)
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    run()
