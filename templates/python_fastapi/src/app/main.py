from fastapi import FastAPI

app = FastAPI(title="AutoDev App")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

