"""
load.py
Grava o DataFrame tratado no Postgres via UPSERT (ON CONFLICT DO UPDATE),
usando row_hash como chave natural. Isso permite rodar o pipeline várias
vezes (planilha atualizada) sem duplicar registros.
"""

import logging
import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

UPSERT_SQL = text("""
    INSERT INTO expedientes (
        row_hash, nome, numero_protocolo,
        data_solicitacao, hora_solicitacao,
        consulado_origem, consulado_processamento,
        categoria_anexo, parentesco,
        previsao_informada, situacao, situacao_raw,
        retencao_parcial_docs, data_entrega_docs_finais, data_conclusao,
        espera_dias_planilha, espera_dias_calculado, em_aberto,
        notas, fonte, atualizado_em
    ) VALUES (
        :row_hash, :nome, :numero_protocolo,
        :data_solicitacao, :hora_solicitacao,
        :consulado_origem, :consulado_processamento,
        :categoria_anexo, :parentesco,
        :previsao_informada, :situacao, :situacao_raw,
        :retencao_parcial_docs, :data_entrega_docs_finais, :data_conclusao,
        :espera_dias_planilha, :espera_dias_calculado, :em_aberto,
        :notas, :fonte, now()
    )
    ON CONFLICT (row_hash) DO UPDATE SET
        situacao = EXCLUDED.situacao,
        situacao_raw = EXCLUDED.situacao_raw,
        data_conclusao = EXCLUDED.data_conclusao,
        data_entrega_docs_finais = EXCLUDED.data_entrega_docs_finais,
        espera_dias_planilha = EXCLUDED.espera_dias_planilha,
        espera_dias_calculado = EXCLUDED.espera_dias_calculado,
        em_aberto = EXCLUDED.em_aberto,
        notas = EXCLUDED.notas,
        atualizado_em = now();
""")


def get_engine() -> Engine:
    user = os.environ.get("POSTGRES_USER", "lmd_user")
    password = os.environ.get("POSTGRES_PASSWORD", "lmd_pass")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lmd_dashboard")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def _clean_record(record: dict) -> dict:
    """Converte NaN/NaT/NaT do pandas para None (o driver do Postgres não entende NaT)."""
    return {k: (None if pd.isna(v) else v) for k, v in record.items()}


def load(df: pd.DataFrame, engine: Engine, fonte: str = "local_xlsx") -> None:
    if df.empty:
        logger.warning("DataFrame vazio — nada para carregar.")
        return

    records = [_clean_record(r) for r in df.to_dict(orient="records")]
    for r in records:
        r["fonte"] = fonte

    logger.info("Fazendo upsert de %d registros...", len(records))
    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, records)
    logger.info("Upsert concluído.")
