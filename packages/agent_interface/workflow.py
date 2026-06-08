from __future__ import annotations

from enum import Enum


class WorkflowStage(str, Enum):
    RESEARCH = "research"
    PROPOSAL = "proposal"
    CANDIDATE_CODE = "candidate_code"
    FIXTURE_TEST = "fixture_test"
    REPLAY = "replay"
    REPORT = "report"
    HUMAN_REVIEW = "human_review"


TRANSITIONS = {
    WorkflowStage.RESEARCH: {WorkflowStage.PROPOSAL},
    WorkflowStage.PROPOSAL: {WorkflowStage.CANDIDATE_CODE, WorkflowStage.HUMAN_REVIEW},
    WorkflowStage.CANDIDATE_CODE: {WorkflowStage.FIXTURE_TEST},
    WorkflowStage.FIXTURE_TEST: {WorkflowStage.REPLAY, WorkflowStage.CANDIDATE_CODE},
    WorkflowStage.REPLAY: {WorkflowStage.REPORT},
    WorkflowStage.REPORT: {WorkflowStage.HUMAN_REVIEW},
    WorkflowStage.HUMAN_REVIEW: set(),
}


def next_allowed_stages(stage: WorkflowStage | str) -> set[WorkflowStage]:
    return TRANSITIONS[WorkflowStage(stage)]
