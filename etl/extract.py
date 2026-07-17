"""
extract.py
Responsável por obter a planilha "bruta" (local ou direto do Google Sheets)
e devolver um DataFrame, sem nenhuma limpeza ainda. A única responsabilidade
aqui é achar corretamente a linha de cabeçalho e ler os dados — a planilha
tem uma linha em branco antes do header e uma coluna oculta (M) no meio,
então não dá pra confiar em posições fixas de linha.
"""

import io
import logging
from pathlib import Path

import pandas as pd
import requests

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


def extract_google_sheets(sheet_id: str, gid: str) -> pd.DataFrame:
    """
    Baixa a planilha direto do Google Sheets via export CSV público (sem
    precisar de API key/OAuth, já que a planilha é pública). Usado no modo
    automático (GitHub Actions), onde não há um arquivo local disponível.

    Baixa o CSV uma única vez e faz as duas leituras (localizar header +
    ler de fato) em memória, para não duplicar a requisição de rede.
    """
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    logger.info("Baixando planilha do Google Sheets (sheet_id=%s, gid=%s)...", sheet_id, gid)

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # O Google nem sempre informa o charset no header HTTP, e sem isso o
    # `requests` pode assumir Latin-1 por padrão — o que corrompe acentos
    # (ex: "Situação" vira algo ilegível) e quebra a busca pelo header.
    # A exportação do Sheets é sempre UTF-8, então forçamos aqui.
    response.encoding = "utf-8"
    csv_text = response.text

    if "text/csv" not in response.headers.get("Content-Type", "") and "<html" in csv_text[:500].lower():
        raise ValueError(
            "A resposta do Google Sheets parece ser uma página HTML, não um CSV. "
            "Isso costuma acontecer quando a planilha não está compartilhada como "
            "'Qualquer pessoa com o link pode visualizar', ou o link/gid mudou. "
            f"Início da resposta recebida: {csv_text[:300]!r}"
        )

    raw = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str)

    try:
        header_row_idx = _find_header_row(raw)
    except ValueError:
        preview = csv_text[:500]
        raise ValueError(
            f"Não encontrei a linha de cabeçalho no CSV baixado do Google Sheets. "
            f"Prévia do conteúdo recebido (primeiros 500 caracteres):\n{preview!r}"
        ) from None

    logger.info("Header localizado na linha %d (0-indexed)", header_row_idx)

    df = pd.read_csv(io.StringIO(csv_text), header=header_row_idx)

    logger.info("Extraídas %d linhas brutas (antes da limpeza).", len(df))
    return df


def extract(source: str, xlsx_path: str = None, sheet_name=0,
            google_sheet_id: str = None, google_sheet_gid: str = None) -> pd.DataFrame:
    """Ponto de entrada único: escolhe local ou Google Sheets conforme `source`."""
    if source == "local":
        return extract_local_xlsx(xlsx_path, sheet_name=sheet_name)
    elif source == "sheets":
        if not google_sheet_id or not google_sheet_gid:
            raise ValueError("source='sheets' requer google_sheet_id e google_sheet_gid.")
        return extract_google_sheets(google_sheet_id, google_sheet_gid)
    else:
        raise ValueError(f"source inválido: '{source}' (use 'local' ou 'sheets')")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "./data/Cidadania_espanhola_SP.xlsx"
    df = extract_local_xlsx(xlsx_path)
    print(df.head(10))
    print(f"\nColunas encontradas: {list(df.columns)}")
