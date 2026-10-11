How to run
    Terminal A
        cd backend
        uvicorn app.main:app --reload --port 8000.

    Terminal B
        cd frontend
        npm run dev

## Run with Docker Compose

The backend uses an external PostgreSQL/TimescaleDB database. Copy `.env.example`
to `.env`, set `CONNECTION` to your database URL, then run:

```sh
docker compose up --build
```

Open <http://localhost:3000>. The frontend container forwards API requests to the
backend container. The backend is also available at <http://localhost:8000>.

