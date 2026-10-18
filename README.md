# Grupo 16 - Bruno Budano Mello e Pedro Henrique Mathias Santiago

**Integrantes:** Bruno Budano Mello e Pedro Henrique Mathias Santiago

Motor antifraude de Pix do Bootcamp QI Tech 2026: uma API que recebe o pedido de Pix antes de o dinheiro sair e decide se ele é aprovado, se precisa de 2FA ou se é reprovado, sempre com o motivo.

## Como o motor de decisão funciona

O motor é o do banco de quem paga. Ele recebe o Pix em `POST /pix/transaction`, monta o contexto da transação (o Pix, o histórico do pagador, o que a base viu do recebedor e a política de risco vigente), avalia as 24 regras do catálogo e devolve `approved`, `two_factor_required` ou `rejected`. Toda análise fica gravada com as regras que dispararam, os pontos, o motivo de cada uma e a versão da política que decidiu, e pode ser consultada em `GET /pix/transaction/{id}`.

### A ideia central: histórico tira fricção, não tira etapas

Quem tem histórico coerente recebe menos fricção, mas toda análise passa pelas mesmas etapas. Não existe caminho mais curto para cliente antigo, porque o golpe mais comum no Brasil, a falsa central, é feito pela própria vítima, no celular dela. A "assinatura" dela bate; só as regras de valor e de recebedor enxergam o golpe.

O padrão de cada pagador sai de uma conta só, a **credibilidade**, usada em três lugares:

```
credibilidade         = n / (n + k)
mediana da população  = (N × mediana observada no par + 30 × ticket médio do BCB) / (N + 30)
base de comparação    = (n × mediana do pagador + 5 × mediana da população) / (n + 5)
```

- Com poucos Pix, a referência pesa mais; com 5 Pix aceitos, o histórico do pagador já pesa metade.
- A mediana é calculada por par pagador e recebedor (PF→PF, PF→PJ, PJ→PF, PJ→PJ), para o aluguel de uma pessoa não parecer fora do padrão só porque ela faz muitas compras pequenas em lojas.
- A familiaridade de IP, local e canal usa a mesma ideia: um valor nunca visto pesa mais quanto maior o histórico.

Só os **Pix aceitos** (aprovados ou com 2FA confirmado) formam o histórico. A identidade do histórico é o documento, não a conta. Cliente antigo sem histórico no motor (início frio) não é punido: as regras de valor e de familiaridade só pontuam depois do primeiro Pix aceito.

### Comportamento e evidência

As regras de pontuação se dividem em dois tipos de sinal:

- **Comportamento** é o que o pagador está fazendo de diferente: conta nova, rajada, valor fora do padrão, destino novo, conta de destino recente. É atipicidade, e atipicidade tem explicação honesta (aluguel novo, compra grande).
- **Evidência** é dúvida sobre quem está pagando (identidade) ou o que a base inteira já viu do recebedor (fan-in, reprovações de outros pagadores, várias contas).

No modelo equilibrado, **comportamento sozinho chega no máximo ao 2FA com alerta; reprovar exige evidência**, uma regra eliminatória ou o limite noturno. O 2FA resolve dúvida de identidade, porque um invasor não consegue confirmar. Ele não resolve golpe, porque a vítima confirma; por isso, no golpe, a proteção é o alerta que aparece no 2FA, e a reprovação fica para quando a base aponta o recebedor como laranja.

### Política de risco

Os parâmetros e os ajustes de cada regra ficam numa política versionada. Existem três modelos (`conservative`, `balanced`, `permissive`) e uma política do banco, que nasce como cópia do equilibrado. O banco edita parâmetros e ajustes em `POST /risk-policy/versions`; cada edição cria uma versão nova e nunca altera a anterior. Os valores que vêm de norma do BCB não são editáveis: ficam em constantes no código.

### Garantias do desenho

- **Só INSERT:** um gatilho recusa UPDATE, DELETE e TRUNCATE em todas as tabelas. A decisão nunca muda; a confirmação do 2FA é um fato novo.
- **Um Pix, uma análise:** o mesmo `id` com o mesmo conteúdo devolve a análise gravada (200); com outro conteúdo, é recusado (409).
- **Janelas pela data da transação:** nenhuma regra lê o relógio do servidor. A noite e o dia são decididos no fuso que veio no Pix.
- **Pix simultâneos se enxergam:** a análise trava pagador, aparelho e recebedor no banco antes de decidir.
- **Nenhum documento sai na resposta**, e nenhum id interno do banco: só a chave da análise (UUID) e o `id` do Pix.
- **Dinheiro em centavos**, sempre inteiro.

