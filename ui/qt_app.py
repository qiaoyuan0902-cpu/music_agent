import sys
import io
import asyncio
import tempfile
import os
import random
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QSlider, QScrollArea, QLineEdit,
    QDialog, QSizePolicy, QTextEdit, QSplitter, QStackedWidget, QTabWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject, QUrl
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QBrush, QPixmap, QTextCursor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices

# ── graceful imports ──────────────────────────────────────
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from music.netease import (
        load_session, get_qr_code, poll_qr_login,
        get_liked_songs, get_user_profile, fmt_duration, get_song_url, get_lyrics,
    )
    HAS_NETEASE = True
except Exception as _ne_err:
    print(f"[netease] import failed: {type(_ne_err).__name__}: {_ne_err}")
    HAS_NETEASE = False

try:
    from agent.core import MusicAgent
    _agent = MusicAgent()
except Exception:
    _agent = None

try:
    from memory import conversation as conv_store
except Exception:
    conv_store = None

try:
    from weather.locator import get_city_by_ip
    from weather.fetcher import get_weather
    HAS_WEATHER = True
except Exception:
    HAS_WEATHER = False

# ── Theme ─────────────────────────────────────────────────
DARK = dict(
    BG="#13111f", BG_CARD="#1c1a2e", BG_INPUT="#16142a",
    BG_PLAYING="#1a3a2a", ACCENT="#00ff88", TEXT="#ffffff",
    TEXT_MUTED="#888899", BORDER="#2a2840",
)
LIGHT = dict(
    BG="#f0f0f5", BG_CARD="#ffffff", BG_INPUT="#e8e8f0",
    BG_PLAYING="#d0f0e0", ACCENT="#00aa55", TEXT="#1a1a2e",
    TEXT_MUTED="#666677", BORDER="#ccccdd",
)

# ── TTS 声音库 ────────────────────────────────────────────
VOICES = {
    # 普通话女声
    "晓晓":   "zh-CN-XiaoxiaoNeural",      # 温柔自然，默认
    "晓伊":   "zh-CN-XiaoyiNeural",         # 活泼
    "小北":   "zh-CN-liaoning-XiaobeiNeural", # 东北口音
    "小妮":   "zh-CN-shaanxi-XiaoniNeural",  # 陕西口音
    # 普通话男声
    "云希":   "zh-CN-YunxiNeural",          # 亲切
    "云健":   "zh-CN-YunjianNeural",         # 运动/新闻风
    "云夏":   "zh-CN-YunxiaNeural",          # 年轻
    "云扬":   "zh-CN-YunyangNeural",         # 播音腔
    # 粤语
    "晓佳":   "zh-HK-HiuGaaiNeural",        # 粤语女声
    "云龙":   "zh-HK-WanLungNeural",         # 粤语男声
    # 台湾
    "晓臻":   "zh-TW-HsiaoChenNeural",       # 台湾女声
    "云哲":   "zh-TW-YunJheNeural",          # 台湾男声
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


class ThemeManager(QObject):
    theme_changed = pyqtSignal(dict)
    _inst = None

    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        super().__init__()
        self._dark = True
        self.colors = dict(DARK)

    def toggle(self):
        self._dark = not self._dark
        self.colors = dict(DARK if self._dark else LIGHT)
        self.theme_changed.emit(self.colors)

    def is_dark(self):
        return self._dark

    def c(self, key):
        return self.colors[key]


def tm() -> ThemeManager:
    return ThemeManager.instance()


def mono(size: int, bold: bool = False) -> QFont:
    # macOS 自带等宽字体
    for name in ("Menlo", "Monaco", "Courier New"):
        f = QFont(name, size)
        if f.exactMatch():
            f.setBold(bold)
            return f
    f = QFont("Courier New", size)
    f.setBold(bold)
    return f


# ── SongLoaderWorker ──────────────────────────────────────
class SongLoaderWorker(QThread):
    songs_loaded  = pyqtSignal(list)   # list of song dicts
    need_login    = pyqtSignal()       # session invalid → show QR

    def run(self):
        if not HAS_NETEASE:
            return
        try:
            if load_session():
                songs = get_liked_songs(200)
                self.songs_loaded.emit(songs)
            else:
                self.need_login.emit()
        except Exception:
            self.need_login.emit()


# ── TTSWorker ─────────────────────────────────────────────
try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

class TTSWorker(QThread):
    audio_ready = pyqtSignal(str)   # temp file path

    def __init__(self, text: str, voice: str = "zh-CN-XiaoxiaoNeural"):
        super().__init__()
        self.text  = text
        self.voice = voice

    def run(self):
        if not HAS_TTS:
            return
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            asyncio.run(self._synthesize(tmp.name))
            self.audio_ready.emit(tmp.name)
        except Exception:
            pass

    async def _synthesize(self, path: str):
        c = edge_tts.Communicate(self.text, voice=self.voice)
        await c.save(path)


# ── MicWorker ─────────────────────────────────────────────
try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

class MicWorker(QThread):
    text_ready = pyqtSignal(str)
    error      = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop_flag = False

    def stop(self):
        """请求停止录音，run() 循环会在下一个 chunk 后退出并识别"""
        self._stop_flag = True

    def run(self):
        if not HAS_SR:
            self.error.emit("未安装 SpeechRecognition")
            return
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                frames = []
                # 按块录音，每块约 100ms，随时可被 stop() 打断
                chunk_size = int(source.SAMPLE_RATE * 0.1)
                while not self._stop_flag:
                    buf = source.stream.read(chunk_size)
                    if buf:
                        frames.append(buf)

                if not frames:
                    self.error.emit("未录到音频")
                    return

                raw = b"".join(frames)
                audio = sr.AudioData(raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

            text = recognizer.recognize_google(audio, language="zh-CN")
            self.text_ready.emit(text)
        except sr.UnknownValueError:
            self.error.emit("无法识别语音，请重试")
        except Exception as e:
            self.error.emit(f"麦克风错误: {e}")


class UrlFetchWorker(QThread):
    url_ready = pyqtSignal(str)   # playable URL or ""

    def __init__(self, song_id: int):
        super().__init__()
        self.song_id = song_id

    def run(self):
        url = get_song_url(self.song_id) if HAS_NETEASE else ""
        self.url_ready.emit(url)


class LyricsWorker(QThread):
    lyrics_ready = pyqtSignal(list)   # list of (ms, text) tuples

    def __init__(self, song_id: int):
        super().__init__()
        self.song_id = song_id

    def run(self):
        if not HAS_NETEASE:
            self.lyrics_ready.emit([])
            return
        try:
            from music.netease import get_lyrics
            self.lyrics_ready.emit(get_lyrics(self.song_id))
        except Exception:
            self.lyrics_ready.emit([])


# ── StreamWorker ──────────────────────────────────────────
class StreamWorker(QThread):
    chunk        = pyqtSignal(str)
    done         = pyqtSignal()
    play_song    = pyqtSignal(dict)   # song dict to play
    switch_voice = pyqtSignal(str)    # voice_id to switch TTS to

    def __init__(self, message: str, history: list):
        super().__init__()
        self.message = message
        self.history = history

    def run(self):
        if _agent is None:
            self.chunk.emit("Agent 未初始化，请检查配置。")
            self.done.emit()
            return
        import json as _json
        try:
            for c in _agent.chat_stream(self.message, self.history):
                if isinstance(c, str) and c.startswith("__PLAY_SONG__"):
                    try:
                        song = _json.loads(c[len("__PLAY_SONG__"):])
                        self.play_song.emit(song)
                    except Exception:
                        pass
                elif isinstance(c, str) and c.startswith("__SWITCH_VOICE__"):
                    voice_id = c[len("__SWITCH_VOICE__"):]
                    self.switch_voice.emit(voice_id)
                else:
                    self.chunk.emit(c)
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            print(f"[StreamWorker] ERROR:\n{err}")
            # 写到日志文件，打包后也能查看
            try:
                from config import USER_DATA_DIR
                log_path = USER_DATA_DIR / "claudio_error.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    from datetime import datetime
                    f.write(f"\n[{datetime.now()}]\n{err}\n")
            except Exception:
                pass
            self.chunk.emit(f"\n\n⚠️ 出错了：{type(e).__name__}: {e}")
        finally:
            self.done.emit()


# ── PulseDot ──────────────────────────────────────────────
class PulseDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._alpha = 255
        self._dir = -5
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(40)

    def _tick(self):
        self._alpha += self._dir
        if self._alpha <= 60:  self._dir = 5
        if self._alpha >= 255: self._dir = -5
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(tm().c("ACCENT"))
        c.setAlpha(self._alpha)
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)

    def update_theme(self, _=None):
        self.update()


# ── NavBar ────────────────────────────────────────────────
class NavBar(QFrame):
    login_clicked   = pyqtSignal()
    settings_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)

        self.logo = QLabel("Claudio")
        self.logo.setFont(QFont("Courier New", 15, QFont.Weight.Bold))

        self.login_lbl = QLabel("LOGIN")
        self.login_lbl.setFont(mono(9))
        self.login_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_lbl.mousePressEvent = lambda _: self.login_clicked.emit()

        self.settings_lbl = QLabel("⚙")
        self.settings_lbl.setFont(mono(12))
        self.settings_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_lbl.setToolTip("重新配置 API Key")
        self.settings_lbl.mousePressEvent = lambda _: self.settings_clicked.emit()

        self.toggle_lbl = QLabel()
        self.toggle_lbl.setFont(mono(9, True))
        self.toggle_lbl.setFixedHeight(22)
        self.toggle_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_lbl.mousePressEvent = lambda _: self._on_toggle()

        right = QHBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.login_lbl)
        right.addWidget(self.settings_lbl)
        right.addWidget(self.toggle_lbl)

        lay.addWidget(self.logo)
        lay.addStretch()
        lay.addLayout(right)

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    def _on_toggle(self):
        tm().toggle()

    def set_logged_in(self, nickname: str):
        self.login_lbl.setText(nickname[:8] if nickname else "LOGIN")
        self._apply_theme(tm().colors)

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG_CARD']}; border-bottom:1px solid {c['BORDER']};")
        self.logo.setStyleSheet(f"color:{c['ACCENT']}; letter-spacing:2px;")
        self.login_lbl.setStyleSheet(
            f"color:{c['TEXT_MUTED']}; letter-spacing:1px; text-decoration:underline;"
        )
        self.settings_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        label = "  DARK  " if tm().is_dark() else "  LIGHT  "
        self.toggle_lbl.setText(label)
        if tm().is_dark():
            self.toggle_lbl.setStyleSheet(
                "background:white; color:#13111f; border-radius:10px; padding:2px 8px;"
            )
        else:
            self.toggle_lbl.setStyleSheet(
                f"background:{c['ACCENT']}; color:white; border-radius:10px; padding:2px 8px;"
            )


