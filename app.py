"""FastAPI app — POST /ask serves query layer + static UI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import get_conn
from execute import execute
from guard import apply_guard
from plan import build_plan

load_dotenv()

app = FastAPI(title="eng-intel")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AskRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/ask")
def ask(req: AskRequest):
    plan = build_plan(req.question)
    with get_conn() as conn:
        result = execute(conn, plan)
    guarded = apply_guard(result.answer, result.citations, result.rows, result.aggregates)
    return {
        "question": req.question,
        "plan": plan.to_dict(),
        "answer": guarded.text,
        "coverage": result.coverage_note,
        "citations": result.citations,
        "aggregates": result.aggregates,
        "sql": result.sql,
        "sql_params": result.sql_params,
        "search_mode": result.search_mode,
        "guard": {
            "stripped_urls": guarded.stripped_urls,
            "stripped_numbers": guarded.stripped_numbers,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