## Regras

Valores do modelo equilibrado, que é a versão inicial da política do banco. "Acumulado" quer dizer o Pix analisado mais os Pix aceitos e os 2FA pendentes do pagador nas últimas 24 h: toda regra de valor compara o maior entre o Pix e o acumulado, para nada escapar por fracionamento.

### Eliminatórias: reprovam direto

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `device_used_by_many_sources` | Pagadores PF distintos usando o mesmo aparelho, contando o atual | 5 pagadores em 24 h | Aparelho usado para movimentar contas de vários laranjas. Uma família que divide um celular chega a 4. Empresas que pagam pelo mesmo computador, como um escritório de contabilidade, não contam |
| `impossible_travel_on_unregistered_device` | Velocidade desde o último Pix aceito com geolocalização, num aparelho não cadastrado | Acima de 900 km/h, só a partir de 50 km | 900 km/h é a velocidade de cruzeiro de um avião comercial. Abaixo de 50 km, a localização por wi-fi ou antena erra o suficiente para fingir uma viagem. Aparelho novo em outra cidade minutos depois é invasão |
| `new_account_to_new_destination_far_above_cap` | Conta de origem nova, destino novo e acumulado no recebedor acima de um múltiplo do teto de conta nova | 5 × teto (R$ 5.000 PF, R$ 50.000 PJ) | Em conta aberta com documento roubado, o fraudador controla o aparelho e confirma o 2FA. Até 5 vezes o teto, o cliente novo de verdade ainda paga um aluguel ou uma compra com 2FA |

### Regulatórias: valores fixos de norma

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `nightly_limit_exceeded` | Pix de PF para PF entre 20h e 6h no horário local, com a soma da noite (aceitos e 2FA pendentes) acima do limite | R$ 1.000, ou o limite aprovado pelo banco em `POST /sources/{document}/nightly-limit` | Limite noturno do BCB. Um aumento só vale 24 h depois do pedido; uma redução vale na hora. O 2FA não aumenta limite, então a regra reprova |
| `unregistered_device_limit_exceeded` | Aparelho não cadastrado para o pagador, com Pix ou soma do dia no aparelho acima do limite | R$ 200 por Pix e R$ 1.000 por dia | Res. BCB 403/2024. Pede 2FA, e o 2FA confirmado cadastra o aparelho. Vale também no primeiro Pix do cliente |

### Identidade: quem está pagando (teto 50)

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `impossible_travel` | Mesma regra de velocidade, no aparelho cadastrado | 40 pontos; 900 km/h, a partir de 50 km | Aparelho conhecido em local impossível sugere localização falsa ou acesso remoto. 40 pede 2FA sozinho, que é o que resolve a dúvida |
| `ip_unfamiliar` | IP nunca visto nos Pix aceitos do pagador | 10 pontos × N / (N + 5) | Com pouco histórico, IP novo é normal; com muito, é estranho. Usa o mesmo peso 5 da credibilidade. Fora do início frio |
| `location_unfamiliar` | Local nunca visto, com latitude e longitude arredondadas em 2 casas (cerca de 1 km) | 10 pontos × N / (N + 5) | Mesma ideia do IP |
| `channel_unfamiliar` | Canal nunca usado (`app`, `web` e outros) | 15 pontos × N / (N + 5) | Trocar de canal é mais raro que trocar de IP, e o navegador é o caminho de quem tem a senha mas não tem o celular do dono |
| `two_factor_denied_recently` | O pagador recusou um 2FA há pouco tempo | 30 pontos; 24 h | Alguém tentou e não provou ser o dono. 30 faz qualquer outro sinal levar ao 2FA |

### Tempo (teto 40)

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `new_account_above_cap` | Conta de origem nova com acumulado acima do teto | 40 pontos; menos de 30 dias; R$ 1.000 PF, R$ 10.000 PJ | Fraude de conta aberta acontece nos primeiros dias. R$ 1.000 é o mesmo valor do limite noturno da norma. Fica na família tempo porque o teto da família valor (35) não deixaria a regra chegar ao 2FA sozinha |
| `burst_of_pix` | Tentativas do pagador, inclusive as reprovadas | 25 pontos; 5 Pix em 5 min; pagador PJ: 50 | Automação, ou vítima sob pressão fazendo vários Pix seguidos. Empresa paga em lote, por isso tem limite próprio |

