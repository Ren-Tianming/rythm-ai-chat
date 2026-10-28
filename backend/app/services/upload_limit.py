"""Bound multipart request size before Starlette spools the entire body to disk."""

from starlette.responses import JSONResponse


class UploadBodyLimit:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith("/documents")
        ):
            return await self.app(scope, receive, send)
        limit = self.settings.document_batch_limit * self.settings.document_max_bytes + 1024 * 1024
        length = dict(scope["headers"]).get(b"content-length")
        if length and int(length) > limit:
            return await JSONResponse(
                {
                    "error": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": f"Upload request exceeds {limit} bytes",
                    }
                },
                413,
            )(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                from fastapi import HTTPException

                raise HTTPException(413, "Upload request is too large")
            return message

        await self.app(scope, bounded_receive, send)
