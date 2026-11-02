"""Standalone offline owner-report processing; no canonical-model integration."""

from howreliable.nlp.grouping import validate_partition_assignments
from howreliable.nlp.owner_reports import ProcessingError, process_owner_reports
from howreliable.nlp.schemas import (
    Association,
    ComponentMention,
    ExtractionRow,
    ProcessingConfig,
    RunProvenance,
    SymptomMention,
)

__all__ = [
    "Association",
    "ComponentMention",
    "ExtractionRow",
    "ProcessingConfig",
    "ProcessingError",
    "RunProvenance",
    "SymptomMention",
    "process_owner_reports",
    "validate_partition_assignments",
]