### Valor (teto 35)

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `amount_above_baseline` | Acumulado no recebedor acima de um múltiplo da base de comparação | 25 pontos; 5 × base; a partir de R$ 100 | O valor de Pix varia muito, então só 5 vezes o padrão chama atenção |
| `amount_far_above_baseline` | Mesma conta, com múltiplo maior. Exclusiva com a anterior | 35 pontos; 20 × base | Faz o valor escalar: R$ 1.000 e R$ 100.000 não pesam igual. 20 vezes é onde o Pix deixa de parecer uma compra grande e passa a parecer o esvaziamento da conta |
| `monthly_volume_above_typical` | Volume da janela atual acima do típico do pagador para o mesmo período | 20 pontos; 3 × típico; 30 dias; precisa de período de referência do mesmo tamanho | Pega quem esvazia a conta aos poucos, abaixo do múltiplo por Pix |

O piso de R$ 100 é comparado com o acumulado, para dez Pix de R$ 99 não escaparem dele. Valor alto sozinho fica em 35, abaixo do 2FA: uma compra grande, sozinha, não é suspeita.

### Contraparte: quem recebe (teto 70; sinais da relação até 30)

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `destination_account_opened_very_recently` | Conta de destino aberta há pouco tempo | 25 pontos; menos de 7 dias | Conta laranja costuma ser aberta ou alugada pouco antes do uso. 25 fica abaixo do alerta: conta nova sozinha não alerta, porque muita gente abre conta digital toda semana |
| `destination_account_opened_recently` | Conta de destino com menos de 30 dias. Exclusiva com a anterior | 20 pontos; menos de 30 dias | Mesmo sinal, mais fraco |
| `new_destination_above_usual_ceiling` | Recebedor que o pagador nunca pagou (antes das últimas 24 h), recebendo acima do teto habitual | 30 pontos; 1 × teto; recebedor PJ: 3 ×; a partir de R$ 100 | É a assinatura da falsa central. 30 gera alerta sozinho. Para PJ, 3 vezes o teto evita alerta na primeira compra numa loja |
| `destination_receiving_from_many_sources` | Recebedor PF recebendo de pagadores distintos, com Pix a partir do piso | 30 pontos; 5 pagadores em 1 h | Golpe da venda falsa: muitas vítimas pagam a mesma pessoa. O piso tira o racha de conta de valor baixo. Só PF, porque loja recebe de muita gente |
| `destination_rejected_for_other_sources` | Outros pagadores com 2FA recusado, ou reprovados com regra de contraparte, para o mesmo recebedor | 20 pontos; 2 pagadores em 7 dias | A base já desconfiou desse recebedor. Não conta as análises em que ela mesma disparou, para não se realimentar |
| `destination_document_in_many_accounts` | O mesmo documento recebendo em contas de destino diferentes | 30 pontos; 3 contas em 24 h; recebedor PJ: 10 | Laranja espalha o dinheiro em várias contas. Empresa tem várias contas de recebimento, por isso o limite próprio |

As três primeiras são **sinais da relação**: dependem do que este pagador sabe do recebedor. As três últimas são **sinais da base**: dependem do que todos os pagadores viram dele, e só elas levam a contraparte além de 30.

### Redutores: só abatem o que desmentem

| Regra | Lógica | Parâmetros | Por quê |
|-------|--------|------------|---------|
| `long_registered_device` | Aparelho cadastrado para o pagador há tempo | -10 na identidade; 30 dias | Prova quem está pagando. Não abate o valor nem o recebedor, porque na falsa central o aparelho é da própria vítima |
| `known_destination` | O pagador já pagou esse recebedor, antes das últimas 24 h | -20 nos sinais da relação; 3 Pix aceitos | Prova que a relação existe, não que o valor é normal. Pix das últimas 24 h não contam, para aquecer um destino no mesmo dia não funcionar |
| `same_owner` | Pagador e recebedor com o mesmo documento | -30 nos sinais da relação e no valor | Dinheiro do próprio titular. Não abate os sinais da base nem a identidade |

