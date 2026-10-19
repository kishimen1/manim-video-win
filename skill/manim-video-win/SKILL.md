---
name: manim-video-win
description: 3Blue1Brown 風の解説動画を Manim で作る（Windows 版）。最初にナレーションの声とトーンをユーザーに確認し、場面ごとの台本を付け、AivisSpeech で読み上げて映像と合成し、字幕（.srt）付きの mp4 まで書き出す。「3b1b風の動画を作って」「Manimで〇〇を解説するアニメーション」「数学・概念の解説動画」「ナレーション付きのアニメーション動画」などの依頼で使う。静止画のスライドや、実写動画の編集には使わない。
---

# Manim で 3Blue1Brown 風の解説動画を作る（Windows 版）

使う人の多くはプログラミングに詳しくない。コマンドやエラーの中身をそのまま見せず、何をしているか・何をしてほしいかを短い日本語で伝える。

成果物は 1 本の動画プロジェクトフォルダ:

```
<作業フォルダ>\<テーマ名>\
  tbb_style.py    # 共通スタイル（assets\ からコピー）
  scene.py        # シーンごとの Scene クラス。台詞は self.say("…") で書く
  narration.md    # 台本（build.cmd narration で自動生成）
  final.mp4       # 音声付き完成動画
  final.srt       # 字幕
  build\ media\   # 中間ファイル（build\preview\ にコマ一覧の画像）
```

## 前提と道具

- `<skill>` はこの SKILL.md があるフォルダ（通常 `%USERPROFILE%\.agents\skills\manim-video-win`）。
- コマンドはすべて `<skill>\scripts\build.cmd` から実行する。PC に Python が無くても、uv が Python 3.12 を用意して `build.py` を動かす。PowerShell では `& "<skill>\scripts\build.cmd" <サブコマンド> ...` と書く。
- ツール（Manim・ffmpeg・LaTeX・AivisSpeech）は `setup.bat`（配布リポジトリの直下）でユーザー領域に入っている。場所は `<skill>\tools.json` の `root`、動画の作業フォルダは `work` に書かれている。
- **作業フォルダとテーマ名のフォルダは英数字だけにする**（日本語を含むパスだと数式の描画が失敗する）。例: `%USERPROFILE%\manim-videos\pythagoras`。`tools.json` の `work` の下に作る。
- 音声は **AivisSpeech**。`build.cmd` が裏でエンジン（`http://127.0.0.1:10101`）を自動起動する。初回は 1〜2 分かかる。予備に Windows 標準音声 `--engine sapi`（Haruka など）も使える。

## 手順

0. **環境を確かめる（毎回最初に 1 度）**: 作業フォルダで `build.cmd doctor --quick` を実行する。
   - `NG` があれば、→ の案内をユーザーに伝える。たいていは「`setup.bat` をもう一度ダブルクリックしてください」で直る。直るまで先に進まない。
   - AivisSpeech だけ NG のときは、ユーザーに断ったうえで `--engine sapi` で続けてもよい。

1. **声とトーンを確認する（必須・台本より先）**: チャットで次の 2 問を 1 回のメッセージで聞き、番号で答えてもらう。依頼文で両方指定されていれば省略してよい。
   - **声**: 1) `まお/おちつき`（女性・落ち着き、推奨） 2) `fumifumi/ノーマル`（男性・青年） 3) `阿井田 茂/Calm`（男性・中年バリトン） 4) `阿井田 茂/ノーマル`（男性・中年、明るめ） 5) その他（`build.cmd voices` の一覧から）
   - **トーン**: 1) 落ち着いた解説（です・ます、3b1b 風。推奨） 2) 親しみやすい語りかけ（「〜ですよね」「では、やってみましょう」多め） 3) 講義調（簡潔・断定的。「〜である」は使わず「〜です」で短く） 4) テンポよく（一文を短く、話速 1.1）
   - 答えは `scene.py` 先頭の `VOICE` / `SPEED` に書き、台詞の文体をトーンに合わせる。阿井田 茂で「落ち着いた解説」なら `Calm`、「親しみやすい」なら `ノーマル` のようにスタイルも合わせる。
   - 答えが無いまま進めるときの既定は `まお/おちつき`・落ち着いた解説。

2. **構成を決める**: テーマを 3〜8 シーンに分け、各シーンの「問い → 直観的な図 → 式 → まとめ」を考える。考え方は `references/style_guide.md`。

