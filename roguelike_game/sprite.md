# 精灵图制作要求文档

## 零、总体需求总结 (Summary)

**核心原则：只需要制作单位本体的动画，特效和子弹由代码生成。**

### 1. 需要制作的内容
- **仅限单位本体**：每个兵种只需要制作 **待机 (idle)**、**走路 (walk)**、**攻击 (attack)** 三组动作序列。
- **文件格式**：PNG（透明背景），48x48 像素（或根据具体单位尺寸调整），RGBA 模式。

### 2. 不需要制作的内容（由代码自动实现）
- **❌ 投射物/子弹**：远程单位的箭矢、魔法弹、光束等不需要制作图片，游戏代码会绘制几何图形。
- **❌ 技能特效**：爆炸、地面灼烧、光环、治疗波纹等不需要制作图片，游戏代码会使用粒子或几何图形渲染。
- **❌ 满级/强化变体**：兵种升级或满级时不需要额外的外观变化，游戏仅在数值上体现差异。
- **❌ UI 图标**：暂时不需要单独的头像图标。

### 3. 交付清单概览
对于每个兵种，仅需提供以下文件夹结构的 PNG 序列：
```
兵种名/
├── idle_0.png, idle_1.png...     (待机)
├── walk_0.png, walk_1.png...     (走路)
└── attack_0.png, attack_1.png... (攻击)
```

---

## 一、基础规范

### 1. 文件格式
- **尺寸**：48×48 像素
- **格式**：PNG（透明背景）
- **分辨率**：72-96 DPI（屏幕显示）
- **颜色模式**：RGBA

### 2. 文件命名规范
- 待机动画：`idle_0.png`, `idle_1.png`, `idle_2.png` ...
- 走路动画：`walk_0.png`, `walk_1.png`, `walk_2.png` ...
- 攻击动画：`attack_0.png`, `attack_1.png`, `attack_2.png` ...

### 3. 目录结构
```
assets/sprites/
├── warrior/          # 战士
├── shield/           # 盾卫
├── scout/            # 游击
├── berserker/        # 狂战
├── medic/            # 牧师
├── archer/           # 弓手
├── mage/             # 法师
├── rhino/            # 犀牛
├── assassin/         # 刺客
├── interceptor/      # 破箭
├── drummer/          # 鼓手
├── spearman/         # 矛兵
├── frost_archer/     # 冰弓
├── exploder/         # 自爆车
└── light_cavalry/    # 轻骑
```

### 4. 角色定位
- **中心点**：画布中心 (24, 24)
- **脚部位置**：约在画布下方 1/4 处 (y ≈ 36-38)
- **头部位置**：约在画布上方 1/4 处 (y ≈ 10-12)

### 5. 风格要求
- **主题**：机械战争风格
- **特点**：
  - 金属质感
  - 机械关节
  - 科技感细节
  - 统一的设计语言
  - 未来废土风格

---

## 二、各兵种详细要求

### 1. 战士 (warrior)
- **文件夹名**：`warrior`
- **颜色**：青色 (CYAN: 80, 200, 220)
- **特点**：均衡近战单位，基础步兵
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 轻微呼吸/摆动
    - 持武器待命姿态
  - **走路 (walk)**：4-6 帧（循环）
    - 流畅的步伐循环
    - 手臂自然摆动
  - **攻击 (attack)**：3-4 帧
    - 前摇：举武器
    - 命中：挥击动作
    - 后摇：收招

### 2. 盾卫 (shield)
- **文件夹名**：`shield`
- **颜色**：橙色 (ORANGE: 255, 140, 0)
- **特点**：高生命、低伤害、慢速，持盾防御
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持盾防御姿态
    - 盾牌在前方
  - **走路 (walk)**：4-6 帧（循环）
    - 缓慢移动
    - 盾牌保持防御姿态
  - **攻击 (attack)**：3-4 帧
    - 盾击动作
    - 盾牌向前推击

### 3. 游击 (scout)
- **文件夹名**：`scout`
- **颜色**：黄色 (YELLOW: 240, 210, 60)
- **特点**：快速近战，缴械能力，优先攻击未被缴械单位
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 敏捷姿态
    - 武器准备
  - **走路 (walk)**：6-8 帧（循环）
    - 快速步伐
    - 轻快移动
  - **攻击 (attack)**：3-4 帧
    - 快速挥击
    - 缴械动作

### 4. 狂战 (berserker)
- **文件夹名**：`berserker`
- **颜色**：绿色 (GREEN: 70, 200, 120)
- **特点**：近战 AOE，范围溅射伤害
- **尺寸**：直径 32px (radius=16)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 狂暴姿态
    - 武器高举
  - **走路 (walk)**：4-6 帧（循环）
    - 沉重步伐
    - 武器拖拽
  - **攻击 (attack)**：4-5 帧
    - 大范围挥击
    - AOE 旋转攻击
    - 明显的攻击范围