### Parâmetros da política

| Parâmetro | Valor | Por quê |
|-----------|-------|---------|
| Janela de histórico | 90 dias | Pega padrões mensais e trimestrais (aluguel, fatura, mensalidade) sem carregar hábitos antigos. É janela de cálculo: nada é apagado |
| Peso da referência para o pagador (k) | 5 | Com 5 Pix aceitos, o histórico próprio já pesa metade |
| Peso do ticket do BCB na população (k) | 30 | O ticket público só pesa enquanto a instalação tem poucos Pix no par; depois, a mediana real domina |
| Ticket médio de referência | PF→PF R$ 268,64; PF→PJ R$ 112,42; PJ→PF R$ 549,58; PJ→PJ R$ 5.404,53 | Dados abertos do Pix do BCB, setembro de 2026 |
| Piso das regras de valor | R$ 100 | Pelo Relatório de Gestão do Pix (BCB, 2023), mais de 93% dos Pix de PF ficam abaixo de R$ 200. Abaixo de R$ 100, a perda possível não paga a fricção de pedir 2FA para a maioria dos clientes |
| Idade de conta nova | 30 dias | Janela em que a fraude de abertura de conta aparece |
| Teto de conta nova | R$ 1.000 PF; R$ 10.000 PJ | O mesmo valor do limite noturno para PF; 10 vezes para empresa |
| Tetos das famílias | identidade 50; tempo 40; valor 35; contraparte 70 | Identidade sozinha pede 2FA, mas não reprova. Tempo chega ao 2FA sozinho. Valor sozinho não. Só a evidência da base leva a contraparte além de 30 |
| Teto da relação | 30 | Relação somada a um único sinal da base, como uma vaquinha para uma conta nova, não reprova |
| Teto do comportamento | 65 | Tempo, valor e relação somados ficam abaixo de 70: atipicidade sozinha não reprova |
| Limiar de 2FA | 40 | Um sinal forte (40) ou dois sinais médios pedem 2FA |
| Limiar de reprovação | 70 | Exige comportamento somado a evidência, ou evidência forte da base |
| Limiar de alerta | 30 | Um sinal forte sobre o recebedor gera alerta; conta nova sozinha (25) não |
| Validade do 2FA | 10 minutos | O pagador está esperando; um 2FA que não volta logo vira expirado e não consome limite |
| Janela de curto prazo | 24 h | Período em que os Pix do pagador são somados contra o fracionamento, o mesmo horizonte dos limites diários da norma |

## Como as regras viram decisão

1. **Regras eliminatórias.** Se alguma dispara, a análise é `rejected` na hora e grava só as eliminatórias; a pontuação fica nula.
2. **Pontuação de risco.** Cada família é limitada ao seu teto e perde os redutores que a desmentem, sem ficar abaixo de zero:

   identidade     = min(identidade, 50) - aparelho cadastrado
   relação        = min(sinais da relação, 30) - destino conhecido - mesma titularidade
   valor          = min(valor, 35) - mesma titularidade
   comportamento  = min(tempo + valor + relação, 65)
   contraparte    = min(relação + sinais da base, 70)
   pontuação      = identidade + comportamento + (contraparte - relação)

   Abaixo de 40 aprova, de 40 a 69 pede 2FA, a partir de 70 reprova.
3. **Regras regulatórias.** O limite noturno estourado reprova; o limite do aparelho não cadastrado pede no mínimo 2FA. Vale a decisão mais severa entre elas e a faixa da pontuação: `rejected` > `two_factor_required` > `approved`.
4. **Alerta do recebedor.** O risco do recebedor (sinais da relação menos os redutores dela, mais os sinais da base, sem teto) a partir de 30 gera um alerta em `metadata.alerts`. O alerta não muda a decisão: é o aviso que o app do banco mostra antes de o pagador confirmar.
5. **2FA.** Quando a decisão é 2FA, a análise grava a validade (data da transação mais 10 minutos). O banco informa o resultado em `POST /pix/transaction/{id}/two-factor`. O 2FA confirmado entra no histórico e cadastra o aparelho; o recusado vira sinal de risco para os próximos Pix do pagador.

Dois exemplos, com um pagador que faz Pix de R$ 100 há dois meses no mesmo celular:

