"""3Blue1Brown 風スタイルの共通ヘルパー。

プロジェクトフォルダに scene.py と並べて置き、`from tbb_style import *` で使う。
"""
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from manim import *  # noqa: F401,F403

# ---- 全体設定 -------------------------------------------------------------
config.background_color = "#0E1117"  # 3b1b に近い、ほぼ黒の背景

# 3b1b でよく使われる配色（manim 標準の定数もそのまま使える）
PRIMARY = BLUE_C      # 主役の対象
SECONDARY = YELLOW_C  # 強調・注目
ACCENT = TEAL_C       # 補助
WARN = RED_C          # 対比・誤り
MUTED = GREY_B        # 補足テキスト

def _pick_jp_font():
    """OS に入っている日本語フォントを選ぶ（Windows: 游ゴシック → メイリオ → BIZ UD、macOS: ヒラギノ）。"""
    if sys.platform == "darwin":
        candidates = ["Hiragino Sans"]
    else:
        candidates = ["Yu Gothic UI", "Yu Gothic", "Meiryo", "BIZ UDPGothic", "MS Gothic", "Noto Sans CJK JP"]
    try:
        import manimpango
        installed = set(manimpango.list_fonts())
        for f in candidates:
            if f in installed:
                return f
    except Exception:
        pass
    return candidates[0]


JP_FONT = os.environ.get("MANIM_VIDEO_FONT") or _pick_jp_font()


def jtext(s, size=36, color=WHITE, weight=NORMAL, **kw):
    """日本語テキスト。LaTeX を使わず Pango で描画する。"""
    return Text(s, font=JP_FONT, font_size=size, color=color, weight=weight, **kw)


def title_card(s, sub=None):
    """シーン冒頭のタイトル（＋サブタイトル）。"""
    t = jtext(s, size=56, weight=BOLD)
    if sub is None:
        return t
    st = jtext(sub, size=30, color=MUTED)
    return VGroup(t, st).arrange(DOWN, buff=0.4)


def caption(s, size=30):
    """画面下部に置く短い説明文（字幕とは別の、画面上の説明）。"""
    return jtext(s, size=size, color=MUTED).to_edge(DOWN, buff=0.6)


# ---- ナレーションとの同期 ----------------------------------------------------
# build.py が先に音声を合成し、build/timings.json に「台詞 → 秒数」を書く。
# シーンは say() でその秒数を読み、台詞の長さに映像を合わせる。

BUILD_DIR = Path(os.environ.get("MANIM_VIDEO_BUILD", "build"))
CHARS_PER_SEC = 7.0  # 音声がまだ無いときの見積もり（日本語の読み上げ速度）


def spoken(text):
    """読み上げ用に整形（改行をつなぐ）。build.py と同じ規則。"""
    return re.sub(r"\s*\n\s*", "", text).strip()