### 5. 牧师 (medic)
- **文件夹名**：`medic`
- **颜色**：红色 (RED: 230, 70, 70)
- **特点**：远程治疗，无攻击伤害
- **尺寸**：直径 32px (radius=16)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持治疗设备
    - 设备发光
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 设备保持
  - **攻击 (attack)**：3-4 帧
    - 发射治疗光束
    - 设备激活
    - 光束效果

### 6. 弓手 (archer)
- **文件夹名**：`archer`
- **颜色**：蓝色 (BLUE: 80, 140, 255)
- **特点**：远程单体输出
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持弓待命
    - 箭袋可见
  - **走路 (walk)**：4-6 帧（循环）
    - 正常步伐
    - 弓保持
  - **攻击 (attack)**：4-5 帧
    - 拉弓
    - 瞄准
    - 射箭
    - 收弓

### 7. 法师 (mage)
- **文件夹名**：`mage`
- **颜色**：品红色 (MAGENTA: 200, 80, 220)
- **特点**：中远程 AOE 投射
- **尺寸**：直径 30px (radius=15)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持法杖
    - 法杖发光
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 法杖跟随
  - **攻击 (attack)**：4-5 帧
    - 施法动作
    - 法杖聚集能量
    - 发射魔法弹
    - AOE 爆炸效果

### 8. 犀牛 (rhino)
- **文件夹名**：`rhino`
- **颜色**：橙色 (ORANGE: 255, 140, 0)
- **特点**：推线坦克，每次攻击造成 AOE 击退
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 重型机甲姿态
    - 厚重装甲
  - **走路 (walk)**：4-6 帧（循环）
    - 缓慢沉重
    - 地面震动感
  - **攻击 (attack)**：3-4 帧
    - 冲撞动作
    - 击退效果
    - 前冲姿态

### 9. 刺客 (assassin)
- **文件夹名**：`assassin`
- **颜色**：红色 (RED: 230, 70, 70)
- **特点**：无视接敌持续前进，仅攻击远程/辅助类单位
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 隐身/潜行姿态
    - 武器隐藏
  - **走路 (walk)**：6-8 帧（循环）
    - 快速潜行
    - 轻盈步伐
    - 半透明效果（可选）
  - **攻击 (attack)**：3-4 帧
    - 快速突刺
    - 闪现攻击
    - 收招

### 10. 破箭 (interceptor)
- **文件夹名**：`interceptor`
- **颜色**：蓝色 (BLUE: 80, 140, 255)
- **特点**：拦截弹道，50% 概率反弹
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 拦截设备展开
    - 设备发光
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 设备保持
  - **攻击 (attack)**：3-4 帧
    - 拦截动作
    - 设备激活
    - 反弹效果

### 11. 鼓手 (drummer)
- **文件夹名**：`drummer`
- **颜色**：蓝色 (BLUE: 80, 140, 255)
- **特点**：光环移速/攻速增益，无输出
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持鼓
    - 鼓发光（光环效果）
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 鼓跟随
  - **攻击 (attack)**：3-4 帧
    - 敲鼓动作
    - 产生光环波纹
    - 增益效果可视化

### 12. 矛兵 (spearman)
- **文件夹名**：`spearman`
- **颜色**：黄色 (YELLOW: 240, 210, 60)
- **特点**：克制冲锋，对冲锋单位伤害×1.8并打断
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持矛
    - 防御姿态
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 矛保持
  - **攻击 (attack)**：3-4 帧
    - 刺击动作
    - 克制冲锋的防御姿态
    - 打断效果

### 13. 冰弓 (frost_archer)
- **文件夹名**：`frost_archer`
- **颜色**：青色 (CYAN: 80, 200, 220)
- **特点**：命中叠减速，满 5 层眩晕
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 持冰弓
    - 冰霜效果
  - **走路 (walk)**：4-6 帧（循环）
    - 正常移动
    - 冰弓保持
  - **攻击 (attack)**：4-5 帧
    - 拉冰弓
    - 凝聚冰箭
    - 射箭
    - 冰霜轨迹

### 14. 自爆车 (exploder)
- **文件夹名**：`exploder`
- **颜色**：绿色 (GREEN: 70, 200, 120)
- **特点**：被击杀时范围伤害
- **尺寸**：直径 24px (radius=12)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 自爆装置
    - 装置闪烁
  - **走路 (walk)**：4-6 帧（循环）
    - 滚动移动
    - 装置保持
  - **攻击 (attack)**：3-4 帧
    - 准备爆炸
    - 装置激活
    - 危险警告

