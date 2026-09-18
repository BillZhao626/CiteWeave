# Independent development record

Started: 2026-09-11. Owner: personal project creator (identity and legal review pending).

The M0 implementation uses only the new CiteWeave specifications, public dependency APIs,
public algorithms and newly authored synthetic fixtures. No previous project source,
prompts, data, credentials, endpoints, git objects or configuration files are imported.
The earlier review is local-only and excluded from the repository.

This records provenance; it does not certify employment/research contractual ownership.
Contractual review and the final project license remain pending before public release.
Dependencies, fonts, model weights and source documents keep their own licenses.

Synthetic corpus: authored for this project, clearly labeled as synthetic. Functional
retrieval results on it are not evidence of accuracy on real standards or production data.
Font files and downloaded models are not redistributed in the source repository.

Allowed public source directories: src/, tests/, experiments/, deploy/, apps/, contracts/,
docs/, scripts/, migrations/, prompts/ (excluding local/private material). Generated artifacts are exported individually
after inspecting content; never publish the workspace with git add -f or recursive zip.

M1 extension (2026-09-13/14): database migrations, durable ingestion, model/provider adapters,
React product flow, PDF viewer, recovery tests and original observation-station handbook
were authored within CiteWeave. Only this project's specifications, M0 code and public APIs
were used as implementation inputs. The two-page handbook is a distributable candidate
created by scripts/make_m1_fixture.py; it embeds no copied operating-system font file.
