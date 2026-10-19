# 3Blue1Brown 風にするためのガイド

## 構成の原則

- **問いから始める**: 冒頭で「なぜこうなるのか？」という問いを見せる。答えはすぐ言わない。
- **図が先、式が後**: 直観的な図や動きを見せてから、それを式に落とす。式の各項は図の対応部分と同じ色にする。
- **一度に一つ**: 1 シーンで新しく出す概念は一つだけ。画面に出す要素は 3〜5 個まで。
- **変形で見せる**: 消して出すより `Transform` / `ReplacementTransform` / `TransformMatchingTex` で形を変えて、つながりを見せる。
- **最後に振り返る**: まとめシーンで最初の問いに戻り、答えを一言で言う。

## 見た目

- 背景はほぼ黒（`tbb_style` で設定済み）。色は `PRIMARY`(青) / `SECONDARY`(黄) / `ACCENT`(青緑) / `WARN`(赤) を役割で使い分け、同じ対象には動画全体で同じ色を使う。
- 強調は `Indicate`, `Circumscribe`, `Flash`, `SurroundingRectangle`。
- 文字は少なく。説明は基本ナレーションで行い、画面には要点のキーワードと式だけ置く。

## ナレーションの書き方

- 話し言葉で、一文 40 字以内を目安に。「〜ですね」「では、」のような語りかけを入れる。
- 画面の動きと同時に話す内容を書く（「この青い部分が…」）。画面に無いものを指さない。
- 数式は読み方で書く（`x^2` → 「エックスの二乗」）。記号や英字の読みが怪しい箇所はひらがなにする。

## よく使う API（Manim Community）

```python
# 生成・消去
Write(mob), Create(mob), FadeIn(mob, shift=UP), FadeOut(mob), GrowFromCenter(mob), DrawBorderThenFill(mob)
# 変形
Transform(a, b), ReplacementTransform(a, b), TransformMatchingTex(eq1, eq2), mob.animate.shift(RIGHT).scale(0.5)
# 強調
Indicate(mob), Circumscribe(mob), Flash(point), SurroundingRectangle(mob, color=YELLOW)
# 座標・グラフ
ax = Axes(x_range=[-3, 3, 1], y_range=[-1, 9, 2], tips=False)
graph = ax.plot(lambda x: x**2, color=PRIMARY)
area = ax.get_area(graph, x_range=[0, 2], color=ACCENT, opacity=0.4)
dot = Dot(ax.c2p(1, 1))
# 値を動かす
t = ValueTracker(0)
dot.add_updater(lambda d: d.move_to(ax.c2p(t.get_value(), t.get_value()**2)))
self.play(t.animate.set_value(2), run_time=3)
# 数値表示
num = DecimalNumber(0, num_decimal_places=2).add_updater(lambda n: n.set_value(t.get_value()))
# 配置
VGroup(a, b, c).arrange(RIGHT, buff=0.5); mob.next_to(other, DOWN); mob.to_edge(UP); mob.to_corner(UL)
# ベクトル・平面
plane = NumberPlane(); arrow = Vector([2, 1], color=YELLOW)
self.play(ApplyMatrix([[1, 1], [0, 1]], plane))   # 線形変換（LinearTransformationScene も便利）
# 3D は ThreeDScene を継承し self.set_camera_orientation(phi=70*DEGREES, theta=-45*DEGREES)
```

ドキュメント: https://docs.manim.community/
