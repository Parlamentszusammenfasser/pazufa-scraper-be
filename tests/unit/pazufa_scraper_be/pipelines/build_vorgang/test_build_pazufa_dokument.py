from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pazufa_corelib.api_client.models import Autor
from pazufa_corelib.api_client.models import Doktyp as PaZuFa_DokTyp
from pazufa_corelib.api_client.types import UNSET
from pydantic import HttpUrl

from pazufa_scraper_be.constants import (
    FILE_BYTE_HASH_FILE_NAME,
    LAST_MODIFIED_FILE_NAME,
    SUMMARY_FILE_NAME,
    TEXT_FILE_NAME,
)
from pazufa_scraper_be.pardok import DokTyp
from pazufa_scraper_be.pardok.dokument import (
    AnyGesetzDokument,
    APrDokument,
    BaseGesetzDokument,
    DokArt,
    DrsDokument,
    GVBlDokument,
    PlPrDokument,
    ProtokollTyp,
)
from pazufa_scraper_be.pardok.vorgang import GesetzVorgang
from pazufa_scraper_be.pipelines.build_vorgang.build_pazufa_dokument import (
    _check_hash_file,
    _check_summary_file,
    _check_text_file,
    _clean_urheber,
    _get_autoren,
    _get_drucksnr,
    _get_titel,
    _get_typ,
    _get_zeitpunkte,
    _get_zp_modifiziert,
    _get_zp_referenz,
    build_pazufa_dokument,
)
from tests.unit.pazufa_scraper_be.helpers import build_gesetz_vorgang_data


@pytest.fixture
def gesetz_vorgang_data() -> dict[str, Any]:
    """Provides a basic GesetzVorgang dict instance."""
    return {}


@pytest.mark.parametrize(
    ("dok_art", "dok_typ", "expected_pazufa_typ"),
    [
        # Gesetzentwuerfe
        (DokArt.Drs, DokTyp.Antr_GesEntw, PaZuFa_DokTyp.ENTWURF),
        (DokArt.Drs, DokTyp.VorlBeschl_GesEntw, PaZuFa_DokTyp.ENTWURF),
        (DokArt.Drs, DokTyp.VorlBeschl_GesEntwErg, PaZuFa_DokTyp.ENTWURF),
        # Lesungen
        (DokArt.PlPr, DokTyp.Behandlung_im_Plenum, PaZuFa_DokTyp.REDEPROTOKOLL),
        (DokArt.PlPr, DokTyp.Lesung_I, PaZuFa_DokTyp.REDEPROTOKOLL),
        (DokArt.PlPr, DokTyp.Lesung_II, PaZuFa_DokTyp.REDEPROTOKOLL),
        # Ausschussberatung und Beschlussempfehlung
        (DokArt.APr, DokTyp.Ausschussberatung, PaZuFa_DokTyp.REDEPROTOKOLL),
        (DokArt.APr, DokTyp.ABespr_Par_21_Abs_3_GO, PaZuFa_DokTyp.REDEPROTOKOLL),
        (DokArt.APr, DokTyp.APr, PaZuFa_DokTyp.REDEPROTOKOLL),
        (DokArt.APr, DokTyp.BeschlEmpf, PaZuFa_DokTyp.BESCHLUSSEMPF),
        (DokArt.Drs, DokTyp.BeschlEmpf, PaZuFa_DokTyp.BESCHLUSSEMPF),
        # Gesetzesblatt
        (DokArt.GVBl, DokTyp.GVBl, PaZuFa_DokTyp.SONSTIG),
        (DokArt.GVBl, DokTyp.Bekannt_GVBl, PaZuFa_DokTyp.SONSTIG),
        (DokArt.GVBl, DokTyp.Neufassung, PaZuFa_DokTyp.SONSTIG),
        # Verschiedenes
        (DokArt.Drs, DokTyp.AendAntr, PaZuFa_DokTyp.ANTRAG),
        (DokArt.Drs, DokTyp.Antr, PaZuFa_DokTyp.ANTRAG),
    ],
)
def test_get_typ(base_dok_data: dict[str, Any], dok_art: DokArt, dok_typ: DokTyp, expected_pazufa_typ: PaZuFa_DokTyp) -> None:
    """Verify mapping of (DokArt, DokTyp) to PaZuFa Doktyp for the mapped cases."""
    gesetz_dokument = BaseGesetzDokument.model_validate(base_dok_data)
    gesetz_dokument.art = dok_art
    gesetz_dokument.typ = dok_typ

    actual_pazufa_typ = _get_typ(gesetz_dokument)

    assert actual_pazufa_typ == expected_pazufa_typ


