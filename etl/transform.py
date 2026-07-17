"""
transform.py
Limpeza e normalização da planilha "Cidadania espanhola SP".

Particularidades reais desta planilha que o transform precisa tratar:
  1. Linhas separadoras de mês (ex: "dezembro 22" | 17) sem data de solicitação.
  2. Linhas "lixo" residuais (nome ".", sem quase nenhum dado) com valores de
     data quebrados (bug do epoch do Excel: 30/12/1899).
  3. Coluna "Espera (dias)" vem como número puro quando concluído, mas como
     "1326 passados" quando ainda em aberto — e esse valor fica desatualizado
     toda vez que a planilha não é reaberta, então recalculamos por conta própria.
  4. Coluna "Consulado" às vezes guarda o trâmite todo, ex: "RJ->SP", "Lisboa -> SP".
  5. Cabeçalhos vêm com quebras de linha / texto extra (ex: "Número protocolo
     (ajuda bastante!)"), então mapeamos colunas por palavra-chave, não por nome exato.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, time

import pandas as pd

logger = logging.getLogger(__name__)

# (palavra-chave a procurar no header original, nome final da coluna)
COLUMN_KEYWORDS = [
    ("nome", "nome"),
    ("protocolo", "numero_protocolo"),
    ("dia", "data_solicitacao_raw"),
    ("hora", "hora_raw"),
    ("consulado", "consulado_raw"),
    ("anexo", "categoria_anexo_raw"),
    ("parentesco", "parentesco"),
    ("previsão de conclusão", "previsao_informada"),
    ("situação", "situacao_raw"),
    ("retenção parcial", "retencao_parcial_raw"),
    ("data entrega docs", "data_entrega_docs_raw"),
    ("data conclusão", "data_conclusao_raw"),
    ("espera (dias)", "espera_dias_raw"),
    ("notas", "notas"),
]


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia colunas por palavra-chave (case-insensitive), ignora o resto."""
    rename_map = {}
    normalized_cols = {col: str(col).replace("\n", " ").strip().lower() for col in df.columns}

    for keyword, final_name in COLUMN_KEYWORDS:
        match = next(
            (orig for orig, norm in normalized_cols.items() if keyword in norm),
            None,
        )
        if match is not None:
            rename_map[match] = final_name
        else:
            logger.warning("Coluna com palavra-chave '%s' não encontrada na planilha.", keyword)

    df = df.rename(columns=rename_map)
    keep_cols = [v for _, v in COLUMN_KEYWORDS if v in df.columns]
    return df[keep_cols].copy()


