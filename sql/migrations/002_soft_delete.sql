-- Migração: adiciona soft delete a uma base já existente (criada antes do Sprint 4).
-- Não é necessária se você está criando o banco do zero — o schema.sql já inclui isso.
--
-- Uso (exemplo com o container postgres_dev):
--   docker exec -i postgres_dev psql -U dev -d lmd_dashboard < sql/migrations/002_soft_delete.sql

ALTER TABLE expedientes ADD COLUMN IF NOT EXISTS removido_em TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_expedientes_removido_em ON expedientes (removido_em);

CREATE OR REPLACE VIEW expedientes_ativos AS
    SELECT * FROM expedientes WHERE removido_em IS NULL;
