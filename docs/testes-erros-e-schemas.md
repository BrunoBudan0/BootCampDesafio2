# Testes, códigos de erro e schemas

Os termos seguem a [linguagem onipresente](linguagem-onipresente.md) e as tabelas seguem a [modelagem de dados](modelagem-de-dados.md). Este documento fecha o que os testes exigem: como cada regra é calculada, o formato de cada resposta, os códigos de erro e o porquê de cada schema.

O projeto segue TDD: os testes foram escritos antes do código. Hoje a suíte tem 295 testes. Com as rotas ainda inexistentes, 287 falham com HTTP 404 e 8 passam: os 6 de health check do template e 2 de token ausente, porque o middleware de INTERNAL-TOKEN do Base Service já recusa qualquer rota sem token. Os testes que editam a política também dão erro no fim, porque a restauração da política confere o 201 e a rota ainda não existe.

## 1. Como rodar

```bash
docker compose down -v
docker compose up -d --build --wait
pip install -r requirements-dev.txt
pytest
```

O `down -v` só é preciso quando o `database/database.sql` muda, porque o banco só lê esse arquivo quando nasce.

## 2. Definições que os testes fixam

### Tempo e janelas

| Assunto | Definição |
|---|---|
| Relógio das regras | Nenhuma regra usa o relógio do servidor. Toda janela termina no `transaction_date` do Pix analisado |
| Forma da janela | Intervalo aberto no início e fechado no fim: `(T menos a janela, T]`. Um Pix que aconteceu exatamente no início da janela fica de fora; um Pix com a mesma data do analisado entra |
| Horário local | O `transaction_date` no fuso que veio nele. Decide noite e dia |
| Idade de conta | `T menos opening_date`, em duração exata. "Menos de 30 dias" é `< 30 × 24 h`; com exatamente 30 dias a conta já não é nova |
| Dia do limite do aparelho | Dia de calendário no horário local, da meia-noite até `T` |
| Noite | Das 20:00:00 até 05:59:59 no horário local. Às 06:00:00 já é dia. Um Pix à 01:00 pertence à noite que começou às 20:00 do dia anterior |
| Pix já gravado com data posterior | Fica fora de qualquer janela do Pix analisado, porque a janela termina em `T` |

### Conjuntos de análises

| Conjunto | Quais análises |
|---|---|
| Tentativas | Todas as análises gravadas, com qualquer decisão |
| Pix aceitos | Decisão `approved`, ou decisão `two_factor_required` com confirmação `confirmed` (VIEW `accepted_pix`) |
| 2FA pendente válido para um Pix novo | Decisão `two_factor_required`, sem confirmação e com `two_factor_expires_at > T` do Pix novo |
| Consumo de limite | Pix aceitos mais 2FA pendentes válidos. Reprovados, 2FA recusados e 2FA expirados não consomem limite |
| Histórico do pagador | Pix aceitos do mesmo documento de pagador em `(T menos 90 dias, T]` |
| Início frio | Histórico do pagador vazio (n = 0) |
| Valor acumulado no total | Valor do Pix mais o consumo de limite do pagador em `(T menos 24 h, T]` |
| Valor acumulado no recebedor | Valor do Pix mais o consumo de limite do pagador para o mesmo documento de recebedor em `(T menos 24 h, T]` |
| Repetição idempotente | Um `POST` repetido com o mesmo `id` não é uma tentativa nova |

### Contas

