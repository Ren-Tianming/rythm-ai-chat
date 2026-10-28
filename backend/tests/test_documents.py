import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select

from app.core.security import utc_now
from app.db.models import Document, DocumentChunk, MessageSource, UsageEvent
from app.services.document_worker import claim_document, process_document


def frames(response):
    result = []
    for frame in response.text.split("\n\n"):
        lines = frame.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), "")
        data = next((line[6:] for line in lines if line.startswith("data: ")), "")
        if data:
            result.append((event, json.loads(data)))
    return result


async def upload(
    system,
    name="notes.txt",
    content=b"ORION budget is 4200000 yen. Deadline is November 30.",
    conversation=None,
):
    response = await system.client.post(
        f"/api/v1/conversations/{conversation or system.conversations[0].id}/documents",
        files=[("files", (name, content))],
    )
    assert response.status_code == 202, response.text
    return response.json()[0]


async def process(system):
    item = await claim_document(system.factory, system.settings)
    assert item
    await process_document(item, system.factory, system.settings)
    async with system.factory() as db:
        result = await db.get(Document, item.id)
        assert result.status == "ready", result.error
    return item


async def chat(system, question="What is the ORION budget?", ids=None, **extra):
    return await system.client.post(
        f"/api/v1/conversations/{system.conversations[0].id}/messages/stream",
        json={
            "content": question,
            "document_ids": ids or [],
            "client_request_id": str(uuid.uuid4()),
            **extra,
        },
    )


@pytest.mark.asyncio
async def test_upload_retrieve_citations_and_delete(system):
    doc = await upload(system)
    item = await process(system)
    for question in ("ORION budget?", "オリオンの予算は？", "猎户预算是多少？"):
        response = await chat(system, question, [doc["id"]])
        assert response.status_code == 200, response.text
        metadata = frames(response)[0][1]
        assert metadata["max_output_tokens"] > 1024
        source = metadata["sources"][0]
        assert source["document_id"] == doc["id"]
        assert "4200000" in source["excerpt"]
        assert source["page_number"] is None
    messages = (
        await system.client.get(f"/api/v1/conversations/{system.conversations[0].id}/messages")
    ).json()
    assert messages[-1]["sources"][0]["document_id"] == doc["id"]
    assert (
        "[S1]" in system.provider.calls[-1][0][-1].content
        or '"label": "S1"' in system.provider.calls[-1][0][-1].content
    )
    original = Path(system.settings.upload_dir) / item.storage_key
    assert original.exists()
    assert (await system.client.delete(f"/api/v1/documents/{doc['id']}")).status_code == 204
    assert not original.exists()
    async with system.factory() as db:
        assert await db.scalar(select(func.count(DocumentChunk.id))) == 0
        assert await db.scalar(select(func.count(MessageSource.id))) == 0
    assert (await chat(system, ids=[doc["id"]])).status_code == 404


