"""Streamlit views for the generated, privacy-filtered Cadastro/GD datasets."""
from pathlib import Path
import json
import re

import pandas as pd
import plotly.express as px
import streamlit as st

DATA = Path(__file__).with_name("data")
LAYOUT_VERSION = "GD-2026.11.11.2"


@st.cache_data
def load_gd(mtimes):
    del mtimes
    files = ("gd_atual", "gd_snapshots", "gd_vinculos", "gd_historico_2026", "gd_qualidade", "gd_auditoria_baseline")
    frames = {name: pd.read_csv(DATA / f"{name}.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig") for name in files}
    manifest = json.loads((DATA / "gd_manifesto.json").read_text(encoding="utf-8"))
    return frames, manifest


def download(frame, name, key):
    st.download_button("Baixar CSV", frame.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       name, "text/csv", key=key)


def type_category(row):
    if row["GD_GERADORA"] == "S":
        value = row["TIPO_GD_GERA"]
    elif row["GD_BENEFICIARIA"] == "S":
        value = row["TIPO_GD_BENE"]
    else:
        return "Sem GD identificada"
    types = set(re.findall(r"\bGDII?\b", str(value).upper()))
    return "GDI/GDII" if types == {"GDI", "GDII"} else next(iter(types)) if len(types) == 1 else "Não informado"


def own_power(current):
    generators = current[current["GD_GERADORA"].eq("S")].drop_duplicates("NUM_UC").set_index("NUM_UC")
    power = pd.to_numeric(generators["POTENCIA_INSTALADA_KW"], errors="coerce")
    return power[power.ge(0)].dropna()


def average_power_by_type(current):
    generators = current[current["GD_GERADORA"].eq("S")].drop_duplicates("NUM_UC")
    result = []
    for label, column in [("GDI", "POTENCIA_GDI_KW"), ("GDII", "POTENCIA_GDII_KW"),
                          ("Outros", "POTENCIA_OUTROS_KW"), ("Sem classificação", "POTENCIA_SEM_CLASSIFICACAO_KW")]:
        values = pd.to_numeric(generators[column], errors="coerce")
        values = values[values.gt(0)].dropna()
        if not values.empty:
            result.append({"Classificação": label, "Potência média (kW)": values.mean(), "UCs geradoras": len(values)})
    return pd.DataFrame(result, columns=["Classificação", "Potência média (kW)", "UCs geradoras"])


def power_label(value):
    return "—" if pd.isna(value) else f"{value:,.2f}"


def render_cards(current):
    generator = current["GD_GERADORA"].eq("S")
    beneficiary = current["GD_BENEFICIARIA"].eq("S")
    count = lambda mask: current.loc[mask, "NUM_UC"].nunique()
    cards = st.columns(4)
    cards[0].metric("UCs geradoras", count(generator), help="UCs distintas com geração própria na posição e nos filtros selecionados. Inclui as que também são beneficiárias.")
    cards[1].metric("UCs beneficiárias", count(beneficiary), help="UCs distintas com vínculo de beneficiária no relatório, incluindo vínculo com a própria UC e rateio cadastrado de 0%. Inclui as que também geram; não comprova recebimento de créditos.")
    cards[2].metric("UCs geradoras e beneficiárias", count(generator & beneficiary), help="UCs que têm geração própria e também um vínculo de beneficiária, com a própria geração ou com outra UC geradora. É a interseção dos dois primeiros cards.")
    cards[3].metric("UCs para revisão", count(current["REVISAO_MANUAL"].eq("S")), help="UCs com informações pendentes ou exceções que exigem revisão manual.")
    power = own_power(current)
    extra = st.columns(4)
    extra[0].metric("Potência média (kW)", power_label(power.mean()), help="Média aritmética da potência própria por UC geradora com valor conhecido. Cada UC entra uma vez. Beneficiárias sem geração própria e potências externas associadas não entram; valores ausentes não viram zero.")
    extra[1].metric("Potência máxima (kW)", power_label(power.max()), help="Maior potência própria de uma única UC geradora no recorte. A UC aparece abaixo. Usa a potência consolidada, incluindo as exceções aprovadas e sinalizadas.")
    extra[2].metric("Potência mínima (kW)", power_label(power.min()), help="Menor potência própria conhecida entre as UCs geradoras do recorte. Valores ausentes são excluídos; uma potência conhecida de zero é mantida.")
    extra[3].metric("Total de UCs com GD", count(generator | beneficiary), help="UCs geradoras ou beneficiárias, contadas uma única vez. Uma UC com os dois perfis não é duplicada: geradoras + beneficiárias − geradoras e beneficiárias.")
    if not power.empty:
        for card, value in ((extra[1], power.max()), (extra[2], power.min())):
            ucs = sorted(power[power.eq(value)].index.astype(str))
            card.caption("UC(s): " + ", ".join(ucs[:4]) + (f" e mais {len(ucs) - 4}" if len(ucs) > 4 else ""))


