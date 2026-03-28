from __future__ import annotations

import math

from .localization import tr


SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
FPS = 60

LANE_COUNT = 7
LEFT_MARGIN = 80
RIGHT_MARGIN = 80
TOP_UI_HEIGHT = 190
BOTTOM_MARGIN = 50

BACKGROUND_COLOR = (18, 18, 24)
LANE_COLOR = (40, 44, 52)
GRID_COLOR = (60, 64, 72)
TOP_PANEL_COLOR = (26, 28, 36)

WHITE = (235, 235, 235)
GREEN = (70, 200, 120)
RED = (230, 70, 70)
YELLOW = (240, 210, 60)
CYAN = (80, 200, 220)
MAGENTA = (200, 80, 220)
ORANGE = (255, 140, 0)
BLUE = (80, 140, 255)

HUD_COLOR = (210, 210, 210)
HUD_ACCENT = (120, 200, 255)


def lane_y_positions(height: int = SCREEN_HEIGHT, lane_count: int = LANE_COUNT) -> list[int]:
    # 在顶部 UI 面板与底部边距之间均匀分布战线
    top = TOP_UI_HEIGHT + 20
    bottom = height - BOTTOM_MARGIN
    span = max(1, bottom - top)
    return [int(top + (i + 1) * span / (lane_count + 1)) for i in range(lane_count)]


BASE_MAX_HP = 375
BASES_TO_WIN = 4

# 单线基地展示尺寸（UI 用）
LANE_BASE_BAR_W = 14
LANE_BASE_BAR_H = 40

# 肉鸽 20 关参数（可调整）
CAMPAIGN_PARAMS = {
    "base_hp_scale": [1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5, 1.55, 1.6, 1.65, 1.7, 1.75, 1.8, 1.85, 1.9, 2.0],
    "ai_interval_mult": [1.2, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.68, 0.65, 0.62, 0.6, 0.58, 0.55, 0.52, 0.5, 0.48],
    "ai_pool_sizes": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 15, 15, 15, 15, 15],
}

# 肉鸽模式敌方伤害每日递增百分比（可调整）
# 调低中后段斜率：更容易把“能撑到中段但推不动”的局转化为通关
CAMPAIGN_ENEMY_DAMAGE_GROWTH = 0.04
# 肉鸽模式敌方生命每日递增百分比（可调整）
CAMPAIGN_ENEMY_HP_GROWTH = 0.025

CAMPAIGN_BATTLE_NODE_TYPES = {"combat", "elite", "boss"}

CAMPAIGN_NODE_DISPLAY = {
    "combat": tr("战斗", "Battle"),
    "elite": tr("精英", "Elite"),
    "event": tr("事件", "Event"),
    "rest": tr("休整", "Rest"),
    "shop": tr("商店", "Shop"),
    "boss": tr("首领", "Boss"),
}

CAMPAIGN_NODE_COLORS = {
    "combat": (88, 180, 255),
    "elite": (255, 120, 80),
    "event": (180, 140, 255),
    "rest": (120, 200, 120),
    "shop": (255, 210, 90),
    "boss": (255, 70, 120),
}

CAMPAIGN_BASE_GOLD = 100
CAMPAIGN_GOLD_INCREMENT = 10
CAMPAIGN_EVENT_GOLD = 50

