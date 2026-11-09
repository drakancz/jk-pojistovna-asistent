"""Napodobenina Anthropic API pro testy (nic neodchází ven, nic nestojí).

Běží jen v testovacím profilu Dockeru (`compose.yaml`, služba
`napodobenina`). Testovací server na ni míří přes ANTHROPIC_BASE_URL.

    POST /v1/messages     přepis stránky (OCR), nebo odpověď asistenta:
                          s bloky search_result cituje první z nich;
                          otázka s „kurz eura“ → „nevím“ bez citace,
                          s „podvrh“ → citace na úryvek, který nepřišel;
                          s output_config.format (vytěžení hlášení, krok 4B)
                          → správné údaje prvního ukázkového hlášení (1001)
    POST /v1/messages/batches, GET …/{id}, GET …/{id}/results
                          hromadná dávka (evaluace, krok 5A): hned hotová,
                          odpovědi jako u /v1/messages
    POST /_rezim          {"chyba": true} → další dotazy vrací chybu 400
    GET  /_posledni       co přišlo naposledy (model, druhy bloků, názvy
                          úryvků, jestli v tom byl e-mail či telefon)
                          — bez textu dokumentů
"""

import json
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Kontakt v přepisu hlídá krok 5B: z úryvků hlášení nesmí k asistentovi odejít.
PREPIS = (
    "HLÁŠENÍ ŠKODY\nPřepis napodobeniny OCR\nDatum škody: 12. 10. 2026\n"
    "Kontakt: +420 600 000 001, petra.mala@example.com"
)
# Stejné vzory jako app/anonymizace.py, jen volnější (radši poplach navíc).
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TELEFON = re.compile(r"(?:\+|00)?\s?(?:420[\s-]?)?[2-79]\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\s?Kč)")


def _texty(obsah: list[dict]) -> list[str]:
    """Všechen text, který přišel: úryvky, jejich názvy i otázka."""
    texty = []
    for b in obsah:
        if b["type"] == "text":
            texty.append(b["text"])
        elif b["type"] == "search_result":
            texty.append(b.get("title", ""))
            texty.extend(c.get("text", "") for c in b.get("content", []))
    return texty
stav: dict = {"chyba": False, "posledni": None, "pocet": 0, "vytezeni": None, "pocet_vytezeni": 0}
# Vytěžení vrací údaje hlášení 11-hlaseni-1001-auto.png (dokumenty/hlaseni.json).
UKAZKOVA = Path(__file__).resolve().parents[1] / "dokumenty" / "hlaseni.json"
VYTEZENE = json.loads(UKAZKOVA.read_text(encoding="utf-8"))[0]["spravne_udaje"]


def _odpoved_asistenta(vysledky: list[dict], otazka: str) -> list[dict]:
    if "kurz eura" in otazka.lower():
        return [{"type": "text", "text": "Nevím – v dokumentech odpověď není."}]
    prvni = vysledky[0]
    text = prvni["content"][0]["text"]
    citace = {
        "type": "search_result_location",
        "cited_text": text,
        "source": "uryvek:999999999" if "podvrh" in otazka.lower() else prvni["source"],
        "title": prvni["title"],
        "search_result_index": 0,
        "start_block_index": 0,
        "end_block_index": 1,
    }
    return [
        {"type": "text", "text": "Podle dokumentů: "},
        {"type": "text", "text": "odpověď napodobeniny z prvního úryvku.", "citations": [citace]},
    ]


