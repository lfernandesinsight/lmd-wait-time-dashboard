"""
load.py
Grava o DataFrame tratado no Postgres via UPSERT (ON CONFLICT DO UPDATE),
usando row_hash como chave natural. Isso permite rodar o pipeline várias
vezes (planilha atualizada) sem duplicar registros.

Também implementa soft delete: linhas que existiam numa carga anterior mas
não aparecem mais na planilha atual são marcadas com removido_em = now(),
em vez de apagadas — preserva histórico e evita perda silenciosa de dado.
Se uma linha "removida" reaparecer depois, ela é reativada automaticamente
(removido_em volta a NULL) pelo próprio upsert.
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
        notas, fonte, atualizado_em, removido_em
    ) VALUES (
        :row_hash, :nome, :numero_protocolo,
        :data_solicitacao, :hora_solicitacao,
        :consulado_origem, :consulado_processamento,
        :categoria_anexo, :parentesco,
        :previsao_informada, :situacao, :situacao_raw,
        :retencao_parcial_docs, :data_entrega_docs_finais, :data_conclusao,
        :espera_dias_planilha, :espera_dias_calculado, :em_aberto,
        :notas, :fonte, now(), NULL
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
        atualizado_em = now(),
        removido_em = NULL;
""")

CREATE_TEMP_BATCH_SQL = text("""
    CREATE TEMP TABLE current_batch (row_hash VARCHAR(64) PRIMARY KEY) ON COMMIT DROP;
""")

INSERT_TEMP_BATCH_SQL = text("""
    INSERT INTO current_batch (row_hash) VALUES (:row_hash) ON CONFLICT DO NOTHING;
""")

SOFT_DELETE_SQL = text("""
    UPDATE expedientes
    SET removido_em = now()
    WHERE removido_em IS NULL
      AND row_hash NOT IN (SELECT row_hash FROM current_batch);
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
    """Converte NaN/NaT/NA do pandas para None (o driver do Postgres não entende NaT)."""
    return {k: (None if pd.isna(v) else v) for k, v in record.items()}


def load(df: pd.DataFrame, engine: Engine, fonte: str = "local_xlsx") -> None:
    if df.empty:
        logger.warning("DataFrame vazio — nada para carregar (e nada será marcado como removido, por segurança).")
        return

    records = [_clean_record(r) for r in df.to_dict(orient="records")]
    for r in records:
        r["fonte"] = fonte

    hash_params = [{"row_hash": r["row_hash"]} for r in records]

    with engine.begin() as conn:
        logger.info("Fazendo upsert de %d registros...", len(records))
        conn.execute(UPSERT_SQL, records)

        logger.info("Verificando registros removidos da planilha (soft delete)...")
        conn.execute(CREATE_TEMP_BATCH_SQL)
        conn.execute(INSERT_TEMP_BATCH_SQL, hash_params)
        result = conn.execute(SOFT_DELETE_SQL)
        logger.info("%d registros marcados como removidos (não estavam mais na planilha).", result.rowcount)

    logger.info("Upsert concluído.")