### 15. 轻骑 (light_cavalry)
- **文件夹名**：`light_cavalry`
- **颜色**：白色 (WHITE: 235, 235, 235)
- **特点**：仅首次命中触发 AOE 击退，后续单体
- **尺寸**：直径 28px (radius=14)
- **动画要求**：
  - **待机 (idle)**：2-3 帧
    - 骑乘姿态
    - 马匹站立
  - **走路 (walk)**：4-6 帧（循环）
    - 马步移动
    - 四蹄交替
  - **攻击 (attack)**：4-5 帧
    - 冲锋动作
    - AOE 击退效果
    - 马匹前冲

---

## 三、动画帧数建议

### 待机动画 (idle)
- **帧数**：2-3 帧
- **时长**：每帧 0.2 秒
- **效果**：轻微呼吸、摆动、发光等

### 走路动画 (walk)
- **帧数**：4-8 帧（根据单位速度调整）
  - 慢速单位（盾卫、犀牛）：4-5 帧
  - 中速单位（战士、弓手）：5-6 帧
  - 快速单位（游击、刺客）：6-8 帧
- **时长**：每帧 0.12 秒
- **效果**：流畅循环，步伐自然

### 攻击动画 (attack)
- **帧数**：3-5 帧
  - 简单攻击：3-4 帧
  - 复杂攻击（弓手、法师）：4-5 帧
- **时长**：每帧 0.1-0.15 秒
- **效果**：有明显前摇、命中、后摇

---

## 四、颜色方案参考

| 兵种 | RGB 颜色值 | 十六进制 |
|------|-----------|---------|
| 战士 | (80, 200, 220) | #50C8DC |
| 盾卫 | (255, 140, 0) | #FF8C00 |
| 游击 | (240, 210, 60) | #F0D23C |
| 狂战 | (70, 200, 120) | #46C878 |
| 牧师 | (230, 70, 70) | #E64646 |
| 弓手 | (80, 140, 255) | #508CFF |
| 法师 | (200, 80, 220) | #C850DC |
| 犀牛 | (255, 140, 0) | #FF8C00 |
| 刺客 | (230, 70, 70) | #E64646 |
| 破箭 | (80, 140, 255) | #508CFF |
| 鼓手 | (80, 140, 255) | #508CFF |
| 矛兵 | (240, 210, 60) | #F0D23C |
| 冰弓 | (80, 200, 220) | #50C8DC |
| 自爆车 | (70, 200, 120) | #46C878 |
| 轻骑 | (235, 235, 235) | #EBEBEB |

**注意**：颜色应作为主色调，可以添加金属质感、高光、阴影等效果。

---

## 五、制作优先级

### 第一批（核心单位）- 优先制作
1. **战士** (warrior) - 最基础单位
2. **弓手** (archer) - 远程代表
3. **盾卫** (shield) - 防御代表
4. **法师** (mage) - AOE 代表

### 第二批（特色单位）- 次优先
5. **犀牛** (rhino) - 重装单位
6. **刺客** (assassin) - 特殊机制
7. **狂战** (berserker) - AOE 近战
8. **牧师** (medic) - 治疗单位

### 第三批（剩余单位）- 最后制作
9. **游击** (scout)
10. **破箭** (interceptor)
11. **鼓手** (drummer)
12. **矛兵** (spearman)
13. **冰弓** (frost_archer)
14. **自爆车** (exploder)
15. **轻骑** (light_cavalry)

---

## 六、制作技巧

### 1. 统一设计语言
- 所有单位使用相似的机械结构
- 统一的关节设计
- 一致的金属质感

### 2. 动作流畅性
- 走路动画要循环流畅
- 攻击动画要有力度感
- 待机动画要生动

### 3. 细节处理
- 添加高光和阴影增强立体感
- 使用颜色渐变增加质感
- 添加发光效果（如法师法杖、治疗设备）

### 4. 左右对称
- 尽量设计左右对称的角色
- 方便代码自动翻转
- 如果不对称，需要提供左右两套（可选）

### 5. 动作范围
- 攻击动作可以超出基础半径
- 走路时上下浮动范围约 2-4px
- 攻击时向前突进约 2px

---

## 七、测试建议

1. **先制作 1-2 个完整单位**进行测试
2. **确认效果**后再批量制作
3. **根据实际效果**调整帧数和时长
4. **保持风格统一**，建立设计规范

---

## 八、文件提交格式

每个兵种文件夹应包含：
```
unit_name/
├── idle_0.png
├── idle_1.png
├── walk_0.png
├── walk_1.png
├── walk_2.png
├── walk_3.png
├── attack_0.png
├── attack_1.png
└── attack_2.png
```