# 增益卡定义（id -> 配置）
BOONS = {
    "boon_eco": {
        "name": tr("富足协定", "Prosperity Pact"),
        "desc": tr("资源增长+20%，上限+200（最多2层）", "Resource growth +20%, cap +200 (max 2 stacks)"),
        "max": 2,
        "econ_rate": 0.20,
        "res_cap": 200,
    },
    "boon_hp": {
        "name": tr("钢铁编制", "Steel Formation"),
        "desc": tr("全体最大HP+15%（最多2层）", "All units max HP +15% (max 2 stacks)"),
        "max": 2,
        "hp_mult": 0.15,
    },
    "boon_speed_charge": {
        "name": tr("急速军令", "Rapid Orders"),
        "desc": tr("移速+12%；冲锋击退+15%（移速最多2层）", "Move speed +12%; charge knockback +15% (speed max 2 stacks)"),
        "max": 2,
        "speed_mult": 0.12,
        "knockback_bonus": 0.15,
    },
    "boon_haste": {
        "name": tr("连击战术", "Combo Tactics"),
        "desc": tr("攻速+10%（最多3层）", "Attack speed +10% (max 3 stacks)"),
        "max": 3,
        "cd_mult": 0.90,
        "cd_floor": 0.5,
    },
    "boon_spawn_shield": {
        "name": tr("先锋护盾", "Vanguard Shield"),
        "desc": tr("新出兵3秒护盾=10%HP（最多2层）", "New units gain shield = 10% HP for 3s (max 2 stacks)"),
        "max": 2,
        "shield_pct": 0.10,
        "shield_duration": 3.0,
    },
    "boon_refund": {
        "name": tr("斩获征募", "Recruitment Bounty"),
        "desc": tr("击杀返还生产成本（20%/35%），10秒最多5次", "Kills refund production cost (20%/35%), max 5 times per 10s"),
        "max": 2,
        "refund_rate_first": 0.20,
        "refund_rate_second": 0.35,
        "limit_per_10s": 5,
    },
    "boon_skill": {
        "name": tr("战术超频", "Tactical Overclock"),
        "desc": tr("技能充能阈值-25%/-32.5%，充能上限+1", "Skill charge threshold -25%/-32.5%, max charges +1"),
        "max": 2,
        "threshold_mult_first": 0.75,
        "threshold_mult_next": 0.90,
    },
    "boon_frost": {
        "name": tr("霜寒强化", "Frost Reinforcement"),
        "desc": tr("减速持续+1s/2s；寒冰眩晕+0.4s/0.8s", "Slow duration +1s/2s; frost stun +0.4s/0.8s"),
        "max": 2,
        "slow_extra": 1.0,
        "stun_extra": 0.4,
    },
    "boon_pierce": {
        "name": tr("穿云箭", "Piercing Arrow"),
        "desc": tr("远程穿透+1/+2，后续目标伤害衰减30%", "Ranged pierce +1/+2, subsequent target damage falls off 30%"),
        "max": 2,
        "pierce_each": 1,
        "falloff": 0.30,
    },
    "boon_proj_resist": {
        "name": tr("弹雨庇护", "Hail Shelter"),
        "desc": tr("投射物伤害-15%/-28%", "Projectile damage -15%/-28%"),
        "max": 2,
        "reduction_first": 0.15,
        "reduction_second": 0.28,
    },
}

# 技能配置（按选择顺序）
SKILLS = {
    "spawn": {
        "name": tr("全军出击", "Full Assault"),
        "desc": tr("全线召唤当前兵种各一名", "Summon one of the current unit type on every lane"),
        "cost": 35,
        "target": "global",
    },
    "frost_ray": {
        "name": tr("冰霜射线", "Frost Ray"),
        "desc": tr("指定战线敌军眩晕4秒", "Stun enemies on the target lane for 4s"),
        "cost": 15,
        "target": "lane",
    },
    "death_ray": {
        "name": tr("死亡射线", "Death Ray"),
        "desc": tr("指定战线敌军瞬间消灭", "Instantly eliminate enemies on the target lane"),
        "cost": 25,
        "target": "lane",
    },
    "boom": {
        "name": tr("轰轰轰", "Boom Boom Boom"),
        "desc": tr("指定战线敌军承受3次150点AOE", "Enemies on the target lane take 3 AOE hits of 150"),
        "cost": 15,
        "target": "lane",
    },
    "guardian": {
        "name": tr("爸爸救我", "Guardian"),
        "desc": tr("指定战线友军获得50%最大生命护盾", "Allies on the target lane gain shield = 50% max HP"),
        "cost": 12,
        "target": "lane",
    },
    "black_hole": {
        "name": tr("黑洞", "Black Hole"),
        "desc": tr("指定战线敌军聚拢并禁锢3秒", "Pull enemies together and root them for 3s on the target lane"),
        "cost": 12,
        "target": "lane",
    },
    "windfall": {
        "name": tr("来财", "Windfall"),
        "desc": tr("立即获得300资源", "Gain 300 resources immediately"),
        "cost": 15,
        "target": "global",
    },
    "gotcha": {
        "name": tr("你上当了", "Gotcha"),
        "desc": tr("指定战线基地5秒无敌并处决入侵者", "Target lane base is invulnerable for 5s and executes invaders"),
        "cost": 15,
        "target": "lane",
    },
    "origei": {
        "name": tr("奥里给", "Origei"),
        "desc": tr("全军8秒内+50%伤害与移速", "All units gain +50% damage and move speed for 8s"),
        "cost": 15,
        "target": "global",
    },
}

