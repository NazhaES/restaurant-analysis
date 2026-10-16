import math

import cv2
import numpy as np


MAX_OVERLAP = 0.7

def overlap(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1,by1,bx2,by2 = box_b

    width = min(ax2,bx2) - max(ax1,bx1)
    height = min(ay2, by2) -max(ay1, by1)
    if width <=0 or height <= 0:
        return 0

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return (width * height) / min(area_a, area_b)

def remove_duplicates(boxes):
    corners = boxes.xyxy.tolist()
    confidences = boxes.conf.tolist()
    order = sorted(range(len(corners)), key=lambda i:confidences[i], reverse=True)

    kept = []
    for i in order:
        if all(overlap(corners[i], corners[k]) < MAX_OVERLAP for k in kept ):
            kept.append(i)
    return [boxes[i] for i in kept]


TINT = 0.4

def draw_table_tops(frame, table_tops, colors):
    overlay = frame.copy()
    for name , points in table_tops.items():
        table_top = np.array(points, np.int32)
        cv2.fillPoly(overlay, [table_top], colors[name])
        cv2.polylines(frame, [table_top], True, colors[name], 2)
    return cv2.addWeighted(overlay, TINT, frame, 1 - TINT, 0)


THIGH_TO_TORSO = 0.4
KNEE_CONFIDENCE = 0.5
SAME_PERSON = 0.5

LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_HIP , RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13 , 14

def is_standing(keypoints):
    points = keypoints.xy[0].tolist()
    confidence = keypoints.conf[0].tolist()
    if max(confidence[LEFT_KNEE], confidence[RIGHT_KNEE]) < KNEE_CONFIDENCE:
        return False

    knee = LEFT_KNEE if confidence[LEFT_KNEE] >= confidence[RIGHT_KNEE] else RIGHT_KNEE
    shoulder_y = (points[LEFT_SHOULDER][1] + points[RIGHT_SHOULDER][1]) / 2
    hip_y = (points[LEFT_HIP][1] + points[RIGHT_HIP][1]) / 2

    torso = hip_y - shoulder_y
    thigh = points[knee][1] - hip_y
    if torso <= 0:
        return False

    return thigh / torso > THIGH_TO_TORSO


def shared_area(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    width = min(ax2, bx2) - max(ax1, bx1)
    height = min(ay2, by2) - max(ay1, by1)
    if width <= 0 or height <= 0:
        return 0

    shared = width * height
    total = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - shared
    return shared / total

def remove_standing(boxes , pose_result):
    standing = []
    for box, keypoints in zip(pose_result.boxes, pose_result.keypoints):
        if is_standing(keypoints):
            standing.append(box.xyxy[0].tolist())

    sitting = []
    for i , corners in enumerate(boxes.xyxy.tolist()):
        if not any(shared_area(corners , other) >= SAME_PERSON for other in standing):
            sitting.append(i)
    return boxes[sitting]


SCORE_KEEP = 0.9


def table_shape(top_points):
    return "square" if len(top_points) <= 4 else "round"


def seat_angle(seat, seat_count, shape):
    start = 0 if shape == "square" else 45
    return (start + seat * 360 / seat_count) % 360


def angle_between(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def find_seats(table_center, people, seat_count, shape):
    table_x, table_y = table_center
    pairs = []
    for person, (x, y) in enumerate(people):
        direction = math.degrees(math.atan2(y - table_y, x - table_x)) % 360
        for seat in range(seat_count):
            pairs.append((angle_between(direction, seat_angle(seat, seat_count, shape)), person, seat))
    pairs.sort()

    used_people, taken = set(), set()
    for _, person, seat in pairs:
        if person not in used_people and seat not in taken:
            used_people.add(person)
            taken.add(seat)
    return taken


def steady_seats(scores, taken_now, guests):
    for seat in range(len(scores)):
        scores[seat] = scores[seat] * SCORE_KEEP + (1 if seat in taken_now else 0)
    best = sorted(range(len(scores)), key=lambda seat: scores[seat], reverse=True)[:guests]
    return sorted(best)