def test_get_typ_fallback(base_dok_data: dict[str, Any], base_vorgang_data: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    """Verify mapping of (DokArt, DokTyp) to PaZuFa Doktyp for the fallback case."""
    # random (*promise*) non-mapped combination
    dok_art, dok_typ, expected_pazufa_typ = (DokArt.GVBl, DokTyp.Antr_GesEntw, PaZuFa_DokTyp.SONSTIG)

    gesetz_dokument = BaseGesetzDokument.model_validate(base_dok_data)
    gesetz_dokument.art = dok_art
    gesetz_dokument.typ = dok_typ

    gesetz_vorgang_data = build_gesetz_vorgang_data(
        base_vorgang_data=base_vorgang_data,
        dok_datas=[base_dok_data],
        neben_eintrag_data=[
            {"ReihNr": 1, "Desk": "Desk 1"},
            {"ReihNr": 2, "Desk": "Desk 2"},
        ],
    )
    gesetz_vorgang = GesetzVorgang.model_validate(gesetz_vorgang_data)
    gesetz_dokument.set_vorgang(gesetz_vorgang)

    caplog.set_level(logging.INFO)

    actual_pazufa_typ = _get_typ(gesetz_dokument)

    assert actual_pazufa_typ == expected_pazufa_typ
    assert "Using fallback for DokTyp" in caplog.text


@pytest.mark.parametrize(
    ("fixture_name", "dokument_class", "expected_drucksnr"),
    [
        ("drs_data", DrsDokument, "123/2024"),
        ("plpr_data", PlPrDokument, "123/2024"),
        ("apr_data", APrDokument, "123/2024-42"),
        ("gvbl_data", GVBlDokument, "12345/2024"),
        ("base_dok_data", BaseGesetzDokument, ""),
    ],
)
def test_get_drucksnr(request: pytest.FixtureRequest, fixture_name: str, dokument_class: type[BaseGesetzDokument], expected_drucksnr: str) -> None:
    """Verify Durchsachennummer assignment."""
    data = request.getfixturevalue(fixture_name)
    dokument = dokument_class.model_validate(data)

    dokument_cache_dir = Path("something/fake/42")

    drucksnr = _get_drucksnr(dokument, dokument_cache_dir)
    assert drucksnr == expected_drucksnr


def test_get_drucksnr_cache_dir_is_none(apr_data: dict[str, Any]) -> None:
    """Verify Durchsachennummer assignment for APR without cache dir."""
    dokument = APrDokument.model_validate(apr_data)
    dokument_cache_dir = None

    drucksnr = _get_drucksnr(dokument, dokument_cache_dir)
    assert drucksnr == "123/2024"


@pytest.mark.parametrize(
    ("dok_class", "fixture_name", "expected_titel"),
    [
        (GVBlDokument, "gvbl_data", "Title GVBl"),
        (DrsDokument, "drs_data", "Title Drs"),
    ],
)
def test_get_titel_returns_titel_string(
    request: pytest.FixtureRequest,
    dok_class: type[GVBlDokument | DrsDokument],
    fixture_name: str,
    expected_titel: str,
) -> None:
    """Verify that a non-None titel field is returned directly for GVBl and Drs documents."""
    data = request.getfixturevalue(fixture_name)
    dokument = dok_class.model_validate(data)

    assert _get_titel(dokument, Path("some/fake/dir")) == expected_titel


@pytest.mark.parametrize(
    ("cache_dir_suffix", "expected_titel"),
    [
        (f"-{ProtokollTyp.Beschluss}", "Ausschuss Beschlussprotokoll - 123/2024"),
        (f"-{ProtokollTyp.Inhalt}", "Ausschuss Inhaltsprotokoll - 123/2024"),
        (f"-{ProtokollTyp.Wort}", "Ausschuss Wortprotokoll - 123/2024"),
    ],
)
def test_get_titel_apr(apr_data: dict[str, Any], cache_dir_suffix: str, expected_titel: str) -> None:
    """Verify APrDokument title is derived from cache dir suffix."""
    dokument = APrDokument.model_validate(apr_data)
    cache_dir = Path(f"some/fake/dok{cache_dir_suffix}")

    assert _get_titel(dokument, cache_dir) == expected_titel


@pytest.mark.parametrize(
    ("dok_typ", "expected_titel"),
    [
        (DokTyp.BeschlEmpf, "Ausschuss Beschlussempfehlung - 123/2024"),
        (DokTyp.AendAntr, "Änderungsantrag - 123/2024"),
    ],
)
def test_get_titel_drs_typ(drs_data: dict[str, Any], dok_typ: DokTyp, expected_titel: str) -> None:
    """Verify DrsDokument title is derived from DokTyp when titel is None."""
    data = {**drs_data, "Titel": None, "DokTyp": str(dok_typ)}
    dokument = DrsDokument.model_validate(data)

    assert _get_titel(dokument, Path("some/fake/dir")) == expected_titel


def test_get_titel_gvbl_fallback(gvbl_data: dict[str, Any]) -> None:
    """Verify GVBlDokument falls back to HNr/Jg when titel is None."""
    data = {**gvbl_data, "Titel": None}
    dokument = GVBlDokument.model_validate(data)

    assert _get_titel(dokument, Path("some/fake/dir")) == "Gesetz- und Verordnungsblatt Nr. 12345/2024"


def test_get_titel_generic_fallback_with_nr(plpr_data: dict[str, Any]) -> None:
    """Verify generic fallback returns '{art_l} - {nr}' for documents without a specific title rule."""
    dokument = PlPrDokument.model_validate(plpr_data)

    assert _get_titel(dokument, Path("some/fake/dir")) == "Plenumsprotokoll - 123/2024"


@pytest.mark.parametrize(
    ("input_text", "expected_text"),
    [
        ("Author Name", "Author Name"),
        ("Author Name (federführend)", "Author Name"),
        ("Author Name (FEDERFÜHREND)", "Author Name"),
        (" Author Name (federführend) ", "Author Name"),
        ("Vorname (federführend) Nachname (federführend)", "Vorname Nachname"),
        ("(federführend)", ""),
        ("Name (federführend) Extra", "Name Extra"),
    ],
)
def test_clean_urheber(input_text: str, expected_text: str) -> None:
    """Verify that urheber strings are cleaned of '(federführend)' suffixes and whitespace."""
    assert _clean_urheber(input_text) == expected_text


@pytest.mark.parametrize(
    ("last_modified_str", "expected_date"),
    [
        ("2024-05-10T12:34:56+00:00", datetime(2024, 5, 10, tzinfo=UTC)),
        ("2024-12-31T23:59:59+00:00", datetime(2024, 12, 31, tzinfo=UTC)),
    ],
)
def test_get_zp_modifiziert_with_last_modified(tmp_path: Path, plpr_data: dict[str, Any], last_modified_str: str, expected_date: datetime) -> None:
    """Verify that if LAST_MODIFIED.txt is present, it's used and normalized to midnight UTC."""
    cache_dir = tmp_path / "dokument-folder"
    cache_dir.mkdir()
    (cache_dir / LAST_MODIFIED_FILE_NAME).write_text(last_modified_str)

    dokument = PlPrDokument.model_validate(plpr_data)

    actual_date = _get_zp_modifiziert(dokument, cache_dir)
    assert actual_date == expected_date


def test_get_zp_modifiziert_with_dat_fallback(tmp_path: Path, plpr_data: dict[str, Any]) -> None:
    """Verify that if LAST_MODIFIED.txt is missing, the document's dat field is used."""
    cache_dir = tmp_path / "dokument-folder"
    cache_dir.mkdir()

    data = {**plpr_data, "DokDat": "15.06.2024"}
    dokument = PlPrDokument.model_validate(data)
    expected_date = datetime(2024, 6, 15, tzinfo=UTC)

    actual_date = _get_zp_modifiziert(dokument, cache_dir)
    assert actual_date == expected_date


def test_get_zp_modifiziert_raises_value_error(tmp_path: Path, plpr_data: dict[str, Any]) -> None:
    """Verify that ValueError is raised if no data source is available."""
    cache_dir = tmp_path / "dokument-folder"
    cache_dir.mkdir()

    data = {**plpr_data, "DokDat": None}
    dokument = PlPrDokument.model_validate(data)

    with pytest.raises(ValueError, match=r"Could not resolve zp_modifiziert."):
        _get_zp_modifiziert(dokument, cache_dir)


def test_get_zp_referenz_with_dat(plpr_data: dict[str, Any]) -> None:
    """Verify that when dokument.dat is set, it is returned directly."""
    dokument = PlPrDokument.model_validate(plpr_data)

    actual_datetime = _get_zp_referenz(dokument)

    expected_date = datetime(2024, 5, 10, tzinfo=UTC)
    assert actual_datetime == expected_date


def test_get_zp_referenz_with_none_dat(base_vorgang_data: dict[str, Any], plpr_data: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    """Verify that when dokument.dat is None, a warning is logged and datetime.now(tz=UTC) is returned."""
    data = {**plpr_data, "DokDat": None}
    dokument = PlPrDokument.model_validate(data)

    gesetz_vorgang_data = build_gesetz_vorgang_data(
        base_vorgang_data=base_vorgang_data,
        dok_datas=[data],
        neben_eintrag_data=[],
    )
    gesetz_vorgang = GesetzVorgang.model_validate(gesetz_vorgang_data)
    dokument.set_vorgang(gesetz_vorgang)

    caplog.set_level(logging.WARNING)

    before_call = datetime.now(tz=UTC)
    actual_datetime = _get_zp_referenz(dokument)
    after_call = datetime.now(tz=UTC)

    assert before_call <= actual_datetime <= after_call
    assert "Using fallback for document timestamp zp_referenz" in caplog.text


def test_get_zeitpunkte(tmp_path: Path, plpr_data: dict[str, Any]) -> None:
    """Verify _get_zeitpunkte returns correct zp_erstellt, zp_referenz, and zp_modifiziert values."""
    cache_dir = tmp_path / "dokument-folder"
    cache_dir.mkdir()

    dokument = PlPrDokument.model_validate(plpr_data)

    expected_dt = datetime(2024, 5, 10, tzinfo=UTC)
    assert _get_zeitpunkte(dokument, cache_dir) == (UNSET, expected_dt, expected_dt)


@pytest.mark.parametrize(
    ("fixture_name", "dokument", "urheber", "expected_autoren"),
    [
        (
            "drs_data",
            DrsDokument,
            ["Author 1", "Ausschuss für Finanzen", "Another Author"],
            [Autor(organisation="Author 1"), Autor(organisation="Ausschuss für Finanzen"), Autor(organisation="Another Author")],
        ),
        (
            "apr_data",
            APrDokument,
            ["Ausschuss für Recht", "Private Person", "Interparl. Ausschuss"],
            [Autor(organisation="Ausschuss für Recht"), Autor(organisation="Interparl. Ausschuss")],
        ),
        (
            "gvbl_data",
            GVBlDokument,
            ["Author 1", "Ausschuss für Finanzen"],
            [],
        ),
        (
            "drs_data",
            DrsDokument,
            [],
            [],
        ),
    ],
)
def test_get_autoren(request: pytest.FixtureRequest, fixture_name: str, dokument: AnyGesetzDokument, urheber: list[str], expected_autoren: list[Autor]) -> None:
    """Verify extraction and filtering of authors based on document type."""
    data = request.getfixturevalue(fixture_name)

    if dokument in (DrsDokument, APrDokument):
        data["Urheber"] = urheber

    doc = dokument.model_validate(data)
    actual_autoren = _get_autoren(doc)

    assert actual_autoren == expected_autoren


@pytest.mark.parametrize(
    ("file_exists", "expected_result", "log_level"),
    [
        (True, False, None),
        (False, True, logging.WARNING),
    ],
)
def test_check_text_file(  # noqa: PLR0913
    tmp_path: Path,
    base_vorgang_data: dict[str, Any],
    plpr_data: dict[str, Any],
    file_exists: bool,  # noqa: FBT001
    expected_result: bool,  # noqa: FBT001
    log_level: logging._Level | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that _check_text_file correctly identifies missing text files and logs warnings."""
    dokument = PlPrDokument.model_validate(plpr_data)

    gesetz_vorgang_data = build_gesetz_vorgang_data(
        base_vorgang_data=base_vorgang_data,
        dok_datas=[plpr_data],
        neben_eintrag_data=[],
    )
    gesetz_vorgang = GesetzVorgang.model_validate(gesetz_vorgang_data)
    dokument.set_vorgang(gesetz_vorgang)

    text_file = tmp_path / "TEXT.txt"
    if file_exists:
        text_file.write_text("some text")

    if log_level:
        caplog.set_level(log_level)

    result = _check_text_file(dokument, text_file)
    assert result == expected_result

    if not file_exists:
        assert "Text file does not exist" in caplog.text


@pytest.mark.parametrize(
    ("file_exists", "expected_result", "log_level"),
    [
        (True, False, None),
        (False, True, logging.WARNING),
    ],
)
def test_check_hash_file(  # noqa: PLR0913
    tmp_path: Path,
    base_vorgang_data: dict[str, Any],
    plpr_data: dict[str, Any],
    file_exists: bool,  # noqa: FBT001
    expected_result: bool,  # noqa: FBT001
    log_level: None | logging._Level,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that _check_hash_file correctly identifies missing hash files and logs warnings."""
    dokument = PlPrDokument.model_validate(plpr_data)
    gesetz_vorgang_data = build_gesetz_vorgang_data(
        base_vorgang_data=base_vorgang_data,
        dok_datas=[plpr_data],
        neben_eintrag_data=[],
    )
    gesetz_vorgang = GesetzVorgang.model_validate(gesetz_vorgang_data)
    dokument.set_vorgang(gesetz_vorgang)

    hash_file = tmp_path / "HASH.txt"
    if file_exists:
        hash_file.write_text("some hash")

    if log_level:
        caplog.set_level(log_level)

    result = _check_hash_file(dokument, hash_file)
    assert result == expected_result

    if not file_exists:
        assert "Hash file does not exist" in caplog.text


@pytest.mark.parametrize(
    ("file_exists", "expected_result", "log_level"),
    [
        (True, False, None),
        (False, True, logging.INFO),
    ],
)
def test_check_summary_file(  # noqa: PLR0913
    tmp_path: Path,
    base_vorgang_data: dict[str, Any],
    plpr_data: dict[str, Any],
    file_exists: bool,  # noqa: FBT001
    expected_result: bool,  # noqa: FBT001
    log_level: None | logging._Level,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that _check_summary_file correctly identifies missing summary files and logs info."""
    dokument = PlPrDokument.model_validate(plpr_data)
    gesetz_vorgang_data = build_gesetz_vorgang_data(
        base_vorgang_data=base_vorgang_data,
        dok_datas=[plpr_data],
        neben_eintrag_data=[],
    )
    gesetz_vorgang = GesetzVorgang.model_validate(gesetz_vorgang_data)
    dokument.set_vorgang(gesetz_vorgang)

    summary_file = tmp_path / "SUMMARY.txt"
    if file_exists:
        summary_file.write_text("some summary")

    if log_level:
        caplog.set_level(log_level)

    result = _check_summary_file(dokument, summary_file)
    assert result == expected_result

    if not file_exists:
        assert "Summary file does not exist" in caplog.text


def test_build_pazufa_dokument_cache_dir_none(plpr_data: dict[str, Any]) -> None:
    """Verify that build_pazufa_dokument returns None if cache_dir is None."""
    dokument = PlPrDokument.model_validate(plpr_data)
    url = HttpUrl("https://example.com/doc123")

    result = build_pazufa_dokument(dokument, None, url)
    assert result is None


def test_build_pazufa_dokument_happy_path(tmp_path: Path, plpr_data: dict[str, Any], base_vorgang_data: dict[str, Any]) -> None:
    """Verify the happy path for building a PaZuFaDokument."""
    cache_dir = tmp_path / "dokument-folder"
    cache_dir.mkdir()

    text_content = "This is the extracted text content."
    hash_content = "abc123hash"
    summary_content = "This is a short summary."
    last_modified_str = "2024-05-10T12:34:56+00:00"

    (cache_dir / TEXT_FILE_NAME).write_text(text_content)
    (cache_dir / FILE_BYTE_HASH_FILE_NAME).write_text(hash_content)
    (cache_dir / SUMMARY_FILE_NAME).write_text(summary_content)
    (cache_dir / LAST_MODIFIED_FILE_NAME).write_text(last_modified_str)

    dokument = PlPrDokument.model_validate(plpr_data)

    gesetz_vorgang = GesetzVorgang.model_validate(base_vorgang_data)
    dokument.set_vorgang(gesetz_vorgang)

    url = HttpUrl("https://example.com/doc123")

    result = build_pazufa_dokument(dokument, cache_dir, url)

    assert result is not None
    assert result.volltext == text_content
    assert result.hash_ == hash_content
    assert result.zusammenfassung == summary_content
    assert result.link == str(url)

    assert result.zp_modifiziert == datetime(2024, 5, 10, tzinfo=UTC)
