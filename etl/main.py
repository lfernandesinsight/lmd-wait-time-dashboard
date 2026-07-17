"""
main.py
Orquestra o pipeline: extract -> transform -> load.

Uso:
    python main.py                                          # modo local (padrão)
    python main.py --xlsx-path ./data/outra.xlsx --sheet-name "Página1"
    python main.py --source sheets                          # lê direto do Google Sheets
                                                              # (usado no GitHub Actions)
"""

import argparse
import logging
import os

from dotenv import load_dotenv

from extract import extract
from load import get_engine, load
from transform import transform

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ID e gid da planilha pública "Cidadania espanhola SP" — não são segredos
# (a planilha é pública), por isso podem ficar como default aqui em vez de
# exigir configuração extra no modo --source sheets.
DEFAULT_GOOGLE_SHEET_ID = "13_UGPGJtPE1PY1K9XBWowMdmXQ_Jzyp1G9d1Dsqb5JA"
DEFAULT_GOOGLE_SHEET_GID = "1469616312"


def parse_args():
    parser = argparse.ArgumentParser(description="ETL do dashboard LMD.")
    parser.add_argument(
        "--source",
        choices=["local", "sheets"],
        default=os.environ.get("SOURCE", "local"),
        help="'local' lê o xlsx em disco; 'sheets' baixa direto do Google Sheets público.",
    )
    parser.add_argument(
        "--xlsx-path",
        default=os.environ.get("XLSX_PATH", "./data/Cidadania_espanhola_SP.xlsx"),
        help="Caminho para o arquivo xlsx local (usado com --source local).",
    )
    parser.add_argument(
        "--sheet-name",
        default=os.environ.get("XLSX_SHEET_NAME", "Citas Marcadas"),
        help="Nome ou índice da aba a ser lida no xlsx local.",
    )
    parser.add_argument(
        "--google-sheet-id",
        default=os.environ.get("GOOGLE_SHEET_ID", DEFAULT_GOOGLE_SHEET_ID),
        help="ID da planilha do Google Sheets (usado com --source sheets).",
    )
    parser.add_argument(
        "--google-sheet-gid",
        default=os.environ.get("GOOGLE_SHEET_GID", DEFAULT_GOOGLE_SHEET_GID),
        help="gid (aba) da planilha do Google Sheets (usado com --source sheets).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roda extract + transform e mostra o resultado, sem gravar no Postgres.",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    raw_df = extract(
        source=args.source,
        xlsx_path=args.xlsx_path,
        sheet_name=args.sheet_name,
        google_sheet_id=args.google_sheet_id,
        google_sheet_gid=args.google_sheet_gid,
    )
    clean_df = transform(raw_df)

    if args.dry_run:
        logger.info("Modo --dry-run: exibindo amostra, nada será gravado no banco.")
        with __import__("pandas").option_context("display.max_columns", None, "display.width", 200):
            print(clean_df.head(15))
        print(f"\nTotal de linhas tratadas: {len(clean_df)}")
        print(f"Situações encontradas:\n{clean_df['situacao'].value_counts()}")
        return

    engine = get_engine()
    load(clean_df, engine, fonte=args.source)
    logger.info("Pipeline concluído com sucesso.")


if __name__ == "__main__":
    main()
