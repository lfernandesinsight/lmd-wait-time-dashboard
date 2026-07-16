-- Migração: adiciona a view de tendência/previsão de tempo de espera (Sprint 4).
-- Não é necessária se você está criando o banco do zero — o schema.sql já inclui isso.
--
-- Uso (exemplo com o container postgres_dev):
--   docker exec -i postgres_dev psql -U dev -d lmd_dashboard < sql/migrations/004_tendencia_view.sql

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