| Situação | Regras | Pontuação | Decisão |
|----------|--------|-----------|---------|
| Falsa central: R$ 15.000 para uma pessoa nova | valor muito fora do padrão 35; destino novo acima do teto 30; aparelho cadastrado -10 (só na identidade, que está zerada) | 35 + 30 = 65; risco do recebedor 30 | 2FA com alerta |
| R$ 150 para um recebedor que recebeu de 5 pagadores na última hora, em várias contas, e já foi reprovado para outros 2 | destino novo acima do teto 30; fan-in 30; várias contas 30; reprovado para outros 20 | relação 30, contraparte no teto 70 | Reprovado pela evidência da base |

### Modelos de política

| Parâmetro ou ajuste | conservative | balanced | permissive |
|---------------------|--------------|----------|------------|
| Limiar de 2FA | 35 | 40 | 45 |
| Limiar de reprovação | 60 | 70 | 80 |
| Limiar de alerta | 25 | 30 | 30 |
| Teto do comportamento | 105 (a soma dos tetos de tempo, valor e relação) | 65 | 75 |
| Valor fora do padrão | 3 × base | 5 × base | 10 × base |
| Valor muito fora do padrão | 10 × base | 20 × base | 40 × base |

No conservador, comportamento atípico reprova sozinho: ele barra a falsa central sem evidência da base, e por isso também reprova o aluguel pago a um locador novo. No permissivo, o laranja marcado pela base pede 2FA em vez de reprovar. O banco troca de modelo com `based_on_template` e pode ajustar qualquer parâmetro por cima.

### Personalização segura

O banco pode personalizar a política, mas a QI não assina embaixo de qualquer configuração. Toda edição é julgada contra a política de referência (o modelo equilibrado), e nada disso roda na análise do Pix: só na edição da política.

| Situação | Resultado | Por quê |
|----------|-----------|---------|
| Edição mais rígida que a referência | Aceita | Mais fricção é escolha do banco, não risco de fraude |
| Edição mais frouxa, dentro da faixa de segurança | Aceita só com `risk_acknowledged` e `requested_by`, gravados na versão; sem eles, 422 QIT001020 com a lista do que afrouxou | Fica registrado quem afrouxou, quando, por quê e que foi avisado |
| Valor além da faixa de segurança | 422 QIT001018 | O modelo permissivo é, em linhas gerais, a fronteira do que a QI aceita |
| Regra eliminatória desligada | 422 QIT001018 | Elas existem para fraudes em que o 2FA não protege |
| Algum caso-âncora deixa de ser pego | 422 QIT001019 | Afrouxar um pouco cada ajuste não pode somar uma política que deixa passar invasão, laranja marcado ou falsa central |

As faixas e os casos-âncora ficam em `GET /risk-policy/guardrails`. Os valores de norma (limite noturno e Res. BCB 403) continuam fora de qualquer edição.

### Evolução: monitoramento da política do banco

O próximo passo, desenhado mas fora desta entrega, é medir quanto as decisões do banco se afastam da referência e a QI entrar em contato quando a diferença for grande:

1. **Onde roda:** um job na própria instalação do banco, separado da API, de madrugada e lendo de uma réplica. O tempo de análise do Pix não muda.
2. **O que faz:** reprocessa os Pix do período com a política de referência e compara com a decisão que o banco tomou. Isso é possível porque nenhuma regra lê o relógio, tudo é só INSERT e todos os campos do Pix ficam gravados, cada um na sua coluna: o estado do banco no momento de cada Pix é reconstruído pela ordem de gravação.
3. **O que mede:** Pix em que o banco foi mais frouxo que a referência (em quantidade e em valor somado), Pix em que foi mais rígido, e as regras que explicam a diferença.
4. **Quando avisa:** contato imediato se algum Pix aprovado pelo banco seria reprovado por evidência da base; contato recomendado se a parcela de Pix mais frouxos passar de um limite; oportunidade de ajuda se o banco estiver muito mais rígido que a referência.
5. **O que sai do banco:** só o resumo agregado, enviado pelo `connectors/rest_connector.py`. Nenhum CPF, CNPJ, conta, IP, localização, valor individual ou identificador de Pix vai para a QI; soma de valor só com pelo menos 5 Pix. A lista dos Pix divergentes fica no banco, e é lá que os dois olham quando conversam.

