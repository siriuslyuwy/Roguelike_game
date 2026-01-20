from __future__ import annotations

import os
from functools import lru_cache
import pygame as pg


ASSET_CANDIDATES = [
    os.path.join("assets", "fonts", "NotoSansSC-Regular.otf"),
    os.path.join("assets", "fonts", "NotoSansSC-Regular.ttf"),
    os.path.join("assets", "fonts", "SourceHanSansSC-Regular.otf"),
    os.path.join("assets", "fonts", "SourceHanSansSC-Regular.ttf"),
    os.path.join("assets", "fonts", "msyh.ttc"),  # 微软雅黑
]

SYSTEM_FONT_CANDIDATES = [
    "Microsoft YaHei",  # 微软雅黑
    "SimHei",           # 黑体
    "DengXian",         # 等线
    "SimSun",           # 宋体
    "Noto Sans CJK SC",
    "Arial Unicode MS",
]


def _load_base_font(size: int) -> pg.font.Font:
    # 1) 先尝试项目内置字体
    for path in ASSET_CANDIDATES:
        if os.path.exists(path):
            try:
                return pg.font.Font(path, size)
            except Exception:
                continue

    # 2) 回退系统字体
    for name in SYSTEM_FONT_CANDIDATES:
        try:
            f = pg.font.SysFont(name, size)
            if f:
                return f
        except Exception:
            continue

    # 3) 最后兜底（可能仍无中文，但尽量不崩）
    return pg.font.Font(None, size)


class OutlinedFont:
    """包装字体，统一输出白字黑描边（保持字号/粗细）。"""

    def __init__(self, base: pg.font.Font):
        self._base = base

    def render(self, text, antialias=True, color=(255, 255, 255), background=None):
        # Ensure any Translatable or non-str objects render safely
        text = str(text)
        base_surf = self._base.render(text, antialias, color, background)
        outline_px = 2
        if outline_px <= 0:
            return base_surf
        w, h = base_surf.get_size()
        surf = pg.Surface((w + outline_px * 2, h + outline_px * 2), pg.SRCALPHA)
        outline = self._base.render(text, antialias, (0, 0, 0), background)
        for dx in (-outline_px, 0, outline_px):
            for dy in (-outline_px, 0, outline_px):
                if dx == 0 and dy == 0:
                    continue
                surf.blit(outline, (dx + outline_px, dy + outline_px))
        surf.blit(base_surf, (outline_px, outline_px))
        return surf

    def __getattr__(self, item):
        return getattr(self._base, item)


@lru_cache(maxsize=64)
def get_font(size: int) -> pg.font.Font:
    return OutlinedFont(_load_base_font(size))


@lru_cache(maxsize=64)
def get_font_bold(size: int) -> pg.font.Font:
    """加粗版字体，用于需要更高可读性的文字。"""
    font = _load_base_font(size)
    font.set_bold(True)
    return OutlinedFont(font)


