from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pazufa_corelib.api_client.models import Autor, Doktyp
from pazufa_corelib.api_client.models import Dokument as PaZuFaDokument
from pazufa_corelib.api_client.types import UNSET, Unset

from pazufa_scraper_be.constants import (
    FILE_BYTE_HASH_FILE_NAME,
    LAST_MODIFIED_FILE_NAME,
    SUMMARY_FILE_NAME,
    TEXT_FILE_NAME,
)
from pazufa_scraper_be.pardok import APrDokument, BaseGesetzDokument, DokTyp, DrsDokument, GVBlDokument, PlPrDokument
from pazufa_scraper_be.pardok.dokument import AnyGesetzDokument, DeskTitelSbMixin, DokArt, ProtokollTyp

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import HttpUrl

logger = logging.getLogger(__name__)

# Maps form DokArt-DokTyp combinations defined in this package to DokTyp values in the PaZuFa core package.
_PARDOK_PAZUFA_DOKTYP_MAPPING = {
    # Gesetzentwuerfe
    (DokArt.Drs, DokTyp.Antr_GesEntw): Doktyp.ENTWURF,
    (DokArt.Drs, DokTyp.VorlBeschl_GesEntw): Doktyp.ENTWURF,
    (DokArt.Drs, DokTyp.VorlBeschl_GesEntwErg): Doktyp.ENTWURF,
    # Lesungen
    (DokArt.PlPr, DokTyp.Behandlung_im_Plenum): Doktyp.REDEPROTOKOLL,
    (DokArt.PlPr, DokTyp.Lesung_I): Doktyp.REDEPROTOKOLL,
    (DokArt.PlPr, DokTyp.Lesung_II): Doktyp.REDEPROTOKOLL,
    # Ausschussberatung und Beschlussempfehlung
    (DokArt.APr, DokTyp.Ausschussberatung): Doktyp.REDEPROTOKOLL,
    (DokArt.APr, DokTyp.ABespr_Par_21_Abs_3_GO): Doktyp.REDEPROTOKOLL,
    (DokArt.APr, DokTyp.APr): Doktyp.REDEPROTOKOLL,
    (DokArt.APr, DokTyp.BeschlEmpf): Doktyp.BESCHLUSSEMPF,
    (DokArt.Drs, DokTyp.BeschlEmpf): Doktyp.BESCHLUSSEMPF,
    # Gesetzesblatt
    (DokArt.GVBl, DokTyp.GVBl): Doktyp.SONSTIG,
    (DokArt.GVBl, DokTyp.Bekannt_GVBl): Doktyp.SONSTIG,
    (DokArt.GVBl, DokTyp.Neufassung): Doktyp.SONSTIG,
    # Verschiedenes
    (DokArt.Drs, DokTyp.AendAntr): Doktyp.ANTRAG,
    (DokArt.Drs, DokTyp.Antr): Doktyp.ANTRAG,
}


def _get_schlagworte(dokument: BaseGesetzDokument) -> list[str] | Unset:
    schlagworte = UNSET
    if isinstance(dokument, DeskTitelSbMixin):
        schlagworte = [dokument.desk] if dokument.desk else UNSET

    return schlagworte


def _get_typ(dokument: BaseGesetzDokument) -> Doktyp:
    if ret_val := _PARDOK_PAZUFA_DOKTYP_MAPPING.get((dokument.art, dokument.typ)):
        return ret_val

    msg = f"[{dokument.vorgang.id} - {dokument.id}]: Using fallback for DokTyp. Got the following (DokArt, DokTyp): ({dokument.art}, {dokument.typ})"
    logger.info(msg)
    return Doktyp.SONSTIG


def _get_drucksnr(dokument: BaseGesetzDokument, dokument_cache_dir: Path | None) -> str:
    if isinstance(dokument, (DrsDokument, PlPrDokument)):
        return dokument.nr

    # Ausschussprotokolle append their type abbreviation to avoid Backend treating them as the same document due to the same Nr.
    if isinstance(dokument, APrDokument):
        cache_dir_suffix = f"-{dokument_cache_dir.name[-2:]}" if dokument_cache_dir else ""
        return f"{dokument.nr}{cache_dir_suffix}"

    if isinstance(dokument, GVBlDokument):
        return f"{dokument.h_nr}/{dokument.jg}"

    return ""


_APR_SUFFIX_LABELS: dict[ProtokollTyp, str] = {
    ProtokollTyp.Beschluss: "Ausschuss Beschlussprotokoll",
    ProtokollTyp.Inhalt: "Ausschuss Inhaltsprotokoll",
    ProtokollTyp.Wort: "Ausschuss Wortprotokoll",
}

_DRS_TYP_LABELS: dict[DokTyp, str] = {
    DokTyp.BeschlEmpf: "Ausschuss Beschlussempfehlung",
    DokTyp.AendAntr: "Änderungsantrag",
}


