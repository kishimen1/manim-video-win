#!/usr/bin/env python3
"""Manim シーン + ナレーション台本から、音声付きの動画を組み立てる。

使い方（Windows では build.py の代わりに build.cmd を使う。Python が無くても uv が用意する）:
  python3 build.py doctor                          # 必要なツールがそろっているか調べる
  python3 build.py voices                          # AivisSpeech で使える声（話者/スタイル）を一覧表示
  python3 build.py install-voice <UUIDかURL>       # AivisHub の声を追加
  python3 build.py narration scene.py              # 台本 narration.md を書き出す（音声も合成して長さを計測）
  python3 build.py preview scene.py                # 低画質で描画し、台詞ごとのコマ一覧と配置の警告を画像にする
  python3 build.py render scene.py -q l            # 全シーンを描画し、音声付き final.mp4 を作る
  python3 build.py render scene.py -q h --scenes S02_Main
  python3 build.py render scene.py --voice まお/おちつき --speed 1.1
  python3 build.py render scene.py --engine sapi   # Windows 標準音声（Haruka など）を使う
  python3 build.py render scene.py --engine say    # macOS 標準音声（Kyoko）を使う
  python3 build.py render scene.py --no-audio      # 音声なし（映像の連結のみ）

仕組み:
  1. 台詞を文ごとに合成する（build/audio/cache/ に保存し、同じ文・同じ声なら使い回す）
  2. 台詞 → 秒数 を build/timings.json に書く。シーンの say() がこれを読んで映像の長さを合わせる
  3. シーンを並列に描画する（-j）。前回から変わっていないシーンは描画も合成もしない
  4. シーンが記録した台詞の開始時刻（build/scenes/*.json）どおりに音声を並べ、映像と合成する

必要なもの: manim (uv tool), ffmpeg, LaTeX (TinyTeX), AivisSpeech（または Windows/macOS 標準音声）
Windows では scripts/setup.ps1 がすべてユーザー領域に入れる（場所は tools.json に記録される）。
"""
import argparse
import ast
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import urllib.parse
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
SKILL = Path(__file__).resolve().parent.parent


def tools_root():
    """setup.ps1 がツールを入れたフォルダ。tools.json があればそれ、無ければ既定の場所。"""
    try:
        root = json.loads((SKILL / "tools.json").read_text(encoding="utf-8-sig"))["root"]
        if root:
            return Path(root)
    except (OSError, ValueError, KeyError):
        pass
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "manim-video"
    return Path.home() / "Library/Application Support/manim-video" if MAC else Path.home() / ".local/share/manim-video"


TOOLS = tools_root()
if WINDOWS:
    TINYTEX = TOOLS / "TinyTeX/bin/windows"
    LOG_DIR = TOOLS / "logs"
else:
    TINYTEX = Path.home() / "Library/TinyTeX/bin/universal-darwin"
    LOG_DIR = Path.home() / "Library/Logs" if MAC else TOOLS / "logs"
LEAD_IN = 0.3   # NARRATION 方式のシーンで、映像開始から読み上げ開始までの秒数
TAIL = 0.6      # シーン最後の読み上げ終了後に残す余白（秒）
RATE = 44100    # 音声トラックのサンプリング周波数
CACHE_VERSION = "2"  # クリップのキャッシュ形式を変えたら上げる
QUALITY_DIR = {"l": "480p15", "m": "720p30", "h": "1080p60", "p": "1440p60", "k": "2160p60"}

AIVIS_URL = os.environ.get("AIVIS_URL", "http://127.0.0.1:10101")
if WINDOWS:
    _local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    AIVIS_ENGINE = [
        TOOLS / "AivisSpeech/AivisSpeech-Engine/run.exe",
        _local / "Programs/AivisSpeech/AivisSpeech-Engine/run.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "AivisSpeech/AivisSpeech-Engine/run.exe",
    ]
