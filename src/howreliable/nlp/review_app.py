"""Small offline development annotation UI, deliberately separate from the product API."""

from __future__ import annotations

import argparse
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import get_args

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError

from howreliable.nlp.annotation_review import ReviewError, ReviewStore, WorkingReport
from howreliable.nlp.schemas import (
    TAXONOMY_VERSION,
    ComponentCode,
    ComponentMention,
    StrictModel,
    SymptomCode,
)


class SaveRequest(StrictModel):
    revision: int
    report: WorkingReport


def create_app(source: Path, working: Path, *, port: int = 8765) -> FastAPI:
    store = ReviewStore(source, working)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + host for host in hosts}

    @app.middleware("http")
    async def local_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Host checks prevent DNS rebinding; Origin/custom header reject cross-site writes.
        if (
            request.headers.get("host") not in hosts
            or request.headers.get("sec-fetch-site") == "cross-site"
            or request.headers.get("origin", next(iter(origins))) not in origins
        ):
            return JSONResponse({"error": "local_origin_required"}, status_code=403)
        if request.method == "POST" and (
            request.headers.get("x-review-request") != "1"
            or request.headers.get("content-type", "").split(";")[0] != "application/json"
        ):
            return JSONResponse({"error": "review_request_required"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            }
        )
        return response

    @app.exception_handler(ReviewError)
    async def review_error(request: Request, error: ReviewError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=409)

    @app.exception_handler(OSError)
    async def filesystem_error(request: Request, error: OSError) -> JSONResponse:
        return JSONResponse({"error": "working_file_unavailable"}, status_code=409)

    @app.get("/")
    def home() -> HTMLResponse:
        return HTMLResponse(Path(__file__).with_name("review.html").read_text(encoding="utf-8"))

    @app.get("/app.js")
    def javascript() -> Response:
        return Response(
            Path(__file__).with_name("review.js").read_bytes(), media_type="text/javascript"
        )

    @app.get("/style.css")
    def stylesheet() -> Response:
        return Response(Path(__file__).with_name("review.css").read_bytes(), media_type="text/css")

    @app.get("/api/session")
    def session() -> dict[str, object]:
        document = store.read()
        return {
            "revision": document.revision,
            "reports": [
                {"index": i, "id": r.annotation.annotation_id, "state": r.state}
                for i, r in enumerate(document.reports)
            ],
            "taxonomy_version": TAXONOMY_VERSION,
            "components": get_args(ComponentCode),
            "symptoms": get_args(SymptomCode),
            "assertions": get_args(ComponentMention.model_fields["assertion"].annotation),
            "states": get_args(WorkingReport.model_fields["state"].annotation),
        }

    @app.get("/api/report/{index}")
    def report(index: int) -> dict[str, object]:
        document = store.read()
        if not 0 <= index < len(document.reports):
            raise ReviewError("unknown_report")
        return {
            "revision": document.revision,
            "report": document.reports[index].model_dump(mode="json"),
        }

    @app.post("/api/report/{index}")
    async def save(index: int, request: Request) -> dict[str, object]:
        try:
            payload = SaveRequest.model_validate_json(await request.body())
        except ValidationError:
            raise ReviewError("invalid_save_schema") from None
        result = store.save(index, payload.report, payload.revision)
        return {"revision": result.revision, "saved": True}

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local development-only annotation editor")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--working", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        app = create_app(args.source, args.working, port=args.port)
    except (ReviewError, OSError):
        parser.exit(
            2, "Cannot open development worksheet/working copy; check paths and validation.\n"
        )
    print(f"Development review: http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