| Conta | Definição |
|---|---|
| Mediana | Mediana contínua (média dos dois do meio quando a quantidade é par) |
| Mediana da população | `(N × mediana observada + 30 × ticket médio de referência) / (N + 30)`, com N = Pix aceitos de todos os pagadores com o mesmo par pagador e recebedor na janela de histórico. Com N = 0, vale o ticket médio de referência |
| Base de comparação | `(n × mediana do pagador + 5 × mediana da população) / (n + 5)`, com n = Pix aceitos do pagador no mesmo par. Com n = 0, vale a mediana da população |
| Teto habitual | Maior Pix aceito do pagador no histórico, de qualquer par. Em início frio, a base de comparação |
| Pontos com familiaridade | `piso(pontos × k / (k + n))`, com n = Pix aceitos do pagador com aquele IP, local ou canal. A regra só é gravada quando o resultado é maior que zero. Com 10 pontos e k = 5: n = 0 dá 10, n = 3 dá 6 |
| Local | Latitude e longitude arredondadas em 2 casas, com arredondamento do Postgres (metade para longe do zero) |
| Distância | Fórmula de haversine com raio da Terra de 6.371 km, sobre as coordenadas como vieram |
| Velocidade | Distância dividida pelo tempo entre o Pix analisado e a tentativa anterior mais recente do pagador que tinha geolocalização. Tempo zero com distância maior que zero conta como velocidade infinita |
| Volume mensal típico | Soma dos Pix aceitos do pagador no período de referência vezes 30 dividida pelos dias do período. O período de referência é `[início, T menos 30 dias]`, fechado nas duas pontas, com início no mais tarde entre `T menos 90 dias` e o primeiro Pix aceito do pagador. Com menos de 30 dias de período, a regra não é avaliada |
| Volume do mês atual | Valor do Pix mais o consumo de limite do pagador em `(T menos 30 dias, T]` |
| Comparações de valor | Sempre em centavos e sempre estritas: "acima de R$ 1.000" é `> 100000` |

### Cada regra

| Código | Dispara quando |
|---|---|
| `device_used_by_many_sources` | Documentos de pagador distintos nas tentativas com o mesmo `device_id` em `(T menos 24 h, T]`, contando o atual, `>= 5` |
| `impossible_travel_on_unregistered_device` | Velocidade `> 900 km/h` e o aparelho não está cadastrado para o pagador |
| `new_account_to_new_destination_far_above_cap` | Conta nova, destino novo e valor acumulado no recebedor `> 5 ×` teto de conta nova |
| `nightly_limit_exceeded` | Pagador e recebedor PF, Pix à noite e a soma da noite (valor do Pix mais o consumo de limite PF para PF desde o início da noite) `>` limite noturno do pagador. Vale também em início frio. O limite em vigor em `T` sai do pedido mais recente com `requested_at <= T`: se ele já vale (`effective_at <= T`), é o valor dele; se ainda não vale (aumento pendente), é o limite em vigor imediatamente antes desse pedido. Sem pedido, R$ 1.000. Assim uma redução nunca é desfeita por um aumento pedido antes dela |
| `unregistered_device_limit_exceeded` | Fora do início frio, aparelho não cadastrado e (valor do Pix `> R$ 200` ou soma do dia no mesmo aparelho `> R$ 1.000`) |
| `impossible_travel` | Velocidade `> 900 km/h` com o aparelho cadastrado |
| `ip_unfamiliar`, `location_unfamiliar`, `channel_unfamiliar` | Fora do início frio, com pontos de familiaridade maiores que zero. O local só é avaliado se o Pix trouxer geolocalização. O canal é comparado em minúsculas |
| `two_factor_denied_recently` | Alguma confirmação `denied` de análise do pagador com `confirmed_at` em `(T menos 24 h, T]` |
| `new_account_above_cap` | Conta nova e valor acumulado no total `>` teto de conta nova (PF R$ 1.000, PJ R$ 10.000) |
| `burst_of_pix` | Tentativas do pagador em `(T menos 5 min, T]`, contando a atual, `>= 5` |
| `amount_above_baseline` | Fora do início frio, valor acumulado no recebedor `>=` piso das regras de valor e `>` multiplicador × base de comparação |
| `monthly_volume_above_typical` | Fora do início frio, período de referência com 30 dias ou mais, volume do mês atual `>=` piso e `> 3 ×` volume mensal típico |
| `destination_account_opened_very_recently` | Conta de destino com menos de 7 dias. Vale 25 pontos, abaixo do limiar de alerta: sozinha não gera alerta |
| `destination_account_opened_recently` | Conta de destino com menos de 30 dias e sem a regra anterior |
| `new_destination_above_usual_ceiling` | Documento do recebedor ausente do histórico do pagador e valor acumulado no recebedor `>` teto habitual |
| `destination_receiving_from_many_sources` | Recebedor PF e documentos de pagador distintos nas tentativas para o mesmo documento de recebedor em `(T menos 1 h, T]` com valor `>=` piso das regras de valor, contando o atual se ele também atingir o piso, `>= 5` |
| `destination_rejected_for_other_sources` | Documentos de outros pagadores com análise para o mesmo documento de recebedor em `(T menos 7 dias, T]` que teve 2FA recusado, ou que foi reprovada tendo entre as disparadas alguma regra da família contraparte ou `new_account_to_new_destination_far_above_cap`, `>= 2`. Análises em que esta regra disparou nunca contam. Reprovação só por sinal do pagador (limite noturno, aparelho compartilhado, viagem impossível) não conta |
| `destination_document_in_many_accounts` | Contas de destino distintas (participante, agência e número) nas tentativas para o mesmo documento de recebedor em `(T menos 24 h, T]`, contando a atual, `>= 3` para PF e `>= 10` para PJ |
| `same_owner` | Documento do pagador igual ao do recebedor |
| `known_destination` | 3 ou mais Pix aceitos do pagador para o mesmo documento de recebedor no histórico |
| `long_registered_device` | Aparelho cadastrado para o pagador com `registered_at <= T menos 30 dias` |

