import csv
import io
from contextlib import redirect_stdout
import tempfile
import unittest
import json
from pathlib import Path
from decimal import Decimal

import pandas as pd
from openpyxl import Workbook, load_workbook

from cadastro_pipeline import (
    generator_state, link_states, enrich_links, make_states, compare_gd, compare_links,
    event, mdm_history, discover, run, digest,
    write_rows, ALERT_COLUMNS,
    read_baseline, baseline_audit, preserve_unconfirmed_baseline,
)


def generator(power="10", typ="GDI", percentage="100", sequence="1", start="2024-01-01", end=""):
    return dict(COD_UN_CONS_UEE="101", NUM_SEQ_KCG=sequence, QTD_POT_GER_KCG=power,
                DTA_SOL_ACES_KCG=start, DTA_FIM_VIGN_KCG=end,
                COD_TIPO_CSS_GER_KCD=typ, COD_SUB_TIPO_CSS_GER_KCD=typ,
                PCT_DIS_KCD=percentage)


def beneficiary(gen="101", ben="202", start="2026-02-15", power="10", percentage="25"):
    return dict(COD_UN_CONS_UEE=gen, COD_UN_CONS_BEN_XBG=ben,
                QTD_POT_GER_UTG=power, DTA_INC_XBG=start, DTA_INIC_VIGN_XBG="2026-03-01",
                PCT_RAT_XBG=percentage, NUM_PRI_XBG="1", COD_MODL_DIS_UTG="2")