else:
    AIVIS_ENGINE = [
        Path.home() / "Applications/AivisSpeech.app/Contents/Resources/AivisSpeech-Engine/run",
        Path("/Applications/AivisSpeech.app/Contents/Resources/AivisSpeech-Engine/run"),
    ]
DEFAULT_VOICE = {"aivis": "まお/おちつき", "say": "Kyoko", "sapi": ""}


def extra_paths():
    if WINDOWS:
        return [str(TOOLS / "ffmpeg/bin"), str(Path.home() / ".local/bin"), str(TINYTEX)]
    return [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", str(TINYTEX)]


def env(**extra_vars):
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join(extra_paths() + [e.get("PATH", "")])
    e["PYTHONUTF8"] = "1"  # manim のログを UTF-8 で書かせる（Windows の既定は cp932）
    e.update(extra_vars)
    return e


def tool(name):
    """コマンドの実体のパス。Windows の subprocess は env の PATH で探さないので、先に解決しておく。"""
    return shutil.which(name, path=env()["PATH"]) or name


def run(cmd, **kw):
    cmd = [tool(cmd[0])] + list(cmd[1:])
    r = subprocess.run(cmd, env=env(), **kw)
    if r.returncode != 0:
        sys.exit("コマンドが失敗しました: " + " ".join(map(str, cmd)))
    return r


def sha(*parts):
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


# ---- scene.py の読み取り ------------------------------------------------------

def spoken(text):
    """読み上げ用に整形（改行をつなぐ）。tbb_style.spoken と同じ規則。"""
    return re.sub(r"\s*\n\s*", "", text).strip()


def sentences(text):
    return [s for s in re.split(r"(?<=[。？！?!])", spoken(text)) if s.strip()]


class SceneInfo:
    def __init__(self, index, name, says, narration, source):
        self.index, self.name, self.says, self.narration, self.source = index, name, says, narration, source

    @property
    def texts(self):
        """読み上げる台詞（say() 方式なら台詞ごと、NARRATION 方式なら全体で 1 つ）。"""
        if self.says:
            return self.says
        return [spoken(self.narration)] if self.narration else []


def load_scenes(path):
    """scene.py を import せずに、Scene クラスと台詞を書かれた順に取り出す。

    台詞は self.say("...") の文字列（推奨）か、クラス変数 NARRATION。
    共通部分（クラス以外のコード）も返す。キャッシュの判定に使う。
    """
    src = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    scenes, shared = [], []
    for node in tree.body:
        bases = [getattr(b, "id", getattr(b, "attr", "")) for b in getattr(node, "bases", [])]
        if not (isinstance(node, ast.ClassDef) and any(b.endswith("Scene") for b in bases)):
            shared.append(ast.get_source_segment(src, node) or "")
            continue
        narration = ""
        for item in node.body:
            if (isinstance(item, ast.Assign) and any(getattr(t, "id", "") == "NARRATION" for t in item.targets)
                    and isinstance(item.value, ast.Constant)):
                narration = textwrap.dedent(item.value.value).strip()
        calls = []
        for n in ast.walk(node):
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "say" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                calls.append((n.lineno, n.col_offset, spoken(n.args[0].value)))
        says = [t for _, _, t in sorted(calls) if t]
        scenes.append(SceneInfo(len(scenes) + 1, node.name, says, narration,
                                ast.get_source_segment(src, node)))
    return scenes, "\n".join(shared)


def load_settings(path):
    """scene.py の先頭に書いた VOICE / SPEED を読む（コマンドの指定が優先）。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if getattr(t, "id", "") in ("VOICE", "SPEED"):
                    found[t.id] = node.value.value
    return found


def duration(media):
    out = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(media)],
        env=env(), capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


# ---- AivisSpeech -----------------------------------------------------------

# 社内プロキシの設定があっても、手元のエンジン（127.0.0.1）には直接つなぐ
_local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def aivis_get(path):
    with _local_http.open(AIVIS_URL + path, timeout=5) as r:
        return json.loads(r.read())


def aivis_post(path, params, body=None):
    url = AIVIS_URL + path + "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with _local_http.open(req, timeout=300) as r:
        return r.read()


def aivis_ensure():
    """エンジンが動いていなければ起動して、応答するまで待つ。"""
    try:
        aivis_get("/version")
        return
    except Exception:
        pass
    exe = aivis_exe()
    if exe is None:
        sys.exit("AivisSpeech が見つかりません。セットアップ（references/setup.md）をやり直してください。"
                 "\n音声なしで試すなら --engine sapi（Windows 標準音声）が使えます")
    print("AivisSpeech エンジンを起動しています（初回は 1〜2 分かかります）...")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / "aivisspeech-engine.log", "ab")
    if WINDOWS:
        detach = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        detach = {"start_new_session": True}
    subprocess.Popen([str(exe), "--port", AIVIS_URL.rsplit(":", 1)[-1]],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, **detach)
    for _ in range(120):
        time.sleep(2)
        try:
            aivis_get("/version")
            return
        except Exception:
            pass
    sys.exit("AivisSpeech エンジンが起動しませんでした（ログ: %s）" % (LOG_DIR / "aivisspeech-engine.log"))


def aivis_exe():
    return next((p for p in AIVIS_ENGINE if p.exists()), None)


def aivis_styles():
    """[(話者名, スタイル名, style_id)] を返す。"""
    aivis_ensure()
    return [(sp["name"], st["name"], st["id"]) for sp in aivis_get("/speakers") for st in sp["styles"]]


_style_ids = {}


def aivis_style_id(voice):
    """'まお/おちつき'、'まお'（最初のスタイル）、または数値の style_id を受け付ける。"""
    if str(voice).isdigit():
        return int(voice)
    if voice not in _style_ids:
        name, _, style = voice.partition("/")
        for sp, st, sid in aivis_styles():
            if sp == name and (not style or st == style):
                _style_ids[voice] = sid
                break
        else:
            sys.exit("声 '%s' が見つかりません。`build.py voices` で一覧を確認してください" % voice)
    return _style_ids[voice]


# ---- 音声合成（文ごと・キャッシュ付き） -------------------------------------------

_synth_lock = threading.Lock()


def sentence_wav(sentence, cache, a):
    """1 文を合成した wav（44.1kHz・モノラル・16bit）を返す。同じ文・同じ声なら使い回す。"""
    key = sha(a.engine, str(a.voice), a.speed if a.engine == "aivis" else a.rate, sentence)
    out = cache / (key + ".wav")
    if out.exists():
        return out
    with _synth_lock:  # エンジンへの同時リクエストを避ける
        if out.exists():
            return out
        tmp = out.with_suffix(".tmp.wav")
        if a.engine == "aivis":
            sid = aivis_style_id(a.voice)
            query = json.loads(aivis_post("/audio_query", {"text": sentence, "speaker": sid}))
            if a.speed:
                query["speedScale"] = a.speed
            raw = out.with_suffix(".raw.wav")
            raw.write_bytes(aivis_post("/synthesis", {"speaker": sid}, query))
        elif a.engine == "sapi":
            raw = out.with_suffix(".raw.wav")
            sapi_say(sentence, a.voice, a.rate, raw)
        else:
            raw = out.with_suffix(".raw.aiff")
            cmd = ["say", "-v", a.voice, "-o", str(raw), sentence]
            if a.rate:
                cmd[1:1] = ["-r", str(a.rate)]
            run(cmd)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
             "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le", str(tmp)])
        raw.unlink()
        tmp.rename(out)
    return out


SAPI_SCRIPT = r'''
param([string]$TextFile, [string]$Out, [string]$Voice, [int]$Rate)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo }
if ($Voice) { $s.SelectVoice($Voice) }
else {
  $ja = $voices | Where-Object { $_.Culture.Name -eq 'ja-JP' } | Select-Object -First 1
  if ($ja) { $s.SelectVoice($ja.Name) }
}
$s.Rate = $Rate
$s.SetOutputToWaveFile($Out)
$s.Speak([IO.File]::ReadAllText($TextFile, [Text.Encoding]::UTF8))
$s.Dispose()
'''


def sapi_say(sentence, voice, rate, out):
    """Windows 標準の音声合成（SAPI）で 1 文を wav にする。voice が空なら日本語の声を自動で選ぶ。"""
    if not WINDOWS:
        sys.exit("--engine sapi は Windows 専用です（macOS は --engine say）")
    script = out.with_suffix(".ps1")
    text = out.with_suffix(".txt")
    script.write_text(SAPI_SCRIPT, encoding="utf-8-sig")
    text.write_text(sentence, encoding="utf-8")
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-TextFile", str(text), "-Out", str(out), "-Voice", voice or "", "-Rate", str(max(-10, min(10, rate or 0)))])
    script.unlink()
    text.unlink()


def sapi_voices():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer)"
                        ".GetInstalledVoices() | % { $_.VoiceInfo.Name + [char]9 + $_.VoiceInfo.Culture.Name }"],
                       capture_output=True, text=True, errors="replace")
    return [line.split("\t") for line in r.stdout.splitlines() if "\t" in line]


def wav_seconds(p):
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / w.getframerate()


def synthesize(scenes, work, a):
    """全台詞を文ごとに合成し、{台詞: [(文, wav, 秒数)]} を返す。timings.json も更新する。"""
    cache = work / "audio" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    texts = [t for sc in scenes for t in sc.texts]
    todo = sum(1 for t in texts for s in sentences(t)
               if not (cache / (sha(a.engine, str(a.voice), a.speed if a.engine == "aivis" else a.rate, s)
                                + ".wav")).exists())
    if todo and a.engine == "aivis":
        aivis_ensure()
    if todo:
        print("音声を合成しています（新しい文: %d）..." % todo)
    result = {}
    for t in texts:
        parts = []
        for s in sentences(t):
            p = sentence_wav(s, cache, a)
            parts.append((s, p, wav_seconds(p)))
        result[t] = parts
    tfile = work / "timings.json"
    try:
        timings = json.loads(tfile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        timings = {}
    timings.update({t: round(sum(d for _, _, d in parts), 4) for t, parts in result.items()})
    tfile.write_text(json.dumps(timings, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


# ---- シーンの描画と合成 ------------------------------------------------------

def fmt_srt(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def render_scene(scene_py, name, quality, work):
    """manim で 1 シーンを描画する。失敗したら 1 回だけやり直す（並列描画中のキャッシュ競合対策）。"""
    log = work / "logs" / ("%s.log" % name)
    # manim の部分キャッシュを使うと内部時刻が実際のフレーム数とずれ、音声の位置がずれる。
    # 変わっていないシーンは build_clips が丸ごと飛ばすので、manim 側のキャッシュは切る。
    cmd = [tool("manim"), "-q" + quality, "--disable_caching", str(scene_py), name]
    for attempt in range(2):
        with open(log, "w", encoding="utf-8") as f:
            r = subprocess.run(cmd, cwd=scene_py.parent, stdout=f, stderr=subprocess.STDOUT,
                               env=env(MANIM_VIDEO_BUILD=str(work)))
        if r.returncode == 0:
            break
    else:
        tail = "".join(log.read_text(encoding="utf-8", errors="replace").splitlines(True)[-25:])
        raise RuntimeError("%s の描画に失敗しました（ログ: %s）\n%s" % (name, log, tail))
    video = scene_py.parent / "media/videos" / scene_py.stem / QUALITY_DIR[quality] / ("%s.mp4" % name)
    if not video.exists():
        raise RuntimeError("描画結果が見つかりません: %s" % video)
    return video


def scene_record(work, sc):
    try:
        return json.loads((work / "scenes" / ("%s.json" % sc.name)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"cues": [], "warnings": []}


def placements(sc, rec, voice):
    """[(開始秒, 文, wav, 秒数)]。say() 方式はシーンが記録した開始時刻、NARRATION 方式は冒頭から。"""
    cues = rec.get("cues") or []
    if not cues and sc.narration:
        cues = [{"text": spoken(sc.narration), "start": LEAD_IN}]
    out = []
    for cue in cues:
        parts = voice.get(cue["text"])
        if parts is None:
            print("  注意: %s の台詞が台本から読み取れず、音声がありません: %s" % (sc.name, cue["text"][:30]))
            continue
        t = cue["start"]
        for s, p, d in parts:
            out.append((t, s, p, d))
            t += d
    return out


def mux(video, placed, work, name, out):
    """文ごとの音声を開始時刻どおりに並べたトラックを作り、映像と合成する。"""
    v = duration(video)
    end = max([v] + [t + d + TAIL for t, _, _, d in placed])
    buf = bytearray(int(math.ceil(end * RATE)) * 2)
    for t, _, p, _ in placed:
        with wave.open(str(p), "rb") as w:
            data = w.readframes(w.getnframes())
        off = int(round(t * RATE)) * 2
        data = data[:max(0, len(buf) - off)]
        buf[off:off + len(data)] = data
    track = work / "audio" / ("%s.wav" % name)
    with wave.open(str(track), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(track),
         "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=%.3f[v]" % (end - v),
         "-map", "[v]", "-map", "1:a", "-t", "%.3f" % end,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         str(out)])


def build_clips(a):
    """選んだシーンを描画・合成し、[(SceneInfo, clip, 記録, 配置)] を返す。変わっていないシーンは飛ばす。"""
    scene_py = Path(a.scene).resolve()
    work = scene_py.parent / "build"
    clips_dir = work / "clips" / QUALITY_DIR[a.quality]
    for d in (clips_dir, work / "logs", work / "scenes", work / "audio"):
        d.mkdir(parents=True, exist_ok=True)
    style = scene_py.parent / "tbb_style.py"
    if not style.exists():
        sys.exit("tbb_style.py がありません。%s をコピーしてください" % (SKILL / "assets/tbb_style.py"))
    scenes, shared = load_scenes(scene_py)
    if a.scenes:
        want = a.scenes.split(",")
        missing = set(want) - {s.name for s in scenes}
        if missing:
            sys.exit("シーンが見つかりません: " + ", ".join(sorted(missing)))
        scenes = [s for s in scenes if s.name in want]
    if not scenes:
        sys.exit("Scene クラスが見つかりません")

    voice = {} if a.no_audio else synthesize(scenes, work, a)
    style_src = style.read_text(encoding="utf-8")

    def job(sc):
        clip = clips_dir / ("%02d_%s.mp4" % (sc.index, sc.name))
        stamp = clip.with_suffix(".hash")
        key = sha(CACHE_VERSION, sc.source, shared, style_src, a.quality, a.no_audio,
                  [[(s, str(p.name)) for s, p, _ in voice.get(t, [])] for t in sc.texts])
        rec_file = work / "scenes" / ("%s.json" % sc.name)
        cached = (not a.force and clip.exists() and rec_file.exists()
                  and stamp.exists() and stamp.read_text() == key)
        if not cached:
            t0 = time.time()
            video = render_scene(scene_py, sc.name, a.quality, work)
            rec = scene_record(work, sc)
            mux(video, placements(sc, rec, voice), work, sc.name, clip)
            stamp.write_text(key)
            print("  %s: 描画しました（%.0f 秒）" % (sc.name, time.time() - t0))
        else:
            print("  %s: 変更なし（前回のものを使います）" % sc.name)
        rec = scene_record(work, sc)
        return sc, clip, rec, placements(sc, rec, voice)

    print("シーンを描画しています（%d シーン、並列 %d）..." % (len(scenes), a.jobs))
    errors, results = [], []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futures = [ex.submit(job, sc) for sc in scenes]
        for f in futures:
            try:
                results.append(f.result())
            except RuntimeError as e:
                errors.append(str(e))
    if errors:
        sys.exit("\n\n".join(errors))

    warns = [(sc.name, w) for sc, _, rec, _ in results for w in rec.get("warnings", [])]
    if warns:
        print("\nレイアウトの警告（%d 件）:" % len(warns))
        for name, w in warns:
            print("  %s %5.1fs  %s" % (name, w["time"], w["message"]))
    return results


# ---- プレビュー（コマ一覧） ----------------------------------------------------

SHEET_SCRIPT = r'''
import json, sys, glob
from PIL import Image, ImageDraw, ImageFont
spec = json.load(open(sys.argv[1], encoding="utf-8"))
def font(w, size):
    win = "C:/Windows/Fonts/"
    paths = (sorted(glob.glob("/System/Library/Fonts/*W%d.ttc" % w)) + ["/System/Library/Fonts/Hiragino Sans GB.ttc"]
             + [win + f for f in (["YuGothB.ttc", "meiryob.ttc"] if w >= 6 else ["YuGothM.ttc", "meiryo.ttc"])]
             + [win + "msgothic.ttc"])
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()
F, FB = font(3, 19), font(6, 26)
W, H, LH, PAD, COLS = 640, 360, 58, 12, 3
def wrap(s, n=33, lines=2):
    out = [s[i:i + n] for i in range(0, len(s), n)] or [""]
    return out[:lines - 1] + [out[lines - 1][:n - 1] + "…"] if len(out) > lines else out
for sh in spec["sheets"]:
    frames, warns = sh["frames"], sh["warnings"]
    rows = (len(frames) + COLS - 1) // COLS
    width = COLS * W + (COLS + 1) * PAD
    height = 56 + rows * (H + LH + PAD) + PAD + (len(warns) * 26 + 20 if warns else 0)
    img = Image.new("RGB", (width, height), (24, 26, 32))
    d = ImageDraw.Draw(img)
    d.text((PAD, 14), sh["title"], font=FB, fill=(235, 235, 235))
    for i, fr in enumerate(frames):
        x = PAD + (i % COLS) * (W + PAD)
        y = 56 + (i // COLS) * (H + LH + PAD)
        img.paste(Image.open(fr["png"]).convert("RGB").resize((W, H)), (x, y))
        if fr["warn"]:
            d.rectangle([x - 3, y - 3, x + W + 2, y + H + 2], outline=(230, 70, 70), width=3)
        label = "%d) %.1fs  %s" % (i + 1, fr["time"], fr["label"])
        for k, line in enumerate(wrap(label)):
            d.text((x, y + H + 6 + k * 25), line, font=F, fill=(200, 200, 200))
    y = 56 + rows * (H + LH + PAD) + 10
    for w in warns:
        d.text((PAD, y), "⚠ %.1fs  %s" % (w["time"], w["message"]), font=F, fill=(240, 110, 110))
        y += 26
    img.save(sh["out"])
'''


def manim_python():
    """Pillow が入っている Python（manim を入れた uv tool の環境）。"""
    uv = shutil.which("uv", path=env()["PATH"])
    if uv:
        r = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, errors="replace")
        venv = Path(r.stdout.strip()) / "manim"
        for py in (venv / "Scripts/python.exe", venv / "bin/python"):
            if r.returncode == 0 and py.exists():
                return str(py)
    exe = shutil.which("manim", path=env()["PATH"])
    if exe and not WINDOWS:
        first = Path(exe).read_text(errors="replace").split("\n", 1)[0]
        if first.startswith("#!"):
            return first[2:].strip()
    return sys.executable


def cmd_preview(a):
    results = build_clips(a)
    scene_py = Path(a.scene).resolve()
    out_dir = scene_py.parent / "build" / "preview"
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    for sc, clip, rec, _ in results:
        length = duration(clip)
        cues = rec.get("cues") or []
        if cues:
            # 各台詞の終わり（次の台詞の直前）のコマ = その台詞で見せたい状態
            ends = [c["start"] for c in cues[1:]] + [length]
            shots = [(max(0.0, e - 0.15), c["text"]) for c, e in zip(cues, ends)]
        else:
            n = 6
            shots = [(length * (k + 1) / n - 0.15, "") for k in range(n)]
        warn_cues = {w.get("cue") for w in rec.get("warnings", [])}
        frames = []
        for k, (t, label) in enumerate(shots, 1):
            png = frames_dir / ("%s_%02d.png" % (sc.name, k))
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % t, "-i", str(clip),
                 "-frames:v", "1", "-vf", "scale=640:-2", str(png)])
            frames.append({"png": str(png), "time": t, "label": label,
                           "warn": bool(label) and label in warn_cues})
        sheets.append({"title": "%s（%.1f 秒）" % (sc.name, length), "frames": frames,
                       "warnings": rec.get("warnings", []),
                       "out": str(out_dir / ("%02d_%s.png" % (sc.index, sc.name)))})
    spec = out_dir / "sheets.json"
    spec.write_text(json.dumps({"sheets": sheets}, ensure_ascii=False), encoding="utf-8")
    script = out_dir / "make_sheets.py"
    script.write_text(SHEET_SCRIPT, encoding="utf-8")
    run([manim_python(), str(script), str(spec)])
    print("\nコマ一覧:")
    for sh in sheets:
        print("  " + sh["out"])


# ---- サブコマンド -----------------------------------------------------------

def cmd_voices(a):
    for sp, st, sid in aivis_styles():
        print("%s/%s\t%d" % (sp, st, sid))
    if WINDOWS:
        print("\n# Windows 標準音声（--engine sapi --voice <名前>）")
        for name, culture in sapi_voices():
            print("%s\t%s" % (name, culture))


def cmd_install_voice(a):
    """AivisHub のモデルをエンジンに追加する（UUID かモデルページの URL を受け付ける）。"""
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", a.model)
    if not m:
        sys.exit("AivisHub のモデル UUID が見つかりません: " + a.model)
    aivis_ensure()
    if m.group(0) in aivis_get("/aivm_models"):
        print("すでに入っています:", m.group(0))
        return
    url = "https://api.aivis-project.com/v1/aivm-models/%s/download?model_type=AIVMX" % m.group(0)
    boundary = "----manimvideo"
    body = ("--%s\r\nContent-Disposition: form-data; name=\"url\"\r\n\r\n%s\r\n--%s--\r\n"
            % (boundary, url, boundary)).encode()
    req = urllib.request.Request(AIVIS_URL + "/aivm_models/install", data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    _local_http.open(req, timeout=600)
    print("追加しました。`build.py voices` で確認できます")


def cmd_narration(a):
    scene_py = Path(a.scene).resolve()
    work = scene_py.parent / "build"
    scenes, _ = load_scenes(scene_py)
    voice = {} if a.no_audio else synthesize(scenes, work, a)
    lines = ["# ナレーション台本: %s" % scene_py.stem, ""]
    total = 0.0
    for sc in scenes:
        secs = [sum(d for _, _, d in voice[t]) if t in voice else len(t) / 7.0 for t in sc.texts]
        sec = sum(secs)
        total += sec
        lines += ["## %d. %s（約 %.1f 秒）" % (sc.index, sc.name, sec), ""]
        if not sc.texts:
            lines += ["（ナレーションなし）", ""]
        elif sc.says:
            lines += ["- %s（%.1f 秒）" % (t, s) for t, s in zip(sc.texts, secs)] + [""]
        else:
            lines += [sc.narration, ""]
    lines.insert(2, "合計: 約 %d 分 %d 秒（音声のみ。映像が長い箇所はその分のびる） / 音声: %s（%s）\n"
                 % (total // 60, total % 60, a.voice, a.engine))
    out = scene_py.parent / "narration.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("台本を書き出しました:", out)


def cmd_render(a):
    results = build_clips(a)
    scene_py = Path(a.scene).resolve()
    work = scene_py.parent / "build"
    srt, t = [], 0.0
    for sc, clip, rec, placed in results:
        for start, s, _, d in placed:
            srt.append((t + start, t + start + d, s))
        t += duration(clip)
    lst = work / "clips.txt"
    # ffmpeg の concat はバックスラッシュを解釈するので、/ 区切りにして ' をエスケープする
    lst.write_text("".join("file '%s'\n" % c.as_posix().replace("'", "'\\''") for _, c, _, _ in results),
                   encoding="utf-8")
    out = scene_py.parent / (a.output or "final.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    if srt:
        out.with_suffix(".srt").write_text(
            "".join("%d\n%s --> %s\n%s\n\n" % (k, fmt_srt(s), fmt_srt(e), txt) for k, (s, e, txt) in enumerate(srt, 1)),
            encoding="utf-8")
    print("完成: %s（%.1f 秒）" % (out, t))


def main():
    # 出力先が cp932 でも、表せない文字で止まらないようにする
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("voices")
    sub.add_parser("doctor").add_argument("--quick", action="store_true", help="試し描画を省く")
    sub.add_parser("install-voice").add_argument("model", help="AivisHub のモデル UUID またはページ URL")
    for name in ("narration", "render", "preview"):
        s = sub.add_parser(name)
        s.add_argument("scene", help="scene.py のパス")
        s.add_argument("--engine", default="aivis", choices=["aivis", "sapi", "say"],
                       help="音声合成（既定: aivis）。sapi=Windows 標準、say=macOS 標準")
        s.add_argument("--voice", help="aivis: '話者/スタイル' か style_id（既定: まお/おちつき）／sapi・say: 声の名前")
        s.add_argument("--speed", type=float, default=0, help="aivis の話速（1.0 が標準）")
        s.add_argument("--rate", type=int, default=0, help="say の読み上げ速度（語/分）／sapi の速さ（-10〜10）")
        s.add_argument("--no-audio", action="store_true")
        if name != "narration":
            s.add_argument("-q", "--quality", default="l", choices=list("lmhpk"),
                           help="l=480p15 m=720p30 h=1080p60 k=4K")
            s.add_argument("--scenes", help="描画するシーン名（カンマ区切り）")
            s.add_argument("-j", "--jobs", type=int, default=min(4, max(1, (os.cpu_count() or 2) // 2)),
                           help="同時に描画するシーン数")
            s.add_argument("--force", action="store_true", help="変更がなくても描画し直す")
    sub.choices["render"].add_argument("-o", "--output", help="出力ファイル名（既定: final.mp4）")
    a = p.parse_args()
    if a.cmd == "voices":
        return cmd_voices(a)
    if a.cmd == "install-voice":
        return cmd_install_voice(a)
    if a.cmd == "doctor":
        from doctor import doctor
        return doctor(a)
    if a.engine == "aivis":
        s = load_settings(a.scene)
        a.voice = a.voice or s.get("VOICE")
        a.speed = a.speed or s.get("SPEED", 0)
    a.voice = a.voice or DEFAULT_VOICE[a.engine]
    if not shutil.which("manim", path=env()["PATH"]):
        sys.exit("manim が見つかりません。セットアップ（references/setup.md）をやり直すか、"
                 "`uv tool install --python 3.12 manim` を実行してください")
    {"narration": cmd_narration, "render": cmd_render, "preview": cmd_preview}[a.cmd](a)


if __name__ == "__main__":
    main()
