"""動画タイトル: <ここに動画のタイトル>

シーンはファイル内に書いた順番で連結される。
`with self.say("台詞"):` のブロック内に、その台詞の間に見せるアニメーションを書く。
台詞の音声が終わるまでブロックの最後で自動的に待つので、run_time は目安でよい。
"""
from tbb_style import *

# ナレーションの声と話速（build.py が読む。--voice / --speed を付けるとそちらが優先）
VOICE = "まお/おちつき"
SPEED = 1.0


class S01_Intro(NarratedScene):
    def construct(self):
        title = title_card("動画のタイトル", "サブタイトル")
        with self.say("ここに、このシーンで読み上げるナレーションを書きます。"):
            self.play(Write(title[0]), run_time=1.5)
            self.play(FadeIn(title[1], shift=UP * 0.3))
        with self.say("台詞は一文ずつ分けると、映像と音声がぴったり合います。"):
            self.play(title.animate.scale(0.6).to_edge(UP))


class S02_Main(NarratedScene):
    def construct(self):
        # 部分ごとに色を変えたい数式は、パーツを分けて渡す
        eq = MathTex("a^2", "+", "b^2", "=", "c^2", font_size=72)
        with self.say("次のシーンのナレーションです。"):
            self.play(Write(eq))
        # 台詞の長さいっぱいに動かしたいときは cue.remaining を使う
        with self.say("この部分に注目してください。") as cue:
            self.play(eq[4].animate.set_color(SECONDARY), run_time=max(1.0, cue.remaining))