SKILL_ORDER = [
    "spawn",
    "frost_ray",
    "death_ray",
    "boom",
    "guardian",
    "black_hole",
    "windfall",
    "gotcha",
    "origei",
]

# 资源与经济
STARTING_RESOURCE = 100
RESOURCE_PER_SEC = 12
MAX_RESOURCE = 999

# === AI 渐进式资源增长（用于“非镜像Boss”）===
# 说明：
# - 以“关卡阶段(stage)”计数：第1关对应 stage=1（stage_idx=0）
# - 从第 AI_RESOURCE_GROWTH_START_STAGE 关开始，每关线性提高 AI 回资源倍率
# - 同时线性提高 AI 资源上限，避免高倍率下过早顶到上限
AI_RESOURCE_GROWTH_START_STAGE = 4
AI_RESOURCE_GROWTH_PER_STAGE = 0.03     # 每关 +3% 回资源
AI_RESOURCE_CAP_GROWTH_PER_STAGE = 0.05 # 每关 +5% 资源上限

# === M3：锻造 / 俘虏 / 祝福（DEMO参数，可后续平衡）===
# 锻造：改锻费用基数（基于兵种当前总等级递增）
FORGE_RETARGET_BASE_COST = 30
FORGE_RETARGET_PER_LEVEL_COST = 10  # 每个锻造等级增加的改锻费用

# 俘虏：放归/处决金币收益（基础值）
PRISONER_RELEASE_GOLD = 80
PRISONER_EXECUTE_GOLD = 60
# 俘虏：声望变动（加快反馈）
PRISONER_REP_GAIN = 2  # 放归获得的声望
PRISONER_REP_LOSS = 2  # 处决失去的声望

# 声望夹断（DEMO推荐）
REPUTATION_MIN = -20
REPUTATION_MAX = 20

# 祝福池：10个经营流派（核心战役政策，每局4选1）
BLESSINGS = {
    "veteran_unyielding": {
        "name": tr("不屈之志", "Unyielding Will"),
        "desc": tr(
            "开局战士升至2级并获得2攻2防锻造；解锁老兵的商店购买与锻造权限",
            "Start with Warrior at level 2 and gain +2 attack/+2 defense forging; unlock Veteran shop purchases and forging",
        ),
        "tags": ["老兵", "锻造"],
    },
    "veteran_mentor": {
        "name": tr("教官光环", "Instructor Aura"),
        "desc": tr(
            "老兵HP+60%/伤害-40%；老兵正后方的单位获得+6%攻速+6%伤害",
            "Veteran HP +60% / damage -40%; units directly behind gain +6% attack speed and +6% damage",
        ),
        "tags": ["老兵", "阵型"],
    },
    "veteran_sacrifice": {
        "name": tr("英雄祭献", "Heroic Sacrifice"),
        "desc": tr(
            "第5关起无法部署老兵；补偿：所有其他伙伴基础属性+50%",
            "From stage 5, Veteran cannot be deployed; compensation: all other companions base stats +50%",
        ),
        "tags": ["老兵", "养成"],
    },
    "looter_logic": {
        "name": tr("掠夺者逻辑", "Raider Logic"),
        "desc": tr("全局金币获取+50%（战斗、事件、俘虏等所有来源）", "Global gold gain +50% (battle, event, prisoners, all sources)"),
        "tags": ["经济", "战斗"],
    },
    "ring_of_destiny": {
        "name": tr("宿命之环", "Ring of Destiny"),
        "desc": tr(
            "名声决定命运：圣人路线(正名声)提供攻速加成，暴君路线(负名声)提供伤害加成；1点名声=1.5%数值",
            "Reputation shapes fate: Saint route (positive rep) grants attack speed, Tyrant route (negative rep) grants damage; 1 rep = 1.5%",
        ),
        "tags": ["经济", "名声"],
    },
    "elite_simplicity": {
        "name": tr("精兵简政", "Elite Simplicity"),
        "desc": tr(
            "最大兵种数量限制为3种（含战士）；补偿：全属性+30%",
            "Max unit types limited to 3 (incl. Warrior); compensation: all stats +30%",
        ),
        "tags": ["养成", "限制"],
    },
    "steel_tide": {
        "name": tr("钢铁洪流", "Steel Tide"),
        "desc": tr(
            "所有单位费用/CD减半；代价：单位HP/伤害永久-25%",
            "All units cost/CD halved; tradeoff: unit HP/damage permanently -25%",
        ),
        "tags": ["战斗", "爆兵"],
    },
    "tactical_master": {
        "name": tr("战术大师", "Tactical Master"),
        "desc": tr("技能不再消耗击杀数，改为消耗金币/资源", "Skills no longer cost kills; now cost gold/resources"),
        "tags": ["技能", "资源"],
    },
    "veteran_last_stand": {
        "name": tr("破釜沉舟", "Last Stand"),
        "desc": tr(
            "仅战士部署费为0，改为扣除基地5点生命；其他兵种正常消费",
            "Only Warrior deployment cost becomes 0, instead costs 5 base HP; other units pay normally",
        ),
        "tags": ["老兵", "卖血"],
    },
    "craftsman_spirit": {
        "name": tr("匠人精神", "Craftsman Spirit"),
        "desc": tr(
            "锻造成功率100%，解锁4/5级锻造；代价：取消俘虏处置环节",
            "Forging success 100%, unlock level 4/5 forging; tradeoff: remove prisoner handling",
        ),
        "tags": ["锻造", "极限"],
    },
}