### Cadastro de aparelho

| Origem | Quando |
|---|---|
| `first_seen` | A análise é aprovada direto e o pagador não tem nenhum Pix aceito antes, em qualquer data |
| `two_factor` | Uma confirmação `confirmed` chega para uma análise. O aparelho daquela análise é cadastrado se ainda não estiver |

### Decisão

1. Regras eliminatórias. Se alguma dispara, só elas são gravadas, a decisão é `rejected`, e `risk_score` e `destination_risk` ficam nulos.
2. Pontuação de risco: soma de cada família limitada ao teto, mais os redutores (negativos), nunca abaixo de zero. Faixa: `< 40` aprova, `40 a 69` pede 2FA, `>= 70` reprova.
3. Regras regulatórias: o limite noturno força `rejected` e o limite do aparelho força no mínimo `two_factor_required`. Elas entram com 0 ponto.
4. Vale a decisão mais severa entre a faixa e as decisões forçadas.
5. Risco do recebedor: `max(0, sinais da relação + same_owner + known_destination) + sinais da base`, sem teto. Os sinais da relação são as regras com `counterparty_signal = relationship` (idade da conta de destino e destino novo acima do teto habitual); os da base são as com `base` (fan-in, reprovações de outros pagadores e várias contas). A partir de 30 sai um alerta.
6. Decisão `two_factor_required` grava `two_factor_expires_at = T + 10 min`.

Análise, regras disparadas e cadastro `first_seen` entram no mesmo COMMIT. Antes de ler o histórico, a análise pega `pg_advisory_xact_lock` em três chaves: o documento do pagador, o `device_id` e o documento do recebedor, sempre na mesma ordem (pelo valor numérico da chave) para não haver deadlock. Assim Pix simultâneos do mesmo pagador, do mesmo aparelho ou para o mesmo recebedor se enxergam. A confirmação de 2FA pega a do pagador.

## 3. Respostas

### `POST /pix/transaction` e `GET /pix/transaction/{id}`

`201` para análise nova, `200` para repetição do mesmo Pix e para o GET.

```json
{
    "key": "b3f1c2e0-7d4a-4c1e-9a52-1f0e6c9d2a77",
    "status": "two_factor_required",
    "metadata": {
        "risk_score": 65,
        "destination_risk": 25,
        "policy": {"name": "bank", "version": 1},
        "rules": [
            {"code": "new_account_above_cap", "kind": "scoring", "family": "velocity", "points": 40, "reason": "Conta aberta há 10 dias pagando R$ 1.500,00, acima do teto de R$ 1.000,00"}
        ],
        "alerts": [],
        "two_factor": {"status": "pending", "expires_at": "2026-10-17T14:10:00-03:00", "confirmed_at": null}
    }
}
```