def csv_file(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


class DomainRules(unittest.TestCase):
    def test_undated_generator_is_first_observed_not_assumed_active_in_2025(self):
        gd = {"101": [generator(start="")]}
        old = make_states({"101"}, gd, {}, "2025-12-31", "2026-10-22", "GD.csv", "BEN.csv")
        current = make_states({"101"}, gd, {}, "2026-10-22", "2026-10-22", "GD.csv", "BEN.csv")
        self.assertEqual(old["101"]["GD_GERADORA"], "N")
        self.assertEqual(current["101"]["GD_GERADORA"], "S")
        change = next(e for e in compare_gd(old, current, "GD.csv", "GD.csv") if e["CAMPO"] == "GD_GERADORA")
        self.assertEqual(change["DATA_ALERTA"], "2026-10-22")
        self.assertEqual(change["BASE_DATA"], "Primeira observação")
        self.assertEqual(change["DATA_EFETIVA"], "")

    def test_survey_baseline_maps_types_without_inventing_generator_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "amostra.xlsx"
            wb = Workbook()
            wb.active.title = "Grupo Experimental"
            wb.active.append(["UC", "GD2"])
            wb.active.append(["00101", "GDI"])
            wb.active.append(["202", 0])
            control = wb.create_sheet("Grupo Controle e Reservas")
            control.append(["UC", "Se tem ou Não GD", "Qual GD (GDI, GDII, GDI/GDII)", "Autoconsumo Local ou Remoto"])
            control.append(["303", "303", "GD I - 77 / GDII - 23", "Autoconsumo Local"])
            control.append(["404", "404", None, "Sem GD"])
            wb.save(path)
            baseline = read_baseline(path, {"00101", "202", "303", "404"})
            self.assertEqual(baseline["00101"]["GD_DECLARADA"], "S")
            self.assertEqual(baseline["202"]["GD_DECLARADA"], "N")
            self.assertEqual(baseline["303"]["TIPO_GD_DECLARADO"], "GDI | GDII")
            self.assertEqual(baseline["404"]["GD_DECLARADA"], "N")
            self.assertIsNone(baseline["00101"]["TIPO_GD_GERA"])
            states = make_states(set(baseline), {}, {}, "2025-12-31", "2026-10-22", "GD.csv", "BEN.csv")
            preserve_unconfirmed_baseline(states, baseline, {}, {})
            self.assertEqual(states["00101"]["GD_GERADORA"], "N")
            self.assertEqual(states["00101"]["GD_SEM_VINCULO_CONFIRMADO"], "S")
            audit = baseline_audit(baseline, states, path, "2026-10-22", {})
            self.assertEqual(len(audit), 8)

    def test_duplicate_classification_does_not_multiply_power(self):
        rows = [generator(percentage="60"), generator(typ="GDII", percentage="40"), generator(percentage="60")]
        state = generator_state(rows, "2026-10-22")
        self.assertEqual(state["power"], Decimal("10"))
        self.assertEqual(state["split"]["GDI"], Decimal("6"))
        self.assertEqual(state["split"]["GDII"], Decimal("4"))

    def test_conflicting_power_keeps_largest_and_flags_review(self):
        state = generator_state([generator(), generator(power="15", sequence="2")], "2026-10-22")
        self.assertEqual(state["power"], Decimal("15"))
        self.assertIn("POTENCIAS_CONFLITANTES_MAIOR_ADOTADA", state["flags"])

    def test_invalid_split_goes_to_unclassified(self):
        state = generator_state([generator(percentage="90")], "2026-10-22")
        self.assertEqual(state["split"]["SEM_CLASSIFICACAO"], Decimal("10"))
        self.assertEqual(state["split"]["GDI"], 0)

    def test_dates_exclude_future_and_expired_records(self):
        self.assertFalse(generator_state([generator(start="2026-11-01")], "2026-10-22")["active"])
        self.assertFalse(generator_state([generator(end="2026-10-22")], "2026-10-22")["active"])

    def test_unknown_power_stays_unknown(self):
        state = generator_state([generator(power="")], "2026-10-22")
        self.assertIsNone(state["power"])

    def test_beneficiary_uses_inclusion_not_validity_date(self):
        rows = {("101", "202"): [beneficiary()]}
        links = link_states(rows, "2026-02-20", "BEN.csv", "2026-10-22")
        self.assertEqual(links["101", "202"]["DATA_INICIO"], "2026-02-15")

    def test_no_invented_self_benefit(self):
        current = make_states({"101", "202"}, {"101": [generator()]}, {}, "2026-10-22", "2026-10-22", "GD.csv", "BEN.csv")
        self.assertEqual(current["101"]["GD_GERADORA"], "S")
        self.assertEqual(current["101"]["GD_BENEFICIARIA"], "N")

    def test_absence_is_not_cancellation(self):
        previous = make_states({"101"}, {"101": [generator()]}, {}, "2026-10-22", "2026-10-22", "a", "b")
        current = make_states({"101"}, {}, {}, "2026-10-29", "2026-10-29", "c", "d")
        events = compare_gd(previous, current, "c", "a")
        role = next(e for e in events if e["CAMPO"] == "GD_GERADORA")
        self.assertEqual(role["NATUREZA"], "Ausência no export")
        self.assertEqual(role["BASE_DATA"], "Primeira observação")

    def test_old_effective_date_is_not_new_event_date(self):
        e = event("101", "TYPE", "GDI", "GDII", "2026-10-29", "2026-10-22", effective="2024-01-01")
        self.assertEqual(e["DATA_ALERTA"], "2026-10-29")
        self.assertEqual(e["DATA_EFETIVA"], "2024-01-01")

    def test_intermediate_changes_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for dt, value in [("20260101", "LG"), ("20260201", "DS"), ("20260301", "LG")]:
                path = Path(folder) / f"mdm-sandbox_clientes_novo-{dt}-{dt}.csv"
                incoming = dict(UC="101", SITUACAO_UC=value) if dt == "20260201" else dict(uc="101", situacao_uc=value)
                csv_file(path, [incoming])
                paths.append(path)
            current, events, dates = mdm_history(paths, {"101"}, [])
            self.assertEqual(current["101"]["SITUACAO_UC"], "LG")
            self.assertEqual([(e["VALOR_ANTERIOR"], e["VALOR_NOVO"]) for e in events], [("LG", "DS"), ("DS", "LG")])

    def test_same_day_conflict_resets_comparison_and_absent_field_does_not_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            specs = [("a-20260101-20260101.csv", dict(uc="101", tipo_fase="MO")),
                     ("b-20260101-20260101.csv", dict(uc="101", tipo_fase="BI")),
                     ("a-20260201-20260201.csv", dict(uc="101", tipo_fase="TR")),
                     ("a-20260301-20260301.csv", dict(uc="101", municipio="CURITIBA"))]
            paths, quality = [], []
            for name, row in specs:
                path = Path(folder) / name
                csv_file(path, [row])
                paths.append(path)
            current, events, _ = mdm_history(paths, {"101"}, quality)
            self.assertEqual(current["101"]["TIPO_FASE"], "TR")
            self.assertEqual(len(quality), 1)
            self.assertEqual(events, [])

    def test_incomplete_batch_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "2026-10-29-consulta_GD.csv"
            csv_file(path, [generator()])
            self.assertEqual(set(discover(Path(folder))["2026-10-29"]), {"GD"})


class WorkflowIntegration(unittest.TestCase):
    def test_full_and_public_base_scope_history_privacy_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bi = root / "BI-Cadastro"
            (bi / "data").mkdir(parents=True)
            cadastro = root / "Cadastro"
            exports = cadastro / "DADOS_GD_GERAL"
            exports.mkdir(parents=True)
            base = pd.DataFrame([dict(NUM_UC="101", SITUACAO_INICIAL="Ativo", SITUACAO_ATUAL="Ativo", DT_DISTRATO="", MOTIV_DIST="", IND_SOLICITAÇAO="S", DT_MUD_TIT="", CLASSE="B1", GRUPO="1"),
                                 dict(NUM_UC="202", SITUACAO_INICIAL="Controle", SITUACAO_ATUAL="Controle", DT_DISTRATO="", MOTIV_DIST="", IND_SOLICITAÇAO="S", DT_MUD_TIT="", CLASSE="B1", GRUPO="1")])
            base.to_csv(bi / "base_consolidada_BI.csv", index=False)
            full = root / "base_consolidada_copel.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append([*base.columns, "NOME"])
            for row in base.itertuples(index=False, name=None):
                ws.append([*row, "Private name"])
            ws.append(["999", *([""] * (len(base.columns) - 1)), "External private"])
            wb.save(full)
            baseline = root / "amostra.xlsx"
            wb = Workbook()
            wb.active.append(["NUM_UC", "TIPO_GD_GERA", "DATA_INICIO_GD"])
            wb.active.append(["101", "GDII", "2024-01-01"])
            wb.active.append(["202", "", ""])
            wb.save(baseline)
            removal = bi / "data/relatorio_ucs_removidas.xlsx"
            wb = Workbook()
            wb.active.append(["NUM_UC", "DT_DISTRATO", "MOTIV_DIST"])
            wb.save(removal)
            for dt, power in [("2026-10-22", "10"), ("2026-10-29", "15")]:
                csv_file(exports / f"{dt}-consulta_GD.csv", [generator(power=power), {**generator(), "COD_UN_CONS_UEE": "999"}])
                csv_file(exports / f"{dt}-consulta_BEN.csv", [beneficiary(power=power)])
                csv_file(exports / f"{dt}-consulta_UC.csv", [dict(ISN_UC="101", NUM_CLI_UC="1", TIPO_SIT_UC="LG"), dict(ISN_UC="202", NUM_CLI_UC="2", TIPO_SIT_UC="LG")])
            csv_file(cadastro / "mdm-sandbox_clientes_novo-20260101-20260101.csv", [dict(uc="101", situacao_uc="LG", nome="PRIVATE")])
            sources = {p: digest(p) for p in [*exports.glob("*.csv"), *cadastro.glob("*.csv"), baseline]}
            initial_full = digest(full)
            with redirect_stdout(io.StringIO()):
                run(root, bi, baseline, dry_run=True)
            self.assertEqual(digest(full), initial_full)
            with redirect_stdout(io.StringIO()):
                run(root, bi, baseline)
            result = pd.read_csv(bi / "base_consolidada_BI.csv", dtype=str, keep_default_na=False)
            self.assertEqual(set(result["NUM_UC"]), {"101", "202"})
            self.assertEqual(result.loc[result["NUM_UC"].eq("101"), "POTENCIA_INSTALADA_KW"].iloc[0], "15")
            self.assertNotIn("NOME", result.columns)
            audit = pd.read_csv(bi / "data/gd_auditoria_baseline.csv", dtype=str, keep_default_na=False)
            corrected = audit[audit["NUM_UC"].eq("101") & audit["CAMPO"].eq("TIPO_GD_GERA")].iloc[0]
            self.assertEqual(corrected["VALOR_AMOSTRA"], "GDII")
            self.assertEqual(corrected["VALOR_RECONSTRUIDO"], "GDI")
            self.assertEqual(corrected["STATUS"], "CORRIGIDO_PELA_FONTE_GD")
            history = pd.read_csv(bi / "data/gd_historico_2026.csv", dtype=str, keep_default_na=False)
            self.assertFalse(history["CAMPO"].eq("TIPO_GD_GERA").any())
            beneficiary_entry = history[history["NUM_UC"].eq("202") & history["CAMPO"].eq("GD_BENEFICIARIA")].iloc[0]
            self.assertEqual(beneficiary_entry["DATA_ALERTA"], "2026-02-15")
            wb = load_workbook(full, data_only=True)
            self.assertEqual(wb.active.max_row, 4)
            self.assertEqual(wb.active.cell(2, list(base.columns).index("NUM_UC") + 1).value, "101")
            self.assertEqual(wb.active.cell(2, len(base.columns) + 1).value, "Private name")
            hashes = {p: digest(p) for p in [bi / "base_consolidada_BI.csv", bi / "data/historico_alertas.csv", full]}
            with redirect_stdout(io.StringIO()):
                repeated = run(root, bi, baseline)
            self.assertEqual(repeated["celulas_alteradas_base_completa"], 0)
            for p, value in hashes.items():
                self.assertEqual(digest(p), value, str(p))
            for p, value in sources.items():
                self.assertEqual(digest(p), value)
            csv_file(exports / "2026-10-30-consulta_GD.csv", [dict(INVALID="broken")])
            csv_file(exports / "2026-10-30-consulta_BEN.csv", [beneficiary()])
            csv_file(exports / "2026-10-30-consulta_UC.csv", [dict(ISN_UC="101", NUM_CLI_UC="1", TIPO_SIT_UC="LG")])
            with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                run(root, bi, baseline)
            for p, value in hashes.items():
                self.assertEqual(digest(p), value, str(p))


class DashboardSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        states = make_states({"101", "202"}, {"101": [generator()]},
            enrich_links(link_states({("101", "202"): [beneficiary()]}, "2026-10-29", "BEN.csv", "2026-10-29"),
                         {"101": [generator()]}, "2026-10-29"),
            "2026-10-29", "2026-10-29", "GD.csv", "BEN.csv")
        write_rows(self.folder / "gd_atual.csv", states.values())
        write_rows(self.folder / "gd_snapshots.csv", states.values())
        links = link_states({("101", "202"): [beneficiary()]}, "2026-10-29", "BEN.csv", "2026-10-29")
        write_rows(self.folder / "gd_vinculos.csv", links.values())
        e = event("202", "GD_BENEFICIARIA", "N", "S", "2026-10-29", "2025-12-31", "BEN.csv", effective="2026-02-15")
        e["GRUPO_UC"] = "Controle"
        for name in ("gd_historico_2026", "historico_alertas", "ultima_atualizacao_alertas"):
            write_rows(self.folder / f"{name}.csv", [e], ALERT_COLUMNS)
        write_rows(self.folder / "gd_qualidade.csv", [], ["NUM_UC", "TIPO", "DETALHE", "ARQUIVO_ORIGEM", "DATA_FONTE"])
        write_rows(self.folder / "gd_auditoria_baseline.csv", [], ["NUM_UC", "CAMPO", "STATUS"])
        manifest = dict(data_gd="2026-10-29", periodo_fim="20261029", periodo_inicio="20261029", baseline_limite="Baseline retrospectiva", arquivo_baseline="amostra.xlsx")
        for name in ("gd_manifesto.json", "ultima_atualizacao_resumo.json"):
            (self.folder / name).write_text(json.dumps(manifest), encoding="utf-8")

    def test_gd_latest_history_reference_and_uc_detail_render(self):
        from streamlit.testing.v1 import AppTest
        directory = repr(str(self.folder))
        script = f'''
from pathlib import Path
import pandas as pd
import gd_dashboard
gd_dashboard.DATA = Path({directory})
frame = pd.DataFrame([dict(NUM_UC=101, SITUACAO_ATUAL='Ativo'), dict(NUM_UC=202, SITUACAO_ATUAL='Controle')])
gd_dashboard.render(frame, pd.Timestamp('2026-10-29'), lambda fig, height: fig.update_layout(height=height), {{}})
'''
        app = AppTest.from_string(script).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        app.selectbox[1].select("202").run(timeout=30)
        self.assertEqual(list(app.exception), [])
        app.radio[0].set_value("Data de referência da barra lateral").run(timeout=30)
        self.assertEqual(list(app.exception), [])

    def test_alerts_show_evidence_and_january_february_filters(self):
        from streamlit.testing.v1 import AppTest
        source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        source = source.split("\ninject_css()\n", 1)[0]
        # Replace file-based __file__ uses because AppTest.from_string creates
        # its own script in a temporary directory.
        source = source.replace("Path(__file__)", f"Path({str(Path(__file__).with_name('app.py'))!r})")
        source += f'''
UPDATE_HISTORY_FILE = Path({str(self.folder / 'historico_alertas.csv')!r})
UPDATE_ALERT_FILE = Path({str(self.folder / 'ultima_atualizacao_alertas.csv')!r})
UPDATE_SUMMARY_FILE = Path({str(self.folder / 'ultima_atualizacao_resumo.json')!r})
update_report_page(pd.DataFrame([dict(NUM_UC='101'), dict(NUM_UC='202')]))
'''
        app = AppTest.from_string(source).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertIn("Fevereiro", app.pills[0].options)
        app.radio[0].set_value("Experimento: desde 01/03/2026").run(timeout=30)
        self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
