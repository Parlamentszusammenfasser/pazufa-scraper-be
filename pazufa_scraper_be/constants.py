from pathlib import Path

CACHE_DIR_PATH = Path(".cache")
DEBUG_DIR_PATH = Path(".debug")
DOK_CACHE_SUB_DIR_PATH = Path("dokument")
DOK_CACHE_HISTORY_SUB_DIR_PATH = Path(".history")


DOK_BASE_URL = "https://pardok.parlament-berlin.de/starweb/adis/citat/VT"


DOCUMENT_CHECK_MODIFIED_EVERY_DAYS = 7
SUBMISSION_ERROR_GRACE_PERIOD_DAYS = 30


ANGENOMMEN = "Angenommen"
VERTAGT = "Vertagt"
ZUSTIMMUNG = "Zustimmung"
ABGELEHNT = "Abgelehnt"
ZURUECKGEZOGEN = "Zurückgezogen"
HAUSHALTSGESETZ = "Haushaltsgesetz"

ABSTRACT_TYPO_CORRECTIONS = {
    "Ausschusses für Ausschusses für": "Ausschuss für",
    "für für": "für",
    "Umwelt und Klimaschutz": "Umwelt- und Klimaschutz",
}