- `status` é sempre a decisão do motor e nunca muda.
- O mesmo Pix é reconhecido pelo `payload_hash`: SHA-256 do JSON canônico (chaves em ordem) depois de normalizar documentos (só dígitos e letras), `channel` (minúsculas) e `amount` (inteiro). As datas entram como vieram: o mesmo instante com outro fuso é outro conteúdo (409), porque o fuso decide a noite.
- `alerts` traz `{"code": "destination_alert", "destination_risk": 30, "threshold": 30}` quando o risco do recebedor atinge o limiar.
- `two_factor` é `null` quando a decisão não foi 2FA. O `status` dele é `confirmed` ou `denied` quando há confirmação. Sem confirmação, é `pending` ou `expired` pelo relógio do servidor (exceção consciente: é apresentação, não regra).
- Nenhum documento, nem com nem sem pontuação, aparece na resposta, inclusive nos motivos.

### `POST /pix/transaction/{id}/two-factor`

Devolve a análise inteira no mesmo formato acima, já com o resultado em `two_factor`. `201` na primeira confirmação. O mesmo resultado repetido dá `200` com a confirmação já gravada, mesmo que o `confirmed_at` enviado seja outro. Duas confirmações simultâneas com resultados diferentes gravam uma só: uma recebe `201` e a outra `409`.

### `POST /sources/{document}/nightly-limit`

`201` com `{"nightly_limit_cents", "requested_at", "effective_at"}`. O documento do caminho pode vir com ou sem pontuação. Um valor maior que o limite em vigor no `requested_at` (pela regra da seção 2) vale 24 h depois do pedido; um valor menor ou igual vale no próprio pedido.

### Política de risco

`GET /risk-policy`, `GET /risk-policy/versions/{version}` e o `201` do `POST /risk-policy/versions` devolvem:

```json
{
    "name": "bank",
    "version": 2,
    "change_reason": "Baixa o limiar de 2FA",
    "based_on": {"name": "bank", "version": 1},
    "parameters": {"history_window_days": 90, "two_factor_score_threshold": 35},
    "rules": [
        {"code": "burst_of_pix", "kind": "scoring", "family": "velocity", "enabled": true, "points": 25, "threshold": 5, "window_minutes": 5, "company_threshold": null}
    ]
}
```

`parameters` traz os 20 parâmetros, e `rules` traz as 21 regras editáveis (as regulatórias ficam de fora). `GET /risk-policy/templates` devolve `{"templates": [...]}` com os três modelos nesse mesmo formato.

O `POST` herda tudo da versão vigente da política do banco, ou do modelo pedido em `based_on_template`, e aplica por cima o que veio em `parameters` e `rules`.

## 4. Códigos de erro

Todo erro tem o corpo `{title, description, translation, code}`.

| Código | HTTP | Quando | Rotas |
|---|---|---|---|
| QIT000001 | 400 | O corpo não segue o JSON Schema, ou traz número que não é finito (NaN, Infinity), que o JSON Schema não barra | Todas com corpo |
| QIT000002 | 403 | Sem `INTERNAL-TOKEN` ou com token errado | Todas, menos `/` e `/health_check` |
| QIT000404 | 404 | Rota inexistente | Qualquer |
| QIT000405 | 405 | Método não aceito na rota | Qualquer |
| QIT000500 | 500 | Erro inesperado | Qualquer |
| QIT001001 | 404 | Pix sem análise gravada | GET do Pix, confirmação de 2FA |
| QIT001002 | 409 | `id` já analisado com outro conteúdo | POST do Pix |
| QIT001003 | 422 | CPF ou CNPJ com dígito verificador errado, ou CPF com todos os dígitos iguais | POST do Pix, limite noturno |
| QIT001004 | 422 | Data com formato certo que não existe no calendário (30 de fevereiro, 25 horas) ou com fuso fora de -12:00 a +14:00 | POST do Pix, confirmação de 2FA, limite noturno |
| QIT001005 | 422 | IP com caracteres válidos que não é um IPv4 nem um IPv6 | POST do Pix |
| QIT001006 | 422 | Conta de origem ou de destino aberta depois da data do Pix | POST do Pix |
| QIT001007 | 409 | Confirmação de 2FA para análise que não pediu 2FA | Confirmação de 2FA |
| QIT001008 | 409 | Confirmação de 2FA com resultado diferente do já gravado | Confirmação de 2FA |
| QIT001009 | 422 | `confirmed_at` antes do Pix ou depois de `two_factor_expires_at` | Confirmação de 2FA |
| QIT001010 | 422 | Limite noturno pedido para CNPJ | Limite noturno |
| QIT001011 | 404 | Versão de política inexistente | GET de versão |
| QIT001012 | 422 | Código de regra desconhecido na edição | Edição da política |
| QIT001013 | 422 | Tentativa de editar uma regra regulatória | Edição da política |
| QIT001014 | 422 | Ajuste que a regra não usa (janela, limite, limite de PJ ou pontos numa regra sem esse ajuste), limite com mais de 2 casas decimais, ou limite fracionado em regra de unidade `count` ou `days` | Edição da política |
| QIT001015 | 422 | A mesma regra repetida na edição | Edição da política |
| QIT001016 | 422 | Política resultante incoerente: reprovação `<=` 2FA, pontos negativos em regra de pontuação, pontos positivos em redutor, faixa de 7 dias `>=` faixa de 30 dias, janela do volume mensal `>=` janela de histórico | Edição da política |
| QIT001017 | 409 | Duas edições simultâneas tentaram criar a mesma versão | Edição da política |

