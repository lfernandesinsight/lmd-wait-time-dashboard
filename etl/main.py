"""
main.py
Orquestra o pipeline: extract -> transform -> load.

Uso:
    python main.py
    python main.py --xlsx-path ./data/outra_planilha.xlsx --sheet-name "Página1"
"""

import argparse
import logging
import os

from dotenv import load_dotenv

from extract import extract_local_xlsx
from load import get_engine, load
from transform import transform

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="ETL do dashboard LMD.")
    parser.add_argument(
        "--xlsx-path",
        default=os.environ.get("XLSX_PATH", "./data/Cidadania_espanhola_SP.xlsx"),
        help="Caminho para o arquivo xlsx local.",
    )
    parser.add_argument(
        "--sheet-name",
        default=os.environ.get("XLSX_SHEET_NAME", "Citas Marcadas"),
        help="Nome ou índice da aba a ser lida (padrão: primeira aba).",
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

    raw_df = extract_local_xlsx(args.xlsx_path, sheet_name=args.sheet_name)
    clean_df = transform(raw_df)

    if args.dry_run:
        logger.info("Modo --dry-run: exibindo amostra, nada será gravado no banco.")
        with __import__("pandas").option_context("display.max_columns", None, "display.width", 200):
            print(clean_df.head(15))
        print(f"\nTotal de linhas tratadas: {len(clean_df)}")
        print(f"Situações encontradas:\n{clean_df['situacao'].value_counts()}")
        return

    engine = get_engine()
    load(clean_df, engine)
    logger.info("Pipeline concluído com sucesso.")


if __name__ == "__main__":
    main()
