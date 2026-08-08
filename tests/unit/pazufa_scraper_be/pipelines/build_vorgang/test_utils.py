import datetime
from collections.abc import Callable
from typing import Any

import pytest
from pazufa_corelib.api_client.models import Doktyp, Gremium, Parlament, Station, Stationstyp
from pazufa_corelib.api_client.models import Dokument as PaZuFaDokument
from pazufa_corelib.api_client.types import UNSET

from pazufa_scraper_be.pardok import PlPrDokument
from pazufa_scraper_be.pardok.vorgang import GesetzVorgang
from pazufa_scraper_be.pipelines.build_vorgang.utils import (
    DokumentContainer,
    check_and_create_vote_outcome_station,
    get_vorgang_schlagworte,
    merge_vorgang_and_station_schlagworte,
)

angenommen_abstracts = [
    "Angenommen",
    # leading flag
    "Angenommen Irgendwas",
    "Angenommen Änderungsanträge Drucksache 19/0200-1, 19/0200-2 und 19/0200-3 wurden abgelehnt",
    # trailing flag
    "Irgendwas Angenommen",
    "Zusammen beraten mit: Drucksache 19/1191 Angenommen",
    # If Lesung is split into multiple entries in the XML, we merge them together.
    """Angenommen

    Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information vorangestellt
    """,
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information nachgestellt

    Angenommen""",
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Angenommen

    Hier ist die relevante Information nachgestellt""",
]
abgelehnt_abstracts = [
    "Abgelehnt",
    # leading flag
    "Abgelehnt Irgendwas",
    "Abgelehnt Zusammen beraten mit: Aktuelle Stunde und Drucksache 19/2473 und 19/2822",
    # trailing flag
    "Irgendwas Abgelehnt",
    "Zusammen beraten mit: Aktuelle Stunde und Drucksache 19/2553 Abgelehnt",
    # If Lesung is split into multiple entries in the XML, we merge them together.
    """Abgelehnt

    Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information vorangestellt
    """,
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Abgelehnt

    Hier ist die relevante Information nachgestellt""",
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information nachgestellt

    Abgelehnt""",
]
zurueckgezogen_abstracts = [
    "Zurückgezogen",
    # leading flag
    "Zurückgezogen Irgendwas",
    "Zurückgezogen Folge der Neukonstituierung des Abgeordnetenhauses von Berlin der 19. Wahlperiode nach der Wiederholungswahl vom 12. Februar 2023",
    # trailing flag
    "Irgendwas Zurückgezogen",
    "In Folge der Neukonstituierung des Abgeordnetenhauses von Berlin der 19. Wahlperiode nach der Wiederholungswahl vom 12. Februar 2023. Zurückgezogen",
    # If Lesung is split into multiple entries in the XML, we merge them together.
    """Zurückgezogen

    Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information vorangestellt
    """,
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Zurückgezogen

    Hier ist die relevante Information nachgestellt""",
    """Weitere Informationen

    Nach dem mergen sind diese mit doppelten newlines getrennt

    Hier ist die relevante Information nachgestellt

    Zurückgezogen""",
]
irrelevant_abstracts = [
    # case-sensitive match
    "angenommen",
    "abgelehnt",
    "zurückgezogen",
    # word bound match
    "AngenommenAngenommen",
    "AbgelehntAbgelehnt",
    "ZurückgezogenZurückgezogen",
    # other information
    "Vertagt",
    "Irgendwelche andere Informationen",
    "Überweisung an den Hauptausschuss",
    "Abstimmung über die Vertagung",
    # negative test for angenommen/abgeleht/zurueckgezogen
    "Die Worte angenommen oder abgelehnt oder zurückgezogen haben werden auch in der Mitte nicht gemacht",
    "Das gilt auch fuer das Ende: angenommen",
    "Das gilt auch fuer das Ende: abgelehnt",
    "Das gilt auch fuer das Ende: zurueckgezogen",
]


@pytest.fixture
def make_station() -> Callable[..., Station]:
    """Helper to create Station object."""

    def _make(typ: Stationstyp, **overrides: dict[str, Any]) -> Station:
        defaults: dict[str, Any] = {
            "zp_start": datetime.datetime.now(tz=datetime.UTC),
            "gremium": Gremium(Parlament.BE, 19, "Plenum"),
            "typ": typ,
            "dokumente": [],
        }
        defaults.update(overrides)
        return Station(**defaults)

    return _make


@pytest.mark.parametrize(
    "dok_abstract",
    angenommen_abstracts,
)
def test__check_and_create_vote_outcome_station__angenommen(make_station: Callable[..., Station], dok_abstract: str) -> None:
    """Test Angenommen voting."""
    station = make_station(typ=Stationstyp.PARL_VOLLVLSGN)
    result = check_and_create_vote_outcome_station(station, dok_abstract)

    assert result is not None
    assert result.typ == Stationstyp.PARL_AKZEPTANZ
    assert result.titel == "Angenommen"
    assert result.zp_start == station.zp_start + datetime.timedelta(minutes=30)


@pytest.mark.parametrize(
    "dok_abstract",
    abgelehnt_abstracts,
)
def test__check_and_create_vote_outcome_station__abgelehnt(make_station: Callable[..., Station], dok_abstract: str) -> None:
    """Test Abgelehnt voting."""
    station = make_station(typ=Stationstyp.PARL_VOLLVLSGN)
    result = check_and_create_vote_outcome_station(station, dok_abstract)

    assert result is not None
    assert result.typ == Stationstyp.PARL_ABLEHNUNG
    assert result.titel == "Abgelehnt"
    assert result.zp_start == station.zp_start + datetime.timedelta(minutes=30)


@pytest.mark.parametrize(
    "dok_abstract",
    zurueckgezogen_abstracts,
)
def test__check_and_create_vote_outcome_station__zurueckgezogen(make_station: Callable[..., Station], dok_abstract: str) -> None:
    """Test Zurückgezogen voting."""
    station = make_station(typ=Stationstyp.PARL_VOLLVLSGN)
    result = check_and_create_vote_outcome_station(station, dok_abstract)

    assert result is not None
    assert result.typ == Stationstyp.PARL_ZURUECKGZ
    assert result.titel == "Zurückgezogen"
    assert result.zp_start == station.zp_start + datetime.timedelta(minutes=30)


@pytest.mark.parametrize(
    "dok_abstract",
    irrelevant_abstracts,
)
def test__check_and_create_vote_outcome_station__irrelevant_abstract_returns_none(make_station: Callable[..., Station], dok_abstract: str) -> None:
    """Test abstracts with irrelevant text; should return None."""
    station = make_station(typ=Stationstyp.PARL_VOLLVLSGN)
    assert check_and_create_vote_outcome_station(station, dok_abstract) is None


@pytest.mark.parametrize(
    "dok_abstract",
    angenommen_abstracts + abgelehnt_abstracts + zurueckgezogen_abstracts + irrelevant_abstracts,
)
@pytest.mark.parametrize(
    "station_typ",
    [x for x in Stationstyp if x != Stationstyp.PARL_VOLLVLSGN],
)
def test__check_and_create_vote_outcome_station__wrong_station_returns_none(
    make_station: Callable[..., Station], station_typ: Stationstyp, dok_abstract: str
) -> None:
    """Test any other station type should return None."""
    station = make_station(typ=station_typ)
    assert check_and_create_vote_outcome_station(station, dok_abstract) is None


def _make_vorgang(base_vorgang_data: dict[str, Any], nebeneintraege: list[dict[str, Any]]) -> GesetzVorgang:
    return GesetzVorgang.model_validate({**base_vorgang_data, "Dokument": [], "Nebeneintrag": nebeneintraege})


def test__get_vorgang_schlagworte__no_nebeneintraege_returns_none(base_vorgang_data: dict[str, Any]) -> None:
    """Returns None when the Vorgang has no Nebeneinträge."""
    vorgang = _make_vorgang(base_vorgang_data, [])
    assert get_vorgang_schlagworte(vorgang) is None


def test__get_vorgang_schlagworte__single_nebeneintrag(base_vorgang_data: dict[str, Any]) -> None:
    """Returns a single-element list when there is one Nebeneintrag."""
    vorgang = _make_vorgang(base_vorgang_data, [{"ReihNr": 1, "Desk": "Klimaschutz"}])
    assert get_vorgang_schlagworte(vorgang) == ["Klimaschutz"]


def test__get_vorgang_schlagworte__multiple_nebeneintraege(base_vorgang_data: dict[str, Any]) -> None:
    """Returns all Desk values in order when multiple Nebeneinträge are present."""
    nebeneintraege = [{"ReihNr": 1, "Desk": "Klimaschutz"}, {"ReihNr": 2, "Desk": "Energie"}, {"ReihNr": 3, "Desk": "Verkehr"}]
    vorgang = _make_vorgang(base_vorgang_data, nebeneintraege)
    schlagworte = get_vorgang_schlagworte(vorgang)

    expected = ["Klimaschutz", "Energie", "Verkehr"]
    assert schlagworte is not None
    assert len(schlagworte) == len(expected)
    assert all(x in expected for x in schlagworte)


def _make_pazufa_dokument(schlagworte: list[str] | None = None) -> PaZuFaDokument:
    return PaZuFaDokument(
        typ=Doktyp.ENTWURF,
        titel="Test",
        volltext="",
        zp_modifiziert=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        zp_referenz=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        link="https://example.com/doc",
        hash_="abc123",
        autoren=[],
        schlagworte=schlagworte if schlagworte is not None else UNSET,
    )


def _make_dok_container(pardok_data: dict[str, Any], pazufa_doks: list[PaZuFaDokument]) -> DokumentContainer:

    pardok = PlPrDokument.model_validate(pardok_data)
    return DokumentContainer(pardok=pardok, pazufa=pazufa_doks)


def test__merge_vorgang_and_station_schlagworte__both_none_returns_unset(plpr_data: dict[str, Any]) -> None:
    """Returns UNSET when vorgang_schlagworte is None and no document has schlagworte."""
    dok = _make_pazufa_dokument(schlagworte=None)
    container = _make_dok_container(plpr_data, [dok])
    result = merge_vorgang_and_station_schlagworte(None, container)
    assert result is UNSET


def test__merge_vorgang_and_station_schlagworte__vorgang_only(plpr_data: dict[str, Any]) -> None:
    """Returns only vorgang schlagworte when documents have none."""
    dok = _make_pazufa_dokument(schlagworte=None)
    container = _make_dok_container(plpr_data, [dok])
    result = merge_vorgang_and_station_schlagworte(["Klimaschutz", "Energie"], container)
    assert result == ["Klimaschutz", "Energie"]


def test__merge_vorgang_and_station_schlagworte__dok_only(plpr_data: dict[str, Any]) -> None:
    """Returns only document schlagworte when vorgang_schlagworte is None."""
    dok = _make_pazufa_dokument(schlagworte=["Verkehr"])
    container = _make_dok_container(plpr_data, [dok])
    result = merge_vorgang_and_station_schlagworte(None, container)
    assert result == ["Verkehr"]


def test__merge_vorgang_and_station_schlagworte__merged_no_duplicates(plpr_data: dict[str, Any]) -> None:
    """Merges vorgang and document schlagworte; document duplicates are deduplicated."""
    dok1 = _make_pazufa_dokument(schlagworte=["A", "B"])
    dok2 = _make_pazufa_dokument(schlagworte=["B", "C"])
    container = _make_dok_container(plpr_data, [dok1, dok2])
    result = merge_vorgang_and_station_schlagworte(["X", "Y"], container)

    expected = ["A", "B", "C", "X", "Y"]
    assert isinstance(result, list)
    assert len(result) == len(expected)
    assert all(x in expected for x in result)


def test__merge_vorgang_and_station_schlagworte__empty_strings_filtered(plpr_data: dict[str, Any]) -> None:
    """Empty strings in document schlagworte are excluded from the result."""
    dok = _make_pazufa_dokument(schlagworte=["", "Valid", ""])
    container = _make_dok_container(plpr_data, [dok])
    result = merge_vorgang_and_station_schlagworte(None, container)
    assert result == ["Valid"]


def test__merge_vorgang_and_station_schlagworte__no_documents(plpr_data: dict[str, Any]) -> None:
    """Returns only vorgang schlagworte when the container has no documents."""
    container = _make_dok_container(plpr_data, [])
    result = merge_vorgang_and_station_schlagworte(["Umwelt"], container)
    assert result == ["Umwelt"]


def test__merge_vorgang_and_station_schlagworte__no_documents_no_vorgang(plpr_data: dict[str, Any]) -> None:
    """Returns UNSET when the container has no documents and vorgang_schlagworte is None."""
    container = _make_dok_container(plpr_data, [])
    result = merge_vorgang_and_station_schlagworte(None, container)
    assert result is UNSET


def test__merge_vorgang_and_station_schlagworte__dok_with_unset_schlagworte(plpr_data: dict[str, Any]) -> None:
    """Document with UNSET schlagworte contributes nothing; only vorgang schlagworte are returned."""
    dok = _make_pazufa_dokument(schlagworte=None)  # schlagworte=UNSET
    container = _make_dok_container(plpr_data, [dok])
    result = merge_vorgang_and_station_schlagworte(["Bildung"], container)
    assert result == ["Bildung"]
