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

### Fluxo integrado Cadastro / GD / duas bases

O comando `python update_base.py` agora reconstrói o histórico a partir de
`../Cadastro`, gera a posição GD mais recente e atualiza **as duas bases**:
`base_consolidada_BI.csv`, sem dados pessoais diretos, e
`../base_consolidada_copel.xlsx`, mantendo os dados privados e campos de projeto.
Também gera `../Cadastro/gd_report_atual/Relatorio_GD_Atual.xlsx` e suas tabelas CSV.
O escopo permanece exatamente nas UCs já presentes no BI; vínculos externos são
contexto e não acrescentam UCs à população. As demais linhas da base completa
permanecem preservadas.

Na pasta Copel, prepare o ambiente e execute:

```powershell
python -m venv .cadastro-venv
.\.cadastro-venv\Scripts\python.exe -m pip install -r BI-Cadastro/requirements.txt
.\.cadastro-venv\Scripts\python.exe BI-Cadastro/update_base.py --dry-run
.\.cadastro-venv\Scripts\python.exe BI-Cadastro/update_base.py
```

`atualizar_base_consolidada_copel.py` e `Cadastro/build_gd_report.py` chamam o
mesmo fluxo. A execução com `--dry-run` prepara os resultados em
`data/backups/pipeline-staging`, sem substituir as bases. Antes da substituição,
as saídas existentes são copiadas para `data/backups/<data-hora>`; em falha na
substituição, o fluxo restaura as saídas já alteradas. Não faça commit dessa pasta.

Novas exportações completas devem ficar em `../Cadastro/DADOS_GD_GERAL`:
`YYYY-MM-DD-consulta_GD.csv`, `YYYY-MM-DD-consulta_BEN.csv` e
`YYYY-MM-DD-consulta_UC.csv`. Lotes incompletos são sinalizados; a posição atual
continua no último lote completo. Os arquivos MDM históricos ficam em Cadastro;
arquivos MDM em `data/` complementam datas não presentes nessa pasta. O export
anual sem data confiável é excluído e a correção conhecida de `202606011` é mantida.
Fontes originais não são higienizadas nem regravadas pelo novo fluxo.

A baseline usa `Amostra Final - Tarifa Mobiflex - 21.07.2026.xlsx` como referência
de 31/12/2025, auditada contra o primeiro export completo de GD. A fonte GD tem
precedência; divergências ficam em `gd_auditoria_baseline.csv`. Datas cadastradas
permitem reconstrução retrospectiva, mas potência e classificação não têm vigência
histórica própria: sua condição em 2025 não pode ser certificada apenas pelo
export de outubro. Correções de baseline não são novas entradas em 2026.

Na amostra real, `GD2` do Grupo Experimental e `Qual GD (GDI, GDII, GDI/GDII)`
do Grupo Controle e Reservas são declarações de tipo, sem distinguir UC geradora
de beneficiária. `0`/`Sem GD` indicam ausência declarada; `?` e vazios permanecem
desconhecidos. A coluna `Se tem ou Não GD` contém identificadores de UC e não é
usada como indicador. A auditoria registra aba, linha, coluna e valor original,
inclusive as composições GDI/GDII. Ausência de informação não conta como erro.
Uma geradora sem data de solicitação aparece como primeira observação no export;
sua presença em 2025 não é presumida.

Regras aprovadas: início geradora = `DTA_SOL_ACES_KCG`; início beneficiária =
`DTA_INC_XBG`; potência em kW. A maior potência conflitante é adotada com
`REVISAO_MANUAL=S` e motivo em `STATUS_QUALIDADE`. Linhas GDI/GDII são deduplicadas
por registro e `PCT_DIS_KCD` divide a potência; `PCT_RAT_XBG` é rateio de créditos.
Cada parcela é `potência total ativa × PCT_DIS_KCD / 100`, inclusive quando os
percentuais foram truncados na fonte. Exemplo: UC 105145530, 10 kW com 67% GDI
e 33% GDII, resulta em 6,7 kW GDI e 3,3 kW GDII. A potência de registros encerrados
não é somada nem usada para ajustar retroativamente as parcelas calculadas.
Registros ativos distintos com a mesma potência conhecida e a mesma classificação,
subtipo e distribuição percentual válida são unificados para a análise: uma só
potência e classificação, sem alerta de multiplicidade. Os IDs ficam preservados
em `REGISTROS_GD_ATIVOS`, com a decisão em `TRATAMENTO_REGISTROS_GD`; os vínculos
também identificam os registros do gerador relacionado. Diferenças de potência,
tipo, subtipo ou percentuais, e informações incompletas, continuam para revisão.
Ausência no export não comprova encerramento. Benefício próprio só existe quando
registrado na fonte. Potência externa associada não deve ser somada entre UCs.

Exceção aprovada para a UC **93911335**: somar as potências ativas distintas após
consolidar registros equivalentes. As parcelas GDI/GDII vêm da potência e dos
percentuais de cada registro ativo. No export atual: 4 kW GDI + 6,25 kW GDII =
10,25 kW; percentuais agregados de 39,024390% e 60,975610%, respectivamente.
Manter revisão manual: trata-se de possível inconsistência cadastral, não de
correção da fonte. `REGRA_POTENCIA_GD`, `OBSERVACAO_EXCECAO_GD` e o manifesto
identificam a decisão; `PCT_POTENCIA_*` guarda os percentuais derivados com seis
casas decimais. O padrão para as demais UCs continua sendo a maior potência.

As saídas `gd_atual`, `gd_snapshots`, `gd_vinculos`, `gd_historico_2026`,
`gd_qualidade`, `gd_auditoria_baseline` e `gd_manifesto` alimentam a página GD.
`historico_alertas.csv` inclui todo 2026, com filtro do experimento desde março.
Alertas identificam data cadastrada, data observada, intervalo de observações,
arquivos anterior/atual, reconstruções e condições persistentes. A primeira
observação de um campo não é uma mudança, exceto evento explicitamente datado.
MDM e GD mostram suas datas separadamente.

Teste as regras e o fluxo completo com:

```powershell
.\.cadastro-venv\Scripts\python.exe -m unittest discover -s BI-Cadastro -p test_cadastro_pipeline.py -v
```

O procedimento abaixo descreve o atualizador legado, mantido apenas como
referência. Para novas atualizações, use o fluxo integrado acima.

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
que não apareçam no relatório permanecem inalteradas.

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

Os relatórios MDM e as antigas bases `base_consolidada_copel.csv` e `.xlsx`
ficam fora do Git. Os arquivos de alertas publicados não incluem nome,
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
