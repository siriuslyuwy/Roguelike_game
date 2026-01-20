from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .constants import (
    CAMPAIGN_BASE_GOLD,
    CAMPAIGN_BATTLE_NODE_TYPES,
    CAMPAIGN_EVENT_GOLD,
    CAMPAIGN_GOLD_INCREMENT,
)


MAP_COLUMN_STEP = 160.0
MAP_LAYER_GAP = 130.0
MAP_COLUMN_JITTER = 14.0
MAP_COLUMN_SLOTS = [-2, -1, 0, 1, 2]


DEFAULT_MAP_BLUEPRINT: Sequence[dict] = (
    {"count": 3, "forced": ["combat", "combat", "combat"]},
    {"count": 3, "weights": {"combat": 0.65, "event": 0.25, "shop": 0.1}},
    {"count": 3, "weights": {"combat": 0.6, "event": 0.25, "rest": 0.15}},
    {"count": 3, "weights": {"combat": 0.55, "event": 0.25, "elite": 0.2}},
    {"count": 3, "weights": {"combat": 0.55, "event": 0.3, "elite": 0.15}},
    {"count": 3, "weights": {"combat": 0.45, "elite": 0.45, "event": 0.1}},
    {"count": 3, "weights": {"rest": 0.5, "event": 0.3, "combat": 0.2}},
    {"count": 3, "weights": {"shop": 0.4, "combat": 0.4, "event": 0.2}},
    {"count": 3, "weights": {"combat": 0.55, "event": 0.25, "elite": 0.2}},
    {"count": 3, "weights": {"elite": 0.5, "combat": 0.5}},
    {"count": 3, "weights": {"combat": 0.5, "elite": 0.4, "event": 0.1}},
    {"count": 3, "weights": {"combat": 0.45, "elite": 0.45, "rest": 0.1}},
    {"count": 3, "weights": {"combat": 0.4, "elite": 0.5, "event": 0.1}},
    {"count": 3, "weights": {"elite": 0.6, "combat": 0.3, "rest": 0.1}},
    {"count": 3, "weights": {"elite": 0.55, "combat": 0.35, "shop": 0.1}},
    {"count": 3, "weights": {"elite": 0.5, "combat": 0.4, "rest": 0.1}},
    {"count": 3, "weights": {"elite": 0.5, "combat": 0.5}},
    {"count": 3, "weights": {"elite": 0.6, "combat": 0.4}},
    {"count": 2, "weights": {"elite": 0.5, "rest": 0.5}},
    {"count": 1, "forced": ["boss"]},
)


@dataclass
class CampaignNode:
    node_id: int
    layer_index: int
    column_index: int
    node_type: str
    connections: List[int] = field(default_factory=list)
    prev_nodes: List[int] = field(default_factory=list)
    cleared: bool = False
    x_offset: float = 0.0
    column_slot: int = 0
    ai_seed: int = 0
    event_subtype: Optional[str] = None  # 事件子类型，用于区分不同的事件


