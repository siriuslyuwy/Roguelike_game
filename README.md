# Geometry Wars: Seven Lines

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![pygame](https://img.shields.io/badge/pygame-2.5%2B-green?logo=pygame)
![Status](https://img.shields.io/badge/Status-WIP-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

A side-scrolling tactical strategy game with Roguelike progression — 7 independent battle lines, 15+ unit types, and deep build customization through a node-based campaign map.

> Destroy 4 of the enemy's 7 bases to win. Every line is its own battlefield.

---

## Features

- **7 Independent Battle Lines** — Each line has its own fog of war, unit queue, and base health. Macro-level decisions about where to focus pressure define the game.
- **15+ Distinct Units** — From the Assassin (bypasses frontline) and Ice Archer (stackable stun) to the Rhino (AOE knockback) and Exploder (suicide bomber), every unit has a unique mechanical niche.
- **Campaign Mode** — A 20-node map inspired by *Slay the Spire*: choose your path through battles, events, shops, and rest sites. Each victory grants a 3-way choice of unit unlock, skill, or permanent buff.
- **Free Mode** — Freeform army composition with custom buff configuration for unrestricted experimentation.
- **Skill System (Q / W / E)** — Active abilities powered by a kill-score resource, rewarding aggressive play.
- **Unit Progression** — Units level up to Lv4. Max-level units gain special passive effects that change how they interact on the field.
- **Buff System** — Meta-progression layer with stackable multipliers affecting specific unit types or global stats.
- **Wiki / Codex** — In-game reference covering controls, unit stats, and ability descriptions.

## Installation

**Requirements:** Python 3.9+, pygame 2.5+

```bash
# Clone the repository
git clone https://github.com/yourusername/sevenlines.git
cd sevenlines

# Install dependencies
pip install -r requirements.txt

# Run the game
python main.py
```

## Controls

| Key | Action |
|-----|--------|
| `↑` / `↓` | Switch active battle line |
| `←` / `→` | Cycle unit selection |
| `Space` | Deploy selected unit |
| `Q` / `W` / `E` | Activate skill 1 / 2 / 3 |
| `Esc` | Return to menu / pause |

## Project Structure

```
├── main.py              # Entry point
├── requirements.txt
├── roguelike_game/      # Main game module
│   ├── constants.py     # Game config & balancing
│   ├── entities.py      # Units, projectiles, bases
│   ├── game.py          # Core game state & AI logic
│   ├── ui.py            # Rendering & HUD
│   └── save_system.py   # Save/load (WIP)
└── game/
    └── sprites.py
```

## Roadmap

- [ ] **Save / Load System** — Persist campaign progress across sessions
- [ ] **English Localization** — Full text pass for all UI, unit descriptions, and events
- [ ] **Multiplayer Support** — Local or network PvP across the 7 lines

---

Built with Python + pygame. Solo project.

---
---

# 几何大战：七条战线

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![pygame](https://img.shields.io/badge/pygame-2.5%2B-green?logo=pygame)
![Status](https://img.shields.io/badge/状态-开发中-yellow)

一款横版战术策略游戏，融合肉鸽(Roguelike)成长元素。7条独立战线同时展开，通过战略布阵、技能调度与增益积累，率先摧毁敌方4座基地获胜。

> 核心胜负条件：率先摧毁对手7座基地中的4座。每一条战线都是独立的战场。

---

## 核心特性

### 7条独立战线
每条战线拥有独立的迷雾视野、出兵队列和基地血量。宏观上如何分配兵力压制与防守，是决定胜负的关键。

### 15种以上兵种
每种单位都有独特的机制定位：

| 兵种 | 核心机制 |
|------|---------|
| 刺客 | 无视前排直接攻击后方单位 |
| 截击手 | 拦截敌方弓箭并反弹 |
| 犀牛 | AOE冲锋，附带大范围击退 |
| 冰弓 | 每次攻击叠加眩晕层数 |
| 自爆车 | 接近敌阵时自爆，造成范围伤害 |
| 狂战士 | 低血量进入狂暴状态，攻速大幅提升 |
| 圣骑士 | 正面防御，配合后排输出 |
| 法师 | 魔法穿透，无视护甲 |
| …… | 共15种以上 |

### 正常模式（类杀戮尖塔）
20层节点战役地图，每个节点类型各异（战斗、精英战、Boss、事件、商店、休息）。每场战斗胜利后提供三选一奖励：解锁新兵种、获得技能、或获取永久增益。

### 自由模式
不受节点限制，自由配置阵容与增益组合，适合深度测试和策略探索。

### 技能系统
Q / W / E 三个主动技能槽，以击杀积分为资源消耗，鼓励积极进攻的打法风格。

### 兵种升级系统
单位可升级至 Lv4，满级单位解锁专属被动特效，部分特效会改变该兵种的基本交战逻辑。

### 增益系统（局外成长）
可跨局积累的增益层，针对特定兵种或全局属性提供叠加倍率，构建专属流派。

### 百科系统
内置操作说明与兵种数值参考，新手友好。

---

## 安装与运行

**环境要求：** Python 3.9+，pygame 2.5+

```bash
# 克隆仓库
git clone https://github.com/yourusername/sevenlines.git
cd sevenlines

# 安装依赖
pip install -r requirements.txt

# 启动游戏
python main.py
```

---

## 操作说明

| 按键 | 功能 |
|------|------|
| `↑` / `↓` | 切换当前操作战线 |
| `←` / `→` | 切换选择兵种 |
| `空格` | 在当前战线出兵 |
| `Q` / `W` / `E` | 释放技能 1 / 2 / 3 |
| `Esc` | 返回菜单 / 暂停 |

---

## 项目结构

```
├── main.py              # 程序入口
├── requirements.txt
├── roguelike_game/      # 主游戏模块
│   ├── constants.py     # 游戏配置与数值平衡
│   ├── entities.py      # 单位、投射物、基地
│   ├── game.py          # 核心游戏状态与AI逻辑
│   ├── ui.py            # 渲染与HUD界面
│   └── save_system.py   # 存档读档（开发中）
└── game/
    └── sprites.py
```

---

## 开发计划 (Roadmap)

- [ ] **存档/读档系统** — 战役进度持久化保存
- [ ] **英文本地化** — 完整UI、兵种描述与事件文本的英文翻译
- [ ] **多人对战** — 本地或联网PvP模式

---

个人独立项目，使用 Python + pygame 开发。
