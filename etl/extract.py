"""
extract.py
Responsável por obter a planilha "bruta" (local ou direto do Google Sheets)
e devolver um DataFrame, sem nenhuma limpeza ainda. A única responsabilidade
aqui é achar corretamente a linha de cabeçalho e ler os dados — a planilha
tem uma linha em branco antes do header e uma coluna oculta (M) no meio,
então não dá pra confiar em posições fixas de linha.
"""

import json
import logging
import os
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# Palavra-chave que identifica com segurança a linha de cabeçalho real,
# mesmo que a planilha ganhe/perca linhas em branco no topo no futuro.
HEADER_KEYWORD = "Situação"

GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


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

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=str)
    header_row_idx = _find_header_row(raw)
    logger.info("Header localizado na linha %d (0-indexed)", header_row_idx)

    df = pd.read_excel(path, sheet_name=sheet_name, header=header_row_idx)

    logger.info("Extraídas %d linhas brutas (antes da limpeza).", len(df))
    return df


def _get_gspread_client() -> gspread.Client:
    """
    Autentica na Google Sheets API usando uma service account.
    A credencial vem da variável de ambiente GOOGLE_SHEETS_CREDENTIALS,
    que deve conter o JSON inteiro da chave (não um caminho de arquivo).
    """
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        raise EnvironmentError(
            "Variável de ambiente GOOGLE_SHEETS_CREDENTIALS não encontrada. "
            "Ela deve conter o conteúdo do JSON da service account "
            "(configure como secret no GitHub Actions ou export local para testes)."
        )

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SHEETS_SCOPES)
    return gspread.authorize(creds)


def extract_google_sheets(sheet_id: str, gid: str) -> pd.DataFrame:
    """
    Lê a planilha via Google Sheets API, autenticado com uma service account
    (substitui o antigo link público de export CSV, que passou a ser
    bloqueado pela política de compartilhamento do Workspace).
    A planilha precisa estar compartilhada com o e-mail da service account.
    """
    logger.info("Autenticando com a Google Sheets API (service account)...")
    client = _get_gspread_client()

    logger.info("Abrindo planilha (sheet_id=%s, gid=%s)...", sheet_id, gid)
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = next(ws for ws in spreadsheet.worksheets() if ws.id == int(gid))
    except StopIteration:
        abas_disponiveis = [(ws.title, ws.id) for ws in spreadsheet.worksheets()]
        raise ValueError(
            f"Não encontrei nenhuma aba com gid={gid} na planilha {sheet_id}. "
            f"Abas disponíveis: {abas_disponiveis}"
        ) from None

    values = worksheet.get_all_values()
    if not values:
        raise ValueError("A aba retornou vazia — verifique se a planilha tem dados.")

    raw = pd.DataFrame(values, dtype=str)

    try:
        header_row_idx = _find_header_row(raw)
    except ValueError:
        preview = values[:5]
        raise ValueError(
            f"Não encontrei a linha de cabeçalho na planilha do Google Sheets. "
            f"Prévia das primeiras linhas recebidas: {preview!r}"
        ) from None

    logger.info("Header localizado na linha %d (0-indexed)", header_row_idx)

    header = raw.iloc[header_row_idx]
    df = raw.iloc[header_row_idx + 1:].reset_index(drop=True)
    df.columns = header

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