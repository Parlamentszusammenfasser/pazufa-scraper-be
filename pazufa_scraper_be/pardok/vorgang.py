from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from pazufa_scraper_be.pardok.dokument import AnyGesetzDokument, parse_dokument
from pazufa_scraper_be.pardok.utils import CoercedStrList, ensure_list, ignore_invalid_factory

logger = logging.getLogger(__name__)


class Nebeneintrag(BaseModel):
    """Secondary entry contains keywords about the Vorgang."""

    reih_nr: int = Field(alias="ReihNr", gt=0)
    desk: str = Field(alias="Desk")


class GesetzVorgang(BaseModel):
    """Root model representing a legislative process ('Vorgang') of type 'Gesetz'."""

    model_config = ConfigDict(extra="forbid", revalidate_instances="always", populate_by_name=True)

    typ: str = Field(alias="VTyp")
    typ_l: str = Field(alias="VTypL")

    id: str = Field(alias="VID")
    reih_nr: int = Field(alias="ReihNr", ge=0, lt=1)
    nr: str = Field(alias="VNr")
    sys: CoercedStrList = Field(alias="VSys", default_factory=list)
    sys_l: CoercedStrList = Field(alias="VSysL", default_factory=list)
    ir: str = Field(alias="VIR")
    nebeneintraege: Annotated[
        list[Nebeneintrag],
        # NOTE: Order of validators is crucial - last runs first.
        BeforeValidator(ignore_invalid_factory(Nebeneintrag)),
        BeforeValidator(ensure_list),
    ] = Field(alias="Nebeneintrag", default_factory=list)
    dokumente: Annotated[
        list[Annotated[AnyGesetzDokument, Field(discriminator="art")]],
        # NOTE: Order of validators is crucial - last runs first.
        BeforeValidator(lambda dokumente: [dokument for dok in dokumente if (dokument := parse_dokument(dok))]),
        BeforeValidator(ensure_list),
    ] = Field(alias="Dokument", default_factory=list)

    def model_post_init(self, _context: object) -> None:
        """After validation, set each child document's back-reference to this Vorgang and shift hour of Dokument Datums to ensure total order."""
        for index, dokument in enumerate(self.dokumente):
            if dokument.dat:
                dokument.dat = dokument.dat + timedelta(hours=index)

            dokument.set_vorgang(self)
