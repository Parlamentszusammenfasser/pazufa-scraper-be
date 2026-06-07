import asyncio
import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pazufa_corelib.api_client.models import Autor, Doktyp, Gremium, Parlament, Station, Stationstyp, VgIdent, Vorgang, Vorgangstyp
from pazufa_corelib.api_client.models import Dokument as PaZuFaDokument
from pazufa_corelib.api_client.types import UNSET
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import DropItem
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector

from pazufa_scraper_be.pipelines.dump import DumpVorgang, get_dump_file_name, vorgang_to_json

START_TIME = dt.datetime(2026, 11, 25, 9, 30, 15, tzinfo=dt.UTC)
RUN_DIR_NAME = "20261125T093015"
VOLLTEXT = "Der Volltext des Gesetzentwurfs."
API_ID = uuid.UUID("6f0ac5c8-0d4e-5b8c-9a58-3a6a3d2f6a11")


def _make_vorgang(*, id_: str | None = "V-457263") -> Vorgang:
    dokument = PaZuFaDokument(
        typ=Doktyp.ENTWURF,
        titel="Gesetz zur Stärkung der Öffentlichen Bibliotheken",
        volltext=VOLLTEXT,
        zp_modifiziert=dt.datetime(2026, 8, 18, tzinfo=dt.UTC),
        zp_referenz=dt.datetime(2026, 8, 18, tzinfo=dt.UTC),
        link="https://example.com/doc.pdf",
        hash_="abc123",
        autoren=[Autor(organisation="SPD")],
        schlagworte=UNSET,
    )
    station = Station(
        zp_start=dt.datetime(2026, 8, 18, tzinfo=dt.UTC),
        gremium=Gremium(parlament=Parlament.BE, wahlperiode=19, name="Plenum"),
        typ=Stationstyp.PARL_INITIATIV,
        dokumente=[dokument],
    )
    return Vorgang(
        api_id=API_ID,
        titel="Gesetz zur Stärkung der Öffentlichen Bibliotheken",
        kurztitel=UNSET,
        wahlperiode=19,
        typ=Vorgangstyp.GG_LAND_PARL,
        initiatoren=[Autor(organisation="SPD")],
        stationen=[station],
        ids=[VgIdent(id=id_, typ="vorgnr")] if id_ else UNSET,
        verfassungsaendernd=False,
    )


def _make_pipeline(tmp_path: Path, *, settings: dict[str, Any] | None = None, start_time: dt.datetime | None = START_TIME) -> DumpVorgang:
    crawler = Crawler(Spider, Settings({"WAHLPERIODE": 19, "DEBUG": True, "DEBUG_DIR": str(tmp_path / ".debug"), **(settings or {})}))
    crawler.stats = StatsCollector(crawler)
    if start_time is not None:
        crawler.stats.set_value("start_time", start_time)

    return DumpVorgang(crawler)


def _volltexte(payload: dict[str, Any]) -> list[str | None]:
    return [dokument.get("volltext") for station in payload["stationen"] for dokument in station["dokumente"]]


def test__vorgang_to_json__omits_volltext_by_default() -> None:
    """Test the large volltext is removed but the rest of the Dokument stays."""
    payload = json.loads(vorgang_to_json(vorgang=_make_vorgang(), include_volltext=False))

    assert _volltexte(payload) == [None]
    assert payload["stationen"][0]["dokumente"][0]["hash"] == "abc123"


def test__vorgang_to_json__keeps_volltext_if_requested() -> None:
    """Test volltext is part of the JSON if requested."""
    payload = json.loads(vorgang_to_json(vorgang=_make_vorgang(), include_volltext=True))

    assert _volltexte(payload) == [VOLLTEXT]