def _get_titel(dokument: AnyGesetzDokument, dokument_cache_dir: Path) -> str:
    """Derive a human-readable title for a document, falling back to its art label."""
    if isinstance(dokument, (GVBlDokument, DrsDokument)) and isinstance(dokument.titel, str):
        return dokument.titel

    drucksnr = _get_drucksnr(dokument, dokument_cache_dir)
    suffix = f" - {drucksnr}" if drucksnr else ""

    if isinstance(dokument, APrDokument):
        for typ, label in _APR_SUFFIX_LABELS.items():
            if dokument_cache_dir.name.endswith(f"-{typ}"):
                return f"{label}{suffix[:-3]}"  # for Dokument Titel, we do not need the '-ip' suffix

    if isinstance(dokument, DrsDokument) and (label := _DRS_TYP_LABELS.get(dokument.typ)):
        return f"{label}{suffix}"

    if isinstance(dokument, GVBlDokument):
        return f"Gesetz- und Verordnungsblatt Nr. {drucksnr}"

    if dokument.nr is not None:
        return f"{dokument.art_l} - {dokument.nr}"

    # TODO(se-jaeger): log
    return dokument.art_l


def _clean_urheber(urheber: str) -> str:
    return re.sub(r"\s*\(federführend\)", "", urheber, flags=re.IGNORECASE).strip()


def _get_autoren(dokument: AnyGesetzDokument) -> list[Autor]:
    autoren = []

    if not isinstance(dokument, (DrsDokument, APrDokument)):
        return autoren

    is_apr = isinstance(dokument, APrDokument)

    for urheber in dokument.urheber:
        organisation = _clean_urheber(urheber)
        isnt_ausschuss = not bool(re.search("ausschuss", organisation, flags=re.IGNORECASE))

        if is_apr and isnt_ausschuss:
            continue

        autoren.append(
            Autor(
                organisation=organisation,
            )
        )

    return autoren


def _get_zp_modifiziert(dokument: AnyGesetzDokument, dokument_cache_dir: Path) -> datetime:

    last_modified_file = dokument_cache_dir / LAST_MODIFIED_FILE_NAME

    if last_modified_file.exists():
        dt = datetime.fromisoformat(last_modified_file.read_text())
        return datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
    if dokument.dat is not None:
        return dokument.dat
    msg = "Could not resolve zp_modifiziert."
    raise ValueError(msg)


def _get_zp_referenz(dokument: AnyGesetzDokument) -> datetime:

    if dokument.dat is not None:
        return dokument.dat

    msg = f"[{dokument.vorgang.id} - {dokument.id}]: Using fallback for document timestamp zp_referenz."
    logger.warning(msg)
    return datetime.now(tz=UTC)


def _get_zeitpunkte(dokument: AnyGesetzDokument, dokument_cache_dir: Path) -> tuple[Unset | datetime, datetime, datetime]:
    """Extract timestamps relevant for document."""
    zp_referenz = _get_zp_referenz(dokument)
    zp_modifiziert = _get_zp_modifiziert(dokument, dokument_cache_dir)

    # TODO(anyone): revisit this
    zp_erstellt = UNSET

    return zp_erstellt, zp_referenz, zp_modifiziert


def _check_text_file(dokument: AnyGesetzDokument, text_file: Path) -> bool:
    text_file_missing = not text_file.exists()

    if text_file_missing:
        msg = f"[{dokument.vorgang.id} - {dokument.id}]: Text file does not exist, ignoring Dokument."
        logger.warning(msg)

    return text_file_missing


def _check_hash_file(dokument: AnyGesetzDokument, file_byte_hash_file: Path) -> bool:
    hash_file_missing = not file_byte_hash_file.exists()

    if hash_file_missing:
        msg = f"[{dokument.vorgang.id} - {dokument.id}]: Hash file does not exist, ignoring Dokument."
        logger.warning(msg)
    return hash_file_missing


def _check_summary_file(dokument: AnyGesetzDokument, summary_file: Path) -> bool:
    summary_file_missing = not summary_file.exists()

    if summary_file_missing:
        msg = f"[{dokument.vorgang.id} - {dokument.id}]: Summary file does not exist."
        logger.info(msg)

    return summary_file_missing


def build_pazufa_dokument(dokument: AnyGesetzDokument, dokument_cache_dir: Path | None, url: HttpUrl) -> PaZuFaDokument | None:
    """Build a PaZuFaDokument from a cached document, returning None if required files are missing."""
    if dokument_cache_dir is None:
        return None

    text_file = dokument_cache_dir / TEXT_FILE_NAME
    summary_file = dokument_cache_dir / SUMMARY_FILE_NAME
    file_byte_hash_file = dokument_cache_dir / FILE_BYTE_HASH_FILE_NAME

    text_file_missing = _check_text_file(dokument, text_file)
    hash_file_missing = _check_hash_file(dokument, file_byte_hash_file)

    if text_file_missing or hash_file_missing:
        return None

    summary_file_missing = _check_summary_file(dokument, summary_file)

    volltext = text_file.read_text()
    hash_ = file_byte_hash_file.read_text()
    zusammenfassung = UNSET if summary_file_missing else summary_file.read_text()

    zp_erstellt, zp_referenz, zp_modifiziert = _get_zeitpunkte(dokument, dokument_cache_dir)

    return PaZuFaDokument(
        typ=_get_typ(dokument),
        titel=_get_titel(dokument, dokument_cache_dir),
        volltext=volltext,
        zp_erstellt=zp_erstellt,
        zp_referenz=zp_referenz,
        zp_modifiziert=zp_modifiziert,
        link=str(url),
        hash_=hash_,
        autoren=_get_autoren(dokument),
        drucksnr=_get_drucksnr(dokument, dokument_cache_dir),
        zusammenfassung=zusammenfassung,
        schlagworte=_get_schlagworte(dokument),
        # NOTE: Following should be revisited
        kurztitel=UNSET,
        vorwort=UNSET,
        meinung=UNSET,
    )