# ── WeatherWorker ─────────────────────────────────────────
class WeatherWorker(QThread):
    result = pyqtSignal(dict)

    def run(self):
        try:
            from weather.locator import get_location_id
            from weather.fetcher import get_weather
            loc = get_location_id()
            data = get_weather(loc)
            print(f"[weather] {loc} → {data}")
            self.result.emit(data)
        except Exception as e:
            import traceback
            print(f"[weather] ERROR: {e}")
            traceback.print_exc()


# ── ClockHero ─────────────────────────────────────────────
class ClockHero(QFrame):
    # weather_main → emoji
    _WEATHER_ICON = {
        "clear":        "☀️",
        "clouds":       "☁️",
        "rain":         "🌧️",
        "drizzle":      "🌦️",
        "thunderstorm": "⛈️",
        "snow":         "❄️",
        "mist":         "🌫️",
        "fog":          "🌫️",
        "haze":         "🌫️",
        "smoke":        "🌫️",
        "dust":         "🌫️",
        "sand":         "🌫️",
        "ash":          "🌋",
        "squall":       "🌬️",
        "tornado":      "🌪️",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 20, 0, 16)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # clock row: [left_pad] stretch [clock] stretch [weather_widget]
        # left_pad mirrors weather_widget width so clock stays truly centered
        clock_row = QHBoxLayout()
        clock_row.setContentsMargins(24, 0, 24, 0)

        self.clock_lbl = QLabel()
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_lbl.setFont(QFont("Courier New", 52, QFont.Weight.Bold))

        # weather widget: icon on top, text below
        weather_widget = QWidget()
        weather_widget.setFixedWidth(110)
        wlay = QVBoxLayout(weather_widget)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.setSpacing(2)
        wlay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.weather_icon_lbl = QLabel()
        self.weather_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weather_icon_lbl.setFont(QFont("Segoe UI Emoji", 32))

        self.weather_lbl = QLabel()
        self.weather_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weather_lbl.setFont(mono(13))

        wlay.addWidget(self.weather_icon_lbl)
        wlay.addWidget(self.weather_lbl)

        # left placeholder balances weather_widget so clock is truly centered
        left_pad = QWidget()
        left_pad.setFixedWidth(110)

        clock_row.addWidget(left_pad)
        clock_row.addStretch()
        clock_row.addWidget(self.clock_lbl)
        clock_row.addStretch()
        clock_row.addWidget(weather_widget)

        self.date_lbl = QLabel()
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl.setFont(mono(11))

        on_air_row = QHBoxLayout()
        on_air_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        on_air_row.setSpacing(6)
        self.dot = PulseDot()
        self.on_air_lbl = QLabel("ON AIR")
        self.on_air_lbl.setFont(mono(9, True))
        on_air_row.addWidget(self.dot)
        on_air_row.addWidget(self.on_air_lbl)

        lay.addLayout(clock_row)
        lay.addWidget(self.date_lbl)
        lay.addSpacing(6)
        lay.addLayout(on_air_row)

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)
        self._tick()

        # 异步拉取天气，每30分钟刷新一次
        self._fetch_weather()
        wt = QTimer(self)
        wt.timeout.connect(self._fetch_weather)
        wt.start(30 * 60 * 1000)

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    def _fetch_weather(self):
        self._w_worker = WeatherWorker()
        self._w_worker.result.connect(self._on_weather)
        self._w_worker.start()

    def _on_weather(self, data: dict):
        desc = data.get("description", "")
        temp = data.get("temp", "")
        main = data.get("weather_main", "")
        icon = self._WEATHER_ICON.get(main, "🌡️")
        self.weather_icon_lbl.setText(icon)
        if temp != "":
            self.weather_lbl.setText(f"{desc}\n{temp}°C")
        else:
            self.weather_lbl.setText(desc)

    def _tick(self):
        now = datetime.now()
        self.clock_lbl.setText(now.strftime("%H:%M"))
        days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        self.date_lbl.setText(f"{days[now.weekday()]}  {now.strftime('%d %b %Y').upper()}")

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG']};")
        self.clock_lbl.setStyleSheet(f"color:{c['TEXT']}; letter-spacing:6px;")
        self.date_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']}; letter-spacing:2px;")
        self.on_air_lbl.setStyleSheet(f"color:{c['ACCENT']}; letter-spacing:3px;")
        self.weather_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']}; letter-spacing:1px;")
        self.weather_icon_lbl.setStyleSheet("background:transparent;")


