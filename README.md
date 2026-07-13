# BI Cadastro Copel

Dashboard Streamlit para análise consolidada das unidades consumidoras do arquivo `base_consolidada_copel.csv`.

## Recursos

- login protegido por hash de senha;
- KPIs consolidados na página inicial;
- filtros globais de situação, município, fase, etapa, finalidade e fabricante;
- páginas comparativas de UCs, veículos, recarga, geração distribuída e qualidade;
- consulta operacional sem nome, telefone ou e-mail do titular;
- atualização automática ao substituir o arquivo Excel no repositório.

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

Substitua `base_consolidada_copel.csv` por uma nova versão UTF-8 mantendo o nome e as colunas atuais. Depois, faça commit e push; o deploy será reconstruído automaticamente.
