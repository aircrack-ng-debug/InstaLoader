import os
import glob
import uuid
import subprocess
import tempfile
import logging
import base64
from functools import wraps
from flask import Flask, request, jsonify, send_file

# --- Configuration (ENV) ---
PORT = int(os.environ.get("PORT", 8080))
API_KEY = os.environ.get("API_KEY")
COOKIES_PATH = os.environ.get("COOKIES_PATH", "/tmp/cookies.txt")
COOKIES_B64 = os.environ.get("COOKIES_B64")

# Bevorzuge kombinierten Download: best video + best audio; kein Audio-only Fallback hier.
YTDLP_FORMAT = os.environ.get("YTDLP_FORMAT", "bv*+ba")
# Sortierung: erst Auflösung, dann MP4/M4A bevorzugen (gut für Remux/Merge zu MP4)
YTDLP_SORT = os.environ.get("YTDLP_SORT", "res,ext:mp4:m4a")
# Merge-Zielcontainer
YTDLP_MERGE = os.environ.get("YTDLP_MERGE_FORMAT", "mp4")
# Kontrollierter Fallback, falls der Primärversuch scheitert (z. B. "b" = best available)
YTDLP_FALLBACK_FORMAT = os.environ.get("YTDLP_FALLBACK_FORMAT", "b")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# --- Startup Logic: Cookie-Datei erstellen ---
def setup_cookies_from_env():
    """
    Prüft, ob COOKIES_B64 existiert, dekodiert es
    und schreibt den Inhalt in die COOKIES_PATH-Datei.
    """
    if COOKIES_B64:
        try:
            logger.info(f"Found COOKIES_B64 env var, decoding to {COOKIES_PATH}")
            decoded_cookies = base64.b64decode(COOKIES_B64)
            with open(COOKIES_PATH, "w") as f:
                f.write(decoded_cookies.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to decode and write cookies: {e}")


setup_cookies_from_env()

# --- Flask App Initialization ---
app = Flask(__name__)


# --- Helpers ---
def require_api_key(f):
    """
    Optionaler API-Key-Schutz.
    Erwartet 'Authorization: Bearer <API_KEY>' wenn API_KEY gesetzt ist.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"error": "Authorization header is missing or invalid"}), 401
            provided_key = auth_header.split("Bearer ", 1)[1]
            if provided_key != API_KEY:
                return jsonify({"error": "Invalid API key"}), 403
        return f(*args, **kwargs)

    return decorated


def is_instagram_url(u: str) -> bool:
    try:
        return ("instagram.com" in u) and ("/reel/" in u or "/p/" in u)
    except Exception:
        return False


def build_ytdlp_cmd(url: str, fmt: str, out_template: str) -> list[str]:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", fmt,
        "-S", YTDLP_SORT,
        "--merge-output-format", YTDLP_MERGE,
        "--force-overwrites",
        "--no-warnings",
        "-R", "5",
        "--fragment-retries", "5",
        "-o", out_template,
        url,
    ]
    if COOKIES_PATH and os.path.exists(COOKIES_PATH):
        cmd.extend(["--cookies", COOKIES_PATH])
        logger.info(f"Using cookies from {COOKIES_PATH}")
    elif COOKIES_PATH:
        logger.warning(f"Cookies file specified but not found at {COOKIES_PATH}")
    return cmd


def pick_output_file(tmpdir: str) -> str:
    """
    Wähle die beste erzeugte Datei:
    1) bevorzugt .mp4 (gemerged)
    2) sonst größtes gängiges Media-File (m4a/webm/mkv/mp3)
    """
    mp4s = sorted(glob.glob(os.path.join(tmpdir, "*.mp4")), key=lambda p: os.path.getsize(p), reverse=True)
    if mp4s:
        return mp4s[0]
    candidates: list[str] = []
    for pattern in ("*.m4a", "*.webm", "*.mkv", "*.mp3"):
        candidates += glob.glob(os.path.join(tmpdir, pattern))
    if candidates:
        candidates.sort(key=lambda p: os.path.getsize(p), reverse=True)
        return candidates[0]
    return ""


def guess_mimetype(path: str) -> tuple[str, str]:
    """
    Gib (mimetype, download_name) zurück – setze einen stabilen Dateinamen.
    """
    base = f"ig_reel_{uuid.uuid4().hex}"
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp4":
        return "video/mp4", f"{base}.mp4"
    if ext == ".m4a":
        return "audio/mp4", f"{base}.m4a"
    if ext == ".webm":
        return "video/webm", f"{base}.webm"
    if ext == ".mkv":
        return "video/x-matroska", f"{base}.mkv"
    if ext == ".mp3":
        return "audio/mpeg", f"{base}.mp3"
    return "application/octet-stream", os.path.basename(path)


# --- Endpoints ---
@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200


@app.route("/download", methods=["GET"])
@require_api_key
def download_reel():
    """
    Query Param: url=<instagram reel/post url>
    Lädt das Video (und Audio) herunter und liefert es gemerged als MP4 zurück.
    """
    video_url = request.args.get("url", "").strip()
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400
    if not is_instagram_url(video_url):
        return jsonify({"error": "Only instagram reel/post URLs are supported"}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
        process = None

        try:
            # 1) Primär: Erzwinge Video+Audio
            primary_cmd = build_ytdlp_cmd(video_url, YTDLP_FORMAT, output_template)
            logger.info(f"Executing command (primary): {' '.join(primary_cmd)}")
            process = subprocess.run(
                primary_cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 min
            )
        except subprocess.CalledProcessError as e:
            # 2) Fallback: best available (kann Audio-only sein)
            if YTDLP_FALLBACK_FORMAT:
                logger.warning(f"Primary format failed, retrying with fallback '{YTDLP_FALLBACK_FORMAT}'")
                fb_cmd = build_ytdlp_cmd(video_url, YTDLP_FALLBACK_FORMAT, output_template)
                logger.info(f"Executing command (fallback): {' '.join(fb_cmd)}")
                try:
                    process = subprocess.run(
                        fb_cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=300,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as fb_e:
                    logger.error("yt-dlp fallback also failed.")
                    return jsonify({
                        "error": "Failed to download video after fallback.",
                        "url": video_url,
                        "stdout": fb_e.stdout if hasattr(fb_e, "stdout") else "",
                        "stderr": fb_e.stderr if hasattr(fb_e, "stderr") else ""
                    }), 500
            else:
                logger.error("yt-dlp failed (no fallback configured).")
                return jsonify({
                    "error": "Failed to download video.",
                    "url": video_url,
                    "stdout": e.stdout,
                    "stderr": e.stderr
                }), 500
        except subprocess.TimeoutExpired as e:
            logger.error(f"yt-dlp timed out for URL: {video_url}")
            return jsonify({
                "error": "Download process timed out.",
                "url": video_url,
                "stdout": e.stdout if hasattr(e, "stdout") else "",
                "stderr": e.stderr if hasattr(e, "stderr") else ""
            }), 504
        except Exception as e:
            logger.exception("Unexpected error while running yt-dlp.")
            return jsonify({"error": "An unexpected server error occurred."}), 500

        # Ausgabedatei auswählen
        video_path = pick_output_file(temp_dir)
        if not video_path:
            logger.error("yt-dlp ran successfully but no file was produced.")
            return jsonify({
                "error": "yt-dlp did not produce a media file.",
                "stdout": process.stdout if process else "",
                "stderr": process.stderr if process else ""
            }), 500

        mimetype, download_name = guess_mimetype(video_path)

        # Datei senden
        return send_file(
            video_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype,
        )


if __name__ == "__main__":
    # Nur für lokalen Test – in Production via Gunicorn starten.
    app.run(host="0.0.0.0", port=PORT, debug=True)