# ── PlayerBar ─────────────────────────────────────────────
class PlayerBar(QFrame):
    # signals for MainWindow to call prev/next
    request_prev    = pyqtSignal()
    request_next    = pyqtSignal()
    shuffle_changed = pyqtSignal(bool)
    position_changed = pyqtSignal(int)   # current position in ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)

        # ── media backend ──────────────────────────────────
        self._player = QMediaPlayer()
        _dev = QMediaDevices.defaultAudioOutput()
        self._audio_out = QAudioOutput(_dev)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.7)
        self._player.errorOccurred.connect(self._on_player_error)
        self._songs: list = []
        self._current_idx: int = 0
        self._seeking = False
        self._current_song: dict = {}
        self._retry_count: int = 0
        self._url_worker = None

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._media_devices = QMediaDevices()
        self._media_devices.audioOutputsChanged.connect(self._on_audio_device_changed)

        # ── layout ─────────────────────────────────────────
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()

        # left: spectrum + song info
        left = QHBoxLayout()
        left.setSpacing(8)
        self.spec = QLabel("▁▂▃▄▅")
        self.spec.setFont(mono(10))
        song_col = QVBoxLayout()
        song_col.setSpacing(1)
        self.song_lbl = QLabel("— 未连接网易云 —")
        self.song_lbl.setFont(mono(11, True))
        self.status_lbl = QLabel("STOPPED")
        self.status_lbl.setFont(mono(8))
        song_col.addWidget(self.song_lbl)
        song_col.addWidget(self.status_lbl)
        left.addWidget(self.spec)
        left.addLayout(song_col)

        # mid: controls  ⏮ ⏸/▶ ⏭ ⏹
        mid = QHBoxLayout()
        mid.setSpacing(4)
        mid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_prev   = QPushButton("⏮"); self.btn_prev.setFixedSize(32, 32)
        self.btn_play   = QPushButton("▶"); self.btn_play.setFixedSize(32, 32)
        self.btn_next   = QPushButton("⏭"); self.btn_next.setFixedSize(32, 32)
        self.btn_stop   = QPushButton("⏹"); self.btn_stop.setFixedSize(32, 32)
        self.btn_shuffle = QPushButton("⇄"); self.btn_shuffle.setFixedSize(32, 32)
        self.btn_shuffle.setCheckable(True)
        self.btn_shuffle.setToolTip("随机播放")
        self.ctrl_btns = [self.btn_prev, self.btn_play, self.btn_next, self.btn_stop, self.btn_shuffle]
        for b in self.ctrl_btns:
            b.setFont(QFont("Arial", 12))
            mid.addWidget(b)

        self.btn_prev.clicked.connect(self.request_prev)
        self.btn_next.clicked.connect(self.request_next)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_shuffle.clicked.connect(lambda checked: self.shuffle_changed.emit(checked))

        # right: volume
        right = QHBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.vol_lbl = QLabel("VOL")
        self.vol_lbl.setFont(mono(8))
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setFixedWidth(80)
        self.vol.setRange(0, 100)
        self.vol.setValue(70)
        self.vol.valueChanged.connect(lambda v: self._audio_out.setVolume(v / 100))
        right.addWidget(self.vol_lbl)
        right.addWidget(self.vol)

        top.addLayout(left, 3)
        top.addLayout(mid, 4)
        top.addLayout(right, 3)

        # progress row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.t_cur = QLabel("0:00"); self.t_cur.setFont(mono(8))
        self.prog = QSlider(Qt.Orientation.Horizontal)
        self.prog.setRange(0, 1000)
        self.prog.setValue(0)
        self.t_tot = QLabel("0:00"); self.t_tot.setFont(mono(8))
        self.prog.sliderPressed.connect(self._seek_start)
        self.prog.sliderReleased.connect(self._seek_end)
        prog_row.addWidget(self.t_cur)
        prog_row.addWidget(self.prog, 1)
        prog_row.addWidget(self.t_tot)

        lay.addLayout(top)
        lay.addLayout(prog_row)

        # spectrum animation
        self._frames = ["▁▂▃▄▅", "▂▃▄▅▄", "▃▄▅▄▃", "▄▅▄▃▂", "▅▄▃▂▁", "▄▃▂▁▂"]
        self._fi = 0
        self._spec_timer = QTimer(self)
        self._spec_timer.timeout.connect(self._anim)

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    # ── playback control ───────────────────────────────────
    def display_song(self, song: dict):
        """仅更新 UI 显示，不触发播放（启动时用）"""
        self.song_lbl.setText(f"{song['name']} - {song['artist']}")
        self.status_lbl.setText("STOPPED")
        self.prog.setValue(0)
        self.t_cur.setText("0:00")
        self.t_tot.setText(fmt_duration(song.get("duration_ms", 0)) if HAS_NETEASE else "")
        self._current_song = song

    def load_song(self, song: dict):
        """Load and immediately play a song dict {id, name, artist, duration_ms}"""
        self.song_lbl.setText(f"{song['name']} - {song['artist']}")
        self.status_lbl.setText("加载中...")
        self.prog.setValue(0)
        self.t_cur.setText("0:00")
        self.t_tot.setText(fmt_duration(song.get("duration_ms", 0)) if HAS_NETEASE else "")
        self._player.stop()
        self._current_song = song
        self._retry_count = 0
        # Disconnect previous worker to avoid stale signal firing
        if hasattr(self, "_url_worker") and self._url_worker is not None:
            try:
                self._url_worker.url_ready.disconnect()
            except Exception:
                pass
        self._url_worker = UrlFetchWorker(song["id"])
        self._url_worker.url_ready.connect(self._on_url_ready)
        self._url_worker.start()

    def _on_audio_device_changed(self):
        """蓝牙耳机断开重连等设备变化时，重新绑定默认输出设备"""
        vol = self.vol.value() / 100
        self._audio_out = QAudioOutput(QMediaDevices.defaultAudioOutput())
        self._audio_out.setVolume(vol)
        self._player.setAudioOutput(self._audio_out)

    def _on_url_ready(self, url: str):
        if not url:
            # URL fetch failed — retry once, then skip
            self._retry_url()
            return
        # re-assert audio output in case stop() reset it on macOS
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(self.vol.value() / 100)
        self._player.setSource(QUrl(url))
        self._player.play()

    def _toggle_play(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self):
        self._player.stop()

    def _seek_start(self):
        self._seeking = True

    def _seek_end(self):
        dur = self._player.duration()
        if dur > 0:
            self._player.setPosition(int(self.prog.value() / 1000 * dur))
        self._seeking = False

    # ── player callbacks ───────────────────────────────────
    def _on_position(self, pos_ms: int):
        if self._seeking:
            return
        dur = self._player.duration()
        if dur > 0:
            self.prog.setValue(int(pos_ms / dur * 1000))
        self.t_cur.setText(fmt_duration(pos_ms) if HAS_NETEASE else "")
        self.position_changed.emit(pos_ms)

    def _on_duration(self, dur_ms: int):
        self.t_tot.setText(fmt_duration(dur_ms) if HAS_NETEASE else "")

    def _on_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸")
            self._spec_timer.start(150)
        else:
            self.btn_play.setText("▶")
            self._spec_timer.stop()
            self.spec.setText("▁▂▃▄▅")
        labels = {
            QMediaPlayer.PlaybackState.PlayingState:  "PLAYING",
            QMediaPlayer.PlaybackState.PausedState:   "PAUSED",
            QMediaPlayer.PlaybackState.StoppedState:  "STOPPED",
        }
        self.status_lbl.setText(labels.get(state, ""))

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.request_next.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._retry_url()
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            # Network stall — start a 12s watchdog, retry if still stalled
            if not hasattr(self, "_stall_timer"):
                self._stall_timer = QTimer(self)
                self._stall_timer.setSingleShot(True)
                self._stall_timer.timeout.connect(self._on_stall_timeout)
            self._stall_timer.start(12000)
        elif status == QMediaPlayer.MediaStatus.BufferingMedia:
            # Recovered from stall — cancel watchdog
            if hasattr(self, "_stall_timer"):
                self._stall_timer.stop()
        elif status == QMediaPlayer.MediaStatus.LoadedMedia:
            if hasattr(self, "_stall_timer"):
                self._stall_timer.stop()

    def _on_stall_timeout(self):
        if self._player.mediaStatus() == QMediaPlayer.MediaStatus.StalledMedia:
            print("[player] stall timeout, retrying")
            self._retry_url()

    def _on_player_error(self, err, msg: str):
        print(f"[player] error {err}: {msg}")
        # Only retry on recoverable errors (network/resource), not format errors
        recoverable = {
            QMediaPlayer.Error.ResourceError,
            QMediaPlayer.Error.NetworkError,
        }
        if err in recoverable:
            self._retry_url()

    def _retry_url(self):
        """URL 失效时重新拉取，最多重试 1 次，失败则跳下一首"""
        if not self._current_song:
            return
        if getattr(self, "_retry_count", 0) >= 1:
            print("[player] retry exhausted, skipping to next")
            self.status_lbl.setText("链接失效，跳过")
            self.request_next.emit()
            return
        self._retry_count = getattr(self, "_retry_count", 0) + 1
        print(f"[player] retrying URL for {self._current_song.get('name')}")
        self.status_lbl.setText("重新获取链接...")
        if hasattr(self, "_url_worker") and self._url_worker is not None:
            try:
                self._url_worker.url_ready.disconnect()
            except Exception:
                pass
        self._url_worker = UrlFetchWorker(self._current_song["id"])
        self._url_worker.url_ready.connect(self._on_url_ready)
        self._url_worker.start()

    def _anim(self):
        self._fi = (self._fi + 1) % len(self._frames)
        self.spec.setText(self._frames[self._fi])

    # kept for compatibility with MainWindow._on_song_selected
    def set_song(self, name: str, artist: str, duration_ms: int = 0):
        self.song_lbl.setText(f"{name} - {artist}")
        self.t_tot.setText(fmt_duration(duration_ms) if HAS_NETEASE else "")

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG_CARD']}; border-bottom:1px solid {c['BORDER']};")
        self.spec.setStyleSheet(f"color:{c['ACCENT']};")
        self.song_lbl.setStyleSheet(f"color:{c['TEXT']};")
        self.status_lbl.setStyleSheet(f"color:{c['ACCENT']}; letter-spacing:2px;")
        self.vol_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        self.t_cur.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        self.t_tot.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        slider_ss = f"""
            QSlider::groove:horizontal {{ height:2px; background:{c['BORDER']}; }}
            QSlider::sub-page:horizontal {{ background:{c['ACCENT']}; }}
            QSlider::handle:horizontal {{
                width:10px; height:10px; margin:-4px 0;
                background:{c['TEXT']}; border-radius:5px;
            }}
        """
        self.vol.setStyleSheet(slider_ss)
        self.prog.setStyleSheet(slider_ss)
        btn_ss = f"""
            QPushButton {{
                background:transparent; color:{c['TEXT']};
                border:1px solid {c['BORDER']}; border-radius:16px;
            }}
            QPushButton:hover {{ border-color:{c['ACCENT']}; color:{c['ACCENT']}; }}
            QPushButton:checked {{ background:{c['ACCENT']}; color:#13111f; border-color:{c['ACCENT']}; }}
        """
        for b in self.ctrl_btns:
            b.setStyleSheet(btn_ss)


