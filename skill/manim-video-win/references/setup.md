# セットアップ（Windows 10/11, 64 ビット）

ふつうは配布リポジトリ直下の `setup.bat` をダブルクリックするだけでよい。管理者権限は不要。何度実行してもよい（入っているものは飛ばす）。

`setup.bat` は `scripts\setup.ps1` を呼び、次を入れる。

| もの | 用途 | 入る場所 |
|---|---|---|
| uv / Python 3.12 / Manim | 描画 | `%USERPROFILE%\.local\bin`、`%APPDATA%\uv` |
| ffmpeg（BtbN ビルド） | 映像と音声の合成 | `<root>\ffmpeg` |
| TinyTeX + 数式用パッケージ | `MathTex` | `<root>\TinyTeX` |
| AivisSpeech（エンジン） | ナレーション | `<root>\AivisSpeech` |
| 声モデル（fumifumi / 阿井田 茂 / Lux） | 追加の声 | AivisSpeech のデータフォルダ |
| このスキル | Codex に登録 | `%USERPROFILE%\.agents\skills\manim-video-win` |

`<root>` は `%LOCALAPPDATA%\manim-video`。ユーザー名に日本語が含まれるときは `C:\Users\Public\manim-video`（LaTeX が日本語のパスで失敗するため）。実際の場所はスキルフォルダの `tools.json` に書かれる。

## オプション

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipVoices   # 追加の声を入れない（まおだけ）
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipAivis    # AivisSpeech を入れない（--engine sapi を使う）
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipLatex    # 数式を使わない
powershell -ExecutionPolicy Bypass -File setup.ps1 -Root D:\mv   # ツールの場所を変える（英数字のみ）
```

## 確認

```powershell
& "$env:USERPROFILE\.agents\skills\manim-video-win\scripts\build.cmd" doctor
```

## 更新・削除

- 更新: 新しい ZIP を取ってきて `setup.bat` をもう一度実行する（スキルは上書きされる）。Manim の更新は `uv tool upgrade manim`。
- 削除: `<root>` フォルダと `%USERPROFILE%\.agents\skills\manim-video-win` を消し、`uv tool uninstall manim`。AivisSpeech の声のデータは `%LOCALAPPDATA%` か `%APPDATA%` の下の `AivisSpeech-Engine` フォルダにある。

## macOS で使う場合

build.py は macOS でも動く（Homebrew の ffmpeg、`uv tool install --python 3.12 manim`、TinyTeX、`~/Applications/AivisSpeech.app`）。`build.cmd` の代わりに `python3 scripts/build.py` を使う。