Esse desenho segue o sigilo bancário (LC 105/2001) e a LGPD: o banco é o controlador, o reprocesso serve à mesma finalidade da coleta (prevenir fraude), e para a QI só vai informação agregada. Os dados de bancos diferentes nunca são cruzados.

### Limites conhecidos

- **MEI:** todo CNPJ é tratado como PJ, então o MEI fica fora do limite noturno, que é de PF.
- **Golpe do amor e falso investimento:** quando a vítima já pagou o golpista várias vezes, o destino é conhecido e só o valor pontua. O equilibrado aprova; o conservador pede 2FA.
- **Visão de um banco só:** o motor vê apenas os pagadores da própria instalação. Um laranja que recebe de vítimas de vários bancos parece limpo aqui. As marcações de fraude do DICT e o MED ficam fora do escopo.
- **Cadastro do aparelho no primeiro Pix:** sem acesso ao onboarding, o motor considera cadastrado o aparelho do primeiro Pix aceito do cliente.
- **Aparelho no navegador:** o `device_id` do canal `web` muda mais que o de um celular, então gera mais 2FA por aparelho não cadastrado.
- **Ticket médio do BCB:** é média, não mediana, e puxa a referência para cima. Isso só pesa nos primeiros dias da instalação.
- **Datas:** o motor confia na data e no fuso enviados pelo backend do banco, que é quem chama a API.

## Rotas

| Rota | O que faz |
|------|-----------|
| `POST /pix/transaction` | Analisa um Pix. 201 análise nova; 200 o mesmo Pix repetido; 409 mesmo `id` com outro conteúdo |
| `GET /pix/transaction/{id}` | Devolve a análise gravada, com o estado do 2FA (pendente, confirmado, recusado ou expirado) |
| `POST /pix/transaction/{id}/two-factor` | O banco informa o resultado do 2FA (`confirmed` ou `denied`) e a data |
| `POST /sources/{document}/nightly-limit` | O banco informa um limite noturno aprovado para um CPF; o motor calcula quando ele passa a valer |
| `GET /risk-policy` | Versão vigente da política do banco |
| `GET /risk-policy/versions/{version}` | Uma versão anterior, para auditoria |
| `GET /risk-policy/templates` | Os três modelos de política |
| `GET /risk-policy/guardrails` | A política de referência, as faixas de segurança e os casos-âncora |
| `POST /risk-policy/versions` | Cria uma versão nova da política: só o que vier no corpo muda, o resto é herdado. Afrouxar exige o aceite do risco |
| `GET /system-logs` | Os eventos críticos gravados no banco, com filtro por nível, evento, `request_id` e data |

### Códigos de erro

Todo erro sai com código QIT e corpo `{title, description, translation, code}`.

