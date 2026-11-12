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
    def test_93911335_exception_sums_active_powers_and_keeps_review(self):
        rows = [{**generator(power="4", sequence="976605", typ="GDI"), "COD_UN_CONS_UEE": "93911335"},
                {**generator(power="6.25", sequence="976607", typ="GDII"), "COD_UN_CONS_UEE": "93911335"},
                {**generator(power="6.25", sequence="ended", end="2024-10-01"), "COD_UN_CONS_UEE": "93911335"}]
        state = generator_state(rows, "2026-10-30")
        self.assertEqual(state["power"], Decimal("10.25"))
        self.assertEqual(state["split"]["GDI"], Decimal("4"))
        self.assertEqual(state["split"]["GDII"], Decimal("6.25"))
        self.assertIn("EXCECAO_SOMA_POTENCIAS_ATIVAS_REVISAO_MANUAL", state["flags"])
        self.assertNotIn("POTENCIAS_CONFLITANTES_MAIOR_ADOTADA", state["flags"])
        self.assertEqual(state["power_rule"], "EXCECAO_SOMA_POTENCIAS_ATIVAS")
        current = make_states({"93911335"}, {"93911335": rows}, {}, "2026-10-30", "2026-10-30", "GD.csv", "BEN.csv")["93911335"]
        self.assertEqual(current["PCT_POTENCIA_GDI"], "39.024390")
        self.assertEqual(current["PCT_POTENCIA_GDII"], "60.975610")
        self.assertEqual(current["REVISAO_MANUAL"], "S")
        ordinary = [{**row, "COD_UN_CONS_UEE": "101"} for row in rows]
        self.assertEqual(generator_state(ordinary, "2026-10-30")["power"], Decimal("6.25"))

    def test_sum_exception_deduplicates_equivalent_entries_and_classification_rows(self):
        rows = [generator(power="4", sequence="1", percentage="50"),
                generator(power="4", sequence="1", typ="GDII", percentage="50"),
                generator(power="4", sequence="duplicate", percentage="50"),
                generator(power="4", sequence="duplicate", typ="GDII", percentage="50"),
                generator(power="6.25", sequence="2", typ="GDII")]
        rows = [{**row, "COD_UN_CONS_UEE": "93911335"} for row in rows]
        state = generator_state(rows, "2026-10-30")
        self.assertEqual(state["power"], Decimal("10.25"))
        self.assertEqual(state["split"]["GDI"], Decimal("2"))
        self.assertEqual(state["split"]["GDII"], Decimal("8.25"))

    def test_sum_exception_does_not_guess_when_active_data_is_incomplete(self):
        rows = [{**generator(power=power, sequence=sequence), "COD_UN_CONS_UEE": "93911335"}
                for sequence, power in (("1", "4"), ("2", ""))]
        state = generator_state(rows, "2026-10-30")
        self.assertIn("EXCECAO_SOMA_NAO_APLICADA_DADOS_AMBIGUOS", state["flags"])
        self.assertNotEqual(state["power_rule"], "EXCECAO_SOMA_POTENCIAS_ATIVAS")

    def test_active_power_split_uses_percentages_not_ended_capacity(self):
        cases = [("10", "67", "33", "6.7", "6.7", "3.3"),
                 ("11", "44", "56", "4.86", "4.84", "6.16")]
        for total, gdi_pct, gdii_pct, old_power, expected_gdi, expected_gdii in cases:
            with self.subTest(total=total):
                rows = [generator(power=old_power, sequence="old", end="2025-05-01"),
                        generator(power=total, sequence="new", typ="GDI", percentage=gdi_pct),
                        generator(power=total, sequence="new", typ="GDII", percentage=gdii_pct)]
                state = generator_state(rows, "2026-10-30")
                self.assertEqual(state["power"], Decimal(total))
                self.assertEqual(state["split"]["GDI"], Decimal(expected_gdi))
                self.assertEqual(state["split"]["GDII"], Decimal(expected_gdii))
                self.assertEqual(sum(state["split"].values()), Decimal(total))

    def test_identical_active_registrations_count_once_without_review(self):
        state = generator_state([generator(power="12", sequence="1173708"),
                                 generator(power="12.0", sequence="1180102", start="2023-01-01")], "2026-10-30")
        self.assertEqual(state["power"], Decimal("12"))
        self.assertEqual(state["types"], "GDI")
        self.assertEqual(state["split"]["GDI"], Decimal("12"))
        self.assertEqual(state["flags"], [])
        self.assertEqual(state["registration_ids"], ["1173708", "1180102"])
        self.assertEqual(state["registration_treatment"], "UNIFICADOS_POTENCIA_CLASSIFICACAO_IGUAIS")

    def test_identical_mixed_classifications_keep_single_power_and_split(self):
        rows = [generator(sequence=sequence, typ=typ, percentage=pct)
                for sequence in ("1", "2") for typ, pct in (("GDI", "60"), ("GDII", "40"))]
        state = generator_state(rows, "2026-10-30")
        self.assertEqual(state["flags"], [])
        self.assertEqual(state["power"], Decimal("10"))
        self.assertEqual(state["split"]["GDI"], Decimal("6"))
        self.assertEqual(state["split"]["GDII"], Decimal("4"))

    def test_different_or_unconfirmed_classifications_stay_flagged(self):
        cases = {
            "type": [generator(sequence="1"), generator(sequence="2", typ="GDII")],
            "allocation": [generator(sequence="1", typ="GDI", percentage="60"), generator(sequence="1", typ="GDII", percentage="40"),
                           generator(sequence="2", typ="GDI", percentage="70"), generator(sequence="2", typ="GDII", percentage="30")],
            "subtype": [generator(sequence="1"), {**generator(sequence="2"), "COD_SUB_TIPO_CSS_GER_KCD": "OTHER"}],
            "missing_power": [generator(sequence="1", power=""), generator(sequence="2", power="")],
            "missing_type": [generator(sequence="1", typ=""), generator(sequence="2", typ="")],
            "invalid_allocation": [generator(sequence="1", percentage="90"), generator(sequence="2", percentage="90")],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                self.assertIn("MULTIPLOS_REGISTROS_ATIVOS", generator_state(rows, "2026-10-30")["flags"])

    def test_resolved_generator_clears_inherited_flag_but_keeps_other_issues(self):
        gd = {"101": [generator(power="12", sequence="1"), generator(power="12", sequence="2")]}
        for rate, expected in (("25", "N"), ("125", "S")):
            with self.subTest(rate=rate):
                links = enrich_links(link_states({("101", "202"): [beneficiary(power="12", percentage=rate)]},
                                                  "2026-10-30", "BEN.csv", "2026-10-30"), gd, "2026-10-30")
                states = make_states({"101", "202"}, gd, links, "2026-10-30", "2026-10-30", "GD.csv", "BEN.csv")
                self.assertNotIn("MULTIPLOS_REGISTROS_ATIVOS", states["202"]["STATUS_QUALIDADE"])
                self.assertEqual(states["202"]["REVISAO_MANUAL"], expected)
                self.assertEqual(states["101"]["POTENCIA_INSTALADA_KW"], "12")

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
        self.assertIn("MULTIPLOS_REGISTROS_ATIVOS", state["flags"])

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

    def test_power_averages_use_own_capacity_and_positive_classification_portions(self):
        from gd_dashboard import own_power, average_power_by_type, type_category
        frame = pd.DataFrame([
            dict(NUM_UC="101", GD_GERADORA="S", POTENCIA_INSTALADA_KW="10", POTENCIA_GDI_KW="10", POTENCIA_GDII_KW="0", POTENCIA_OUTROS_KW="", POTENCIA_SEM_CLASSIFICACAO_KW=""),
            dict(NUM_UC="303", GD_GERADORA="S", POTENCIA_INSTALADA_KW="20", POTENCIA_GDI_KW="12", POTENCIA_GDII_KW="8", POTENCIA_OUTROS_KW="0", POTENCIA_SEM_CLASSIFICACAO_KW="0"),
            dict(NUM_UC="404", GD_GERADORA="S", POTENCIA_INSTALADA_KW="30", POTENCIA_GDI_KW="0", POTENCIA_GDII_KW="30", POTENCIA_OUTROS_KW="0", POTENCIA_SEM_CLASSIFICACAO_KW="0"),
            dict(NUM_UC="606", GD_GERADORA="S", POTENCIA_INSTALADA_KW="", POTENCIA_GDI_KW="", POTENCIA_GDII_KW="", POTENCIA_OUTROS_KW="", POTENCIA_SEM_CLASSIFICACAO_KW=""),
            dict(NUM_UC="202", GD_GERADORA="N", POTENCIA_INSTALADA_KW="", POTENCIA_GDI_KW="", POTENCIA_GDII_KW="", POTENCIA_OUTROS_KW="", POTENCIA_SEM_CLASSIFICACAO_KW="", POTENCIA_EXTERNA_ASSOCIADA_KW="300"),
        ])
        self.assertEqual(own_power(frame).mean(), 20)
        powers = average_power_by_type(frame).set_index("Classificação")
        self.assertEqual(powers.at["GDI", "Potência média (kW)"], 11)
        self.assertEqual(powers.at["GDII", "Potência média (kW)"], 19)
        self.assertEqual(powers.at["GDI", "UCs geradoras"], 2)
        self.assertEqual(type_category(dict(GD_GERADORA="S", GD_BENEFICIARIA="S", TIPO_GD_GERA="GDII", TIPO_GD_BENE="GDI")), "GDII")
        self.assertEqual(type_category(dict(GD_GERADORA="N", GD_BENEFICIARIA="S", TIPO_GD_GERA="", TIPO_GD_BENE="GDI | GDII")), "GDI/GDII")

    def test_gd_group_type_filters_update_all_eight_cards_and_handle_unknown_power(self):
        from streamlit.testing.v1 import AppTest
        gd = {"101": [generator()],
              "303": [{**generator(power="20", typ="GDI", percentage="60"), "COD_UN_CONS_UEE": "303"},
                      {**generator(power="20", typ="GDII", percentage="40"), "COD_UN_CONS_UEE": "303"}],
              "404": [{**generator(power="30", typ="GDII"), "COD_UN_CONS_UEE": "404"}],
              "606": [{**generator(power="", typ="GDII"), "COD_UN_CONS_UEE": "606"}]}
        pairs = {("101", "202"): [beneficiary()], ("303", "303"): [beneficiary(gen="303", ben="303", power="20")]}
        links = enrich_links(link_states(pairs, "2026-10-29", "BEN.csv", "2026-10-29"), gd, "2026-10-29")
        states = make_states({"101", "202", "303", "404", "505", "606"}, gd, links, "2026-10-29", "2026-10-29", "GD.csv", "BEN.csv")
        for name in ("gd_atual.csv", "gd_snapshots.csv"):
            write_rows(self.folder / name, states.values())
        write_rows(self.folder / "gd_vinculos.csv", links.values())
        script = f'''
from pathlib import Path
import pandas as pd
import gd_dashboard
gd_dashboard.DATA = Path({str(self.folder)!r})
frame = pd.DataFrame([
 dict(NUM_UC='101', SITUACAO_INICIAL='Ativo', SITUACAO_ATUAL='Ativo'),
 dict(NUM_UC='202', SITUACAO_INICIAL='Controle', SITUACAO_ATUAL='Controle'),
 dict(NUM_UC='303', SITUACAO_INICIAL='Reserva', SITUACAO_ATUAL='Reserva'),
 dict(NUM_UC='404', SITUACAO_INICIAL='Ativo', SITUACAO_ATUAL='Removido'),
 dict(NUM_UC='505', SITUACAO_INICIAL='Controle', SITUACAO_ATUAL='Controle'),
 dict(NUM_UC='606', SITUACAO_INICIAL='Controle', SITUACAO_ATUAL='Controle')])
gd_dashboard.render(frame, pd.Timestamp('2026-10-29'), lambda fig, height: fig.update_layout(height=height), {{}})
'''
        app = AppTest.from_string(script).run(timeout=30)
        labels = ["UCs geradoras", "UCs beneficiárias", "UCs geradoras e beneficiárias", "UCs para revisão",
                  "Potência média (kW)", "Potência máxima (kW)", "Potência mínima (kW)", "Total de UCs com GD"]
        self.assertEqual(list(app.exception), [])
        self.assertEqual([metric.label for metric in app.metric], labels)
        self.assertEqual([metric.value for metric in app.metric], ["4", "2", "1", "1", "20.00", "30.00", "10.00", "5"])
        self.assertTrue(all(metric.proto.help for metric in app.metric))
        app.multiselect(key="gd_groups").set_value(["Tratamento", "Controle"]).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.metric[0].value, "3")
        self.assertEqual(app.metric[-1].value, "4")
        table = next(d.value for d in app.dataframe if "Grupo" in d.value.columns)
        self.assertIn("404", set(table.NUM_UC))
        app.multiselect(key="gd_types").set_value(["GDI"]).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual([metric.value for metric in app.metric], ["1", "1", "0", "0", "10.00", "10.00", "10.00", "2"])
        app.multiselect(key="gd_groups").set_value(["Controle"])
        app.multiselect(key="gd_types").set_value(["GDII"]).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.metric[4].value, "—")
        self.assertEqual(app.metric[-1].value, "1")
        app.multiselect(key="gd_types").set_value(["GDI/GDII"]).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.metric[-1].value, "0")
        app.multiselect(key="gd_groups").set_value(["Reserva"]).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual([metric.value for metric in app.metric], ["1", "1", "1", "0", "20.00", "20.00", "20.00", "1"])
        uc_picker = next(widget for widget in app.selectbox if widget.label == "UC")
        self.assertEqual(uc_picker.options, ["303"])

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

    def test_gd_latest_grouping_uses_export_date_and_historical_mode_uses_reference(self):
        from streamlit.testing.v1 import AppTest
        source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        source = source.split("\ninject_css()\n", 1)[0]
        source = source.replace("Path(__file__)", f"Path({str(Path(__file__).with_name('app.py'))!r})")
        source += f'''
GD_MANIFEST_FILE = Path({str(self.folder / 'gd_manifesto.json')!r})
frame = pd.DataFrame([dict(NUM_UC='101', SITUACAO_INICIAL='Ativo', SITUACAO_ATUAL='Removido',
    DT_DISTRATO=pd.Timestamp('2026-06-01'), LOCAL='CURITIBA', FINALIDADE='Pessoal', FABRI_VEIC='BYD')])
filtered, page, reference = sidebar_filters(frame)
if page == 'Geração distribuída':
    st.radio('Posição de GD', ['Último export completo', 'Data de referência da barra lateral'], key='gd_position_mode')
st.dataframe(filtered[['NUM_UC', 'SITUACAO_ATUAL']])
'''
        app = AppTest.from_string(source).run(timeout=30)
        app.sidebar.radio[0].set_value("Geração distribuída").run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.dataframe[0].value["SITUACAO_ATUAL"].tolist(), ["Removido"])
        self.assertEqual(str(app.sidebar.date_input[0].value), "2026-03-01")
        mode = next(radio for radio in app.radio if radio.label == "Posição de GD")
        mode.set_value("Data de referência da barra lateral").run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.dataframe[0].value["SITUACAO_ATUAL"].tolist(), ["Ativo"])
        app.sidebar.date_input[0].set_value(pd.Timestamp("2026-06-01").date()).run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.dataframe[0].value["SITUACAO_ATUAL"].tolist(), ["Removido"])
        app.sidebar.date_input[0].set_value(pd.Timestamp("2026-03-01").date()).run(timeout=30)
        app.sidebar.radio[0].set_value("Geral").run(timeout=30)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.dataframe[0].value["SITUACAO_ATUAL"].tolist(), ["Ativo"])


if __name__ == "__main__":
    unittest.main()
