# -*- coding: utf-8 -*-
"""Download providers, journal catalog, and document acquisition helpers."""

from litsurveygrp.multi_journal_downloader import (
    CrossrefJournalProvider,
    JournalConfig,
    LayeredJournalProvider,
    MultiJournalDownloadService,
    NatureCrawlerJournalProvider,
    OpenAlexJournalProvider,
    OpenAlexSearchProvider,
    SUPPORTED_JOURNALS,
    build_default_provider_registry,
    list_supported_journals,
    parse_journal_specs,
)
from litsurveygrp.pdf_utils import (
    HtmlXmlToPdfConverter,
    OpenAccessPdfResolver,
    PdfDownloader,
    PdfPathBuilder,
)
from litsurveygrp.provider_registry import DiscoveryProvider, JournalProviderRegistry, ProviderBuildContext

__all__ = [
    "CrossrefJournalProvider",
    "DiscoveryProvider",
    "HtmlXmlToPdfConverter",
    "JournalConfig",
    "JournalProviderRegistry",
    "LayeredJournalProvider",
    "MultiJournalDownloadService",
    "NatureCrawlerJournalProvider",
    "OpenAccessPdfResolver",
    "OpenAlexJournalProvider",
    "OpenAlexSearchProvider",
    "PdfDownloader",
    "PdfPathBuilder",
    "ProviderBuildContext",
    "SUPPORTED_JOURNALS",
    "build_default_provider_registry",
    "list_supported_journals",
    "parse_journal_specs",
]