@pytest.mark.asyncio
async def test_all_document_routes_enforce_user_session_and_csrf(system):
    doc = await upload(system)
    await process(system)
    urls = [
        f"/api/v1/documents/{doc['id']}",
        f"/api/v1/documents/{doc['id']}/content",
        f"/api/v1/conversations/{system.conversations[0].id}/documents",
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=system.app), base_url="http://testserver"
    ) as anonymous:
        for url in urls:
            assert (await anonymous.get(url)).status_code == 401
    system.client.cookies.update(system.cookies[1])
    system.client.headers["X-CSRF-Token"] = system.cookies[1]["rythm_csrf"]
    for url in urls:
        assert (await system.client.get(url)).status_code == 404
    assert (await system.client.delete(f"/api/v1/documents/{doc['id']}")).status_code == 404
    assert (await system.client.post(f"/api/v1/documents/{doc['id']}/retry")).status_code == 404
    response = await system.client.post(
        f"/api/v1/conversations/{system.conversations[1].id}/messages/stream",
        json={
            "content": "ORION?",
            "document_ids": [doc["id"]],
            "client_request_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404
    system.client.cookies.update(system.cookies[0])
    system.client.headers["X-CSRF-Token"] = "wrong"
    assert (await system.client.delete(f"/api/v1/documents/{doc['id']}")).status_code == 403


@pytest.mark.asyncio
async def test_selected_conversation_only_and_no_evidence(system):
    first = await upload(system)
    await process(system)
    other = (
        await system.client.post(
            "/api/v1/conversations", json={"model_profile_id": str(system.model.id)}
        )
    ).json()
    other_doc = await upload(system, conversation=other["id"])
    await process(system)
    assert (await chat(system, ids=[other_doc["id"]])).status_code == 404
    response = await chat(system, "How tall is Mount Everest?", [first["id"]])
    assert frames(response)[0][1]["sources"] == []
    assert frames(response)[-1][1]["finish_reason"] == "insufficient_evidence"
    assert not system.provider.calls
    assert (await chat(system)).status_code == 200
    assert system.provider.calls


def make_image():
    image = Image.new("RGB", (1400, 220), "white")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = (
        ImageFont.truetype(font_path, 44)
        if Path(font_path).exists()
        else ImageFont.load_default(size=44)
    )
    draw.text((35, 70), "ORION budget is 4200000 yen.", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["pdf", "scan", "png", "jpg", "webp", "md", "encoded"])
async def test_real_parsers_and_ocr(system, kind):
    if kind in ("pdf", "scan"):
        pdf = pymupdf.open()
        page = pdf.new_page()
        if kind == "pdf":
            page.insert_text(
                (40, 80),
                "ORION budget is 4200000 yen. This is an actual PDF text paragraph.",
                fontsize=12,
            )
        else:
            page.insert_image(pymupdf.Rect(0, 0, 595, 100), stream=make_image())
        data, name = pdf.tobytes(), "plan.pdf"
        pdf.close()
    elif kind in ("png", "jpg", "webp"):
        buffer = io.BytesIO()
        Image.open(io.BytesIO(make_image())).save(
            buffer, format={"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}[kind]
        )
        data, name = buffer.getvalue(), f"plan.{kind}"
    elif kind == "encoded":
        data, name = (
            "ORION budget is 4200000 yen. 日本語の仕様です。".encode("utf-16"),
            "日本語.txt",
        )
    else:
        data, name = b"# ORION\n\nORION budget is 4200000 yen.", "plan.md"
    doc = await upload(system, name, data)
    await process(system)
    content = await system.client.get(f"/api/v1/documents/{doc['id']}/content")
    assert content.content == data and content.headers["cache-control"] == "private, no-store"
    response = await chat(system, ids=[doc["id"]])
    assert response.status_code == 200
    sources = frames(response)[0][1]["sources"]
    assert "4200000" in sources[0]["excerpt"]
    assert sources[0]["page_number"] == (1 if kind in ("pdf", "scan") else None)


@pytest.mark.asyncio
async def test_invalid_batch_limits_no_partial_files(system):
    for name, data, status in [
        ("bad.pdf", b"not a PDF", 422),
        ("bad.exe", b"bad", 415),
        ("bad.txt", b"\x00\x01binary", 422),
        ("bad.png", b"fakepng", 422),
        ("empty.md", b"", 422),
    ]:
        response = await system.client.post(
            f"/api/v1/conversations/{system.conversations[0].id}/documents",
            files={"files": (name, data)},
        )
        assert response.status_code == status, response.text
    system.settings.document_max_bytes = 20
    response = await system.client.post(
        f"/api/v1/conversations/{system.conversations[0].id}/documents",
        files=[("files", ("valid.txt", b"hello")), ("files", ("large.txt", b"x" * 21))],
    )
    assert response.status_code == 413
    assert not list(Path(system.settings.upload_dir).glob("*"))
    system.settings.document_user_limit = 1
    await upload(system, content=b"hello")
    assert (
        await system.client.post(
            f"/api/v1/conversations/{system.conversations[0].id}/documents",
            files={"files": ("other.txt", b"hi")},
        )
    ).status_code == 413


@pytest.mark.asyncio
async def test_failure_retry_reindex_and_restart_recovery(system, monkeypatch):
    doc = await upload(system)

    async def fail(*args):
        raise ValueError("Embedding unavailable")

    with monkeypatch.context() as context:
        context.setattr("app.services.document_worker.embed_texts", fail)
        item = await claim_document(system.factory, system.settings)
        await process_document(item, system.factory, system.settings)
    assert (await system.client.get(f"/api/v1/documents/{doc['id']}")).json()["status"] == "failed"
    assert (await chat(system, ids=[doc["id"]])).status_code == 409
    assert (await system.client.post(f"/api/v1/documents/{doc['id']}/retry")).status_code == 202
    await process(system)
    system.settings.embedding_version = "new-version"
    assert (await chat(system, ids=[doc["id"]])).status_code == 409
    assert (await system.client.get(f"/api/v1/documents/{doc['id']}")).json()["requires_reindex"]
    await system.client.post(f"/api/v1/documents/{doc['id']}/retry")
    item = await claim_document(system.factory, system.settings)
    async with system.factory() as db:
        row = await db.get(Document, item.id)
        row.processing_started_at = utc_now() - timedelta(minutes=20)
        await db.commit()
    await claim_document(system.factory, system.settings)
    assert (await system.client.get(f"/api/v1/documents/{doc['id']}")).json()["status"] == "failed"


@pytest.mark.asyncio
async def test_long_output_continuation_history_model_switch(system):
    response = await chat(system, "LONG report")
    assert frames(response)[-1][1]["truncated"] is True
    assert (
        len("".join(d["text"] for event, d in frames(response) if event == "delta").split()) > 1024
    )
    messages = (
        await system.client.get(f"/api/v1/conversations/{system.conversations[0].id}/messages")
    ).json()
    assert messages[-1]["finish_reason"] == "length"
    assert (
        await chat(system, "Continue", continue_message_id=messages[-1]["id"])
    ).status_code == 200
    assert "word word" in system.provider.calls[-1][0][-1].content
    assert (
        await chat(system, "Continue", continue_message_id=messages[-1]["id"])
    ).status_code == 409
    assert (
        await chat(system, "hello", model_profile_id=str(system.second_model.id))
    ).status_code == 200
    async with system.factory() as db:
        assert await db.scalar(select(func.count(UsageEvent.id))) == 3
    assert system.provider.calls[-1][2] > 1024


@pytest.mark.asyncio
async def test_multiple_documents_and_conversation_delete(system):
    first = await upload(system, "one.txt")
    await process(system)
    second = await upload(system, "two.txt")
    await process(system)
    sources = frames(await chat(system, ids=[first["id"], second["id"]]))[0][1]["sources"]
    assert {s["document_id"] for s in sources} == {first["id"], second["id"]}
    assert (
        await system.client.delete(f"/api/v1/conversations/{system.conversations[0].id}")
    ).status_code == 200
    assert not list(Path(system.settings.upload_dir).glob("*"))
    assert (await system.client.get(f"/api/v1/documents/{first['id']}/content")).status_code == 404


@pytest.mark.asyncio
async def test_cancel_immediately_preserves_partial_text_and_usage(system):
    import asyncio
    from app.db.models import Generation
    from app.services.llm.base import ProviderEvent

    started = asyncio.Event()

    async def slow_stream(*args):
        yield ProviderEvent(text="partial response ", input_tokens=10)
        started.set()
        await asyncio.Event().wait()

    system.provider.stream = slow_stream
    task = asyncio.create_task(chat(system, "Slow response"))
    await asyncio.wait_for(started.wait(), 3)
    async with system.factory() as db:
        generation = await db.scalar(select(Generation))
    response = await system.client.post(f"/api/v1/generations/{generation.id}/cancel")
    assert response.status_code == 200
    await asyncio.wait_for(task, 2)
    messages = (
        await system.client.get(f"/api/v1/conversations/{system.conversations[0].id}/messages")
    ).json()
    assert messages[-1]["content"] == "partial response "
    assert messages[-1]["status"] == "cancelled"
    async with system.factory() as db:
        assert (await db.scalar(select(UsageEvent))).output_tokens > 0


@pytest.mark.asyncio
async def test_vision_and_ocr_only_are_explicit(system):
    doc = await upload(system, "photo.png", make_image())
    await process(system)
    response = await chat(system, ids=[doc["id"]])
    assert frames(response)[0][1]["document_warnings"] == ["OCR_ONLY"]
    async with system.factory() as db:
        from app.db.models import ModelProfile

        model = await db.get(ModelProfile, system.model.id)
        model.config_json = {"supports_vision": True, "context_window_tokens": 65536}
        await db.commit()
    response = await chat(system, ids=[doc["id"]])
    metadata = frames(response)[0][1]
    assert metadata["sources"][0]["source_kind"] == "vision"
    assert len(system.provider.calls[-1][0][-1].images) == 1
    assert metadata["document_warnings"] == []


@pytest.mark.asyncio
async def test_pdf_page_limit_and_malformed_parser_failure_do_not_break_chat(system):
    system.settings.document_pdf_pages = 1
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.new_page()
    doc = await upload(system, "too-many.pdf", pdf.tobytes())
    pdf.close()
    item = await claim_document(system.factory, system.settings)
    await process_document(item, system.factory, system.settings)
    metadata = (await system.client.get(f"/api/v1/documents/{doc['id']}")).json()
    assert metadata["status"] == "failed" and "1" in metadata["error"]
    assert (await chat(system)).status_code == 200


@pytest.mark.asyncio
async def test_context_budget_failure_is_not_misreported_as_no_document_evidence(system):
    doc = await upload(system)
    await process(system)
    system.settings.rag_context_tokens = 1
    response = await chat(system, ids=[doc["id"]])
    assert response.status_code == 422
    assert "context budget" in response.text
    assert not system.provider.calls