# 锻造高阶等级定义（仅匠人精神祝福解锁）
FORGE_LEVEL_4_BONUS = 0.80  # 4级总加成：+80%
FORGE_LEVEL_5_BONUS = 1.20  # 5级总加成：+120%
FORGE_LEVEL_4_SUCCESS_RATE = 0.25  # 4级基础成功率：25%
FORGE_LEVEL_5_SUCCESS_RATE = 0.10  # 5级基础成功率：10%

# === M4：商店 / Combo / 事件（DEMO参数，可调）===
SHOP_REFRESH_BASE_COST = 50
SHOP_ITEM_PRICE_LOW = 120
SHOP_ITEM_PRICE_MED = 200
SHOP_ITEM_PRICE_HIGH = 280

SHOP_DONATE_GOLD_COST = 100
SHOP_DONATE_REP_GAIN = 2
SHOP_ROB_GOLD_GAIN = 300
SHOP_ROB_REP_LOSS = 3

# 事件金币量级（先用三档，便于统一调参）
EVENT_GOLD_SMALL = 60
EVENT_GOLD_MED = 120
EVENT_GOLD_LARGE = 200

# === M4.1：里程碑式发放（降低“地图依赖”波动）===
# 说明：
# - BLESSING：首战后给一次
# - COMBO1：第3战后给第1张
# - COMBO2：累计完成 N 次非战斗节点后给第2张；若一直没走非战斗则战斗数兜底
# - COMBO3：首次击败精英后给第3张；若一直不打精英则战斗数兜底
BLESSING_TRIGGER_BATTLE_COUNT = 1
COMBO1_TRIGGER_BATTLE_COUNT = 3
COMBO2_TRIGGER_NONBATTLE_COUNT = 2
COMBO2_PITY_BATTLE_COUNT = 6
COMBO3_PITY_BATTLE_COUNT = 9

