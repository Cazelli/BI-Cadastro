# BI Cadastro Copel

Dashboard Streamlit para análise consolidada das unidades consumidoras do arquivo
`base_consolidada_BI.csv`, preparado sem campos pessoais diretos.

## Recursos

- login protegido por hash de senha;
- KPIs consolidados na página inicial;
- ajuda contextual nos cards, com a regra usada em cada cálculo;
- filtros globais de situação, município, fase, etapa, finalidade e fabricante;
- atalhos de data para o período Inicial e para o último dia de cada mês;
- páginas comparativas de UCs, veículos, recarga, geração distribuída e qualidade;
- alertas de UCs sem comunicação, incluindo o atraso em dias;
- disponibilidade mensal de dados e consulta das maiores lacunas por UC;
- histórico acumulado de alertas desde 01/03/2026, com valores anteriores e novos por UC;
- consulta operacional sem nome, telefone ou e-mail do titular;
- atualização automática ao substituir o arquivo CSV no repositório;
- identidade visual com marcas COPEL e Essenz Soluções em todas as páginas.

As marcas exibidas no cabeçalho foram obtidas nos sites oficiais da
[COPEL](https://www.copel.com/site/) e da
[Essenz Soluções](https://www.essenzsolucoes.com/).

As páginas de medição usam `relatorio_medicao/relatorio_alertas_por_uc.csv`
e `relatorio_medicao/detalhe_gaps.csv`. Substitua esses arquivos por uma nova
execução do relatório para atualizar os alertas e os gráficos.

## Executar localmente

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Acesse `http://localhost:8501` e use o login fornecido pelo administrador.

## Publicar gratuitamente no Streamlit Community Cloud

1. Envie estes arquivos para um repositório no GitHub.
2. Acesse [share.streamlit.io](https://share.streamlit.io/) e conecte sua conta GitHub.
3. Crie um app escolhendo o repositório, a branch principal e `app.py` como arquivo inicial.
4. Publique. Cada novo commit na branch selecionada atualiza o app automaticamente.

> A base do BI não contém nome, telefone, e-mail, código de cliente, medidor,
> placa ou coordenada individual. Os identificadores de UC continuam presentes
> para permitir o monitoramento e devem ser tratados como dados pseudonimizados.

## Atualizar a base

1. Coloque o novo relatório na pasta `data` com o nome
   `mdm-sandbox_clientes_novo-YYYYMMDD-YYYYMMDD.csv`.
2. Execute:

   ```powershell
   py update_base.py
   ```

3. Revise o resumo exibido no terminal e a página **Atualizações e alertas**.
4. Faça commit e push de `base_consolidada_BI.csv`,
   `data/historico_alertas.csv`, `data/ultima_atualizacao_alertas.csv` e
   `data/ultima_atualizacao_resumo.json`.

O atualizador escolhe automaticamente o relatório com a data final mais recente.
Somente UCs que já existem em `base_consolidada_BI.csv` são atualizadas. A
coluna `amostra` e todas as UCs extras do relatório são ignoradas. UCs da base
que não apareçam no relatório permanecem inalteradas. Uma cópia de segurança
local é criada em `data/backups/` antes de cada atualização.

O processo sincroniza na base BI as colunas `DT_SITUACAO_UC`
(`data_situacao`), `DT_MUD_TIT` (`max_data_tt`) e `MUD_TIT`. Esta última recebe
`S` quando `DT_MUD_TIT` é igual ou posterior a 01/03/2026; nos demais casos
permanece vazia. Durante a leitura, o relatório MDM é regravado sem as colunas
`cliente`, `nome`, `celular`, `email` e `medidor`.

Cada execução acrescenta ao `data/historico_alertas.csv` os novos eventos sem
duplicar os já registrados. O histórico contém somente mudanças com data igual
ou posterior a 01/03/2026, incluindo mudança de titularidade, desligamentos
(categoria única para DS e CR, diferenciados no detalhe),
mudança de classe, ativação de tarifa especial e alterações de geração
distribuída. Na página **Atualizações e alertas**, os seletores de período aceitam
uma ou várias opções. **Inicial** considera registros até 28/02/2026 e **Março**
considera o mês inteiro, de 01/03 a 31/03. A página apresenta primeiro os
indicadores, gráficos e a tabela exclusivos do relatório mais recente. Em seguida,
apresenta uma segunda visão com os totais históricos e seus próprios filtros,
gráficos e tabela.

Os relatórios MDM, backups e as antigas bases `base_consolidada_copel.csv` e
`.xlsx` ficam fora do Git. Os arquivos de alertas publicados não incluem nome,
telefone ou e-mail. Se as bases antigas já foram publicadas, removê-las em um
novo commit não apaga versões anteriores do histórico do Git; nesse caso, use um
novo repositório ou faça uma limpeza controlada do histórico antes de torná-lo
público.
# BI Cadastro

## Monitoramento automático do Streamlit

O workflow `.github/workflows/monitor-streamlit.yml` acessa o app às 00:01,
06:01, 12:01 e 18:01 no horário de Brasília. Se o Streamlit estiver suspenso,
o agente aciona o botão de despertar e envia um e-mail. Se ocorrer uma falha,
envia um e-mail de erro e tenta salvar uma captura de tela nos artefatos da
execução.

### Configuração no GitHub

1. No repositório, abra **Settings → Secrets and variables → Actions**.
2. Em **Repository secrets**, cadastre:
   - `EMAIL_REMETENTE`: endereço Gmail usado para enviar os alertas.
   - `EMAIL_SENHA`: senha de app do Gmail, não a senha normal da conta.
3. Opcionalmente, em **Variables**, cadastre `EMAIL_DESTINO`. Se não for
   cadastrada, será usado `pedro.cazelli@essenzsolucoes.com`.
4. Envie os arquivos para a branch padrão do GitHub.
5. Abra **Actions → Monitor Streamlit → Run workflow** para testar manualmente.

Na conta Google do remetente, a verificação em duas etapas deve estar ativa.
Depois, crie uma senha de app em **Conta Google → Segurança → Senhas de app** e
salve esse valor no secret `EMAIL_SENHA`.

O agendamento do GitHub Actions usa UTC e pode iniciar alguns minutos depois do
horário previsto em períodos de alta demanda. O cron configurado corresponde ao
horário de Brasília enquanto o fuso permanecer em UTC-3.