**Por que 400 e 422 são diferentes:** 400 quer dizer "não consegui ler o pedido", e é o schema que decide. 422 quer dizer "li, entendi, e o valor não pode existir": um CPF com o formato certo e o dígito errado, ou uma data que passa no padrão e não existe no calendário. É a mesma separação do Base Service (`InvalidDocumentNumber` e `InvalidBirthdate`).

**Por que pedido recusado não é gravado:** um pedido que não passa no schema ou na validação não é um Pix. Todo teste de recusa confere, pelo GET, que nada ficou gravado.

## 5. Schemas

Os schemas ficam em `src/schemas/` e usam JSON Schema draft-07, como o Base Service. O `SchemaHandler` do template não liga a checagem de `format`, então todo formato é escrito como `pattern`. Todo objeto tem `additionalProperties: false`: campo a mais é erro de quem chamou, e o motor não deve aceitar em silêncio algo que não sabe tratar.

### `definitions.json`

Peças usadas por mais de um schema, para cada regra de formato existir uma vez só.

| Definição | Regra | Por quê |
|---|---|---|
| `date_time_with_offset` | `AAAA-MM-DDTHH:MM:SS`, frações opcionais e fuso obrigatório (`Z` ou `+HH:MM`) | Noite e dia são decididos pelo fuso do Pix. Data sem fuso não tem horário local, então não pode ser analisada. O fuso entre -12:00 e +14:00 é conferido no código (422), para não chegar ao banco e virar 500 |
| `amount_cents` | Inteiro de 1 a 1.000.000.000.000 | Dinheiro em centavos, sem ponto flutuante. O teto existe para um valor absurdo virar 400, e não estourar o BIGINT com 500 |
| `document_number` | CPF com ou sem pontuação, ou CNPJ com ou sem pontuação e com letras maiúsculas nas 12 primeiras posições | O exemplo do desafio vem pontuado. O CNPJ alfanumérico vale para CNPJs novos desde julho de 2026. O dígito verificador é conferido no código (422) |
| `branch` | 1 a 10 dígitos | Agência é numérica. O limite cabe na coluna |
| `account_number` | 1 a 20 dígitos | O limite do DICT para número de conta |
| `participant` | Exatamente 8 dígitos | É o ISPB do banco do recebedor |

### `post_pix_transaction.json`

