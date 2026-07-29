"""Provider-neutral ranking over already-eligible I4-A candidates."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from batch87_apprentice.common.errors import ValidationError

from .contracts import (
    RANKABLE_SECTIONS,
    RankComponents,
    RankedCandidate,
    RetrievalCandidate,
    RetrievalRequest,
)


@runtime_checkable
class RelevanceRanker(Protocol):
    """Rank immutable, already-eligible candidates without persistence access."""

    @property
    def strategy(self) -> str: ...

    def rank(
        self,
        request: RetrievalRequest,
        eligible_candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RankedCandidate, ...]: ...


class DeterministicFallbackRanker:
    """Auditable structural ordering; this is not semantic relevance."""

    @property
    def strategy(self) -> str:
        return "deterministic_fallback_v1"

    @staticmethod
    def _components(candidate: RetrievalCandidate) -> RankComponents:
        return RankComponents(
            required_priority=0 if candidate.required else 1,
            section_priority=RANKABLE_SECTIONS.index(candidate.target_section),
            finalized_injection_order=candidate.injection_order,
            stable_tiebreak=(
                f"{candidate.source_kind}:{candidate.source_id}:"
                f"{candidate.context_item_id}"
            ),
        )

    @staticmethod
    def _sort_key(
        candidate: RetrievalCandidate,
        components: RankComponents,
    ) -> tuple[object, ...]:
        # Required entries retain their exact finalized relative order. Optional
        # entries use section priority before finalized order.
        if candidate.required:
            return (
                components.required_priority,
                components.finalized_injection_order,
                components.section_priority,
                components.stable_tiebreak,
            )
        return (
            components.required_priority,
            components.section_priority,
            components.finalized_injection_order,
            components.stable_tiebreak,
        )

    def rank(
        self,
        request: RetrievalRequest,
        eligible_candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RankedCandidate, ...]:
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        if request.ranking_strategy != self.strategy:
            raise ValidationError(
                "retrieval request ranking strategy does not match ranker"
            )
        if not isinstance(eligible_candidates, tuple):
            raise TypeError("eligible_candidates must be an immutable tuple")
        if any(
            not isinstance(candidate, RetrievalCandidate)
            for candidate in eligible_candidates
        ):
            raise TypeError("eligible_candidates contains an invalid value")
        if any(not candidate.includable for candidate in eligible_candidates):
            raise ValidationError(
                "fallback ranker accepts only eligible materialized candidates"
            )
        item_ids = [candidate.context_item_id for candidate in eligible_candidates]
        if len(set(item_ids)) != len(item_ids):
            raise ValidationError("rank input contains duplicate context items")

        prepared = tuple(
            (candidate, self._components(candidate))
            for candidate in eligible_candidates
        )
        ordered = sorted(
            prepared,
            key=lambda pair: self._sort_key(pair[0], pair[1]),
        )
        return tuple(
            RankedCandidate(
                candidate=candidate,
                components=components,
                explanation=(
                    (
                        "required context precedes optional context"
                        if candidate.required
                        else "optional context follows required context"
                    ),
                    (
                        "required finalized order is authoritative"
                        if candidate.required
                        else "optional section priority is policy, evidence, memory"
                    ),
                    "stable source and context identity resolves any remaining tie",
                    "no semantic relevance is claimed",
                ),
                final_rank=rank,
            )
            for rank, (candidate, components) in enumerate(ordered)
        )
