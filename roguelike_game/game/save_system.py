from __future__ import annotations

import json
import os
import shutil
from dataclasses import fields
from pathlib import Path
from typing import Any, Optional

from .campaign import CampaignNode, CampaignState
from .run_state import CampaignRunState, ComboState, ForgeState, OneShotState, PrisonerMemoryState


SAVE_VERSION = 2
AUTOSAVE_FILENAME = "autosave.json"
AUTOSAVE_BAK_FILENAME = "autosave.bak.json"
MIRROR_PROFILE_FILENAME = "mirror_profile.json"

# 旧单字母 key 到新语义化 key 的映射（用于存档兼容）
OLD_TO_NEW_KEY = {
    "Q": "warrior", "W": "shield", "E": "maul", "R": "berserker",
    "A": "priest", "S": "archer", "D": "mage", "F": "rhino",
    "G": "assassin", "H": "interceptor", "J": "drummer", "K": "spearman",
    "L": "frost_archer", "M": "exploder", "N": "light_cavalry",
}


def _migrate_unit_key(key: str) -> str:
    """将旧的单字母 key 转换为新的语义化 key"""
    return OLD_TO_NEW_KEY.get(key, key)


def _migrate_unit_list(keys: list) -> list:
    """迁移兵种列表，同时过滤掉已删除的 'O' (splitling)"""
    return [_migrate_unit_key(k) for k in keys if k != "O"]


def _migrate_unit_dict(d: dict) -> dict:
    """迁移以兵种 key 为键的字典，同时过滤掉已删除的 'O' (splitling)"""
    return {_migrate_unit_key(k): v for k, v in d.items() if k != "O"}


def _env_truthy(name: str) -> bool:
    v = os.getenv(name)
    if v is None:
        return False
    v = str(v).strip().lower()
    return v not in ("", "0", "false", "no", "off")


def default_save_dir() -> Path:
    """
    Demo/本地存档目录（无需第三方依赖）：
    - 可通过环境变量 SEVENLINES_SAVE_DIR 覆盖，便于开发测试/多档隔离
    - 默认写到用户目录（避免安装目录无写权限）
    """
    override = os.getenv("SEVENLINES_SAVE_DIR")
    if override:
        return Path(override).expanduser().resolve()

    # Windows: %APPDATA%/SevenLines/saves
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return base / "SevenLines" / "saves"

    # Linux/macOS: ~/.local/share/sevenlines/saves (Demo 足够)
    xdg = os.getenv("XDG_DATA_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".local" / "share")
    return base / "sevenlines" / "saves"


def autosave_path() -> Path:
    return default_save_dir() / AUTOSAVE_FILENAME


def autosave_backup_path() -> Path:
    return default_save_dir() / AUTOSAVE_BAK_FILENAME


def mirror_profile_path() -> Path:
    return default_save_dir() / MIRROR_PROFILE_FILENAME


def load_mirror_profile() -> dict:
    """
    返回 {"mirror_snapshot", "mirror_script", "mirror_last_updated"}。
    读取失败或缺失字段时返回默认空值。
    """
    p = mirror_profile_path()
    if not p.exists():
        return {"mirror_snapshot": {}, "mirror_script": [], "mirror_last_updated": 0.0}
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    snapshot = data.get("mirror_snapshot") if isinstance(data.get("mirror_snapshot"), dict) else {}
    script = data.get("mirror_script") if isinstance(data.get("mirror_script"), list) else []
    try:
        last_updated = float(data.get("mirror_last_updated", 0.0) or 0.0)
    except Exception:
        last_updated = 0.0
    return {"mirror_snapshot": snapshot, "mirror_script": script, "mirror_last_updated": last_updated}


def save_mirror_profile(snapshot: dict, script: list, last_updated: float) -> None:
    if _env_truthy("SEVENLINES_DISABLE_SAVE"):
        return
    save_dir = default_save_dir()
    save_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mirror_snapshot": dict(snapshot or {}),
        "mirror_script": list(script or []),
        "mirror_last_updated": float(last_updated or 0.0),
    }
    tmp = mirror_profile_path().with_suffix(".json.tmp")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, mirror_profile_path())


def autosave_exists() -> bool:
    try:
        return autosave_path().exists()
    except OSError:
        return False


