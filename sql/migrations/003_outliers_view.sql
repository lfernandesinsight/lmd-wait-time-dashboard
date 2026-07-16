-- Migração: adiciona a view de detecção de outliers (Sprint 4).
-- Não é necessária se você está criando o banco do zero — o schema.sql já inclui isso.
--
-- Uso (exemplo com o container postgres_dev):
--   docker exec -i postgres_dev psql -U dev -d lmd_dashboard < sql/migrations/003_outliers_view.sql

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
