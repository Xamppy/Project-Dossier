"""Tests — alineación depth_level persona con trigger PostgreSQL (1 crédito = basic)."""
from __future__ import annotations

import inspect

from dossier.services import person_research_pipeline


def test_person_pipeline_persists_basic_depth_level():
    """El trigger debita 1 cr solo con depth_level='basic'; standard cobraría 3."""
    source = inspect.getsource(person_research_pipeline.run_person_research_and_persist)
    assert 'depth_level="basic"' in source
    assert 'depth_level="standard"' not in source