def _parse_br_date(series: pd.Series) -> pd.Series:
    """
    Parseia datas. A coluna pode vir como datetime nativo (quando o Excel já
    armazenou a célula como data) ou como string "DD/MM/YYYY" (quando veio de
    CSV/entrada manual). Descarta também o bug de epoch do Excel (30/12/1899).
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = series.copy()
    else:
        parsed = pd.to_datetime(series, format="%d/%m/%Y", errors="coerce", dayfirst=True)
        still_null = parsed.isna() & series.notna()
        if still_null.any():
            parsed.loc[still_null] = pd.to_datetime(series[still_null], errors="coerce", dayfirst=True)

    parsed = pd.to_datetime(parsed, errors="coerce")
    parsed = parsed.mask(parsed.dt.date == date(1899, 12, 30))
    return parsed


_JUNK_HORA_VALUES = {"?", "-", "", "na", "n/a", "nan"}


def _parse_hora_value(val):
    """
    Coluna "Hora" foi digitada manualmente por várias pessoas ao longo dos anos,
    então aparece em formatos bem diferentes: time nativo do Excel, "10h00",
    "10;30", "10.30", "1030" (int sem separador), "?", "-", etc.
    Melhor esforço: se não der para interpretar com segurança, retorna None
    em vez de arriscar um horário errado.
    """
    if val is None:
        return None
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    if isinstance(val, float) and pd.isna(val):
        return None

    if isinstance(val, (int, float)):
        digits = str(int(val))
        if len(digits) == 3:
            h, m = int(digits[0]), int(digits[1:])
        elif len(digits) == 4:
            h, m = int(digits[:2]), int(digits[2:])
        else:
            return None
        return time(h, m) if 0 <= h < 24 and 0 <= m < 60 else None

    if isinstance(val, str):
        s = val.strip().lower()
        if s in _JUNK_HORA_VALUES:
            return None
        s = re.sub(r"[h;.]", ":", s)
        s = re.sub(r":+", ":", s).strip(":")
        parts = s.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            return time(h, m) if 0 <= h < 24 and 0 <= m < 60 else None
        except (ValueError, IndexError):
            return None

    return None


def _parse_hora(series: pd.Series) -> pd.Series:
    return series.apply(_parse_hora_value)


def _split_consulado(raw: str) -> tuple[str | None, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    raw_clean = raw.strip()
    parts = re.split(r"->|=|>|-(?!\d)", raw_clean)  # separadores usados na planilha para indicar trâmite
    parts = [p.strip() for p in parts if p.strip()]
    destino = parts[-1] if parts else None
    destino_norm = _normalize_consulado_code(destino)
    return raw_clean, destino_norm


def _normalize_consulado_code(value: str | None) -> str | None:
    if not value:
        return None
    v = value.upper().replace(".", "").replace(" ", "")
    return v if v else None


def _normalize_situacao(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "nao_informado"
    val = raw.strip().lower()
    if "conclu" in val:
        return "concluido"
    if "aguardando" in val:
        return "aguardando_resultado"
    if "sem noti" in val:
        return "sem_noticias"
    return "outro"


def _extract_int(raw) -> int | None:
    if raw is None:
        return None
    match = re.search(r"\d+", str(raw))
    return int(match.group()) if match else None


def _row_hash(row: pd.Series) -> str:
    """
    Gera uma chave estável para a linha, usada como row_hash no upsert.

    IMPORTANTE: usa os campos JÁ PARSEADOS (data_solicitacao, hora_solicitacao),
    não os "_raw". Os valores brutos têm representação diferente dependendo da
    origem — no xlsx local, a data chega como datetime nativo do Excel; no CSV
    baixado do Google Sheets, chega como texto "28/10/2022". Se o hash usasse o
    valor bruto, a MESMA linha geraria hashes diferentes conforme a fonte,
    fazendo o upsert tratar o mesmo expediente como registros duplicados.
    Os campos já parseados têm sempre o mesmo tipo/formato, não importa a
    origem dos dados.
    """
    data_str = row["data_solicitacao"].strftime("%Y-%m-%d") if pd.notna(row.get("data_solicitacao")) else ""
    hora_val = row.get("hora_solicitacao")
    hora_str = hora_val.isoformat() if isinstance(hora_val, time) else ""
    key = "|".join([
        str(row.get("nome") or "").strip(),
        str(row.get("numero_protocolo") or "").strip(),
        data_str,
        hora_str,
        str(row.get("situacao_raw") or "").strip(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def transform(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = _map_columns(raw_df)
    logger.info("Colunas mapeadas: %s", list(df.columns))

    # --- Datas ---
    df["data_solicitacao"] = _parse_br_date(df["data_solicitacao_raw"])
    df["data_entrega_docs_finais"] = _parse_br_date(df.get("data_entrega_docs_raw"))
    df["data_conclusao"] = _parse_br_date(df.get("data_conclusao_raw"))
    df["hora_solicitacao"] = _parse_hora(df["hora_raw"]) if "hora_raw" in df else None

    # --- Filtro central: descarta linhas separadoras de mês e linhas "lixo" ---
    before = len(df)
    df = df[df["data_solicitacao"].notna()].copy()
    logger.info("Filtradas %d linhas sem data de solicitação válida (separadores/lixo). Restam %d.",
                before - len(df), len(df))

    # --- Consulado ---
    consulado_split = df["consulado_raw"].apply(_split_consulado)
    df["consulado_origem"] = consulado_split.apply(lambda t: t[0])
    df["consulado_processamento"] = consulado_split.apply(lambda t: t[1])

    # --- Categóricos ---
    df["categoria_anexo"] = pd.to_numeric(df.get("categoria_anexo_raw"), errors="coerce").astype("Int64")
    df["parentesco"] = df.get("parentesco").astype(str).str.strip().str.lower().replace({"nan": None})
    df["situacao"] = df["situacao_raw"].apply(_normalize_situacao)
    df["retencao_parcial_docs"] = df.get("retencao_parcial_raw").astype(str).str.strip().str.lower().eq("sim")

    # --- Espera ---
    df["espera_dias_planilha"] = df["espera_dias_raw"].apply(_extract_int)
    df["em_aberto"] = df["situacao"] != "concluido"

    today = pd.Timestamp(date.today())
    dias_concluido = (df["data_conclusao"] - df["data_solicitacao"]).dt.days
    dias_em_aberto = (today - df["data_solicitacao"]).dt.days
    df["espera_dias_calculado"] = dias_concluido.where(~df["em_aberto"], dias_em_aberto)

    # --- Identidade da linha (para upsert idempotente) ---
    df["row_hash"] = df.apply(_row_hash, axis=1)

    final_cols = [
        "row_hash", "nome", "numero_protocolo",
        "data_solicitacao", "hora_solicitacao",
        "consulado_origem", "consulado_processamento",
        "categoria_anexo", "parentesco",
        "previsao_informada", "situacao", "situacao_raw",
        "retencao_parcial_docs", "data_entrega_docs_finais", "data_conclusao",
        "espera_dias_planilha", "espera_dias_calculado", "em_aberto",
        "notas",
    ]
    df = df[[c for c in final_cols if c in df.columns]].reset_index(drop=True)

    dupes = df["row_hash"].duplicated().sum()
    if dupes:
        logger.warning("%d linhas com row_hash duplicado (possível linha repetida na planilha).", dupes)

    logger.info("Transform concluído: %d linhas prontas para carga.", len(df))
    return df