def history_view(history, key="gd"):
    if history.empty:
        st.info("Nenhum evento de GD no recorte selecionado.")
        return
    view = history.copy()
    controls = st.columns(3)
    period = controls[0].selectbox("Período", ["Todo o ano de 2026", "Experimento: desde 01/03/2026"], key=f"{key}_period")
    if period.startswith("Experimento"):
        view = view[view["DATA_ALERTA"].ge("2026-03-01")]
    field = controls[1].multiselect("Alteração", sorted(history["CAMPO"].unique()), key=f"{key}_field")
    basis = controls[2].multiselect("Base da data", sorted(history["BASE_DATA"].unique()), key=f"{key}_basis")
    if field:
        view = view[view["CAMPO"].isin(field)]
    if basis:
        view = view[view["BASE_DATA"].isin(basis)]
    controls2 = st.columns(3)
    nature = controls2[0].multiselect("Natureza do registro", sorted(history["NATUREZA"].unique()), key=f"{key}_nature")
    source_dates = controls2[1].multiselect("Data de observação", sorted(history["OBSERVACAO_ATUAL"].unique()), key=f"{key}_source_dates")
    review = controls2[2].checkbox("Somente registros para revisão", key=f"{key}_review")
    if nature:
        view = view[view["NATUREZA"].isin(nature)]
    if source_dates:
        view = view[view["OBSERVACAO_ATUAL"].isin(source_dates)]
    if review:
        view = view[~view["STATUS_QUALIDADE"].isin(["", "OK"])]
    st.caption("Data cadastrada segue os campos definidos para GD. Primeira observação indica o limite da detecção; consulte a observação anterior. Reconstruções anteriores ao primeiro export estão identificadas.")
    columns = ["DATA_ALERTA", "NUM_UC", "CAMPO", "VALOR_ANTERIOR", "VALOR_NOVO", "BASE_DATA", "DATA_EFETIVA", "OBSERVACAO_ANTERIOR", "OBSERVACAO_ATUAL", "NATUREZA", "STATUS_QUALIDADE", "UC_RELACIONADA", "DETALHE", "ARQUIVO_ANTERIOR", "ARQUIVO_ORIGEM"]
    view = view.sort_values(["DATA_ALERTA", "NUM_UC"], ascending=[False, True])
    st.dataframe(view[columns], width="stretch", hide_index=True)
    download(view, "gd_historico_2026.csv", f"{key}_download")


