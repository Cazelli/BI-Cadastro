# BI Cadastro Copel

Dashboard Streamlit para análise consolidada das unidades consumidoras do arquivo `base_consolidada_copel.csv`.

## Recursos

- login protegido por hash de senha;
- KPIs consolidados na página inicial;
- filtros globais de situação, município, fase, etapa, finalidade e fabricante;
- páginas comparativas de UCs, veículos, recarga, geração distribuída e qualidade;
- histórico acumulado de alertas desde 01/03/2026, com valores anteriores e novos por UC;
- consulta operacional sem nome, telefone ou e-mail do titular;
- atualização automática ao substituir o arquivo CSV no repositório;
- identidade visual com marcas COPEL e Essenz Soluções em todas as páginas.

As marcas exibidas no cabeçalho foram obtidas nos sites oficiais da
[COPEL](https://www.copel.com/site/) e da
[Essenz Soluções](https://www.essenzsolucoes.com/).

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

> A autenticação reduz o acesso casual, mas dados pessoais não devem ser publicados em um repositório público. Use um repositório privado compatível com sua conta do Streamlit Community Cloud e limite o acesso ao app quando necessário.

## Atualizar a base

1. Coloque o novo relatório na pasta `data` com o nome
   `mdm-sandbox_clientes_novo-YYYYMMDD-YYYYMMDD.csv`.
2. Execute:

   ```powershell
   py update_base.py
   ```

3. Revise o resumo exibido no terminal e a página **Atualizações e alertas**.
4. Faça commit e push de `base_consolidada_copel.csv`,
   `data/historico_alertas.csv`, `data/ultima_atualizacao_alertas.csv` e
   `data/ultima_atualizacao_resumo.json`.

O atualizador escolhe automaticamente o relatório com a data final mais recente.
Somente UCs que já existem em `base_consolidada_copel.csv` são atualizadas. A
coluna `amostra` e todas as UCs extras do relatório são ignoradas. UCs da base
que não apareçam no relatório permanecem inalteradas. Uma cópia de segurança
local é criada em `data/backups/` antes de cada atualização.

O processo também sincroniza no CSV e no XLSX as colunas
`DT_SITUACAO_UC` (`data_situacao`), `DT_MUD_TIT` (`max_data_tt`) e
`MUD_TIT`. Esta última recebe `S` quando `DT_MUD_TIT` é igual ou posterior a
01/03/2026; nos demais casos permanece vazia.

Cada execução acrescenta ao `data/historico_alertas.csv` os novos eventos sem
duplicar os já registrados. O histórico contém somente mudanças com data igual
ou posterior a 01/03/2026, incluindo mudança de titularidade, desligamento,
mudança de classe, ativação de tarifa especial e alterações de geração
distribuída. Na página **Atualizações e alertas**, os seletores de período aceitam
uma ou várias opções. **Inicial** corresponde exclusivamente a 01/03/2026 e
**Março** corresponde ao restante do mês, evitando contar o mesmo evento duas
vezes quando ambas as opções forem selecionadas. A página apresenta primeiro os
indicadores, gráficos e a tabela exclusivos do relatório mais recente. Em seguida,
apresenta uma segunda visão com os totais históricos e seus próprios filtros,
gráficos e tabela.

Os relatórios brutos e backups ficam fora do Git por poderem conter dados
pessoais. Os arquivos de alertas publicados não incluem nome, telefone ou e-mail.