# Combo 卡池（24张分层设计：12基础 + 12联动）
COMBO_CARDS = {
    # === 第一层：基础职能加成 (12张) ===
    "combo_heavy_armor": {
        "name": tr("厚甲整备", "Heavy Armor Prep"),
        "desc": tr("坦克单位最大HP +25%", "Tank units max HP +25%"),
        "tags": ["tank"],
        "target_tags": ["tank"],
        "bonus_type": "hp",
        "bonus_value": 0.25,
    },
    "combo_sharpened_blades": {
        "name": tr("锋刃淬炼", "Sharpened Blades"),
        "desc": tr("输出单位伤害 +20%", "DPS unit damage +20%"),
        "tags": ["dps"],
        "target_tags": ["dps"],
        "bonus_type": "damage",
        "bonus_value": 0.20,
    },
    "combo_medical_kit": {
        "name": tr("战地医疗包", "Field Medkit"),
        "desc": tr("支援单位治疗/护盾量 +35%", "Support unit heal/shield +35%"),
        "tags": ["support"],
        "target_tags": ["support"],
        "bonus_type": "heal",
        "bonus_value": 0.35,
    },
    "combo_disruption": {
        "name": tr("干扰信号", "Disruption Signal"),
        "desc": tr("控制单位控制时长 +35%", "Control duration +35%"),
        "tags": ["control"],
        "target_tags": ["control"],
        "bonus_type": "control_duration",
        "bonus_value": 0.35,
    },
    "combo_heavy_payload": {
        "name": tr("重型装药", "Heavy Payload"),
        "desc": tr("AOE效果半径 +40%", "AOE radius +40%"),
        "tags": ["aoe"],
        "target_tags": ["aoe"],
        "bonus_type": "aoe_radius",
        "bonus_value": 0.40,
    },
    "combo_rapid_advance": {
        "name": tr("急速军令", "Rapid Advance"),
        "desc": tr("近战单位移速 +20%", "Melee move speed +20%"),
        "tags": ["melee"],
        "target_tags": ["melee"],
        "bonus_type": "speed",
        "bonus_value": 0.20,
    },
    "combo_light_crossbow": {
        "name": tr("轻型连弩", "Light Crossbow"),
        "desc": tr("远程单位攻速 +15%", "Ranged attack speed +15%"),
        "tags": ["ranged"],
        "target_tags": ["ranged"],
        "bonus_type": "attack_speed",
        "bonus_value": 0.15,
    },
    "combo_far_sight": {
        "name": tr("远视之镜", "Far Sight Lens"),
        "desc": tr("远程单位射程 +15%", "Ranged range +15%"),
        "tags": ["ranged"],
        "target_tags": ["ranged"],
        "bonus_type": "range",
        "bonus_value": 0.15,
    },
    "combo_war_funding": {
        "name": tr("军费加拨", "War Funding"),
        "desc": tr("战斗金币奖励 +20%", "Battle gold rewards +20%"),
        "tags": ["经济"],
        "bonus_type": "battle_gold",
        "bonus_value": 0.20,
    },
    "combo_prisoner_bounty": {
        "name": tr("战俘悬赏", "Prisoner Bounty"),
        "desc": tr("俘虏处置金币收益 +20%", "Prisoner handling gold +20%"),
        "tags": ["经济"],
        "bonus_type": "prisoner_gold",
        "bonus_value": 0.20,
    },
    "combo_fortification": {
        "name": tr("紧急加固", "Emergency Fortification"),
        "desc": tr("基地最大生命值 +50%", "Base max HP +50%"),
        "tags": ["防御"],
        "bonus_type": "base_hp",
        "bonus_value": 0.50,
    },
    
    # === 第二层：战术联动 (12张) ===
    "combo_firm_line": {
        "name": tr("坚毅阵线", "Firm Line"),
        "desc": tr("同线同时有坦克和输出时，两者伤害 +15%", "When tank and DPS are on the same lane, both deal +15% damage"),
        "tags": ["联动", "tank", "dps"],
        "trigger_condition": "tank_and_dps_in_lane",
        "bonus_value": 0.15,
    },
    "combo_combined_arms": {
        "name": tr("步炮协同", "Combined Arms"),
        "desc": tr("同线同时有近战和远程时，远程攻速 +25%", "When melee and ranged are on the same lane, ranged attack speed +25%"),
        "tags": ["联动", "melee", "ranged"],
        "trigger_condition": "melee_and_ranged_in_lane",
        "bonus_value": 0.25,
    },
    "combo_dead_recruit": {
        "name": tr("死士招募", "Death Recruit"),
        "desc": tr("每损失5个输出单位，下次部署任意单位免费", "Every 5 DPS deaths, next deployment of any unit is free"),
        "tags": ["联动", "dps"],
        "trigger_condition": "dps_death_count",
        "bonus_value": 5,
    },
    "combo_ice_shatter": {
        "name": tr("碎冰效应", "Ice Shatter"),
        "desc": tr("对受控单位造成的伤害 +20%", "Damage to controlled targets +20%"),
        "tags": ["联动", "control"],
        "trigger_condition": "target_controlled",
        "bonus_value": 0.20,
    },
    "combo_counter_stance": {
        "name": tr("反击姿态", "Counter Stance"),
        "desc": tr("拦截反弹造成的伤害 +30%", "Intercept reflect damage +30%"),
        "tags": ["联动", "support"],
        "trigger_condition": "intercept_reflect",
        "bonus_value": 0.30,
    },
    "combo_aura_resonance": {
        "name": tr("光环共鸣", "Aura Resonance"),
        "desc": tr("光环单位效果范围 +30%", "Aura unit effect radius +30%"),
        "tags": ["联动", "support"],
        "trigger_condition": "aura_buffer",
        "bonus_value": 0.30,
    },
    "combo_overflow_shield": {
        "name": tr("溢出转换", "Overflow Conversion"),
        "desc": tr("治疗溢出部分50%转化为护盾(持续3秒)", "50% of overheal converts to a shield (3s)"),
        "tags": ["联动", "support"],
        "trigger_condition": "heal_overflow",
        "bonus_value": 0.50,
    },
    "combo_logistics": {
        "name": tr("后勤优化", "Logistics Optimization"),
        "desc": tr("所有单位部署费用降低 10%", "All unit deployment costs -10%"),
        "tags": ["联动", "经济"],
        "bonus_type": "cost",
        "bonus_value": 0.10,
    },
    "combo_skill_optimization": {
        "name": tr("战术优化", "Skill Optimization"),
        "desc": tr("技能消耗击杀数降低 15%", "Skill kill-cost -15%"),
        "tags": ["联动", "技能"],
        "bonus_type": "skill_cost",
        "bonus_value": 0.15,
    },
    "combo_shock_armor": {
        "name": tr("震荡铠甲", "Shock Armor"),
        "desc": tr("坦克受击时20%概率眩晕攻击者0.8秒", "Tanks have a 20% chance to stun attackers for 0.8s when hit"),
        "tags": ["联动", "tank"],
        "trigger_condition": "tank_hit_counter",
        "bonus_value": 0.20,
    },
    "combo_emergency_protocol": {
        "name": tr("应急协议", "Emergency Protocol"),
        "desc": tr("每当一个基地爆炸，立即获得250资源", "Whenever a base explodes, gain 250 resources immediately"),
        "tags": ["联动", "防御"],
        "trigger_condition": "base_destroyed",
        "bonus_value": 250,
    },
    "combo_full_suppression": {
        "name": tr("全线压制", "Full Suppression"),
        "desc": tr("场上同时有3条线的友军时，全员伤害 +15%", "If allies occupy 3 lanes at once, all units deal +15% damage"),
        "tags": ["联动", "战线"],
        "trigger_condition": "three_lanes_active",
        "bonus_value": 0.15,
    },
}


