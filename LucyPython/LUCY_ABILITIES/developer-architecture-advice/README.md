# Developer Architecture Advice
## Goal
Provide a repeatable way to tackle difficult software design and architecture problems instead of trying to imagine an entire finished system at once.
## Core Method
Use this loop:
Goal -> constraints -> invariants -> data flow -> ownership -> interfaces -> risky assumptions -> prototype -> failure testing -> refactor.
Build one small end-to-end vertical slice first. Test the assumptions most likely to invalidate the design. Introduce abstractions from evidence rather than guessing the perfect architecture beforehand.
## Key Principle
Implementation answers "how do I code this behavior?"
Architecture answers:
- Who owns this responsibility?
- Where does state live?
- How does information flow?
- What can fail?
- Who recovers?
- What can be replaced independently?
- Which assumptions must be proven first?
## Stability / Risk
Safe. This is a reasoning framework and does not modify project code.
