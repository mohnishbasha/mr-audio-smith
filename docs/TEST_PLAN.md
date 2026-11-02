# mr-audio-smith Test Plan

Version: 1.0 (spec, pre-implementation)
Date: 2026-11-01
Owner: Serverless Ventures LLC
Related documents: PRD.md (FR and NFR ids), ARCHITECTURE.md (data formats, ADRs), SPRINT_PLAN.md (task ids), DESIGN.md (player and Studio states)

This plan lists every automated and manual test the project commits to, mapped to functional requirements (FR-001 to FR-026). Sprint tasks in SPRINT_PLAN.md reference the scenario ids defined here in their **Tests** field.

## Contents

1. Strategy and test pyramid
2. Coverage targets
3. Naming convention
4. Fixtures and golden files
5. Scenario tables per feature area
6. Listening test protocol
7. Smoke checklist for staging
8. Regression policy and flake policy

---

## 1. Strategy and test pyramid

- **Unit** (pytest): pure logic: extraction rules, block normalization, hashing, profile validation, script parse and validate, lexicon, VTT timing math, cache keys, inject idempotence, consent rules.
- **Integration** (pytest -m integration): real ffmpeg, real Ollama with a small model, real Kokoro on CPU, Maya 2 server when `AUDIO_SMITH_IT_MAYA2_URL` is set (GPU runner).
- **Golden audio tests**: mock backend produces deterministic tones per character; mastering output compared by duration, loudness, and chunk boundary timestamps within tolerance (never byte equality for encoded audio).
- **Smoke**: `tests/smoke/smoke.sh` runs `doctor`, then `run` on `tests/fixtures/pages/letter-calm.html` with the mock LLM and mock TTS, asserts outputs exist and manifest validates.
- **E2E** (Playwright): player component (keyboard, captions, language toggle, no-JS fallback) and Studio flows.
- **Regression**: one test per fixed bug, never deleted.
- **Listening tests** (manual, per release): 3 fixture letters, kid-5 profile, cloned voice; rubric scored 1 to 5 on warmth, clarity, pacing, pronunciation, consistency, script faithfulness. Release blocked if any average under 4.

### Test pyramid

```
                      /\
                     /  \          Listening (manual, per release)
                    /    \         4 letters (3 en + 1 hi), human raters
                   /------\
                  /        \       E2E (Playwright)
                 /          \      player + Studio flows, axe-core
                /------------\
               /              \    Smoke (tests/smoke/smoke.sh)
              /                \   doctor + mock run, ~1 minute
             /------------------\
            /                    \ Integration (pytest -m integration)
           /                      \ ffmpeg, Ollama tiny model, Kokoro CPU,
          /                        \ Maya 2 on GPU runner
         /--------------------------\
        /                            \ Golden audio (mock tones, tolerances)
       /                              \
      /--------------------------------\
     /                                  \ Unit (pytest, vitest): the majority
    /                                    \ pure logic, no I/O, no network
   /--------------------------------------\

   Many, fast, cheap  <------------------>  Few, slow, expensive
```

### Test types and locations

| Type | When | Runner | Location |
|---|---|---|---|
| Unit | Pure logic, no I/O, no network | pytest / vitest | `tests/unit/`, `player/tests/` |
| Integration | Real ffmpeg, Ollama, Kokoro, Maya 2 (GPU) | pytest -m integration | `tests/integration/` |
| Smoke | Minimal end-to-end sanity | `tests/smoke/smoke.sh` | `tests/smoke/` |
| E2E | Player and Studio flows | Playwright | `tests/e2e/` |
| Regression | Every bug fixed gets one | pytest / vitest | `tests/regression/` |
| Listening | Human evaluation per release | Section 6 protocol | `docs/LISTENING_TESTS.md` |

### Pytest markers

| Marker | Meaning |
|---|---|
| `integration` | Needs real ffmpeg, Ollama, Kokoro, or a server |
| `gpu` | Needs an NVIDIA GPU (Maya 2); runs only on the self-hosted `gpu` runner |
| `slow` | Over 10 seconds; excluded from the default local run |
| `flaky_quarantine` | Quarantined flaky test (see section 8) |

### CI mapping

| CI job | Test types it runs |
|---|---|
| lint-and-typecheck | ruff, mypy --strict, eslint, tsc, em dash check |
| unit-tests | Unit and regression, 3 OS x Python 3.12/3.13; vitest for player, Studio, pi |
| coverage | Threshold script (`scripts/check-coverage.py`), Codecov upload |
| integration-tests | Integration with ffmpeg, Ollama `qwen3:0.6b`, Kokoro CPU |
| e2e-tests | Playwright plus axe-core |
| check-versions | `scripts/check-versions.sh` on PRs to staging and main |
| smoke | `tests/smoke/smoke.sh` with mocks |
| gpu-integration | Self-hosted `[gpu]` runner, Maya 2 (PRs to staging/main and dispatch) |
| harness-smoke-tests | Staging and release only |

### Status legend (used in section 5)

| Status | Meaning |
|---|---|
| ✅ Automated | Test exists and runs in CI |
| ⚠️ Deferred | Specified, not yet implemented; implemented in the sprint named by the linked task |
| ❌ Skipped | Cannot run in the default CI or by the executing agent; the reason and manual step are in the row |

All rows start as ⚠️ Deferred or ❌ Skipped. A row moves to ✅ Automated in the same PR that adds the test.

---

## 2. Coverage targets

Mirrors `.coverage-thresholds.toml` exactly. `scripts/check-coverage.py` fails CI when any module is under its threshold.

```toml
# .coverage-thresholds.toml
[python]
"audio_smith/extract.py" = 90
"audio_smith/blocks.py" = 95
"audio_smith/script" = 90
"audio_smith/profiles" = 90
"audio_smith/voices" = 90
"audio_smith/tts" = 85
"audio_smith/master" = 85
"audio_smith/publish" = 90
"audio_smith/cache" = 90
"audio_smith/qa" = 80
"audio_smith/server" = 80
"audio_smith/mcp_server" = 80
"audio_smith/cli.py" = 75
overall = 85

[typescript]
"player/src" = 85
"web/studio/src" = 75
"integrations/pi/src" = 70
```

Notes:

- GPU-only code paths (Maya 2 live calls) are covered by respx-mocked unit tests for the adapter so the `tts` threshold is reachable without a GPU.
- Coverage is measured on the unit plus integration suites on ubuntu; Windows and macOS runs do not gate coverage.

---

## 3. Naming convention

```
Unit:        test_{module}_{function}_{scenario}_{expected_outcome}
Integration: it_{component}_{operation}_{scenario}
Smoke:       smoke_{feature}_{minimal_assertion}
E2E:         e2e_{user_story_id}_{scenario}
Regression:  regression_{gh_issue_number}_{what_was_broken}
```

---

## 4. Fixtures and golden files

### Fixture layout

```
tests/fixtures/
  pages/letter-calm.html          saved copy of the reference letter (author's own content)
  pages/index-messages.html       saved copy of the letters index page
  pages/data-narrate.html         page using data-narrate attributes, skip and parent tracks
  pages/hostile.html              scripts, iframes, giant inline base64, 3 MB of text
  scripts/valid.script.md
  scripts/invalid-markers.script.md
  profiles/custom-commute.yaml
  voices/clean.wav                synthetic tone clip with consent record
  voices/clipped.wav | noisy.wav | too-short.wav
  llm/                            recorded LLM responses for the fake provider
```

### Golden files

```
tests/fixtures/golden/
  letter-calm.blocks.json         expected block list from extracting letter-calm.html
  letter-calm.en.script.md        expected kid-5 Script Markdown from the FakeProvider replay
```