def delete_autosave() -> None:
    for p in (autosave_path(), autosave_backup_path()):
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def _campaign_state_to_dict(state: CampaignState) -> dict:
    # 直接存 dict；JSON 会把 int key 变成 str，加载时再转回 int
    nodes = {
        int(nid): {
            "node_id": int(node.node_id),
            "layer_index": int(node.layer_index),
            "column_index": int(node.column_index),
            "node_type": str(node.node_type),
            "connections": list(node.connections or []),
            "prev_nodes": list(node.prev_nodes or []),
            "cleared": bool(node.cleared),
            "x_offset": float(node.x_offset),
            "column_slot": int(node.column_slot),
            "ai_seed": int(node.ai_seed),
            "event_subtype": node.event_subtype,
        }
        for nid, node in (state.nodes or {}).items()
    }
    return {
        "nodes": nodes,
        "layers": [list(layer) for layer in (state.layers or [])],
        "gold": int(state.gold),
        "battle_count": int(state.battle_count),
        "cursor_node_id": state.cursor_node_id,
        "active_node_id": state.active_node_id,
        "day": int(state.day),
    }


def _campaign_state_from_dict(d: dict) -> CampaignState:
    raw_nodes = d.get("nodes", {}) or {}
    nodes: dict[int, CampaignNode] = {}
    for k, v in raw_nodes.items():
        try:
            nid = int(k)
        except Exception:
            continue
        if not isinstance(v, dict):
            continue
        node = CampaignNode(
            node_id=int(v.get("node_id", nid)),
            layer_index=int(v.get("layer_index", 0)),
            column_index=int(v.get("column_index", 0)),
            node_type=str(v.get("node_type", "combat")),
            connections=[int(x) for x in (v.get("connections", []) or [])],
            prev_nodes=[int(x) for x in (v.get("prev_nodes", []) or [])],
            cleared=bool(v.get("cleared", False)),
            x_offset=float(v.get("x_offset", 0.0) or 0.0),
            column_slot=int(v.get("column_slot", 0)),
            ai_seed=int(v.get("ai_seed", 0)),
            event_subtype=v.get("event_subtype"),
        )
        nodes[nid] = node
    return CampaignState(
        nodes=nodes,
        layers=[list(layer) for layer in (d.get("layers", []) or [])],
        gold=int(d.get("gold", 0) or 0),
        battle_count=int(d.get("battle_count", 0) or 0),
        cursor_node_id=d.get("cursor_node_id"),
        active_node_id=d.get("active_node_id"),
        day=int(d.get("day", 0) or 0),
    )


def _campaign_run_to_dict(run: CampaignRunState) -> dict:
    # 只存“局内状态”，不存 pygame/game 运行态
    payload: dict[str, Any] = {
        "save_version": SAVE_VERSION,
        "run": {},
    }

    run_dict: dict[str, Any] = {}
    for f in fields(CampaignRunState):
        name = f.name
        val = getattr(run, name)
        if name == "state":
            run_dict["state"] = _campaign_state_to_dict(val) if val else None
        elif name == "oneshot":
            run_dict["oneshot"] = {
                "next_shop_free_refresh_disabled": bool(val.next_shop_free_refresh_disabled),
                "next_shop_free_refresh_bonus": int(val.next_shop_free_refresh_bonus),
                "next_shop_price_mult_once": float(val.next_shop_price_mult_once),
                "next_combo_reroll_once": bool(val.next_combo_reroll_once),
                "next_combo_bias_once": bool(val.next_combo_bias_once),
            }
        elif name == "forge":
            run_dict["forge"] = {
                "offense_level_by_unit": dict(val.offense_level_by_unit or {}),
                "defense_level_by_unit": dict(val.defense_level_by_unit or {}),
                "spawn_count_by_unit": dict(val.spawn_count_by_unit or {}),
                "last_target_unit": val.last_target_unit,
                "last_direction": val.last_direction,
            }
        elif name == "prisoners":
            run_dict["prisoners"] = {
                "joined_once": dict(val.joined_once or {}),
                "executed_once": dict(val.executed_once or {}),
            }
        elif name == "combo":
            run_dict["combo"] = {
                "selected_cards": list(val.selected_cards or []),
                "triggered_shop_once": bool(val.triggered_shop_once),
                "triggered_event_once": bool(val.triggered_event_once),
                "triggered_elite_once": bool(val.triggered_elite_once),
            }
        else:
            # JSON 友好字段（list/dict/str/int/bool/None/float）
            run_dict[name] = val

    payload["run"] = run_dict
    return payload


