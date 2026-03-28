from __future__ import annotations

import math
import os
import random
from typing import Tuple, List, Dict, Optional

import pygame as pg

from .constants import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    LANE_COUNT,
    BACKGROUND_COLOR,
    LANE_COLOR,
    GRID_COLOR,
    WHITE,
    GREEN,
    RED,
    YELLOW,
    ORANGE,
    BLUE,
    HUD_COLOR,
    HUD_ACCENT,
    lane_y_positions,
    TOP_UI_HEIGHT,
    TOP_PANEL_COLOR,
    BOTTOM_MARGIN,
    BOONS,
    SKILLS,
    SKILL_ORDER,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    CAMPAIGN_NODE_COLORS,
    CAMPAIGN_NODE_DISPLAY,
    CAMPAIGN_BATTLE_NODE_TYPES,
    BLESSINGS,
    SHOP_REFRESH_BASE_COST,
    COMBO_CARDS,
    FORGE_RETARGET_BASE_COST,
    FORGE_RETARGET_PER_LEVEL_COST,
)
from .campaign import CampaignState, MAP_COLUMN_STEP, MAP_LAYER_GAP, MAP_COLUMN_SLOTS
from .game import Game, UNIT_TYPES, ORDER_KEYS, MAX_UNIT_LEVEL, UNIT_LEVEL_STEP
from .font import get_font, get_font_bold
from .localization import tr
from .sprites import get_current_sprite_frame
from .run_state import CampaignRunState

BACKGROUND_SURFACE: Optional[pg.Surface] = None
BACKGROUND_LOAD_ATTEMPTED = False

FORMATION_BG_SURFACE: Optional[pg.Surface] = None
WIKI_BG_SURFACE: Optional[pg.Surface] = None
MAP_BG_SURFACE: Optional[pg.Surface] = None
MAP_BG_HEIGHT: int = 0  # 存储地图背景的完整高度，用于滚动

# 新增：界面专用背景缓存
STORE_BG_SURFACE: Optional[pg.Surface] = None
UPGRADE_BG_SURFACE: Optional[pg.Surface] = None
EVENT_BG_SURFACE: Optional[pg.Surface] = None



def _outline_text(font: pg.font.Font, text: str, color, outline_color=(0, 0, 0), outline_px: int = 2) -> pg.Surface:
    """Render text with an outline for better readability."""
    base = font.render(text, True, color)
    if outline_px <= 0:
        return base
    w, h = base.get_size()
    surf = pg.Surface((w + outline_px * 2, h + outline_px * 2), pg.SRCALPHA)
    outline_surf = font.render(text, True, outline_color)
    for dx in (-outline_px, 0, outline_px):
        for dy in (-outline_px, 0, outline_px):
            if dx == 0 and dy == 0:
                continue
            surf.blit(outline_surf, (dx + outline_px, dy + outline_px))
    surf.blit(base, (outline_px, outline_px))
    return surf


def _blit_text(surface: pg.Surface, font: pg.font.Font, text: str, pos, color=WHITE, outline_px: int = 2):
    surf = _outline_text(font, text, color, (0, 0, 0), outline_px)
    surface.blit(surf, pos)
    return surf


def _wrap_text(font: pg.font.Font, text: str, max_width: int) -> list[str]:
    """中文按字换行即可；用于卡片描述避免挤在一起。"""
    if max_width <= 10:
        return [str(text)] if text else [""]
    # 支持 Translatable 等非字符串对象
    chars = list(str(text or ""))
    lines: list[str] = []
    cur = ""
    for ch in chars:
        test = cur + ch
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]

def _load_specific_background(bg_name: str) -> Optional[pg.Surface]:
    """加载指定名称的背景图片"""
    # 尝试查找背景图目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    assets_dir = os.path.join(os.path.dirname(project_root), "assets", "backgrounds")
    
    candidates_dirs = [
        assets_dir,
        os.path.join(project_root, "assets", "backgrounds"),
        "../assets/backgrounds",
        "assets/backgrounds",
        "d:/Cursor File/sevenlines/assets/backgrounds"
    ]
    
    bg_dir = None
    for d in candidates_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            bg_dir = d
            break
            
    if not bg_dir:
        return None
        
    try:
        bg_path = os.path.join(bg_dir, bg_name)
        if not os.path.exists(bg_path):
            return None
            
        img = pg.image.load(bg_path).convert()
        
        iw, ih = img.get_size()
        scale_w = SCREEN_WIDTH / iw
        scale_h = SCREEN_HEIGHT / ih
        scale = max(scale_w, scale_h)
        
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        if new_w != iw or new_h != ih:
            img = pg.transform.smoothscale(img, (new_w, new_h))
            
        final_surf = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        dest_x = (SCREEN_WIDTH - new_w) // 2
        dest_y = 0
        
        final_surf.blit(img, (dest_x, dest_y))
        
        return final_surf
    except Exception as e:
        print(f"Failed to load background {bg_name}: {e}")
        return None


def _load_cached_background(cache_ref: str, bg_name: str) -> Optional[pg.Surface]:
    """
    通用缓存加载器：按名称加载背景并缓存到全局变量
    cache_ref: 全局变量名字符串，例如 'STORE_BG_SURFACE'
    """
    global STORE_BG_SURFACE, UPGRADE_BG_SURFACE, EVENT_BG_SURFACE
    cache_map = {
        "STORE_BG_SURFACE": "store_bg.png",
        "UPGRADE_BG_SURFACE": "upgrade_bg.png",
        "EVENT_BG_SURFACE": "event_bg.png",
    }
    target_name = bg_name or cache_map.get(cache_ref, "")
    if not target_name:
        return None
    current_val = globals().get(cache_ref)
    if current_val is not None:
        return current_val
    surf = _load_specific_background(target_name)
    globals()[cache_ref] = surf
    return surf

def _load_map_background() -> Optional[pg.Surface]:
    """加载地图背景，使用 min 缩放以确保整张图都能显示，并返回完整高度的图片"""
    global MAP_BG_HEIGHT
    # 尝试查找背景图目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    assets_dir = os.path.join(os.path.dirname(project_root), "assets", "backgrounds")
    
    candidates_dirs = [
        assets_dir,
        os.path.join(project_root, "assets", "backgrounds"),
        "../assets/backgrounds",
        "assets/backgrounds",
        "d:/Cursor File/sevenlines/assets/backgrounds"
    ]
    
    bg_dir = None
    for d in candidates_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            bg_dir = d
            break
            
    if not bg_dir:
        return None
        
    try:
        bg_path = os.path.join(bg_dir, "map_bg.png")
        if not os.path.exists(bg_path):
            return None
            
        img = pg.image.load(bg_path).convert()
        
        iw, ih = img.get_size()
        # 让背景至少覆盖屏幕（宽和高都不小于屏幕），同时保留整张图用于滚动
        scale_w = SCREEN_WIDTH / iw
        scale_h = SCREEN_HEIGHT / ih
        # 选择较大的缩放，使宽、高都 >= 屏幕，滚动时能看到整张图
        scale = max(scale_w, scale_h)
        
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        if new_w != iw or new_h != ih:
            img = pg.transform.smoothscale(img, (new_w, new_h))
        
        # 保存完整高度，用于滚动计算
        MAP_BG_HEIGHT = new_h
        
        # 返回完整尺寸的图片（不裁剪到屏幕大小）
        return img
    except Exception as e:
        print(f"Failed to load map background: {e}")
        return None

def _get_background_surface() -> Optional[pg.Surface]:
    global BACKGROUND_SURFACE, BACKGROUND_LOAD_ATTEMPTED
    if BACKGROUND_SURFACE is not None:
        return BACKGROUND_SURFACE
    
    if BACKGROUND_LOAD_ATTEMPTED:
        return None
        
    BACKGROUND_LOAD_ATTEMPTED = True
    
    # 尝试查找背景图目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    assets_dir = os.path.join(os.path.dirname(project_root), "assets", "backgrounds")
    
    candidates_dirs = [
        assets_dir,
        os.path.join(project_root, "assets", "backgrounds"),
        "../assets/backgrounds",
        "assets/backgrounds",
        "d:/Cursor File/sevenlines/assets/backgrounds"
    ]
    
    bg_dir = None
    for d in candidates_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            bg_dir = d
            break
            
    if not bg_dir:
        return None
        
    try:
        # 获取所有图片文件
        files = []
        try:
            for f in os.listdir(bg_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                    if not f.startswith("Baseport") and "menu_bg" not in f:
                        files.append(os.path.join(bg_dir, f))
        except Exception:
            pass
            
        if not files:
            return None
            
        # 强制使用 background_iron.png 作为战斗背景（如果存在）
        bg_name_override = "background_iron.png"
        iron_path = None
        for f in files:
             if bg_name_override in os.path.basename(f):
                 iron_path = f
                 break
        
        if iron_path:
            path = iron_path
        else:
            # 原有逻辑回退
            path = None
            for f in files:
                if "battle_bg" in os.path.basename(f):
                    path = f
                    break
            else:
                # 避免随机选中 icon_ 开头的图标文件（它们也在 backgrounds 目录下）
                valid_files = [f for f in files if not os.path.basename(f).startswith("icon_")]
                if valid_files:
                    path = random.choice(valid_files)
                else:
                     path = random.choice(files)
            
        img = pg.image.load(path).convert()
        
        iw, ih = img.get_size()
        scale_w = SCREEN_WIDTH / iw
        scale_h = SCREEN_HEIGHT / ih
        scale = max(scale_w, scale_h)
        
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        if new_w != iw or new_h != ih:
            img = pg.transform.smoothscale(img, (new_w, new_h))
            
        darkener = pg.Surface((new_w, new_h))
        darkener.fill((40, 40, 40))
        img.blit(darkener, (0, 0), special_flags=pg.BLEND_RGB_SUB)
            
        final_surf = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        dest_x = (SCREEN_WIDTH - new_w) // 2
        dest_y = 0
        
        final_surf.blit(img, (dest_x, dest_y))
        
        hud_gradient = pg.Surface((SCREEN_WIDTH, TOP_UI_HEIGHT + 40), pg.SRCALPHA)
        for y in range(TOP_UI_HEIGHT + 40):
            alpha = int(200 * (1.0 - y / (TOP_UI_HEIGHT + 40)))
            pg.draw.line(hud_gradient, (0, 0, 0, alpha), (0, y), (SCREEN_WIDTH, y))
        final_surf.blit(hud_gradient, (0, 0))
        
        BACKGROUND_SURFACE = final_surf
        return BACKGROUND_SURFACE
    except Exception as e:
        print(f"Failed to load background: {e}")
        return None

UNIT_BOOK: Dict[str, Dict[str, str]] = {
    "warrior": {
        "short": "均衡近战，顶线之选。",
        "role": "均衡前排",
        "intro": "费用适中，可在敌人压线时顶住并配合远程火力稳固战局。",
    },
    "shield": {
        "short": "高血量肉盾，护队友。",
        "role": "重盾防线",
        "intro": "极高耐久承担第一波火力，适合搭配治疗或鼓手组成铁桶防线。",
    },
    "maul": {
        "short": "高速突袭，近战眩晕。",
        "role": "高爆刺击",
        "intro": "冲到前排后眩晕近战目标，快速撕裂薄弱防线，需要防远程火力。",
    },
    "berserker": {
        "short": "近战范围伤害。",
        "role": "踏入式清线",
        "intro": "挥击带范围伤害，适合清理成群敌军，需护卫防止被集火。",
    },
    "priest": {
        "short": "远程治疗，不输出。",
        "role": "后排支援",
        "intro": "持续给同线友军补血，保持前排续航，是拖住长线战斗的核心。",
    },
    "archer": {
        "short": "廉价远程火力。",
        "role": "基础输出",
        "intro": "射程远、费用低，适合作为量产火力点，搭配前排稳定推进。",
    },
    "mage": {
        "short": "远程爆破，AOE 输出。",
        "role": "爆发法系",
        "intro": "高额范围魔法伤害，用于清理密集敌阵，需要前排保护避免被击杀。",
    },
    "rhino": {
        "short": "冲撞肉盾，附带击退。",
        "role": "重装推进",
        "intro": "冲锋附带范围伤害与击退，适合撕开战线，但需要支援避免被风筝。",
    },
    "assassin": {
        "short": "直扑后排，刺杀远程。",
        "role": "背刺专家",
        "intro": "无视小兵直取远程/辅助，清除敌方关键火力，需避开厚重防线。",
    },
    "interceptor": {
        "short": "拦截投射，反弹火力。",
        "role": "投射屏障",
        "intro": "拦截并反弹敌方炮火，克制远程阵容，为己方推进创造窗口。",
    },
    "drummer": {
        "short": "光环加速与攻速。",
        "role": "团队增益",
        "intro": "为同线友军提供移速和攻速增益，是远程火力与轻骑兵的最佳拍档。",
    },
    "spearman": {
        "short": "克制冲锋，附带打断。",
        "role": "反骑兵",
        "intro": "长矛在命中冲锋单位时造成额外伤害并打断，对抗轻骑和犀牛很有效。",
    },
    "frost_archer": {
        "short": "减速叠层，触发眩晕。",
        "role": "冰控射手",
        "intro": "箭矢叠加减速并在满层眩晕一次，拖慢厚重敌军的推进节奏。",
    },
    "exploder": {
        "short": "近身自爆，清扫护卫。",
        "role": "削线炸弹",
        "intro": "接近目标后死亡爆炸，适合与前排混战时交换，注意防止被远程拆掉。",
    },
    "light_cavalry": {
        "short": "高速冲锋，击退成片。",
        "role": "机动力量",
        "intro": "首冲造成大范围击退，快速打散敌阵，但怕控制与矛兵。",
    },
}


def _draw_dashed_line(
    surface: pg.Surface,
    color: tuple[int, int, int],
    start: tuple[float, float],
    end: tuple[float, float],
    width: int = 3,
    dash_length: float = 28.0,
    gap_length: float = 18.0,
):
    start_v = pg.Vector2(start)
    end_v = pg.Vector2(end)
    diff = end_v - start_v
    length = diff.length()
    if length <= 0.0:
        return
    direction = diff.normalize()
    travelled = 0.0
    seg_start = start_v
    while travelled < length:
        seg_len = min(dash_length, length - travelled)
        seg_end = seg_start + direction * seg_len
        pg.draw.line(surface, color, seg_start, seg_end, width)
        travelled += seg_len + gap_length
        seg_start = seg_end + direction * gap_length


_BASE_SPRITE_CACHE: dict[tuple[str, int, int, int], pg.Surface] = {}

_NODE_ICON_CACHE: dict[tuple[str, int, int], pg.Surface] = {}

# 全局缩放系数：地图节点图标整体放大倍数
MAP_ICON_SCALE = 2.0

# 地图节点文字与图标的距离/字号
MAP_ICON_LABEL_OFFSET = 10
MAP_ICON_LABEL_FONT_SIZE = 20

def load_node_icon(node_type: str, width: int, height: int) -> Optional[pg.Surface]:
    """
    加载节点图标
    """
    cache_key = (node_type, width, height)
    if cache_key in _NODE_ICON_CACHE:
        return _NODE_ICON_CACHE[cache_key]
    
    filename_map = {
        "combat": "icon_battle.png",
        "elite": "icon_superbattle.png",
        "shop": "icon_store.png",
        "rest": "icon_recover.png",
        "boss": "icon_boss.png",
        "event": "icon_event.png"
    }
    
    filename = filename_map.get(node_type)
    if not filename:
        return None

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        candidates = [
            os.path.join(project_root, "assets", "backgrounds", filename),
            os.path.join(project_root, "..", "assets", "backgrounds", filename),
            os.path.join(os.path.dirname(project_root), "sevenlines", "assets", "backgrounds", filename),
            f"sevenlines/assets/backgrounds/{filename}",
            f"assets/backgrounds/{filename}",
            "d:/Cursor File/sevenlines/assets/backgrounds/" + filename,
        ]

        bg_path = None
        for path in candidates:
            if os.path.exists(path):
                bg_path = path
                break

        if not bg_path:
            return None

        img = pg.image.load(bg_path).convert_alpha()
        
        # 缩放到目标尺寸
        img = pg.transform.smoothscale(img, (width, height))
        
        _NODE_ICON_CACHE[cache_key] = img
        return img
    except Exception as e:
        print(f"Failed to load node icon {filename}: {e}")
        return None

def load_base_sprite(state: str, frame_idx: int, target_w: int, target_h: int) -> Optional[pg.Surface]:
    """
    加载基地精灵图
    state: "A" | "B" | "C" | "D"
    frame_idx: 0-3
    """
    cache_key = (state, frame_idx, target_w, target_h)
    if cache_key in _BASE_SPRITE_CACHE:
        return _BASE_SPRITE_CACHE[cache_key]

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)

        filename = f"Baseport{state}_{frame_idx}.png"

        candidates = [
            os.path.join(project_root, "assets", "backgrounds", filename),
            os.path.join(project_root, "..", "assets", "backgrounds", filename),
            os.path.join(os.path.dirname(project_root), "sevenlines", "assets", "backgrounds", filename),
            f"sevenlines/assets/backgrounds/{filename}",
            f"assets/backgrounds/{filename}",
            "d:/Cursor File/sevenlines/assets/backgrounds/" + filename,
        ]

        bg_path = None
        for path in candidates:
            if os.path.exists(path):
                bg_path = path
                break

        if not bg_path:
            return None

        img = pg.image.load(bg_path).convert_alpha()

        # 智能缩放 (Aspect Fit): 缩放到能放入 target_w/h 且保持比例
        iw, ih = img.get_size()
        scale = min(target_w / iw, target_h / ih)

        # 如果图片本身比目标小，可能不需要放大或者按需放大
        new_w = int(iw * scale)
        new_h = int(ih * scale)

        if new_w != iw or new_h != ih:
            img = pg.transform.smoothscale(img, (new_w, new_h))

        _BASE_SPRITE_CACHE[cache_key] = img
        return img
    except Exception as e:
        print(f"Failed to load base sprite {state}_{frame_idx}: {e}")
        return None