| Golden file | Produced by | Compared by | Update rule |
|---|---|---|---|
| `letter-calm.blocks.json` | `extract(pages/letter-calm.html)` | syrupy snapshot, exact JSON equality | Update only with `scripts/validate-fixtures.sh --update` in the same PR as the extractor change |
| `letter-calm.en.script.md` | `write_script` with FakeProvider replaying `tests/fixtures/llm/` for profile kid-5 | exact text equality after newline normalization | Re-record with `make record-llm` (requires Ollama) when the writer prompt template version changes; review the diff |

### Golden audio tolerances (Appendix J)

| Quantity | Tolerance |
|---|---|
| Duration of assembled audio | plus or minus 5 ms per join |
| Integrated loudness | plus or minus 1 LU |
| Chunk boundary timestamps | plus or minus 10 ms |
| Encoded audio (MP3, Opus) | Never byte equality; compare duration, loudness, boundaries only |

### Fixture maintenance

- `scripts/validate-fixtures.sh` re-runs extraction on fixture pages and fails if block snapshots drift without a snapshot update in the same PR.
- Recorded LLM fixtures are keyed by prompt hash; when a prompt template version changes, re-record with `make record-llm` (requires Ollama) and review diffs.
- Fixture voice clips are synthetic tones or the maintainer's own voice with a consent record; never third-party voices.
- `tests/fixtures/voices/*.wav` is tracked in Git LFS (see `.gitattributes`) and is exempt from the `voices/*/reference.wav` ignore rule.

---

## 5. Scenario tables per feature area

Conventions: ids follow section 3. Types are Unit, Integration, Smoke, E2E, Regression (none exist yet). "FR" references are in the section heading. A row marked ❌ Skipped names the reason and the manual step.

### 5.1 Fetch (FR-001)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_fetch_private_ip_blocked` | SSRF guard rejects private, loopback, link-local, metadata addresses | Unit | ⚠️ Deferred |
| `test_fetch_redirect_to_private_blocked` | Redirect from public host to private IP is rejected | Unit | ⚠️ Deferred |
| `test_fetch_allow_private_flag_permits_loopback` | `--allow-private` lets loopback through | Unit | ⚠️ Deferred |
| `test_fetch_dns_rebinding_connects_to_resolved_ip` | DNS resolved once, connection pinned to that IP | Unit | ⚠️ Deferred |
| `test_fetch_non_http_scheme_rejected` | `ftp:`, `gopher:`, `javascript:` rejected with clear error | Unit | ⚠️ Deferred |
| `test_fetch_timeout_default_20s_honored` | Default timeout of 20 s applies; configured value overrides | Unit | ⚠️ Deferred |
| `test_fetch_max_size_5mb_aborts_stream` | Streamed body aborted at the 5 MB limit | Unit | ⚠️ Deferred |
| `test_fetch_redirect_limit_5_enforced` | Sixth redirect raises | Unit | ⚠️ Deferred |
| `test_fetch_user_agent_descriptive_sent` | Request carries `mr-audio-smith/{version}` User-Agent | Unit | ⚠️ Deferred |
| `test_fetch_local_file_no_network` | Local .html and .md read with network disabled | Unit | ⚠️ Deferred |
| `test_fetch_charset_from_content_type_decoded` | Non-UTF-8 charset decoded correctly | Unit | ⚠️ Deferred |
| `test_fetch_hostile_page_within_limits` | `hostile.html` (3 MB text, base64) handled without exceeding memory or time budget | Unit | ⚠️ Deferred |

### 5.2 Extract and blocks (FR-002, FR-003, FR-026)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_extract_blocks_data_narrate_present_uses_only_marked_element` | Extraction honors [data-narrate] | Unit | ⚠️ Deferred |
| `test_extract_blocks_article_used_when_no_data_narrate` | Fallback 2: `<article>` | Unit | ⚠️ Deferred |
| `test_extract_blocks_trafilatura_used_when_no_article` | Fallback 3: trafilatura main content | Unit | ⚠️ Deferred |
| `test_extract_blocks_readability_fallback_last_resort` | Fallback 4: readability when trafilatura returns empty | Unit | ⚠️ Deferred |
| `test_extract_blocks_nav_header_footer_excluded` | Boilerplate elements excluded | Unit | ⚠️ Deferred |
| `test_extract_blocks_scripts_styles_forms_excluded` | script, style, noscript, svg, button, form removed | Unit | ⚠️ Deferred |
| `test_extract_blocks_emoji_stripped` | Emoji never reach blocks | Unit | ⚠️ Deferred |
| `test_extract_blocks_regional_indicator_flags_stripped` | Flag emoji (regional indicator pairs) stripped | Unit | ⚠️ Deferred |
| `test_extract_blocks_skip_attribute_excluded` | data-narrate="skip" excluded | Unit | ⚠️ Deferred |
| `test_extract_blocks_parent_attribute_routed` | Parent track routing | Unit | ⚠️ Deferred |
| `test_extract_blocks_types_title_heading_paragraph_list_quote_signature` | All six block types emitted in document order | Unit | ⚠️ Deferred |
| `test_extract_blocks_signature_role_attribute_detected` | `data-narrate-role="signature"` becomes signature block | Unit | ⚠️ Deferred |
| `test_extract_blocks_signoff_pattern_detected` | Final short paragraph with sign-off pattern becomes signature | Unit | ⚠️ Deferred |
| `test_extract_blocks_list_items_capture_index_and_nested_heading` | list_item keeps index and parent heading | Unit | ⚠️ Deferred |
| `test_extract_blocks_grown_up_note_not_parent_without_attribute` | No magic-string matching in core | Unit | ⚠️ Deferred |
| `test_extract_blocks_parent_headings_profile_rule_opt_in` | `parent_headings` profile rule routes "A grown-up note" to parent | Unit | ⚠️ Deferred |
| `test_extract_letter_calm_matches_golden_blocks` | Snapshot of `letter-calm.html` equals `golden/letter-calm.blocks.json` | Unit | ⚠️ Deferred |
| `test_extract_hostile_html_no_crash_within_limits` | `hostile.html` yields blocks without hang | Unit | ⚠️ Deferred |
| `test_extract_blocks_fuzz_hypothesis_never_raises` | Hypothesis-generated HTML never crashes the extractor | Unit | ⚠️ Deferred |
| `test_blocks_hash_whitespace_change_stable` | Hash ignores whitespace | Unit | ⚠️ Deferred |
| `test_blocks_hash_markup_only_change_stable` | Markup-only change (extra wrapper div) keeps hash | Unit | ⚠️ Deferred |
| `test_blocks_hash_text_change_differs` | Hash detects text edits | Unit | ⚠️ Deferred |
| `test_blocks_hash_profile_version_change_differs` | Profile version is part of the hash input | Unit | ⚠️ Deferred |
| `test_blocks_hash_backend_voice_language_change_differs` | Backend id, voice id, and language each alter the hash | Unit | ⚠️ Deferred |
| `test_blocks_normalize_smart_quotes_for_hash_only` | Smart quotes normalized for hashing, preserved in stored text | Unit | ⚠️ Deferred |
| `test_blocks_hash_whitespace_invariant_property` | Hypothesis property: whitespace invariance | Unit | ⚠️ Deferred |
| `test_parent_track_excluded_from_child_blocks` | Parent-marked blocks never appear in the child track (FR-026) | Unit | ⚠️ Deferred |

### 5.3 Profiles (FR-004)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_profiles_load_invalid_rate_rejected` | Schema errors are clear | Unit | ⚠️ Deferred |
| `test_profiles_load_error_names_field_path` | Error message contains the YAML field path | Unit | ⚠️ Deferred |
| `test_profiles_builtins_kid5_kid8_commute_brief_load` | All four built-in profiles validate | Unit | ⚠️ Deferred |
| `test_profiles_user_profile_overrides_builtin_same_id` | `./profiles` entry wins over the built-in | Unit | ⚠️ Deferred |
| `test_profiles_semantic_version_required` | Missing or non-semver version rejected | Unit | ⚠️ Deferred |
| `test_profiles_custom_commute_fixture_loads` | `profiles/custom-commute.yaml` loads | Unit | ⚠️ Deferred |
| `test_profiles_json_schema_matches_pydantic_model` | Exported `schemas/profile.schema.json` is current | Unit | ⚠️ Deferred |
| `test_cli_profile_list_show_validate_commands` | `profile list`, `show`, `validate` behave and set exit codes | Unit | ⚠️ Deferred |