@dataclass
class CampaignState:
    nodes: Dict[int, CampaignNode]
    layers: List[List[int]]
    gold: int = 0
    battle_count: int = 0
    cursor_node_id: Optional[int] = None
    active_node_id: Optional[int] = None
    day: int = 0

    def available_nodes(self) -> List[int]:
        # 尚未确定落脚点：默认开放第一层节点供选择
        if self.active_node_id is None:
            if not self.layers:
                return []
            return list(self.layers[0])

        active_node = self.nodes.get(self.active_node_id)
        if not active_node:
            return []

        candidate_ids = {active_node.node_id}
        candidate_ids.update(active_node.connections)
        candidate_ids.update(active_node.prev_nodes)

        ordered: List[int] = []
        for nid in sorted(
            (nid for nid in candidate_ids if nid in self.nodes),
            key=lambda nid: (self.nodes[nid].layer_index, self.nodes[nid].column_index),
        ):
            ordered.append(nid)
        return ordered

    def ensure_cursor(self) -> Optional[int]:
        available = self.available_nodes()
        if not available:
            self.cursor_node_id = None
            return None
        if self.cursor_node_id not in available:
            self.cursor_node_id = available[0]
        return self.cursor_node_id

    def move_to_node(self, node_id: int) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return False
        moved = node_id != self.active_node_id
        self.cursor_node_id = node_id
        if moved:
            self.active_node_id = node_id
            self.day += 1
        return moved

    def move_cursor(self, direction: int) -> Optional[int]:
        available = self.available_nodes()
        if not available:
            self.cursor_node_id = None
            return None
        if self.cursor_node_id not in available:
            self.cursor_node_id = available[0]
            return self.cursor_node_id
        idx = available.index(self.cursor_node_id)
        idx = (idx + direction) % len(available)
        self.cursor_node_id = available[idx]
        return self.cursor_node_id

    def mark_node_cleared(self, node_id: int) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].cleared = True
            self.active_node_id = node_id
            self.cursor_node_id = node_id

    def all_cleared(self) -> bool:
        return all(node.cleared for node in self.nodes.values())

    def battle_nodes_remaining(self) -> bool:
        for node in self.nodes.values():
            if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES and not node.cleared:
                return True
        return False

    def difficulty_index(self, node_type: str, max_index: int) -> int:
        base_index = self.battle_count
        if node_type == "elite":
            base_index += 1
        elif node_type == "boss":
            base_index += 2
        return min(base_index, max_index - 1)

    def battle_reward_amount(self) -> int:
        return CAMPAIGN_BASE_GOLD + CAMPAIGN_GOLD_INCREMENT * self.battle_count

    def grant_event_reward(self) -> int:
        self.gold += CAMPAIGN_EVENT_GOLD
        return CAMPAIGN_EVENT_GOLD

    def mark_battle_completed(self) -> None:
        self.battle_count += 1


def _build_layer_types(blueprint: dict, rng: random.Random) -> List[str]:
    count = blueprint.get("count") or 3
    min_count = blueprint.get("min_count")
    max_count = blueprint.get("max_count")
    if min_count is not None and max_count is not None:
        count = rng.randint(int(min_count), int(max_count))
    elif min_count is not None:
        count = rng.randint(int(min_count), int(min_count) + 1)
    elif max_count is not None:
        count = min(count, int(max_count))

    forced = list(blueprint.get("forced", []))
    types: List[str] = forced[:count]
    weights = blueprint.get("weights")

    if not weights and not types:
        weights = {"combat": 1.0}

    if weights:
        choices = list(weights.keys())
        weight_vals = list(weights.values())
        total_weight = sum(weight_vals) or 1.0
        weight_vals = [w / total_weight for w in weight_vals]
    else:
        choices = []
        weight_vals = []

    while len(types) < count:
        if choices:
            pick = rng.choices(choices, weights=weight_vals)[0]
        else:
            pick = "combat"
        types.append(pick)

    rng.shuffle(types)
    return types[:count]