| Campo | Regra | Por quê |
|---|---|---|
| `id` | 1 a 64 caracteres entre letras, dígitos, `.`, `_`, `:` e `-`, começando com letra ou dígito | Vai no caminho do GET e da confirmação de 2FA, então não pode ter `/` nem espaço, nem ser `.` ou `..`, que o cliente HTTP transforma em outro caminho e deixariam o Pix gravado sem consulta. 64 cabe o EndToEndId real do Pix (32) com folga |
| `amount` | `amount_cents` | Ver acima |
| `transaction_date`, `opening_date` | `date_time_with_offset` | Ver acima |
| `source_account` | `branch`, `account_number`, `opening_date` e `owner.document_number`, todos obrigatórios | São os dados que as regras usam: conta nova e identidade do pagador |
| `destination_account` | Os mesmos e mais `participant` | O recebedor é identificado pelo documento, e a conta (participante, agência, número) diferencia as contas do mesmo documento |
| `source.device_id` | 1 a 100 caracteres sem espaço | Identificador do aparelho para o cadastro e para o aparelho compartilhado |
| `source.channel` | Começa com letra; letras, dígitos e `_`; até 30 | Texto aberto, porque a lista de canais não é fechada (`app`, `web` e outros). Maiúsculas são aceitas e o motor compara em minúsculas |
| `source.ip` | Só caracteres de IP (`0-9`, `a-f`, `:` e `.`), de 2 a 45 | O schema barra lixo evidente com 400. Um IPv4 ou IPv6 que não existe passa no padrão e o código recusa com 422 |
| `source.geolocation` | Opcional e pode ser `null`. Quando vem, `latitude` (-90 a 90) e `longitude` (-180 a 180) são obrigatórias juntas | O desafio diz que é opcional. Meia coordenada não é um local |

### `post_two_factor_confirmation.json`

| Campo | Regra | Por quê |
|---|---|---|
| `result` | `confirmed` ou `denied` | Palavras diferentes de `approved` e `rejected`, que são decisões do motor |
| `confirmed_at` | `date_time_with_offset` | A data vem no corpo para a validade ser decidida sem relógio do servidor, o que deixa a regra determinística |

### `post_source_nightly_limit.json`

| Campo | Regra | Por quê |
|---|---|---|
| `nightly_limit_cents` | `amount_cents` | O banco pode aumentar ou reduzir o limite |
| `requested_at` | `date_time_with_offset` | A norma conta o prazo do aumento a partir do pedido do cliente, então o motor precisa da data do pedido, não da data da chamada |

O documento vem no caminho e é validado no código: precisa ser um CPF válido (422 QIT001003), e CNPJ é recusado (422 QIT001010), porque o limite noturno da norma é de pessoa física.

### `post_risk_policy_version.json`

| Campo | Regra | Por quê |
|---|---|---|
| `change_reason` | Obrigatório, até 255, com pelo menos um caractere que não seja espaço | Toda versão precisa dizer por que existe (auditoria e LGPD, art. 20) |
| `based_on_template` | Opcional: `conservative`, `balanced` ou `permissive` | É assim que o banco troca de modelo de partida |
| `parameters` | Opcional; só os 20 parâmetros conhecidos, cada um inteiro dentro de uma faixa | Parâmetro desconhecido é 400 porque não existe. As faixas barram valores sem sentido (janela de 0 dias). A coerência entre parâmetros fica no código (422) |
| `rules` | Opcional; até 50 itens com `code` obrigatório e pelo menos um ajuste (`enabled`, `points` de -100 a 100, `threshold > 0`, `window_minutes >= 1`, `company_threshold > 0`) | Um item só com o código não ajusta nada. Qual ajuste cada regra aceita depende do catálogo e é conferido no código (422) |

Os valores regulatórios (R$ 1.000 da noite, R$ 200 e R$ 1.000 do aparelho) não aparecem em nenhum schema: não há como editá-los.

## 6. Banco de dados

O `database/database.sql` cria as tabelas da modelagem, a VIEW `accepted_pix`, um gatilho comum (`refuse_change`) que recusa UPDATE, DELETE e TRUNCATE em todas as tabelas, e a carga inicial:
- as 3 decisões;
- as 23 regras do catálogo;
- os 3 modelos e a política do banco;
- os 84 ajustes de regra (21 por versão).