3. **プロジェクトを作る**: `work` の下に英数字の名前でフォルダを作り、`<skill>\assets\tbb_style.py` をコピーし、`<skill>\assets\scene_template.py` を元に `scene.py` を書く。
   - 1 シーン = `NarratedScene` を継承した 1 クラス。クラス名は `S01_Intro` のように番号を付ける（ファイル内の順番で連結される）。
   - 台詞は `with self.say("台詞"):` で書き、その台詞の間に見せるアニメーションをブロック内に置く。台詞は 1〜2 文ずつ、話し言葉で一文を短く。
     - ブロックの最後で、台詞の音声が終わるまで自動で待つ。アニメーションの方が長ければ次の台詞がその分遅れる。`run_time` は目安でよい。
     - 台詞の長さいっぱいに動かすなら `with self.say("…") as cue:` として `run_time=max(1.0, cue.remaining)`。
     - 台詞の文字列はそのまま書く（f 文字列や変数にしない）。build.py がコードを読んで先に音声を作るため。
   - 日本語は `jtext()`（游ゴシック／メイリオで描画）、数式は `MathTex`。`MathTex`/`Tex` に日本語を入れない。
   - `scene.py` は UTF-8 で保存する。

4. **台本を確認する**: `build.cmd narration scene.py` で `narration.md` を作り（各シーンの音声の長さ入り）、ユーザーに台本を見せて直す。ここで声やトーンを変えたいかもう一度聞いてよい。

5. **プレビューで確かめる（必須）**: `build.cmd preview scene.py`（480p で全シーンを描画）。
   - `build\preview\NN_<シーン名>.png` に、台詞ごとの「台詞が終わる直前のコマ」と台詞の文が並ぶ。**全シーンの画像を開いて見て**、台詞と画面が合っているか、文字が詰まりすぎていないかを確かめる。
   - 画面からのはみ出し・テキストの重なりは警告として端末と画像の下（赤字・赤枠）に出る。直す。意図した重なりならそのシーンに `LAYOUT_CHECK = False`。
   - 描画エラーは `build\logs\<シーン名>.log`。1 シーンだけなら `--scenes S02_Main`。
   - ユーザーに見た目を見せるときも、この一覧画像を渡す。

6. **完成版を書き出す**: `build.cmd render scene.py -q h`（1080p60）。`final.mp4` と `final.srt` ができる。最後にファイルの場所をユーザーに伝える（エクスプローラーで開くなら `explorer <フォルダ>`）。
   - 変わっていないシーンは描画し直さない（`変更なし`）。作り直すなら `--force`。
   - 一部だけ: `--scenes S02_Main,S03_Proof`／音声なし: `--no-audio`／並列数: `-j 2`（PC が重いときは下げる）
   - 声と話速は `scene.py` の `VOICE` / `SPEED` から読む。日本語の声の名前はコマンドに書かず `scene.py` に書く（`build.cmd` の引数で日本語が化けることがあるため）。一時的に変えるなら、`build.cmd voices` で調べた数字の style_id を `--voice <数字>` で渡す。
   - Windows 標準音声: `--engine sapi`（声を指定するなら `--voice "Microsoft Haruka Desktop"`、速さ `--rate 2`）。

## 声を増やす・読みを直す

- `build.cmd voices` で使える「話者/スタイル」と style_id を一覧表示。
- 声を増やすには AivisHub（https://hub.aivis-project.com/）でモデルを探し、`build.cmd install-voice <モデルページの URL か UUID>`。
- 読み間違い（専門用語・人名など）は台本側をひらがなにして直す。
- 公開する動画では、使った声のモデルの利用規約（クレジット表記の要否など）を AivisHub のモデルページで確認するようユーザーに伝える。

## うまくいかないとき

`references/troubleshooting.md` を見る。よくあるもの:

- Codex の承認を求められたら: `build.cmd` は手元のエンジン（127.0.0.1:10101）への接続、エンジンの起動、ツールのフォルダの読み取りを行う。ユーザーに「動画を作るために必要な操作です」と説明して許可してもらう。
- 日本語が豆腐（□）になる: `Text` ではなく `jtext()` を使う。
- `MathTex` のエラー: フォルダのパスに日本語が無いか確認。パッケージ不足なら `tools.json` の `root` の下の `TinyTeX\bin\windows\tlmgr.bat install <パッケージ名>`。
- 長い描画は `preview`（480p）で確認してから `render -q h` に上げる。4K は `-q k`（かなり時間がかかる）。
- `manim` を直接実行すると台詞の時刻が音声と合わない。必ず `build.cmd` を通す。
- `media\` と `build\` は消しても作り直される。
