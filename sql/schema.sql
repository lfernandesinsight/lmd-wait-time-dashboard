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
    atualizado_em           TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expedientes_situacao ON expedientes (situacao);
CREATE INDEX IF NOT EXISTS idx_expedientes_data_solicitacao ON expedientes (data_solicitacao);
CREATE INDEX IF NOT EXISTS idx_expedientes_consulado ON expedientes (consulado_processamento);