def draw_lane_base(
    surface: pg.Surface,
    x: int,
    y: int,
    hp: float,
    max_hp: float,
    color: Tuple[int, int, int],
    highlight: bool = False,
    selected: bool = False,
):
    from .constants import LANE_BASE_BAR_W, LANE_BASE_BAR_H
    
    # 基地精灵图尺寸（缩小为之前的一半）
    base_w = 75
    base_h = 75  # 方形素材
    
    # 确定状态
    if hp <= 0:
        state = "D"
    elif hp <= max_hp * 0.5:
        state = "C"
    elif hp < max_hp * 0.99: # 给点容差
        state = "B"
    else:
        state = "A"
        
    # 动画帧
    if state == "D":
        # 基地被摧毁时，固定显示 BaseportD_3.png，不播放动画
        frame_idx = 3
    else:
        # 其他状态保持原有动画 (每秒 8 帧，4 帧循环)
        ticks = pg.time.get_ticks()
        frame_idx = (ticks // 125) % 4
    
    base_img = load_base_sprite(state, frame_idx, base_w, base_h)
    
    if base_img:
        # 绘制精灵图
        from .constants import MAGENTA, RED
        is_right = (color == MAGENTA or color == RED)

        # 使用副本避免污染缓存
        draw_img = base_img.copy()

        # 我方原汁原味；敌方仅镜像 + 轻度色偏，不叠加半透明矩形
        if is_right:
            draw_img = pg.transform.flip(draw_img, True, False)
            # 加红提升辨识度；可再调高 R 以更强 (70,0,0)
            draw_img.fill((56, 0, 0), special_flags=pg.BLEND_RGB_ADD)
            # 适度压暗蓝绿，防止过亮；如需更亮提高 G/B 或移除此行
            draw_img.fill((255, 228, 228), special_flags=pg.BLEND_RGB_MULT)

        base_rect = draw_img.get_rect(center=(x, y))
        surface.blit(draw_img, base_rect)
        
        # 高亮/选中效果 (在精灵图外围)
        if selected:
            glow_size = 6
            pg.draw.rect(surface, (100, 200, 255), base_rect.inflate(glow_size, glow_size), 2, border_radius=4)
        if highlight:
            glow_size = 4
            pg.draw.rect(surface, (255, 50, 50), base_rect.inflate(glow_size, glow_size), 3, border_radius=4)
            
    else:
        # 回退到旧的矩形绘制逻辑
        w = LANE_BASE_BAR_W
        h = LANE_BASE_BAR_H
        
        if selected:
            glow_size = 20
            sel_surf = pg.Surface((w + glow_size, h + glow_size), pg.SRCALPHA)
            pulse = 0.7 + 0.3 * math.sin(pg.time.get_ticks() / 200.0)
            alpha = int(150 * pulse)
            pg.draw.rect(sel_surf, (100, 200, 255, alpha), sel_surf.get_rect(), border_radius=8)
            sel_rect = sel_surf.get_rect(center=(x, y))
            surface.blit(sel_surf, sel_rect.topleft)

        if highlight:
            glow_surf = pg.Surface((w + 12, h + 12), pg.SRCALPHA)
            pulse = 0.55 + 0.45 * math.sin(pg.time.get_ticks() / 150.0)
            alpha = int(120 + 80 * pulse)
            pg.draw.rect(glow_surf, (255, 80, 80, alpha), glow_surf.get_rect(), border_radius=6)
            glow_rect = glow_surf.get_rect(center=(x, y))
            surface.blit(glow_surf, glow_rect.topleft)
        base_color = RED if highlight else color
        border_width = 3 if highlight else 2
        pg.draw.rect(surface, base_color, (x - w // 2, y - h // 2, w, h), width=border_width)
        # HP 填充（自底向上）
        ratio = max(0.0, min(1.0, hp / max_hp))
        inner_w = w - 4
        inner_h = int((h - 4) * ratio)
        if inner_h > 0:
            pg.draw.rect(surface, base_color, (x - w // 2 + 2, y + h // 2 - 2 - inner_h, inner_w, inner_h))



def draw_lanes(surface: pg.Surface, font: pg.font.Font, game: Game | None = None):
    ys = list(getattr(game, "lane_y", None) or lane_y_positions())
    lane_count = len(ys)
    if lane_count <= 0:
        return

    # 简单UI区分：淡色条带 + “1 侧翼/2 持久/3 爆发/4 中线 …”
    top_start = TOP_UI_HEIGHT + 20
    bottom_end = SCREEN_HEIGHT - BOTTOM_MARGIN
    group_list = list(getattr(game, "lane_group", []) or [])

    def _group_of(i: int) -> str:
        if 0 <= i < len(group_list):
            return str(group_list[i])
        # 兜底按 index 推断（默认 7线）
        if i in (0, 6):
            return "flank"
        if i in (1, 5):
            return "tank"
        if i in (2, 4):
            return "burst"
        return "mid"

    group_name = {"flank": "侧翼", "tank": "持久", "burst": "爆发", "mid": "中线"}
    group_color = {
        "flank": (90, 170, 255),
        "tank": (110, 220, 150),
        "burst": (255, 120, 90),
        "mid": (90, 90, 110),
    }

    for i, y in enumerate(ys):
        band_top = top_start if i == 0 else int((ys[i - 1] + ys[i]) / 2)
        band_bottom = bottom_end if i == lane_count - 1 else int((ys[i] + ys[i + 1]) / 2)
        g = _group_of(i)
        rgb = group_color.get(g, (90, 90, 110))
        overlay = pg.Surface((SCREEN_WIDTH, max(1, band_bottom - band_top)), pg.SRCALPHA)
        overlay.fill((*rgb, 26))  # 低透明度，不抢画面
        surface.blit(overlay, (0, band_top))

        # 左侧编号与标签
        tag = group_name.get(g, g)
        label = font.render(f"{i + 1} {tag}", True, GRID_COLOR)
        surface.blit(label, (18, y - 10))


def draw_unit(
    surface: pg.Surface,
    x: float,
    y: int,
    shape: str,
    color: Tuple[int, int, int],
    r: int,
    facing_left: bool,
    ut=None,
    unit=None,
):
    # 程序化动画效果
    original_y = y
    original_r = r
    animation_offset_x = 0.0
    
    animation_state = "idle"
    animation_timer = 0.0
    
    if unit is not None:
        animation_state = getattr(unit, 'animation_state', 'idle')
        animation_timer = getattr(unit, 'animation_timer', 0.0)
        
        if animation_state == "walk":
            # 走路时上下浮动
            walk_offset = math.sin(animation_timer * 8) * 2
            y = int(y + walk_offset)
            # 轻微左右摆动（模拟步伐）
            animation_offset_x = math.sin(animation_timer * 12) * 0.5
        elif animation_state == "attack":
            # 攻击时轻微放大
            attack_scale = 1.0 + 0.15 * (1 - min(1.0, animation_timer / 0.3))
            r = int(r * attack_scale)
            # 攻击时向前突进
            dir_sign = -1 if facing_left else 1
            animation_offset_x = dir_sign * 2 * (1 - min(1.0, animation_timer / 0.3))
        elif animation_state == "idle":
            # 待机时轻微呼吸效果
            idle_scale = 1.0 + 0.05 * math.sin(animation_timer * 2)
            r = int(r * idle_scale)
            # 轻微上下浮动
            idle_offset = math.sin(animation_timer * 1.5) * 1
            y = int(y + idle_offset)
    
    # 应用动画偏移
    x = x + animation_offset_x
    
    # 尝试加载精灵图
    sprite_image = None
    if ut is not None:
        unit_key = getattr(ut, "key", "") or str(getattr(ut, "name", ""))
        if unit_key:
            # 对于攻击动画，现在 animation_timer 已经是正向计时（time_since_last_attack）
            sprite_timer = animation_timer
            
            # === 使用缓存加载基础尺寸 ===
            # 这里的 r 是单位半径，乘以 2 就是直径（基础大小）
            base_size = int(r * 2)
            
            sprite_image = get_current_sprite_frame(
                unit_key,
                animation_state,
                sprite_timer,
                fps=8.0,  # 动画播放速度
                target_size=(base_size, base_size) # 传入目标尺寸，触发缓存缩放
            )

    # === 绘制光环特效（表示 Buff 范围） ===
    # 仅在战斗中显示 (unit is not None)，且仅针对 Buffer 单位
    if unit is not None and ut is not None and getattr(ut, 'is_buffer', False):
        aura_radius = getattr(ut, 'aura_radius', 0.0)
        if aura_radius > 0:
            # 椭圆尺寸：宽度=2*半径，高度固定为 50 (适应单兵线)
            rx = int(aura_radius)
            ry = 25 # 垂直半径
            
            aura_w = rx * 2
            aura_h = ry * 2
            
            # 创建临时 Surface
            aura_surf = pg.Surface((aura_w, aura_h), pg.SRCALPHA)
            
            # 呼吸效果
            pulse = 0.5 + 0.5 * math.sin(pg.time.get_ticks() / 800.0)
            fill_alpha = int(15 + 15 * pulse)
            border_alpha = int(60 + 40 * pulse)
            
            rect_local = pg.Rect(0, 0, aura_w, aura_h)
            
            # 绘制填充
            pg.draw.ellipse(aura_surf, (100, 220, 255, fill_alpha), rect_local)
            # 绘制边缘
            pg.draw.ellipse(aura_surf, (100, 220, 255, border_alpha), rect_local, 2)
            
            # 绘制到主画面 (居中)
            aura_rect = aura_surf.get_rect(center=(int(x), int(y)))
            surface.blit(aura_surf, aura_rect)
    
    is_stealthed = False
    if unit is not None:
        is_stealthed = bool(getattr(unit, "is_stealthed_dynamic", False))
    elif ut is not None:
        is_stealthed = bool(getattr(ut, 'is_stealthed', False))
    if ut and getattr(ut, 'is_stealthed', False):
        is_stealthed = True
    if is_stealthed:
        color = tuple(min(255, int(c * 0.55 + 90)) for c in color)
    
    # 如果有精灵图，优先使用精灵图
    if sprite_image is not None:
        # 计算最终渲染尺寸（包含动画导致的尺寸变化，如呼吸、攻击放大）
        final_size = int(r * 2)
        
        # 获取当前（已缓存的缩小版）图片的尺寸
        cached_w, cached_h = sprite_image.get_size()
        
        # 只有当呼吸/攻击特效导致尺寸微调时（例如 30 -> 32），才进行额外缩放
        # 这里用 scale 而不是 smoothscale，因为微小变化看不出锯齿，且性能极快
        if cached_w != final_size or cached_h != final_size:
            sprite_image = pg.transform.scale(sprite_image, (final_size, final_size))
        
        # 如果需要翻转（面向左边）
        if facing_left:
            sprite_image = pg.transform.flip(sprite_image, True, False)
        
        # 隐身效果：降低透明度
        if is_stealthed:
            # 注意：直接 set_alpha 需要 copy 或者 convert_alpha 的 surface
            # 已经在加载时 convert_alpha()
            # 为了不修改缓存中的原始 Surface，这里必须 copy
            sprite_image = sprite_image.copy()
            sprite_image.set_alpha(int(255 * 0.55))
        
        # 绘制精灵图（中心对齐）
        sprite_rect = sprite_image.get_rect(center=(int(x), int(y)))
        surface.blit(sprite_image, sprite_rect)
    elif shape == "circle":
        pg.draw.circle(surface, color, (int(x), int(y)), r)
    elif shape == "square":
        side = r * 2
        pg.draw.rect(surface, color, (int(x - r), int(y - r), side, side))
    elif shape == "triangle":
        # 朝向：左/右
        if facing_left:
            pts = [(x + r, y), (x - r, y - r), (x - r, y + r)]
        else:
            pts = [(x - r, y), (x + r, y - r), (x + r, y + r)]
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])
    elif shape == "hexagon":
        pts = []
        for i in range(6):
            ang = math.pi / 3 * i
            pts.append((x + r * math.cos(ang), y + r * math.sin(ang)))
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])
    elif shape == "pentagon":
        pts = []
        for i in range(5):
            ang = -math.pi / 2 + (2 * math.pi / 5) * i
            pts.append((x + r * math.cos(ang), y + r * math.sin(ang)))
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])
    elif shape == "diamond":
        pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])
    elif shape == "star":
        pts = []
        outer = r
        inner = r * 0.45
        for i in range(10):
            ang = -math.pi / 2 + (math.pi / 5) * i
            rad = outer if i % 2 == 0 else inner
            pts.append((x + rad * math.cos(ang), y + rad * math.sin(ang)))
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])
    elif shape == "octagon":
        pts = []
        for i in range(8):
            ang = -math.pi / 8 + (2 * math.pi / 8) * i
            pts.append((x + r * math.cos(ang), y + r * math.sin(ang)))
        pg.draw.polygon(surface, color, [(int(px), int(py)) for (px, py) in pts])

    # 叠加标记：根据单位特性自动绘制
    if not ut:
        return
    
    # 仅当没有精灵图时，才绘制几何辅助标记
    if sprite_image is None:
        oc = WHITE
        dir_sign = -1 if facing_left else 1

        # 远程标记：前方短线
        if getattr(ut, 'is_ranged', False):
            sx = int(x + dir_sign * (r - 2))
            ex = int(x + dir_sign * (r + 6))
            pg.draw.line(surface, oc, (sx, int(y)), (ex, int(y)), 2)

        # AOE 标记：四个小点
        if getattr(ut, 'is_aoe', False):
            # 狂战士（Hexagon/berserker）特例：不绘制AOE点
            is_berserker = (getattr(ut, "key", "") == "berserker")
            if not is_berserker:
                d = r + 4
                for (dx, dy) in ((0, -d), (0, d), (-d, 0), (d, 0)):
                    pg.draw.circle(surface, oc, (int(x + dx), int(y + dy)), 2)

        # 奶妈：中央十字
        if getattr(ut, 'is_healer', False):
            pg.draw.line(surface, oc, (int(x - r // 2), int(y)), (int(x + r // 2), int(y)), 2)
            pg.draw.line(surface, oc, (int(x), int(y - r // 2)), (int(x), int(y + r // 2)), 2)

        # 鼓手/光环：外圈细环
        if getattr(ut, 'is_buffer', False):
            pg.draw.circle(surface, oc, (int(x), int(y)), r + 3, 1)

        # 冲锋：朝向箭头
        if getattr(ut, 'is_charger', False):
            fx = int(x + dir_sign * (r + 2))
            pg.draw.line(surface, oc, (fx, int(y)), (int(fx - dir_sign * 6), int(y - 4)), 2)
            pg.draw.line(surface, oc, (fx, int(y)), (int(fx - dir_sign * 6), int(y + 4)), 2)

        # 破箭/拦截：前方小弧
        if getattr(ut, 'intercept_radius', 0.0) > 0.0:
            arc_r = 4
            rect = pg.Rect(int(x + dir_sign * (r + 6) - arc_r), int(y - arc_r), arc_r * 2, arc_r * 2)
            start_ang = math.pi * (0.0 if facing_left else 1.0)
            end_ang = math.pi * (1.0 if facing_left else 2.0)
            pg.draw.arc(surface, oc, rect, start_ang, end_ang, 2)

        # 刺客/优先强攻：小 V
        if getattr(ut, 'prioritize_high_damage', False):
            pg.draw.line(surface, oc, (int(x - 4), int(y - 2)), (int(x), int(y + 2)), 2)
            pg.draw.line(surface, oc, (int(x), int(y + 2)), (int(x + 4), int(y - 2)), 2)

        # 分裂体：竖线
        if getattr(ut, 'split_on_death', False):
            pg.draw.line(surface, oc, (int(x), int(y - r)), (int(x), int(y + r)), 2)

    oc = WHITE # 重置 oc 供下方使用（如果没进上面的 if）

    ability_flags: List[str] = []
    if getattr(ut, 'invulnerable', False):
        ability_flags.append("invuln")
    if getattr(ut, 'reflect_all_damage', False) or getattr(ut, 'passive_reflect_ratio', 0.0) > 0.0:
        ability_flags.append("reflect")
    if getattr(ut, 'lifesteal_ratio', 0.0) > 0.0:
        ability_flags.append("lifesteal")
    if getattr(ut, 'projectile_pierce', 0) > 0:
        ability_flags.append("pierce")
    if getattr(ut, 'ignite_duration', 0.0) > 0.0 and getattr(ut, 'ignite_dps', 0.0) > 0.0:
        ability_flags.append("ignite")
    if getattr(ut, 'is_stealthed', False) or getattr(ut, 'stealth_in_own_half', False):
        ability_flags.append("stealth")
    if getattr(ut, 'control_immune', False):
        ability_flags.append("control")

    if ability_flags:
        marker_r = 4
        gap = marker_r * 2 + 4
        start_x = int(x - (len(ability_flags) - 1) * gap / 2)
        base_y = int(y + r + 8)
        for idx, flag in enumerate(ability_flags):
            cx = start_x + idx * gap
            cy = base_y
            if flag == "invuln":
                pg.draw.circle(surface, oc, (cx, cy), marker_r, 1)
            elif flag == "reflect":
                pg.draw.line(surface, oc, (cx - marker_r, cy), (cx + marker_r - 2, cy), 1)
                arrow = [
                    (cx + marker_r - 2, cy - 3),
                    (cx + marker_r + 2, cy),
                    (cx + marker_r - 2, cy + 3),
                ]
                pg.draw.polygon(surface, oc, arrow)
            elif flag == "lifesteal":
                pg.draw.line(surface, oc, (cx, cy - marker_r), (cx, cy + marker_r), 1)
                pg.draw.line(surface, oc, (cx - marker_r, cy), (cx + marker_r, cy), 1)
            elif flag == "pierce":
                pg.draw.line(surface, oc, (cx - marker_r, cy - 1), (cx + marker_r, cy - 1), 1)
                pg.draw.line(surface, oc, (cx - marker_r, cy + 1), (cx + marker_r, cy + 1), 1)
            elif flag == "ignite":
                tri = [
                    (cx, cy - marker_r),
                    (cx + marker_r, cy + marker_r),
                    (cx - marker_r, cy + marker_r),
                ]
                pg.draw.polygon(surface, oc, tri, 1)
            elif flag == "stealth":
                diamond = [
                    (cx, cy - marker_r),
                    (cx + marker_r, cy),
                    (cx, cy + marker_r),
                    (cx - marker_r, cy),
                ]
                pg.draw.polygon(surface, oc, diamond, 1)
            elif flag == "control":
                pg.draw.line(surface, oc, (cx - marker_r, cy - marker_r), (cx + marker_r, cy + marker_r), 1)
                pg.draw.line(surface, oc, (cx - marker_r, cy + marker_r), (cx + marker_r, cy - marker_r), 1)


def draw_projectile(surface: pg.Surface, x: float, y: int, color: Tuple[int, int, int], shape: str = "default"):
    if shape == "arrow":
        # 箭矢：画一条线，带一个小箭头
        # 假设都向右飞（简化），如果需要双向，需要把 velocity 传进来，或者根据 side 判断
        # 这里为了简化，直接画水平线。更好的做法是根据 projectile 的 side 翻转。
        # 但 draw_projectile 接口没传 side，我们只能画通用样式或者稍微改下调用
        # 不过，调用方通常已经根据 side 筛选了绘制逻辑，这里主要画形状
        
        # 为了更炫酷，画一条发光的线
        length = 14
        width = 2
        # 核心白线
        pg.draw.line(surface, WHITE, (x - length//2, y), (x + length//2, y), width)
        # 外发光（半透明）
        glow_surf = pg.Surface((length + 8, width + 8), pg.SRCALPHA)
        pg.draw.line(glow_surf, (*color, 100), (4, 4 + width//2), (4 + length, 4 + width//2), width + 4)
        surface.blit(glow_surf, (x - length//2 - 4, y - 4 - width//2))
        
    elif shape == "orb":
        # 法球：脉冲圆形
        pulse = 0.8 + 0.2 * math.sin(pg.time.get_ticks() / 100.0)
        radius = 5 * pulse
        
        # 核心
        pg.draw.circle(surface, WHITE, (int(x), int(y)), int(radius * 0.6))
        # 辉光
        glow_radius = int(radius * 1.8)
        glow_surf = pg.Surface((glow_radius * 2, glow_radius * 2), pg.SRCALPHA)
        pg.draw.circle(glow_surf, (*color, 120), (glow_radius, glow_radius), glow_radius)
        surface.blit(glow_surf, (int(x) - glow_radius, int(y) - glow_radius))
        
    else:
        # 默认圆形
        pg.draw.circle(surface, color, (int(x), int(y)), 4)


def draw_particles(surface: pg.Surface, game: Game):
    for p in game.particles:
        # 随时间淡出
        life_ratio = 1.0 - (p.timer / p.duration)
        if life_ratio <= 0:
            continue
        
        alpha = int(255 * life_ratio)
        
        # 根据形状绘制
        if p.shape == "line":
            # 线条粒子（火花/碎片）
            # 根据速度方向拉伸，如果没有速度则随机方向或点
            length = max(2, p.radius * 3)
            angle = math.atan2(p.vy, p.vx) if (p.vx != 0 or p.vy != 0) else 0
            end_x = p.x - math.cos(angle) * length
            end_y = p.y - math.sin(angle) * length
            
            color_with_alpha = (*p.color, alpha)
            # Pygame draw.line 不支持 alpha，需要 Surface
            # 优化：小粒子直接画实色，或者创建小 Surface
            # 为了性能，这里用实色模拟，或者简单的淡出颜色（变黑）
            # 使用 blend 模式或者创建 temp surface
            
            if alpha < 255:
                # 简单的颜色衰减模拟透明度（针对黑色背景有效）
                draw_color = tuple(int(c * life_ratio) for c in p.color)
            else:
                draw_color = p.color
                
            pg.draw.line(surface, draw_color, (p.x, p.y), (end_x, end_y), max(1, int(p.radius)))
            
        elif p.shape == "ring":
            # 冲击波（空心圆）
            radius = int(p.radius)
            if radius <= 0: continue
            width = getattr(p, 'width', 2)
            
            # 创建带 alpha 的 Surface
            surf_size = radius * 2 + width * 2
            surf = pg.Surface((surf_size, surf_size), pg.SRCALPHA)
            center = surf_size // 2
            
            pg.draw.circle(surf, (*p.color, alpha), (center, center), radius, width)
            surface.blit(surf, (int(p.x - center), int(p.y - center)))
            
        elif p.shape == "square":
            # 方形粒子（碎片/像素）
            size = int(p.radius * 2)
            if size <= 0: continue
            surf = pg.Surface((size, size), pg.SRCALPHA)
            surf.fill((*p.color, alpha))
            # 简单的旋转效果? 暂时不加旋转以保性能
            surface.blit(surf, (int(p.x - size//2), int(p.y - size//2)))
            
        else:
            # 默认圆形光晕
            radius = int(p.radius)
            if radius <= 0: continue
                
            surf = pg.Surface((radius * 2, radius * 2), pg.SRCALPHA)
            color_with_alpha = (*p.color, alpha)
            pg.draw.circle(surf, color_with_alpha, (radius, radius), radius)
            
            # 绘制核心（更亮，更小）
            core_radius = max(1, int(radius * 0.6))
            core_alpha = int(255 * life_ratio * life_ratio) # 核心淡出更快
            core_color = (255, 255, 255, core_alpha)
            pg.draw.circle(surf, core_color, (radius, radius), core_radius)
            
            surface.blit(surf, (int(p.x - radius), int(p.y - radius)))


def draw_hud(surface: pg.Surface, font: pg.font.Font, game: Game, layout: dict):
    # 第一行：资源与兵种横向排布
    res_text = f"资源 {int(game.left.resource)}"
    res_surf = get_font(font.get_height()).render(res_text, True, HUD_COLOR)
    row_y = layout.get("palette_row_y", [])
    if row_y:
        res_y = int(row_y[0] - res_surf.get_height() / 2)
    else:
        res_y = 12
    surface.blit(res_surf, (20, res_y))
    
    # 显示战斗时间（右上角）
    battle_time = getattr(game, 'battle_time', 0.0)
    minutes = int(battle_time // 60)
    seconds = int(battle_time % 60)
    time_text = f"时间 {minutes:02d}:{seconds:02d}"
    time_surf = get_font(font.get_height()).render(time_text, True, HUD_COLOR)
    surface.blit(time_surf, (SCREEN_WIDTH - time_surf.get_width() - 20, res_y))


def _calc_palette_rows(game: Game) -> int:
    keys = getattr(game, 'player_order_keys', ORDER_KEYS)
    start_x = 260
    slot_w = 140
    max_per_row = max(1, (SCREEN_WIDTH - start_x - 60) // slot_w)
    return 1 if len(keys) <= max_per_row else 2


def _top_panel_layout(game: Game) -> dict:
    card_height = 52
    row_gap = 16
    top_margin = 24
    rows = _calc_palette_rows(game)
    row_y: list[int] = []
    if rows > 0:
        first_center = top_margin + card_height // 2
        for idx in range(rows):
            row_y.append(int(first_center + idx * (card_height + row_gap)))
        palette_bottom = row_y[-1] + card_height // 2
    else:
        palette_bottom = top_margin + card_height
    skill_y = palette_bottom + 18
    boon_y = skill_y + 32
    return {
        "palette_rows": rows,
        "palette_row_y": row_y,
        "palette_bottom": palette_bottom,
        "skill_y": skill_y,
        "boon_y": boon_y,
    }


def _draw_skill_row(surface: pg.Surface, font: pg.font.Font, game: Game, layout: dict):
    slot_labels = ["Q", "W", "E"]
    skills = list(getattr(game, 'left_skill_types', []) or [])
    costs = getattr(game, 'left_skill_costs', {}) or {}
    kill_resource = int(getattr(game, 'left_kill_resource', 0))
    infinite = getattr(game, 'left_infinite_skill', False)

    tokens = []
    for idx, slot_label in enumerate(slot_labels):
        if idx < len(skills):
            key = skills[idx]
            cfg = SKILLS.get(key, {})
            cost = costs.get(key, cfg.get("cost", 0))
            ready = infinite or kill_resource >= cost
            status = "就绪" if ready else "不足"
            tokens.append(f"{slot_label}:{cfg.get('name', key)}({cost}杀·{status})")
        else:
            tokens.append(f"{slot_label}:未配置")

    if tokens:
        skill_line = "  |  ".join(tokens)
        skill_text = f"特殊技能: {skill_line}"
    else:
        skill_text = "特殊技能: 未携带"
    kill_text = f"击杀数: {'∞' if infinite else kill_resource}"

    skill_font = get_font(font.get_height())
    surf = skill_font.render(skill_text, True, HUD_ACCENT)
    skill_y = layout.get("skill_y", 88)
    surface.blit(surf, (20, skill_y))

    kill_font = get_font(max(14, font.get_height() - 2))
    kill_surf = kill_font.render(kill_text, True, HUD_COLOR)
    kill_x = SCREEN_WIDTH - kill_surf.get_width() - 20
    kill_y = skill_y + max(0, (surf.get_height() - kill_surf.get_height()) // 2)
    surface.blit(kill_surf, (kill_x, kill_y))


def _draw_boons_row(surface: pg.Surface, font: pg.font.Font, game: Game, layout: dict):
    # 提取祝福、Combo 和 原有 Boon
    tokens = []
    
    # 1) 祝福 (Blessing)
    active_blessing = game.modifiers.get("active_blessing")
    if active_blessing:
        cfg = BLESSINGS.get(active_blessing, {"name": active_blessing})
        tokens.append(f"★{cfg.get('name', active_blessing)}")

    # 2) Combo
    active_combos = game.modifiers.get("active_combos", [])
    for cid in active_combos:
        cfg = COMBO_CARDS.get(cid, {"name": cid})
        tokens.append(f"◆{cfg.get('name', cid)}")

    # 3) 原有 Boon (主要用于自由模式兼容)
    boons = getattr(game, 'boons', {}) or {}
    for bid, lvl in boons.items():
        cfg = BOONS.get(bid, {"name": bid})
        tokens.append(f"{cfg.get('name', bid)} x{lvl}")

    if not tokens:
        return
        
    max_width = SCREEN_WIDTH - 40
    fnt = get_font(max(12, font.get_height() - 2))
    lines: List[str] = []
    label = "当前增益: "
    current = label
    for tok in tokens:
        separator = "" if current == label else "  |  "
        candidate = current + (tok if separator == "" else separator + tok)
        width, _ = fnt.size(candidate)
        if width <= max_width or current == label:
            current = candidate
        else:
            if current != label:
                lines.append(current)
            current = label + tok
    if current != label:
        lines.append(current)

    boons_y = layout.get("boon_y", 120)
    for idx, line in enumerate(lines):
        surf = fnt.render(line, True, HUD_COLOR)
        surface.blit(surf, (20, boons_y + idx * 24))


def draw_world(surface: pg.Surface, game: Game, font: pg.font.Font):
    bg = _get_background_surface()
    if bg:
        surface.blit(bg, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    # 顶部面板
    pg.draw.rect(surface, TOP_PANEL_COLOR, (0, 0, SCREEN_WIDTH, TOP_UI_HEIGHT))
    # HUD 与兵种面板
    layout = _top_panel_layout(game)
    draw_hud(surface, font, game, layout)
    draw_palette(surface, font, game, layout)
    _draw_skill_row(surface, font, game, layout)
    _draw_boons_row(surface, font, game, layout)
    
    # 计算每条战线的可见右边界：基础 1/2 视野 + 该线最前友军 + 半屏
    base_visible = SCREEN_WIDTH * 0.5
    lane_count = len(game.lane_y)
    visible_right_by_lane = [0] * lane_count
    for lane in range(lane_count):
        furthest = 0.0
        for u in game.left_units[lane]:
            if u.x > furthest:
                furthest = u.x
        visible_right_by_lane[lane] = int(min(SCREEN_WIDTH, max(base_visible, furthest + SCREEN_WIDTH * 0.5)))
    # 战场元素
    draw_lanes(surface, font, game)

    # 地面危害（燃烧区域）
    hazards = getattr(game, 'lane_hazards', None)
    if hazards:
        for hazard in hazards:
            if hazard.duration <= 0.0:
                continue
            if hazard.lane < 0 or hazard.lane >= len(game.lane_y):
                continue
            lane_y = game.lane_y[hazard.lane]
            radius = max(12, int(hazard.radius))
            height = 20
            overlay = pg.Surface((radius * 2, height), pg.SRCALPHA)
            ratio = max(0.1, min(1.0, hazard.duration / hazard.max_duration))
            alpha = int(160 * ratio)
            if hazard.side == "left":
                base_rgb = (255, 120, 40)
                outline_rgb = (255, 200, 120)
            else:
                base_rgb = (140, 100, 255)
                outline_rgb = (200, 160, 255)
            color = (*base_rgb, alpha)
            pg.draw.ellipse(overlay, color, overlay.get_rect())
            outline_color = (*outline_rgb, max(80, alpha))
            pg.draw.ellipse(overlay, outline_color, overlay.get_rect(), 2)
            rect = overlay.get_rect(center=(int(hazard.x), int(lane_y)))
            surface.blit(overlay, rect.topleft)

    # 基地（每条战线各自显示）
    from .constants import BASE_MAX_HP, CYAN, MAGENTA
    for idx, y in enumerate(game.lane_y):
        left_base_alert = False
        right_base_alert = False
        if idx < len(getattr(game, 'left_base_invuln_timer', [])):
            left_base_alert = game.left_base_invuln_timer[idx] > 0.0
        if idx < len(getattr(game, 'right_base_invuln_timer', [])):
            right_base_alert = game.right_base_invuln_timer[idx] > 0.0
        
        # 判断该战线是否被选中
        is_selected_lane = (idx == game.selected_lane)
        
        draw_lane_base(
            surface,
            game.left_bases[idx].x,
            y,
            game.left_bases[idx].hp,
            BASE_MAX_HP,
            CYAN,
            highlight=left_base_alert,
            selected=is_selected_lane,  # 传入选中状态
        )
        draw_lane_base(
            surface,
            game.right_bases[idx].x,
            y,
            game.right_bases[idx].hp,
            BASE_MAX_HP,
            MAGENTA,
            highlight=right_base_alert,
            selected=False,  # 敌方基地不显示选中状态
        )

    # 单位
    def _render_hp_bar(unit):
        bar_w = 24
        bar_h = 4
        bx = int(unit.x - bar_w // 2)
        by = int(unit.y - unit.unit_type.radius * 2 - 12)
        pg.draw.rect(surface, GRID_COLOR, (bx, by, bar_w, bar_h))
        max_hp = max(1.0, float(getattr(unit, "max_hp", unit.unit_type.hp)))
        hp_ratio = 0.0 if max_hp <= 0 else max(0.0, min(1.0, unit.hp / max_hp))
        fill_w = int(round(bar_w * hp_ratio))
        tags = set(getattr(unit, "ui_highlights", ()) or [])
        low_hp = hp_ratio <= 0.3
        pulse = 0.6 + 0.4 * math.sin(pg.time.get_ticks() / 200.0)
        base_color = GREEN if not low_hp else (int(255 * pulse), 60, 60)
        if tags:
            if "origei" in tags and "drummer" in tags:
                base_color = YELLOW
            elif "origei" in tags:
                base_color = ORANGE
            elif "drummer" in tags:
                base_color = BLUE
        if fill_w > 0:
            pg.draw.rect(surface, base_color, (bx, by, fill_w, bar_h))
        elif tags:
            pg.draw.rect(surface, base_color, (bx, by, bar_w, bar_h), width=1)

        shield_hp = max(0.0, getattr(unit, "shield_hp", 0.0))
        shield_timer = getattr(unit, "shield_timer", 0.0)
        if shield_hp > 0.0 and shield_timer > 0.0 and max_hp > 0:
            shield_ratio = max(0.0, shield_hp / max_hp)
            shield_pixels_total = max(1, int(round(bar_w * min(shield_ratio, 1.5))))
            space_in_bar = max(0, bar_w - fill_w)
            inside_w = min(shield_pixels_total, space_in_bar)
            if inside_w > 0:
                pg.draw.rect(surface, WHITE, (bx + fill_w, by, inside_w, bar_h))
                pg.draw.rect(surface, (200, 200, 200), (bx + fill_w, by, inside_w, bar_h), width=1)
            overflow_w = shield_pixels_total - inside_w
            if overflow_w > 0:
                pg.draw.rect(surface, GRID_COLOR, (bx + bar_w, by, overflow_w, bar_h))
                pg.draw.rect(surface, WHITE, (bx + bar_w, by, overflow_w, bar_h))
                pg.draw.rect(surface, (200, 200, 200), (bx + bar_w, by, overflow_w, bar_h), width=1)

        pg.draw.rect(surface, GRID_COLOR, (bx, by, bar_w, bar_h), width=1)

    for lane in range(len(game.lane_y)):
        for u in game.left_units[lane]:
            draw_unit(
                surface,
                u.x,
                u.y,
                u.unit_type.shape,
                u.unit_type.color,
                u.unit_type.radius * 2,
                facing_left=False,
                ut=u.unit_type,
                unit=u,
            )
            _render_hp_bar(u)
        for u in game.right_units[lane]:
            if u.x <= visible_right_by_lane[lane]:
                draw_unit(
                    surface,
                    u.x,
                    u.y,
                    u.unit_type.shape,
                    u.unit_type.color,
                    u.unit_type.radius * 2,
                    facing_left=True,
                    ut=u.unit_type,
                    unit=u,
                )
                _render_hp_bar(u)

    # 投射物
    for p in game.projectiles:
        color = (240, 240, 240)
        # 冰弓（frost_archer）子弹改为荧光蓝，与精灵图风格一致
        if p.owner and getattr(p.owner.unit_type, "key", "") == "frost_archer":
            color = (100, 240, 255)  # 荧光冰蓝色
        elif p.frost_stun_cap > 0:  # 备选判断：如果有寒冰眩晕能力
            color = (100, 240, 255)
            
        if p.side == "left" or p.x <= visible_right_by_lane[p.lane]:
            # 获取视觉类型
            visual = getattr(p, "visual_type", "default")
            draw_projectile(surface, p.x, p.y, color, shape=visual)

    # 粒子特效
    draw_particles(surface, game)

    # 技能导弹 / 爆炸特效
    for m in game.skill_missiles:
        if m.state in ("waiting", "done"):
            continue
        pos = (int(m.x), int(m.y))
        if m.state == "travel":
            color = ORANGE if m.side == "left" else MAGENTA
            dir_sign = 1 if m.side == "left" else -1
            tail = 12
            points = [
                pos,
                (int(m.x - dir_sign * tail), int(m.y - 4)),
                (int(m.x - dir_sign * tail), int(m.y + 4)),
            ]
            pg.draw.polygon(surface, color, points)
            trail_end = (int(m.x - dir_sign * (tail + 12)), int(m.y))
            pg.draw.line(surface, color, pos, trail_end, 2)
        elif m.state == "explode":
            lifetime = m.explosion_duration if m.explosion_duration > 0 else 0.001
            progress = 1.0 - max(0.0, m.explosion_timer) / lifetime
            progress = max(0.0, min(1.0, progress))
            radius = max(14, int(m.aoe_radius * (0.35 + 0.65 * progress)))
            alpha = max(40, min(230, int(220 * (1.0 - progress * 0.5))))
            overlay = pg.Surface((radius * 2, radius * 2), pg.SRCALPHA)
            pg.draw.circle(overlay, (255, 190, 80, alpha), (radius, radius), radius)
            surface.blit(overlay, (pos[0] - radius, pos[1] - radius))
            core_radius = max(6, radius // 3)
            pg.draw.circle(surface, (255, 240, 180), pos, radius, width=2)
            pg.draw.circle(surface, (255, 220, 140), pos, core_radius)

    # 选线高亮 (已改为基地高亮，此处移除横线绘制)
    # y = game.lane_y[game.selected_lane]
    # pg.draw.line(surface, (120, 160, 255), (60, y), (SCREEN_WIDTH - 60, y), 2)

    # 已在顶部面板处绘制 HUD 与兵种面板

    # 每条战线右侧未探索区域雾面板
    ys = game.lane_y
    top_start = TOP_UI_HEIGHT + 20
    bottom_end = SCREEN_HEIGHT - BOTTOM_MARGIN
    for i in range(lane_count):
        band_top = top_start if i == 0 else int((ys[i - 1] + ys[i]) / 2)
        band_bottom = bottom_end if i == lane_count - 1 else int((ys[i] + ys[i + 1]) / 2)
        vr = visible_right_by_lane[i]
        if vr < SCREEN_WIDTH:
            fog = pg.Surface((SCREEN_WIDTH - vr, band_bottom - band_top), flags=pg.SRCALPHA)
            fog.fill((0, 0, 0, 160))
            surface.blit(fog, (vr, band_top))

    if game.winner:
        msg = "胜利！" if game.winner == "left" else "失败…"
        big = get_font(48)
        wsurf = big.render(msg + " (Esc 退出)", True, WHITE)
        rect = wsurf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        surface.blit(wsurf, rect)


def draw_palette(surface: pg.Surface, font: pg.font.Font, game: Game, layout: dict):
    keys = getattr(game, 'player_order_keys', ORDER_KEYS)
    unit_levels = getattr(game, 'player_unit_levels', {}) or {}
    start_x = 260
    slot_w = 140
    r = 12
    # 计算每行可放数量
    max_per_row = max(1, (SCREEN_WIDTH - start_x - 60) // slot_w)
    rows_needed = layout.get("palette_rows", 1)
    # 行Y坐标
    row_y = layout.get("palette_row_y")
    if not row_y:
        row_y = [56] if rows_needed == 1 else [36, 96]

    for idx, k in enumerate(keys):
        row = 0 if idx < max_per_row or rows_needed == 1 else 1
        col = idx if row == 0 else (idx - max_per_row)
        if row >= len(row_y):
            row = len(row_y) - 1
        y = row_y[row]
        x = start_x + col * slot_w
        ut = UNIT_TYPES[k]
        # 实时费用逻辑
        actual_cost = ut.cost
        if k == "warrior" and getattr(game, 'veteran_q_free_cost', False):
            actual_cost = 0
        else:
            actual_cost = int(actual_cost * getattr(game, 'left_cost_mult', 1.0))

        affordable = game.left.resource >= actual_cost
        color = ut.color if affordable else (120, 120, 120)
        # 外框
        rect = pg.Rect(x - 32, y - 20, 140, 52)
        border_color = HUD_ACCENT if idx == game.selected_unit_idx else GRID_COLOR
        border_w = 3 if idx == game.selected_unit_idx else 1
        pg.draw.rect(surface, border_color, rect, border_w)
        level_val = max(1, int(unit_levels.get(k, 1)))
        level_color = HUD_ACCENT if level_val > 1 else HUD_COLOR
        lv_surf = get_font(12).render(f"Lv{level_val}", True, level_color)
        lv_rect = lv_surf.get_rect(center=(x, y - 28))
        surface.blit(lv_surf, lv_rect)
        # 图标
        draw_unit(surface, x, y, ut.shape, color, r, facing_left=False, ut=ut)
        # 兵种名称（放在图标下方，避免两行互相重叠）
        name_surf = get_font(14).render(ut.name, True, HUD_COLOR)
        name_rect = name_surf.get_rect(center=(x, y + 22))
        surface.blit(name_surf, name_rect)
        # 费用
        cost_text = f"{actual_cost}"
        cost_color = HUD_COLOR if affordable else GRID_COLOR
        cost_surf = get_font(max(12, font.get_height() - 4)).render(cost_text, True, cost_color)
        cost_x = int(x + r + 8)
        cost_y = int(y - cost_surf.get_height() / 2)
        surface.blit(cost_surf, (cost_x, cost_y))


def _get_menu_background() -> Optional[pg.Surface]:
    """专门用于加载菜单背景"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        # 尝试多个可能的路径，包括用户刚刚放置的位置
        candidates = [
            os.path.join(project_root, "assets", "backgrounds", "menu_bg.png"),
            os.path.join(project_root, "..", "assets", "backgrounds", "menu_bg.png"),
            os.path.join(os.path.dirname(project_root), "sevenlines", "assets", "backgrounds", "menu_bg.png"),
            "sevenlines/assets/backgrounds/menu_bg.png",
            "assets/backgrounds/menu_bg.png"
        ]
        
        bg_path = None
        for path in candidates:
            if os.path.exists(path):
                bg_path = path
                break
                
        if not bg_path:
            return None
            
        img = pg.image.load(bg_path).convert()
        
        # 缩放以覆盖屏幕
        iw, ih = img.get_size()
        scale_w = SCREEN_WIDTH / iw
        scale_h = SCREEN_HEIGHT / ih
        scale = max(scale_w, scale_h)
        
        new_w = int(iw * scale)
        new_h = int(ih * scale)
        if new_w != iw or new_h != ih:
            img = pg.transform.smoothscale(img, (new_w, new_h))
            
        # 居中裁剪
        final_surf = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        dest_x = (SCREEN_WIDTH - new_w) // 2
        dest_y = (SCREEN_HEIGHT - new_h) // 2
        final_surf.blit(img, (dest_x, dest_y))
        
        # 添加暗色遮罩让文字更清晰
        overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 80)) # 30% 黑色遮罩
        final_surf.blit(overlay, (0, 0))
        
        return final_surf
    except Exception as e:
        print(f"Failed to load menu background: {e}")
        return None

def draw_menu(surface: pg.Surface, font: pg.font.Font, has_autosave: bool = False):
    # 尝试绘制图片背景
    bg = _get_menu_background()
    if bg:
        surface.blit(bg, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
        
    title_font = get_font(56)
    mid_font = get_font(28)
    small_font = get_font(20)

    title = title_font.render("几何大战", True, WHITE)
    subtitle = small_font.render("7 战线  |  几何即时战术", True, HUD_COLOR)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 150)))
    surface.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 195)))

    opt1 = mid_font.render("1. 正常模式", True, HUD_ACCENT)
    opt2 = mid_font.render("2. 百科（操作说明与兵种数值）", True, HUD_ACCENT)
    opt3 = mid_font.render("3. 自由模式（无限配阵 + 增益）", True, HUD_ACCENT)
    opt5_color = HUD_ACCENT if has_autosave else GRID_COLOR
    opt5 = mid_font.render("5. 继续游戏（自动档）", True, opt5_color)

    surface.blit(opt1, opt1.get_rect(center=(SCREEN_WIDTH // 2, 320)))
    surface.blit(opt2, opt2.get_rect(center=(SCREEN_WIDTH // 2, 380)))
    surface.blit(opt3, opt3.get_rect(center=(SCREEN_WIDTH // 2, 440)))
    surface.blit(opt5, opt5.get_rect(center=(SCREEN_WIDTH // 2, 500)))
    
    opt4 = mid_font.render("4. 设置", True, HUD_ACCENT)
    surface.blit(opt4, opt4.get_rect(center=(SCREEN_WIDTH // 2, 560)))
    
    esc = get_font(font.get_height()).render("Esc 退出", True, HUD_COLOR)
    esc_rect = esc.get_rect()
    esc_rect.bottomleft = (36, SCREEN_HEIGHT - 36)
    surface.blit(esc, esc_rect)
    hint = small_font.render("按数字选择模式", True, GRID_COLOR)
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)))


def draw_pause_menu(surface: pg.Surface, font: pg.font.Font, cursor_idx: int):
    # 半透明黑色背景
    overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (0, 0))

    title_font = get_font(48)
    mid_font = get_font(28)

    title = title_font.render("暂停", True, WHITE)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 160)))

    options = ["继续游戏", "回到主菜单", "设置", "百科"]
    start_y = 300
    gap_y = 60
    arrow = "▶ "

    for i, opt_text in enumerate(options):
        color = HUD_ACCENT if i == cursor_idx else HUD_COLOR
        text = (arrow if i == cursor_idx else "   ") + opt_text
        opt_surf = mid_font.render(text, True, color)
        surface.blit(opt_surf, opt_surf.get_rect(center=(SCREEN_WIDTH // 2, start_y + i * gap_y)))

    # esc = get_font(font.get_height()).render("Esc 返回游戏", True, HUD_COLOR)
    # surface.blit(esc, esc.get_rect(center=(SCREEN_WIDTH // 2, start_y + len(options) * gap_y + 40)))


def draw_settings(
    surface: pg.Surface,
    font: pg.font.Font,
    current_res_idx: int,
    resolutions: list[tuple[int, int]],
    is_fullscreen: bool,
    bgm_volume: float,
    sfx_volume: float,
    cursor_idx: int,
    lang: str,
):
    bg = _get_menu_background()
    if bg:
        surface.blit(bg, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    
    title = get_font(40).render(str(tr("设置", "Settings")), True, WHITE)
    surface.blit(title, (80, 60))
    
    mid_font = get_font(28)
    
    # 选项垂直位置
    start_y = 180
    gap_y = 60
    
    # 1. 分辨率选项
    res_color = HUD_ACCENT if cursor_idx == 0 else HUD_COLOR
    res_label = mid_font.render(str(tr("分辨率", "Resolution")), True, res_color)
    surface.blit(res_label, (200, start_y))
    
    w, h = resolutions[current_res_idx]
    res_val_text = f"< {w} x {h} >"
    res_val = mid_font.render(res_val_text, True, res_color)
    surface.blit(res_val, (500, start_y))
    
    # 2. 全屏选项
    fs_color = HUD_ACCENT if cursor_idx == 1 else HUD_COLOR
    fs_label = mid_font.render(str(tr("显示模式", "Display Mode")), True, fs_color)
    surface.blit(fs_label, (200, start_y + gap_y))
    
    fs_val_text = "< 全屏 >" if is_fullscreen else "< 窗口 >"
    if lang == "en":
        fs_val_text = "< Fullscreen >" if is_fullscreen else "< Windowed >"
    fs_val = mid_font.render(fs_val_text, True, fs_color)
    surface.blit(fs_val, (500, start_y + gap_y))

    # 3. BGM 音量
    bgm_color = HUD_ACCENT if cursor_idx == 2 else HUD_COLOR
    bgm_label = mid_font.render(str(tr("音乐音量", "Music Volume")), True, bgm_color)
    surface.blit(bgm_label, (200, start_y + gap_y * 2))
    
    # 绘制音量条
    bar_w = 200
    bar_h = 20
    bar_x = 500
    bar_y = start_y + gap_y * 2 + 10
    pg.draw.rect(surface, GRID_COLOR, (bar_x, bar_y, bar_w, bar_h), 2)
    fill_w = int(bar_w * bgm_volume)
    if fill_w > 0:
        pg.draw.rect(surface, bgm_color, (bar_x + 2, bar_y + 2, fill_w - 4, bar_h - 4))
    knob_x = bar_x + max(2, fill_w)
    pg.draw.circle(surface, bgm_color, (knob_x, bar_y + bar_h // 2), 8)
    vol_text = f"{int(bgm_volume * 100)}%"
    vol_surf = mid_font.render(vol_text, True, bgm_color)
    surface.blit(vol_surf, (bar_x + bar_w + 20, start_y + gap_y * 2))

    # 4. SFX 音量
    sfx_color = HUD_ACCENT if cursor_idx == 3 else HUD_COLOR
    sfx_label = mid_font.render(str(tr("音效音量", "SFX Volume")), True, sfx_color)
    surface.blit(sfx_label, (200, start_y + gap_y * 3))
    
    # 绘制音量条
    bar_y = start_y + gap_y * 3 + 10
    pg.draw.rect(surface, GRID_COLOR, (bar_x, bar_y, bar_w, bar_h), 2)
    fill_w = int(bar_w * sfx_volume)
    if fill_w > 0:
        pg.draw.rect(surface, sfx_color, (bar_x + 2, bar_y + 2, fill_w - 4, bar_h - 4))
    knob_x = bar_x + max(2, fill_w)
    pg.draw.circle(surface, sfx_color, (knob_x, bar_y + bar_h // 2), 8)
    vol_text = f"{int(sfx_volume * 100)}%"
    vol_surf = mid_font.render(vol_text, True, sfx_color)
    surface.blit(vol_surf, (bar_x + bar_w + 20, start_y + gap_y * 3))
    
    # 5. 语言
    lang_color = HUD_ACCENT if cursor_idx == 4 else HUD_COLOR
    lang_label = mid_font.render(str(tr("语言", "Language")), True, lang_color)
    surface.blit(lang_label, (200, start_y + gap_y * 4))
    lang_val_text = "< 中文 >" if lang == "zh" else "< English >"
    lang_val = mid_font.render(lang_val_text, True, lang_color)
    surface.blit(lang_val, (500, start_y + gap_y * 4))

    # 提示
    tips_text = "↑↓ 选择  ←→ 修改  回车/Esc 返回"
    if lang == "en":
        tips_text = "↑↓ Select  ←→ Change  Enter/Esc Back"
    tips = get_font(20).render(tips_text, True, GRID_COLOR)
    tips_rect = tips.get_rect()
    tips_rect.bottomright = (SCREEN_WIDTH - 60, SCREEN_HEIGHT - 40)
    surface.blit(tips, tips_rect)


def draw_campaign_defeat(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    """失败结算画面：用于复盘/测试，展示本局关键数据。"""
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(56).render("战役失败", True, RED)
    surface.blit(title, (60, 40))

    if not campaign_run or not campaign_run.state:
        info = get_font(26).render("本局数据缺失。按 Esc/回车 返回主菜单。", True, YELLOW)
        surface.blit(info, (60, 140))
        return

    # 基础统计
    gold = campaign_run.state.gold
    battle_count = campaign_run.state.battle_count
    day = campaign_run.state.day
    rep = getattr(campaign_run, "reputation", 0)
    total_time = campaign_run.total_time
    blessing_key = campaign_run.blessing_selected
    blessing = BLESSINGS.get(blessing_key, {}).get("name", blessing_key) if blessing_key else "（无）"

    combo_selected = campaign_run.combo.selected_cards if getattr(campaign_run, "combo", None) else []
    combo_names = [str(COMBO_CARDS.get(cid, {}).get("name", cid)) for cid in (combo_selected or [])]
    combo_text = " / ".join(combo_names) if combo_names else "（无）"

    executed_n = sum(1 for v in (campaign_run.prisoners.executed_once or {}).values() if v)
    joined_n = sum(1 for v in (campaign_run.prisoners.joined_once or {}).values() if v)

    stat_lines = [
        f"金币：{gold}",
        f"战斗场次：{battle_count}",
        f"天数：{day}",
        f"声望：{rep}",
        f"总用时：{int(total_time)} 秒",
        f"祝福：{blessing}",
        f"Combo：{combo_text}",
        f"俘虏记录：归顺{joined_n} / 处决{executed_n}",
    ]

    x0, y0 = 60, 130
    for i, ln in enumerate(stat_lines):
        _blit_text(surface, get_font(26), ln, (x0, y0 + i * 34), WHITE, outline_px=2)

    # 队伍/技能/锻造摘要
    y = y0 + len(stat_lines) * 34 + 20
    _blit_text(surface, get_font_bold(30), "兵种：", (60, y), WHITE, outline_px=2)
    y += 38
    if campaign_run.units:
        for k in campaign_run.units[:10]:
            lv = campaign_run.unit_levels.get(k, 1)
            ut = UNIT_TYPES.get(k)
            name = ut.name if ut else k
            _blit_text(surface, get_font(24), f"- {name}  Lv{lv}", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无兵种）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    y += 10
    _blit_text(surface, get_font_bold(30), "技能：", (60, y), WHITE, outline_px=2)
    y += 38
    if campaign_run.skills:
        for sk in campaign_run.skills[:6]:
            cfg = SKILLS.get(sk, {})
            nm = cfg.get("name", sk)
            _blit_text(surface, get_font(24), f"- {nm}", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    # 锻造摘要
    y += 10
    _blit_text(surface, get_font_bold(30), "锻造：", (60, y), WHITE, outline_px=2)
    y += 38
    forge_levels = getattr(getattr(campaign_run, "forge", None), "level_by_unit", {}) or {}
    forge_dirs = getattr(getattr(campaign_run, "forge", None), "locked_direction", {}) or {}
    if campaign_run.units:
        shown = 0
        for k in campaign_run.units:
            lvl = int(forge_levels.get(k, 0) or 0)
            if lvl <= 0 and k not in forge_dirs:
                continue
            d = forge_dirs.get(k)
            d_txt = "攻" if d == "offense" else ("防" if d == "defense" else "未定")
            ut = UNIT_TYPES.get(k)
            name = ut.name if ut else k
            _blit_text(surface, get_font(24), f"- {name}：{d_txt} {lvl}级", (60, y), HUD_COLOR, outline_px=2)
            y += 30
            shown += 1
            if shown >= 6:
                break
        if shown == 0:
            _blit_text(surface, get_font(24), "（本局无锻造）", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    tips = get_font(20).render("回车/空格：再来一局    Esc：返回主菜单", True, GRID_COLOR)
    tips_rect = tips.get_rect()
    tips_rect.bottomright = (SCREEN_WIDTH - 60, SCREEN_HEIGHT - 40)
    surface.blit(tips, tips_rect)


def draw_campaign_postbattle_summary(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(48).render("胜利结算", True, WHITE)
    surface.blit(title, (60, 50))

    if not campaign_run or not campaign_run.state:
        info = get_font(26).render("结算数据缺失，按回车返回。", True, YELLOW)
        surface.blit(info, (60, 140))
    else:
        gold = campaign_run.state.gold
        bc = campaign_run.state.battle_count
        subtitle = get_font(24).render(f"金币：{gold}    已战斗：{bc}    节点：{campaign_run.postbattle_node_type}", True, HUD_COLOR)
        surface.blit(subtitle, (60, 120))

        lines = (campaign_run.postbattle_summary or "战斗胜利！").splitlines()
        y = 170
        for ln in lines[:8]:
            _blit_text(surface, get_font(26), ln, (60, y), WHITE, outline_px=2)
            y += 36

    tips = get_font(20).render("回车/空格：继续（进入锻造）", True, GRID_COLOR)
    surface.blit(tips, (60, SCREEN_HEIGHT - 60))


def draw_campaign_forge(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("UPGRADE_BG_SURFACE", "upgrade_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(48).render("锻造", True, WHITE)
    surface.blit(title, (60, 50))

    if not campaign_run or not campaign_run.state:
        _blit_text(surface, get_font(26), "锻造数据缺失，按回车继续。", (60, 150), YELLOW, outline_px=2)
        return

    # 顶部信息
    gold = campaign_run.state.gold
    rep = campaign_run.reputation
    _blit_text(surface, get_font(24), f"金币：{gold}    声望：{rep}", (60, 120), HUD_COLOR, outline_px=2)

    # 默认目标与出兵次数列表（此处口径：单场战斗）
    counts = campaign_run.forge.spawn_count_by_unit
    units = campaign_run.units or []
    if not units:
        _blit_text(surface, get_font(26), "无可用兵种", (60, 170), YELLOW, outline_px=2)
        return

    sel = campaign_run.forge_selected_unit or units[0]
    default = campaign_run.forge_default_unit
    reason = campaign_run.forge_default_reason or ""

    # 左侧：列表
    y = 170
    _blit_text(surface, get_font_bold(28), "出兵次数（上一场战斗）", (60, y), WHITE, outline_px=2)
    y += 40
    for k in units:
        ut = UNIT_TYPES.get(k)
        name = ut.name if ut else k
        c = counts.get(k, 0)
        
        # 攻防拆分显示
        off_lvl = campaign_run.forge.offense_level_by_unit.get(k, 0)
        def_lvl = campaign_run.forge.defense_level_by_unit.get(k, 0)
        tag = ""
        if off_lvl or def_lvl:
            parts = []
            if off_lvl: parts.append(f"攻{off_lvl}")
            if def_lvl: parts.append(f"防{def_lvl}")
            tag = f"  [{'/'.join(parts)}]"

        mark = "（默认）" if (default and k == default) else ""
        color = (255, 220, 0) if k == sel else HUD_COLOR
        _blit_text(surface, get_font(24), f"{name}({k})：{c}{tag}{mark}", (60, y), color, outline_px=2)
        y += 30

    # 右侧：决策信息（更像卡片）
    panel_x = 780
    panel_y = 170
    panel_w = 600
    panel_h = 520
    pg.draw.rect(surface, (22, 22, 30), (panel_x, panel_y, panel_w, panel_h), border_radius=16)
    pg.draw.rect(surface, GRID_COLOR, (panel_x, panel_y, panel_w, panel_h), width=2, border_radius=16)

    dir_txt = "攻" if campaign_run.forge_selected_dir == "offense" else "防"
    off_lvl = campaign_run.forge.offense_level_by_unit.get(sel, 0)
    def_lvl = campaign_run.forge.defense_level_by_unit.get(sel, 0)
    cur_lvl = off_lvl if campaign_run.forge_selected_dir == "offense" else def_lvl
    
    _blit_text(surface, get_font_bold(30), f"选择：{sel}   方向：{dir_txt}", (panel_x + 20, panel_y + 18), WHITE, outline_px=2)
    
    lvl_txt = f"当前等级：攻{off_lvl} / 防{def_lvl}"
    _blit_text(surface, get_font(24), lvl_txt, (panel_x + 20, panel_y + 60), HUD_COLOR, outline_px=2)

    # 费用提示（仅 UI 提示；真实扣费逻辑在 main.py）
    cost_line = "改锻费用：0"
    if default and sel != default:
        # UI 层逻辑应与 main.py 中的 _forge_retarget_cost 保持一致
        total_level = off_lvl + def_lvl
        base_cost = FORGE_RETARGET_BASE_COST + (total_level * FORGE_RETARGET_PER_LEVEL_COST)
        
        # 祝福/Combo 修正
        if campaign_run.blessing_selected == "arms_grant":
            base_cost = int(math.ceil(base_cost * 0.7))
        if "combo_forge_discount" in campaign_run.combo.selected_cards:
            base_cost = int(math.ceil(base_cost * 0.8))
            
        cost_line = f"改锻费用：{base_cost} (随等级增加)"
    _blit_text(surface, get_font(24), cost_line, (panel_x + 20, panel_y + 95), HUD_COLOR, outline_px=2)

    # 成功率提示（显示“最终成功率”，与 main.py 的锻造结算口径一致）
    next_lvl = min(5, cur_lvl + 1)
    if cur_lvl >= 5:
        chance_txt = "已满级：5级"
    else:
        # 基础：1级100%，2级50%，3级25%，4/5级仅匠人精神解锁（否则视为不可升阶）
        if next_lvl <= 1:
            base_p = 1.0
        elif next_lvl == 2:
            base_p = 0.5
        elif next_lvl == 3:
            base_p = 0.25
        elif next_lvl == 4:
            base_p = FORGE_LEVEL_4_SUCCESS_RATE if campaign_run.blessing_selected == "craftsman_spirit" else 0.0
        elif next_lvl == 5:
            base_p = FORGE_LEVEL_5_SUCCESS_RATE if campaign_run.blessing_selected == "craftsman_spirit" else 0.0
        else:
            base_p = 0.0

        final_p = base_p
        # 祝福：匠人精神 → 成功率100%
        if campaign_run.blessing_selected == "craftsman_spirit":
            final_p = 1.0

        if base_p <= 0.0 and next_lvl >= 4 and campaign_run.blessing_selected != "craftsman_spirit":
            chance_txt = f"下一次升阶：{next_lvl}级  （需要“匠人精神”解锁）"
        elif abs(final_p - base_p) < 1e-9:
            chance_txt = f"下一次升阶：{next_lvl}级  成功率：{int(final_p*100)}%"
        else:
            chance_txt = f"下一次升阶：{next_lvl}级  基础成功率：{int(base_p*100)}%  最终成功率：{int(final_p*100)}%"

    _blit_text(surface, get_font(24), chance_txt, (panel_x + 20, panel_y + 130), HUD_COLOR, outline_px=2)

    # 数值变化预览
    ut = UNIT_TYPES.get(sel)
    if ut:
        def get_stat_mults(off, dfn):
            d_p, a_p = 0, 0
            if off == 1: d_p, a_p = 0.10, 0.03
            elif off == 2: d_p, a_p = 0.25, 0.07
            elif off == 3: d_p, a_p = 0.50, 0.12
            elif off == 4: d_p, a_p = 0.80, 0.15
            elif off == 5: d_p, a_p = 1.20, 0.20
            
            h_p, s_p = 0, 0
            if dfn == 1: h_p, s_p = 0.10, 0.03
            elif dfn == 2: h_p, s_p = 0.25, 0.07
            elif dfn == 3: h_p, s_p = 0.50, 0.12
            elif dfn == 4: h_p, s_p = 0.80, 0.15
            elif dfn == 5: h_p, s_p = 1.20, 0.20
            return d_p, a_p, h_p, s_p

        # 当前属性 (含目前锻造)
        d0, a0, h0, s0 = get_stat_mults(off_lvl, def_lvl)
        # 目标属性 (若成功)
        if campaign_run.forge_selected_dir == "offense":
            d1, a1, h1, s1 = get_stat_mults(next_lvl, def_lvl)
        else:
            d1, a1, h1, s1 = get_stat_mults(off_lvl, next_lvl)
            
        # 这里为了简化，只显示相对于基础值的变化，或者显示绝对值
        # 考虑到 sub_stat_mult 可能存在，这里先显示 基础 -> 目标 的百分比变化
        stat_y = panel_y + 260
        _blit_text(surface, get_font_bold(22), "预估数值变化：", (panel_x + 20, stat_y), WHITE, outline_px=2)
        stat_y += 30
        
        lines = []
        if campaign_run.forge_selected_dir == "offense":
            # 伤害与攻速
            cur_dmg = int(round(ut.damage * (1.0 + d0)))
            nxt_dmg = int(round(ut.damage * (1.0 + d1)))
            cur_cd = ut.cooldown / (1.0 + a0)
            nxt_cd = ut.cooldown / (1.0 + a1)
            lines.append(f"伤害：{cur_dmg} -> {nxt_dmg} (+{int((nxt_dmg-cur_dmg)/max(1,cur_dmg)*100)}%)")
            lines.append(f"攻速：{1.0/max(0.01, cur_cd):.1f} -> {1.0/max(0.01, nxt_cd):.1f} 次/秒")
        else:
            # 生命与移速
            cur_hp = int(round(ut.hp * (1.0 + h0)))
            nxt_hp = int(round(ut.hp * (1.0 + h1)))
            cur_spd = ut.speed * (1.0 + s0)
            nxt_spd = ut.speed * (1.0 + s1)
            lines.append(f"生命：{cur_hp} -> {nxt_hp} (+{int((nxt_hp-cur_hp)/max(1,cur_hp)*100)}%)")
            lines.append(f"移速：{int(cur_spd)} -> {int(nxt_spd)} (+{int((nxt_spd-cur_spd)/max(1,cur_spd)*100)}%)")
            
        for ln in lines:
            _blit_text(surface, get_font(20), ln, (panel_x + 40, stat_y), YELLOW, outline_px=2)
            stat_y += 25

    if reason:
        _blit_text(surface, get_font(22), f"默认目标原因：{reason}", (panel_x + 20, panel_y + 170), HUD_COLOR, outline_px=2)

    if campaign_run.forge_result_message:
        _blit_text(surface, get_font_bold(26), campaign_run.forge_result_message, (panel_x + 20, panel_y + 215), WHITE, outline_px=2)

    tips = get_font(20).render("←/→ 选兵种  ↑/↓ 选攻防  Tab切换  回车：执行锻造 / 已执行则继续", True, GRID_COLOR)
    surface.blit(tips, (60, SCREEN_HEIGHT - 60))


def draw_campaign_prisoners(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(48).render("俘虏处置", True, WHITE)
    surface.blit(title, (60, 50))

    if not campaign_run or not campaign_run.state:
        _blit_text(surface, get_font(26), "俘虏数据缺失，按回车继续。", (60, 150), YELLOW, outline_px=2)
        return

    gold = campaign_run.state.gold
    rep = campaign_run.reputation
    _blit_text(surface, get_font(24), f"金币：{gold}    声望：{rep}", (60, 120), HUD_COLOR, outline_px=2)

    if not getattr(campaign_run, "prisoners_inited", True):
        _blit_text(surface, get_font(26), "正在生成俘虏列表…", (60, 180), WHITE, outline_px=2)
        _blit_text(surface, get_font(22), "（如果敌方没有实际出兵，将使用本关AI池作为候选）", (60, 220), HUD_COLOR, outline_px=2)
        return
    if not campaign_run.prisoner_queue:
        _blit_text(surface, get_font(26), "（本关没有可俘虏对象）回车继续", (60, 180), WHITE, outline_px=2)
        _blit_text(surface, get_font(22), "提示：可能是敌方全被处决过，或本关候选池为空。", (60, 220), HUD_COLOR, outline_px=2)
        return

    idx = campaign_run.prisoner_idx
    total = len(campaign_run.prisoner_queue)
    if idx >= total:
        _blit_text(surface, get_font(26), "本关俘虏已全部处置完毕。回车继续", (60, 180), WHITE, outline_px=2)
        return

    uk = campaign_run.prisoner_queue[idx]
    ut = UNIT_TYPES.get(uk)
    
    # 百科风格卡片
    card_rect = pg.Rect(60, 160, SCREEN_WIDTH - 120, 360)
    pg.draw.rect(surface, (30, 30, 42), card_rect, border_radius=15)
    pg.draw.rect(surface, GRID_COLOR, card_rect, width=2, border_radius=15)
    
    # 顶部显示 俘虏进度
    _blit_text(surface, get_font(24), f"俘虏进度：{idx+1}/{total}", (card_rect.right - 180, card_rect.y + 15), HUD_COLOR)

    if ut:
        # 1. 兵种图像 (放大显示)
        img_x = card_rect.x + 100
        img_y = card_rect.y + 150
        draw_unit(surface, img_x, img_y, ut.shape, ut.color, 45, facing_left=False, ut=ut)
        
        # 2. 兵种数值与简介
        info_x = card_rect.x + 220
        info_y = card_rect.y + 30
        
        # 名称
        _blit_text(surface, get_font_bold(40), ut.name, (info_x, info_y), HUD_ACCENT, outline_px=2)
        
        meta = _lookup_unit_meta(ut)
        role = meta.get("role", "未知") if meta else "未知"
        short = meta.get("short", "") if meta else ""
        intro = meta.get("intro", "") if meta else ""
        
        body_font = get_font(22)
        line_h = 32
        
        # 定位与亮点
        _blit_text(surface, body_font, f"定位：{role}", (info_x, info_y + 55), WHITE)
        if short:
            _blit_text(surface, body_font, f"亮点：{short}", (info_x, info_y + 55 + line_h), HUD_COLOR)
            
        # 数值
        stats = f"费{ut.cost}  HP{ut.hp}  伤{ut.damage}  速{int(ut.speed)}  {'远' if ut.is_ranged else '近'}程{int(ut.range)}  攻速{ut.cooldown:.1f}"
        _blit_text(surface, body_font, f"数值：{stats}", (info_x, info_y + 55 + line_h * 2), HUD_COLOR)
        
        # 简介 (自动换行)
        if intro:
            intro_lines = _wrap_text(body_font, f"简介：{intro}", card_rect.width - 260)
            for i, ln in enumerate(intro_lines):
                _blit_text(surface, body_font, ln, (info_x, info_y + 55 + line_h * 3 + i * line_h), HUD_COLOR)
    else:
        # 如果兵种数据异常
        _blit_text(surface, get_font_bold(32), f"未知单位 ({uk})", (card_rect.x + 40, card_rect.y + 40), WHITE)

    # 三选一处置选项
    cur_level = campaign_run.unit_levels.get(uk, 0)
    actions = [
        ("归顺", "新获得兵种" if cur_level == 0 else f"等级+1 (Lv{cur_level}→{cur_level+1})"),
        ("处决", "获60金 声望-2 此兵种不再出现"),
        ("放归", "获80金 声望+2")
    ]
    
    actions_y = card_rect.bottom + 40
    for i, (action_name, desc) in enumerate(actions):
        selected = (i == campaign_run.prisoner_action_idx)
        color = (255, 220, 0) if selected else HUD_COLOR
        
        # 选项背景
        opt_w = 360
        opt_rect = pg.Rect(60 + i * 380, actions_y - 10, opt_w, 80)
        if selected:
            pg.draw.rect(surface, (50, 50, 70), opt_rect, border_radius=8)
            pg.draw.rect(surface, color, opt_rect, width=2, border_radius=8)
        
        _blit_text(surface, get_font_bold(32), action_name, (opt_rect.x + 20, opt_rect.y + 10), color, outline_px=2)
        _blit_text(surface, get_font(18), desc, (opt_rect.x + 20, opt_rect.y + 45), GRID_COLOR, outline_px=1)

    if campaign_run.prisoner_message:
        _blit_text(surface, get_font(24), campaign_run.prisoner_message, (60, actions_y + 90), WHITE, outline_px=2)

    tips = get_font(20).render("←/→ 选择处置  回车确认", True, GRID_COLOR)
    surface.blit(tips, (60, SCREEN_HEIGHT - 60))


def draw_campaign_blessing_select(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("UPGRADE_BG_SURFACE", "upgrade_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(48).render("祝福（首战后触发一次）", True, WHITE)
    surface.blit(title, (60, 50))

    if not campaign_run:
        info = get_font(26).render("祝福数据缺失，按回车返回。", True, YELLOW)
        surface.blit(info, (60, 140))
        return

    opts = campaign_run.blessing_options or ["（无候选）"]
    idx = max(0, min(campaign_run.blessing_idx, len(opts) - 1))

    # 简单横向 4 选 1 卡片（描述自动换行，避免挤成一坨）
    card_w = 280
    card_h = 220
    gap = 30
    start_x = 60
    y = 170
    for i, bid in enumerate(opts[:4]):
        x = start_x + i * (card_w + gap)
        selected = i == idx
        border = (255, 220, 0) if selected else GRID_COLOR
        fill = (30, 30, 42)
        pg.draw.rect(surface, fill, (x, y, card_w, card_h), border_radius=12)
        pg.draw.rect(surface, border, (x, y, card_w, card_h), width=3, border_radius=12)
        cfg = BLESSINGS.get(bid, {})
        nm = cfg.get("name", str(bid))
        desc = cfg.get("desc", "（占位效果）")
        label = get_font_bold(28).render(nm, True, WHITE)
        surface.blit(label, (x + 12, y + 14))

        desc_font = get_font(18)
        lines = _wrap_text(desc_font, desc, card_w - 24)
        yy = y + 62
        for ln in lines[:6]:
            surface.blit(desc_font.render(ln, True, HUD_COLOR), (x + 12, yy))
            yy += 22

    tips = get_font(20).render("←/→ 选择  回车/空格确认", True, GRID_COLOR)
    surface.blit(tips, (60, SCREEN_HEIGHT - 60))



def draw_campaign_map(
    surface: pg.Surface,
    font: pg.font.Font,
    campaign_state: CampaignState | None,
    cursor_node_id: int | None,
    message: str = "",
    scroll_offset: float = 0.0,
    enemy_previews: Dict[int, List[str]] | None = None,
):
    global MAP_BG_SURFACE, MAP_BG_HEIGHT
    # 先清屏，避免残留上一界面内容
    surface.fill(BACKGROUND_COLOR)
    # 尝试加载地图背景
    if MAP_BG_SURFACE is None:
        MAP_BG_SURFACE = _load_map_background()
    
    if MAP_BG_SURFACE:
        # 计算背景的绘制位置，根据 scroll_offset 调整
        bg_w, bg_h = MAP_BG_SURFACE.get_size()
        # 背景水平居中
        bg_x = (SCREEN_WIDTH - bg_w) // 2
        # 根据地图滚动比例让背景与关卡同步滚动
        # 计算地图最大滚动（与 main.py 的 campaign_map_max_scroll 一致）
        layer_count = campaign_state and len(campaign_state.layers) or 0
        if layer_count <= 1:
            max_scroll = 0.0
        else:
            visible_height = SCREEN_HEIGHT - (TOP_UI_HEIGHT + 80) - (BOTTOM_MARGIN + 160)
            total_height = (layer_count - 1) * MAP_LAYER_GAP
            max_scroll = max(0.0, total_height - visible_height + 80)

        if max_scroll > 0:
            ratio = max(0.0, min(1.0, scroll_offset / max_scroll))
        else:
            ratio = 0.0

        # 当 ratio=0 背景顶对齐屏幕顶；ratio=1 背景底对齐屏幕底
        bg_y = - (bg_h - SCREEN_HEIGHT) * ratio
        bg_y = int(bg_y)
        
        # 绘制背景（可能只显示一部分）
        surface.blit(MAP_BG_SURFACE, (bg_x, bg_y))
        
        # 填充背景未覆盖的区域（上下左右）
        if bg_y > 0:
            # 上方有空白，填充顶部
            surface.fill(BACKGROUND_COLOR, (0, 0, SCREEN_WIDTH, bg_y))
        if bg_y + bg_h < SCREEN_HEIGHT:
            # 下方有空白，填充底部
            surface.fill(BACKGROUND_COLOR, (0, bg_y + bg_h, SCREEN_WIDTH, SCREEN_HEIGHT - (bg_y + bg_h)))
        if bg_x > 0:
            # 左侧空白
            surface.fill(BACKGROUND_COLOR, (0, 0, bg_x, SCREEN_HEIGHT))
        if bg_x + bg_w < SCREEN_WIDTH:
            # 右侧空白
            surface.fill(BACKGROUND_COLOR, (bg_x + bg_w, 0, SCREEN_WIDTH - (bg_x + bg_w), SCREEN_HEIGHT))
    else:
        surface.fill(BACKGROUND_COLOR)
    enemy_previews = enemy_previews or {}

    title = get_font(40).render("战役地图", True, WHITE)
    surface.blit(title, (60, 40))

    if not campaign_state:
        info = get_font(24).render("地图尚未生成", True, HUD_COLOR)
        surface.blit(info, info.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))
        return

    campaign_state.ensure_cursor()
    available_nodes = set(campaign_state.available_nodes())

    # 反转层的绘制方向：第0层在最下方，越往上 layer_index 越大
    # 将第0层贴近底部（预留 40px 底部安全区）
    map_top = TOP_UI_HEIGHT + 80  # 单层时用于居中计算
    # 如需让第0层更贴近背景底部，可减小这里的留白；将 40 改成 -40 表示向下再压 40 像素
    map_bottom = SCREEN_HEIGHT - BOTTOM_MARGIN + 2050 - scroll_offset
    layer_count = max(1, len(campaign_state.layers))
    layer_gap = MAP_LAYER_GAP if layer_count > 1 else 0
    inner_margin_x = max(220, LEFT_MARGIN + 120)
    positions: dict[int, tuple[int, int]] = {}

    for layer_idx, node_ids in enumerate(campaign_state.layers):
        y = int(map_bottom - layer_gap * layer_idx) if layer_count > 1 else (map_top + map_bottom) // 2
        for node_id in node_ids:
            node = campaign_state.nodes.get(node_id)
            if not node:
                continue
            rel = MAP_COLUMN_SLOTS[node.column_slot] if 0 <= node.column_slot < len(MAP_COLUMN_SLOTS) else 0
            base_x = SCREEN_WIDTH // 2 + int(rel * MAP_COLUMN_STEP)
            offset = node.x_offset
            left_bound = inner_margin_x
            right_bound = SCREEN_WIDTH - inner_margin_x
            pos_x = max(left_bound, min(right_bound, base_x + offset))
            positions[node_id] = (int(pos_x), int(y))

    for node in campaign_state.nodes.values():
        start = positions.get(node.node_id)
        if not start:
            continue
        for cid in node.connections:
            end = positions.get(cid)
            if not end:
                continue
            dest_node = campaign_state.nodes[cid]
            if dest_node.cleared and node.cleared:
                line_color = (185, 210, 230)
            elif dest_node.cleared:
                line_color = (160, 190, 210)
            elif cid in available_nodes or node.node_id in available_nodes:
                line_color = (130, 150, 180)
            else:
                line_color = (70, 80, 100)
            _draw_dashed_line(surface, line_color, start, end, width=3)

    active_node_id = campaign_state.active_node_id

    for node_id, node in campaign_state.nodes.items():
        center = positions.get(node_id)
        if not center:
            continue
        # 尝试加载图标
        if node.node_type == "boss":
            base_radius = 64
        elif node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            base_radius = 32
        else:
            base_radius = 28

        # 根据全局缩放系数放大节点图标尺寸
        radius = int(base_radius * MAP_ICON_SCALE)
        icon_size = radius * 2
        icon_img = load_node_icon(node.node_type, icon_size, icon_size)
        
        base_color = CAMPAIGN_NODE_COLORS.get(node.node_type, WHITE)
        is_selected = node_id == cursor_node_id
        is_active = node_id == active_node_id
        
        border_color = WHITE
        
        if node.cleared:
            border_color = (140, 150, 170)
        elif node_id in available_nodes:
            border_color = (255, 220, 0) if is_selected else WHITE
        else:
            border_color = GRID_COLOR

        # 活跃/选中特效（在图标下方绘制）
        if is_active:
            pulse = 0.5 + 0.5 * math.sin(pg.time.get_ticks() / 280.0)
            active_radius = int(radius + 10 + pulse * 4)
            active_color = (80, 220, 255, int(140 + 70 * pulse))
            active_surf = pg.Surface((active_radius * 2 + 4, active_radius * 2 + 4), pg.SRCALPHA)
            pg.draw.circle(active_surf, active_color, (active_radius + 2, active_radius + 2), active_radius, width=4)
            active_rect = active_surf.get_rect(center=center)
            surface.blit(active_surf, active_rect.topleft)

        if is_selected and node_id in available_nodes:
            pulse = 0.6 + 0.4 * math.sin(pg.time.get_ticks() / 300.0)
            highlight_radius = int(radius + 6 + pulse * 4)
            highlight_color = (255, 220, 0, int(180 * pulse))
            highlight_surf = pg.Surface((highlight_radius * 2 + 4, highlight_radius * 2 + 4), pg.SRCALPHA)
            pg.draw.circle(highlight_surf, highlight_color, (highlight_radius + 2, highlight_radius + 2), highlight_radius, width=3)
            highlight_rect = highlight_surf.get_rect(center=center)
            surface.blit(highlight_surf, highlight_rect.topleft)

        if icon_img:
            # 使用图标绘制
            draw_icon = icon_img.copy()
            
            # 根据状态调整亮度/颜色
            if node.cleared:
                # 变暗
                dark = pg.Surface((icon_size, icon_size), pg.SRCALPHA)
                dark.fill((0, 0, 0, 120))
                draw_icon.blit(dark, (0, 0))
            elif node_id not in available_nodes and node.node_type != "boss":
                # 未解锁：黑色剪影（Boss 例外，保持正常亮度以凸显特殊性）
                draw_icon.fill((0, 0, 0, 255), special_flags=pg.BLEND_RGBA_MULT)
                draw_icon.set_alpha(200)
            
            icon_rect = draw_icon.get_rect(center=center)
            surface.blit(draw_icon, icon_rect)
            
            # 选中时叠加一个边框指示
            if is_selected:
                pg.draw.rect(surface, border_color, icon_rect.inflate(4, 4), 3, border_radius=8)
        else:
            # 回退到几何绘制
            base_fallback_radius = 26 if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES else 22
            radius = int(base_fallback_radius * MAP_ICON_SCALE)
            if node.cleared:
                fill_color = tuple(min(255, int(c * 0.35 + 90)) for c in base_color)
            elif node_id in available_nodes:
                fill_color = base_color
            else:
                fill_color = tuple(int(c * 0.45) for c in base_color)
            
            pg.draw.circle(surface, fill_color, center, radius)
            border_width = int((5 if is_selected else 2) * MAP_ICON_SCALE)
            pg.draw.circle(surface, border_color, center, radius, border_width)

        if node.node_type != "boss":
            label = CAMPAIGN_NODE_DISPLAY.get(node.node_type, node.node_type)
            label_font = get_font_bold(MAP_ICON_LABEL_FONT_SIZE)
            label_surf = label_font.render(label, True, WHITE)
            label_rect = label_surf.get_rect(center=(center[0], center[1] + radius + MAP_ICON_LABEL_OFFSET))
            surface.blit(label_surf, label_rect)

        if node.cleared:
            check_surf = get_font(20).render("√", True, HUD_COLOR)
            surface.blit(check_surf, check_surf.get_rect(center=center))

    sidebar_x = SCREEN_WIDTH - 280
    sidebar_y = 90
    sidebar_w = 220
    sidebar_h = SCREEN_HEIGHT - sidebar_y - 180
    pg.draw.rect(surface, GRID_COLOR, (sidebar_x, sidebar_y, sidebar_w, sidebar_h), 2)
    info_font = get_font(22)
    y = sidebar_y + 20
    stat_lines = [
        f"天数：{campaign_state.day}",
        f"金钱：{campaign_state.gold}",
        f"战斗完成：{campaign_state.battle_count}",
        f"可选节点：{len(available_nodes)}",
    ]
    line_height = 30
    for text in stat_lines:
        surf = info_font.render(text, True, HUD_COLOR)
        surface.blit(surf, (sidebar_x + 16, y))
        y += line_height

    y += 18
    instruction_lines = [
        "方向键移动，回车进入",
        "PgUp/PgDn 滚动",
        "Esc 返回主菜单",
    ]
    instruction_font = get_font(20)
    instruction_height = 26
    for text in instruction_lines:
        surf = instruction_font.render(text, True, HUD_COLOR)
        surface.blit(surf, (sidebar_x + 16, y))
        y += instruction_height

    y += 20

    if cursor_node_id is not None and cursor_node_id in campaign_state.nodes:
        node = campaign_state.nodes[cursor_node_id]
        detail_top = y
        detail_lines = [
            f"节点：{CAMPAIGN_NODE_DISPLAY.get(node.node_type, node.node_type)}",
            "状态：" + ("已完成" if node.cleared else ("可进入" if cursor_node_id in available_nodes else "暂未解锁")),
        ]
        if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            detail_lines.append("类型：战斗节点")
        elif node.node_type == "rest":
            detail_lines.append("类型：休整节点")
        elif node.node_type == "event":
            detail_lines.append("类型：随机事件")
        else:
            detail_lines.append("类型：特殊节点")

        enemy_detail_units: List = []
        if node.node_type in CAMPAIGN_BATTLE_NODE_TYPES:
            preview_keys = enemy_previews.get(node.node_id, []) if enemy_previews else []
            for key in preview_keys:
                ut = UNIT_TYPES.get(key)
                if ut:
                    enemy_detail_units.append(ut)

        detail_font = get_font(20)
        line_spacing = 28
        icon_radius = 10
        for idx, line in enumerate(detail_lines):
            line_y = detail_top + idx * line_spacing
            surf = detail_font.render(line, True, WHITE)
            surface.blit(surf, (sidebar_x + 16, line_y))

        enemy_start_idx = len(detail_lines)
        for offset, ut in enumerate(enemy_detail_units):
            line_y = detail_top + (enemy_start_idx + offset) * line_spacing
            icon_x = sidebar_x + 16
            icon_y = line_y + detail_font.get_height() // 2
            draw_unit(surface, icon_x, icon_y, ut.shape, ut.color, icon_radius, facing_left=False, ut=ut)
            text_x = icon_x + icon_radius * 2 + 8
            label = f"敌军：{ut.name}"
            surf = detail_font.render(label, True, WHITE)
            surface.blit(surf, (text_x, line_y))

    if message:
        msg_font = get_font(22)
        msg_surf = msg_font.render(message, True, HUD_ACCENT)
        surface.blit(msg_surf, msg_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)))


def draw_campaign_shop(
    surface: pg.Surface,
    font: pg.font.Font,
    items: list[dict],
    cursor_idx: int,
    gold: int,
    message: str,
    item_cost: int,
    refresh_cost: int,
    unit_levels: dict | None = None,
):
    global STORE_BG_SURFACE
    if STORE_BG_SURFACE is None:
        STORE_BG_SURFACE = _load_cached_background("STORE_BG_SURFACE", "store_bg.png")
    if STORE_BG_SURFACE:
        surface.blit(STORE_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)

    unit_levels = unit_levels or {}

    _blit_text(surface, get_font(36), "局内商店", (60, 40), WHITE)

    _blit_text(surface, get_font(24), f"当前金币：{gold}", (60, 90), WHITE)

    _blit_text(
        surface,
        get_font(18),
        f"商品价格：{item_cost} 金    刷新价格：{refresh_cost} 金 (按 R)",
        (60, 126),
        WHITE,
    )

    _blit_text(surface, get_font(18), "←→↑↓ 选择  空格/回车 购买  R 刷新  Esc 离开", (60, 156), WHITE)

    cols = 2
    card_w = 280
    card_h = 210
    gap_x = 48
    gap_y = 36
    total_cols_width = cols * card_w + (cols - 1) * gap_x
    start_x = SCREEN_WIDTH // 2 - total_cols_width // 2
    start_y = SCREEN_HEIGHT // 2 - card_h - gap_y // 2

    for idx in range(4):
        row = idx // cols
        col = idx % cols
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)
        rect = pg.Rect(x, y, card_w, card_h)
        is_cursor = idx == cursor_idx
        border_color = HUD_ACCENT if is_cursor else GRID_COLOR
        border_w = 4 if is_cursor else 2
        pg.draw.rect(surface, border_color, rect, border_w, border_radius=10)

        entry = items[idx] if idx < len(items) else {"key": None, "sold": False}
        key = entry.get("key") if isinstance(entry, dict) else None
        sold = bool(entry.get("sold")) if isinstance(entry, dict) else False
        locked = bool(entry.get("locked")) if isinstance(entry, dict) else False

        pad_x = x + 18
        pad_y = y + 18

        if locked:
            _blit_text(surface, get_font(22), "已封锁", (pad_x, pad_y), WHITE)
            _blit_text(surface, get_font(16), "抢劫惩罚：该格不可用", (pad_x, pad_y + 30), WHITE)
        elif not key:
            _blit_text(surface, get_font(22), "暂时缺货", (pad_x, pad_y), WHITE)
        elif key.startswith("boon_"):
            cfg = BOONS.get(key, {"name": key, "desc": ""})
            _blit_text(surface, get_font(22), cfg.get("name", key), (pad_x, pad_y), WHITE)
            desc = cfg.get("desc", "")
            if desc:
                _blit_text(surface, get_font(16), desc, (pad_x, pad_y + 30), WHITE)
            _blit_text(surface, get_font(16), "类型：增益", (pad_x, pad_y + 58), WHITE)
        elif key in SKILLS:
            cfg = SKILLS.get(key, {"name": key, "desc": "", "cost": 0, "target": ""})
            _blit_text(surface, get_font(22), cfg.get("name", key), (pad_x, pad_y), WHITE)
            desc = cfg.get("desc", "")
            if desc:
                _blit_text(surface, get_font(16), desc, (pad_x, pad_y + 30), WHITE)
            target_map = {"global": "全局", "lane": "战线"}
            target = target_map.get(cfg.get("target"), cfg.get("target", "-"))
            info = f"费用：{cfg.get('cost', 0)} 击杀    目标：{target}"
            _blit_text(surface, get_font(16), info, (pad_x, pad_y + 58), WHITE)
        else:
            ut = UNIT_TYPES.get(key)
            display_name = ut.name if ut else key
            _blit_text(surface, get_font(22), display_name, (pad_x, pad_y), WHITE)
            if ut:
                desc = _short_desc(ut)
                _blit_text(surface, get_font(16), desc, (pad_x, pad_y + 30), WHITE)
                stats = f"费{ut.cost} HP{ut.hp} 速{int(ut.speed)} {('远' if ut.is_ranged else '近')} 程{int(ut.range)} 伤{ut.damage} 攻速{ut.cooldown:.1f}"
                if ut.is_ranged:
                    stats += f" 弹{int(ut.projectile_speed)}"
                _blit_text(surface, get_font(16), stats, (pad_x, pad_y + 58), WHITE)
                current_level = unit_levels.get(key, 0)
                next_level = min(MAX_UNIT_LEVEL, current_level + 1 if current_level > 0 else 1)
                current_label = f"Lv{current_level}" if current_level > 0 else "未解锁"
                level_line = f"等级：{current_label} → Lv{next_level}"
                _blit_text(surface, get_font(16), level_line, (pad_x, pad_y + 86), WHITE)
                draw_unit(surface, x + card_w // 2, y + card_h - 60, ut.shape, ut.color, 18, facing_left=False, ut=ut)

        price_text = "已售出" if sold else f"价格：{item_cost} 金"
        price_color = WHITE if not sold else GRID_COLOR
        _blit_text(surface, get_font(18), price_text, (pad_x, y + card_h - 36), price_color)

        if sold and key:
            overlay = pg.Surface((card_w, card_h), pg.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            surface.blit(overlay, (x, y))
            sold_text = _outline_text(get_font(24), "已售出", WHITE, (0, 0, 0), 2)
            surface.blit(sold_text, sold_text.get_rect(center=rect.center))

    if message:
        msg_surf = _outline_text(get_font(20), message, WHITE, (0, 0, 0), 2)
        surface.blit(msg_surf, msg_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 70)))


def draw_campaign_shop_v2(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    """M4 商店：结构化商品 + 免费刷新 + 捐赠/抢劫。"""
    global STORE_BG_SURFACE
    if STORE_BG_SURFACE is None:
        STORE_BG_SURFACE = _load_cached_background("STORE_BG_SURFACE", "store_bg.png")
    if STORE_BG_SURFACE:
        surface.blit(STORE_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)

    if not campaign_run or not campaign_run.state:
        _blit_text(surface, get_font(26), "商店数据缺失", (60, 80), YELLOW)
        return

    gold = campaign_run.state.gold
    rep = campaign_run.reputation
    _blit_text(surface, get_font_bold(40), "商店", (60, 40), WHITE)
    _blit_text(surface, get_font(24), f"金币：{gold}    声望：{rep}", (60, 96), WHITE)

    free_left = int(getattr(campaign_run, "shop_free_refresh_left", 0) or 0)
    paid_n = int(getattr(campaign_run, "shop_refresh_paid_count", 0) or 0)
    next_refresh_cost = SHOP_REFRESH_BASE_COST * max(1, paid_n + 1)
    refresh_line = f"免费刷新：{free_left} 次    下一次付费刷新：{next_refresh_cost} 金（R）"
    _blit_text(surface, get_font(20), refresh_line, (60, 130), HUD_COLOR)

    tips = "←→↑↓ 选择  回车购买  R刷新  D捐赠  X抢劫  Esc离开"
    _blit_text(surface, get_font(18), tips, (60, 158), HUD_COLOR)

    items = campaign_run.shop_items or []
    cursor = int(getattr(campaign_run, "shop_cursor", 0) or 0)
    cols = 2
    card_w = 520
    card_h = 240
    gap_x = 50
    gap_y = 40
    start_x = 120
    start_y = 220

    desc_font = get_font(18)
    name_font = get_font_bold(26)

    for idx in range(4):
        row = idx // cols
        col = idx % cols
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)
        rect = pg.Rect(x, y, card_w, card_h)
        selected = idx == cursor
        pg.draw.rect(surface, (22, 22, 30), rect, border_radius=14)
        pg.draw.rect(surface, (255, 220, 0) if selected else GRID_COLOR, rect, width=3, border_radius=14)

        entry = items[idx] if idx < len(items) else {"type": "empty", "sold": False, "price": 0, "name": "空", "desc": ""}
        sold = bool(entry.get("sold"))
        locked = bool(entry.get("locked"))
        nm = str(entry.get("name", ""))
        desc = str(entry.get("desc", ""))
        price = int(entry.get("price", 0) or 0)

        surface.blit(name_font.render(nm, True, WHITE), (x + 16, y + 14))
        lines = _wrap_text(desc_font, desc, card_w - 32)
        yy = y + 58
        for ln in lines[:5]:
            surface.blit(desc_font.render(ln, True, HUD_COLOR), (x + 16, yy))
            yy += 22

        if locked:
            price_txt = "已封锁"
        else:
            price_txt = "已售出" if sold else (f"价格：{price} 金" if price > 0 else "价格：-")
        surface.blit(get_font(20).render(price_txt, True, GRID_COLOR if sold else WHITE), (x + 16, y + card_h - 36))

        if locked:
            overlay = pg.Surface((card_w, card_h), pg.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            surface.blit(overlay, (x, y))
            tag = _outline_text(get_font_bold(28), "封锁", WHITE, (0, 0, 0), 2)
            surface.blit(tag, tag.get_rect(center=(x + card_w // 2, y + card_h // 2)))
        elif sold:
            overlay = pg.Surface((card_w, card_h), pg.SRCALPHA)
            overlay.fill((0, 0, 0, 110))
            surface.blit(overlay, (x, y))

    if campaign_run.shop_message:
        msg_surf = _outline_text(get_font(20), campaign_run.shop_message, WHITE, (0, 0, 0), 2)
        surface.blit(msg_surf, msg_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 70)))

    # 抢劫确认弹框（modal）
    if bool(getattr(campaign_run, "shop_robbery_confirm", False)):
        # 背景遮罩
        overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # 弹框主体
        box_w = 900
        box_h = 360
        box_x = (SCREEN_WIDTH - box_w) // 2
        box_y = (SCREEN_HEIGHT - box_h) // 2
        box = pg.Rect(box_x, box_y, box_w, box_h)
        pg.draw.rect(surface, (24, 24, 34), box, border_radius=16)
        pg.draw.rect(surface, (255, 220, 0), box, width=3, border_radius=16)

        title = "确认抢劫商店？"
        title_surf = _outline_text(get_font_bold(36), title, WHITE, (0, 0, 0), 2)
        surface.blit(title_surf, (box_x + 28, box_y + 22))

        # 内容（直接复用 shop_message，保证与实际效果一致）
        body = str(getattr(campaign_run, "shop_message", "") or "")
        body_font = get_font(22)
        lines = _wrap_text(body_font, body, box_w - 56)
        yy = box_y + 86
        for ln in lines[:8]:
            surface.blit(body_font.render(ln, True, HUD_COLOR), (box_x + 28, yy))
            yy += 30

        hint = "回车/空格：确认抢劫    Esc/X：取消"
        hint_surf = _outline_text(get_font(20), hint, WHITE, (0, 0, 0), 2)
        surface.blit(hint_surf, (box_x + 28, box_y + box_h - 54))


def draw_campaign_event(surface: pg.Surface, font: pg.font.Font, message: str):
    """事件结果界面：全屏背景 + 居中文本"""
    global EVENT_BG_SURFACE
    if EVENT_BG_SURFACE is None:
        EVENT_BG_SURFACE = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if EVENT_BG_SURFACE:
        surface.blit(EVENT_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)

    _blit_text(surface, get_font(36), "事件", (60, 40), WHITE)

    msg_text = message or "获得奖励"
    msg_font = get_font(28)
    msg_surf = _outline_text(msg_font, msg_text, WHITE, (0, 0, 0), 2)
    surface.blit(msg_surf, msg_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

    hint_surf = _outline_text(get_font(18), "按 空格/回车/ESC 返回地图", WHITE, (0, 0, 0), 2)
    surface.blit(hint_surf, hint_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)))


def draw_campaign_event_choice(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    if not campaign_run or not campaign_run.state:
        _blit_text(surface, get_font(26), "事件数据缺失", (60, 120), YELLOW)
        return

    _blit_text(surface, get_font_bold(48), f"事件：{campaign_run.event_title}", (60, 50), WHITE)
    _blit_text(surface, get_font(22), campaign_run.event_desc, (60, 118), HUD_COLOR)

    choice = int(getattr(campaign_run, "event_choice_idx", 0) or 0)
    opts = [campaign_run.event_option_a or "A：-", campaign_run.event_option_b or "B：-"]

    card_w = 620
    card_h = 240
    gap = 60
    start_x = 120
    y = 220
    desc_font = get_font(20)
    for i in range(2):
        x = start_x + i * (card_w + gap)
        rect = pg.Rect(x, y, card_w, card_h)
        pg.draw.rect(surface, (22, 22, 30), rect, border_radius=16)
        pg.draw.rect(surface, (255, 220, 0) if i == choice else GRID_COLOR, rect, width=3, border_radius=16)
        lines = _wrap_text(desc_font, opts[i], card_w - 32)
        yy = y + 24
        for ln in lines[:7]:
            surface.blit(desc_font.render(ln, True, WHITE), (x + 16, yy))
            yy += 28

    _blit_text(surface, get_font(20), "←/→ 选择A/B  回车确认", (60, SCREEN_HEIGHT - 60), GRID_COLOR)


def draw_campaign_combo_select(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("UPGRADE_BG_SURFACE", "upgrade_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    if not campaign_run:
        _blit_text(surface, get_font(26), "Combo数据缺失", (60, 120), YELLOW)
        return

    ctx_map = {
        "shop": "商店",
        "event": "事件",
        "elite": "精英",
        "battle3": "第3战",
        "nonbattle2": "探索",
        "elite_win": "精英首胜",
        "pity": "保底",
    }
    ctx = ctx_map.get(campaign_run.combo_context, campaign_run.combo_context or "未知")
    _blit_text(surface, get_font_bold(48), f"Combo（三选一）- {ctx}", (60, 50), WHITE)

    selected = campaign_run.combo.selected_cards or []
    if selected:
        names = [str(COMBO_CARDS.get(cid, {}).get("name", cid)) for cid in selected]
        _blit_text(surface, get_font(20), "已选：" + " / ".join(names), (60, 118), HUD_COLOR)

    opts = campaign_run.combo_options or []
    idx = int(getattr(campaign_run, "combo_idx", 0) or 0)
    card_w = 420
    card_h = 320
    gap = 40
    start_x = 90
    y = 200
    name_font = get_font_bold(28)
    desc_font = get_font(18)

    for i, cid in enumerate(opts[:3]):
        x = start_x + i * (card_w + gap)
        rect = pg.Rect(x, y, card_w, card_h)
        pg.draw.rect(surface, (22, 22, 30), rect, border_radius=16)
        pg.draw.rect(surface, (255, 220, 0) if i == idx else GRID_COLOR, rect, width=3, border_radius=16)
        cfg = COMBO_CARDS.get(cid, {})
        nm = cfg.get("name", cid)
        desc = cfg.get("desc", "")
        tags = cfg.get("tags", [])
        surface.blit(name_font.render(str(nm), True, WHITE), (x + 16, y + 16))
        surface.blit(get_font(18).render("标签：" + "/".join([str(t) for t in tags]), True, HUD_COLOR), (x + 16, y + 56))
        lines = _wrap_text(desc_font, str(desc), card_w - 32)
        yy = y + 90
        for ln in lines[:9]:
            surface.blit(desc_font.render(ln, True, WHITE), (x + 16, yy))
            yy += 22

    reroll_hint = "（按 R 可重抽一次）" if campaign_run.oneshot.next_combo_reroll_once else ""
    _blit_text(surface, get_font(20), f"←/→ 选择  回车确认 {reroll_hint}", (60, SCREEN_HEIGHT - 60), GRID_COLOR)

def draw_loadout(
    surface: pg.Surface,
    font: pg.font.Font,
    loadout_units,
    unit_levels,
    cursor_idx,
    focus,
    skill_idx,
    loadout_skills,
    max_units: int = 5,
    max_skills: int = 1,
):
    global FORMATION_BG_SURFACE
    # 尝试加载配阵背景
    if FORMATION_BG_SURFACE is None:
        FORMATION_BG_SURFACE = _load_specific_background("formation_bg.png")
    
    if FORMATION_BG_SURFACE:
        surface.blit(FORMATION_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    title = get_font(44).render("配阵", True, WHITE)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 54)))

    # 兵种选择行
    grid_top = 170  # 下移，避免与操作提示重合
    cols = 6
    slot_w = 128  # 扩卡：更宽的格子
    slot_h = 96   # 扩卡：更高的格子，避免文字压线
    r = 22        # 模型半径变大，显示更清晰
    unit_card_w = 108
    unit_left_pad = 38
    unit_grid_w = unit_card_w + (cols - 1) * slot_w
    unit_start_x = (SCREEN_WIDTH - unit_grid_w) // 2 + unit_left_pad
    unit_levels = unit_levels or {}
    unit_lim_text = "无限" if max_units is None or max_units <= 0 else str(max_units)
    skill_lim_text = "0" if max_skills == 0 else ("无限" if max_skills is None or max_skills < 0 else str(max_skills))
    tips_line = (
        f"左右移动 空格选/取消（兵种最多{unit_lim_text} 技能最多{skill_lim_text}） 自由模式可重复空格提升等级  "
        "Tab 切换焦点 上下切换技能行 回车保存 / Esc 返回"
    )
    tips = get_font(22).render(tips_line, True, HUD_COLOR)
    surface.blit(tips, (60, 90))
    unit_title = get_font(29).render("兵种", True, WHITE)
    surface.blit(unit_title, (60, grid_top - 36))

    for i, k in enumerate(ORDER_KEYS):
        ut = UNIT_TYPES[k]
        row = i // cols
        col = i % cols
        x = unit_start_x + col * slot_w
        y = grid_top + row * slot_h
        selected = (k in loadout_units)
        is_focus = (focus == "units" and i == cursor_idx)
        border_color = HUD_ACCENT if is_focus else GRID_COLOR
        border_w = 3 if is_focus else 1
        rect = pg.Rect(x - 38, y - 22, 108, 60)
        # 底色卡片
        card_color = (20, 24, 32)
        card_alpha = 200 if selected else 140
        card = pg.Surface(rect.size, pg.SRCALPHA)
        card.fill((*card_color, card_alpha))
        surface.blit(card, rect.topleft)
        if is_focus:
            glow = pg.Surface(rect.inflate(10, 10).size, pg.SRCALPHA)
            pg.draw.rect(glow, (*HUD_ACCENT, 60), glow.get_rect(), border_radius=6)
            surface.blit(glow, rect.inflate(10, 10).topleft)
        pg.draw.rect(surface, border_color, rect, border_w, border_radius=6)
        draw_unit(surface, x + 16, y + 6, ut.shape, ut.color, r, facing_left=False, ut=ut)
        mark = get_font(19).render(("√" if selected else " "), True, HUD_ACCENT if selected else GRID_COLOR)
        surface.blit(mark, (x + 50, y - 10))
        name_text = str(ut.name)
        if selected:
            level_val = max(1, unit_levels.get(k, 1))
            name_text = f"{name_text}  Lv{level_val}"
        name_surf = get_font(16).render(name_text, True, HUD_COLOR if not selected else HUD_ACCENT)
        surface.blit(name_surf, (x - 32, y - 42))

    rows = (len(ORDER_KEYS) - 1) // cols + 1
    if max_units and max_units > 0:
        count_text_val = f"{len(loadout_units)}/{unit_lim_text}"
    else:
        count_text_val = f"{len(loadout_units)}/∞"
    count_text = get_font(22).render(f"已选兵种 {count_text_val}", True, HUD_COLOR)
    surface.blit(count_text, (unit_start_x - unit_left_pad, grid_top + rows * slot_h - 20))

    # 技能选择行（max_skills==0 时隐藏：用于战役“开局无技能”）
    show_skills = (max_skills is None) or (max_skills > 0)
    skills: list[tuple[str, str]] = []
    skill_y = grid_top + rows * slot_h + 70
    if show_skills:
        skills = [(key, f"{str(SKILLS[key]['name'])}({SKILLS[key]['cost']}杀)") for key in SKILL_ORDER]
        skill_cols = 5
        box_w = 220
        box_h = 48
        gap_x = 220
        gap_y = 60
        skill_grid_w = box_w + (skill_cols - 1) * gap_x
        skill_start_x = (SCREEN_WIDTH - skill_grid_w) // 2 + 12
        skill_title = get_font(29).render("特殊技能", True, WHITE)
        surface.blit(skill_title, (60, skill_y - 42))
        slot_labels = ["Q", "W", "E"]
        for idx, (key, label) in enumerate(skills):
            row = idx // skill_cols
            col = idx % skill_cols
            cur_x = skill_start_x + col * gap_x
            cur_y = skill_y + row * gap_y
            sel = key in loadout_skills
            cur = (focus == "skill" and skill_idx == idx)
            color = HUD_ACCENT if sel else HUD_COLOR
            border = HUD_ACCENT if cur else GRID_COLOR
            rect = pg.Rect(cur_x - 6, cur_y - 18, box_w, box_h)
            pg.draw.rect(surface, border, rect, 2)
            suffix = ""
            if sel:
                try:
                    slot_idx = loadout_skills.index(key)
                    if 0 <= slot_idx < len(slot_labels):
                        suffix = f" [{slot_labels[slot_idx]}]"
                except ValueError:
                    suffix = ""
            mark = "√" if sel else " "
            txt = get_font(21).render(f"{mark} {label}{suffix}", True, color)
            txt_rect = txt.get_rect(midleft=(cur_x + 6, cur_y))
            surface.blit(txt, txt_rect)

        skill_count_val = f"{len(loadout_skills)}/{skill_lim_text}"
        skill_rows = (len(skills) - 1) // skill_cols + 1
        skill_count = get_font(21).render(f"已选技能 {skill_count_val}", True, HUD_COLOR)
        surface.blit(skill_count, (skill_start_x - 12, skill_y + skill_rows * gap_y))

    else:
        note = "战役开局无技能：技能仅可在商店购买（最多3个）"
        _blit_text(surface, get_font(22), note, (60, skill_y), HUD_COLOR, outline_px=2)

    # 详情面板：放在下方（无论是否显示技能区都要有）
    panel_x = 60
    panel_y = (skill_y + 240) if not show_skills else (skill_y + ((len(skills) - 1) // 5 + 1) * 60 + 20)
    lines: list[str] = []

    if show_skills and focus == "skill" and 0 <= skill_idx < len(skills):
        skill_key = skills[skill_idx][0]
        cfg = SKILLS.get(skill_key, {})
        target_map = {"global": "全局", "lane": "战线"}
        target_text = target_map.get(cfg.get("target"), cfg.get("target", "-"))
        owned_tag = "√ 已选择" if skill_key in loadout_skills else "未选择"
        lines = [
            f"技能: {cfg.get('name', skill_key)}",
            owned_tag,
            f"费用: {cfg.get('cost', 0)} 击杀  目标: {target_text}",
            f"说明: {cfg.get('desc', '')}",
        ]
    else:
        ut = UNIT_TYPES[ORDER_KEYS[cursor_idx]]
        stats_line1 = f"费:{ut.cost} HP:{ut.hp} 移速:{int(ut.speed)} 攻速:{ut.cooldown:.1f}"
        stats_line2 = f"{'远程' if ut.is_ranged else '近战'} 射程:{int(ut.range)} 伤害:{ut.damage}"
        if ut.is_ranged:
            stats_line2 += f" 弹速:{int(ut.projectile_speed)}"

        tag_parts = []
        if getattr(ut, 'is_aoe', False):
            tag_parts.append(f"AOE:{int(getattr(ut, 'aoe_radius', 0))}")
        if getattr(ut, 'is_healer', False):
            tag_parts.append(f"治疗:{getattr(ut, 'heal_amount', 0)}")
        if getattr(ut, 'is_buffer', False):
            tag_parts.append("增益")
        if getattr(ut, 'intercept_radius', 0.0) > 0.0:
            tag_parts.append("拦截弹道")

        meta = _lookup_unit_meta(ut)
        short_text = meta.get("short") if meta else _short_desc(ut)
        highlight_parts = []
        if short_text:
            highlight_parts.append(f"亮点:{short_text}")
        if meta and meta.get("role"):
            highlight_parts.append(f"定位:{meta['role']}")
        
        # 提取兵种标签
        unit_tags = getattr(ut, "tags", [])
        tag_display = " | ".join([t.upper() for t in unit_tags]) if unit_tags else ""

        lines = [f"名称: {ut.name}", stats_line1, stats_line2]
        if tag_display:
            lines.append(f"属性: {tag_display}")
        if tag_parts:
            lines.append(" | ".join(tag_parts))
        if highlight_parts:
            lines.append(" | ".join(highlight_parts))
        if meta and meta.get("intro"):
            lines.append(f"打法: {meta['intro']}")
        lines.append(f"满级: {_unit_max_level_summary(ut)}")

    py = panel_y + 16
    for t in lines:
        s = get_font(22).render(t, True, HUD_COLOR)
        surface.blit(s, (panel_x + 12, py))
        py += 29


def draw_encyclopedia(surface: pg.Surface, font: pg.font.Font, scroll_offset: int = 0):
    global WIKI_BG_SURFACE
    # 尝试加载百科背景
    if WIKI_BG_SURFACE is None:
        # 与配阵相同的暗色背景
        WIKI_BG_SURFACE = _load_specific_background("formation_bg.png")
    
    if WIKI_BG_SURFACE:
        surface.blit(WIKI_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    title_font = get_font(40)
    title = title_font.render("百科", True, WHITE)
    surface.blit(title, (80, 60))

    # 操作说明
    lines = [
        "操作说明:",
        "- 上/下：选择生产战线",
        "- 左/右：切换兵种",
        "- 空格：在当前战线出兵",
        "- Esc：返回主菜单/退出（百科中返回主页）",
        "- PgUp/PgDn：战役地图滚动",
        "- 鼠标滚轮：百科/地图滚动",
        "",
        "战役地图指南:",
        "- 配阵完成后进入节点式地图，按方向键选择下层节点推进",
        "- 战斗胜利固定掉落金钱：首战100，每场+10，事件+50",
        "- 时间奖励：1分钟内通关+120金，2分钟内+60金，3分钟内+30金",
        "- 休整节点恢复基地HP，商店可购买兵种/技能/增益（250金/件，R刷新-50金）",
        "- 难度提升：每过一天敌军伤害+5%，生命+3%，右侧面板可预览敌军兵种",
        "- 奖励机制：已解锁兵种在奖励选择中概率+50%，更容易获得高级兵种",
        "",
        "兵种升级:",
        "- 兵种可升至Lv4，2级和3级全属性+5%（每级+5%）",
        "- 4级与3级属性相同（+10%），并解锁满级特效",
        "",
        "兵种数值:",
    ]

    # 内容裁剪区域
    content_top = 120
    content_bottom = SCREEN_HEIGHT - 60
    clip_rect = pg.Rect(60, content_top, SCREEN_WIDTH - 120, content_bottom - content_top)
    prev_clip = surface.get_clip()
    surface.set_clip(clip_rect)

    y = content_top - scroll_offset
    for t in lines:
        surf = get_font(font.get_height()).render(t, True, HUD_COLOR)
        surface.blit(surf, (80, y))
        y += 28

    # 兵种（两列卡片式）
    col_x = [80, SCREEN_WIDTH // 2 + 20]
    body_font = get_font(21)
    body_gap = body_font.get_height() + 6
    row_h = 200
    cur_row = 0
    cur_col = 0
    for key in ORDER_KEYS:
        ut = UNIT_TYPES[key]
        bx = col_x[cur_col]
        by = y + cur_row * row_h
        # 兵种模型展示（与配阵一致）
        draw_unit(surface, bx + 46, by + 46, ut.shape, ut.color, 22, facing_left=False, ut=ut)
        name_font = get_font(27)  # 18 * 1.5
        name = name_font.render(ut.name, True, HUD_ACCENT)
        meta = _lookup_unit_meta(ut)
        short_text = meta.get("short") if meta else _short_desc(ut)
        role_text = meta.get("role") if meta else None
        intro_text = meta.get("intro") if meta else None
        stats = f"费{ut.cost} HP{ut.hp} 速{int(ut.speed)} {'远' if ut.is_ranged else '近'} 程{int(ut.range)} 伤{ut.damage} 攻速{ut.cooldown:.1f}"
        if ut.is_ranged:
            stats += f" 弹{int(ut.projectile_speed)}"
        stats_surf = body_font.render(stats, True, HUD_COLOR)
        max_effect = _max_level_effect_text(key)

        surface.blit(name, (bx + 90, by + 4))
        line_y = by + 40  # 留出与名称的垂直间距
        if short_text:
            surface.blit(body_font.render(f"亮点：{short_text}", True, HUD_COLOR), (bx + 90, line_y))
            line_y += body_gap
        if role_text:
            surface.blit(body_font.render(f"定位：{role_text}", True, HUD_COLOR), (bx + 90, line_y))
            line_y += body_gap
        if intro_text:
            surface.blit(body_font.render(f"打法：{intro_text}", True, HUD_COLOR), (bx + 90, line_y))
            line_y += body_gap
        surface.blit(stats_surf, (bx + 90, line_y))
        line_y += body_gap
        if max_effect:
            surface.blit(body_font.render(f"满级效果：{max_effect}", True, HUD_COLOR), (bx + 90, line_y))
        # next position
        if cur_col == 0:
            cur_col = 1
        else:
            cur_col = 0
            cur_row += 1

    # 复原裁剪
    surface.set_clip(prev_clip)

    # 滚动条指示
    pg.draw.rect(surface, GRID_COLOR, clip_rect, 1)

    back = get_font(font.get_height()).render("Esc 返回主页", True, HUD_COLOR)
    surface.blit(back, (80, SCREEN_HEIGHT - 50))


def _short_desc(ut) -> str:
    meta = _lookup_unit_meta(ut)
    if meta and meta.get("short"):
        return meta["short"]
    if getattr(ut, 'is_buffer', False):
        return "光环加速与攻速增益"
    if getattr(ut, 'is_healer', False):
        return "远程治疗，无攻击"
    if getattr(ut, 'is_charger', False) and getattr(ut, 'knockback_factor', 0) > 0:
        return "冲锋命中击退"
    if getattr(ut, 'is_charger', False):
        return "冲锋突破阻挡"
    if getattr(ut, 'bonus_vs_charge_mult', 1.0) > 1.0:
        return "克制冲锋并可打断"
    if getattr(ut, 'intercept_radius', 0.0) > 0.0:
        return "拦截敌方投射物"
    if getattr(ut, 'split_on_death', False):
        return "死亡分裂为小体"
    if getattr(ut, 'projectile_slow_stack', 0) > 0:
        return "远程叠减速，满层眩晕一次"
    if getattr(ut, 'is_aoe', False) and ut.is_ranged:
        return "远程范围伤害"
    if getattr(ut, 'is_aoe', False):
        return "近战范围伤害"
    if getattr(ut, 'prioritize_high_damage', False):
        return "优先攻击高伤目标"
    return "远程单体" if ut.is_ranged else "近战单体"


def _max_level_effect_text(key: str) -> str:
    effect_map = {
        "warrior": "首次受击无敌5秒",
        "shield": "被攻击反伤20%",
        "maul": "重锤命中附带48范围眩晕",
        "berserker": "攻击吸血20%",
        "priest": "治疗范围提升至120",
        "archer": "箭矢可穿透1个目标并启用伤害衰减",
        "mage": "攻击附带点燃（半径60，3秒，每秒60%伤害）",
        "rhino": "第4次击退触发1秒眩晕",
        "assassin": "己方半场隐身",
        "interceptor": "反弹伤害转治疗8%",
        "drummer": "为友军施加25%最大生命护盾（10秒一次，持续5秒）",
        "spearman": "控制免疫",
        "frost_archer": "满层眩晕范围提升至60",
        "exploder": "自爆后留下燃烧（半径70，5秒，每秒35伤害）",
        "light_cavalry": "冲锋冷却缩短至2秒",
    }
    return effect_map.get(key, "")


def draw_reward_picker(surface: pg.Surface, font: pg.font.Font, options: list, selected_idx: int, unit_levels: dict | None = None):
    global UPGRADE_BG_SURFACE
    if UPGRADE_BG_SURFACE is None:
        UPGRADE_BG_SURFACE = _load_cached_background("UPGRADE_BG_SURFACE", "upgrade_bg.png")
    if UPGRADE_BG_SURFACE:
        surface.blit(UPGRADE_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    _blit_text(surface, get_font(36), "奖励选择（3选1）", (60, 40), WHITE)

    unit_levels = unit_levels or {}

    if not options:
        _blit_text(surface, get_font(20), "兵种已达上限，自动进入下一关……", (60, 100), WHITE)
        return

    center_y = SCREEN_HEIGHT // 2
    start_x = SCREEN_WIDTH // 2 - 360
    card_w = 240
    gap = 40

    for i, key in enumerate(options):
        is_boon = isinstance(key, str) and key.startswith("boon_")
        is_skill = isinstance(key, str) and key in SKILLS
        x = start_x + i * (card_w + gap)
        rect = pg.Rect(x, center_y - 120, card_w, 220)
        border = HUD_ACCENT if i == selected_idx else GRID_COLOR
        pg.draw.rect(surface, border, rect, 2)
        if is_boon:
            cfg = BOONS.get(key, {"name": key, "desc": key})
            _blit_text(surface, get_font(18), cfg.get("name", key), (x + 12, center_y - 110), WHITE)
            _blit_text(surface, get_font(14), cfg.get("desc", ""), (x + 12, center_y - 86), WHITE)
            _blit_text(surface, get_font(14), "增益卡", (x + 12, center_y - 62), WHITE)
        elif is_skill:
            cfg = SKILLS.get(key, {"name": key})
            _blit_text(surface, get_font(18), cfg.get("name", key), (x + 12, center_y - 110), WHITE)
            _blit_text(surface, get_font(14), cfg.get("desc", ""), (x + 12, center_y - 86), WHITE)
            target_map = {"global": "全局", "lane": "战线"}
            target_text = target_map.get(cfg.get("target"), cfg.get("target", "-"))
            stats = f"费用 {cfg.get('cost', 0)} 击杀  目标 {target_text}"
            _blit_text(surface, get_font(14), stats, (x + 12, center_y - 62), WHITE)
            _blit_text(surface, get_font(14), "特殊技能", (x + 12, center_y - 38), WHITE)
        else:
            ut = UNIT_TYPES[key]
            _blit_text(surface, get_font(18), ut.name, (x + 12, center_y - 110), WHITE)
            _blit_text(surface, get_font(14), _short_desc(ut), (x + 12, center_y - 86), WHITE)
            stats = f"费{ut.cost} HP{ut.hp} 速{int(ut.speed)} {'远' if ut.is_ranged else '近'} 程{int(ut.range)} 伤{ut.damage} 攻速{ut.cooldown:.1f}"
            if ut.is_ranged:
                stats += f" 弹{int(ut.projectile_speed)}"
            _blit_text(surface, get_font(14), stats, (x + 12, center_y - 62), WHITE)
            current_level = unit_levels.get(key, 0)
            next_level = min(MAX_UNIT_LEVEL, current_level + 1 if current_level > 0 else 1)
            current_label = f"Lv{current_level}" if current_level > 0 else "未解锁"
            level_line = f"等级：{current_label} → Lv{next_level}"
            _blit_text(surface, get_font(14), level_line, (x + 12, center_y - 38), WHITE)
            draw_unit(surface, x + card_w // 2, center_y + 20, ut.shape, ut.color, 14, facing_left=False, ut=ut)
    _blit_text(surface, get_font(18), "←/→ 选择  回车/空格 确认  Esc 放弃", (60, SCREEN_HEIGHT - 50), WHITE)


def draw_campaign_victory(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    """通关结算：展示 Combo/祝福/锻造摘要（不再展示旧 boon）。"""
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    title = get_font_bold(56).render("战役通关", True, HUD_ACCENT)
    surface.blit(title, (60, 40))

    if not campaign_run or not campaign_run.state:
        info = get_font(26).render("本局数据缺失。按 Esc/回车 返回主菜单。", True, YELLOW)
        surface.blit(info, (60, 140))
        return

    gold = campaign_run.state.gold
    battle_count = campaign_run.state.battle_count
    day = campaign_run.state.day
    rep = getattr(campaign_run, "reputation", 0)
    total_time = float(getattr(campaign_run, "total_time", 0.0) or 0.0)

    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    blessing_key = campaign_run.blessing_selected
    blessing = BLESSINGS.get(blessing_key, {}).get("name", blessing_key) if blessing_key else "（无）"

    combo_selected = campaign_run.combo.selected_cards if getattr(campaign_run, "combo", None) else []
    combo_names = [str(COMBO_CARDS.get(cid, {}).get("name", cid)) for cid in (combo_selected or [])]
    combo_text = " / ".join(combo_names) if combo_names else "（无）"

    executed_n = sum(1 for v in (campaign_run.prisoners.executed_once or {}).values() if v)
    joined_n = sum(1 for v in (campaign_run.prisoners.joined_once or {}).values() if v)

    stat_lines = [
        f"总用时：{minutes:02d}:{seconds:02d}",
        f"金币：{gold}    声望：{rep}",
        f"战斗场次：{battle_count}    天数：{day}",
        f"祝福：{blessing}",
        f"Combo：{combo_text}",
        f"俘虏记录：归顺{joined_n} / 处决{executed_n}",
    ]

    x0, y0 = 60, 130
    for i, ln in enumerate(stat_lines):
        _blit_text(surface, get_font(26), ln, (x0, y0 + i * 34), WHITE, outline_px=2)

    # 兵种/技能/锻造摘要
    y = y0 + len(stat_lines) * 34 + 18
    _blit_text(surface, get_font_bold(30), "兵种：", (60, y), WHITE, outline_px=2)
    y += 38
    if campaign_run.units:
        for k in campaign_run.units[:10]:
            lv = campaign_run.unit_levels.get(k, 1)
            ut = UNIT_TYPES.get(k)
            name = ut.name if ut else k
            _blit_text(surface, get_font(24), f"- {name}  Lv{lv}", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无兵种）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    y += 10
    _blit_text(surface, get_font_bold(30), "技能：", (60, y), WHITE, outline_px=2)
    y += 38
    if campaign_run.skills:
        for sk in campaign_run.skills[:6]:
            cfg = SKILLS.get(sk, {})
            nm = cfg.get("name", sk)
            _blit_text(surface, get_font(24), f"- {nm}", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    y += 10
    _blit_text(surface, get_font_bold(30), "锻造：", (60, y), WHITE, outline_px=2)
    y += 38
    forge_levels = getattr(getattr(campaign_run, "forge", None), "level_by_unit", {}) or {}
    forge_dirs = getattr(getattr(campaign_run, "forge", None), "locked_direction", {}) or {}
    if campaign_run.units:
        shown = 0
        for k in campaign_run.units:
            lvl = int(forge_levels.get(k, 0) or 0)
            if lvl <= 0 and k not in forge_dirs:
                continue
            d = forge_dirs.get(k)
            d_txt = "攻" if d == "offense" else ("防" if d == "defense" else "未定")
            ut = UNIT_TYPES.get(k)
            name = ut.name if ut else k
            _blit_text(surface, get_font(24), f"- {name}：{d_txt} {lvl}级", (60, y), HUD_COLOR, outline_px=2)
            y += 30
            shown += 1
            if shown >= 6:
                break
        if shown == 0:
            _blit_text(surface, get_font(24), "（本局无锻造）", (60, y), HUD_COLOR, outline_px=2)
            y += 30
    else:
        _blit_text(surface, get_font(24), "（无）", (60, y), HUD_COLOR, outline_px=2)
        y += 30

    tips = get_font(20).render("回车/空格：再来一局    Esc：返回主菜单", True, GRID_COLOR)
    tips_rect = tips.get_rect()
    tips_rect.bottomright = (SCREEN_WIDTH - 60, SCREEN_HEIGHT - 40)
    surface.blit(tips, tips_rect)


def draw_boon_select(surface: pg.Surface, font: pg.font.Font, boons: dict, cursor_idx: int):
    global FORMATION_BG_SURFACE
    if FORMATION_BG_SURFACE is None:
        FORMATION_BG_SURFACE = _load_specific_background("formation_bg.png")
    if FORMATION_BG_SURFACE:
        surface.blit(FORMATION_BG_SURFACE, (0, 0))
    else:
        surface.fill(BACKGROUND_COLOR)
    _blit_text(surface, get_font(48), "增益选择（自由模式：任意选择/叠层）", (60, 40), WHITE)
    _blit_text(surface, get_font(27), "↑↓ 移动  ←/→ 调整层数  空格+1层  回车确认  Esc返回", (60, 110), WHITE)

    keys = list(BOONS.keys())
    start_y = 140
    row_h = 48
    for i, bid in enumerate(keys):
        cfg = BOONS[bid]
        selected = (i == cursor_idx)
        name = cfg.get("name", bid)
        desc = cfg.get("desc", "")
        level = boons.get(bid, 0)
        line_text = f"[{level}/{cfg['max']}] {name} - {desc}"
        color = HUD_ACCENT if selected else WHITE
        _blit_text(surface, get_font(24), line_text, (80, start_y + i * row_h), color)


def _lookup_unit_meta(ut) -> Optional[Dict[str, str]]:
    key = getattr(ut, "key", "")
    if not key:
        return None
    return UNIT_BOOK.get(key)


def _unit_max_level_summary(ut) -> str:
    # Lv4 与 Lv3 属性相同（+10%），仅额外解锁特效
    if MAX_UNIT_LEVEL >= 3:
        mult = 1.10
    else:
        mult = 1.0 + UNIT_LEVEL_STEP * (MAX_UNIT_LEVEL - 1)
    hp = int(round(ut.hp * mult))
    dmg = int(round(ut.damage * mult))
    speed = int(round(ut.speed * mult))
    rng = int(round(ut.range * mult))
    cooldown = max(0.05, ut.cooldown / mult)
    parts = [f"HP {hp}", f"伤害 {dmg}", f"速度 {int(speed)}", f"射程 {rng}", f"攻速 {cooldown:.2f}"]
    if ut.is_ranged:
        parts.append(f"弹速 {int(round(ut.projectile_speed * mult))}")
    heal_amount = getattr(ut, "heal_amount", 0)
    if heal_amount > 0:
        parts.append(f"治疗 {int(round(heal_amount * mult))}")
    explode = getattr(ut, "death_explode_damage", 0)
    if explode > 0:
        parts.append(f"爆炸 {int(round(explode * mult))}")
    return " / ".join(parts)


def draw_campaign_event_unit_select(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    """绘制事件中的选兵界面"""
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    candidates = getattr(campaign_run, "event_candidates", [])
    if not campaign_run or (not campaign_run.units and not candidates):
        _blit_text(surface, get_font(26), "没有可选择的兵种", (60, 120), YELLOW)
        return

    action_text = "请选择要操作的兵种"
    if campaign_run.event_pending_action == "delete_unit_for_skill":
        action_text = "血肉祭坛：选择要献祭的兵种（1-5）"
    elif campaign_run.event_pending_action == "forge_to_3":
        action_text = f"禁忌重铸：选择要强化的兵种（1-5）"
        if campaign_run.event_pending_target:
            victim_name = UNIT_TYPES.get(campaign_run.event_pending_target).name if UNIT_TYPES.get(campaign_run.event_pending_target) else campaign_run.event_pending_target
            action_text += f"\n（{victim_name}的锻造已归零）"
    elif campaign_run.event_pending_action == "royal_summon_choice":
        action_text = "皇家征召：请选择要解锁的兵种（1-2）"

    _blit_text(surface, get_font_bold(36), action_text, (60, 50), WHITE)
    _blit_text(surface, get_font(20), "按 ESC 取消", (60, 110), HUD_COLOR)

    # 绘制兵种列表
    y = 180
    display_list = candidates if candidates else campaign_run.units
    for i, uk in enumerate(display_list):
        ut = UNIT_TYPES.get(uk)
        name = ut.name if ut else uk
        level = campaign_run.unit_levels.get(uk, 1) if not candidates else 0
        lv_str = f" (Lv{level})" if level > 0 else " (待解锁)"
        
        rect = pg.Rect(80, y + i * 80, 1280, 70)
        pg.draw.rect(surface, (30, 30, 40), rect, border_radius=8)
        pg.draw.rect(surface, GRID_COLOR, rect, width=2, border_radius=8)
        
        _blit_text(surface, get_font(24), f"[{i+1}] {name}{lv_str}", (100, y + i * 80 + 20), WHITE)

    _blit_text(surface, get_font(18), "提示：按数字键 1-5 选择对应兵种", (60, 750), (150, 150, 150))


def draw_campaign_event_skill_select(surface: pg.Surface, font: pg.font.Font, campaign_run: CampaignRunState | None):
    """绘制事件中的选技能界面"""
    surface.fill(BACKGROUND_COLOR)
    bg = _load_cached_background("EVENT_BG_SURFACE", "event_bg.png")
    if bg:
        surface.blit(bg, (0, 0))

    if not campaign_run or not campaign_run.skills:
        _blit_text(surface, get_font(26), "没有可选择的技能", (60, 120), YELLOW)
        return

    action_text = "知识荒废：选择要遗忘的技能（1-4）"
    _blit_text(surface, get_font_bold(36), action_text, (60, 50), WHITE)
    _blit_text(surface, get_font(20), "按 ESC 取消", (60, 110), HUD_COLOR)

    # 绘制技能列表
    y = 180
    from .constants import SKILLS
    for i, sk in enumerate(campaign_run.skills):
        skill_data = SKILLS.get(sk, {})
        name = skill_data.get("name", sk)
        desc = skill_data.get("desc", "")
        
        rect = pg.Rect(80, y + i * 100, 1280, 90)
        pg.draw.rect(surface, (30, 30, 40), rect, border_radius=8)
        pg.draw.rect(surface, GRID_COLOR, rect, width=2, border_radius=8)
        
        _blit_text(surface, get_font(24), f"[{i+1}] {name}", (100, y + i * 100 + 15), WHITE)
        _blit_text(surface, get_font(18), desc, (100, y + i * 100 + 50), HUD_COLOR)

    _blit_text(surface, get_font(18), "提示：按数字键 1-4 选择对应技能", (60, 750), (150, 150, 150))