def generate_campaign_map(
    rng: Optional[random.Random] = None,
    layers: Optional[Sequence[Sequence[str]]] = None,
) -> CampaignState:
    rng = rng or random.Random()
    nodes: Dict[int, CampaignNode] = {}
    layer_nodes: List[List[int]] = []
    node_counter = 0
    prev_layer_ids: List[int] = []
    prev_layer_slots: List[int] = []

    if layers is None:
        all_layer_blueprints = list(DEFAULT_MAP_BLUEPRINT)
        first_layer_idx = 0
        boss_layer_idx = len(all_layer_blueprints) - 1
        middle_start = first_layer_idx + 1
        middle_end = boss_layer_idx - 1  # inclusive

        # === 地图硬约束（按用户规格）===
        # - 第1层（index=0）：全 combat（由 blueprint forced 保证）
        # - 第2~10层（index 1..9）：只允许 combat/event/shop/rest（禁止 elite）
        # - 第11~17层（index 10..16）：允许 elite，但任意相邻两层最多1层出现 elite（避免连着精英）
        # - 第18~19层（index 17..18）：允许更高 elite 密度；且 boss 前至少出现 1 次 rest 或 shop
        # - 全局均匀性：任意连续5层至少1个 shop；任意连续3层至少1个 event（均仅对中间层生效）

        early_end = 9
        mid_start = 10
        mid_end = 16
        late_start = 17
        late_end = 18

        # 每层节点数（来自 blueprint）
        layer_counts: Dict[int, int] = {}
        for li in range(len(all_layer_blueprints)):
            layer_counts[li] = int(all_layer_blueprints[li].get("count", 3) or 3)

        middle_layers = list(range(middle_start, middle_end + 1))

        def _ensure_window_presence(layers_with_type: set[int], window: int, required_layers: List[int]) -> set[int]:
            """在 required_layers（按升序）上保证任意连续 window 个 layer 至少包含一次该类型。"""
            s = set(layers_with_type)
            if not required_layers:
                return s
            for i in range(len(required_layers) - window + 1):
                block = required_layers[i : i + window]
                if not any(li in s for li in block):
                    # 缺失：补到这个窗口的最后一层（更不影响前面窗口）
                    s.add(block[-1])
            return s

        def _pick_spaced_layers(candidates: List[int], desired: int, *, avoid_adjacent_in: set[int] | None = None) -> set[int]:
            """从 candidates 中挑 desired 个；若 layer 在 avoid_adjacent_in 范围，则不允许相邻层同时被选。"""
            if desired <= 0 or not candidates:
                return set()
            avoid_adjacent_in = avoid_adjacent_in or set()

            picked: set[int] = set()
            pool = list(candidates)
            rng.shuffle(pool)
            for li in pool:
                if len(picked) >= desired:
                    break
                if li in picked:
                    continue
                if li in avoid_adjacent_in:
                    if (li - 1) in picked and (li - 1) in avoid_adjacent_in:
                        continue
                    if (li + 1) in picked and (li + 1) in avoid_adjacent_in:
                        continue
                picked.add(li)
            return picked

        # --- 规划 shop layers（gap<=5）---
        shop_layers: set[int] = set()
        cur = rng.randint(middle_start, min(middle_start + 2, middle_end))
        while cur <= middle_end:
            shop_layers.add(cur)
            cur += rng.randint(4, 5)
        # 强制：2~10 层至少出现 1 次 shop
        if not any(li in shop_layers for li in range(middle_start, early_end + 1)):
            shop_layers.add(rng.randint(middle_start, early_end))
        # 全局保底：任意连续5层至少1 shop（仅中间层）
        shop_layers = _ensure_window_presence(shop_layers, 5, middle_layers)

        # --- 规划 event layers（gap<=3）---
        event_layers: set[int] = set()
        cur = rng.randint(middle_start, min(middle_start + 1, middle_end))
        while cur <= middle_end:
            event_layers.add(cur)
            cur += rng.randint(2, 3)
        # 全局保底：任意连续3层至少1 event（仅中间层）
        event_layers = _ensure_window_presence(event_layers, 3, middle_layers)

        # --- 规划 rest layers（偏少即可，但要满足 boss 前整备）---
        rest_layers: set[int] = set()
        # 轻量：全图默认 2 个休整点（可按后续平衡调）
        rest_candidates = [li for li in middle_layers if li not in (middle_start,)]
        rest_layers = _pick_spaced_layers(rest_candidates, 2, avoid_adjacent_in=set())

        # boss 前至少 1 次 rest 或 shop（第18~19层，即 index 17..18）
        if not any(li in shop_layers or li in rest_layers for li in range(late_start, late_end + 1)):
            # 优先放 rest，让 shop 主要承担“5层保底”职责
            rest_layers.add(rng.choice([late_start, late_end]))

        # --- 规划 elite layers ---
        # 保持原先“总量控制”的感觉：默认 5 个精英节点
        desired_elite = 5
        elite_candidates = list(range(mid_start, late_end + 1))  # 11层后才有精英（index>=10）
        elite_layers: set[int] = set()
        # 多尝试几次，尽量满足 mid 段不连层
        for _ in range(30):
            picked = _pick_spaced_layers(elite_candidates, desired_elite, avoid_adjacent_in=set(range(mid_start, mid_end + 1)))
            # 额外校验：mid 段（10..16）不允许相邻同时精英
            ok = True
            for li in range(mid_start, mid_end):
                if li in picked and (li + 1) in picked:
                    ok = False
                    break
            if ok:
                elite_layers = picked
                break
        # 兜底：若未挑满，也可以减少数量（避免卡死）
        if not elite_layers:
            elite_layers = _pick_spaced_layers(elite_candidates, min(desired_elite, len(elite_candidates)), avoid_adjacent_in=set(range(mid_start, mid_end + 1)))

        # 禁止 elite 出现在第2~10层（index 1..9）
        elite_layers = {li for li in elite_layers if li >= mid_start}

        def _build_layer(count: int, li: int) -> List[str]:
            """为某层构建 node types，满足该层允许类型与全局规划。"""
            types = ["combat"] * max(1, int(count))
            slots = list(range(len(types)))
            rng.shuffle(slots)

            def place(t: str) -> bool:
                nonlocal slots, types
                if not slots:
                    return False
                idx = slots.pop()
                types[idx] = t
                return True

            # 早期层：严格禁止 elite
            if li <= early_end:
                # shop/event/rest 按规划落地
                if li in shop_layers:
                    place("shop")
                if li in event_layers:
                    place("event")
                if li in rest_layers:
                    place("rest")
                return types

            # 中后期：允许 elite
            planned: List[str] = []
            if li in shop_layers:
                planned.append("shop")
            if li in event_layers:
                planned.append("event")
            if li in rest_layers:
                planned.append("rest")
            if li in elite_layers:
                planned.append("elite")

            # 若 planned 超出该层容量：按优先级丢弃（尽量不破坏全局保底）
            if len(planned) > len(types):
                # 优先丢 elite（因为它不是保底约束），再丢 rest（只有 boss 前约束），再丢 event，最后才丢 shop
                prio = {"elite": 0, "rest": 1, "event": 2, "shop": 3}
                planned.sort(key=lambda t: prio.get(t, 0))
                planned = planned[-len(types) :]

                # boss 前整备兜底：late 段必须保留至少一个 rest/shop
                if late_start <= li <= late_end and not any(t in ("rest", "shop") for t in planned):
                    # 强行把最后一个替换为 rest
                    if planned:
                        planned[-1] = "rest"
                    else:
                        planned = ["rest"]

            for t in planned:
                place(t)
            return types

        # 生成各层 node types
        resolved_layers: List[List[str]] = []
        for li, blueprint in enumerate(all_layer_blueprints):
            if li == first_layer_idx or li == boss_layer_idx:
                resolved_layers.append(_build_layer_types(blueprint, rng))
                continue
            resolved_layers.append(_build_layer(layer_counts.get(li, 3), li))

        # === 轻量自检（开发期防止规则失效）===
        def _layer_has(li: int, t: str) -> bool:
            return t in resolved_layers[li]

        # 2~10 禁 elite
        for li in range(middle_start, early_end + 1):
            if _layer_has(li, "elite"):
                raise ValueError(f"Map rule violated: elite in early layer {li}")

        # 11~17 不连层精英（相邻两层最多一层有 elite）
        for li in range(mid_start, mid_end):
            if _layer_has(li, "elite") and _layer_has(li + 1, "elite"):
                raise ValueError(f"Map rule violated: consecutive elite at layers {li} & {li+1}")

        # boss 前至少 1 次 rest 或 shop（18~19层）
        if not any(_layer_has(li, "rest") or _layer_has(li, "shop") for li in range(late_start, late_end + 1)):
            raise ValueError("Map rule violated: missing rest/shop before boss")

        # 任意连续5层至少1 shop（中间层）
        for i in range(middle_start, middle_end - 5 + 2):
            block = range(i, i + 5)
            if not any(_layer_has(li, "shop") for li in block):
                raise ValueError(f"Map rule violated: missing shop in 5-layer window {i}..{i+4}")

        # 任意连续3层至少1 event（中间层）
        for i in range(middle_start, middle_end - 3 + 2):
            block = range(i, i + 3)
            if not any(_layer_has(li, "event") for li in block):
                raise ValueError(f"Map rule violated: missing event in 3-layer window {i}..{i+2}")
    else:
        resolved_layers = [list(layer) for layer in layers]

    for layer_index, node_types in enumerate(resolved_layers):
        current_ids: List[int] = []
        count = len(node_types)
        if count <= 0:
            continue

        candidate_slots: List[int]
        if prev_layer_slots:
            slot_set = set()
            for slot in prev_layer_slots:
                slot_set.add(slot)
                if slot - 1 in range(len(MAP_COLUMN_SLOTS)):
                    slot_set.add(slot - 1)
                if slot + 1 in range(len(MAP_COLUMN_SLOTS)):
                    slot_set.add(slot + 1)
            if len(slot_set) < count:
                slot_set = set(range(len(MAP_COLUMN_SLOTS)))
            candidate_slots = sorted(slot_set)
        else:
            candidate_slots = list(range(len(MAP_COLUMN_SLOTS)))

        if len(candidate_slots) < count:
            candidate_slots = list(range(len(MAP_COLUMN_SLOTS)))

        chosen_slots = sorted(rng.sample(candidate_slots, k=count))
        prev_layer_slots = chosen_slots

        center_slot_idx = len(MAP_COLUMN_SLOTS) // 2

        for column_index, node_type in enumerate(node_types):
            # Boss 节点强制居中
            if node_type == "boss":
                slot_idx = center_slot_idx
                jitter = 0.0
            else:
                slot_idx = chosen_slots[column_index]
                jitter = rng.uniform(-MAP_COLUMN_JITTER, MAP_COLUMN_JITTER) if count > 1 else 0.0
            
            # 为事件节点随机分配子类型
            event_subtype = None
            if node_type == "event":
                event_subtypes = [
                    "lucky_gold",      # 幸运金币
                    "investment",       # 投资
                    "supply_station",   # 补给站
                    "lost_warrior",     # 迷失战士
                    "mystic_merchant",  # 神秘商人
                    "cursed_treasure",  # 诅咒宝箱
                    "training_ground",  # 训练场
                    "black_market",     # 黑市
                ]
                event_subtype = rng.choice(event_subtypes)
            
            node = CampaignNode(
                node_id=node_counter,
                layer_index=layer_index,
                column_index=column_index,
                node_type=node_type,
                x_offset=jitter,
                column_slot=slot_idx,
                ai_seed=rng.randint(0, 2**31 - 1),
                event_subtype=event_subtype,
            )
            nodes[node_counter] = node
            current_ids.append(node_counter)
            node_counter += 1
        layer_nodes.append(current_ids)

        if prev_layer_ids:
            prev_nodes = [nodes[pid] for pid in prev_layer_ids]
            for prev_node in prev_nodes:
                connections: List[int] = []
                for cid in current_ids:
                    cur_node = nodes[cid]
                    if abs(cur_node.column_slot - prev_node.column_slot) <= 1:
                        connections.append(cid)
                        if prev_node.node_id not in cur_node.prev_nodes:
                            cur_node.prev_nodes.append(prev_node.node_id)
                if not connections:
                    # 没有邻近节点则连向最近的一个
                    closest_id = min(
                        current_ids,
                        key=lambda cid: abs(nodes[cid].column_slot - prev_node.column_slot),
                    )
                    connections = [closest_id]
                    if prev_node.node_id not in nodes[closest_id].prev_nodes:
                        nodes[closest_id].prev_nodes.append(prev_node.node_id)
                prev_node.connections = connections

            for cid in current_ids:
                cur_node = nodes[cid]
                if cur_node.prev_nodes:
                    continue
                parent_id = min(
                    prev_layer_ids,
                    key=lambda pid: abs(nodes[pid].column_slot - cur_node.column_slot),
                )
                parent_node = nodes[parent_id]
                if cid not in parent_node.connections:
                    parent_node.connections.append(cid)
                cur_node.prev_nodes.append(parent_id)

        prev_layer_ids = current_ids

    state = CampaignState(nodes=nodes, layers=layer_nodes)
    state.ensure_cursor()
    return state

