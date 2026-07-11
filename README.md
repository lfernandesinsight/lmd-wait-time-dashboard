# LMD Wait-Time Dashboard

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![Grafana](https://img.shields.io/badge/Grafana-Cloud-F46800.svg)](https://grafana.com/)
[![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow.svg)](#roadmap)

Dashboard público com pipeline de dados completo (ETL → banco relacional → visualização) para analisar tempos de espera em processos de **Cidadania Espanhola pela Lei de Memória Democrática (LMD)**, com base em dados voluntariamente compartilhados pela comunidade de solicitantes.

> 🇪🇸 *A public data pipeline (ETL → relational database → dashboard) analyzing wait times for Spanish citizenship applications under the Democratic Memory Law (LMD), built on data voluntarily shared by the applicant community.*

---

## 📌 Sobre o projeto

A Lei de Memória Democrática (LMD) permite que descendentes de espanhóis que emigraram ou foram exilados solicitem a nacionalidade espanhola. O processo é longo, pouco transparente e a única fonte real de informação sobre prazos costuma ser uma planilha colaborativa mantida pela própria comunidade de solicitantes.

Este projeto transforma essa planilha crua — cheia das inconsistências típicas de preenchimento manual coletivo — em uma base de dados estruturada e um dashboard público, para dar visibilidade real sobre:

- Tempo médio de espera por situação do processo (concluído / aguardando resultado)
- Evolução do volume de solicitações ao longo do tempo
- Distribuição por consulado, parentesco e tipo de expediente
- Tendências que ajudem outros solicitantes a entender onde estão no processo

Também serve como projeto de portfólio, demonstrando um pipeline de dados completo do mundo real — incluindo o trabalho, nada glamouroso mas essencial, de lidar com dados sujos gerados por preenchimento humano coletivo.

## 🧱 Stack

| Camada | Tecnologia |
|---|---|
| Extração/Transformação | Python + pandas |
| Armazenamento | PostgreSQL (via Docker) |
| Visualização | Grafana (local → Grafana Cloud) |
| Orquestração local | Docker Compose |

## 📂 Estrutura do repositório

```
lmd-dashboard/
├── etl/
│   ├── extract.py      # leitura da planilha (localiza header dinamicamente)
│   ├── transform.py     # limpeza, normalização e cálculo de tempo de espera
│   ├── load.py           # upsert idempotente no Postgres
│   ├── main.py            # orquestra o pipeline (CLI)
│   └── Dockerfile          # imagem do serviço ETL
├── sql/
│   └── schema.sql          # DDL da tabela principal
├── data/                     # dados locais (ignorado no git — ver Privacidade)
├── docker-compose.yml        # orquestra Postgres + ETL
├── .dockerignore
├── requirements.txt
└── .env.example
```

## 🗺️ Roadmap (Sprints)

- [x] **Sprint 1** — ETL (Python/pandas) lendo a planilha local e carregando no Postgres
- [x] **Sprint 2** — Containerização completa via Docker Compose (ETL + Postgres)
- [ ] **Sprint 3** — Dashboard de KPIs no Grafana (tempo médio de espera, volume por período, por consulado)
- [ ] **Sprint 4** — Analytics avançado (tendências, previsão de tempo de espera, outliers)
- [ ] **Sprint 5** — Deploy público no Grafana Cloud

## 🚀 Como rodar

```bash
git clone https://github.com/lfernandesinsight/lmd-wait-time-dashboard.git
cd lmd-wait-time-dashboard
```

Coloque a planilha de origem em `data/` antes de seguir (veja [Privacidade dos dados](#-privacidade-dos-dados) — o arquivo não vem versionado no repositório).

### Opção A — Docker (recomendado)

Sobe o Postgres e roda o ETL automaticamente, sem precisar instalar Python nem nada localmente.

```bash
docker compose up --build
```

Isso builda a imagem do ETL, sobe um Postgres isolado (porta `5434` no host, pra não colidir com outros bancos que você já tenha rodando) e executa o pipeline completo assim que o banco estiver saudável.

Pra rodar o ETL de novo depois (ex: planilha atualizada), sem rebuildar a imagem:
```bash
docker compose run --rm etl
```

Pra conferir os dados carregados:
```bash
docker exec -it lmd_postgres psql -U lmd_user -d lmd_dashboard -c "SELECT situacao, COUNT(*) FROM expedientes GROUP BY situacao;"
```

### Opção B — Ambiente local (Python + venv)

Útil para desenvolvimento/debug do ETL, ou se preferir usar um Postgres que você já tenha rodando.

```bash
# ambiente virtual
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# configurar conexão com o Postgres (ajuste host/porta/usuário conforme seu ambiente)
cp .env.example .env

# rodar o ETL
python3 etl/main.py --dry-run --xlsx-path "data/Cidadania espanhola SP.xlsx"   # valida sem gravar
python3 etl/main.py --xlsx-path "data/Cidadania espanhola SP.xlsx"              # grava no Postgres
```

## 🔒 Privacidade dos dados

A planilha de origem contém nomes reais de solicitantes compartilhados voluntariamente pela comunidade. Por isso:

- O arquivo `.xlsx` original **não é versionado** neste repositório (veja `.gitignore`)
- Qualquer dado de exemplo publicado neste repo será anonimizado/sintético
- O dashboard público (quando publicado no Sprint 5) exibirá apenas agregações estatísticas, nunca dados individuais identificáveis

## 👤 Autor

**Leandro Fernandes** — Senior BI Analyst & Data Engineer
[Portfolio](https://lfernandesinsight.github.io) · [GitHub](https://github.com/lfernandesinsight)
