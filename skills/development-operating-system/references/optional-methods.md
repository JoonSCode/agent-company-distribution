# Optional Implementation Lenses

Use only a lens that changes this slice's design; skip the rest. Keep any
material rationale in the existing handoff, without a new artifact or quota.
These are Company adaptations of sources checked in the supplied research on
2026-10-26, not validated prompts or execution authority. Local conventions and
required safety, accessibility and compatibility controls remain binding.

| Lens and source | Use / skip | Benefit, limit, and reversal evidence |
| --- | --- | --- |
| [Wrong abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction) | Use when shared code grows caller-specific flags and incompatible change reasons; skip duplication when it expresses one stable rule. | Separating accidental coupling can cost less than reuse. Do not duplicate a shared security or business invariant; repeated coordinated changes or inconsistent fixes are evidence to restore a common seam. |
| [Deep modules](https://web.stanford.edu/~ouster/cgi-bin/aposd.php) | Use when a proposed helper or module exposes nearly as much complexity as it hides; skip a new layer without a concrete caller benefit. | Judge interface burden rather than function length. Hiding unrelated responsibilities can create a monolith; revise when callers still manage internal details or independently changing responsibilities become coupled. |
| [Small changes](https://google.github.io/eng-practices/review/developer/small-cls.html) | Use when review or rollback is obscured by unrelated changes; do not split an atomic migration, interface and consumers, or required tests into unsafe intermediate states. | A coherent, verifiable change shortens feedback. Line count is not quality; merge or reslice when an intermediate candidate breaks an invariant or cannot be independently understood and verified. |
| [Hyrum's Law](https://www.hyrumslaw.com/) | Use for identified public callers, persisted data or widely consumed behavior; skip an exhaustive search for imaginary consumers of local code. | Surfaces compatibility assumptions beyond documentation. It is not a ban on change; a traced consumer, stored-data sample or focused compatibility failure changes the migration or preservation decision. |