O banco foi validado à parte, numa transação desfeita no fim, com 32 conferências. Todas passaram:
- a política do banco é cópia exata do modelo equilibrado;
- os multiplicadores são 3, 5, 10 e 5;
- as regulatórias não têm ajuste;
- as decisões forçadas estão certas;
- uma segunda política do banco é recusada;
- UPDATE, DELETE e TRUNCATE são recusados;
- versão repetida e limiar de reprovação abaixo do 2FA são recusados;
- motivo em branco é recusado;
- regra de pontuação sem família e eliminatória sem decisão forçada são recusadas;
- `pix_id` repetido é recusado;
- valor zero é recusado;
- tipo de pessoa diferente do documento é recusado;
- latitude sem longitude é recusada;
- conta aberta depois do Pix é recusada;
- canal com maiúscula é recusado no banco (o código normaliza antes);
- `risk_score` e `destination_risk` só vêm juntos;
- o 2FA não pode expirar na própria data do Pix;
- um Pix com CNPJ alfanumérico é aceito;
- uma segunda confirmação de 2FA é recusada;
- resultado de 2FA desconhecido é recusado;
- a VIEW aceita o 2FA confirmado;
- o mesmo aparelho não é cadastrado duas vezes;
- limite noturno para CNPJ e limite valendo antes do pedido são recusados.

Essas conferências não entram na suíte, porque a regra do projeto é testar só por HTTP.

## 7. Os testes

### Convenções

- **Só HTTP.** Nenhum teste importa `src/` nem lê o banco.
- **Cada teste monta o próprio cenário pelas rotas**, com documentos, aparelhos, IPs e contas novos a cada vez. O banco não é limpo entre testes.
- **Preparação com nome.** Toda preparação passa por `setup_ok` ou `analyze_expecting`. Se ela falha, a mensagem diz que foi a preparação, em qual passo e com quais regras.
- **Datas montadas pelo teste** (`tests/utils/clock.py`, fuso de São Paulo). Os Pix comuns são às 14h, para não cair no limite noturno. Só os testes de 2FA pendente usam "agora", porque o GET mostra pendente ou expirado pelo relógio.
- **Recusa confere que nada mudou:** o Pix recusado não aparece no GET, o 2FA recusado continua sem resposta, e a política recusada não ganha versão.
- **Testes de política devolvem a política ao modelo equilibrado** ao terminar (fixture `restore_bank_policy`). A suíte roda em sequência; rodar em paralelo misturaria as políticas.
- **Premissa da população:** todo Pix aceito dos testes que não testa valor usa R$ 100,00. Só o teste do piso do fan-in grava 4 Pix de R$ 99,99 por rodada, o que não mexe na mediana. Assim, a mediana da população fica entre R$ 100,00 e o ticket médio do BCB, e os limites dos testes de valor têm folga para qualquer valor nessa faixa. Rode a suíte num banco recém-criado, sem dados manuais.
- **Datas do dia:** `today_at` usa a data de São Paulo fixada quando a suíte começa, para nenhum teste mudar de dia no meio se a meia-noite passar durante a rodada.

### O que cada arquivo prova