def _load_timings():
    try:
        return json.loads((BUILD_DIR / "timings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Cue:
    """say() のブロック内で使う。台詞の長さと残り時間が分かる。"""

    def __init__(self, scene, text, duration):
        self.scene, self.text, self.duration = scene, text, duration
        self.start = scene.renderer.time

    @property
    def elapsed(self):
        return self.scene.renderer.time - self.start

    @property
    def remaining(self):
        """台詞が終わるまでの残り秒数（0 未満にはならない）。"""
        return max(0.0, self.duration - self.elapsed)


TEXT_TYPES = (Text, MarkupText, SingleStringMathTex, DecimalNumber)


def _describe(m):
    """警告に出す名前。テキストなら中身、グループなら最初のテキスト。"""
    for sm in m.get_family():
        if isinstance(sm, (Text, MarkupText)):
            s = sm.text
        elif isinstance(sm, SingleStringMathTex):
            s = sm.get_tex_string()
        elif isinstance(sm, DecimalNumber):
            s = "%g" % sm.get_value()
        else:
            continue
        s = s if len(s) <= 20 else s[:19] + "…"
        return "『%s』" % s if sm is m else "%s(『%s』…)" % (type(m).__name__, s)
    return type(m).__name__


def _visible_leaves(m):
    return [sm for sm in m.family_members_with_points()
            if isinstance(sm, VMobject)  # ValueTracker なども点を持つので除く
            and sm.get_fill_opacity() > 0.02
            or isinstance(sm, VMobject)
            and sm.get_stroke_opacity() > 0.02 and sm.get_stroke_width() > 0]


def _box(mobs):
    pts = np.concatenate([sm.points for sm in mobs])
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def _area(r):
    return max(1e-6, (r[2] - r[0]) * (r[3] - r[1]))


def _text_mobjects(mobs):
    """テキスト系 mobject を、それより内側に潜らずに集める。"""
    out = []
    for m in mobs:
        if isinstance(m, TEXT_TYPES):
            out.append(m)
        else:
            out += _text_mobjects(m.submobjects)
    return out


class NarratedScene(Scene):
    """ナレーション付きシーンの基底クラス。

    推奨: construct() の中で `with self.say("台詞"):` と書き、その台詞の間に
    見せるアニメーションをブロック内に置く。ブロックを抜けるとき、台詞が
    まだ続いていれば残りの時間だけ待つ。アニメーションの方が長ければ、
    次の台詞はその分だけ遅れて始まる（音声は映像に合わせて配置される）。

    従来の書き方（クラス変数 NARRATION に台本をまとめて書く）も使える。
    その場合は音声をシーン冒頭から流し、映像が短ければ最後のフレームを延ばす。

    play() のたびに、画面からはみ出した要素とテキスト同士の重なりを調べ、
    警告を build/scenes/<シーン名>.json に書く（build.py preview で一覧できる）。
    """

    NARRATION = ""
    GAP = 0.25          # 台詞と台詞の間（秒）
    LEAD_IN = 0.4       # シーン冒頭の最初の台詞の前に置く間（秒）
    LAYOUT_CHECK = True

    def setup(self):
        super().setup()
        self._timings = _load_timings()
        self._cues, self._warnings, self._seen = [], [], set()
        self._cue = None

    @contextmanager
    def say(self, text):
        if not self._cues and self.renderer.time < self.LEAD_IN:
            self.wait(self.LEAD_IN - self.renderer.time)  # シーンの切り替わり直後に話し始めない
        text = spoken(text)
        dur = self._timings.get(text)
        if dur is None:
            dur = len(text) / CHARS_PER_SEC
        cue = Cue(self, text, dur)
        self._cues.append({"text": text, "start": round(cue.start, 4), "duration": dur})
        self._cue = cue
        try:
            yield cue
        finally:
            rest = cue.remaining + self.GAP
            if rest >= 1 / config.frame_rate:
                self.wait(rest)
            self._check_layout()
            self._cue = None

    def play(self, *args, **kwargs):
        super().play(*args, **kwargs)
        self._check_layout()

    # ---- レイアウト検査 ----

    def _warn(self, kind, key, msg):
        if (kind, key) in self._seen:
            return
        self._seen.add((kind, key))
        w = {"kind": kind, "time": round(self.renderer.time, 2), "message": msg,
             "cue": self._cue.text if self._cue else None}
        self._warnings.append(w)
        print("[layout] %s %.1fs: %s" % (type(self).__name__, w["time"], msg), file=sys.stderr)

    def _check_layout(self):
        if not self.LAYOUT_CHECK:
            return
        hw, hh, tol = config.frame_width / 2, config.frame_height / 2, 0.05
        for m in self.mobjects:
            leaves = _visible_leaves(m)
            if not leaves:
                continue
            x0, y0, x1, y1 = _box(leaves)
            if x0 < -hw - tol or x1 > hw + tol or y0 < -hh - tol or y1 > hh + tol:
                name = _describe(m)
                self._warn("offscreen", name, "%s が画面からはみ出しています" % name)

        boxes = []
        for t in _text_mobjects(self.mobjects):
            leaves = _visible_leaves(t)
            if leaves:
                boxes.append((t, _box(leaves)))
        for i, (a, ba) in enumerate(boxes):
            for b, bb in boxes[i + 1:]:
                ix = min(ba[2], bb[2]) - max(ba[0], bb[0])
                iy = min(ba[3], bb[3]) - max(ba[1], bb[1])
                if ix <= 0.02 or iy <= 0.02:
                    continue
                inter = ix * iy
                if inter / (_area(ba) + _area(bb) - inter) > 0.9:
                    continue  # 同じ位置に重ねたコピー（TransformFromCopy の名残など）
                if inter / min(_area(ba), _area(bb)) < 0.1:
                    continue
                na, nb = _describe(a), _describe(b)
                self._warn("overlap", (na, nb), "%s と %s が重なっています" % (na, nb))

    def tear_down(self):
        super().tear_down()
        out = BUILD_DIR / "scenes"
        out.mkdir(parents=True, exist_ok=True)
        (out / ("%s.json" % type(self).__name__)).write_text(json.dumps(
            {"duration": round(self.renderer.time, 4), "cues": self._cues, "warnings": self._warnings},
            ensure_ascii=False, indent=1), encoding="utf-8")
