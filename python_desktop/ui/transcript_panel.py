import html
import os
import re
from typing import Any, Dict, List
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QTextBrowser, QVBoxLayout, QWidget

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except Exception:  # QtMultimedia не установлен: покажем стенограмму без воспроизведения
    QAudioOutput = QMediaPlayer = None

_SPEAKER_COLORS = ["#6c8cff", "#e0883e", "#4fb286", "#c46bd6", "#d6566b", "#b8a227", "#3fb3c4", "#8e8e93"]


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _speaker_color(label: str) -> str:
    m = re.search(r"(\d+)\s*$", label)
    idx = int(m.group(1)) - 1 if m else sum(map(ord, label))
    return _SPEAKER_COLORS[idx % len(_SPEAKER_COLORS)]


class TranscriptPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.player_bar = QWidget()
        bar = QHBoxLayout(self.player_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self.play_btn = QPushButton("Воспроизвести")
        self.play_btn.clicked.connect(self._toggle)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._on_slider)
        self.time_lbl = QLabel("00:00 / 00:00")
        self.note_lbl = QLabel("")
        bar.addWidget(self.play_btn)
        bar.addWidget(self.slider, stretch=1)
        bar.addWidget(self.time_lbl)
        layout.addWidget(self.player_bar)
        layout.addWidget(self.note_lbl)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_link)
        layout.addWidget(self.browser, stretch=1)

        self.player = None
        if QMediaPlayer is not None:
            self.player = QMediaPlayer(self)
            self.audio_out = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_out)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
            self.player.playbackStateChanged.connect(self._on_state)
            self.player.errorOccurred.connect(self._on_error)
        self._has_audio = False
        self.player_bar.setVisible(False)
        self.note_lbl.setVisible(False)

    # ----- загрузка лекции -----
    def set_lecture(self, lec: Dict[str, Any], marks: List[Dict[str, Any]], dark: bool = True) -> None:
        audio = lec.get("audio_file") or ""
        self._has_audio = bool(self.player is not None and audio and os.path.isfile(audio))
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(os.path.abspath(audio)) if self._has_audio else QUrl())
        self.slider.setRange(0, 0)
        self.time_lbl.setText("00:00 / 00:00")
        self.player_bar.setVisible(self._has_audio)
        if self._has_audio:
            self.note_lbl.setVisible(False)
        else:
            self.note_lbl.setText("Аудиозапись недоступна: таймкоды показаны без перехода к записи.")
            self.note_lbl.setVisible(bool(lec.get("segments")))

        link = "#8b9dff" if dark else "#3b4fd6"
        self.browser.document().setDefaultStyleSheet(f"a {{ color: {link}; text-decoration: none; }}")
        self.browser.setHtml(self._build_html(lec, marks))

    def _stamp(self, seconds: float, label: str) -> str:
        if self._has_audio:
            return f'<a href="t:{float(seconds):.2f}">[{label}]</a>'
        return f"[{label}]"

    def _build_html(self, lec: Dict[str, Any], marks: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        if marks:
            parts.append("<p><b>Метки записи</b></p>")
            for m in marks:
                note = html.escape(m.get("note") or "Метка")
                parts.append(f"<p>{self._stamp(m['time_sec'], _mmss(m['time_sec']))} &nbsp;{note}</p>")
            parts.append("<hr>")
        segs = lec.get("segments") or []
        if segs:
            for s in segs:
                start = float(s.get("start", 0))
                label = s.get("time") or _mmss(start)
                who = ""
                if s.get("speaker"):
                    sp = html.escape(str(s["speaker"]))
                    who = f'<b style="color:{_speaker_color(str(s["speaker"]))}">{sp}:</b> '
                parts.append(f"<p>{self._stamp(start, html.escape(str(label)))} &nbsp;{who}{html.escape(s.get('text', ''))}</p>")
        else:
            body = html.escape(lec.get("raw_transcript") or "Стенограмма отсутствует.")
            parts.append("<p>" + body.replace("\n", "<br>") + "</p>")
        return "".join(parts)

    # ----- воспроизведение -----
    def _on_link(self, url: QUrl) -> None:
        text = url.toString()
        if self.player is None or not text.startswith("t:"):
            return
        try:
            seconds = float(text[2:])
        except ValueError:
            return
        self.player.setPosition(int(seconds * 1000))
        self.player.play()

    def _toggle(self) -> None:
        if self.player is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_slider(self, value: int) -> None:
        if self.player is not None:
            self.player.setPosition(value)

    def _on_position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_lbl.setText(f"{_mmss(ms / 1000)} / {_mmss(self.slider.maximum() / 1000)}")

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, ms)

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setText("Пауза" if playing else "Воспроизвести")

    def _on_error(self, *_args) -> None:
        self.note_lbl.setText("Не удалось воспроизвести запись (формат файла не поддерживается системой).")
        self.note_lbl.setVisible(True)

    def stop(self) -> None:
        if self.player is not None:
            self.player.stop()
