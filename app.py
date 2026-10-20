import logging
import threading

from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from legaldebunkr import language_generation, pipeline, retrieval
from legaldebunkr.config import settings

logging.basicConfig(level=logging.INFO)

ALLOWED = {"pdf", "docx", "png", "jpg", "jpeg", "tiff", "bmp"}
# Check real file signatures, not just the extension.
MAGIC = {
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "bmp": (b"BM",),
}
MAX_QUESTION_CHARS = 500

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024

# Behind a reverse proxy (Azure App Service, Nginx, Render...) set TRUST_PROXY_HOPS
# so rate limits key on the real client IP instead of the proxy's.
if settings.trust_proxy_hops > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=settings.trust_proxy_hops)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.ratelimit_storage_uri,
    headers_enabled=True,
)

# Caps how many analyses run at once in this process, to protect Azure spend.
_slots = threading.BoundedSemaphore(settings.max_concurrent_analyses)


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def index():
    return render_template("index.html", max_mb=settings.max_upload_mb)


@app.get("/health")
@limiter.exempt
def health():
    # Reports only whether services are configured, never any values.
    return jsonify(
        document_intelligence=settings.di_ready,
        content_understanding=settings.cu_ready,
        language_generation=settings.llm_ready,
    )


@app.post("/api/analyze")
@limiter.limit(settings.rate_limit_analyze)
def analyze():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="Choose a file to upload."), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED:
        return jsonify(error=f"Unsupported file type. Use: {', '.join(sorted(ALLOWED))}."), 400
    if not (settings.di_ready and settings.llm_ready):
        return jsonify(error="The server isn't configured yet."), 503

    data = file.read()
    if not data:
        return jsonify(error="That file is empty."), 400
    if not data.startswith(MAGIC[ext]):
        return jsonify(error="The file contents don't match its extension."), 400

    if not _slots.acquire(blocking=False):
        return jsonify(error="The server is busy. Try again in a minute."), 503
    try:
        result = pipeline.analyze_document(data, file.filename)
    except ValueError as exc:
        return jsonify(error=str(exc)), 422
    except Exception:
        app.logger.exception("analysis failed")
        return jsonify(error="Analysis failed. Try again, or try a different file."), 500
    finally:
        _slots.release()
    return jsonify(result)


@app.post("/api/ask")
@limiter.limit(settings.rate_limit_ask)
def ask():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    analysis = pipeline.get_analysis(str(body.get("doc_id", "")))
    if not analysis:
        return jsonify(error="That document session expired. Upload it again."), 404
    if not question:
        return jsonify(error="Type a question first."), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"Keep questions under {MAX_QUESTION_CHARS} characters."), 400
    context = retrieval.top_sections(question, analysis["sections"])
    try:
        answer = language_generation.answer_question(question, context, analysis["fields"])
    except Exception:
        app.logger.exception("ask failed")
        return jsonify(error="Could not answer that. Try again."), 500
    return jsonify(answer)


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"File is larger than {settings.max_upload_mb} MB."), 413


@app.errorhandler(429)
def rate_limited(e):
    return jsonify(error="Too many requests. Wait a bit and try again."), 429


if __name__ == "__main__":
    # Debug mode exposes an interactive debugger: opt in with FLASK_DEBUG=1, local only.
    app.run(debug=settings.debug, port=5000)
