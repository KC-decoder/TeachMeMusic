"""Private MusicXML standards, validation, and conformance infrastructure.

Nothing in this package is part of the public canonical score API. XML-library
objects must terminate inside the score-ingestion boundary established by
ADR-0001 and ADR-0005. Import concrete helpers from their defining modules so
module command-line entry points remain deterministic and warning-free.
"""
