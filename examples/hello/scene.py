"""動作確認用の最小の動画（約 20 秒）。

使い方: このフォルダに tbb_style.py をコピーしてから
  & "$env:USERPROFILE\.agents\skills\manim-video-win\scripts\build.cmd" render scene.py
"""
from tbb_style import *

VOICE = "まお/おちつき"
SPEED = 1.0


class S01_Intro(NarratedScene):
    def construct(self):
        title = title_card("三平方の定理", "動作確認用のサンプル")
        with self.say("これは、動作確認用のサンプル動画です。"):
            self.play(Write(title[0]))
            self.play(FadeIn(title[1], shift=UP * 0.3))
        with self.say("日本語の文字と、数式が表示されれば成功です。"):
            self.play(title.animate.scale(0.6).to_edge(UP))


class S02_Formula(NarratedScene):
    def construct(self):
        eq = MathTex("a^2", "+", "b^2", "=", "c^2", font_size=72)
        with self.say("直角三角形の三辺には、この関係があります。"):
            self.play(Write(eq))
        with self.say("斜辺の二乗は、残りの二辺の二乗の和です。") as cue:
            self.play(eq[4].animate.set_color(SECONDARY), run_time=max(1.0, cue.remaining))