### 5.4 LLM providers (FR-005 provider support)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_llm_ollama_chat_request_shape` | `/api/chat` body, model, options match (respx) | Unit | ⚠️ Deferred |
| `test_llm_anthropic_provider_passes_model_and_system` | Anthropic SDK called with configured model (stubbed) | Unit | ⚠️ Deferred |
| `test_llm_openai_compat_base_url_and_key` | base_url and key applied | Unit | ⚠️ Deferred |
| `test_llm_fake_provider_replays_by_prompt_hash` | FakeProvider returns the recorded response | Unit | ⚠️ Deferred |
| `test_llm_fake_provider_unknown_hash_raises_clear_error` | Missing recording names the hash and `make record-llm` | Unit | ⚠️ Deferred |
| `test_llm_provider_string_parsing_all_three_formats` | `ollama:qwen3:14b`, `anthropic:<id>`, `openai_compat:<url>#<model>` | Unit | ⚠️ Deferred |
| `test_llm_ollama_unreachable_preflight_hint` | Doctor hint when Ollama is down | Unit | ⚠️ Deferred |
| `test_llm_seed_and_temperature_zero_passed_where_supported` | Determinism parameters forwarded | Unit | ⚠️ Deferred |
| `it_ollama_script_kid5_within_length` | Real LLM script length | Integration | ⚠️ Deferred |

### 5.5 Script generation and validation (FR-005, FR-006)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_script_validate_unknown_marker_rejected` | Validator rejects invented tags | Unit | ⚠️ Deferred |
| `test_script_validate_empty_chunk_rejected` | Empty chunk reported with number | Unit | ⚠️ Deferred |
| `test_script_validate_chunk_over_max_chars_rejected` | Chunk over `max_chunk_chars` reported | Unit | ⚠️ Deferred |
| `test_script_validate_strips_stray_markdown_and_emoji` | Stray `**`, `#`, emoji removed | Unit | ⚠️ Deferred |
| `test_script_validate_reports_violations_with_chunk_numbers` | Every violation carries its chunk number | Unit | ⚠️ Deferred |
| `test_script_validate_verbatim_chunk_changed_rejected` | Verbatim enforced | Unit | ⚠️ Deferred |
| `test_script_validate_signature_altered_rejected` | Signature must be preserved exactly | Unit | ⚠️ Deferred |
| `test_script_validate_allowed_markers_only_pass` | `[pause N]` and allowed emphasis pass | Unit | ⚠️ Deferred |
| `test_script_parse_serialize_roundtrip_property` | Parse then serialize is identity (hypothesis) | Unit | ⚠️ Deferred |
| `test_script_parse_frontmatter_and_numbered_chunks` | Frontmatter and chunk numbering parsed | Unit | ⚠️ Deferred |
| `test_script_parse_invalid_markers_fixture_rejected` | `scripts/invalid-markers.script.md` fails | Unit | ⚠️ Deferred |
| `test_script_parse_valid_fixture_passes` | `scripts/valid.script.md` passes | Unit | ⚠️ Deferred |
| `test_script_writer_retry_with_violations_succeeds` | One corrective retry | Unit | ⚠️ Deferred |
| `test_script_writer_second_failure_raises` | Fails after the single retry | Unit | ⚠️ Deferred |
| `test_script_writer_target_length_within_20_percent` | Word count within target_minutes x 130 x rate, plus or minus 20 percent | Unit | ⚠️ Deferred |
| `test_script_writer_prompt_version_in_cache_key` | Template version changes the script cache key | Unit | ⚠️ Deferred |
| `test_script_writer_interactive_moments_count_requested` | Prompt carries `interactive_moments` count | Unit | ⚠️ Deferred |
| `test_script_writer_fake_provider_matches_golden_script` | `letter-calm` + kid-5 equals `golden/letter-calm.en.script.md` | Unit | ⚠️ Deferred |
| `test_script_writer_deterministic_temperature_zero_fixed_seed` | Same inputs and seed give the same script (fake and where supported) | Unit | ⚠️ Deferred |

### 5.6 Lexicon (FR-007)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_lexicon_apply_whole_word_only` | "Aadi" replaced, "Aadish" not | Unit | ⚠️ Deferred |
| `test_lexicon_apply_case_sensitive` | "aadi" untouched when entry is "Aadi" | Unit | ⚠️ Deferred |
| `test_lexicon_stored_script_unchanged_after_apply` | Replacement happens at synthesis only; stored script bytes unchanged | Unit | ⚠️ Deferred |
| `test_lexicon_project_overrides_profile_entry` | `lexicon.yaml` wins on conflict | Unit | ⚠️ Deferred |
| `test_lexicon_merge_profile_and_project` | Union of both sources | Unit | ⚠️ Deferred |

### 5.7 Translation (FR-008)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_translate_preserves_chunk_count_and_pauses` | Translation alignment | Unit | ⚠️ Deferred |
| `test_translate_output_named_slug_lang_script_md` | `{slug}.hi.script.md` written | Unit | ⚠️ Deferred |
| `test_translate_misaligned_output_retried_then_fails` | Chunk count mismatch triggers corrective retry | Unit | ⚠️ Deferred |
| `test_translate_backend_lacking_language_fails_preflight` | Clear message for unsupported language | Unit | ⚠️ Deferred |
| `test_translate_manifest_lists_language_tracks` | Manifest `tracks` has one entry per language | Unit | ⚠️ Deferred |
| `it_maya2_translate_hindi_track_rendered` | Hindi track rendered with cross-lingual cloned voice | Integration | ❌ Skipped: requires NVIDIA GPU runner. Manual step: on a GPU machine run `mr-audio-smith run <letter> --langs en,hi --voice <clone>` and confirm `{slug}.hi.mp3` plays in the cloned voice |

