# Guia do Usuário do AtendimentoBot

Este guia foi escrito para quem vai usar o bot no Telegram no dia a dia.

O AtendimentoBot trabalha com dois perfis:

- `Administrador`: configura a empresa, a base de conhecimento e o comportamento do agente.
- `Cliente`: entra pelo link enviado pelo administrador e usa o bot apenas para conversar.

## Visão geral

O bot pode:

- responder perguntas com base nos documentos enviados pela empresa;
- usar FAQs para respostas rápidas;
- informar horário de atendimento;
- encaminhar o usuário para um contato humano quando necessário;
- permitir que o administrador pause ou reative o agente.

## Antes de começar

Para usar corretamente:

1. O administrador deve abrir o bot no Telegram e enviar `/start`.
2. O cliente deve entrar no atendimento usando o link compartilhado pelo administrador.
3. O bot precisa estar configurado pelo administrador antes de atender com a base de conhecimento.

## Guia do Administrador

### 1. Primeiro acesso

No primeiro uso, envie `/start` e siga o onboarding. O bot vai pedir:

1. Nome da empresa
2. Nome do assistente
3. Mensagem de saudação
4. Instruções de comportamento

Ao final, revise os dados e confirme.

Se quiser interromper um fluxo guiado, use `/cancelar`.

### 2. Primeira configuração recomendada

Depois do cadastro, a sequência mais prática é:

1. Enviar documentos com `/upload` ou mandar arquivos diretamente no chat
2. Cadastrar perguntas frequentes com `/faq`
3. Definir horário com `/horario`
4. Definir contato humano com `/fallback`
5. Configurar a imagem do agente com `/imagem`
6. Testar o agente no próprio chat
7. Gerar e compartilhar o link com `/link`

### 3. Como enviar documentos

Você pode enviar documentos de duas formas:

- usar `/upload` para entrar no modo guiado;
- mandar arquivos diretamente no chat, sem entrar no modo de upload.

Formatos aceitos:

- `.pdf`
- `.docx`
- `.pptx`
- `.txt`
- `.md`
- `.csv`

Boas práticas para os documentos:

- prefira arquivos com texto selecionável;
- mantenha o conteúdo atualizado;
- envie materiais objetivos e relevantes para o atendimento;
- se substituir um arquivo com o mesmo nome, a base será reindexada automaticamente.

No modo `/upload`:

1. Envie um arquivo por vez.
2. Aguarde a confirmação de processamento.
3. Repita o envio dos demais arquivos.
4. Finalize com `/pronto`.

### 4. Como gerenciar a base de conhecimento

Use `/documentos` para:

- ver a lista de arquivos enviados;
- reprocessar um documento específico;
- excluir documentos;
- reindexar toda a base.

Se a empresa ainda não tiver documentos, o agente não responderá com conhecimento da base.

### 5. Como configurar FAQs

Use `/faq` para cadastrar respostas rápidas para perguntas recorrentes.

Fluxo de cadastro:

1. Envie `/faq`
2. Escolha adicionar uma nova FAQ
3. Informe a pergunta
4. Informe a resposta

As FAQs são úteis para perguntas padronizadas, como:

- prazo de entrega;
- formas de pagamento;
- política de troca;
- canais de contato.

### 6. Como configurar a imagem do agente

Use `/imagem` para enviar uma foto do Telegram ou um arquivo de imagem.

