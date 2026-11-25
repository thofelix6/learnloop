# LearnLoop

A multi-course study app with auto-graded exercises: FastAPI + SQLite + vanilla JS.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 7777
```

Data (SQLite database, audio, guides) lives in `data/` and is not committed.

## Docker

```bash
docker build -t learnloop .
docker run -p 7777:7777 -v /path/to/data:/app/data learnloop
```
