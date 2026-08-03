import datetime
from collections.abc import Callable
from typing import Any

import pytest
from pazufa_corelib.api_client.models import Gremium, Parlament, Station, Stationstyp

from pazufa_scraper_be.pipelines.build_vorgang.utils import check_and_create_vote_outcome_station

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
