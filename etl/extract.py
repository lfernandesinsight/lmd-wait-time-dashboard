"""
extract.py
Responsável por ler a planilha local (.xlsx) e devolver um DataFrame "bruto",
sem nenhuma limpeza ainda. A única responsabilidade aqui é achar corretamente
a linha de cabeçalho e ler os dados — a planilha tem uma linha em branco antes
do header e uma coluna oculta (M) no meio, então não dá pra confiar em
posições fixas de linha.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Palavra-chave que identifica com segurança a linha de cabeçalho real,
# mesmo que a planilha ganhe/perca linhas em branco no topo no futuro.
HEADER_KEYWORD = "Situação"


def _find_header_row(raw: pd.DataFrame, keyword: str = HEADER_KEYWORD, max_scan_rows: int = 10) -> int:
    """Varre as primeiras linhas procurando a linha que contém o keyword do header."""
    scan_limit = min(max_scan_rows, len(raw))
    for i in range(scan_limit):
        row_values = raw.iloc[i].astype(str).str.strip()
        if row_values.str.contains(keyword, case=False, na=False).any():
            return i
    raise ValueError(
        f"Não encontrei a linha de cabeçalho (procurando por '{keyword}') "
        f"nas primeiras {scan_limit} linhas. A estrutura da planilha pode ter mudado."
    )


def extract_local_xlsx(xlsx_path: str, sheet_name=0) -> pd.DataFrame:
    """
    Lê o xlsx local sem assumir onde o header está.
    Retorna um DataFrame bruto, com o header já aplicado, mas SEM nenhuma
    limpeza de linhas/valores (isso é responsabilidade do transform.py).
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path.resolve()}")

    logger.info("Lendo %s (sheet=%s)...", path, sheet_name)

    # Primeira leitura sem header, só para localizar a linha correta
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=str)
    header_row_idx = _find_header_row(raw)
    logger.info("Header localizado na linha %d (0-indexed)", header_row_idx)

    # Releitura já usando o header correto
    df = pd.read_excel(path, sheet_name=sheet_name, header=header_row_idx)

    logger.info("Extraídas %d linhas brutas (antes da limpeza).", len(df))
    return df


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "./data/Cidadania_espanhola_SP.xlsx"
    df = extract_local_xlsx(xlsx_path)
    print(df.head(10))
    print(f"\nColunas encontradas: {list(df.columns)}")
