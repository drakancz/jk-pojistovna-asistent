"""Asistent nad dokumenty — JK pojišťovna (vymyšlená firma, ukázka do portfolia)."""

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import cteni, hledani, ukazka, vytezeni
from app.nastaveni import nastaveni
from app.opravneni import Neprihlasen
from app.routy import asistent as asistent_routy
from app.routy import dokumenty, hledani as hledani_routy, hlaseni, prehled, prihlaseni
from app.sablony import stranka


@asynccontextmanager
async def zivot(_: FastAPI):
    # Dočíst dokumenty, které zůstaly rozečtené po restartu serveru.
    cteni.naplanuj_cekajici()
    # Totéž pro vytěžení údajů z hlášení škody (krok 4B).
    vytezeni.naplanuj_cekajici()
    # Načíst vyhledávací model a doplnit otisky starším úryvkům (na pozadí).
    cteni.na_pozadi(hledani.priprav)
    yield


app = FastAPI(
    title="Asistent nad dokumenty",
    lifespan=zivot,
    # Dokumentace API se ven neukazuje — prozrazovala by adresy.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
)
BEZPECNE_METODY = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def zabezpeceni(request: Request, call_next):
    # 1) Velikost požadavku: nic většího než soubor + rezerva na formulář.
    delka = request.headers.get("content-length")
    limit = (nastaveni().max_upload_mb + 1) * 1024 * 1024
    if delka is not None and (not delka.isdigit() or int(delka) > limit):
        return PlainTextResponse("Soubor je příliš velký.", status_code=413)

    # 2) Odeslání formuláře jen z naší stránky: Origin musí sedět s adresou.
    #    Porovnává se jen server (host), schéma za proxy Railway nesedí.
    if request.method not in BEZPECNE_METODY:
        puvod = request.headers.get("origin")
        if not puvod or urlsplit(puvod).netloc != request.headers.get("host"):
            return PlainTextResponse("Požadavek odmítnut.", status_code=403)

    # 3) Živá ukázka: první požadavek nového dne vrátí data do výchozího stavu
    #    (jednou za den, app/ukazka.py). Hlavička jen pro testy.
    if ukazka.je_ukazka() and request.url.path != "/zdravi":
        vynutit = nastaveni().ukazka_test_obnova and request.headers.get("x-obnova-ukazky") == "1"
        await run_in_threadpool(ukazka.obnov_pokud_je_treba, vynutit)

    odpoved = await call_next(request)
    # Vlastní politiku smí mít jen sken hlášení (zobrazení PDF a obrázku).
    odpoved.headers.setdefault("Content-Security-Policy", CSP)
    odpoved.headers["X-Content-Type-Options"] = "nosniff"
    odpoved.headers["Referrer-Policy"] = "same-origin"
    odpoved.headers["X-Frame-Options"] = "DENY"
    odpoved.headers.setdefault("Cache-Control", "no-store")
    return odpoved


@app.exception_handler(Neprihlasen)
async def na_prihlaseni(request: Request, _: Neprihlasen):
    return RedirectResponse("/prihlaseni", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def chyba(request: Request, exc: HTTPException):
    if exc.status_code == 404:
        return stranka(request, "404.html", status_code=404)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def nesmyslny_pozadavek(request: Request, _: RequestValidationError):
    # Nesmyslná adresa (např. /dokumenty/abc/smazat) = neexistuje.
    return stranka(request, "404.html", status_code=404)


@app.get("/zdravi", include_in_schema=False)
def zdravi() -> PlainTextResponse:
    """Pro kontrolu, že server běží (Docker, Railway). Nic neprozrazuje."""
    return PlainTextResponse("ok")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(prihlaseni.router)
app.include_router(prehled.router)
app.include_router(dokumenty.router)
app.include_router(hledani_routy.router)
app.include_router(asistent_routy.router)
app.include_router(hlaseni.router)