@app.post("/v1/messages")
async def zprava(request: Request):
    telo = await request.json()
    obsah = telo["messages"][0]["content"]
    vysledky = [b for b in obsah if b["type"] == "search_result"]
    zaznam = {
        "model": telo.get("model"),
        # SDK 2.x posílá klíč jako Authorization: Bearer, starší jako x-api-key.
        "klic": bool(request.headers.get("x-api-key"))
        or request.headers.get("authorization", "").startswith("Bearer "),
        "verze_api": request.headers.get("anthropic-version"),
        "bloky": [
            {"type": b["type"], "media_type": b.get("source", {}).get("media_type")
             if isinstance(b.get("source"), dict) else None}
            for b in obsah
        ],
        "pokyny": bool(telo.get("system")),
        "uryvky": [b["title"] for b in vysledky],
        "citace": all(b.get("citations", {}).get("enabled") for b in vysledky),
        # Vytěžení: přišlo schéma a přepis v <prepis>? (text dokumentu se neukládá)
        "schema": bool((telo.get("output_config") or {}).get("format", {}).get("schema")),
        "prepis": any(b["type"] == "text" and b["text"].startswith("<prepis>") for b in obsah),
        "thinking": telo.get("thinking"),
        # Krok 5B: přišel e-mail nebo telefon? A přišla náhrada? (jen ano/ne, text se neukládá)
        "osobni_udaje": any(EMAIL.search(t) or TELEFON.search(t) for t in _texty(obsah)),
        "nahrazeno": any("[e-mail]" in t or "[telefon]" in t for t in _texty(obsah)),
    }
    # Vytěžení běží na pozadí hned po OCR — má vlastní záznam, aby nepřepsalo
    # „posledni“, který kontrolují testy OCR a asistenta.
    if zaznam["schema"]:
        stav["pocet_vytezeni"] += 1
        stav["vytezeni"] = zaznam
    else:
        stav["pocet"] += 1
        stav["posledni"] = zaznam
    if stav["chyba"]:
        return JSONResponse(
            {"type": "error", "error": {"type": "invalid_request_error", "message": "napodobenina: chyba"}},
            status_code=400,
        )
    if zaznam["schema"]:
        content = [{"type": "text", "text": json.dumps(VYTEZENE, ensure_ascii=False)}]
    elif vysledky:
        otazka = next((b["text"] for b in reversed(obsah) if b["type"] == "text"), "")
        content = _odpoved_asistenta(vysledky, otazka)
    else:
        content = [{"type": "text", "text": PREPIS}]
    return {
        "id": f"msg_napodobenina_{stav['pocet'] + stav['pocet_vytezeni']}",
        "type": "message",
        "role": "assistant",
        "model": telo.get("model"),
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


# --- Hromadné dávky (Message Batches API, evaluace v kroku 5A) ---------------
# Dávka je hned „ended“; výsledky jsou odpovědi asistenta jako u /v1/messages.
davky: dict[str, list[dict]] = {}
CAS = "2026-11-08T12:00:00Z"


def _davka(id_: str, base: str) -> dict:
    return {
        "id": id_, "type": "message_batch", "processing_status": "ended",
        "request_counts": {"processing": 0, "succeeded": len(davky[id_]), "errored": 0, "canceled": 0, "expired": 0},
        "created_at": CAS, "ended_at": CAS, "expires_at": CAS, "cancel_initiated_at": None, "archived_at": None,
        "results_url": f"{base}v1/messages/batches/{id_}/results",
    }


@app.post("/v1/messages/batches")
async def nova_davka(request: Request):
    telo = await request.json()
    id_ = f"msgbatch_napodobenina_{len(davky) + 1}"
    vysledky = []
    for pozadavek in telo["requests"]:
        obsah = pozadavek["params"]["messages"][0]["content"]
        uryvky = [b for b in obsah if b["type"] == "search_result"]
        otazka = next((b["text"] for b in reversed(obsah) if b["type"] == "text"), "")
        vysledky.append({"custom_id": pozadavek["custom_id"], "result": {"type": "succeeded", "message": {
            "id": f"msg_davka_{len(vysledky)}", "type": "message", "role": "assistant",
            "model": pozadavek["params"].get("model"), "content": _odpoved_asistenta(uryvky, otazka),
            "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 20},
        }}})
    davky[id_] = vysledky
    # Jen ano/ne a počty, text se neukládá (stejně jako u /_posledni).
    stav["davka"] = {
        "pozadavku": len(telo["requests"]),
        "modely": sorted({p["params"].get("model") for p in telo["requests"]}),
        "citace": all(b.get("citations", {}).get("enabled") for p in telo["requests"]
                      for b in p["params"]["messages"][0]["content"] if b["type"] == "search_result"),
        "osobni_udaje": any(EMAIL.search(t) or TELEFON.search(t) for p in telo["requests"]
                            for t in _texty(p["params"]["messages"][0]["content"])),
    }
    return _davka(id_, str(request.base_url))


@app.get("/v1/messages/batches/{id_}")
def stav_davky(id_: str, request: Request):
    if id_ not in davky:
        return JSONResponse({"type": "error", "error": {"type": "not_found_error", "message": "neznámá dávka"}}, 404)
    return _davka(id_, str(request.base_url))


@app.get("/v1/messages/batches/{id_}/results")
def vysledky_davky(id_: str):
    radky = "\n".join(json.dumps(r, ensure_ascii=False) for r in davky.get(id_, []))
    return PlainTextResponse(radky + "\n", media_type="application/x-jsonl")


@app.post("/_rezim")
async def rezim(request: Request):
    stav["chyba"] = bool((await request.json()).get("chyba"))
    return {"chyba": stav["chyba"]}


@app.get("/_posledni")
def posledni():
    return {
        "posledni": stav["posledni"],
        "pocet": stav["pocet"],
        "vytezeni": stav["vytezeni"],
        "pocet_vytezeni": stav["pocet_vytezeni"],
        "davka": stav.get("davka"),
    }


@app.get("/zdravi")
def zdravi():
    return "ok"
