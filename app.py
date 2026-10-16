import json
import os
import threading
import time
from collections import deque

import cv2
import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import database
from pipeline import DEFAULT_SETTINGS, run_pipeline

WEB_FOLDER = "web"
SETTINGS_PATH = "data/settings.json"
VIDEO_FOLDERS = ["videos"]
PORT = int(os.environ.get("PORT", 8020))
SNAPSHOT_SECONDS = 5
LIVE_MINUTES = 5


EDITABLE = {
    "video": None,
    "jpeg_quality": (30, 95),
    "occupy_seconds": (0, 60),
    "free_seconds": (0, 60),
    "up_seconds": (0, 60),
    "down_seconds": (1, 120),
    "confidence": (0.05, 0.95),
    "pose_confidence": (0.05, 0.95),
    "seats_per_table": (1, 12),
}

DEFAULTS = {**DEFAULT_SETTINGS, "video": "videos/Resturant-Demo-short.mp4", "jpeg_quality": 80}
settings = dict(DEFAULTS)
if os.path.exists(SETTINGS_PATH):
    with open(SETTINGS_PATH) as f:
        settings.update(json.load(f))
if not os.path.exists(settings["video"]):
    settings["video"] = DEFAULTS["video"]

app = FastAPI()


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response

latest = {"jpeg": None, "number": 0, "info": None, "processing_fps": 0,
          "started": time.time(), "restart": False}
live_points = deque(maxlen=LIVE_MINUTES * 60)
activity = deque(maxlen=50)


def list_videos():
    videos = []
    for folder in VIDEO_FOLDERS:
        if os.path.isdir(folder):
            videos += [os.path.normpath(os.path.join(folder, f))
                for f in sorted(os.listdir(folder)) if f.lower().endswith((".mp4", ".avi", ".mov"))]
    return videos


def save_history(info, visits):
    for name, table in info["tables"].items():
        if table["occupied"] and table["guests"] > 0:
            if name not in visits:
                activity.appendleft({"time": database.now(), "table": name, "event": "Seated",
                    "guests": table["guests"]})
            guests = max(table["guests"], visits.get(name, {}).get("guests", 0))
            visits[name] = {"guests": guests, "seconds": table["seconds"]}
        elif not table["occupied"] and name in visits:

            visit = visits.pop(name)
            database.save_visit(name, visit["seconds"], visit["guests"])
            activity.appendleft({"time": database.now(), "table": name,
                "event": f"Left after {visit['seconds'] // 60}:{visit['seconds'] % 60:02d}",
                "guests": visit["guests"]})


def process_video():

    visits = {}
    last_snapshot = last_point = 0
    while True:
        latest["restart"] = False
        started = time.time()
        for frame_count, (frame, info) in enumerate(
                run_pipeline(settings["video"], {**settings, "draw_summary": False})):
            if latest["restart"]:
                break
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(settings["jpeg_quality"])])
            latest["jpeg"] = jpeg.tobytes()
            latest["info"] = info
            latest["number"] += 1
            latest["processing_fps"] = round((frame_count + 1) / (time.time() - started), 1)

            save_history(info, visits)
            if time.time() - last_snapshot >= SNAPSHOT_SECONDS:
                database.save_snapshot(info["occupied_tables"], info["guests"])
                last_snapshot = time.time()
            if time.time() - last_point >= 1:
                live_points.append({"time": database.now(), "occupied_tables": info["occupied_tables"],
                    "guests": info["guests"]})
                last_point = time.time()


            wait = started + frame_count / info["fps"] - time.time()
            if wait > 0:
                time.sleep(wait)


def video_frames():

    sent = 0
    while True:
        if latest["number"] == sent:
            time.sleep(0.005)
            continue
        sent = latest["number"]
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + latest["jpeg"] + b"\r\n"


@app.get("/", response_class=HTMLResponse)
def page():
    with open(f"{WEB_FOLDER}/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/video")
def video():
    return StreamingResponse(video_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/stats")
def stats():
    if latest["info"] is None:
        return {"ready": False, "video": os.path.basename(settings["video"])}
    return {"ready": True, **latest["info"],
            "video": os.path.basename(settings["video"]),
            "processing_fps": latest["processing_fps"],
            "running_seconds": int(time.time() - latest["started"])}


@app.get("/analytics/data")
def analytics_data():
    return {"now": database.now(), "points": list(live_points), "activity": list(activity)}


@app.get("/history/data")
def history_data(seconds: int = 300):

    return {
        "now": database.now(),
        "counts": database.counts(),
        "snapshots": database.snapshots(seconds or None),
        "tables": database.table_summary(),
        "recent": database.recent_visits(),
    }


@app.get("/settings")
def get_settings():
    return {"settings": {key: settings[key] for key in EDITABLE}, "videos": list_videos()}


@app.post("/settings")
def save_settings(new: dict = Body(...)):
    for key, limits in EDITABLE.items():
        if key not in new:
            continue
        if key == "video":
            if new[key] in list_videos():
                settings[key] = new[key]
            continue
        try:
            value = float(new[key])
        except (TypeError, ValueError):
            continue
        if key in ("jpeg_quality", "seats_per_table"):
            value = int(value)
        settings[key] = min(max(value, limits[0]), limits[1])

    return apply_settings()


@app.post("/settings/reset")
def reset_settings():
    settings.update({key: DEFAULTS[key] for key in EDITABLE})
    return apply_settings()


def apply_settings():
    with open(SETTINGS_PATH, "w") as f:
        json.dump({key: settings[key] for key in EDITABLE}, f, indent=2)
    latest["restart"] = True
    return get_settings()


@app.post("/restart")
def restart_video():
    latest["restart"] = True
    return {"ok": True}


@app.get("/snapshot")
def snapshot():

    name = time.strftime("snapshot-%Y%m%d-%H%M%S.jpg")
    return Response(latest["jpeg"] or b"", media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


app.mount("/static", StaticFiles(directory=WEB_FOLDER), name="static")

if __name__ == "__main__":
    threading.Thread(target=process_video, daemon=True).start()

    print(f"\n  Open http://localhost:{PORT}\n")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning", timeout_graceful_shutdown=1)