### 5.8 TTS backends (FR-009, FR-010)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_tts_registry_lists_five_backends` | maya2, kokoro, openai, openai_compat, mock registered | Unit | ⚠️ Deferred |
| `test_tts_mock_deterministic_across_runs` | Same text, voice, seed give identical samples | Unit | ⚠️ Deferred |
| `test_tts_mock_duration_proportional_to_text_length` | Duration scales with characters | Unit | ⚠️ Deferred |
| `test_tts_mock_pitch_derived_from_voice_id` | Different voices give different pitch | Unit | ⚠️ Deferred |
| `test_tts_capabilities_flags_per_backend` | Languages, clone, sample rate, license, commercial_ok correct | Unit | ⚠️ Deferred |
| `test_tts_openai_compat_success_returns_pcm` | 200 WAV decoded to PcmAudio (respx) | Unit | ⚠️ Deferred |
| `test_tts_openai_compat_4xx_raises_no_retry` | 4xx surfaced immediately | Unit | ⚠️ Deferred |
| `test_tts_openai_compat_5xx_retries_with_backoff` | 5xx retried | Unit | ⚠️ Deferred |
| `test_tts_openai_compat_timeout_raises` | Timeout becomes backend error | Unit | ⚠️ Deferred |
| `test_tts_maya2_request_body_matches_server_contract` | Body has model, input, voice, language, response_format, seed, `speed` fixed at 1.0 | Unit | ⚠️ Deferred |
| `test_tts_maya2_default_url_port_8080` | Default `AUDIO_SMITH_MAYA2_URL` is `http://127.0.0.1:8080/v1` | Unit | ⚠️ Deferred |
| `test_tts_maya2_rate_applied_post_synthesis_atempo` | Speaking rate applied by ffmpeg atempo, not sent to the server (ADR-016) | Unit | ⚠️ Deferred |
| `test_tts_maya2_pause_markers_split_into_separate_requests` | No inline tags; pauses become silences | Unit | ⚠️ Deferred |
| `test_tts_maya2_emphasis_markers_stripped` | `*emphasis*` removed before the request | Unit | ⚠️ Deferred |
| `test_tts_maya2_registers_clone_via_voices_endpoint_idempotent` | POST /v1/voices with `as-{voice_id}-{clip_hash[:8]}`; 409 treated as ok | Unit | ⚠️ Deferred |
| `test_tts_maya2_503_not_ready_retries_with_retry_after` | 503 honored before failing | Unit | ⚠️ Deferred |
| `test_tts_maya2_supports_all_12_languages` | Capabilities list as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te | Unit | ⚠️ Deferred |
| `test_tts_maya2_inproc_mode_requires_extra` | `--maya2-mode inproc` errors with hint when `maya2` extra missing | Unit | ⚠️ Deferred |
| `test_tts_license_guard_noncommercial_requires_flag` | `commercial_ok: false` without `--accept-noncommercial` refuses | Unit | ⚠️ Deferred |
| `test_tts_license_guard_flag_recorded_in_manifest_warnings` | Accepted noncommercial use is logged in the manifest | Unit | ⚠️ Deferred |
| `it_maya2_synth_clone_returns_24khz_mono` | Maya 2 integration | Integration | ❌ Skipped: no GPU runner in default CI (marker `gpu`, needs `AUDIO_SMITH_IT_MAYA2_URL`). Manual step: start `python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080`, then `AUDIO_SMITH_IT_MAYA2_URL=http://127.0.0.1:8080/v1 pytest -m "integration and gpu"` |
| `it_maya2_synth_builtin_voice_returns_audio` | Built-in voice (for example Ahana) renders | Integration | ❌ Skipped: no GPU runner. Manual step: same server as above, run the `gpu` marker subset |
| `it_maya2_health_reports_loaded_model` | Doctor reports reachability and loaded model | Integration | ❌ Skipped: no GPU runner. Manual step: run `mr-audio-smith doctor` against a live Maya 2 server and confirm the backend row is OK |
| `it_kokoro_synth_cpu_returns_audio` | Kokoro integration | Integration | ⚠️ Deferred |
| `it_kokoro_weights_checksum_verified` | First-use download verified against the pinned checksum | Integration | ⚠️ Deferred |
| `it_openai_compat_local_stub_server_roundtrip` | Real HTTP against a local stub speech server | Integration | ⚠️ Deferred |

### 5.9 Voices, consent, and clip check (FR-011)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_consent_clone_unregistered_voice_raises` | Consent enforced in core | Unit | ⚠️ Deferred |
| `test_consent_registration_requires_all_fields` | Name, relationship, date, statement all required | Unit | ⚠️ Deferred |
| `test_consent_relationship_only_self_or_written_permission` | Other relationship values rejected | Unit | ⚠️ Deferred |
| `test_consent_enforced_from_python_api_and_cli_and_server` | `voices.registry.resolve()` guards every front door | Unit | ⚠️ Deferred |
| `test_consent_backend_refuses_clone_without_registry_entry` | Backend-level refusal | Unit | ⚠️ Deferred |
| `test_clipcheck_too_short_rejected` | Clip quality gate | Unit | ⚠️ Deferred |
| `test_clipcheck_too_long_over_30s_rejected` | Duration above 30 s rejected | Unit | ⚠️ Deferred |
| `test_clipcheck_sample_rate_below_16khz_rejected` | Low sample rate rejected | Unit | ⚠️ Deferred |
| `test_clipcheck_clipping_over_0_1_percent_rejected` | `voices/clipped.wav` fails | Unit | ⚠️ Deferred |
| `test_clipcheck_snr_below_25db_rejected` | `voices/noisy.wav` fails | Unit | ⚠️ Deferred |
| `test_clipcheck_stereo_downmixed_to_mono` | Stereo accepted and downmixed | Unit | ⚠️ Deferred |
| `test_clipcheck_clean_fixture_passes` | `voices/clean.wav` passes | Unit | ⚠️ Deferred |
| `test_voices_add_stores_24k_mono_reference_copy` | `reference.24k.wav` written; clip hash computed | Unit | ⚠️ Deferred |
| `test_voices_list_check_remove_commands` | Registry CRUD works | Unit | ⚠️ Deferred |
| `test_voices_gitignore_blocks_reference_wav` | Real clips under `voices/*/reference.wav` are ignored; fixtures are not | Unit | ⚠️ Deferred |
| `test_cli_voice_add_interactive_consent_prompt` | Interactive consent flow completes | Unit | ⚠️ Deferred |

### 5.10 Chunk planner and synthesis runner (FR-009, FR-012)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_planner_split_on_pause_markers_into_segments` | `[pause N]` splits units | Unit | ⚠️ Deferred |
| `test_planner_max_chars_splits_on_sentence_boundary` | Never splits mid-sentence | Unit | ⚠️ Deferred |
| `test_planner_lexicon_applied_before_keying` | Lexicon affects synthesis text and key | Unit | ⚠️ Deferred |
| `test_planner_chunk_key_stable_across_runs` | Keys deterministic | Unit | ⚠️ Deferred |
| `test_planner_chunk_key_changes_with_voice_seed_rate` | Voice, seed, or rate alters the key | Unit | ⚠️ Deferred |
| `test_runner_cache_hit_skips_synthesis` | Cached chunk is not re-synthesized | Unit | ⚠️ Deferred |
| `test_runner_failed_chunk_retried_twice_with_backoff` | Retries 2 times with exponential backoff and jitter | Unit | ⚠️ Deferred |
| `test_runner_third_failure_marks_chunk_failed` | Failure surfaced after retries | Unit | ⚠️ Deferred |
| `test_runner_resume_after_interrupt_renders_only_remainder` | Partial progress survives (FR-012) | Unit | ⚠️ Deferred |
| `test_runner_cache_write_atomic_temp_rename` | No partial WAV is ever visible | Unit | ⚠️ Deferred |
| `test_runner_chunks_subset_renders_only_selected` | `--chunks 3,4` renders those only | Unit | ⚠️ Deferred |
| `test_runner_concurrency_bounded_semaphore_default_2` | At most 2 in-flight requests | Unit | ⚠️ Deferred |
| `it_runner_kill_midrun_then_resume_renders_remainder` | Real process killed with SIGINT, re-run completes | Integration | ⚠️ Deferred |

### 5.11 Voice consistency QA (FR-013)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_qa_similarity_below_threshold_rerenders` | QA retake loop | Unit | ⚠️ Deferred |
| `test_qa_rerender_uses_new_seed_each_take` | Seeds differ across takes | Unit | ⚠️ Deferred |
| `test_qa_takes_per_chunk_limit_respected` | Stops after `takes_per_chunk` | Unit | ⚠️ Deferred |
| `test_qa_best_take_kept_by_score` | Highest similarity retained | Unit | ⚠️ Deferred |
| `test_qa_builtin_voice_compared_to_chunk_1` | Reference is chunk 1 when no clip | Unit | ⚠️ Deferred |
| `test_qa_report_lists_scores_per_chunk` | Scores in the report and manifest | Unit | ⚠️ Deferred |
| `test_qa_default_threshold_0_75` | Default threshold value | Unit | ⚠️ Deferred |
| `test_qa_extra_missing_skips_with_manifest_warning` | resemblyzer absent: warning, no crash (ADR-015) | Unit | ⚠️ Deferred |
| `it_qa_resemblyzer_embeds_fixture_clip` | Real embedding of `voices/clean.wav` returns a vector | Integration | ⚠️ Deferred |