def test__vorgang_to_json__is_deterministic_and_sorted() -> None:
    """Test same data gives identical text with sorted keys, readable umlauts and trailing newline."""
    first = vorgang_to_json(vorgang=_make_vorgang(), include_volltext=True)
    second = vorgang_to_json(vorgang=_make_vorgang(), include_volltext=True)

    assert first == second
    assert first == json.dumps(json.loads(first), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert "Stärkung" in first


@pytest.mark.parametrize(
    ("id_", "expected"),
    [
        ("V-457263", "V-457263.json"),
        ("V/45 7263", "V_45_7263.json"),
        (None, f"{API_ID}.json"),
    ],
)
def test__get_dump_file_name(id_: str | None, expected: str) -> None:
    """Test file name uses the sanitized PARDOK id and falls back to the api_id."""
    assert get_dump_file_name(vorgang=_make_vorgang(id_=id_)) == expected


def test__dump_vorgang__writes_json_file_into_run_directory(tmp_path: Path) -> None:
    """Test the Vorgang is saved to <DEBUG_DIR>/<start of run>/<Vorgang id>.json and passed on unchanged."""
    pipeline = _make_pipeline(tmp_path)
    vorgang = _make_vorgang()

    result = asyncio.run(pipeline.process_item(vorgang=vorgang))

    dump_file = tmp_path / ".debug" / RUN_DIR_NAME / "V-457263.json"
    assert result is vorgang
    assert dump_file.read_text(encoding="utf-8") == vorgang_to_json(vorgang=vorgang, include_volltext=False)


def test__dump_vorgang__uses_same_run_directory_for_all_items(tmp_path: Path) -> None:
    """Test all items of a run end up in the same directory and a repeated id overwrites the file."""
    pipeline = _make_pipeline(tmp_path)

    asyncio.run(pipeline.process_item(vorgang=_make_vorgang(id_="V-1")))
    asyncio.run(pipeline.process_item(vorgang=_make_vorgang(id_="V-2")))
    asyncio.run(pipeline.process_item(vorgang=_make_vorgang(id_="V-2")))

    assert sorted(path.name for path in (tmp_path / ".debug" / RUN_DIR_NAME).iterdir()) == ["V-1.json", "V-2.json"]


def test__dump_vorgang__includes_volltext_if_configured(tmp_path: Path) -> None:
    """Test DEBUG_INCLUDE_VOLLTEXT keeps the volltext in the file."""
    pipeline = _make_pipeline(tmp_path, settings={"DEBUG_INCLUDE_VOLLTEXT": True})

    asyncio.run(pipeline.process_item(vorgang=_make_vorgang()))

    payload = json.loads((tmp_path / ".debug" / RUN_DIR_NAME / "V-457263.json").read_text(encoding="utf-8"))
    assert _volltexte(payload) == [VOLLTEXT]


def test__dump_vorgang__does_nothing_if_debug_is_off(tmp_path: Path) -> None:
    """Test the pipeline passes the item on and writes nothing if DEBUG is not set."""
    pipeline = _make_pipeline(tmp_path, settings={"DEBUG": False})
    vorgang = _make_vorgang()

    result = asyncio.run(pipeline.process_item(vorgang=vorgang))

    assert result is vorgang
    assert not (tmp_path / ".debug").exists()


def test__dump_vorgang__raises_if_debug_is_on_without_debug_dir(tmp_path: Path) -> None:
    """Test initialization fails if DEBUG is set but DEBUG_DIR is missing."""
    with pytest.raises(ValueError, match="DEBUG_DIR"):
        _make_pipeline(tmp_path, settings={"DEBUG_DIR": None})


def test__dump_vorgang__raises_without_start_time(tmp_path: Path) -> None:
    """Test a missing start_time stat is reported instead of writing to a wrong directory."""
    pipeline = _make_pipeline(tmp_path, start_time=None)

    with pytest.raises(TypeError, match="start_time"):
        asyncio.run(pipeline.process_item(vorgang=_make_vorgang()))


def test__dump_vorgang__drops_unexpected_items(tmp_path: Path) -> None:
    """Test items that are not a Vorgang are dropped."""
    pipeline = _make_pipeline(tmp_path)

    with pytest.raises(DropItem):
        asyncio.run(pipeline.process_item(vorgang={"not": "a vorgang"}))  # ty: ignore[invalid-argument-type]