Formatos aceitos:

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`
- `.bmp`
- `.gif`

Regras importantes:

- a imagem fica vinculada somente ao seu agente;
- o sistema converte a imagem para JPG;
- para remover a imagem atual, use `/imagem remover`.

### 7. Como configurar horário de atendimento

Use `/horario` para informar o horário operacional da empresa.

Exemplo:

```text
Seg a Sex, 08h às 18h
```

Quando esse campo estiver configurado, o bot pode responder diretamente perguntas sobre horário.

Para remover o horário:

```text
/horario limpar
```

### 8. Como configurar fallback para atendimento humano

Use `/fallback` para definir um contato humano, como:

- WhatsApp;
- telefone;
- e-mail;
- outro canal oficial da empresa.

Exemplo:

```text
WhatsApp (11) 99999-9999
```

Se o usuário pedir um atendente humano, o bot poderá orientar esse contato.

Para remover o fallback:

```text
/fallback limpar
```

### 9. Como pausar ou reativar o agente

Use:

- `/pausar` para interromper as respostas automáticas;
- `/ativar` para voltar ao funcionamento normal.

Quando o agente estiver pausado, o usuário receberá apenas a orientação operacional disponível, como horário e contato humano.

### 10. Como editar a configuração

Use `/editar` para alterar:

- nome da empresa;
- nome do assistente;
- saudação;
- instruções do bot.

### 11. Como acompanhar o status

Use:

- `/painel` para abrir o painel principal;
- `/status` para ver um resumo da configuração atual;
- `/ajuda` para consultar os comandos disponíveis.

O painel mostra, entre outras informações:

- situação do agente;
- quantidade de documentos;
- quantidade de FAQs;
- quantidade de clientes vinculados;
- status da imagem, horário e fallback.

### 12. Como compartilhar com clientes

Use `/link` para gerar o link de atendimento da sua empresa.

Depois:

1. copie o link enviado pelo bot;
2. compartilhe com seus clientes;
3. peça que eles abram o link no Telegram.

Observação:

- o bot precisa ter um `username` público no Telegram para gerar o link.

### 13. Como testar o agente

O administrador pode testar o atendimento no mesmo chat do bot.

Faça testes como:

- perguntas sobre o conteúdo dos documentos;
- perguntas iguais às FAQs cadastradas;
- perguntas sobre horário;
- pedido de atendimento humano.

Sempre teste novamente depois de:

- enviar novos documentos;
- alterar FAQs;
- trocar instruções;
- configurar horário ou fallback.

### 14. Comandos do Administrador

| Comando | Uso |
|---|---|
| `/start` | Inicia a configuração ou reabre o fluxo principal |
| `/meuid` | Mostra o ID do Telegram do usuário atual |
| `/painel` | Abre o painel principal |
| `/link` | Gera o link para clientes |
| `/upload` | Inicia o envio guiado de documentos |
| `/documentos` | Abre a gestão da base de conhecimento |
| `/imagem` | Configura ou remove a imagem do agente |
| `/pausar` | Pausa o agente |
| `/ativar` | Reativa o agente |
| `/horario` | Configura o horário de atendimento |
| `/fallback` | Configura o contato humano |
| `/faq` | Gerencia perguntas frequentes |
| `/editar` | Edita dados do agente |
| `/status` | Mostra o status da configuração |
| `/reset` | Apaga toda a configuração atual e reinicia do zero |
| `/ajuda` | Mostra ajuda rápida |
| `/cancelar` | Cancela um fluxo guiado em andamento |

## Guia do Cliente

### 1. Como entrar no atendimento

1. Receba o link enviado pela empresa.
2. Abra o link no Telegram.
3. O bot conectará seu usuário ao atendimento.
4. Envie sua mensagem normalmente.

### 2. O que o cliente pode fazer

O cliente usa o bot principalmente para conversar.

Os comandos mais comuns são:

- `/start` para abrir novamente o atendimento;
- `/meuid` para ver seu ID do Telegram;
- `/ajuda` para ver instruções rápidas;
- `/sair` para sair do atendimento atual.

### 3. O que esperar nas respostas

Dependendo da configuração feita pela empresa, o bot pode:

- responder com base nos documentos cadastrados;
- responder usando FAQs;
- informar horário de atendimento;
- indicar contato humano;
- avisar que o atendimento está em preparação;
- avisar que o agente está pausado.

### 4. Como sair do atendimento

Se quiser desvincular seu usuário desse atendimento, use:

```text
/sair
```

Para entrar novamente depois disso, será necessário abrir o link enviado pela empresa.

### 5. Como descobrir seu ID no Telegram

Se a empresa pedir seu identificador para suporte ou testes, use:

```text
/meuid
```

O bot responderá com o seu ID do Telegram e o ID do chat atual.

## Limites importantes

Os principais limites de uso são:

| Recurso | Limite |
|---|---|
| Documento por arquivo | 20 MB |
| Imagem por arquivo | 10 MB |
| Documentos por empresa | 50 |
| FAQs por empresa | 100 |
| Mensagem enviada ao agente | 4.000 caracteres |

## Problemas comuns

### O bot não responde como esperado

Verifique se:

- existem documentos carregados;
- o agente está ativo;
- a pergunta está coberta pelos documentos ou FAQs;
- o fallback humano está configurado para casos fora da base.

### O documento foi recusado

Confirme se:

- o formato é suportado;
- o arquivo está dentro do limite de tamanho;
- o documento possui texto extraível;
- o limite total de documentos da empresa não foi atingido.

### O cliente não consegue entrar

Confira se:

- o link foi gerado com `/link`;
- o link é o mais recente e foi copiado completo;
- o cliente abriu o link no Telegram.

### O comando `/link` não funciona

Nesse caso, normalmente o bot ainda não tem um nome de usuário público configurado no Telegram.

## Boas práticas de uso

- mantenha a base de documentos enxuta e atualizada;
- use FAQ para perguntas que se repetem muito;
- escreva instruções claras para o comportamento do agente;
- configure horário e fallback antes de compartilhar com clientes;
- teste o atendimento antes de divulgar o link;
- revise periodicamente os documentos e FAQs.
