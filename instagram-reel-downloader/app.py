import os
import subprocess
import tempfile
import logging
from functools import wraps
from flask import Flask, request, jsonify, send_file

# --- Configuration ---
PORT = os.environ.get("PORT", 8080)
API_KEY = os.environ.get("API_KEY")
COOKIES_PATH = os.environ.get("COOKIES_PATH")
YTDLP_FORMAT = os.environ.get("YTDLP_FORMAT", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Authentication Decorator ---
def require_api_key(f):
    """
    Decorator to protect an endpoint with an API key.
    The key must be provided in the 'Authorization' header as 'Bearer <key>'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if API_KEY:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"error": "Authorization header is missing or invalid"}), 401

            provided_key = auth_header.split("Bearer ")[1]
            if provided_key != API_KEY:
                return jsonify({"error": "Invalid API key"}), 403
        return f(*args, **kwargs)
    return decorated_function

# --- API Endpoints ---

@app.route("/healthz", methods=["GET"])
def health_check():
    """
    Health check endpoint to confirm the service is running.
    """
    return jsonify({"status": "ok"}), 200

@app.route("/download", methods=["GET"])
@require_api_key
def download_reel():
    """
    Downloads an Instagram Reel or Post video.
    Query Parameter:
        url (str): The full URL of the Instagram reel or post.
    """
    video_url = request.args.get("url")
    if not video_url:
        return jsonify({"error": "URL parameter is required"}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

        command = [
            "yt-dlp",
            "--no-playlist",
            "-f", YTDLP_FORMAT,
            "-o", output_template,
            "--force-overwrites",
            "--no-warnings",
            video_url,
        ]

        if COOKIES_PATH and os.path.exists(COOKIES_PATH):
            command.extend(["--cookies", COOKIES_PATH])
            logging.info(f"Using cookies from {COOKIES_PATH}")
        elif COOKIES_PATH:
            logging.warning(f"Cookies file specified but not found at {COOKIES_PATH}")

        logging.info(f"Executing command: {' '.join(command)}")

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=300  # 5-minute timeout
            )

            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                logging.error("yt-dlp ran successfully but no file was downloaded.")
                return jsonify({
                    "error": "yt-dlp did not download any file.",
                    "stdout": process.stdout,
                    "stderr": process.stderr
                }), 500

            video_path = os.path.join(temp_dir, downloaded_files[0])

            return send_file(
                video_path,
                as_attachment=True,
                download_name=f"{os.path.basename(video_path)}",
                mimetype="video/mp4"
            )

        except subprocess.CalledProcessError as e:
            logging.error(f"yt-dlp failed for URL: {video_url}")
            logging.error(f"Stderr: {e.stderr}")
            return jsonify({
                "error": "Failed to download video.",
                "url": video_url,
                "stdout": e.stdout,
                "stderr": e.stderr
            }), 500
        except subprocess.TimeoutExpired as e:
            logging.error(f"yt-dlp timed out for URL: {video_url}")
            return jsonify({
                "error": "Download process timed out.",
                "url": video_url,
                "stdout": e.stdout,
                "stderr": e.stderr
            }), 504 # Gateway Timeout
        except Exception as e:
            logging.error(f"An unexpected error occurred: {str(e)}")
            return jsonify({"error": "An unexpected server error occurred."}), 500

if __name__ == "__main__":
    # This block is for local development testing.
    # In production, Gunicorn will be used as the WSGI server.
    app.run(host="0.0.0.0", port=PORT, debug=True)
