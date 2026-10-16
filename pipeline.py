import json
from collections import Counter, deque

import cv2
import numpy as np
from ultralytics import YOLO

from utils import draw_table_tops, find_seats, remove_duplicates, remove_standing, steady_seats, table_shape


RED = (0,0,255)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

DEFAULT_SETTINGS = {
    "tables_path": "data/tables.json",
    "table_tops_path": "data/table_tops.json",
    "model_path": "models/yolo11s.pt",
    "pose_model_path": "models/yolo11s-pose.pt",
    "confidence": 0.2,
    "pose_confidence": 0.3,
    "occupy_seconds": 1,
    "free_seconds": 1,
    "up_seconds": 2,
    "down_seconds": 10,
    "seats_per_table": 4,
    "draw_summary": True,
}


def run_pipeline(video_path, settings=DEFAULT_SETTINGS):
    s = {**DEFAULT_SETTINGS, **settings}
    model = YOLO(s["model_path"])
    pose_model = YOLO(s["pose_model_path"])
    with open(s["tables_path"]) as f:
        tables = json.load(f)
    with open(s["table_tops_path"]) as f:
        table_tops = json.load(f)
    seat_count = s["seats_per_table"]
    table_centers = {name: np.array(points).mean(axis=0) for name, points in table_tops.items()}
    shapes = {name: table_shape(points) for name, points in table_tops.items()}

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    up_frames = int(s["up_seconds"] * fps)
    down_frames = int(s["down_seconds"] * fps)

    present = {name: 0 for name in tables}
    empty = {name: 0 for name in tables}
    recent = {name: deque([0] * down_frames, maxlen=down_frames) for name in tables}
    locked = {name: 0 for name in tables}
    since = {name: 0 for name in tables}
    was_occupied = {name: False for name in tables}
    seat_scores = {name: [0.0] * seat_count for name in tables}
    frame_number = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_number += 1

        boxes = model(frame, classes=[0], conf=s["confidence"], verbose=False)[0].boxes
        pose = pose_model(frame, conf=s["pose_confidence"], verbose=False)[0]
        people = remove_duplicates(remove_standing(boxes, pose))
        centers = [((x1 + x2) // 2, (y1 + y2) // 2)
            for x1, y1, x2, y2 in (map(int, box.xyxy[0]) for box in people)]

        colors, guests = {}, {}
        info = {"tables": {}}
        for name, points in tables.items():
            polygon = np.array(points, np.int32)
            seated = [c for c in centers if cv2.pointPolygonTest(polygon, c, False) >= 0]
            count = min(len(seated), seat_count)
            recent[name].append(count)


            steady = Counter(list(recent[name])[-up_frames:]).most_common(1)[0][0]
            if steady > locked[name]:
                locked[name] = steady
            elif max(recent[name]) < locked[name]:
                locked[name] = max(recent[name])

            if count > 0:
                present[name] += 1
                empty[name] = 0
            else:
                empty[name] += 1
                if empty[name] > s["free_seconds"] * fps:
                    present[name] = 0

            occupied = present[name] >= s["occupy_seconds"] * fps
            colors[name] = RED if occupied else GREEN
            guests[name] = locked[name] if occupied else 0
            if occupied != was_occupied[name]:
                was_occupied[name] = occupied
                since[name] = frame_number

            taken_now = find_seats(table_centers[name], seated, seat_count, shapes[name])
            info["tables"][name] = {
                "occupied": occupied,
                "guests": guests[name],
                "seconds": int((frame_number - since[name]) / fps),
                "shape": shapes[name],
                "seats_taken": steady_seats(seat_scores[name], taken_now, guests[name]),
            }

        frame = draw_table_tops(frame, table_tops, colors)
        for name, points in table_tops.items():
            if guests[name] == 0:
                continue
            x, y = np.array(points).mean(axis=0).astype(int)
            seconds = info["tables"][name]["seconds"]
            label, time_text = str(guests[name]), f"{seconds // 60}:{seconds % 60:02d}"
            (w, h), _ = cv2.getTextSize(label, FONT, 1.2, 3)
            (tw, th), _ = cv2.getTextSize(time_text, FONT, 0.6, 2)
            top = y - (h + 8 + th) // 2
            cv2.putText(frame, label, (x - w // 2, top + h), FONT, 1.2, WHITE, 3)
            cv2.putText(frame, time_text, (x - tw // 2, top + h + 8 + th), FONT, 0.6, WHITE, 2)

        info["occupied_tables"] = sum(table["occupied"] for table in info["tables"].values())
        info["total_tables"] = len(tables)
        info["guests"] = sum(table["guests"] for table in info["tables"].values())
        info["seats_per_table"] = seat_count
        info["seats"] = seat_count * len(tables)
        info["fps"] = fps

        if s["draw_summary"]:
            cv2.rectangle(frame, (10, 10), (400, 100), (0,0,0), -1)
            cv2.putText(frame, f"Occupied: {info['occupied_tables']} / {info['total_tables']} tables",
                (20, 46), FONT, 0.9, WHITE, 2)
            cv2.putText(frame, f"Guests: {info['guests']} / {info['seats']} seats",
                (20, 86), FONT, 0.9, WHITE, 2)

        yield frame, info

    cap.release()
