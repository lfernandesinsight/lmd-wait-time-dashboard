-- Schema: lmd_dashboard
-- Tabela principal de expedientes de Cidadania Espanhola (LMD) - Consulado SP

CREATE TABLE IF NOT EXISTS expedientes (
    id                      SERIAL PRIMARY KEY,

    -- chave natural (hash da linha original, já que não há protocolo em 100% dos casos)
    row_hash                VARCHAR(64) UNIQUE NOT NULL,

    nome                    TEXT,
    numero_protocolo        TEXT,

    data_solicitacao        DATE,
    hora_solicitacao        TIME,

    consulado_origem        TEXT,          -- ex: "SP", "RJ->SP", "Lisboa->SP"
    consulado_processamento TEXT,          -- consulado onde o processo tramitou de fato (após "->")

    categoria_anexo         SMALLINT,      -- 1, 3, 4... (tipo de anexo/expediente)
    parentesco              TEXT,          -- neto, filho, bisneto...

    previsao_informada      TEXT,          -- texto livre: "2 meses", "não informado"...
    situacao                TEXT,          -- normalizado: concluido | aguardando_resultado | sem_noticias | outro
    situacao_raw            TEXT,          -- valor original da planilha

    retencao_parcial_docs   BOOLEAN,
    data_entrega_docs_finais DATE,
    data_conclusao          DATE,

    espera_dias_planilha    INTEGER,       -- valor bruto reportado na planilha (pode estar desatualizado)
    espera_dias_calculado   INTEGER,       -- calculado no ETL: conclusao - solicitacao, ou hoje - solicitacao se em aberto
    em_aberto                BOOLEAN,       -- true se ainda não concluído

    notas                   TEXT,

    fonte                   TEXT NOT NULL DEFAULT 'local_xlsx',
    carga_em                TIMESTAMP NOT NULL DEFAULT now(),
    atualizado_em           TIMESTAMP NOT NULL DEFAULT now(),

    -- Soft delete: preenchido quando a linha desaparece da planilha de origem
    -- numa carga posterior. NULL = ativo/atual. Nunca apagamos a linha de fato,
    -- pra preservar histórico (ex: entrada duplicada removida pelos mantenedores).
    removido_em             TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expedientes_situacao ON expedientes (situacao);
CREATE INDEX IF NOT EXISTS idx_expedientes_data_solicitacao ON expedientes (data_solicitacao);
CREATE INDEX IF NOT EXISTS idx_expedientes_consulado ON expedientes (consulado_processamento);
CREATE INDEX IF NOT EXISTS idx_expedientes_removido_em ON expedientes (removido_em);

-- Conveniência: consultas/dashboards devem usar esta view por padrão,
-- em vez de filtrar "WHERE removido_em IS NULL" toda vez.
CREATE OR REPLACE VIEW expedientes_ativos AS
    SELECT * FROM expedientes WHERE removido_em IS NULL;

-- Detecção de outliers de tempo de espera, por situação, usando o método IQR
-- (mais robusto que desvio-padrão para distribuições assimétricas como esta,
-- onde a maioria espera poucos meses mas uma cauda longa espera anos).
-- Recalculada dinamicamente a cada consulta — não precisa reprocessar no ETL
-- quando novos dados chegam.
CREATE OR REPLACE VIEW expedientes_outliers AS
    WITH quartis AS (
        SELECT
            situacao,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY espera_dias_calculado) AS q1,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY espera_dias_calculado) AS q3
        FROM expedientes_ativos
        WHERE situacao IN ('concluido', 'aguardando_resultado')
          AND espera_dias_calculado IS NOT NULL
        GROUP BY situacao
    )
    SELECT
        e.id,
        e.numero_protocolo,
        e.data_solicitacao,
        e.situacao,
        e.consulado_processamento,
        e.parentesco,
        e.espera_dias_calculado,
        q.q1,
        q.q3,
        (q.q3 - q.q1) AS iqr,
        ROUND(q.q3 + 1.5 * (q.q3 - q.q1)) AS limite_superior,
        (e.espera_dias_calculado > (q.q3 + 1.5 * (q.q3 - q.q1))) AS is_outlier
    FROM expedientes_ativos e
    JOIN quartis q ON e.situacao = q.situacao
    WHERE e.situacao IN ('concluido', 'aguardando_resultado')
      AND e.espera_dias_calculado IS NOT NULL;

-- Tendência de tempo de espera ao longo do tempo, via regressão linear simples
-- (espera_dias_calculado em função da data de solicitação), usando as funções
-- estatísticas nativas do Postgres — sem depender de bibliotecas externas de ML.
-- Baseada apenas em casos concluídos (única situação com duração real e final).
-- R² indica o quão confiável é a tendência: valores baixos significam que a
-- reta não descreve bem os dados, e a previsão deve ser vista com cautela.
CREATE OR REPLACE VIEW expedientes_tendencia_espera AS
    SELECT
        regr_slope(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400) AS inclinacao_dias_por_dia,
        regr_intercept(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400) AS intercepto,
        regr_r2(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400) AS r2,
        COUNT(*) AS amostras,
        ROUND(
            regr_slope(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400) * 30
        ) AS tendencia_dias_por_mes,
        ROUND(
            regr_slope(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400)
                * (EXTRACT(epoch FROM now()) / 86400)
            + regr_intercept(espera_dias_calculado, EXTRACT(epoch FROM data_solicitacao) / 86400)
        ) AS previsao_dias_se_solicitar_hoje
    FROM expedientes_ativos
    WHERE situacao = 'concluido' AND espera_dias_calculado IS NOT NULL;
