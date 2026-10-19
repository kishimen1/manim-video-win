"""build.py doctor: 動画づくりに必要なツールがそろっているかを調べ、直し方を表示する。"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import build as b

FIX_SETUP = "セットアップ.bat をもう一度ダブルクリックしてください" if b.WINDOWS else "references/setup.md の手順で入れ直してください"

TEST_SCENE = '''
from tbb_style import *

class DoctorTest(Scene):
    def construct(self):
        self.add(jtext("日本語の表示テスト"), MathTex(r"e^{i\\pi}+1=0").shift(DOWN))
'''


def is_ascii(p):
    return all(ord(c) < 128 for c in str(p))


def doctor(a):
    results = []

    def check(name, ok, detail="", fix="", required=True):
        if required:
            results.append(ok)
        mark = "OK" if ok else ("NG" if required else "--")
        print("[%s] %s%s" % (mark, name, ("  " + detail) if detail else ""))
        if not ok and fix:
            print("     → " + fix)

    def version(cmd, *args):
        exe = shutil.which(cmd, path=b.env()["PATH"])
        if not exe:
            return None
        r = subprocess.run([exe, *args], env=b.env(), capture_output=True, text=True, errors="replace")
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None

    print("ツールの場所: %s\n" % b.TOOLS)
    v = version("uv", "--version")
    check("uv", bool(v), v or "", FIX_SETUP)
    v = version("manim", "--version")
    check("Manim", bool(v), v or "", FIX_SETUP)
    for name in ("ffmpeg", "ffprobe"):
        v = version(name, "-version")
        check(name, bool(v), (v or "")[:40], FIX_SETUP)
    for name in ("latex", "dvisvgm"):
        v = version(name, "--version")
        check(name + "（数式用）", bool(v), (v or "")[:40], FIX_SETUP)

    exe = b.aivis_exe()
    check("AivisSpeech（音声）", exe is not None, str(exe or ""), FIX_SETUP)
    if exe:
        try:
            styles = b.aivis_styles()
            speakers = sorted({sp for sp, _, _ in styles})
            check("AivisSpeech の声", bool(styles), "、".join(speakers),
                  "初回はエンジンが声を取得するまで時間がかかります。数分後にもう一度試してください")
        except SystemExit as e:
            check("AivisSpeech の起動", False, str(e),
                  "Codex から実行していて失敗する場合は、127.0.0.1:10101 への接続を許可してください")
    if b.WINDOWS:
        voices = b.sapi_voices()
        ja = [n for n, c in voices if c == "ja-JP"]
        check("Windows 標準音声（予備）", bool(ja), "、".join(ja) or "日本語の声なし",
              "設定 → 時刻と言語 → 音声 で日本語の音声を追加できます（無くても AivisSpeech があれば動きます）",
              required=False)

    if not is_ascii(b.TOOLS):
        check("ツールの場所が英数字のみ", False, str(b.TOOLS),
              "日本語を含む場所だと数式（LaTeX）が失敗します。" + FIX_SETUP)
    cwd = Path.cwd()
    check("作業フォルダが英数字のみ", is_ascii(cwd), str(cwd),
          "C:\\videos\\テーマ名 ではなく C:\\videos\\theme1 のような英数字だけのフォルダで作業してください")

    if not a.quick and shutil.which("manim", path=b.env()["PATH"]):
        base = None
        if b.WINDOWS and is_ascii(b.TOOLS):  # 一時フォルダがユーザー名（日本語のことがある）の下にならないように
            base = b.TOOLS / "tmp"
            base.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="manimdoctor", dir=base))
        shutil.copy(b.SKILL / "assets/tbb_style.py", work)
        (work / "doctor_test.py").write_text(TEST_SCENE, encoding="utf-8")
        r = subprocess.run([b.tool("manim"), "-ql", "--dry_run", "--disable_caching", "doctor_test.py", "DoctorTest"],
                           cwd=work, env=b.env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
        check("試し描画（日本語＋数式）", r.returncode == 0, "", "詳しい内容:\n" + tail)
        shutil.rmtree(work, ignore_errors=True)

    print()
    if all(results):
        print("すべてそろっています。動画を作れます。")
    else:
        print("NG の項目があります。→ の案内に沿って直してください。")
        sys.exit(1)