def _campaign_run_from_dict(d: dict) -> CampaignRunState:
    run_data = (d.get("run") or {}) if isinstance(d, dict) else {}
    rs = CampaignRunState()

    if isinstance(run_data.get("state"), dict):
        rs.state = _campaign_state_from_dict(run_data["state"])
    else:
        rs.state = None

    # 先把普通字段灌进去（未知字段忽略，缺失字段用默认值）
    for f in fields(CampaignRunState):
        name = f.name
        if name in ("state", "oneshot", "forge", "prisoners", "combo"):
            continue
        if name in run_data:
            try:
                setattr(rs, name, run_data[name])
            except Exception:
                pass

    # 镜像Boss字段（保证类型安全）
    if not isinstance(rs.mirror_snapshot, dict):
        rs.mirror_snapshot = {}
    if not isinstance(rs.mirror_script, list):
        rs.mirror_script = []
    try:
        rs.mirror_last_updated = float(rs.mirror_last_updated or 0.0)
    except Exception:
        rs.mirror_last_updated = 0.0

    # 兵种 key 迁移（旧单字母 -> 新语义化命名）
    if isinstance(rs.units, list):
        rs.units = _migrate_unit_list(rs.units)
    if isinstance(rs.unit_levels, dict):
        rs.unit_levels = _migrate_unit_dict(rs.unit_levels)
    if rs.primary_unit:
        rs.primary_unit = _migrate_unit_key(rs.primary_unit)
    if isinstance(rs.last_battle_enemy_types, list):
        rs.last_battle_enemy_types = _migrate_unit_list(rs.last_battle_enemy_types)
    if isinstance(rs.last_battle_ai_types, list):
        rs.last_battle_ai_types = _migrate_unit_list(rs.last_battle_ai_types)
    if isinstance(rs.prisoner_queue, list):
        rs.prisoner_queue = _migrate_unit_list(rs.prisoner_queue)
    if hasattr(rs, 'forge_selected_unit') and rs.forge_selected_unit:
        rs.forge_selected_unit = _migrate_unit_key(rs.forge_selected_unit)
    if hasattr(rs, 'forge_default_unit') and rs.forge_default_unit:
        rs.forge_default_unit = _migrate_unit_key(rs.forge_default_unit)

    # 嵌套状态
    oneshot = run_data.get("oneshot") or {}
    if isinstance(oneshot, dict):
        rs.oneshot = OneShotState(
            next_shop_free_refresh_disabled=bool(oneshot.get("next_shop_free_refresh_disabled", False)),
            next_shop_free_refresh_bonus=int(oneshot.get("next_shop_free_refresh_bonus", 0) or 0),
            next_shop_price_mult_once=float(oneshot.get("next_shop_price_mult_once", 1.0) or 1.0),
            next_combo_reroll_once=bool(oneshot.get("next_combo_reroll_once", False)),
            next_combo_bias_once=bool(oneshot.get("next_combo_bias_once", False)),
        )

    forge = run_data.get("forge") or {}
    if isinstance(forge, dict):
        rs.forge = ForgeState(
            offense_level_by_unit=_migrate_unit_dict(forge.get("offense_level_by_unit", {}) or {}),
            defense_level_by_unit=_migrate_unit_dict(forge.get("defense_level_by_unit", {}) or {}),
            spawn_count_by_unit=_migrate_unit_dict(forge.get("spawn_count_by_unit", {}) or {}),
            last_target_unit=_migrate_unit_key(forge.get("last_target_unit")) if forge.get("last_target_unit") else None,
            last_direction=forge.get("last_direction"),
        )

    prisoners = run_data.get("prisoners") or {}
    if isinstance(prisoners, dict):
        rs.prisoners = PrisonerMemoryState(
            joined_once=_migrate_unit_dict(prisoners.get("joined_once", {}) or {}),
            executed_once=_migrate_unit_dict(prisoners.get("executed_once", {}) or {}),
        )

    combo = run_data.get("combo") or {}
    if isinstance(combo, dict):
        rs.combo = ComboState(
            selected_cards=list(combo.get("selected_cards", []) or []),
            triggered_shop_once=bool(combo.get("triggered_shop_once", False)),
            triggered_event_once=bool(combo.get("triggered_event_once", False)),
            triggered_elite_once=bool(combo.get("triggered_elite_once", False)),
        )

    # 读档后兜底：确保光标有效
    if rs.state:
        rs.cursor_node_id = rs.state.ensure_cursor() if rs.cursor_node_id is None else rs.cursor_node_id
        rs.state.cursor_node_id = rs.state.ensure_cursor()
    return rs


def save_autosave(run: CampaignRunState) -> None:
    if _env_truthy("SEVENLINES_DISABLE_SAVE"):
        return

    save_dir = default_save_dir()
    save_dir.mkdir(parents=True, exist_ok=True)

    p = autosave_path()
    bak = autosave_backup_path()
    tmp = p.with_suffix(p.suffix + ".tmp")

    # 备份旧档
    try:
        if p.exists():
            shutil.copy2(p, bak)
    except OSError:
        pass

    data = _campaign_run_to_dict(run)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, p)


def load_autosave() -> Optional[CampaignRunState]:
    def _try_load(path: Path) -> Optional[CampaignRunState]:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return _campaign_run_from_dict(data)
        except Exception:
            return None

    p = autosave_path()
    if p.exists():
        rs = _try_load(p)
        if rs is not None:
            return rs

    bak = autosave_backup_path()
    if bak.exists():
        return _try_load(bak)
    return None


