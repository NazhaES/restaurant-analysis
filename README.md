# restaurant-analysis

Live restaurant table occupancy from a camera video.

A YOLO model finds the people in each frame, and a pose model filters out the ones standing,
like waiters and people walking past. Each seated guest is matched to a table and a seat.
A web dashboard shows the live video with every table colored free or occupied, plus how many
guests are at it and for how long. Every visit is saved to a database for the history charts.

- **Live floor**: the video, occupancy, guests, seat utilization and seated time
- **Analytics**: the last 5 minutes and an activity log
- **History**: saved visits for each table, with charts
- **Settings**: video source and detection timings, applied without a restart

Everything runs on your own computer. No video leaves the machine.

## Demo

![Demo](docs/demo.gif)

[Watch the full-quality video](docs/demo.mp4)

## Run with Docker

```bash
docker compose up --build
```

Open http://localhost:8080 (Docker) or http://localhost:8020 (without Docker)

## Run without Docker

```bash
pip install -r requirements.txt
python app.py
```

## Draw the tables

Run once for a new camera, on your computer (not in Docker, it opens a window):

```bash
python draw_tables.py tables
python draw_tables.py tops
```

Click the corners, `N` for the next shape, `S` to save, `Q` to quit.
Draw the whole table area with its chairs first, then only the table tops.
Each top takes the name of the table it is drawn inside.

## Folders

- `models/`: `yolo11s.pt` and `yolo11s-pose.pt`
- `videos/`: videos you can pick in Settings
- `data/`: `tables.json`, `table_tops.json`, plus `settings.json` and `history.db` (created on first run)
