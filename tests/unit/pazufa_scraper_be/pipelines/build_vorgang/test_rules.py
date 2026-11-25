import datetime as dt

import pytest
from pazufa_corelib.api_client.models import Autor, Doktyp
from pazufa_corelib.api_client.models import Dokument as PaZuFaDokument
from pazufa_corelib.api_client.types import UNSET

from pazufa_scraper_be.constants import ABSTRACT_TYPO_CORRECTIONS
from pazufa_scraper_be.pardok.dokument import AnyGesetzDokument, DrsDokument, parse_dokument
from pazufa_scraper_be.pipelines.build_vorgang.build_vorgang import RULES
from pazufa_scraper_be.pipelines.build_vorgang.rules import apply_rules, change_urheber_to_abstract_ausschuss_transform_fn
from pazufa_scraper_be.pipelines.build_vorgang.utils import DokumentContainer

KULTUR = "Ausschuss für Kultur, Engagement und Demokratieförderung"
HAUPT = "Hauptausschuss"
KULTUR_ABSTRACT = f"Beschlussempfehlung des {KULTUR.replace('Ausschuss', 'Ausschusses', 1)} vom 31. August 2026"
HAUPT_ABSTRACT = "Beschlussempfehlung des Hauptausschusses vom 2. September 2026"


def _pardok(data: dict[str, str]) -> AnyGesetzDokument:
    defaults = {"DHerk": "BLN", "DHerkL": "Berlin", "Wp": "19", "DokDat": "01.09.2026", "LokURL": "https://example.com/doc.pdf"}
    dokument = parse_dokument(defaults | data)
    assert dokument is not None
    return dokument


def _container(pardok: AnyGesetzDokument) -> DokumentContainer:
    pazufa = PaZuFaDokument(
        typ=Doktyp.SONSTIG,
        titel="Test",
        volltext="",
        zp_modifiziert=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        zp_referenz=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        link="https://example.com/doc",
        hash_="abc123",
        autoren=[Autor(organisation=x) for x in getattr(pardok, "urheber", [])],
        schlagworte=UNSET,
    )
    return DokumentContainer(pardok=pardok, pazufa=[pazufa])


def _aprotokoll(*, nr: str, urheber: str) -> DokumentContainer:
    data = {
        "DBID": f"D-{nr}",
        "ReihNr": "1",
        "DokArt": "APr",
        "DokArtL": "Ausschussprotokoll",
        "DokTyp": "Ausschussberatung",
        "DokTypL": "Ausschussberatung",
        "DokNr": nr,
        "Urheber": urheber,
    }
    return _container(_pardok(data))


def _beschlussempfehlung(*, nr: str, urheber: str, abstract: str | None) -> DokumentContainer:
    data = {
        "DBID": f"D-{nr}",
        "ReihNr": "1",
        "DokArt": "Drs",
        "DokArtL": "Drucksache",
        "DokTyp": "BeschlEmpf",
        "DokTypL": "Beschlussempfehlung",
        "DokNr": nr,
        "Urheber": urheber,
    }
    if abstract is not None:
        data["Abstract"] = abstract

    return _container(_pardok(data))


def _urheber(container: DokumentContainer) -> list[str]:
    assert isinstance(container.pardok, DrsDokument)
    return container.pardok.urheber


def _autoren(container: DokumentContainer) -> list[str]:
    return [autor.organisation for autor in container.pazufa[0].autoren]


def test__change_urheber_to_abstract_ausschuss__changes_pardok_and_pazufa_autoren() -> None:
    """Test Urheber and Autoren are replaced with the Ausschuss named in the Abstract."""
    container = _beschlussempfehlung(nr="19/3500", urheber=HAUPT, abstract=KULTUR_ABSTRACT)

    change_urheber_to_abstract_ausschuss_transform_fn(current=container)

    assert _urheber(container) == [KULTUR]
    assert _autoren(container) == [KULTUR]


@pytest.mark.parametrize("abstract", [None, "Angenommen", "Beschlussempfehlung des Plenums vom 2. September 2026"])
def test__change_urheber_to_abstract_ausschuss__keeps_urheber_if_abstract_names_no_ausschuss(abstract: str | None) -> None:
    """Test nothing changes if the Abstract does not name an Ausschuss."""
    container = _beschlussempfehlung(nr="19/3500", urheber=HAUPT, abstract=abstract)

    change_urheber_to_abstract_ausschuss_transform_fn(current=container)

    assert _urheber(container) == [HAUPT]
    assert _autoren(container) == [HAUPT]


def test__apply_rules__beschlussempfehlung_of_fachausschuss_is_merged_into_fachausschuss_station() -> None:
    """Test the Beschlussempfehlung lands on the Fachausschuss station, not on the later Hauptausschuss station (Vorgang V-457263)."""
    kultur = _aprotokoll(nr="19/71", urheber=KULTUR)
    haupt = _aprotokoll(nr="19/105", urheber=HAUPT)
    beschlussempfehlung = _beschlussempfehlung(nr="19/3500", urheber=HAUPT, abstract=KULTUR_ABSTRACT)

    result = apply_rules(pardok_pazufa_doks=[kultur, haupt, beschlussempfehlung], rules=RULES)

    assert [container.pardok.nr for container in result] == ["19/71", "19/105"]
    assert len(result[0].pazufa) == 2
    assert len(result[1].pazufa) == 1


def test__apply_rules__beschlussempfehlung_of_hauptausschuss_is_merged_into_hauptausschuss_station() -> None:
    """Test a Beschlussempfehlung whose Abstract names the Hauptausschuss is still merged into the Hauptausschuss station."""
    kultur = _aprotokoll(nr="19/71", urheber=KULTUR)
    haupt = _aprotokoll(nr="19/105", urheber=HAUPT)
    beschlussempfehlung = _beschlussempfehlung(nr="19/3500", urheber=HAUPT, abstract=HAUPT_ABSTRACT)

    result = apply_rules(pardok_pazufa_doks=[kultur, haupt, beschlussempfehlung], rules=RULES)

    assert [container.pardok.nr for container in result] == ["19/71", "19/105"]
    assert len(result[0].pazufa) == 1
    assert len(result[1].pazufa) == 2


def test__apply_rules__beschlussempfehlung_with_typo_in_abstract_is_merged_after_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test a typo in the Ausschuss of the Abstract does not prevent the merge once it is part of ABSTRACT_TYPO_CORRECTIONS."""
    monkeypatch.setitem(ABSTRACT_TYPO_CORRECTIONS, "Ausschusess", "Ausschusses")
    kultur = _aprotokoll(nr="19/71", urheber=KULTUR)
    haupt = _aprotokoll(nr="19/105", urheber=HAUPT)
    beschlussempfehlung = _beschlussempfehlung(nr="19/3500", urheber=HAUPT, abstract=KULTUR_ABSTRACT.replace("Ausschusses", "Ausschusess"))

    result = apply_rules(pardok_pazufa_doks=[kultur, haupt, beschlussempfehlung], rules=RULES)

    assert [container.pardok.nr for container in result] == ["19/71", "19/105"]
    assert len(result[0].pazufa) == 2
