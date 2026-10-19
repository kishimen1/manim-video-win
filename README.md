# manim-video-win

Codex に頼むだけで、3Blue1Brown 風の解説動画（ナレーション・字幕付きの mp4）を作れるスキルです。Windows 10/11 向け。

> 例:「3b1b風の動画で、三平方の定理を中学生向けに解説して」

プログラミングの知識や Python のインストールは不要です。下のセットアップを 1 回だけ行えば、あとは Codex にお願いするだけです。

## 必要なもの

- Windows 10 / 11（64 ビット）
- 空き容量 約 4 GB、メモリ 8 GB 以上推奨
- Codex（デスクトップアプリまたは CLI）が使えること
- インターネット接続（セットアップ時に約 2 GB をダウンロードします）
- 管理者権限は**不要**です

## セットアップ（初回だけ、20〜40 分）

1. このページの緑の **「Code」→「Download ZIP」** で ZIP をダウンロードします。
2. ダウンロードした ZIP を右クリック →「プロパティ」→ 下の「許可する」にチェック →「OK」。
3. ZIP を右クリック →「すべて展開」。
4. 展開したフォルダの中の **`setup.bat`** をダブルクリックします。
   - 「Windows によって PC が保護されました」と出たら、「詳細情報」→「実行」を押します。
   - 黒い画面に進み具合が表示されます。終わるまで閉じずに待ってください。
5. 最後に「セットアップが終わりました。」と出れば完了です。キーを押して画面を閉じます。
6. Codex を起動し直します（開いていた場合）。

途中で失敗した場合は、もう一度 `setup.bat` を実行してください。入ったものは飛ばして続きから行います。

## 使い方

Codex に次のように頼みます。

- 「3b1b風の動画で〇〇を解説して」
- 「Manim で〇〇のアニメーションを作って」

Codex が最初に**声**と**話し方**を聞いてきます。番号で答えてください。そのあと台本・プレビュー画像を見せてくれるので、直したいところを伝えます。最後に `final.mp4`（動画）と `final.srt`（字幕）ができます。

動画は `C:\Users\<あなたの名前>\manim-videos\` の中に作られます（ユーザー名に日本語が含まれる場合は `C:\Users\Public\manim-videos\`）。

## 入るもの

| もの | 用途 | ライセンス |
|---|---|---|
| [Manim Community](https://www.manim.community/) | アニメーションの描画 | MIT |
| [uv](https://docs.astral.sh/uv/) / Python 3.12 | Manim を動かす | Apache-2.0 / MIT, PSF |
| [FFmpeg](https://ffmpeg.org/)（[BtbN ビルド](https://github.com/BtbN/FFmpeg-Builds)） | 映像と音声の合成 | GPL |
| [TinyTeX](https://yihui.org/tinytex/) | 数式の表示 | GPL ほか TeX Live の各ライセンス |
| [AivisSpeech](https://aivis-project.com/) | ナレーションの音声合成 | LGPL-3.0 |
| 声のモデル（まお / fumifumi / 阿井田 茂 / Lux） | ナレーションの声 | 各モデルの規約（[AivisHub](https://hub.aivis-project.com/)） |

**作った動画を公開する前に**、使った声のモデルの利用規約（クレジット表記が必要かなど）を AivisHub のモデルページで確認してください。

詳しい場所や削除方法は [skill/manim-video-win/references/setup.md](skill/manim-video-win/references/setup.md)、困ったときは [troubleshooting.md](skill/manim-video-win/references/troubleshooting.md) を見てください。

## 社内で配布する前に（情報システム担当の方へ）

セットアップは次の通信と操作を行います。社内ポリシーで制限がある場合は事前に許可が必要です。

- 接続先: `github.com` / `objects.githubusercontent.com`（ffmpeg・TinyTeX・AivisSpeech）、`astral.sh`（uv）、`pypi.org` / `files.pythonhosted.org`（Manim）、`python-build-standalone` の GitHub Releases（Python）、`tlnet.yihui.org` ほか CTAN ミラー（LaTeX パッケージ）、`api.aivis-project.com`（声のモデル）
- PowerShell スクリプトを `-ExecutionPolicy Bypass` で実行します。
- すべてユーザー領域（`%USERPROFILE%`、`%LOCALAPPDATA%`、`%APPDATA%`、場合により `C:\Users\Public`）に入れます。レジストリはユーザーの PATH（uv の導入時）だけ変更します。
- 動画を作るとき、AivisSpeech エンジンが `127.0.0.1:10101` で待ち受けます（外部には公開しません）。

## 開発者向け

```
setup.bat                       ダブルクリック用の入口
skill/manim-video-win/          スキル本体（setup で %USERPROFILE%\.agents\skills にコピー）
  SKILL.md                      Codex への指示
  scripts/setup.ps1             ツールの一括導入
  scripts/build.cmd, build.py   描画・音声合成・合成（build.cmd は uv 経由で build.py を実行）
  scripts/doctor.py             環境診断（build.cmd doctor）
  assets/                       tbb_style.py（共通スタイル）、scene_template.py
examples/hello/                 動作確認用のサンプル
.github/workflows/windows.yml   windows-latest でセットアップからサンプルの書き出しまでを検証
```

取得するツールのバージョンは `setup.ps1` 冒頭の URL で決まります。更新するときはそこを変え、CI が通ることを確認してください。
