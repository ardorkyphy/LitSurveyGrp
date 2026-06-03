# RefChaser Package Layout

This package is organized around the paper-survey pipeline.

- `models.py` and `paper_models.py`: shared article, reference, and PDF validation records.
- `download/`: public download API exports.
- `multi_journal_downloader.py`: journal catalog, metadata providers, and batch download orchestration.
- `nature_aging_downloader.py`: Nature-family HTML crawler used by the catalog.
- `pdf_utils.py`: PDF download, open-access PDF resolution, HTML/XML-to-PDF conversion, naming, and validation.
- `pipeline.py`: end-to-end survey workflow orchestration for download, enrichment, classification, stats, and visualization.
- `classify/`: public classification API exports.
- `paper_classifier.py`: clustering, domain labeling, folder organization, and basic stats.
- `references/`: public reference extraction API exports.
- `reference_extractor.py`: PDF reference-section parsing and manifest updates.
- `exporters/`: public export API exports.
- `citation_exporter.py`: source/reference RIS export and reference relevance filtering.
- `__main__.py`: command-line interface.
