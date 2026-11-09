"""Stáhne vyhledávací model do obrazu (běží jen při `docker build`).

Model: minishlab/potion-multilingual-128M (model2vec, licence MIT) —
„otisk významu“ textu bez PyTorche: tokenizér + tabulka 500 353 × 256
čísel, otisk textu je průměr řádků jeho tokenů. Verze je zafixovaná na
commit. Uloží se:

- `tokenizer.json` beze změny,
- `vektory.npy` — tabulka zmenšená na float16 (256 MB místo 512 MB);
  aplikace ji čte přímo z disku (memmap), v paměti jsou jen použité řádky,
- `nastaveni.json` — rozměr, id neznámého tokenu, nejvýš tokenů.

Převod textu na otisk je v app/hledani.py (dělá totéž co knihovna
model2vec; ta by si v paměti vzala o 900 MB víc). Za běhu se nic
nestahuje.

Při změně modelu: nový commit sem, `DIMENZE` v app/hledani.py a migrace
sloupce `uryvky.vektor`.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from huggingface_hub import snapshot_download
from safetensors.numpy import load_file

MODEL = "minishlab/potion-multilingual-128M"
REVIZE = "73908c3438cf03b6a01bcb9611d62b23d0726f08"  # ověřeno 4. 11. 2026

cil = Path(sys.argv[1])
docasne = Path(tempfile.mkdtemp())
try:
    snapshot_download(
        MODEL,
        revision=REVIZE,
        local_dir=docasne,
        allow_patterns=["config.json", "tokenizer.json", "model.safetensors"],
    )
    config = json.loads((docasne / "config.json").read_text(encoding="utf-8"))
    tokenizer = json.loads((docasne / "tokenizer.json").read_text(encoding="utf-8"))
    vektory = load_file(docasne / "model.safetensors")["embeddings"]

    pocet_tokenu = len(tokenizer["model"]["vocab"])
    if vektory.shape[0] != pocet_tokenu or not config.get("normalize"):
        sys.exit("Model nesedí s tokenizérem nebo nenormalizuje — zkontroluj převod v app/hledani.py.")

    cil.mkdir(parents=True, exist_ok=True)
    np.save(cil / "vektory.npy", vektory.astype(np.float16))
    shutil.copy(docasne / "tokenizer.json", cil / "tokenizer.json")
    (cil / "nastaveni.json").write_text(
        json.dumps(
            {
                "model": MODEL,
                "revize": REVIZE,
                "rozmer": int(vektory.shape[1]),
                "neznamy_token": tokenizer["model"]["unk_id"],
                "max_tokenu": config.get("max_length") or 512,
            }
        ),
        encoding="utf-8",
    )
    print(f"Model uložen do {cil}: {vektory.shape[0]} tokenů × {vektory.shape[1]}.")
finally:
    shutil.rmtree(docasne, ignore_errors=True)
