# -*- coding: utf-8 -*-
"""Download providers, journal catalog, and document acquisition helpers."""

from refchaser.multi_journal_downloader import (
    CrossrefJournalProvider,
    JournalConfig,
    MultiJournalDownloadService,
    OpenAlexJournalProvider,
    SUPPORTED_JOURNALS,
    list_supported_journals,
    parse_journal_specs,
)
from refchaser.pdf_utils import (
    HtmlXmlToPdfConverter,
    OpenAccessPdfResolver,
    PdfDownloader,
    PdfPathBuilder,
)

__all__ = [
    "CrossrefJournalProvider",
    "HtmlXmlToPdfConverter",
    "JournalConfig",
    "MultiJournalDownloadService",
    "OpenAccessPdfResolver",
    "OpenAlexJournalProvider",
    "PdfDownloader",
    "PdfPathBuilder",
    "SUPPORTED_JOURNALS",
    "list_supported_journals",
    "parse_journal_specs",
]