# ── QueuePanel ────────────────────────────────────────────
class QueuePanel(QFrame):
    song_selected    = pyqtSignal(int)   # liked songs tab → index into _songs
    ai_song_selected = pyqtSignal(dict)  # AI tab → song dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._songs   = []
        self._current = 0
        self._rows    = []
        self._ai_songs = []
        self._ai_rows  = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs)

        # ── Tab 0: QUEUE ──────────────────────────────────
        queue_w = QWidget()
        ql = QVBoxLayout(queue_w)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(0)

        self.hdr_frame = QFrame()
        self.hdr_frame.setFixedHeight(32)
        hl = QHBoxLayout(self.hdr_frame)
        hl.setContentsMargins(16, 0, 16, 0)
        self.hdr_title = QLabel("QUEUE")
        self.hdr_title.setFont(mono(9, True))
        self.hdr_count = QLabel("0 TRACKS")
        self.hdr_count.setFont(mono(8))
        hl.addWidget(self.hdr_title)
        hl.addStretch()
        hl.addWidget(self.hdr_count)
        ql.addWidget(self.hdr_frame)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._container = QWidget()
        self._list_lay = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(0)
        self._list_lay.addStretch()
        self.scroll.setWidget(self._container)
        ql.addWidget(self.scroll)

        self.tabs.addTab(queue_w, "QUEUE")

        # ── Tab 1: AI 点歌 ────────────────────────────────
        ai_w = QWidget()
        al = QVBoxLayout(ai_w)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)

        self.ai_hdr_frame = QFrame()
        self.ai_hdr_frame.setFixedHeight(32)
        ahl = QHBoxLayout(self.ai_hdr_frame)
        ahl.setContentsMargins(16, 0, 16, 0)
        self.ai_hdr_title = QLabel("AI 点歌")
        self.ai_hdr_title.setFont(mono(9, True))
        self.ai_hdr_count = QLabel("0 TRACKS")
        self.ai_hdr_count.setFont(mono(8))
        ahl.addWidget(self.ai_hdr_title)
        ahl.addStretch()
        ahl.addWidget(self.ai_hdr_count)
        al.addWidget(self.ai_hdr_frame)

        self.ai_scroll = QScrollArea()
        self.ai_scroll.setWidgetResizable(True)
        self.ai_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ai_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ai_container = QWidget()
        self._ai_list_lay = QVBoxLayout(self._ai_container)
        self._ai_list_lay.setContentsMargins(0, 0, 0, 0)
        self._ai_list_lay.setSpacing(0)
        self._ai_list_lay.addStretch()
        self.ai_scroll.setWidget(self._ai_container)
        al.addWidget(self.ai_scroll)

        self.tabs.addTab(ai_w, "AI 点歌")

        # ── Tab 2: 歌词 ───────────────────────────────────
        lyrics_w = QWidget()
        lyl = QVBoxLayout(lyrics_w)
        lyl.setContentsMargins(0, 0, 0, 0)
        lyl.setSpacing(0)

        self.lyrics_hdr_frame = QFrame()
        self.lyrics_hdr_frame.setFixedHeight(32)
        lyhl = QHBoxLayout(self.lyrics_hdr_frame)
        lyhl.setContentsMargins(16, 0, 16, 0)
        self.lyrics_hdr_title = QLabel("歌词")
        self.lyrics_hdr_title.setFont(mono(9, True))
        self.lyrics_song_lbl = QLabel("")
        self.lyrics_song_lbl.setFont(mono(8))
        lyhl.addWidget(self.lyrics_hdr_title)
        lyhl.addStretch()
        lyhl.addWidget(self.lyrics_song_lbl)
        lyl.addWidget(self.lyrics_hdr_frame)

        self.lyrics_scroll = QScrollArea()
        self.lyrics_scroll.setWidgetResizable(True)
        self.lyrics_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lyrics_container = QWidget()
        self._lyrics_lay = QVBoxLayout(self._lyrics_container)
        self._lyrics_lay.setContentsMargins(0, 24, 0, 24)
        self._lyrics_lay.setSpacing(0)
        self._lyrics_lay.addStretch()
        self.lyrics_scroll.setWidget(self._lyrics_container)
        lyl.addWidget(self.lyrics_scroll)

        self.tabs.addTab(lyrics_w, "歌词")

        self._lyrics: list = []          # [(ms, text), ...]
        self._lyrics_labels: list = []
        self._lyrics_current = -1

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    # ── liked songs ───────────────────────────────────────
    def set_songs(self, songs: list):
        self._songs = songs
        self._rows.clear()
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.hdr_count.setText(f"{len(songs)} TRACKS")
        for i, s in enumerate(songs):
            row = self._make_row(s["name"], s["artist"], f"{i+1:02d}")
            self._rows.append(row)
            idx = i
            row.mousePressEvent = lambda _, i=idx: self._select(i)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)

        self.set_current(0)

    def set_current(self, idx: int):
        self._current = idx
        self._refresh_rows()

    def _select(self, idx: int):
        self.set_current(idx)
        self.song_selected.emit(idx)

    def _refresh_rows(self):
        c = tm().colors
        for i, row in enumerate(self._rows):
            playing = (i == self._current)
            if playing:
                row.setStyleSheet(
                    f"background:{c['BG_PLAYING']}; border-left:3px solid {c['ACCENT']};"
                )
                row._num_l.setStyleSheet(f"color:{c['ACCENT']};")
                row._song_l.setStyleSheet(f"color:{c['TEXT']}; font-weight:bold;")
                row._art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
            else:
                row.setStyleSheet("background:transparent; border-left:3px solid transparent;")
                row._num_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                row._song_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                row._art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")

    # ── AI playlist ───────────────────────────────────────
    def add_ai_song(self, song: dict, switch_tab: bool = True):
        """Add a song to the AI tab (dedup by id)."""
        sid = song.get("id")
        if sid and any(s.get("id") == sid for s in self._ai_songs):
            if switch_tab:
                self.tabs.setCurrentIndex(1)
            return
        self._ai_songs.append(song)
        idx = len(self._ai_songs) - 1
        row = self._make_row(song.get("name", ""), song.get("artist", ""), f"{idx+1:02d}")
        self._ai_rows.append(row)
        row.mousePressEvent = lambda _, s=song: self._select_ai(s)
        self._ai_list_lay.insertWidget(self._ai_list_lay.count() - 1, row)
        self.ai_hdr_count.setText(f"{len(self._ai_songs)} TRACKS")
        self._refresh_ai_rows()
        if switch_tab:
            self.tabs.setCurrentIndex(1)

    def restore_ai_songs(self, songs: list):
        """启动时从数据库恢复 AI 点歌列表，不切换 tab"""
        for song in songs:
            self.add_ai_song(song, switch_tab=False)

    def clear_ai_songs(self):
        """清空 AI 点歌 UI（切换账号时调用）"""
        self._ai_songs.clear()
        self._ai_rows.clear()
        while self._ai_list_lay.count() > 1:
            item = self._ai_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.ai_hdr_count.setText("0 TRACKS")

    def set_ai_current(self, song: dict):
        """Highlight the currently playing AI song."""
        sid = song.get("id")
        self._ai_current_id = sid
        self._refresh_ai_rows()

    def _select_ai(self, song: dict):
        self._ai_current_id = song.get("id")
        self._refresh_ai_rows()
        self.ai_song_selected.emit(song)

    def _refresh_ai_rows(self):
        c = tm().colors
        cur = getattr(self, "_ai_current_id", None)
        for i, row in enumerate(self._ai_rows):
            playing = (self._ai_songs[i].get("id") == cur) if cur else False
            if playing:
                row.setStyleSheet(
                    f"background:{c['BG_PLAYING']}; border-left:3px solid {c['ACCENT']};"
                )
                row._num_l.setStyleSheet(f"color:{c['ACCENT']};")
                row._song_l.setStyleSheet(f"color:{c['TEXT']}; font-weight:bold;")
                row._art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
            else:
                row.setStyleSheet("background:transparent; border-left:3px solid transparent;")
                row._num_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                row._song_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                row._art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")

    # ── lyrics ────────────────────────────────────────────
    def set_lyrics(self, song_name: str, lines: list):
        """Set lyrics for the current song. lines = [(ms, text), ...]"""
        self._lyrics = lines
        self._lyrics_current = -1
        self._lyrics_labels.clear()
        # Clear old labels
        while self._lyrics_lay.count() > 1:
            item = self._lyrics_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.lyrics_song_lbl.setText(song_name[:22] if song_name else "")
        c = tm().colors

        if not lines:
            lbl = QLabel("暂无歌词")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(mono(10))
            lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
            lbl.setContentsMargins(0, 8, 0, 8)
            self._lyrics_lay.insertWidget(0, lbl)
            return

        for ms, text in lines:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(mono(11))
            lbl.setWordWrap(True)
            lbl.setContentsMargins(16, 7, 16, 7)
            lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
            self._lyrics_labels.append(lbl)
            self._lyrics_lay.insertWidget(self._lyrics_lay.count() - 1, lbl)

    def update_lyrics_position(self, ms: int):
        """Highlight the lyric line matching the current playback position."""
        if not self._lyrics or not self._lyrics_labels:
            return
        # Find the last line whose timestamp <= ms
        idx = 0
        for i, (t, _) in enumerate(self._lyrics):
            if t <= ms:
                idx = i
            else:
                break
        if idx == self._lyrics_current:
            return
        c = tm().colors
        # Unhighlight previous
        if 0 <= self._lyrics_current < len(self._lyrics_labels):
            self._lyrics_labels[self._lyrics_current].setFont(mono(11))
            self._lyrics_labels[self._lyrics_current].setStyleSheet(
                f"color:{c['TEXT_MUTED']};"
            )
        # Highlight current
        self._lyrics_current = idx
        lbl = self._lyrics_labels[idx]
        lbl.setFont(mono(12, True))
        lbl.setStyleSheet(f"color:{c['ACCENT']}; font-weight:bold;")
        # Scroll to center the current line
        QTimer.singleShot(0, lambda: self.lyrics_scroll.ensureWidgetVisible(lbl, 0, 80))

    # ── helpers ───────────────────────────────────────────
    def _make_row(self, name: str, artist: str, num: str) -> QFrame:
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 5, 16, 5)
        num_l  = QLabel(num);    num_l.setFont(mono(9));  num_l.setFixedWidth(24)
        song_l = QLabel(name);   song_l.setFont(mono(10))
        art_l  = QLabel(artist); art_l.setFont(mono(9))
        rl.addWidget(num_l)
        rl.addWidget(song_l)
        rl.addStretch()
        rl.addWidget(art_l)
        row._num_l  = num_l
        row._song_l = song_l
        row._art_l  = art_l
        return row

    def _apply_theme(self, c):
        card = c['BG_CARD']
        border = c['BORDER']
        accent = c['ACCENT']
        muted  = c['TEXT_MUTED']
        text   = c['TEXT']
        bg     = c['BG']

        self.setStyleSheet(f"background:{card};")
        self.tabs.setStyleSheet(f"""
            QTabWidget {{
                background: {bg};
            }}
            QTabWidget::pane {{
                border: none;
                background: {card};
            }}
            QTabWidget::tab-bar {{
                alignment: left;
            }}
            QTabBar {{
                background: {bg};
                border: none;
            }}
            QTabBar::tab {{
                background: {bg};
                color: {muted};
                padding: 6px 20px;
                border: none;
                font-family: Menlo, Monaco, "Courier New";
                font-size: 9pt;
                letter-spacing: 2px;
                min-width: 80px;
            }}
            QTabBar::tab:selected {{
                background: {card};
                color: {accent};
                border-bottom: 2px solid {accent};
            }}
            QTabBar::tab:hover {{
                color: {text};
            }}
            QTabBar::scroller {{
                width: 0px;
            }}
        """)
        # Force tab bar background via palette to cover the right-side gap
        from PyQt6.QtGui import QPalette, QColor as _QColor
        pal = self.tabs.tabBar().palette()
        pal.setColor(QPalette.ColorRole.Window, _QColor(bg))
        pal.setColor(QPalette.ColorRole.Button, _QColor(bg))
        self.tabs.tabBar().setPalette(pal)
        self.tabs.tabBar().setAutoFillBackground(True)
        self.tabs.tabBar().setExpanding(True)   # tabs fill full width, no gap
        for frame in (self.hdr_frame, self.ai_hdr_frame, self.lyrics_hdr_frame):
            frame.setStyleSheet(f"background:{card}; border-bottom:1px solid {border};")
        self.hdr_title.setStyleSheet(f"color:{text}; letter-spacing:2px;")
        self.hdr_count.setStyleSheet(f"color:{muted};")
        self.ai_hdr_title.setStyleSheet(f"color:{text}; letter-spacing:2px;")
        self.ai_hdr_count.setStyleSheet(f"color:{muted};")
        self.lyrics_hdr_title.setStyleSheet(f"color:{text}; letter-spacing:2px;")
        self.lyrics_song_lbl.setStyleSheet(f"color:{muted};")
        for s in (self.scroll, self.ai_scroll, self.lyrics_scroll):
            s.setStyleSheet(f"background:{card}; border:none;")
        for cont in (self._container, self._ai_container, self._lyrics_container):
            cont.setStyleSheet(f"background:{card};")
        self._refresh_rows()
        self._refresh_ai_rows()


