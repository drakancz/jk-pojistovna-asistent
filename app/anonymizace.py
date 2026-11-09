"""Osobní údaje mimo AI (krok 5B).

Než asistent pošle Claudovi otázku a úryvky dokumentů, nahradí v nich
e-mailové adresy za `[e-mail]` a telefonní čísla za `[telefon]`.
Dokumenty JK pojišťovny jsou vymyšlené, ale přepisy hlášení škody kontakty
obsahují a otázku může člověk napsat i s cizím číslem — model je
k odpovědi nepotřebuje.

**Vědomá výjimka:** OCR a vytěžení hlášení (`app.ocr`, `app.vytezeni`)
kontakty posílají, protože je mají z hlášení přečíst. Sken vidí model
celý už při OCR, nahrazení v přepisu by nic neschovalo.

Telefon = české číslo s devíti číslicemi (3-3-3, s mezerami, pomlčkami
nebo bez), volitelně s předvolbou +420 / 00420. Schválně se nenahrazuje:
číslo, které začíná 0, 1 nebo 8 (částky jako 100 000 000, linky 800),
číslo s lomítkem (účet, rodné číslo), část delšího čísla a číslo
následované měnou (200 000 000 Kč).
"""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TELEFON = re.compile(
    r"(?<![\w/+])(?<!\d )"  # ne uprostřed slova, čísla ani za lomítkem
    r"(?:(?:\+|00)\s?420[\s-]?)?"  # volitelná předvolba
    r"[2-79]\d{2}[\s-]?\d{3}[\s-]?\d{3}"  # 9 číslic, první 2–7 nebo 9
    r"(?![\w/])(?!\s?\d)(?!\s?(?:Kč|CZK|EUR|€|,-))"  # ne delší číslo ani částka
)


def bez_osobnich_udaju(text: str) -> str:
    """Text bez e-mailů a telefonních čísel (nahrazené zástupným textem)."""
    return TELEFON.sub("[telefon]", EMAIL.sub("[e-mail]", text))