def render(frame, reference_date, chart_style, plotly_config):
    if not (DATA / "gd_manifesto.json").exists():
        return False
    names = ("gd_atual.csv", "gd_snapshots.csv", "gd_vinculos.csv", "gd_historico_2026.csv", "gd_qualidade.csv", "gd_auditoria_baseline.csv", "gd_manifesto.json")
    frames, manifest = load_gd(tuple((DATA / name).stat().st_mtime_ns for name in names))
    scope = set(frame["NUM_UC"].astype(str))
    st.caption(f"GD/BEN/UC: {manifest['data_gd']} · MDM: {manifest['periodo_fim']} · Potência em kW · População: UCs da base BI")
    if manifest.get("lote_gd_incompleto"):
        st.warning(f"O lote de {manifest['data_ultimo_arquivo_gd']} está incompleto. A posição atual usa o último lote completo, de {manifest['data_gd']}.")
    mode = st.radio("Posição de GD", ["Último export completo", "Data de referência da barra lateral"], horizontal=True,
                    key="gd_position_mode")
    current = frames["gd_atual"]
    if mode.startswith("Data"):
        snapshots = frames["gd_snapshots"]
        eligible = snapshots[snapshots["DATA_REFERENCIA"].le(pd.Timestamp(reference_date).strftime("%Y-%m-%d"))]
        if eligible.empty:
            st.info("A referência é anterior à baseline de 31/12/2025.")
            return True
        snapshot_date = eligible["DATA_REFERENCIA"].max()
        current = eligible[eligible["DATA_REFERENCIA"].eq(snapshot_date)]
        st.caption(f"Última posição disponível até a referência: {snapshot_date}. {manifest['baseline_limite']}")
    current = current[current["NUM_UC"].isin(scope)].copy()
    groups = frame[["NUM_UC", "SITUACAO_ATUAL", *(["SITUACAO_INICIAL"] if "SITUACAO_INICIAL" in frame else [])]].copy()
    groups["NUM_UC"] = groups["NUM_UC"].astype(str)
    current = current.merge(groups, on="NUM_UC", how="left", validate="one_to_one")
    current["Grupo"] = current["SITUACAO_ATUAL"].replace({"Ativo": "Tratamento"})
    current["Grupo de origem"] = current.get("SITUACAO_INICIAL", current["SITUACAO_ATUAL"]).replace({"Ativo": "Tratamento"})
    current["Tipo de GD"] = current.apply(type_category, axis=1) if not current.empty else pd.Series(index=current.index, dtype=str)
    st.caption(f"Versão do painel: {LAYOUT_VERSION}")
    filters = st.columns(2)
    selected_groups = filters[0].multiselect("Grupo", ["Tratamento", "Controle", "Reserva"],
        default=["Tratamento", "Controle", "Reserva"], key="gd_groups",
        help="Grupo de origem da UC. UCs removidas continuam no seu grupo original e aparecem como Removido no gráfico de situação. Seleção vazia inclui todos os grupos.")
    selected_types = filters[1].multiselect("Tipo de GD", ["GDI", "GDII", "GDI/GDII"], key="gd_types",
        placeholder="Todos os tipos",
        help="GDI e GDII selecionam tipos exclusivos; GDI/GDII seleciona UCs com os dois tipos. Para geradoras, considera a GD própria; para UCs apenas beneficiárias, os tipos das geradoras vinculadas. Vazio inclui todos, inclusive tipo desconhecido e UCs sem GD.")
    if selected_groups:
        current = current[current["Grupo de origem"].isin(selected_groups)].copy()
    if selected_types:
        current = current[current["Tipo de GD"].isin(selected_types)].copy()
    scope = set(current["NUM_UC"])
    history = frames["gd_historico_2026"]
    history = history[history["NUM_UC"].isin(scope)]
    render_cards(current)
    if current.empty:
        st.info("Nenhuma UC corresponde aos filtros de grupo e tipo de GD selecionados.")
        return True
    tabs = st.tabs(["Posição e potência", "Histórico 2026", "Consulta por UC", "Qualidade e baseline"])
    with tabs[0]:
        display = current.copy()
        chart = display.groupby(["Grupo", "PERFIL_GD"]).size().reset_index(name="UCs")
        fig = px.bar(chart, x="Grupo", y="UCs", color="PERFIL_GD", barmode="group", text="UCs", labels={"PERFIL_GD": "Perfil GD"}, color_discrete_sequence=["#F5821E", "#FDB422", "#69727D", "#3F444B"])
        st.plotly_chart(chart_style(fig, 400), width="stretch", config=plotly_config)
        powers = average_power_by_type(current)
        if powers.empty:
            st.info("Nenhuma potência própria de UC geradora conhecida para comparar por classificação.")
        else:
            fig = px.bar(powers, x="Classificação", y="Potência média (kW)", text_auto=".2f", color="Classificação",
                         hover_data=["UCs geradoras"], title="Potência média por tipo de GD",
                         color_discrete_sequence=["#F5821E", "#FDB422", "#69727D", "#3F444B"])
            st.plotly_chart(chart_style(fig, 350), width="stretch", config=plotly_config)
        st.caption("Média da parcela de potência entre UCs geradoras que possuem essa classificação com valor maior que zero. Uma UC GDI/GDII participa de cada tipo com sua respectiva parcela. Potência de geradores externos vinculados a beneficiárias não entra nas médias.")
        review_only = st.checkbox("Mostrar somente UCs para revisão", key="gd_current_review")
        table = display[display["REVISAO_MANUAL"].eq("S")] if review_only else display
        st.dataframe(table, width="stretch", hide_index=True)
        download(table, "gd_atual.csv", "gd_current_download")
    with tabs[1]:
        history_view(history)
    with tabs[2]:
        selected = st.selectbox("UC", sorted(scope), index=None, placeholder="Pesquisar UC")
        if selected:
            st.dataframe(current[current["NUM_UC"].eq(selected)], width="stretch", hide_index=True)
            relationships = frames["gd_vinculos"]
            relationships = relationships[relationships["UC_GERADORA"].eq(selected) | relationships["UC_BENEFICIARIA"].eq(selected)]
            st.caption("Vínculos presentes no último export completo, incluindo UCs relacionadas externas ao BI. Autorrelacionamentos são exibidos somente quando constam na fonte.")
            st.dataframe(relationships, width="stretch", hide_index=True)
            download(relationships, f"gd_vinculos_{selected}.csv", "gd_links_download")
            history_view(history[history["NUM_UC"].eq(selected)], "gd_uc")
    with tabs[3]:
        st.caption(f"Baseline: {manifest['arquivo_baseline']} · Referência: 31/12/2025. Correções de baseline não são novas entradas GD em 2026.")
        audit = frames["gd_auditoria_baseline"]
        audit = audit[audit["NUM_UC"].isin(scope)]
        st.dataframe(audit, width="stretch", hide_index=True)
        download(audit, "gd_auditoria_baseline.csv", "gd_audit_download")
        quality = frames["gd_qualidade"]
        quality = quality[quality["NUM_UC"].isin(scope | {""})]
        st.dataframe(quality, width="stretch", hide_index=True)
        download(quality, "gd_qualidade.csv", "gd_quality_download")
    return True