# ── QR 后台 Worker ────────────────────────────────────────
class QRWorker(QThread):
    qr_ready    = pyqtSignal(bytes, str)   # png_data, unikey
    qr_error    = pyqtSignal(str)
    poll_result = pyqtSignal(int, str)     # code, message

    def __init__(self, mode: str, unikey: str = ""):
        super().__init__()
        self.mode   = mode   # "fetch" | "poll"
        self.unikey = unikey

    def run(self):
        if self.mode == "fetch":
            try:
                unikey, url = get_qr_code()
                img = qrcode.make(url)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                self.qr_ready.emit(buf.getvalue(), unikey)
            except Exception as e:
                self.qr_error.emit(str(e))
        elif self.mode == "poll":
            try:
                result = poll_qr_login(self.unikey)
                self.poll_result.emit(result["code"], result["message"])
            except Exception as e:
                self.poll_result.emit(0, f"轮询错误: {e}")


# ── QRLoginDialog ─────────────────────────────────────────
class QRLoginDialog(QDialog):
    login_success = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫码登录网易云音乐")
        self.setFixedSize(300, 380)
        self.setModal(True)
        c = tm().colors
        self.setStyleSheet(f"background:{c['BG_CARD']}; color:{c['TEXT']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = QLabel("扫码登录网易云音乐")
        title.setFont(mono(12, True))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{c['TEXT']};")
        lay.addWidget(title)

        self.qr_label = QLabel("生成二维码中...")
        self.qr_label.setFixedSize(210, 210)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background:white; border-radius:8px; color:#333;")
        lay.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.status_lbl = QLabel("正在获取二维码...")
        self.status_lbl.setFont(mono(9))
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        lay.addWidget(self.status_lbl)

        self.refresh_btn = QPushButton("刷新二维码")
        self.refresh_btn.setFont(mono(9))
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c['ACCENT']}; color:#13111f;
                border:none; border-radius:6px; padding:6px;
            }}
        """)
        self.refresh_btn.clicked.connect(self._load_qr)
        lay.addWidget(self.refresh_btn)

        self._unikey = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._worker = None
        self._load_qr()

    def _load_qr(self):
        self._poll_timer.stop()
        self.refresh_btn.setEnabled(False)
        self.status_lbl.setText("生成二维码中...")
        self.qr_label.setPixmap(QPixmap())
        self.qr_label.setText("生成中...")

        self._worker = QRWorker("fetch")
        self._worker.qr_ready.connect(self._on_qr_ready)
        self._worker.qr_error.connect(self._on_qr_error)
        self._worker.start()

    def _on_qr_ready(self, data: bytes, unikey: str):
        self._unikey = unikey
        px = QPixmap()
        px.loadFromData(data)
        self.qr_label.setText("")
        self.qr_label.setPixmap(px.scaled(
            210, 210,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self.status_lbl.setText("请用网易云 App 扫描二维码")
        self.refresh_btn.setEnabled(True)
        self._poll_timer.start(2000)

    def _on_qr_error(self, msg: str):
        self.status_lbl.setText(f"获取失败: {msg}")
        self.qr_label.setText("获取失败")
        self.refresh_btn.setEnabled(True)

    def _poll(self):
        if not self._unikey:
            return
        self._poll_timer.stop()
        w = QRWorker("poll", self._unikey)
        w.poll_result.connect(self._on_poll_result)
        w.start()
        self._worker = w

    def _on_poll_result(self, code: int, msg: str):
        self.status_lbl.setText(msg)
        if code == 800:
            self._load_qr()
        elif code == 803:
            self.login_success.emit()
            self.accept()
        else:
            self._poll_timer.start(2000)


# ── ChatBubble ────────────────────────────────────────────
class ChatBubble(QFrame):
    def __init__(self, text: str, username: str, timestamp: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 3, 12, 3)
        lay.setSpacing(8)

        self._bubble = QFrame()
        bl = QVBoxLayout(self._bubble)
        bl.setContentsMargins(10, 6, 10, 6)
        bl.setSpacing(2)

        meta = QHBoxLayout()
        self.uname_lbl = QLabel(username)
        self.uname_lbl.setFont(mono(8, True))
        self.ts_lbl = QLabel(timestamp)
        self.ts_lbl.setFont(mono(7))
        meta.addWidget(self.uname_lbl)
        meta.addStretch()
        meta.addWidget(self.ts_lbl)

        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setFont(mono(11))
        self.text_lbl.setMaximumWidth(300)
        self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bl.addLayout(meta)
        bl.addWidget(self.text_lbl)

        self._avatar = QLabel("DJ" if not is_user else username[:2])
        self._avatar.setFixedSize(32, 32)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setFont(mono(7, True))

        if is_user:
            lay.addStretch()
            lay.addWidget(self._bubble)
            lay.addWidget(self._avatar)
        else:
            lay.addWidget(self._avatar)
            lay.addWidget(self._bubble)
            lay.addStretch()

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, c):
        self._bubble.setStyleSheet(
            f"background:{c['BG_CARD']}; border-radius:12px; border:1px solid {c['BORDER']};"
        )
        self.uname_lbl.setStyleSheet(f"color:{c['ACCENT']};")
        self.ts_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        self.text_lbl.setStyleSheet(f"color:{c['TEXT']};")
        self._avatar.setStyleSheet(
            f"background:{c['ACCENT']}; color:#13111f; border-radius:16px;"
        )

    def update_text(self, text: str):
        self.text_lbl.setText(text)


# ── LiveChat ──────────────────────────────────────────────
class LiveChat(QFrame):
    play_song = pyqtSignal(dict)   # forwarded to MainWindow

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._current_bubble = None
        self._worker = None
        self._tts_worker = None
        self._tts_muted = True
        self._tts_voice = DEFAULT_VOICE
        self._username = "You"

        # media player for TTS audio
        self._player = QMediaPlayer()
        _dev = QMediaDevices.defaultAudioOutput()
        self._audio_out = QAudioOutput(_dev)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(1.0)
        self._tts_tmp_path = None
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._media_devices = QMediaDevices()
        self._media_devices.audioOutputsChanged.connect(self._on_audio_device_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # header
        self.hdr = QFrame()
        self.hdr.setFixedHeight(36)
        hl = QHBoxLayout(self.hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        self.hdr_title = QLabel("Claudio")
        self.hdr_title.setFont(mono(10, True))
        self.dot = PulseDot()
        self.live_lbl = QLabel("LIVE")
        self.live_lbl.setFont(mono(8, True))
        # mute toggle
        self.mute_btn = QPushButton("🔇")
        self.mute_btn.setFixedSize(28, 28)
        self.mute_btn.setToolTip("静音 / 取消静音")
        self.mute_btn.clicked.connect(self._toggle_mute)
        hl.addWidget(self.hdr_title)
        hl.addStretch()
        hl.addWidget(self.mute_btn)
        hl.addSpacing(8)
        hl.addWidget(self.dot)
        hl.addSpacing(4)
        hl.addWidget(self.live_lbl)
        lay.addWidget(self.hdr)

        # scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._msg_container = QWidget()
        self._msg_lay = QVBoxLayout(self._msg_container)
        self._msg_lay.setContentsMargins(0, 8, 0, 8)
        self._msg_lay.setSpacing(2)
        self._msg_lay.addStretch()
        self.scroll.setWidget(self._msg_container)
        lay.addWidget(self.scroll, 1)

        # input bar
        self.input_frame = QFrame()
        self.input_frame.setFixedHeight(56)
        il = QHBoxLayout(self.input_frame)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Say something to the DJ...")
        self.input.setFont(mono(11))

        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(36, 36)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(36, 36)

        il.addWidget(self.input)
        il.addWidget(self.mic_btn)
        il.addWidget(self.send_btn)
        lay.addWidget(self.input_frame)

        self.input.returnPressed.connect(self._on_send)
        self.send_btn.clicked.connect(self._on_send)
        self.mic_btn.clicked.connect(self._on_mic)
        self._mic_worker = None

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)
        # 不在此处加载历史，等账号确认后由 reload_history() 调用

    def _toggle_mute(self):
        self._tts_muted = not self._tts_muted
        self.mute_btn.setText("🔇" if self._tts_muted else "🔊")
        if self._tts_muted:
            self._player.stop()

    def _on_mic(self):
        # 正在录音 → 点击停止
        if self._mic_worker and self._mic_worker.isRunning():
            self._mic_worker.stop()
            self._mic_worker = None
            self.mic_btn.setText("🎙")
            self.input.setPlaceholderText("Say something to the DJ...")
            return
        # 开始录音
        self.mic_btn.setText("⏹")
        self.input.setPlaceholderText("正在录音，点击停止...")
        self._mic_worker = MicWorker()
        self._mic_worker.text_ready.connect(self._on_mic_text)
        self._mic_worker.error.connect(self._on_mic_error)
        self._mic_worker.start()

    def _on_mic_text(self, text: str):
        self.mic_btn.setText("🎙")
        self.input.setPlaceholderText("Say something to the DJ...")
        self.input.setText(text)
        self._on_send()

    def _on_mic_error(self, msg: str):
        self.mic_btn.setText("🎙")
        self.input.setPlaceholderText(msg)

    def set_username(self, nickname: str):
        """更新对话框标题为登录账号昵称"""
        self.hdr_title.setText(nickname if nickname else "Claudio")
        if nickname:
            self._username = nickname

    def clear_chat(self):
        """清空聊天 UI 和内存历史（切换账号时调用，不删数据库）"""
        self._history.clear()
        while self._msg_lay.count() > 1:
            item = self._msg_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def reload_history(self):
        """切换账号后加载该账号的历史记录"""
        self.clear_chat()
        self._load_history()

    def set_voice(self, voice_id: str):
        """切换 TTS 声音"""
        self._tts_voice = voice_id

    def _speak(self, text: str):
        if self._tts_muted or not HAS_TTS:
            return
        clean = text.replace("*", "").replace("`", "").replace("#", "").strip()
        if not clean:
            return
        self._tts_worker = TTSWorker(clean, voice=self._tts_voice)
        self._tts_worker.audio_ready.connect(self._on_audio_ready)
        self._tts_worker.start()

    def _on_audio_device_changed(self):
        self._audio_out = QAudioOutput(QMediaDevices.defaultAudioOutput())
        self._audio_out.setVolume(1.0)
        self._player.setAudioOutput(self._audio_out)

    def _on_audio_ready(self, path: str):
        self._tts_tmp_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _on_playback_state(self, state):
        # clean up temp file after playback finishes
        if state == QMediaPlayer.PlaybackState.StoppedState and self._tts_tmp_path:
            try:
                os.remove(self._tts_tmp_path)
            except Exception:
                pass
            self._tts_tmp_path = None

    def _load_history(self):
        if conv_store is None:
            return
        try:
            msgs = conv_store.load_recent(6)
            for m in msgs:
                self._add_bubble(m["content"], m["role"] == "user", animate=False)
        except Exception:
            pass

    def _add_bubble(self, text: str, is_user: bool, animate: bool = True) -> ChatBubble:
        now = datetime.now().strftime("%H:%M")
        uname = self._username if is_user else "Claudio"
        b = ChatBubble(text, uname, now, is_user)
        self._msg_lay.insertWidget(self._msg_lay.count() - 1, b)
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))
        return b

    def _on_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)

        self._add_bubble(text, is_user=True)
        self._current_bubble = self._add_bubble("▌", is_user=False)
        self._history.append({"role": "user", "content": text})

        self._worker = StreamWorker(text, list(self._history))
        self._worker.chunk.connect(self._on_chunk)
        self._worker.done.connect(self._on_done)
        self._worker.play_song.connect(self.play_song)
        self._worker.switch_voice.connect(self.set_voice)
        self._worker.start()

    def _on_chunk(self, text: str):
        if self._current_bubble:
            self._current_bubble.update_text(text + " ▌")

    def _on_done(self):
        if self._current_bubble:
            final = self._current_bubble.text_lbl.text().rstrip(" ▌")
            self._current_bubble.update_text(final)
            self._history.append({"role": "assistant", "content": final})
            self._speak(final)
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input.setFocus()

    def push_recommendation(self):
        """定时推送：由 Claudio 主动根据天气和心情推荐歌曲，不显示用户气泡。"""
        if self._worker and self._worker.isRunning():
            return  # 正在对话中，跳过本次推送
        hour = datetime.now().hour
        time_labels = {12: "中午", 15: "下午三点", 18: "傍晚"}
        time_str = time_labels.get(hour, f"{hour}点")
        prompt = (
            f"现在是{time_str}，请你主动根据当前天气和我们最近对话中感受到的心情，"
            f"给我推荐 3-5 首适合现在听的歌曲，并简短说明推荐理由。"
            f"如果合适的话可以直接帮我播放其中一首。"
        )
        self._current_bubble = self._add_bubble("▌", is_user=False)
        self._worker = StreamWorker(prompt, list(self._history))
        self._worker.chunk.connect(self._on_chunk)
        self._worker.done.connect(self._on_done)
        self._worker.play_song.connect(self.play_song)
        self._worker.switch_voice.connect(self.set_voice)
        self._worker.start()

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG']};")
        self.hdr.setStyleSheet(f"background:{c['BG_CARD']}; border-bottom:1px solid {c['BORDER']};")
        self.hdr_title.setStyleSheet(f"color:{c['TEXT']};")
        self.live_lbl.setStyleSheet(f"color:{c['ACCENT']}; letter-spacing:2px;")
        self.scroll.setStyleSheet(f"background:{c['BG']}; border:none;")
        self._msg_container.setStyleSheet(f"background:{c['BG']};")
        self.input_frame.setStyleSheet(f"background:{c['BG_CARD']}; border-top:1px solid {c['BORDER']};")
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background:{c['BG_INPUT']}; color:{c['TEXT']};
                border:1px solid {c['BORDER']}; border-radius:20px; padding:6px 16px;
            }}
            QLineEdit:focus {{ border:1px solid {c['ACCENT']}; }}
        """)
        self.mute_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{c['TEXT_MUTED']};
                border:none; font-size:14px;
            }}
            QPushButton:hover {{ color:{c['ACCENT']}; }}
        """)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c['BG_INPUT']}; color:{c['TEXT_MUTED']};
                border:1px solid {c['BORDER']}; border-radius:18px; font-size:14px;
            }}
            QPushButton:hover {{ border-color:{c['ACCENT']}; }}
        """)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background:{c['ACCENT']}; color:#13111f;
                border:none; border-radius:18px; font-size:14px; font-weight:bold;
            }}
            QPushButton:hover {{ opacity:0.85; }}
            QPushButton:disabled {{ background:{c['BG_PLAYING']}; color:{c['TEXT_MUTED']}; }}
        """)


# ── StatusBar ─────────────────────────────────────────────
class StatusBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        self.left = QLabel("CLAUDIO FM")
        self.left.setFont(mono(7))
        self.right = QLabel("● CONNECTED")
        self.right.setFont(mono(7))
        lay.addWidget(self.left)
        lay.addStretch()
        lay.addWidget(self.right)
        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG_CARD']}; border-top:1px solid {c['BORDER']};")
        self.left.setStyleSheet(f"color:{c['TEXT_MUTED']}; letter-spacing:2px;")
        self.right.setStyleSheet(f"color:{c['ACCENT']}; letter-spacing:1px;")

    def set_status(self, text: str):
        self.right.setText(text)


# ── MainWindow ────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Claudio FM")
        self.setFixedWidth(480)
        self.resize(480, 860)

        self.nav    = NavBar()
        self.clock  = ClockHero()
        self.player = PlayerBar()
        self.queue  = QueuePanel()
        self.chat   = LiveChat()
        self.status = StatusBar()

        # ── 加载遮罩页 ──────────────────────────────────────
        self._loading_page = QWidget()
        self._loading_page.setObjectName("loadingPage")
        ll = QVBoxLayout(self._loading_page)
        ll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.setSpacing(20)

        # 加载图
        _img_path = str(Path(__file__).parent.parent / "加载图.png")
        self._loading_img = QLabel()
        self._loading_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _px = QPixmap(_img_path)
        if not _px.isNull():
            _px = _px.scaled(200, 260, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        self._loading_img.setPixmap(_px)
        ll.addWidget(self._loading_img)

        self._loading_lbl = QLabel("你的私人 Claudio 努力加载中...")
        self._loading_lbl.setFont(mono(16, True))
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self._loading_lbl)
        self._loading_dots = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading)

        # ── 主内容页 ────────────────────────────────────────
        main_page = QWidget()
        lay = QVBoxLayout(main_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.nav)
        lay.addWidget(self.clock)
        lay.addWidget(self.player)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.queue)
        self.splitter.addWidget(self.chat)
        self.splitter.setSizes([220, 440])
        self.splitter.setHandleWidth(6)
        lay.addWidget(self.splitter, 1)
        lay.addWidget(self.status)

        # ── Stack ───────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._loading_page)   # index 0
        self._stack.addWidget(main_page)            # index 1
        self._stack.setCurrentIndex(0)
        self.setCentralWidget(self._stack)

        self._apply_splitter_style(tm().colors)
        tm().theme_changed.connect(self._apply_splitter_style)
        self.queue.song_selected.connect(self._on_song_selected)
        self.queue.ai_song_selected.connect(self._on_ai_song_selected)
        self.player.request_prev.connect(self._on_prev)
        self.player.request_next.connect(self._on_next)
        self.player.shuffle_changed.connect(self._on_shuffle_changed)
        self.player.position_changed.connect(self.queue.update_lyrics_position)
        self.nav.login_clicked.connect(self._show_qr_dialog)
        self.nav.settings_clicked.connect(self._show_settings)
        self.chat.play_song.connect(self._on_chat_play)
        tm().theme_changed.connect(self._apply_bg)
        self._apply_bg(tm().colors)

        self._shuffle = False
        self._play_context = "queue"   # "queue" | "ai"

        self._start_loader()

        # 定时推荐：每分钟检查，12:00 / 15:00 / 18:00 触发
        self._rec_fired = set()
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._check_recommendation)
        self._rec_timer.start(60_000)

    def _tick_loading(self):
        self._loading_dots = (self._loading_dots + 1) % 4
        self._loading_lbl.setText("你的私人 Claudio 努力加载中" + "." * self._loading_dots)

    def _show_main(self):
        self._loading_timer.stop()
        self._stack.setCurrentIndex(1)

    def _start_loader(self):
        self._loading_dots = 0
        self._loading_lbl.setText("你的私人 Claudio 努力加载中...")
        self._loading_timer.start(400)
        self.status.set_status("● 正在加载歌单...")
        self._loader = SongLoaderWorker()
        self._loader.songs_loaded.connect(self._on_songs_loaded)
        self._loader.need_login.connect(self._on_need_login)
        self._loader.start()

    def _apply_bg(self, c):
        self.setStyleSheet(f"background:{c['BG']};")
        self._loading_page.setStyleSheet(f"background:{c['BG']};")
        self._loading_lbl.setStyleSheet(f"color:{c['TEXT']}; letter-spacing:4px;")

    def _check_recommendation(self):
        now = datetime.now()
        key = (now.date(), now.hour)
        if now.hour in (12, 15, 18) and now.minute == 0 and key not in self._rec_fired:
            self._rec_fired.add(key)
            # 只在主界面已显示且用户已登录时推送
            if self._stack.currentIndex() == 1:
                self.chat.push_recommendation()

    def _apply_splitter_style(self, c):
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background:{c['BORDER']};
                border-top: 1px solid {c['BORDER']};
                border-bottom: 1px solid {c['BORDER']};
            }}
            QSplitter::handle:hover {{
                background:{c['ACCENT']};
            }}
        """)

    def _on_need_login(self):
        self._show_main()
        self.status.set_status("● 未登录")
        self._show_qr_dialog()

    def _show_settings(self):
        from ui.setup_wizard import SetupWizard, get_env_path
        from dotenv import load_dotenv
        wizard = SetupWizard(self)
        if wizard.exec() == SetupWizard.DialogCode.Accepted:
            load_dotenv(get_env_path(), override=True)
            self.status.set_status("● 配置已更新，重启后生效")

    def _show_qr_dialog(self):
        dlg = QRLoginDialog(self)
        dlg.login_success.connect(self._after_login)
        dlg.exec()

    def _after_login(self):
        self.chat.clear_chat()
        self._start_loader()

    def _on_songs_loaded(self, songs: list):
        self._show_main()
        if songs:
            self.queue.set_songs(songs)
            # 启动时只显示第一首，不自动播放
            self.queue.set_current(0)
            self.player.display_song(songs[0])
            if HAS_NETEASE:
                try:
                    profile = get_user_profile()
                    nickname = profile.get("nickname", "")
                    uid = profile.get("uid", 0)
                    # 切换到该用户的对话历史
                    if conv_store:
                        conv_store.set_user(uid)
                    self.nav.set_logged_in(nickname)
                    self.chat.set_username(nickname)
                    self.chat.reload_history()
                    # 恢复该账号的 AI 点歌列表
                    self.queue.clear_ai_songs()
                    if conv_store:
                        ai_songs = conv_store.load_ai_songs()
                        if ai_songs:
                            self.queue.restore_ai_songs(ai_songs)
                    self.status.set_status("● CONNECTED")
                except Exception:
                    pass

    def _fetch_lyrics(self, song: dict):
        """Fetch lyrics in background and populate the lyrics tab."""
        name = song.get("name", "")
        song_id = song.get("id")
        self.queue.set_lyrics(name, [])
        # Disconnect previous worker to avoid stale callback
        if hasattr(self, "_lyrics_worker") and self._lyrics_worker is not None:
            try:
                self._lyrics_worker.lyrics_ready.disconnect()
            except Exception:
                pass
        self._lyrics_worker = LyricsWorker(song_id)
        self._lyrics_worker.lyrics_ready.connect(
            lambda lines, n=name: self.queue.set_lyrics(n, lines)
        )
        self._lyrics_worker.start()

    def _on_song_selected(self, idx: int):
        songs = self.queue._songs
        if not songs or idx >= len(songs):
            return
        self._play_context = "queue"
        self.queue.set_current(idx)
        self.player.load_song(songs[idx])
        self._fetch_lyrics(songs[idx])

    def _on_shuffle_changed(self, enabled: bool):
        self._shuffle = enabled

    def _on_prev(self):
        if self._play_context == "ai":
            self._ai_prev()
        else:
            songs = self.queue._songs
            if not songs:
                return
            idx = max(0, self.queue._current - 1)
            self._on_song_selected(idx)

    def _on_next(self):
        if self._play_context == "ai":
            self._ai_next()
        else:
            songs = self.queue._songs
            if not songs:
                return
            if self._shuffle:
                current = self.queue._current
                choices = [i for i in range(len(songs)) if i != current]
                idx = random.choice(choices) if choices else current
            else:
                idx = (self.queue._current + 1) % len(songs)
            self._on_song_selected(idx)

    def _ai_prev(self):
        songs = self.queue._ai_songs
        if not songs:
            return
        cur_id = getattr(self.queue, "_ai_current_id", None)
        ids = [s.get("id") for s in songs]
        try:
            idx = ids.index(cur_id)
        except ValueError:
            idx = 0
        idx = max(0, idx - 1)
        self._play_ai_at(idx)

    def _ai_next(self):
        songs = self.queue._ai_songs
        if not songs:
            return
        cur_id = getattr(self.queue, "_ai_current_id", None)
        ids = [s.get("id") for s in songs]
        try:
            idx = ids.index(cur_id)
        except ValueError:
            idx = -1
        if self._shuffle:
            choices = [i for i in range(len(songs)) if i != idx]
            idx = random.choice(choices) if choices else idx
        else:
            idx = (idx + 1) % len(songs)
        self._play_ai_at(idx)

    def _play_ai_at(self, idx: int):
        songs = self.queue._ai_songs
        if not songs or idx >= len(songs):
            return
        song = songs[idx]
        self.queue.set_ai_current(song)
        self.player.load_song(song)
        self._fetch_lyrics(song)

    def _on_ai_song_selected(self, song: dict):
        self._play_context = "ai"
        self.queue.set_ai_current(song)
        self.player.load_song(song)
        self._fetch_lyrics(song)

    def _on_chat_play(self, song: dict):
        """AI 要求播放某首歌：加入 AI 点歌列表并播放"""
        self._play_context = "ai"
        self.queue.add_ai_song(song)
        self.queue.set_ai_current(song)
        if conv_store:
            try:
                conv_store.save_ai_song(song)
            except Exception:
                pass
        self.player.load_song(song)
        self._fetch_lyrics(song)


# ── launch ────────────────────────────────────────────────
def launch(app: QApplication = None):
    if app is None:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
    p = QPalette()
    c = tm().colors
    p.setColor(QPalette.ColorRole.Window,     QColor(c["BG"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(c["TEXT"]))
    p.setColor(QPalette.ColorRole.Base,       QColor(c["BG_INPUT"]))
    p.setColor(QPalette.ColorRole.Text,       QColor(c["TEXT"]))
    app.setPalette(p)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
