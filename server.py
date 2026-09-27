import os, secrets
from urllib.parse import urlencode
from flask import Flask, render_template, redirect, request, jsonify, session
import requests

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI = os.environ["TIKTOK_REDIRECT_URI"]

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API_URL = "https://open.tiktokapis.com/v2"

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/oauth")
def oauth():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    params = {
        "client_key": CLIENT_KEY,
        "response_type": "code",
        "scope": "user.info.basic,video.publish,video.upload",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    return redirect(AUTH_URL + "?" + urlencode(params))

@app.get("/callback/")
def callback():
    error = request.args.get("error")
    if error:
        return render_template(
            "callback.html",
            message=request.args.get("error_description") or error,
            ok=False,
        ), 400

    code = request.args.get("code")
    state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)

    if not code or not state or state != saved_state:
        return render_template(
            "callback.html",
            message="Invalid or expired authorization response.",
            ok=False,
        ), 400

    response = requests.post(
        TOKEN_URL,
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )

    if not response.ok:
        return render_template(
            "callback.html",
            message="TikTok token exchange failed.",
            ok=False,
        ), 400

    data = response.json()
    session["access_token"] = data["access_token"]
    session["refresh_token"] = data.get("refresh_token")
    session["open_id"] = data.get("open_id")
    return redirect("/?connected=1")

def auth_headers():
    token = session.get("access_token")
    if not token:
        raise RuntimeError("Not connected")
    return {"Authorization": "Bearer " + token}

@app.get("/api/session")
def api_session():
    token = session.get("access_token")
    if not token:
        return jsonify(connected=False)

    response = requests.get(
        API_URL + "/user/info/",
        params={"fields": "open_id,display_name,avatar_url"},
        headers={"Authorization": "Bearer " + token},
        timeout=20,
    )
    if not response.ok:
        session.pop("access_token", None)
        return jsonify(connected=False)

    user = response.json().get("data", {}).get("user", {})
    return jsonify(
        connected=True,
        display_name=user.get("display_name"),
        avatar_url=user.get("avatar_url"),
    )

@app.post("/api/creator-info")
def creator_info():
    try:
        response = requests.post(
            API_URL + "/post/publish/creator_info/query/",
            headers={**auth_headers(), "Content-Type": "application/json"},
            timeout=30,
        )
        return (response.text, response.status_code,
                {"Content-Type": "application/json"})
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 401

@app.post("/api/publish")
def publish():
    if "access_token" not in session:
        return jsonify(error="Connect TikTok first."), 401

    video = request.files.get("video")
    if not video:
        return jsonify(error="No video selected."), 400

    data = video.read()
    size = len(data)
    if size == 0:
        return jsonify(error="The selected video is empty."), 400

    # TikTok Direct Post FILE_UPLOAD uses chunks. Keep the implementation
    # simple and compatible with the existing uploader.
    max_chunk = 5 * 1024 * 1024
    chunk = min(size, max_chunk)
    total = (size + chunk - 1) // chunk

    payload = {
        "post_info": {
            "title": request.form.get("caption", "")[:2200],
            "privacy_level": request.form.get("privacy_level", "SELF_ONLY"),
            "disable_comment": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk,
            "total_chunk_count": total,
        },
    }

    response = requests.post(
        API_URL + "/post/publish/video/init/",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if not response.ok:
        return jsonify(error=response.text), response.status_code

    result = response.json().get("data", {})
    upload_url = result.get("upload_url")
    if not upload_url:
        return jsonify(error="TikTok did not return an upload URL."), 502

    for index in range(total):
        start = index * chunk
        end = min(size, start + chunk) - 1
        part = data[start:end + 1]

        upload = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            },
            data=part,
            timeout=120,
        )
        if upload.status_code not in (200, 201, 206):
            return jsonify(error=upload.text), 502

    return jsonify(
        message="Video sent to TikTok.",
        publish_id=result.get("publish_id"),
    )

@app.post("/api/draft")
def draft():
    return jsonify(
        error="Draft upload is not enabled in this build yet. Use Direct Post."
    ), 501

@app.get("/terms.html")
def terms():
    return "<h1>Terms of Service</h1><p>Users are responsible for content they submit.</p>"

@app.get("/privacy.html")
def privacy():
    return "<h1>Privacy Policy</h1><p>OAuth tokens are stored server-side.</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
