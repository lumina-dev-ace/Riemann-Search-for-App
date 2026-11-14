## Research data or network change

### Change type
- [ ] New research range
- [ ] Checkpoint advancement proposal
- [ ] Schema / validator change
- [ ] Documentation or progress site change
- [ ] Optional contribution-service change
- [ ] Other

### Research range details (if applicable)
- Record file(s):
- Inclusive index range:
- FLINT/Arb backend and precision:
- Verification method and supporting reproducibility information:

### Checkpoint proposal (if applicable)
- Current global checkpoint:
- Proposed checkpoint:
- Evidence every intervening index is present exactly once and Arb-rechecked:

### Review checklist
- [ ] No local database, private experiment file, personal information, or credential is included.
- [ ] Records follow the versioned schema under `data/schema/`.
- [ ] `python tools/validate_research_repository.py` passes.
- [ ] `python -m unittest discover -s tests -p "test_*.py" -v` passes.
- [ ] The progress site validator and JavaScript syntax check pass.
- [ ] The proposal does not decrease or skip the global checkpoint.
- [ ] Numerical claims describe finite numerical verification, not proof of RH.
