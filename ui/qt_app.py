import sys
import io
import asyncio
import tempfile
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QSlider, QScrollArea, QLineEdit,
    QDialog, QSizePolicy, QTextEdit, QSplitter,
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
        get_liked_songs, get_user_profile, fmt_duration, get_song_url,
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
    login_clicked = pyqtSignal()

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

        self.toggle_lbl = QLabel()
        self.toggle_lbl.setFont(mono(9, True))
        self.toggle_lbl.setFixedHeight(22)
        self.toggle_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_lbl.mousePressEvent = lambda _: self._on_toggle()

        right = QHBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.login_lbl)
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
            f"color:{c['TEXT_MUTED']}; letter-spacing:1px;"
            f" text-decoration:underline;"
        )
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


# ── ClockHero ─────────────────────────────────────────────
class ClockHero(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(200)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 20, 0, 16)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.clock_lbl = QLabel()
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_lbl.setFont(QFont("Courier New", 52, QFont.Weight.Bold))

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

        lay.addWidget(self.clock_lbl)
        lay.addWidget(self.date_lbl)
        lay.addSpacing(6)
        lay.addLayout(on_air_row)

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)
        self._tick()

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

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


# ── PlayerBar ─────────────────────────────────────────────
class PlayerBar(QFrame):
    # signals for MainWindow to call prev/next
    request_prev = pyqtSignal()
    request_next = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)

        # ── media backend ──────────────────────────────────
        self._player = QMediaPlayer()
        _dev = QMediaDevices.defaultAudioOutput()
        self._audio_out = QAudioOutput(_dev)
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.7)
        self._player.errorOccurred.connect(
            lambda err, msg: print(f"[player] error {err}: {msg}")
        )
        self._songs: list = []
        self._current_idx: int = 0
        self._seeking = False

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)

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
        self.btn_prev  = QPushButton("⏮"); self.btn_prev.setFixedSize(32, 32)
        self.btn_play  = QPushButton("▶"); self.btn_play.setFixedSize(32, 32)
        self.btn_next  = QPushButton("⏭"); self.btn_next.setFixedSize(32, 32)
        self.btn_stop  = QPushButton("⏹"); self.btn_stop.setFixedSize(32, 32)
        self.ctrl_btns = [self.btn_prev, self.btn_play, self.btn_next, self.btn_stop]
        for b in self.ctrl_btns:
            b.setFont(QFont("Arial", 12))
            mid.addWidget(b)

        self.btn_prev.clicked.connect(self.request_prev)
        self.btn_next.clicked.connect(self.request_next)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)

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
    def load_song(self, song: dict):
        """Load and immediately play a song dict {id, name, artist, duration_ms}"""
        self.song_lbl.setText(f"{song['name']} - {song['artist']}")
        self.status_lbl.setText("加载中...")
        self.prog.setValue(0)
        self.t_cur.setText("0:00")
        self.t_tot.setText(fmt_duration(song.get("duration_ms", 0)) if HAS_NETEASE else "")
        self._player.stop()
        self._url_worker = UrlFetchWorker(song["id"])
        self._url_worker.url_ready.connect(self._on_url_ready)
        self._url_worker.start()

    def _on_url_ready(self, url: str):
        if not url:
            self.status_lbl.setText("无法获取播放链接")
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
        """
        for b in self.ctrl_btns:
            b.setStyleSheet(btn_ss)


# ── QueuePanel ────────────────────────────────────────────
class QueuePanel(QFrame):
    song_selected = pyqtSignal(int)  # emits index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._songs = []
        self._current = 0
        self._rows = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # header
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
        outer.addWidget(self.hdr_frame)

        # scroll area for rows
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
        outer.addWidget(self.scroll)

        self._apply_theme(tm().colors)
        tm().theme_changed.connect(self._apply_theme)

    def set_songs(self, songs: list):
        self._songs = songs
        self._rows.clear()
        # clear layout
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.hdr_count.setText(f"{len(songs)} TRACKS")
        c = tm().colors
        for i, s in enumerate(songs):
            row = QFrame()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 5, 16, 5)
            num_l = QLabel(f"{i+1:02d}")
            num_l.setFont(mono(9))
            num_l.setFixedWidth(24)
            song_l = QLabel(s["name"])
            song_l.setFont(mono(10))
            art_l = QLabel(s["artist"])
            art_l.setFont(mono(9))
            rl.addWidget(num_l)
            rl.addWidget(song_l)
            rl.addStretch()
            rl.addWidget(art_l)
            self._rows.append((row, num_l, song_l, art_l))
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
        for i, (row, num_l, song_l, art_l) in enumerate(self._rows):
            playing = (i == self._current)
            if playing:
                row.setStyleSheet(
                    f"background:{c['BG_PLAYING']}; border-left:3px solid {c['ACCENT']};"
                )
                num_l.setStyleSheet(f"color:{c['ACCENT']};")
                song_l.setStyleSheet(f"color:{c['TEXT']}; font-weight:bold;")
                art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
            else:
                row.setStyleSheet("background:transparent; border-left:3px solid transparent;")
                num_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                song_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")
                art_l.setStyleSheet(f"color:{c['TEXT_MUTED']};")

    def _apply_theme(self, c):
        self.setStyleSheet(f"background:{c['BG_CARD']}; border-bottom:1px solid {c['BORDER']};")
        self.hdr_frame.setStyleSheet(f"background:{c['BG_CARD']}; border-bottom:1px solid {c['BORDER']};")
        self.hdr_title.setStyleSheet(f"color:{c['TEXT']}; letter-spacing:2px;")
        self.hdr_count.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        self.scroll.setStyleSheet(f"background:{c['BG_CARD']}; border:none;")
        self._container.setStyleSheet(f"background:{c['BG_CARD']};")
        self._refresh_rows()


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

        c = tm().colors
        bubble = QFrame()
        bubble.setStyleSheet(f"background:#221f38; border-radius:12px; border:1px solid {c['BORDER']};")
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(10, 6, 10, 6)
        bl.setSpacing(2)

        meta = QHBoxLayout()
        self.uname_lbl = QLabel(username)
        self.uname_lbl.setFont(mono(8, True))
        self.uname_lbl.setStyleSheet(f"color:{c['ACCENT']};")
        self.ts_lbl = QLabel(timestamp)
        self.ts_lbl.setFont(mono(7))
        self.ts_lbl.setStyleSheet(f"color:{c['TEXT_MUTED']};")
        meta.addWidget(self.uname_lbl)
        meta.addStretch()
        meta.addWidget(self.ts_lbl)

        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setFont(mono(11))
        self.text_lbl.setStyleSheet(f"color:{c['TEXT']};")
        self.text_lbl.setMaximumWidth(300)
        self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bl.addLayout(meta)
        bl.addWidget(self.text_lbl)

        avatar = QLabel("DJ" if not is_user else username[:2])
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFont(mono(7, True))
        avatar.setStyleSheet(f"background:{c['ACCENT']}; color:#13111f; border-radius:16px;")

        if is_user:
            lay.addStretch()
            lay.addWidget(bubble)
            lay.addWidget(avatar)
        else:
            lay.addWidget(avatar)
            lay.addWidget(bubble)
            lay.addStretch()

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
        self._tts_muted = False
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
        self.mute_btn = QPushButton("🔊")
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
        self._load_history()

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

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.nav)
        lay.addWidget(self.clock)
        lay.addWidget(self.player)

        # splitter: queue on top, chat on bottom — user can drag the handle
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.queue)
        self.splitter.addWidget(self.chat)
        self.splitter.setSizes([220, 440])   # initial proportions
        self.splitter.setHandleWidth(6)
        lay.addWidget(self.splitter, 1)

        lay.addWidget(self.status)

        self._apply_splitter_style(tm().colors)
        tm().theme_changed.connect(self._apply_splitter_style)

        self.queue.song_selected.connect(self._on_song_selected)
        self.player.request_prev.connect(self._on_prev)
        self.player.request_next.connect(self._on_next)
        self.nav.login_clicked.connect(self._show_qr_dialog)
        self.chat.play_song.connect(self._on_chat_play)
        tm().theme_changed.connect(self._apply_bg)
        self._apply_bg(tm().colors)

        # 启动时加载 session / 歌单
        self._loader = SongLoaderWorker()
        self._loader.songs_loaded.connect(self._on_songs_loaded)
        self._loader.need_login.connect(self._show_qr_dialog)
        self._loader.start()

    def _apply_bg(self, c):
        self.setStyleSheet(f"background:{c['BG']};")
        self.centralWidget().setStyleSheet(f"background:{c['BG']};")

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

    def _show_qr_dialog(self):
        dlg = QRLoginDialog(self)
        dlg.login_success.connect(self._after_login)
        dlg.exec()

    def _after_login(self):
        self.chat.clear_chat()
        self._loader = SongLoaderWorker()
        self._loader.songs_loaded.connect(self._on_songs_loaded)
        self._loader.need_login.connect(self._show_qr_dialog)
        self._loader.start()

    def _on_songs_loaded(self, songs: list):
        if songs:
            self.queue.set_songs(songs)
            self._on_song_selected(0)
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
                except Exception:
                    pass

    def _on_song_selected(self, idx: int):
        songs = self.queue._songs
        if not songs or idx >= len(songs):
            return
        self.queue.set_current(idx)
        self.player.load_song(songs[idx])

    def _on_prev(self):
        songs = self.queue._songs
        if not songs:
            return
        idx = max(0, self.queue._current - 1)
        self._on_song_selected(idx)

    def _on_next(self):
        songs = self.queue._songs
        if not songs:
            return
        idx = (self.queue._current + 1) % len(songs)
        self._on_song_selected(idx)

    def _on_chat_play(self, song: dict):
        """AI 要求播放某首歌：直接加载，不改变歌单"""
        self.player.load_song(song)


# ── launch ────────────────────────────────────────────────
def launch():
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
