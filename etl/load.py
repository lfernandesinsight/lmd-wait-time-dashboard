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

Usa psycopg2.extras.execute_values para enviar todas as linhas em um único
lote (uma viagem de rede), em vez de uma instrução por linha — importante
para bancos remotos (Neon), onde a latência de rede domina o tempo total
quando cada linha é uma round-trip separada.
"""

import logging
import os

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Ordem das colunas "de dados" do upsert — precisa bater exatamente com a
# ordem dos valores em _record_to_tuple().
COLUMNS = [
    "row_hash", "nome", "numero_protocolo",
    "data_solicitacao", "hora_solicitacao",
    "consulado_origem", "consulado_processamento",
    "categoria_anexo", "parentesco",
    "previsao_informada", "situacao", "situacao_raw",
    "retencao_parcial_docs", "data_entrega_docs_finais", "data_conclusao",
    "espera_dias_planilha", "espera_dias_calculado", "em_aberto",
    "notas", "fonte",
]

UPSERT_SQL_TEMPLATE = f"""
    INSERT INTO expedientes ({", ".join(COLUMNS)}, atualizado_em, removido_em)
    VALUES %s
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
"""
# Template de cada linha do VALUES: um %s por coluna de dado, mais now()/NULL
# fixos para atualizado_em/removido_em (não fazem parte dos dados da linha).
UPSERT_ROW_TEMPLATE = "(" + ",".join(["%s"] * len(COLUMNS)) + ", now(), NULL)"

CREATE_TEMP_BATCH_SQL = "CREATE TEMP TABLE current_batch (row_hash VARCHAR(64) PRIMARY KEY) ON COMMIT DROP;"

INSERT_TEMP_BATCH_SQL = "INSERT INTO current_batch (row_hash) VALUES %s ON CONFLICT DO NOTHING;"

SOFT_DELETE_SQL = """
    UPDATE expedientes
    SET removido_em = now()
    WHERE removido_em IS NULL
      AND row_hash NOT IN (SELECT row_hash FROM current_batch);
"""


def get_engine() -> Engine:
    # Prioriza DATABASE_URL (usado no GitHub Actions / Neon) — connection
    # string única, mais simples de gerenciar como secret do que 4 variáveis.
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Neon (e a maioria dos Postgres gerenciados) exige SSL.
        if "sslmode" not in database_url:
            separator = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{separator}sslmode=require"
        return create_engine(database_url)

    user = os.environ.get("POSTGRES_USER", "lmd_user")
    password = os.environ.get("POSTGRES_PASSWORD", "lmd_pass")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lmd_dashboard")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def _clean_value(v):
    """Converte NaN/NaT/NA do pandas para None (o driver do Postgres não entende NaT)."""
    return None if pd.isna(v) else v


def _record_to_tuple(record: dict) -> tuple:
    """Converte um registro (dict) em tupla, na mesma ordem de COLUMNS."""
    return tuple(_clean_value(record.get(col)) for col in COLUMNS)


def load(df: pd.DataFrame, engine: Engine, fonte: str = "local_xlsx") -> None:
    if df.empty:
        logger.warning("DataFrame vazio — nada para carregar (e nada será marcado como removido, por segurança).")
        return

    records = df.to_dict(orient="records")
    for r in records:
        r["fonte"] = fonte

    # Um único INSERT em lote não pode ter o mesmo row_hash duas vezes
    # (Postgres rejeita "ON CONFLICT DO UPDATE" duplicado na mesma instrução).
    # A planilha tem algumas linhas replicadas com hash idêntico — mantemos
    # a última ocorrência de cada uma, igual ao comportamento anterior
    # (que processava uma instrução por linha, em ordem).
    deduped = {r["row_hash"]: r for r in records}
    if len(deduped) < len(records):
        logger.warning(
            "%d registros com row_hash duplicado dentro do próprio lote — mantendo a última ocorrência de cada.",
            len(records) - len(deduped),
        )
    records = list(deduped.values())

    rows = [_record_to_tuple(r) for r in records]
    hash_rows = [(r["row_hash"],) for r in records]

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()

        logger.info("Fazendo upsert em lote de %d registros...", len(rows))
        execute_values(cur, UPSERT_SQL_TEMPLATE, rows, template=UPSERT_ROW_TEMPLATE, page_size=1000)

        logger.info("Verificando registros removidos da planilha (soft delete)...")
        cur.execute(CREATE_TEMP_BATCH_SQL)
        execute_values(cur, INSERT_TEMP_BATCH_SQL, hash_rows, page_size=1000)
        cur.execute(SOFT_DELETE_SQL)
        logger.info("%d registros marcados como removidos (não estavam mais na planilha).", cur.rowcount)

        raw_conn.commit()
        cur.close()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()

    logger.info("Upsert concluído.")
