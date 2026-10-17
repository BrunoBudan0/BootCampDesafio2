# [Nome do grupo]

**Integrantes:** Bruno Budano Mello e Pedro Henrique Mathias Santiago

Motor antifraude de Pix do Bootcamp QI Tech 2026: uma API que recebe o pedido de Pix e decide se ele é aprovado, se precisa de 2FA ou se é reprovado, sempre com o motivo.

Os termos do projeto estão em [docs/linguagem-onipresente.md](docs/linguagem-onipresente.md) e o modelo de dados em [docs/modelagem-de-dados.md](docs/modelagem-de-dados.md).

## Como o motor de decisão funciona

[descrição breve sobre como estruturaram o motor]

## Regras

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|

[racional por trás da escolha das regras]

## Como as regras viram decisão

[ordem, quando pede 2FA]

## Como rodar e testar

Precisa de Docker e Python 3.11.

Subir a API e o banco:

```bash
docker compose up -d --build --wait
```

Instalar as dependências de teste, uma vez só:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

No Windows, a segunda linha é `.venv\Scripts\activate`.

Rodar os testes, com a API de pé:

```bash
pytest
```

A API atende em `http://localhost:3000`. Toda rota, menos `/` e `/health_check`, exige o header `INTERNAL-TOKEN` (o padrão é `default_token`).

O banco só lê o `database/database.sql` quando nasce. Depois de mudar esse arquivo:

```bash
docker compose down -v
docker compose up -d --build --wait
```