**注意**：帧数可以根据实际情况调整，但命名必须从 0 开始连续编号。

---

## 九、常见问题

### Q: 如果某个动画只有 2 帧可以吗？
A: 可以，但建议至少 2 帧才能形成动画效果。

### Q: 攻击动画需要循环吗？
A: 不需要，攻击动画是一次性的，播放完会回到待机或走路状态。

### Q: 走路动画必须循环吗？
A: 是的，走路动画需要无缝循环，最后一帧应该能平滑过渡到第一帧。

### Q: 颜色必须完全匹配吗？
A: 主色调应该匹配，但可以添加高光、阴影、渐变等效果增强质感。

---

## 十、联系与反馈

制作过程中如有疑问，请参考：
- 游戏内单位实际表现
- 代码中的单位配置 (`game/constants.py`)
- 动画系统实现 (`game/animation.py`)

祝制作顺利！

---

## 十一、环境与UI素材 (Environment & UI)

### 1. 场景背景 (Backgrounds)
- **尺寸**：1440 x 900 (或更大，按比例缩放)
- **格式**：PNG/JPG (不透明)
- **风格**：深色调、科技感、不喧宾夺主
- **存放路径**：`assets/backgrounds/`
- **需求清单**：
  - `menu_bg.png`: 主菜单背景。建议：浩瀚星空或机械堡垒远景。
    - **MJ Prompt**: `sci-fi game main menu background, vast deep space with distant mechanical fortress, dark blue and purple color palette, subtle stars, cinematic lighting, high tech, futuristic, 2d digital art, clean composition --ar 16:10`
  - `battle_bg.png`: 战斗背景。建议：深色金属地面，带有一些网格或电路纹理。
    - **MJ Prompt**: `2d game battle background, dark metallic floor, sci-fi grid texture, subtle circuit patterns, dark grey and blue tones, top-down perspective view, flat ground for strategy game, minimalist, high tech, seamless texture --ar 16:10`
  - `map_bg.png`: 战役地图背景。建议：全息战术地图风格，深蓝色调。
    - **MJ Prompt**: `holographic tactical map background, deep blue interface style, digital grid lines, sci-fi hud elements, dark background, abstract data visualization, cybernetic aesthetic, 2d game asset, clean background --ar 16:10`
  - `shop_bg.png`: 商店背景。建议：内部机械舱室风格，略带暖色灯光。
    - **MJ Prompt**: `sci-fi shop interior background, mechanical cabin, warm lighting, shelves with futuristic items, metallic walls, cozy but high tech, 2d digital art, visual novel background style, wide angle --ar 16:10`

### 2. 游戏物体 (Objects)
- **格式**：PNG (透明背景)
- **存放路径**：`assets/objects/`
- **需求清单**：
  - **基地 (Base) - 传送门风格**
    - `base_portal.png`: 建议尺寸 64x96 或 80x120。
    - **风格**：科幻传送门，机械边框，中间有能量旋涡。
    - **MJ Prompt**: `sci-fi teleport portal, mechanical frame gate, swirling energy vortex in center, glowing cyan energy, isolated on black background, game asset, sprite, isometric view, metallic texture, high detail --no background`
    - **备注**：代码会自动根据阵营（左/右）进行翻转和颜色区分（我方青色，敌方红色），或者您可以分别提供 `base_portal_left.png` 和 `base_portal_right.png`。目前优先制作通用的 `base_portal.png`。

### 3. UI 元素 (UI Elements)
- **格式**：PNG (透明背景)
- **存放路径**：`assets/ui/`
- **需求清单**：
  - `panel_bg.png`: 顶部资源/兵种面板的底图。尺寸：1440 x 190 (Top UI Height)。风格：深色金属面板，带有科技感边框线条。
    - **MJ Prompt**: `sci-fi ui panel background, dark metal texture, cyan glowing borders, rectangular shape, wide aspect ratio, hud element, futuristic interface, clean design, 2d game ui, isolated --ar 8:1`
  - `card_frame.png`: 兵种/技能卡片的边框。尺寸：约 140 x 52。
    - **MJ Prompt**: `sci-fi card frame border, metallic texture, holographic details, rectangular frame for game card, transparent center, futuristic design, game ui asset, isolated on black background`
  - `dialog_box.png`: 通用对话/信息框背景（半透明黑底+科技边框）。
    - **MJ Prompt**: `sci-fi dialog box background, semi-transparent dark glass, glowing high tech border, futuristic ui element, clean and minimal, isolated on black background --ar 3:1`

**注意**：目前游戏大部分UI仍使用代码绘制几何图形，优先制作 **背景图** 和 **基地传送门** 可获得最大的视觉提升。