| Código | HTTP | Quando | Rotas |
|---|---|---|---|
| QIT000001 | 400 | O corpo não segue o JSON Schema, não é JSON válido em UTF-8, ou traz número que não é finito (NaN, Infinity), que o JSON Schema não barra | Todas com corpo |
| QIT000002 | 403 | Sem `INTERNAL-TOKEN` ou com token errado | Todas, menos `/` e `/health_check` |
| QIT000404 | 404 | Rota inexistente | Qualquer |
| QIT000405 | 405 | Método não aceito na rota | Qualquer |
| QIT000500 | 500 | Erro inesperado | Qualquer |
| QIT001001 | 404 | Pix sem análise gravada, ou `pix_id` no caminho fora do formato do `id` (um byte nulo, por exemplo, que o Postgres não aceita) | GET do Pix, confirmação de 2FA |
| QIT001002 | 409 | `id` já analisado com outro conteúdo | POST do Pix |
| QIT001003 | 422 | CPF ou CNPJ com dígito verificador errado, ou CPF com todos os dígitos iguais | POST do Pix, limite noturno |
| QIT001004 | 422 | Data com formato certo que não existe no calendário (30 de fevereiro, 25 horas), com ano fora de 1900 a 2999, ou com fuso fora de -12:00 a +14:00 | POST do Pix, confirmação de 2FA, limite noturno |
| QIT001005 | 422 | IP com caracteres válidos que não é um IPv4 nem um IPv6 | POST do Pix |
| QIT001006 | 422 | Conta de origem ou de destino aberta depois da data do Pix | POST do Pix |
| QIT001007 | 409 | Confirmação de 2FA para análise que não pediu 2FA | Confirmação de 2FA |
| QIT001008 | 409 | Confirmação de 2FA com resultado diferente do já gravado | Confirmação de 2FA |
| QIT001009 | 422 | `answered_at` antes do Pix ou depois de `two_factor_expires_at` | Confirmação de 2FA |
| QIT001010 | 422 | Limite noturno pedido para CNPJ | Limite noturno |
| QIT001011 | 404 | Versão de política inexistente | GET de versão |
| QIT001012 | 422 | Código de regra desconhecido na edição | Edição da política |
| QIT001013 | 422 | Tentativa de editar uma regra regulatória | Edição da política |
| QIT001014 | 422 | Ajuste que a regra não usa (janela, limite, limite de PJ ou pontos numa regra sem esse ajuste), limite com mais de 2 casas decimais, limite fracionado em regra de unidade `count` ou `days`, ou limite acima de 3650 em regra de unidade `days` | Edição da política |
| QIT001015 | 422 | A mesma regra repetida na edição | Edição da política |
| QIT001016 | 422 | Política resultante incoerente: reprovação `<=` 2FA, pontos negativos em regra de pontuação, pontos positivos em redutor, faixa de 7 dias `>=` faixa de 30 dias, janela do volume mensal `>=` janela de histórico, teto da relação acima do teto da contraparte, multiplicador do valor muito fora do padrão `<=` o do valor fora do padrão | Edição da política |
| QIT001017 | 409 | Duas edições simultâneas tentaram criar a mesma versão | Edição da política |
| QIT001018 | 422 | Valor além da faixa de segurança, ou regra eliminatória desligada | Edição da política |
| QIT001019 | 422 | Algum caso-âncora deixaria de chegar à decisão mínima. A mensagem lista todos os que falham | Edição da política |
| QIT001020 | 422 | A edição afrouxa a política em relação à referência sem `risk_acknowledged`. A mensagem lista o que afrouxou | Edição da política |

**Por que 400 e 422 são diferentes:** 400 quer dizer "não consegui ler o pedido", e é o schema que decide. 422 quer dizer "li, entendi, e o valor não pode existir": um CPF com o formato certo e o dígito errado, ou uma data que passa no padrão e não existe no calendário. É a mesma separação do Base Service (`InvalidDocumentNumber` e `InvalidBirthdate`).

**Por que pedido recusado não é gravado:** um pedido que não passa no schema ou na validação não é um Pix. Os testes de recusa do Pix e do 2FA conferem pelo GET que nada ficou gravado, e os da política conferem que nenhuma versão nova foi criada. O que pode ficar de uma recusa é o registro no `system_log`, quando ela é de segurança.

## Log e observabilidade

Toda requisição ganha um `request_id`, que volta no header `X-Request-ID` da resposta. Se quem chama manda um `X-Request-ID` válido, ele é reaproveitado. Toda linha de log daquela requisição sai com esse id, então `docker compose logs api | grep <request_id>` mostra a história inteira de um pedido.

### O que o log escreve

| Nível | Evento | Quando | O que traz |
|---|---|---|---|
| INFO | `request_received`, `response_sent` | Toda requisição, menos `/` e `/health_check` | Método, rota, status e tempo em ms |
| INFO | `pix_analyzed` | Análise nova | `id` do Pix, decisão, risco, risco do recebedor, alerta, regras que dispararam e versão da política |
| INFO | `pix_replayed` | O mesmo Pix enviado de novo | `id` do Pix |
| INFO | `two_factor_answered`, `two_factor_replayed` | Resposta do 2FA | `id` do Pix, resultado e se o aparelho foi cadastrado |
| INFO | `nightly_limit_requested` | Pedido de limite noturno | Valor e quando passa a valer |
| INFO | `policy_version_created` | Versão nova da política | Versão, base, motivo, quem pediu e aceite do risco |
| WARNING | `request_refused` | Toda recusa 4xx | Código QIT, status e descrição |
| WARNING | `access_denied` | `INTERNAL-TOKEN` ausente ou errado | Rota e QIT000002. O token recebido nunca é escrito |
| ERROR | `unexpected_error` | Todo 500 | Rota, QIT000500 e o traceback |

Nenhuma linha traz CPF, CNPJ, conta ou o corpo da requisição. O documento na rota do limite noturno sai como `/sources/***/nightly-limit`. Caracteres de controle viram `?`, para ninguém conseguir escrever uma linha falsa no log.

