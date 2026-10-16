import json
import os
import sys

import cv2
import numpy as np

TABLES_PATH = "data/tables.json"
TOPS_PATH = "data/table_tops.json"
VIDEO_FOLDER = "videos"
DISPLAY_SIZE = (960, 540)

mode = sys.argv[1] if len(sys.argv) > 1 else "tables"
if mode not in ("tables", "tops"):
    sys.exit("Usage: python draw_tables.py [tables|tops] [video]")

if len(sys.argv) > 2:
    video_path = sys.argv[2]
else:
    videos = sorted(f for f in os.listdir(VIDEO_FOLDER) if f.lower().endswith((".mp4", ".avi", ".mov")))
    if not videos:
        sys.exit(f"No video found in {VIDEO_FOLDER}/")
    video_path = os.path.join(VIDEO_FOLDER, videos[0])

cap = cv2.VideoCapture(video_path)
ok, first_frame = cap.read()
cap.release()
if not ok:
    sys.exit(f"Could not read {video_path}")

scale = first_frame.shape[1] / DISPLAY_SIZE[0]


def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


tables = load(TABLES_PATH)
if mode == "tops" and not tables:
    sys.exit("Draw the tables first: python draw_tables.py tables")

save_path = TABLES_PATH if mode == "tables" else TOPS_PATH
shapes = load(save_path)
current_points = []


def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        current_points.append([int(x * scale), int(y * scale)])


def to_display(points):
    return np.array([[int(px / scale), int(py / scale)] for px, py in points], np.int32)


def table_around(points):
    center = tuple(float(v) for v in np.array(points).mean(axis=0))
    for name, area in tables.items():
        if cv2.pointPolygonTest(np.array(area, np.int32), center, False) >= 0:
            return name
    return None


def draw():
    display = cv2.resize(first_frame, DISPLAY_SIZE)

    if mode == "tops":
        for name, points in tables.items():
            pts = to_display(points)
            cv2.polylines(display, [pts], True, (150, 150, 150), 1)
            x, y = pts.min(axis=0)
            cv2.putText(display, name, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    color = (0, 255, 0) if mode == "tables" else (255, 200, 0)
    for name, points in shapes.items():
        pts = to_display(points)
        cv2.polylines(display, [pts], True, color, 2)
        x, y = pts.min(axis=0)
        label = name if mode == "tables" else f"{name} top"
        cv2.putText(display, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    if current_points:
        pts = to_display(current_points)
        cv2.polylines(display, [pts], False, (0, 255, 255), 2)
        for px, py in pts:
            cv2.circle(display, (px, py), 4, (0, 255, 255), -1)

    what = "table" if mode == "tables" else "top, inside its grey table"
    cv2.rectangle(display, (0, 0), (DISPLAY_SIZE[0], 30), (0, 0, 0), -1)
    cv2.putText(display, f"Click = add corner of a {what}   N = next   U = undo   C = clear   S = save   Q = quit",
        (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return display


window = f"Draw {mode}"
cv2.namedWindow(window)
cv2.setMouseCallback(window, on_mouse)

while True:
    cv2.imshow(window, draw())
    key = cv2.waitKey(20) & 0xFF

    if key == ord("n"):
        if len(current_points) < 3:
            print("A shape needs at least 3 corners")
        elif mode == "tables":
            shapes[f"Table {len(shapes) + 1}"] = current_points.copy()
            current_points.clear()
        else:
            name = table_around(current_points)
            if name is None:
                print("This top is not inside any table, draw it inside a grey table")
            else:
                shapes[name] = current_points.copy()
                current_points.clear()
    elif key == ord("u"):
        if current_points:
            current_points.pop()
        elif shapes:
            shapes.popitem()
    elif key == ord("c"):
        shapes.clear()
        current_points.clear()
    elif key == ord("s"):
        with open(save_path, "w") as f:
            json.dump(dict(sorted(shapes.items(), key=lambda item: int(item[0].split()[-1]))), f, indent=2)
        print(f"Saved {len(shapes)} {mode} to {save_path}")
    elif key == ord("q"):
        break

cv2.destroyAllWindows()