class UnitArchetypes:
    # 统一的初始数值；如需微调，改此处即可
    CIRCLE = dict(
        name=tr("战士", "Warrior"),
        tags=["melee", "tank"],
        shape="circle",
        color=CYAN,
        cost=65,
        hp=160,
        speed=100.0,
        damage=20,
        cooldown=0.8,
        range=28,
        is_ranged=False,
        projectile_speed=0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
    )

    SQUARE = dict(
        name=tr("盾卫", "Shield Guard"),
        tags=["melee", "tank"],
        shape="square",
        color=ORANGE,
        cost=80,
        hp=320,
        speed=70.0,
        damage=14,
        cooldown=1.0,
        range=28,
        is_ranged=False,
        projectile_speed=0,
        radius=14,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        attack_animation_duration=0.36,
    )

    TRIANGLE = dict(
        name=tr("大锤", "Maul"),
        tags=["melee", "control"],
        shape="triangle",
        color=YELLOW,
        cost=80,
        hp=120,
        speed=130.0,
        damage=29,
        cooldown=1.7,
        range=28,
        is_ranged=False,
        projectile_speed=0.0,
        radius=14,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        melee_stun_duration=1.8,
        ranged_taken_mult=1.2,
        attack_animation_duration=0.625,
    )

    HEXAGON = dict(
        name=tr("狂战", "Berserker"),
        tags=["melee", "dps", "aoe"],
        shape="hexagon",
        color=GREEN,
        cost=100,
        hp=200,
        speed=95.0,
        damage=18,
        cooldown=0.6,
        range=40,
        is_ranged=False,
        projectile_speed=0.0,
        radius=16,
        is_aoe=True,
        aoe_radius=30.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        attack_animation_duration=0.375,
    )

    PENTAGON = dict(
        name=tr("牧师", "Priest"),
        tags=["ranged", "support"],
        shape="pentagon",
        color=RED,
        cost=90,
        hp=140,
        speed=90.0,
        damage=0,
        cooldown=0.8,
        range=220,
        is_ranged=True,
        projectile_speed=0,
        radius=16,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=True,
        heal_amount=30,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        attack_animation_duration=0.5,
    )

    DIAMOND = dict(
        name=tr("弓手", "Archer"),
        tags=["ranged", "dps"],
        shape="diamond",
        color=BLUE,
        cost=80,
        hp=90,
        speed=110.0,
        damage=21,
        cooldown=1.10,
        range=260,
        is_ranged=True,
        projectile_speed=420.0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        attack_animation_duration=0.5,
    )

    STAR = dict(
        name=tr("法师", "Mage"),
        tags=["ranged", "dps", "aoe"],
        shape="star",
        color=MAGENTA,
        cost=110,
        hp=110,
        speed=95.0,
        damage=19,
        cooldown=1.1,
        range=280,
        is_ranged=True,
        projectile_speed=450.0,
        radius=15,
        is_aoe=True,
        aoe_radius=45.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        attack_animation_duration=0.4,
    )

    # 新增：号手（纯增益）
    DRUMMER = dict(
        name=tr("鼓手", "Drummer"),
        tags=["melee", "support"],
        shape="circle",
        color=BLUE,
        cost=70,
        hp=120,
        speed=95.0,
        damage=0,
        cooldown=1.0,
        range=0,
        is_ranged=False,
        projectile_speed=0.0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        is_buffer=True,
        buff_move_mult=1.20,
        buff_cooldown_mult=0.78,
        # 光环半径设为“可交战宽度”的四分之一，使直径≈半条线
        aura_radius=(SCREEN_WIDTH - LEFT_MARGIN - RIGHT_MARGIN) * 0.25,
        is_charger=False,
        knockback_factor=0.0,
        bonus_vs_charge_mult=1.0,
        charge_interrupt_stun=0.0,
        split_on_death=False,
        split_child_key=None,
        split_children_count=0,
        projectile_slow_stack=0,
        projectile_slow_duration=0.0,
        frost_stun_cap=0,
        frost_stun_duration=0.0,
    )

    # 新增：长矛兵（克制冲锋）
    SPEARMAN = dict(
        name=tr("矛兵", "Spearman"),
        tags=["melee", "control"],
        shape="triangle",
        color=YELLOW,
        cost=70,
        hp=160,
        speed=95.0,
        damage=21,
        cooldown=0.8,
        range=36,
        is_ranged=False,
        projectile_speed=0.0,
        radius=14,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        is_buffer=False,
        buff_move_mult=1.0,
        buff_cooldown_mult=1.0,
        aura_radius=0.0,
        is_charger=False,
        knockback_factor=0.0,
        bonus_vs_charge_mult=1.8,
        charge_interrupt_stun=0.3,
        split_on_death=False,
        split_child_key=None,
        split_children_count=0,
        projectile_slow_stack=0,
        projectile_slow_duration=0.0,
        frost_stun_cap=0,
        frost_stun_duration=0.0,
    )

    # 新增：寒冰射手（减速叠层，满层眩晕一次）
    FROST_ARCHER = dict(
        name=tr("冰弓", "Frost Archer"),
        tags=["ranged", "control"],
        shape="diamond",
        color=CYAN,
        cost=75,
        hp=90,
        speed=100.0,
        damage=13,
        cooldown=1.0,
        range=260,
        is_ranged=True,
        projectile_speed=420.0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        is_buffer=False,
        buff_move_mult=1.0,
        buff_cooldown_mult=1.0,
        aura_radius=0.0,
        is_charger=False,
        knockback_factor=0.0,
        bonus_vs_charge_mult=1.0,
        charge_interrupt_stun=0.0,
        split_on_death=False,
        split_child_key=None,
        split_children_count=0,
        projectile_slow_stack=1,
        projectile_slow_duration=3.0,
        frost_stun_cap=5,
        frost_stun_duration=1.0,
        attack_animation_duration=0.5,
    )

    # 改：自爆车（死亡触发范围伤害）
    SPLITTER = dict(
        name=tr("自爆车", "Bomb Cart"),
        tags=["melee", "dps", "aoe"],
        shape="circle",
        color=GREEN,
        cost=85,
        hp=150,
        speed=120.0,
        damage=10,  # 正常攻击伤害
        cooldown=0.9,
        range=28,
        is_ranged=False,
        projectile_speed=0.0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        is_buffer=False,
        buff_move_mult=1.0,
        buff_cooldown_mult=1.0,
        aura_radius=0.0,
        is_charger=False,
        knockback_factor=0.0,
        bonus_vs_charge_mult=1.0,
        charge_interrupt_stun=0.0,
        split_on_death=False,
        split_child_key=None,
        split_children_count=0,
        projectile_slow_stack=0,
        projectile_slow_duration=0.0,
        frost_stun_cap=0,
        frost_stun_duration=0.0,
        death_explode_radius=40.0,
        death_explode_damage=110,
        attack_animation_duration=0.8,
        suicide_on_attack=False,  # 正常攻击，死亡时才爆炸
    )

    # 新增：轻骑兵（击退随移速）
    LIGHT_CAV = dict(
        name=tr("轻骑", "Light Cavalry"),
        tags=["melee", "dps"],
        shape="diamond",
        color=WHITE,
        cost=90,
        hp=160,
        speed=145.0,
        damage=21,
        cooldown=0.75,
        range=30,
        is_ranged=False,
        projectile_speed=0.0,
        radius=20,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        is_buffer=False,
        buff_move_mult=1.0,
        buff_cooldown_mult=1.0,
        aura_radius=0.0,
        is_charger=True,
        knockback_factor=0.66,
        knockback_damage_mult=1.2,
        bonus_vs_charge_mult=1.0,
        charge_interrupt_stun=0.0,
        split_on_death=False,
        split_child_key=None,
        split_children_count=0,
        projectile_slow_stack=0,
        projectile_slow_duration=0.0,
        frost_stun_cap=0,
        frost_stun_duration=0.0,
    )

    RHINO = dict(
        name=tr("犀牛", "Rhino"),
        tags=["melee", "tank", "aoe"],
        shape="octagon",
        color=ORANGE,
        cost=90,
        hp=240,
        speed=90.0,
        damage=15,
        cooldown=0.7,
        range=30,
        is_ranged=False,
        projectile_speed=0.0,
        radius=14,
        is_aoe=True,
        aoe_radius=32.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        knockback_factor=1.0,
        attack_animation_duration=0.5,
    )

    ASSASSIN = dict(
        name=tr("刺客", "Assassin"),
        tags=["melee", "dps"],
        shape="diamond",
        color=RED,
        cost=85,
        hp=115,
        speed=275.0,
        damage=40,
        cooldown=0.9,
        range=32,
        is_ranged=False,
        projectile_speed=0.0,
        radius=12,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=True,
        prioritize_high_damage=True,
        intercept_radius=0.0,
        intercept_cooldown=0.0,
        target_ranged_support_only=True,
        attack_animation_duration=0.375,
    )

    INTERCEPTOR = dict(
        name=tr("破箭", "Interceptor"),
        tags=["melee", "support"],
        shape="octagon",
        color=BLUE,
        cost=90,
        hp=180,
        speed=85.0,
        damage=0,
        cooldown=0.8,
        range=28,
        is_ranged=False,
        projectile_speed=0.0,
        radius=14,
        is_aoe=False,
        aoe_radius=0.0,
        is_healer=False,
        heal_amount=0,
        ignore_stop_when_enemy=False,
        prioritize_high_damage=False,
        intercept_radius=60.0,
        intercept_cooldown=0.6,
        reflect_chance=0.5,
        reflect_damage_ratio=0.6,
        attack_animation_duration=0.25, # 2 frames @ 8 FPS = 0.25s
    )