### O que é crítico vai para o banco

O container é descartável: o que fica só na saída do processo some junto com ele. Por isso os eventos críticos também são gravados na tabela `system_log`, que aceita apenas INSERT como as outras:

- todo log de nível ERROR ou acima, com o traceback (todo 500 cai aqui);
- `policy_version_created`: quem mudou a política e por quê;
- `access_denied`: chamada sem o token certo;
- as recusas de segurança da política: QIT001018, QIT001019 e QIT001020.

O Pix analisado não vai para o `system_log`: a análise, as regras e os motivos já ficam em `pix_analysis` e `pix_analysis_rule_hit`.

A gravação usa uma conexão própria, fora da transação da requisição. Num 500 a requisição é desfeita, e o registro do erro fica. Com o banco fora do ar, a API responde do mesmo jeito e avisa no stderr que o registro não foi gravado.

### `GET /system-logs`

Exige `INTERNAL-TOKEN` e devolve `{"logs": [...]}`, do mais novo para o mais antigo. Cada registro traz `created_at`, `level`, `event`, `request_id`, `message`, `http_method`, `path`, `http_status`, `error_code`, `details` e `stack_trace`.

| Filtro | Formato |
|---|---|
| `level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL` |
| `event` | Nome do evento, como `access_denied` |
| `request_id` | O `X-Request-ID` da requisição |
| `since` | Data com fuso. O `+` do fuso vai como `%2B` na URL |
| `limit` | De 1 a 200. O padrão é 50 |

Filtro inválido devolve 400 QIT000001, e data impossível em `since` devolve 422 QIT001004.

### Alarmes

Métricas e alarmes ficam na infraestrutura, fora do repositório. A tabela deixa as regras simples de montar:

- algum `unexpected_error` nos últimos 5 minutos: alguém abre o `stack_trace` pelo `request_id`;
- muitos `access_denied` seguidos: alguém tentando adivinhar o token;
- `policy_version_created` com aceite do risco: o time de risco revisa a mudança.

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

São 370 testes, todos pela API, sem ler o banco. Rode num banco recém-criado: os testes contam com a população de Pix que eles mesmos geram.

A API atende em `http://localhost:3000`. Toda rota, menos `/` e `/health_check`, exige o header `INTERNAL-TOKEN` (o padrão é `default_token`).

Analisar o Pix de exemplo do desafio:

```bash
curl -X POST http://localhost:3000/pix/transaction -H "Content-Type: application/json" -H "INTERNAL-TOKEN: default_token" -d '{"id": "pix-000123", "amount": 150000, "transaction_date": "2026-10-17T22:15:00-03:00", "source_account": {"branch": "0001", "account_number": "88213", "opening_date": "2025-03-02T10:00:00-03:00", "owner": {"document_number": "123.456.789-09"}}, "destination_account": {"participant": "60701190", "branch": "3675", "account_number": "10442", "opening_date": "2026-10-10T09:00:00-03:00", "owner": {"document_number": "987.654.321-00"}}, "source": {"device_id": "dvc-9f2c71a8", "channel": "app", "ip": "198.51.100.23", "geolocation": {"latitude": -23.56, "longitude": -46.65}}}'
```

O exemplo do desafio volta `rejected`: é um Pix de R$ 1.500 entre duas PF às 22h15, acima do limite noturno de R$ 1.000. A resposta traz também o limite do aparelho não cadastrado, o destino novo acima do teto e a conta de destino recente, com o motivo de cada um, e o alerta do recebedor.

Consultar a análise gravada:

```bash
curl http://localhost:3000/pix/transaction/pix-000123 -H "INTERNAL-TOKEN: default_token"
```

Ver a política vigente:

```bash
curl http://localhost:3000/risk-policy -H "INTERNAL-TOKEN: default_token"
```

Seguir uma requisição no log, pelo `X-Request-ID` que voltou na resposta:

```bash
docker compose logs api | grep <request_id>
```

Ver os erros gravados no banco:

```bash
curl "http://localhost:3000/system-logs?level=ERROR" -H "INTERNAL-TOKEN: default_token"
```

O banco só lê o `database/database.sql` quando nasce. Depois de mudar esse arquivo:

```bash
docker compose down -v
docker compose up -d --build --wait
```