### 5.12 Assemble and master (FR-014)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_assemble_total_duration_equals_parts_plus_pauses` | Sum within 5 ms per join (golden, mock audio) | Unit | ⚠️ Deferred |
| `test_assemble_crossfade_10ms_at_joins` | Short crossfade at joins | Unit | ⚠️ Deferred |
| `test_assemble_resamples_to_44100` | Output rate 44.1 kHz | Unit | ⚠️ Deferred |
| `test_assemble_chunk_timestamps_within_10ms` | Start and end boundaries within tolerance | Unit | ⚠️ Deferred |
| `test_assemble_heading_and_chunk_pauses_from_profile` | `pause_after_heading_ms`, `pause_between_chunks_ms` applied | Unit | ⚠️ Deferred |
| `test_master_ffmpeg_args_are_array_no_shell` | Wrapper never builds shell strings | Unit | ⚠️ Deferred |
| `test_master_loudness_within_target` | -16 LUFS plus or minus 1 | Integration | ⚠️ Deferred |
| `it_master_true_peak_at_or_below_minus_1_5_dbtp` | True peak limit via ebur128 | Integration | ⚠️ Deferred |
| `it_master_mp3_128k_mono_44100_default` | Default encode parameters verified with ffprobe | Integration | ⚠️ Deferred |
| `it_master_opus_optional_output_created` | `--opus` yields a valid Opus file | Integration | ⚠️ Deferred |
| `it_master_intro_outro_stings_included` | Stings add expected duration | Integration | ⚠️ Deferred |
| `it_master_music_bed_ducks_under_voice` | Bed at -24 dB under voice with sidechain | Integration | ⚠️ Deferred |
| `it_master_two_pass_loudnorm_runs` | Measure pass then apply pass | Integration | ⚠️ Deferred |
| `test_master_stings_are_procedural_and_documented` | `assets/stings/` entries listed as original in THIRD_PARTY_LICENSES | Unit | ⚠️ Deferred |
| `test_perf_reference_letter_meets_nfr_003` | Reference letter time meets NFR-003 (logged to `docs/PERFORMANCE.md`) | Integration | ❌ Skipped: needs GPU runner for the Maya 2 numbers. Manual step: run the reference letter on the GPU machine, record wall time in `docs/PERFORMANCE.md` |

### 5.13 ID3 tags (FR-014)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_tags_id3_title_artist_album_date_written` | TIT2, TPE1, TALB, TDRC readable by mutagen | Unit | ⚠️ Deferred |
| `test_tags_author_from_page_meta_else_config` | Artist fallback order | Unit | ⚠️ Deferred |
| `test_tags_cover_art_same_origin_under_1mb_embedded` | APIC embedded | Unit | ⚠️ Deferred |
| `test_tags_cover_art_cross_origin_skipped` | Cross-origin og:image ignored | Unit | ⚠️ Deferred |
| `test_tags_cover_art_over_1mb_skipped` | Oversized image ignored | Unit | ⚠️ Deferred |

### 5.14 WebVTT captions (FR-015)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_vtt_cues_align_within_150ms` | Caption alignment | Unit | ⚠️ Deferred |
| `test_vtt_one_cue_per_sentence` | Sentence-level cues | Unit | ⚠️ Deferred |
| `test_vtt_text_from_narrated_script_not_page` | Cue text equals the script text | Unit | ⚠️ Deferred |
| `test_vtt_distribution_by_character_length_proportion` | Within-chunk timing split proportionally | Unit | ⚠️ Deferred |
| `test_vtt_format_valid_header_and_timestamps` | `WEBVTT` header, monotonic `hh:mm:ss.mmm` | Unit | ⚠️ Deferred |
| `test_vtt_pause_markers_not_rendered_as_text` | Markers absent from cue text | Unit | ⚠️ Deferred |

### 5.15 Manifest (FR-016)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_manifest_validates_against_published_schema` | Output passes `schemas/manifest.schema.json` | Unit | ⚠️ Deferred |
| `test_manifest_contains_versions_hashes_backend_voice_languages` | All required fields present | Unit | ⚠️ Deferred |
| `test_manifest_records_durations_qa_scores_file_names` | Durations, QA scores, files listed | Unit | ⚠️ Deferred |
| `test_manifest_warnings_include_qa_skipped_and_noncommercial` | Warnings array populated | Unit | ⚠️ Deferred |
| `test_manifest_approved_flag_written_by_studio` | `approved: true` persisted | Unit | ⚠️ Deferred |
| `test_schemas_blocks_profile_manifest_published_and_current` | The three schemas in `schemas/` match models | Unit | ⚠️ Deferred |

### 5.16 Cache (FR-020)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_cache_unchanged_page_skips_render` | Incremental build | Unit | ⚠️ Deferred |
| `test_cache_second_script_run_under_2s` | Second `script` run on unchanged page is a cache hit under 2 s | Integration | ⚠️ Deferred |
| `test_cache_key_format_versioned` | Key begins with a format version | Unit | ⚠️ Deferred |
| `test_cache_version_bump_invalidates_old_entries` | Old-format keys are never read | Unit | ⚠️ Deferred |
| `test_cache_prune_older_than_30d_removes_old_only` | `cache prune --older-than 30d` | Unit | ⚠️ Deferred |
| `test_cache_content_addressed_blocks_scripts_chunks_outputs` | All four kinds stored by hash | Unit | ⚠️ Deferred |
| `test_cache_force_flag_bypasses` | `--force` re-runs the stage | Unit | ⚠️ Deferred |

### 5.17 CLI, doctor, and config (FR-021, S0-T09, S0-T10)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_cli_version_prints_pyproject_version` | `--version` output | Unit | ⚠️ Deferred |
| `test_cli_base_install_does_not_import_torch` | Base install has no torch dependency | Unit | ⚠️ Deferred |
| `test_cli_script_command_writes_blocks_and_script_files` | `{slug}.blocks.json`, `{slug}.en.script.md` | Unit | ⚠️ Deferred |
| `test_cli_slug_from_url_path_stem_sanitized` | Slug rules | Unit | ⚠️ Deferred |
| `test_cli_run_dry_run_prints_plan_and_cache_status` | `--dry-run` writes nothing | Unit | ⚠️ Deferred |
| `test_cli_run_approve_opens_editor_then_continues` | `--approve` with stubbed `$EDITOR` | Unit | ⚠️ Deferred |
| `test_cli_run_output_layout_out_slug` | `out/{slug}/` artifact set | Unit | ⚠️ Deferred |
| `test_cli_run_parent_track_rendered_when_blocks_exist` | `{slug}.parent.mp3` using adult-brief | Unit | ⚠️ Deferred |
| `test_api_narrate_returns_manifest` | `audio_smith.narrate(...)` returns Manifest | Unit | ⚠️ Deferred |
| `test_api_stage_functions_exposed` | extract, write_script, render_script, master, publish importable | Unit | ⚠️ Deferred |
| `test_doctor_all_required_pass_exit_0` | Exit 0 when green | Unit | ⚠️ Deferred |
| `test_doctor_required_failure_exit_3` | Exit 3 on a required failure | Unit | ⚠️ Deferred |
| `test_doctor_each_failure_has_fix_hint` | Hints present for every check | Unit | ⚠️ Deferred |
| `test_doctor_json_output_schema` | `--json` output is valid | Unit | ⚠️ Deferred |
| `test_doctor_ffmpeg_older_than_6_fails` | ffmpeg below 6.0 flagged | Unit | ⚠️ Deferred |
| `test_doctor_python_313_hints_kokoro_use_312` | ADR-017 hint | Unit | ⚠️ Deferred |
| `test_doctor_disk_space_and_cache_writable_checks` | Both checks registered | Unit | ⚠️ Deferred |
| `test_doctor_gpu_visibility_reported_when_torch_installed` | CUDA check conditional on torch | Unit | ⚠️ Deferred |
| `test_doctor_backend_and_llm_and_voices_rows_present` | Each backend, LLM provider, voices checked | Unit | ⚠️ Deferred |
| `test_config_precedence_flags_over_env_over_file_over_defaults` | Full precedence chain | Unit | ⚠️ Deferred |
| `test_config_audio_smith_toml_discovered_upward_from_cwd` | Upward discovery | Unit | ⚠️ Deferred |
| `test_config_unknown_key_warns_not_crashes` | Unknown keys warn | Unit | ⚠️ Deferred |
| `test_config_env_prefix_audio_smith` | `AUDIO_SMITH_` prefix | Unit | ⚠️ Deferred |
| `smoke_run_mock_outputs_exist` | End to end with mocks | Smoke | ⚠️ Deferred |
| `smoke_doctor_exit_0_on_clean_machine` | `doctor` exits 0 first | Smoke | ⚠️ Deferred |
| `smoke_run_mock_manifest_validates` | Manifest passes the schema in the smoke run | Smoke | ⚠️ Deferred |
| `smoke_version_prints_semver` | `--version` smoke | Smoke | ⚠️ Deferred |

