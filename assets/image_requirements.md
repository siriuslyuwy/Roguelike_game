# 图片资源制作要求文档

本项目包含两类主要图片资源：**战场背景图** 和 **单位精灵图**。

## 一、战场背景图 (Battle Backgrounds)

背景图用于游戏核心战斗界面，必须严格遵循以下构图要求，以确保不干扰游戏玩法。

### 1. 存放位置
- 路径：`assets/backgrounds/`
- 命名：任意文件名，游戏会随机或指定加载。推荐命名 `battle_bg_01.png`, `battle_bg_highway.png` 等。

### 2. 基础参数
- **分辨率**：推荐 **1920 x 1080** (16:9)
  - 游戏支持自适应，但建议原始比例为 16:9 以获得最佳裁剪效果。
- **格式**：PNG 或 JPG
- **风格**：像素风 (Pixel Art) + 机械废土/赛博朋克

### 3. 关键构图要求 (CRITICAL)
游戏界面分为上下两部分，背景图必须严格对应：

- **上部 20%-25% (HUD区域)**：
  - **内容**：可以是天空、远处的城市轮廓、太空景色、高耸建筑的顶部。
  - **作用**：作为 UI 面板的衬底（虽然 UI 有半透明遮罩，但这里是唯一可以画复杂风景的地方）。
  - **分界线**：**地平线 (Horizon Line)** 应位于画布顶部往下约 20%-25% 处。

- **下部 75%-80% (战场区域)**：
  - **内容**：**必须是平坦、干净的地面**。
  - **材质**：沥青路面、金属地板、荒漠土地、网格地板。
  - **禁忌**：**绝对不能有前景遮挡物**（如石头、树木、废墟堆、建筑墙体）。
  - **视觉干扰**：避免过于花哨的纹理，以免看不清兵种（兵种颜色丰富，背景应尽量低饱和度或偏暗）。
  - **透视**：侧视 (Side View) 或 极低角度 (Low Angle)，让地面看起来像一个宽阔的平面。

### 4. 推荐 AI 生成提示词 (Prompt Examples)

#### 方案 A：暗夜高速路 (推荐)
> Side scrolling game background, pixel art, futuristic highway surface taking up bottom 80% of the image, clean dark asphalt texture, faint lane markings, cyberpunk city skyline only in the top 20% distance, dark blue night sky at very top, low angle perspective, flat ground, no obstacles on ground, high contrast, 16-bit style --ar 16:9 --no buildings in foreground

#### 方案 B：数字网格
> Retro arcade game background, pixel art, synthwave style, vast black grid floor extending to horizon, ground takes up bottom 80%, neon grid lines, glowing horizon line at top 20%, retro sun and stars in the top sky area only, clean vector aesthetic, simple geometry, dark background, no objects on floor --ar 16:9

---

## 二、单位精灵图 (Unit Sprites)

详情请参考根目录下的 `sprite.md`。

### 1. 存放位置
- 路径：`assets/sprites/{unit_name}/`
  - 例如：`assets/sprites/warrior/`, `assets/sprites/archer/`

### 2. 基础参数
- **画布尺寸**：48x48 像素
- **格式**：PNG (透明背景)
- **中心点**：画布正中心 (24, 24) 为单位几何中心。
- **脚下位置**：约 y=36~38 像素处。

### 3. 命名规范
- **待机**：`idle_0.png`, `idle_1.png` ...
- **移动**：`walk_0.png`, `walk_1.png` ...
- **攻击**：`attack_0.png`, `attack_1.png` ...

### 4. 注意事项
- **朝向**：默认**面向右侧**（我方视角）。敌方单位（在右侧）代码会自动水平翻转。
- **颜色**：尽量契合兵种定义的主色调（如战士=青色，弓手=蓝色），方便玩家识别。