| Arquivo | Testes | O que prova |
|---|---|---|
| `test_pix_transaction_contract.py` | 76 | Token obrigatório; o payload de exemplo do desafio é reprovado pelo limite noturno (PF para PF às 22h15 com R$ 1.500); id `.` e `..` e fuso fora da faixa são recusados; latitude NaN dá 400; o mesmo CPF com e sem pontuação forma um histórico; formato da resposta; cada campo obrigatório faltando dá 400; cada valor inválido dá 400; datas inexistentes, IP inexistente, documentos com dígito errado e conta aberta depois do Pix dão 422; documento sem pontuação, CNPJ alfanumérico, IPv6 e geolocalização ausente ou nula são aceitos; nada recusado fica gravado |
| `test_pix_transaction_idempotency.py` | 7 | Repetição devolve a mesma análise com 200; a ordem dos campos não importa; documento sem pontuação, canal em maiúsculas e valor `10000.0` são o mesmo Pix; o mesmo instante com outro fuso é outro conteúdo; mesmo `id` com outro conteúdo dá 409 e mantém a primeira; 5 cópias em paralelo geram uma análise; repetição não conta como tentativa |
| `test_pix_transaction_get.py` | 7 | GET igual ao POST; 404 com QIT001001; token; nenhum documento exposto; 2FA pendente e expirado pelo relógio; Pix aprovado sem `two_factor` |
| `test_pix_decision_flow.py` | 22 | Pix sem sinal aprova com zero; teto de família; risco do recebedor sem teto; redutores; pontuação nunca negativa; faixas 40 e 70; regulatória de 2FA vence pontuação baixa; limite noturno reprova e mantém a pontuação; eliminatória encerra sem pontuação; validade de 10 minutos; versão da política na análise; formato de cada regra disparada; alerta a partir de 30 e conta de destino muito recente sozinha sem alerta; redutores não abatem sinais da base; destino conhecido abate sinais da relação; eliminatória esconde a regulatória; Pix simultâneos do mesmo pagador, do mesmo aparelho e para o mesmo recebedor se enxergam (travas) |
| `rules/test_eliminatory_rules.py` | 12 | Aparelho compartilhado (5 pagadores, janela de 24 h, mesmo pagador conta uma vez); viagem impossível em aparelho não cadastrado; conta nova para destino novo acima de 5 vezes o teto, com fronteira e fracionamento |
| `rules/test_regulatory_rules.py` | 25 | Limite noturno: fronteira de R$ 1.000, fracionamento, virada da meia-noite, uma noite por vez, 20h e 6h, só PF para PF, fuso do payload, reprovado não consome limite, 2FA pendente consome e expirado não, paralelo não passa os dois, aumento aprovado só depois de 24 h, redução imediata, redução depois de um aumento pendente mantém o limite menor. Aparelho não cadastrado: R$ 200 por Pix, R$ 1.000 por dia, virada do dia local, início frio, cadastro pelo primeiro Pix aceito e pelo 2FA confirmado, 2FA recusado não cadastra |
| `rules/test_identity_rules.py` | 14 | Viagem impossível com 40 pontos e sem geolocalização; IP, local e canal com pontos que caem conforme o uso; local arredondado; canal sem diferença de maiúsculas; 2FA recusado nas últimas 24 h |
| `rules/test_velocity_rules.py` | 12 | Conta nova acima do teto para PF e PJ, com fronteiras de valor e de 30 dias; fracionamento; 2FA pendente consome o teto, recusado e expirado não; rajada com fronteira de 5 minutos e contando tentativas reprovadas |
| `rules/test_amount_rules.py` | 8 | Valor fora do padrão, dentro do padrão, início frio e fracionamento para o mesmo recebedor; volume mensal acima e dentro do típico, histórico curto e início frio |
| `rules/test_counterparty_rules.py` | 26 | Idade da conta de destino com as fronteiras de 7 e 30 dias; destino novo acima do teto habitual, fronteira, destino conhecido, fracionamento e início frio; fan-in só para PF, só a partir do piso e janela de 1 h; reprovações de outros pagadores (2FA recusado e reprovação com sinal de contraparte contam, reprovação só por sinal do pagador não, as do próprio pagador não, 7 dias, sem se realimentar); mesmo documento em várias contas, PF e PJ, janela de 24 h |
| `rules/test_reducer_rules.py` | 6 | Mesma titularidade; destino conhecido a partir de 3 Pix; aparelho cadastrado há mais de 30 dias |
| `two_factor/test_two_factor_confirmation.py` | 21 | Confirmação e recusa gravadas; repetição, inclusive com outro momento; resultados opostos em paralelo gravam um só; resultado trocado dá 409; análise sem 2FA dá 409; 404; fora da validade dá 422; último segundo aceito; corpo inválido; token; 2FA confirmado entra no histórico e cadastra o aparelho, recusado não |
| `source_nightly_limit/test_source_nightly_limit.py` | 15 | Aumento vale em 24 h, redução na hora, comparação com o limite em vigor; documento sem pontuação; CNPJ e CPF inválido dão 422; corpo inválido; data inexistente; token |
| `risk_policy/test_risk_policy.py` | 38 | Formato da política; regulatórias fora; modelos diferem só no multiplicador; política do banco segue o equilibrado; versão inexistente; token; edição herda o resto; versão antiga não muda; troca de modelo; análise grava a versão nova; regra desligada para; pontos editados; multiplicador conservador; piso das regras de valor contra o acumulado; limite de PJ; cada edição incoerente dá 422 sem criar versão, inclusive limite fracionado e com 3 casas; corpo inválido dá 400; edições simultâneas nunca repetem versão |
| `test_healthcheck.py` | 6 | Os testes do template, sem mudança |