### 5.18 Player (FR-017, NFR-007, NFR-011)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `e2e_US006_player_keyboard_play_pause` | Player keyboard (Space and K) | E2E | ⚠️ Deferred |
| `e2e_US006_player_keyboard_arrows_seek_5s` | Left and right seek 5 s | E2E | ⚠️ Deferred |
| `e2e_US012_player_captions_toggle` | Captions (C key and button) | E2E | ⚠️ Deferred |
| `e2e_US006_player_language_toggle_switches_track` | Language toggle (L key) when more than one track | E2E | ⚠️ Deferred |
| `e2e_US006_player_no_js_fallback_plays` | No-JS fallback | E2E | ⚠️ Deferred |
| `e2e_US006_player_axe_core_zero_violations` | Accessibility scan has zero violations | E2E | ⚠️ Deferred |
| `e2e_US006_player_kid_size_variant_renders` | `size="kid"` larger targets | E2E | ⚠️ Deferred |
| `e2e_US006_player_theme_auto_light_dark` | Theme attribute and `prefers-color-scheme` | E2E | ⚠️ Deferred |
| `e2e_US006_player_remembers_position_per_src` | Resume position from localStorage | E2E | ⚠️ Deferred |
| `e2e_US006_player_localstorage_blocked_still_works` | try/catch around storage | E2E | ⚠️ Deferred |
| `e2e_US006_player_media_session_metadata_set` | Media Session API title and artwork | E2E | ⚠️ Deferred |
| `test_player_attributes_parse_tracks_json` | `tracks` JSON parsed; invalid JSON handled | Unit | ⚠️ Deferred |
| `test_player_captions_cue_active_class_follows_time` | Active cue tracking (vitest) | Unit | ⚠️ Deferred |
| `test_player_no_external_network_requests` | Player makes no third-party requests | Unit | ⚠️ Deferred |
| `e2e_US006_player_browser_matrix_chrome_firefox_safari` | Playback in Chromium, Firefox, WebKit | E2E | ❌ Skipped: WebKit and real Safari audio behavior needs a human. Manual step: open the example page in current Safari (macOS and iOS), Firefox, and Chrome; verify play, seek, captions, and language toggle |
| `e2e_US006_player_screen_reader_announcements` | Screen reader labels and live-region announcements | E2E | ❌ Skipped: human required. Manual step: with VoiceOver (macOS) and NVDA (Windows), tab to the player and confirm labels, state changes, and caption toggle are announced |

### 5.19 Embed and inject (FR-017, FR-018)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_embed_snippet_wraps_audio_fallback_inside_component` | Plain `<audio>` inside `<audio-smith-player>` | Unit | ⚠️ Deferred |
| `test_embed_snippet_includes_captions_track` | `<track kind="captions">` present | Unit | ⚠️ Deferred |
| `test_embed_snippet_language_toggle_only_when_multiple_languages` | Toggle conditional | Unit | ⚠️ Deferred |
| `test_embed_snippet_valid_html` | Parses cleanly | Unit | ⚠️ Deferred |
| `test_embed_script_ref_self_hosted_default_path` | `/media/audio/audio-smith-player.js` and file copied | Unit | ⚠️ Deferred |
| `test_embed_script_ref_jsdelivr_pinned_exact_version` | jsDelivr URL pins the exact version | Unit | ⚠️ Deferred |
| `test_inject_idempotent_second_run_no_diff` | Inject idempotence | Unit | ⚠️ Deferred |
| `test_inject_outside_markers_untouched` | Inject safety (byte-identical outside markers) | Unit | ⚠️ Deferred |
| `test_inject_creates_markers_after_selector_when_absent` | Default selector `h1` | Unit | ⚠️ Deferred |
| `test_inject_custom_selector_flag` | `--selector` honored | Unit | ⚠️ Deferred |
| `test_inject_dry_run_prints_unified_diff_writes_nothing` | Dry run | Unit | ⚠️ Deferred |
| `test_inject_replaces_existing_marker_content` | Stale snippet replaced | Unit | ⚠️ Deferred |
| `test_inject_preserves_original_formatting_no_dom_reserialize` | Splice on offsets | Unit | ⚠️ Deferred |
| `test_inject_reference_letter_fixture_idempotent` | Sprint 4 gate on `letter-calm.html` | Unit | ⚠️ Deferred |

### 5.20 Site batch mode (FR-019)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_site_same_origin_links_only` | Cross-origin links dropped | Unit | ⚠️ Deferred |
| `test_site_match_glob_filters_links` | `--match` applied | Unit | ⚠️ Deferred |
| `test_site_max_pages_limit_respected` | Stops at the limit | Unit | ⚠️ Deferred |
| `test_site_unchanged_page_skipped_by_hash` | Skips on identical hash | Unit | ⚠️ Deferred |
| `test_site_fixture_index_second_run_renders_zero` | 3-page fixture, second run renders 0 | Unit | ⚠️ Deferred |
| `test_site_summary_table_columns_page_status_duration` | Table shape and statuses (cached, rendered, failed) | Unit | ⚠️ Deferred |
| `test_site_one_page_failure_does_not_abort_batch` | Failure recorded, run continues | Unit | ⚠️ Deferred |
| `test_site_inject_root_maps_urls_to_local_files` | `--inject-root` mapping | Unit | ⚠️ Deferred |
| `test_examples_letters_to_a_child_runs_with_mock` | Example project runs end to end with mocks in CI | Smoke | ⚠️ Deferred |

### 5.21 GitHub Action (FR-025)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_action_yml_inputs_and_composite_steps_valid` | `action/action.yml` schema valid (actionlint) | Unit | ⚠️ Deferred |
| `test_action_only_files_matching_glob_processed` | Glob filter on changed files | Unit | ⚠️ Deferred |
| `test_action_noop_when_hashes_unchanged` | No commit when nothing changed | Unit | ⚠️ Deferred |
| `test_action_commit_message_format_skip_ci` | `chore(audio): narrate {n} pages [skip ci]` | Unit | ⚠️ Deferred |
| `test_action_remote_server_url_mode_uses_jobs_api` | `server-url` and `server-token` path | Unit | ⚠️ Deferred |
| `test_action_no_voice_clips_in_site_repo` | Clips never committed | Unit | ⚠️ Deferred |
| `it_action_throwaway_repo_run_green` | Action green in a test repo (via `act` or test repo) | Integration | ❌ Skipped: needs a GitHub test repo or a self-hosted GPU runner. Manual step: push a change to the throwaway repo and confirm the workflow commits outputs, then re-push and confirm a no-op |

