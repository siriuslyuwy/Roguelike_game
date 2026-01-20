import pygame
import os
import math
import tempfile

# 尝试导入 pydub
try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    print("Pydub not installed. Dynamic speed generation disabled.")

class AudioManager:
    def __init__(self):
        # 初始化混音器
        # frequency=44100: 标准采样率
        # size=-16: 16位有符号整数
        # channels=2: 立体声
        # buffer=2048: 缓冲区大小，太小可能爆音，太大可能有延迟
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        except Exception as e:
            print(f"Audio init failed: {e}")
            return

        # 路径修正：假设游戏从 main.py 启动，assets 在同级目录
        self.music_dir = os.path.join("assets", "music")
        
        # 状态
        self.current_bgm_level = 0  # 0: base, 1: fast, 2: intense
        self.target_bgm_level = 0
        self.enemy_count = 0
        self.bgm_files = {}
        self.sfx_files = {}
        self.bgm_playing = False
        
        # 连击系统
        self.kill_combo = 0
        self.combo_timer = 0.0
        self.COMBO_WINDOW = 0.5  # 连击判定时间窗口
        
        self.temp_files = []  # 临时文件列表
        self.bgm_volume = 0.3
        self.sfx_volume = 0.3
        self._load_resources()
        
    def __del__(self):
        """清理临时文件"""
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass
        
    def set_bgm_volume(self, volume: float):
        self.bgm_volume = max(0.0, min(1.0, volume))
        if self.bgm_playing:
            pygame.mixer.music.set_volume(self.bgm_volume)

    def set_sfx_volume(self, volume: float):
        self.sfx_volume = max(0.0, min(1.0, volume))
        for sound in self.sfx_files.values():
            sound.set_volume(self.sfx_volume)

    def _load_resources(self):
        if not os.path.exists(self.music_dir):
            # 尝试相对于文件的路径
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.music_dir = os.path.join(base_dir, "assets", "music")
            
            if not os.path.exists(self.music_dir):
                print(f"Music directory not found: {self.music_dir}")
                return

        # 加载 BGM 路径
        bgm_map = {
            0: "bgm_base.mp3",
            1: "bgm_fast.mp3",
            2: "bgm_intense.mp3"
        }
        
        # 检查文件是否存在，如果高级别BGM不存在，回退到低级别
        last_valid_bgm = None
        
        # 先找基础BGM
        base_path = os.path.join(self.music_dir, bgm_map[0])
        if os.path.exists(base_path):
            self.bgm_files[0] = base_path
            last_valid_bgm = base_path
            
            # === 自动生成变速版本 (如果没有手动提供) ===
            if HAS_PYDUB:
                fast_path = os.path.join(self.music_dir, "bgm_fast.mp3")
                if not os.path.exists(fast_path):
                    print("Generating fast BGM (1.15x)...")
                    self.bgm_files[1] = self._create_speed_variant(base_path, 1.15)
                
                intense_path = os.path.join(self.music_dir, "bgm_intense.mp3")
                if not os.path.exists(intense_path):
                    print("Generating intense BGM (1.35x)...")
                    self.bgm_files[2] = self._create_speed_variant(base_path, 1.35)
        else:
            print("Warning: bgm_base.mp3 not found.")
            
        # 找其他级别的BGM，找不到就用基础的
        for level in [1, 2]:
            # 如果已经被自动生成填入了，跳过
            if level in self.bgm_files:
                continue
                
            path = os.path.join(self.music_dir, bgm_map[level])
            if os.path.exists(path):
                self.bgm_files[level] = path
                last_valid_bgm = path
            elif last_valid_bgm:
                self.bgm_files[level] = last_valid_bgm

        # 加载音效 (预加载到内存)
        sfx_map = {
            "light": "kill_light.mp3",
            "medium": "kill_medium.mp3",
            "heavy": "kill_heavy.mp3"
        }
        
        for key, filename in sfx_map.items():
            path = os.path.join(self.music_dir, filename)
            if os.path.exists(path):
                try:
                    self.sfx_files[key] = pygame.mixer.Sound(path)
                    # 适当降低音效音量，避免盖过BGM
                    self.sfx_files[key].set_volume(self.sfx_volume) 
                except Exception as e:
                    print(f"Failed to load SFX {filename}: {e}")

    def _create_speed_variant(self, file_path, speed):
        """使用 pydub 生成变速版本的临时文件"""
        try:
            # 加载音频
            sound = AudioSegment.from_file(file_path)
            
            # 简单的重采样变速 (同时改变音调)
            new_sample_rate = int(sound.frame_rate * speed)
            sound_with_new_rate = sound._spawn(sound.raw_data, overrides={
                "frame_rate": new_sample_rate
            })
            # 设回标准采样率以兼容播放器
            final_sound = sound_with_new_rate.set_frame_rate(sound.frame_rate)
            
            # 导出到临时文件
            # delete=False 因为我们要把名字传给 pygame，后面自己删
            fd, temp_path = tempfile.mkstemp(suffix='.mp3')
            os.close(fd)
            
            final_sound.export(temp_path, format="mp3")
            self.temp_files.append(temp_path)
            return temp_path
        except Exception as e:
            print(f"Failed to generate speed variant: {e}")
            return file_path # 失败则回退到原版

    def play_bgm(self):
        if 0 not in self.bgm_files:
            return
            
        try:
            # 默认播放基础BGM
            pygame.mixer.music.load(self.bgm_files[0])
            pygame.mixer.music.play(loops=-1, fade_ms=1000)
            pygame.mixer.music.set_volume(self.bgm_volume)
            self.bgm_playing = True
            self.current_bgm_level = 0
        except Exception as e:
            print(f"Failed to play BGM: {e}")

    def stop_bgm(self):
        pygame.mixer.music.fadeout(1000)
        self.bgm_playing = False

    def update(self, dt: float, enemy_count: int, new_kills: int):
        self.enemy_count = enemy_count
        
        # --- 处理 BGM 切换 ---
        # 根据敌人数量决定目标 BGM 等级
        if enemy_count > 12:
            target = 2
        elif enemy_count > 6:
            target = 1
        else:
            target = 0
            
        # 如果有更高级别的BGM文件才切换
        if target != self.current_bgm_level and self.bgm_playing:
            # 确保目标文件和当前文件不一样（避免同文件重新加载）
            if self.bgm_files.get(target) != self.bgm_files.get(self.current_bgm_level):
                self.current_bgm_level = target
                try:
                    # 记录当前播放位置（有些格式不支持精确seek，但这是一种尝试）
                    # pos = pygame.mixer.music.get_pos() / 1000.0 
                    # 切换BGM通常直接淡入淡出比较自然，保持位置比较难做到无缝
                    pygame.mixer.music.load(self.bgm_files[target])
                    pygame.mixer.music.play(loops=-1, fade_ms=500)
                except Exception as e:
                    print(f"Failed to switch BGM: {e}")

        # --- 处理击杀音效 ---
        if new_kills > 0:
            self.kill_combo += new_kills
            self.combo_timer = self.COMBO_WINDOW
            self._play_kill_sound()
            
        # 更新连击计时器
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.kill_combo = 0

    def _play_kill_sound(self):
        # 根据连击数选择音效
        sound = None
        if self.kill_combo >= 4:
            sound = self.sfx_files.get("heavy") or self.sfx_files.get("medium") or self.sfx_files.get("light")
        elif self.kill_combo >= 2:
            sound = self.sfx_files.get("medium") or self.sfx_files.get("light")
        else:
            sound = self.sfx_files.get("light")
            
        if sound:
            sound.play()