### 5.22 Studio (FR-022)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `e2e_US017_studio_compare_takes_keep_best` | Studio takes | E2E | ⚠️ Deferred |
| `e2e_US017_studio_edit_validate_save_chunk` | Edit, live validation errors, save marks stale | E2E | ⚠️ Deferred |
| `e2e_US017_studio_marker_autocomplete_pause` | `[pause N]` autocomplete | E2E | ⚠️ Deferred |
| `e2e_US017_studio_rerender_only_edited_chunk` | Only stale chunks re-render | E2E | ⚠️ Deferred |
| `e2e_US017_studio_approve_persists_in_manifest` | Approve writes `approved: true` | E2E | ⚠️ Deferred |
| `e2e_US017_studio_inject_diff_preview_before_write` | Diff shown before the file changes | E2E | ⚠️ Deferred |
| `e2e_US017_studio_zero_external_requests` | Request interception shows no external hosts | E2E | ⚠️ Deferred |
| `test_studio_binds_127_0_0_1_by_default` | Loopback default | Unit | ⚠️ Deferred |
| `test_studio_routes_require_session_token` | Missing or wrong token gets 401/403 | Unit | ⚠️ Deferred |
| `test_studio_save_script_runs_validation` | Invalid script rejected with chunk numbers | Unit | ⚠️ Deferred |
| `test_studio_render_chunk_returns_take_id` | Take id returned | Unit | ⚠️ Deferred |
| `test_studio_list_takes_includes_similarity_scores` | Scores in listing | Unit | ⚠️ Deferred |
| `test_studio_select_take_and_remaster` | Selection triggers re-master | Unit | ⚠️ Deferred |

### 5.23 HTTP server (FR-023)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_server_post_job_returns_job_id_async` | Job accepted asynchronously | Unit | ⚠️ Deferred |
| `test_server_job_status_endpoint_states` | queued, running, done, failed | Unit | ⚠️ Deferred |
| `test_server_artifacts_downloadable_after_done` | MP3, VTT, manifest download | Unit | ⚠️ Deferred |
| `test_server_bearer_token_required_when_configured` | 401 without token | Unit | ⚠️ Deferred |
| `test_server_no_auth_when_token_unset_binds_loopback` | Safe default bind | Unit | ⚠️ Deferred |
| `test_server_clone_request_unregistered_voice_403` | Consent enforced over HTTP | Unit | ⚠️ Deferred |
| `test_server_ssrf_guard_applies_to_submitted_urls` | Private URLs refused | Unit | ⚠️ Deferred |
| `it_server_job_roundtrip_with_mock_backend` | Submit, poll, download with real uvicorn | Integration | ⚠️ Deferred |

### 5.24 MCP server (FR-024)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_mcp_tools_listed_match_appendix_e` | All Appendix E tools present | Unit | ⚠️ Deferred |
| `test_mcp_tool_input_schemas_valid_json_schema` | Schemas are valid | Unit | ⚠️ Deferred |
| `test_mcp_tool_call_narrate_returns_manifest_summary` | Tool executes with mocks | Unit | ⚠️ Deferred |
| `test_mcp_clone_tool_enforces_consent` | Same registry guard | Unit | ⚠️ Deferred |
| `it_mcp_stdio_transport_list_tools` | Real stdio session lists tools | Integration | ⚠️ Deferred |
| `it_mcp_streamable_http_transport_list_tools` | Real streamable HTTP session lists tools | Integration | ⚠️ Deferred |

### 5.25 Agent harness (Appendix K, S0-T08)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_harness_claude_md_first_line_imports_agents_md` | First line is `@import AGENTS.md` | Unit | ⚠️ Deferred |
| `test_harness_soul_md_has_6_constraints_no_commands_or_paths` | SOUL.md rules | Unit | ⚠️ Deferred |
| `test_harness_required_skills_run_and_exit_0` | `run-tests` and `check-types` skills exit 0 | Unit | ⚠️ Deferred |
| `test_harness_no_em_dash_in_repo_text_files` | Em dash check over md, py, ts, yaml | Unit | ⚠️ Deferred |
| `test_harness_em_dash_hook_fails_on_u2014` | Pre-commit hook rejects the character | Unit | ⚠️ Deferred |
| `smoke_harness_narrate_fixture_skill_exits_0` | `narrate-fixture` skill runs with mocks | Smoke | ⚠️ Deferred |
| `it_harness_pi_extension_loads_and_lists_commands` | `integrations/pi` extension loads (vitest) | Integration | ⚠️ Deferred |

### 5.26 Packaging, release, and versions

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_versions_check_exits_1_naming_mismatched_file` | `check-versions.sh` failure message | Unit | ⚠️ Deferred |
| `test_versions_extract_changelog_prints_only_section` | `extract-changelog.sh 0.1.0` | Unit | ⚠️ Deferred |
| `test_packaging_uv_sync_all_extras_succeeds` | `uv sync --all-extras --dev` on macOS arm64 and Linux x86_64 | Integration | ⚠️ Deferred |
| `test_packaging_wheel_contains_studio_static_and_schemas` | Built wheel includes `audio_smith/studio/static/` and schemas | Integration | ⚠️ Deferred |
| `test_packaging_third_party_licenses_covers_all_deps` | CI fails when a dependency has no entry | Unit | ⚠️ Deferred |
| `test_packaging_uv_tool_install_runs_version_and_doctor` | Clean `uv tool install .` works | Integration | ⚠️ Deferred |
| `test_security_gitleaks_pip_audit_npm_audit_clean` | Zero high or critical findings | Integration | ⚠️ Deferred |
| `it_release_testpypi_dry_run_from_rc_tag` | `v1.0.0-rc.1` publishes to TestPyPI | Integration | ❌ Skipped: needs the owner to configure PyPI trusted publishing and push a tag. Manual step: owner pushes `v1.0.0-rc.1` and verifies the TestPyPI release |
| `it_release_npm_provenance_published` | npm packages carry provenance | Integration | ❌ Skipped: requires the owner's npm publishing setup. Manual step: after the release run, verify the provenance badge on npmjs.com |
| `smoke_release_uv_tool_install_v1_0_0` | `uv tool install mr-audio-smith` installs v1.0.0 from PyPI | Smoke | ❌ Skipped: PyPI publication is an owner action. Manual step: after release, run the install on a clean machine and `mr-audio-smith --version` |

### 5.27 Real-voice and listening scenarios

| ID | Scenario | Type | Status |
|---|---|---|---|
| `listen_en_letter_calm_kid5_cloned_voice` | Listening round, letter 1 (en) | Manual | ❌ Skipped: human required. Manual step: section 6 protocol, record scores in `docs/LISTENING_TESTS.md` |
| `listen_en_letter_2_kid5_cloned_voice` | Listening round, letter 2 (en) | Manual | ❌ Skipped: human required. Manual step: section 6 protocol |
| `listen_en_letter_3_kid5_cloned_voice` | Listening round, letter 3 (en) | Manual | ❌ Skipped: human required. Manual step: section 6 protocol |
| `listen_hi_letter_kid5_cloned_voice` | Listening round, Hindi letter | Manual | ❌ Skipped: human required, Hindi-literate rater and GPU. Manual step: section 6 protocol with a Hindi speaker |
| `it_maya2_reference_letter_cloned_voice_end_to_end` | Reference letter narrated in a cloned voice (Sprint 3 gate) | Integration | ❌ Skipped: no GPU runner, real cloned voice needed. Manual step: `mr-audio-smith run <reference-url> --profile kid-5 --voice dad` on a GPU machine, then listen |

Row count: more than 120 scenarios across 27 tables.

---

## 6. Listening test protocol

Human evaluation required before every release and at the Sprint 3 gate (internal round) and Sprint 6 (release round, S6-T04).

### 6.1 Materials

| Item | Detail |
|---|---|
| Letters | 3 fixture letters in English (kid-5 profile) and 1 letter in Hindi (translated track, same cloned voice) |
| Voice | The consented cloned voice (maintainer's own, with a consent record) |
| Build | The release candidate, rendered with the same backend and settings as production |
| Listeners | At least 3 raters, one of whom is a parent or caregiver of the target age group; the Hindi letter needs a fluent Hindi listener |
| Environment | Quiet room, closed-back headphones or a decent speaker; same device for all raters |
| Script access | Raters read the generated script after the first listen, to judge faithfulness |

### 6.2 Procedure

1. Render each letter fresh with the release candidate (clear the chunk cache for the voice).
2. Rater listens once straight through without pausing, then scores clarity, pacing, warmth, and consistency.
3. Rater reads the narrated script and the original page, listens a second time with the script open, and scores pronunciation and script faithfulness.
4. Rater writes at least one specific note per score below 4 (timestamp plus what went wrong).
5. The coordinator collates scores into `docs/LISTENING_TESTS.md`.

### 6.3 Rubric (each criterion scored 1 to 5)

| Criterion | 1 | 3 | 5 |
|---|---|---|---|
| Warmth | Cold, robotic | Pleasant but flat | Sounds like a caring person reading to a child |
| Clarity | Words often unclear | Mostly clear, some mumbling | Every word clear at normal volume |
| Pacing | Rushed or dragging throughout | Acceptable with a few awkward pauses | Natural rhythm, pauses land where a reader would pause |
| Pronunciation | Frequent errors, names wrong | Occasional errors | Names, words, and (for Hindi) native phonemes correct; lexicon entries applied |
| Consistency | Voice identity drifts, level jumps between chunks | Minor drift | Same voice and level across the whole narration; no audible chunk seams |
| Script faithfulness | Meaning changed or content invented | Minor paraphrase drift | Every fact, name, and the signature preserved; verbatim blocks exact |

### 6.4 Pass rule

- Compute the average of each criterion across all raters and across all four letters.
- **Release is blocked if any criterion average is under 4.**
- Any single score of 2 or lower on pronunciation of a person's name, or any invented content, blocks the release regardless of averages and opens a bug issue (which then gets a regression test).
- Failed rounds are re-run after fixes; both rounds are kept in `docs/LISTENING_TESTS.md`.

### 6.5 Scoring sheet template

```
Release candidate: v_._._-rc._      Date: ____-__-__      Rater: __________
Backend: ______  Voice: ______  Profile: kid-5  Device: __________

Letter: [ ] en-1 letter-calm  [ ] en-2  [ ] en-3  [ ] hi-1
```

| Criterion | Score (1-5) | Timestamp and note (required if under 4) |
|---|---|---|
| Warmth | | |
| Clarity | | |
| Pacing | | |
| Pronunciation | | |
| Consistency | | |
| Script faithfulness | | |

Summary table in `docs/LISTENING_TESTS.md`:

| Criterion | en-1 | en-2 | en-3 | hi-1 | Average | Pass (>= 4) |
|---|---|---|---|---|---|---|
| Warmth | | | | | | |
| Clarity | | | | | | |
| Pacing | | | | | | |
| Pronunciation | | | | | | |
| Consistency | | | | | | |
| Script faithfulness | | | | | | |

Decision: [ ] Release approved   [ ] Release blocked (reason: ______________)

---

## 7. Smoke checklist for staging

Run on the staging branch build before promoting to main. Automated items run in CI (`smoke` and `harness-smoke-tests` jobs); manual items need a person.

| # | Check | How | Automated |
|---|---|---|---|
| 1 | Clean install works | `uv tool install .` in a fresh venv; `mr-audio-smith --version` prints the version from `pyproject.toml` | Yes |
| 2 | Doctor passes | `mr-audio-smith doctor` exits 0, `--json` parses | Yes |
| 3 | Mock end-to-end | `tests/smoke/smoke.sh` produces MP3, VTT, manifest, embed html; manifest validates | Yes |
| 4 | Versions agree | `scripts/check-versions.sh` exits 0 | Yes |
| 5 | Cache hit speed | Second `run` on unchanged fixture finishes under 2 s and renders 0 chunks | Yes |
| 6 | Inject idempotence | `--inject` twice on the fixture page: second diff empty | Yes |
| 7 | Site mode | Fixture index (3 pages): first run renders 3, second renders 0 | Yes |
| 8 | Player no-JS | Embed page with JS disabled plays the native audio | Yes (E2E) |
| 9 | Studio zero external requests | Open Studio, load a project, no network request leaves localhost | Yes (E2E) |
| 10 | Consent guard | `mr-audio-smith run ... --voice not-registered` fails with the consent message | Yes |
| 11 | Real LLM script | `script` on the reference page with Ollama yields a valid kid-5 script | Manual (needs Ollama) |
| 12 | Kokoro CPU render | One chunk renders on a CPU-only machine | Yes (integration) |
| 13 | Maya 2 render | One chunk in a registered cloned voice on the GPU machine | Manual (GPU) |
| 14 | Hindi track | `--langs en,hi` produces `{slug}.hi.mp3` and the toggle works in the player | Manual (GPU) |
| 15 | Loudness spot check | `ffmpeg -i out/<slug>/<slug>.mp3 -af ebur128=peak=true -f null -` shows about -16 LUFS and true peak at or below -1.5 dBTP | Yes |
| 16 | Listen to one output | Play the staging MP3 end to end in the real player on desktop and phone | Manual (human) |
| 17 | Browser matrix | Chrome, Firefox, Safari (macOS, iOS): play, seek, captions, language toggle | Manual (human) |
| 18 | Action dry run | Action in the throwaway repo: changed page narrated; unchanged push is a no-op | Manual |
| 19 | Docs links | mkdocs build has no broken links; quickstart commands copy-paste cleanly | Yes |
| 20 | Secrets scan | gitleaks, pip-audit, npm audit report no high findings | Yes |

Sign-off: staging promoted only when every automated item is green and every manual item is checked with initials and date in the release PR.

---

## 8. Regression policy and flake policy

### 8.1 Regression policy

- Every bug fixed gets exactly one new regression test in `tests/regression/` (or the matching vitest folder), named `regression_{gh_issue_number}_{what_was_broken}`.
- The test is written first, shown to fail on the buggy code, then the fix is made (the TDD rule in AGENTS.md).
- Regression tests are never deleted. If a feature is removed, the test is moved to `tests/regression/archived/` with a comment naming the removal PR, and keeps running if it is still meaningful.
- A bug found by a listening test, a staging smoke run, or a user report follows the same path.
- A regression test must run in the default CI (unit or integration tier); a GPU-only bug gets a respx-mocked reproduction plus a `gpu` marked confirmation test.

Lifecycle:

```
  bug reported / found
         |
         v
  GitHub issue opened (#N, label type: bug)
         |
         v
  failing test written:  regression_N_<what_was_broken>   (RED)
         |
         v
  fix implemented, test passes                            (GREEN)
         |
         v
  PR merged, issue closed with link to the test
         |
         v
  test lives in tests/regression/ forever, runs in every CI
         |
         +--> feature removed? move to tests/regression/archived/ (never delete)
```

### 8.2 Flake policy

- A flaky test is quarantined with `@pytest.mark.flaky_quarantine` and a linked issue within 24 hours, fixed within the sprint. Quarantine never exceeds 5 tests.
- Quarantined tests still run on a nightly job and report, but do not gate merges.
- Rerunning a failed CI job until it passes is not a fix; the first flaky failure is logged in the linked issue with the run URL.
- If the quarantine would exceed 5 tests, new feature work stops until the count is back under the cap.
- Network, timing, and ordering flakes are fixed by injecting fakes (respx, fake clocks, mock backend), not by increasing timeouts.
- A test quarantined past the end of its sprint is escalated to p0 for the next sprint.
