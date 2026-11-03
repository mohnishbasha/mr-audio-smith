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
| `test_fetch_private_ip_blocked` | SSRF guard rejects private, loopback, link-local, metadata addresses | Unit | ✅ Automated |
| `test_fetch_redirect_to_private_blocked` | Redirect from public host to private IP is rejected | Unit | ✅ Automated |
| `test_fetch_allow_private_flag_permits_loopback` | `--allow-private` lets loopback through | Unit | ✅ Automated |
| `test_fetch_dns_rebinding_connects_to_resolved_ip` | DNS resolved once, connection pinned to that IP | Unit | ✅ Automated |
| `test_fetch_non_http_scheme_rejected` | `ftp:`, `gopher:`, `javascript:` rejected with clear error | Unit | ✅ Automated |
| `test_fetch_timeout_default_20s_honored` | Default timeout of 20 s applies; configured value overrides | Unit | ✅ Automated |
| `test_fetch_max_size_5mb_aborts_stream` | Streamed body aborted at the 5 MB limit | Unit | ✅ Automated |
| `test_fetch_redirect_limit_5_enforced` | Sixth redirect raises | Unit | ✅ Automated |
| `test_fetch_user_agent_descriptive_sent` | Request carries `mr-audio-smith/{version}` User-Agent | Unit | ✅ Automated |
| `test_fetch_local_file_no_network` | Local .html and .md read with network disabled | Unit | ✅ Automated |
| `test_fetch_charset_from_content_type_decoded` | Non-UTF-8 charset decoded correctly | Unit | ✅ Automated |
| `test_fetch_hostile_page_within_limits` | `hostile.html` (3 MB text, base64) handled without exceeding memory or time budget | Unit | ✅ Automated |

### 5.2 Extract and blocks (FR-002, FR-003, FR-026)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_extract_blocks_data_narrate_present_uses_only_marked_element` | Extraction honors [data-narrate] | Unit | ✅ Automated |
| `test_extract_blocks_article_used_when_no_data_narrate` | Fallback 2: `<article>` | Unit | ✅ Automated |
| `test_extract_blocks_trafilatura_used_when_no_article` | Fallback 3: trafilatura main content | Unit | ✅ Automated |
| `test_extract_blocks_readability_fallback_last_resort` | Fallback 4: readability when trafilatura returns empty | Unit | ✅ Automated |
| `test_extract_blocks_nav_header_footer_excluded` | Boilerplate elements excluded | Unit | ✅ Automated |
| `test_extract_blocks_scripts_styles_forms_excluded` | script, style, noscript, svg, button, form removed | Unit | ✅ Automated |
| `test_extract_blocks_emoji_stripped` | Emoji never reach blocks | Unit | ✅ Automated |
| `test_extract_blocks_regional_indicator_flags_stripped` | Flag emoji (regional indicator pairs) stripped | Unit | ✅ Automated |
| `test_extract_blocks_skip_attribute_excluded` | data-narrate="skip" excluded | Unit | ✅ Automated |
| `test_extract_blocks_parent_attribute_routed` | Parent track routing | Unit | ✅ Automated |
| `test_extract_blocks_types_title_heading_paragraph_list_quote_signature` | All six block types emitted in document order | Unit | ✅ Automated |
| `test_extract_blocks_signature_role_attribute_detected` | `data-narrate-role="signature"` becomes signature block | Unit | ✅ Automated |
| `test_extract_blocks_signoff_pattern_detected` | Final short paragraph with sign-off pattern becomes signature | Unit | ✅ Automated |
| `test_extract_blocks_list_items_capture_index_and_nested_heading` | list_item keeps index and parent heading | Unit | ✅ Automated |
| `test_extract_blocks_grown_up_note_not_parent_without_attribute` | No magic-string matching in core | Unit | ✅ Automated |
| `test_extract_blocks_parent_headings_profile_rule_opt_in` | `parent_headings` profile rule routes "A grown-up note" to parent | Unit | ✅ Automated |
| `test_extract_letter_calm_matches_golden_blocks` | Snapshot of `letter-calm.html` equals `golden/letter-calm.blocks.json` | Unit | ✅ Automated |
| `test_extract_hostile_html_no_crash_within_limits` | `hostile.html` yields blocks without hang | Unit | ✅ Automated |
| `test_extract_blocks_fuzz_hypothesis_never_raises` | Hypothesis-generated HTML never crashes the extractor | Unit | ✅ Automated |
| `test_blocks_hash_whitespace_change_stable` | Hash ignores whitespace | Unit | ✅ Automated |
| `test_blocks_hash_markup_only_change_stable` | Markup-only change (extra wrapper div) keeps hash | Unit | ✅ Automated |
| `test_blocks_hash_text_change_differs` | Hash detects text edits | Unit | ✅ Automated |
| `test_blocks_hash_profile_version_change_differs` | Profile version is part of the hash input | Unit | ✅ Automated |
| `test_blocks_hash_backend_voice_language_change_differs` | Backend id, voice id, and language each alter the hash | Unit | ✅ Automated |
| `test_blocks_normalize_smart_quotes_for_hash_only` | Smart quotes normalized for hashing, preserved in stored text | Unit | ✅ Automated |
| `test_blocks_hash_whitespace_invariant_property` | Hypothesis property: whitespace invariance | Unit | ✅ Automated |
| `test_parent_track_excluded_from_child_blocks` | Parent-marked blocks never appear in the child track (FR-026) | Unit | ✅ Automated |

### 5.3 Profiles (FR-004)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_profiles_load_invalid_rate_rejected` | Schema errors are clear | Unit | ✅ Automated |
| `test_profiles_load_error_names_field_path` | Error message contains the YAML field path | Unit | ✅ Automated |
| `test_profiles_builtins_kid5_kid8_commute_brief_load` | All four built-in profiles validate | Unit | ✅ Automated |
| `test_profiles_user_profile_overrides_builtin_same_id` | `./profiles` entry wins over the built-in | Unit | ✅ Automated |
| `test_profiles_semantic_version_required` | Missing or non-semver version rejected | Unit | ✅ Automated |
| `test_profiles_custom_commute_fixture_loads` | `profiles/custom-commute.yaml` loads | Unit | ✅ Automated |
| `test_profiles_json_schema_matches_pydantic_model` | Exported `schemas/profile.schema.json` is current | Unit | ✅ Automated |
| `test_cli_profile_list_show_validate_commands` | `profile list`, `show`, `validate` behave and set exit codes | Unit | ✅ Automated |

### 5.4 LLM providers (FR-005 provider support)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_llm_ollama_chat_request_shape` | `/api/chat` body, model, options match (respx) | Unit | ✅ Automated |
| `test_llm_anthropic_provider_passes_model_and_system` | Anthropic SDK called with configured model (stubbed) | Unit | ✅ Automated |
| `test_llm_openai_compat_base_url_and_key` | base_url and key applied | Unit | ✅ Automated |
| `test_llm_fake_provider_replays_by_prompt_hash` | FakeProvider returns the recorded response | Unit | ✅ Automated |
| `test_llm_fake_provider_unknown_hash_raises_clear_error` | Missing recording names the hash and `make record-llm` | Unit | ✅ Automated |
| `test_llm_provider_string_parsing_all_three_formats` | `ollama:qwen3:14b`, `anthropic:<id>`, `openai_compat:<url>#<model>` | Unit | ✅ Automated |
| `test_llm_ollama_unreachable_preflight_hint` | Doctor hint when Ollama is down | Unit | ✅ Automated |
| `test_llm_seed_and_temperature_zero_passed_where_supported` | Determinism parameters forwarded | Unit | ✅ Automated |
| `it_ollama_script_kid5_within_length` | Real LLM script length | Integration | ⚠️ Deferred |

### 5.5 Script generation and validation (FR-005, FR-006)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_script_validate_unknown_marker_rejected` | Validator rejects invented tags | Unit | ✅ Automated |
| `test_script_validate_empty_chunk_rejected` | Empty chunk reported with number | Unit | ✅ Automated |
| `test_script_validate_chunk_over_max_chars_rejected` | Chunk over `max_chunk_chars` reported | Unit | ✅ Automated |
| `test_script_validate_strips_stray_markdown_and_emoji` | Stray `**`, `#`, emoji removed | Unit | ✅ Automated |
| `test_script_validate_reports_violations_with_chunk_numbers` | Every violation carries its chunk number | Unit | ✅ Automated |
| `test_script_validate_verbatim_chunk_changed_rejected` | Verbatim enforced | Unit | ✅ Automated |
| `test_script_validate_signature_altered_rejected` | Signature must be preserved exactly | Unit | ✅ Automated |
| `test_script_validate_allowed_markers_only_pass` | `[pause N]` and allowed emphasis pass | Unit | ✅ Automated |
| `test_script_parse_serialize_roundtrip_property` | Parse then serialize is identity (hypothesis) | Unit | ✅ Automated |
| `test_script_parse_frontmatter_and_numbered_chunks` | Frontmatter and chunk numbering parsed | Unit | ✅ Automated |
| `test_script_parse_invalid_markers_fixture_rejected` | `scripts/invalid-markers.script.md` fails | Unit | ✅ Automated |
| `test_script_parse_valid_fixture_passes` | `scripts/valid.script.md` passes | Unit | ✅ Automated |
| `test_script_writer_retry_with_violations_succeeds` | One corrective retry | Unit | ✅ Automated |
| `test_script_writer_second_failure_raises` | Fails after the single retry | Unit | ✅ Automated |
| `test_script_writer_target_length_within_20_percent` | Word count within target_minutes x 130 x rate, plus or minus 20 percent | Unit | ✅ Automated |
| `test_script_writer_prompt_version_in_cache_key` | Template version changes the script cache key | Unit | ✅ Automated |
| `test_script_writer_interactive_moments_count_requested` | Prompt carries `interactive_moments` count | Unit | ✅ Automated |
| `test_script_writer_fake_provider_matches_golden_script` | `letter-calm` + kid-5 equals `golden/letter-calm.en.script.md` | Unit | ✅ Automated |
| `test_script_writer_deterministic_temperature_zero_fixed_seed` | Same inputs and seed give the same script (fake and where supported) | Unit | ✅ Automated |

### 5.6 Lexicon (FR-007)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_lexicon_apply_whole_word_only` | "Aadi" replaced, "Aadish" not | Unit | ✅ Automated |
| `test_lexicon_apply_case_sensitive` | "aadi" untouched when entry is "Aadi" | Unit | ✅ Automated |
| `test_lexicon_stored_script_unchanged_after_apply` | Replacement happens at synthesis only; stored script bytes unchanged | Unit | ✅ Automated |
| `test_lexicon_project_overrides_profile_entry` | `lexicon.yaml` wins on conflict | Unit | ✅ Automated |
| `test_lexicon_merge_profile_and_project` | Union of both sources | Unit | ✅ Automated |

### 5.7 Translation (FR-008)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_translate_preserves_chunk_count_and_pauses` | Translation alignment | Unit | ✅ Automated |
| `test_translate_output_named_slug_lang_script_md` | `{slug}.hi.script.md` written | Unit | ✅ Automated |
| `test_translate_misaligned_output_retried_then_fails` | Chunk count mismatch triggers corrective retry | Unit | ✅ Automated |
| `test_translate_backend_lacking_language_fails_preflight` | Clear message for unsupported language | Unit | ✅ Automated |
| `test_translate_manifest_lists_language_tracks` | Manifest `tracks` has one entry per language | Unit | ✅ Automated |
| `it_maya2_translate_hindi_track_rendered` | Hindi track rendered with cross-lingual cloned voice | Integration | ❌ Skipped: requires NVIDIA GPU runner. Manual step: on a GPU machine run `mr-audio-smith run <letter> --langs en,hi --voice <clone>` and confirm `{slug}.hi.mp3` plays in the cloned voice |

### 5.8 TTS backends (FR-009, FR-010)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_tts_registry_lists_five_backends` | maya2, kokoro, openai, openai_compat, mock registered | Unit | ⚠️ Deferred |
| `test_tts_mock_deterministic_across_runs` | Same text, voice, seed give identical samples | Unit | ✅ Automated |
| `test_tts_mock_duration_proportional_to_text_length` | Duration scales with characters | Unit | ✅ Automated |
| `test_tts_mock_pitch_derived_from_voice_id` | Different voices give different pitch | Unit | ✅ Automated |
| `test_tts_capabilities_flags_per_backend` | Languages, clone, sample rate, license, commercial_ok correct | Unit | ✅ Automated |
| `test_tts_openai_compat_success_returns_pcm` | 200 WAV decoded to PcmAudio (respx) | Unit | ✅ Automated |
| `test_tts_openai_compat_4xx_raises_no_retry` | 4xx surfaced immediately | Unit | ✅ Automated |
| `test_tts_openai_compat_5xx_retries_with_backoff` | 5xx retried | Unit | ✅ Automated |
| `test_tts_openai_compat_timeout_raises` | Timeout becomes backend error | Unit | ✅ Automated |
| `test_tts_maya2_request_body_matches_server_contract` | Body has model, input, voice, language, response_format, seed, `speed` fixed at 1.0 | Unit | ✅ Automated |
| `test_tts_maya2_default_url_port_8080` | Default `AUDIO_SMITH_MAYA2_URL` is `http://127.0.0.1:8080/v1` | Unit | ✅ Automated |
| `test_tts_maya2_rate_applied_post_synthesis_atempo` | Speaking rate applied by ffmpeg atempo, not sent to the server (ADR-016) | Unit | ✅ Automated |
| `test_tts_maya2_pause_markers_split_into_separate_requests` | No inline tags; pauses become silences | Unit | ⚠️ Deferred |
| `test_tts_maya2_emphasis_markers_stripped` | `*emphasis*` removed before the request | Unit | ⚠️ Deferred |
| `test_tts_maya2_registers_clone_via_voices_endpoint_idempotent` | POST /v1/voices with `as-{voice_id}-{clip_hash[:8]}`; 409 treated as ok | Unit | ✅ Automated |
| `test_tts_maya2_503_not_ready_retries_with_retry_after` | 503 honored before failing | Unit | ✅ Automated |
| `test_tts_maya2_supports_all_12_languages` | Capabilities list as, bn, en, gu, hi, kn, ml, mr, or, pa, ta, te | Unit | ✅ Automated |
| `test_tts_maya2_inproc_mode_requires_extra` | `--maya2-mode inproc` errors with hint when `maya2` extra missing | Unit | ✅ Automated |
| `test_tts_license_guard_noncommercial_requires_flag` | `commercial_ok: false` without `--accept-noncommercial` refuses | Unit | ✅ Automated |
| `test_tts_license_guard_flag_recorded_in_manifest_warnings` | Accepted noncommercial use is logged in the manifest | Unit | ✅ Automated |
| `it_maya2_synth_clone_returns_24khz_mono` | Maya 2 integration | Integration | ❌ Skipped: no GPU runner in default CI (marker `gpu`, needs `AUDIO_SMITH_IT_MAYA2_URL`). Manual step: start `python -m maya3.server --ckpt maya-research/maya2-native --host 127.0.0.1 --port 8080`, then `AUDIO_SMITH_IT_MAYA2_URL=http://127.0.0.1:8080/v1 pytest -m "integration and gpu"` |
| `it_maya2_synth_builtin_voice_returns_audio` | Built-in voice (for example Ahana) renders | Integration | ❌ Skipped: no GPU runner. Manual step: same server as above, run the `gpu` marker subset |
| `it_maya2_health_reports_loaded_model` | Doctor reports reachability and loaded model | Integration | ❌ Skipped: no GPU runner. Manual step: run `mr-audio-smith doctor` against a live Maya 2 server and confirm the backend row is OK |
| `it_kokoro_synth_cpu_returns_audio` | Kokoro integration | Integration | ✅ Automated |
| `it_kokoro_weights_checksum_verified` | First-use download verified against the pinned checksum | Integration | ⚠️ Deferred |
| `it_openai_compat_local_stub_server_roundtrip` | Real HTTP against a local stub speech server | Integration | ⚠️ Deferred |

### 5.9 Voices, consent, and clip check (FR-011)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_consent_clone_unregistered_voice_raises` | Consent enforced in core | Unit | ✅ Automated |
| `test_consent_registration_requires_all_fields` | Name, relationship, date, statement all required | Unit | ✅ Automated |
| `test_consent_relationship_only_self_or_written_permission` | Other relationship values rejected | Unit | ✅ Automated |
| `test_consent_enforced_from_python_api_and_cli_and_server` | `voices.registry.resolve()` guards every front door | Unit | ✅ Automated |
| `test_consent_backend_refuses_clone_without_registry_entry` | Backend-level refusal | Unit | ✅ Automated |
| `test_clipcheck_too_short_rejected` | Clip quality gate | Unit | ✅ Automated |
| `test_clipcheck_too_long_over_30s_rejected` | Duration above 30 s rejected | Unit | ✅ Automated |
| `test_clipcheck_sample_rate_below_16khz_rejected` | Low sample rate rejected | Unit | ✅ Automated |
| `test_clipcheck_clipping_over_0_1_percent_rejected` | `voices/clipped.wav` fails | Unit | ✅ Automated |
| `test_clipcheck_snr_below_25db_rejected` | `voices/noisy.wav` fails | Unit | ✅ Automated |
| `test_clipcheck_stereo_downmixed_to_mono` | Stereo accepted and downmixed | Unit | ✅ Automated |
| `test_clipcheck_clean_fixture_passes` | `voices/clean.wav` passes | Unit | ✅ Automated |
| `test_voices_add_stores_24k_mono_reference_copy` | `reference.24k.wav` written; clip hash computed | Unit | ✅ Automated |
| `test_voices_list_check_remove_commands` | Registry CRUD works | Unit | ✅ Automated |
| `test_voices_gitignore_blocks_reference_wav` | Real clips under `voices/*/reference.wav` are ignored; fixtures are not | Unit | ✅ Automated |
| `test_cli_voice_add_interactive_consent_prompt` | Interactive consent flow completes | Unit | ✅ Automated |

### 5.10 Chunk planner and synthesis runner (FR-009, FR-012)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_planner_split_on_pause_markers_into_segments` | `[pause N]` splits units | Unit | ✅ Automated |
| `test_planner_max_chars_splits_on_sentence_boundary` | Never splits mid-sentence | Unit | ✅ Automated |
| `test_planner_lexicon_applied_before_keying` | Lexicon affects synthesis text and key | Unit | ✅ Automated |
| `test_planner_chunk_key_stable_across_runs` | Keys deterministic | Unit | ✅ Automated |
| `test_planner_chunk_key_changes_with_voice_seed_rate` | Voice, seed, or rate alters the key | Unit | ✅ Automated |
| `test_runner_cache_hit_skips_synthesis` | Cached chunk is not re-synthesized | Unit | ✅ Automated |
| `test_runner_failed_chunk_retried_twice_with_backoff` | Retries 2 times with exponential backoff and jitter | Unit | ✅ Automated |
| `test_runner_third_failure_marks_chunk_failed` | Failure surfaced after retries | Unit | ✅ Automated |
| `test_runner_resume_after_interrupt_renders_only_remainder` | Partial progress survives (FR-012) | Unit | ✅ Automated |
| `test_runner_cache_write_atomic_temp_rename` | No partial WAV is ever visible | Unit | ✅ Automated |
| `test_runner_chunks_subset_renders_only_selected` | `--chunks 3,4` renders those only | Unit | ✅ Automated |
| `test_runner_concurrency_bounded_semaphore_default_2` | At most 2 in-flight requests | Unit | ✅ Automated |
| `it_runner_kill_midrun_then_resume_renders_remainder` | Real process killed with SIGINT, re-run completes | Integration | ⚠️ Deferred |

### 5.11 Voice consistency QA (FR-013)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_qa_similarity_below_threshold_rerenders` | QA retake loop | Unit | ✅ Automated |
| `test_qa_rerender_uses_new_seed_each_take` | Seeds differ across takes | Unit | ✅ Automated |
| `test_qa_takes_per_chunk_limit_respected` | Stops after `takes_per_chunk` | Unit | ✅ Automated |
| `test_qa_best_take_kept_by_score` | Highest similarity retained | Unit | ✅ Automated |
| `test_qa_builtin_voice_compared_to_chunk_1` | Reference is chunk 1 when no clip | Unit | ✅ Automated |
| `test_qa_report_lists_scores_per_chunk` | Scores in the report and manifest | Unit | ✅ Automated |
| `test_qa_default_threshold_0_75` | Default threshold value | Unit | ✅ Automated |
| `test_qa_extra_missing_skips_with_manifest_warning` | resemblyzer absent: warning, no crash (ADR-015) | Unit | ✅ Automated |
| `it_qa_resemblyzer_embeds_fixture_clip` | Real embedding of `voices/clean.wav` returns a vector | Integration | ⚠️ Deferred |

### 5.12 Assemble and master (FR-014)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_assemble_total_duration_equals_parts_plus_pauses` | Sum within 5 ms per join (golden, mock audio) | Unit | ✅ Automated |
| `test_assemble_crossfade_10ms_at_joins` | Short crossfade at joins | Unit | ✅ Automated |
| `test_assemble_resamples_to_44100` | Output rate 44.1 kHz | Unit | ✅ Automated |
| `test_assemble_chunk_timestamps_within_10ms` | Start and end boundaries within tolerance | Unit | ✅ Automated |
| `test_assemble_heading_and_chunk_pauses_from_profile` | `pause_after_heading_ms`, `pause_between_chunks_ms` applied | Unit | ✅ Automated |
| `test_master_ffmpeg_args_are_array_no_shell` | Wrapper never builds shell strings | Unit | ✅ Automated |
| `test_master_loudness_within_target` | -16 LUFS plus or minus 1 | Integration | ✅ Automated |
| `it_master_true_peak_at_or_below_minus_1_5_dbtp` | True peak limit via ebur128 | Integration | ✅ Automated |
| `it_master_mp3_128k_mono_44100_default` | Default encode parameters verified with ffprobe | Integration | ✅ Automated |
| `it_master_opus_optional_output_created` | `--opus` yields a valid Opus file | Integration | ✅ Automated |
| `it_master_intro_outro_stings_included` | Stings add expected duration | Integration | ✅ Automated |
| `it_master_music_bed_ducks_under_voice` | Bed at -24 dB under voice with sidechain | Integration | ✅ Automated |
| `it_master_two_pass_loudnorm_runs` | Measure pass then apply pass | Integration | ✅ Automated |
| `test_master_stings_are_procedural_and_documented` | `assets/stings/` entries listed as original in THIRD_PARTY_LICENSES | Unit | ✅ Automated |
| `test_perf_reference_letter_meets_nfr_003` | Reference letter time meets NFR-003 (logged to `docs/PERFORMANCE.md`) | Integration | ❌ Skipped: needs GPU runner for the Maya 2 numbers. Manual step: run the reference letter on the GPU machine, record wall time in `docs/PERFORMANCE.md` |

### 5.13 ID3 tags (FR-014)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_tags_id3_title_artist_album_date_written` | TIT2, TPE1, TALB, TDRC readable by mutagen | Unit | ✅ Automated |
| `test_tags_author_from_page_meta_else_config` | Artist fallback order | Unit | ⚠️ Deferred |
| `test_tags_cover_art_same_origin_under_1mb_embedded` | APIC embedded | Unit | ✅ Automated |
| `test_tags_cover_art_cross_origin_skipped` | Cross-origin og:image ignored | Unit | ✅ Automated |
| `test_tags_cover_art_over_1mb_skipped` | Oversized image ignored | Unit | ✅ Automated |

### 5.14 WebVTT captions (FR-015)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_vtt_cues_align_within_150ms` | Caption alignment | Unit | ✅ Automated |
| `test_vtt_one_cue_per_sentence` | Sentence-level cues | Unit | ✅ Automated |
| `test_vtt_text_from_narrated_script_not_page` | Cue text equals the script text | Unit | ✅ Automated |
| `test_vtt_distribution_by_character_length_proportion` | Within-chunk timing split proportionally | Unit | ✅ Automated |
| `test_vtt_format_valid_header_and_timestamps` | `WEBVTT` header, monotonic `hh:mm:ss.mmm` | Unit | ✅ Automated |
| `test_vtt_pause_markers_not_rendered_as_text` | Markers absent from cue text | Unit | ✅ Automated |

### 5.15 Manifest (FR-016)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_manifest_validates_against_published_schema` | Output passes `schemas/manifest.schema.json` | Unit | ✅ Automated |
| `test_manifest_contains_versions_hashes_backend_voice_languages` | All required fields present | Unit | ⚠️ Deferred |
| `test_manifest_records_durations_qa_scores_file_names` | Durations, QA scores, files listed | Unit | ⚠️ Deferred |
| `test_manifest_warnings_include_qa_skipped_and_noncommercial` | Warnings array populated | Unit | ⚠️ Deferred |
| `test_manifest_approved_flag_written_by_studio` | `approved: true` persisted | Unit | ⚠️ Deferred |
| `test_schemas_blocks_profile_manifest_published_and_current` | The three schemas in `schemas/` match models | Unit | ⚠️ Deferred |

### 5.16 Cache (FR-020)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_cache_unchanged_page_skips_render` | Incremental build | Unit | ✅ Automated |
| `test_cache_second_script_run_under_2s` | Second `script` run on unchanged page is a cache hit under 2 s | Integration | ⚠️ Deferred |
| `test_cache_key_format_versioned` | Key begins with a format version | Unit | ✅ Automated |
| `test_cache_version_bump_invalidates_old_entries` | Old-format keys are never read | Unit | ✅ Automated |
| `test_cache_prune_older_than_30d_removes_old_only` | `cache prune --older-than 30d` | Unit | ✅ Automated |
| `test_cache_content_addressed_blocks_scripts_chunks_outputs` | All four kinds stored by hash | Unit | ✅ Automated |
| `test_cache_force_flag_bypasses` | `--force` re-runs the stage | Unit | ✅ Automated |

### 5.17 CLI, doctor, and config (FR-021, S0-T09, S0-T10)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_cli_version_prints_pyproject_version` | `--version` output | Unit | ✅ Automated |
| `test_cli_base_install_does_not_import_torch` | Base install has no torch dependency | Unit | ⚠️ Deferred |
| `test_cli_script_command_writes_blocks_and_script_files` | `{slug}.blocks.json`, `{slug}.en.script.md` | Unit | ⚠️ Deferred |
| `test_cli_slug_from_url_path_stem_sanitized` | Slug rules | Unit | ⚠️ Deferred |
| `test_cli_run_dry_run_prints_plan_and_cache_status` | `--dry-run` writes nothing | Unit | ⚠️ Deferred |
| `test_cli_run_approve_opens_editor_then_continues` | `--approve` with stubbed `$EDITOR` | Unit | ⚠️ Deferred |
| `test_cli_run_output_layout_out_slug` | `out/{slug}/` artifact set | Unit | ⚠️ Deferred |
| `test_cli_run_parent_track_rendered_when_blocks_exist` | `{slug}.parent.mp3` using adult-brief | Unit | ⚠️ Deferred |
| `test_api_narrate_returns_manifest` | `audio_smith.narrate(...)` returns Manifest | Unit | ⚠️ Deferred |
| `test_api_stage_functions_exposed` | extract, write_script, render_script, master, publish importable | Unit | ⚠️ Deferred |
| `test_doctor_all_required_pass_exit_0` | Exit 0 when green | Unit | ✅ Automated |
| `test_doctor_required_failure_exit_3` | Exit 3 on a required failure | Unit | ✅ Automated |
| `test_doctor_each_failure_has_fix_hint` | Hints present for every check | Unit | ✅ Automated |
| `test_doctor_json_output_schema` | `--json` output is valid | Unit | ✅ Automated |
| `test_doctor_ffmpeg_older_than_6_fails` | ffmpeg below 6.0 flagged | Unit | ✅ Automated |
| `test_doctor_python_313_hints_kokoro_use_312` | ADR-017 hint | Unit | ✅ Automated |
| `test_doctor_disk_space_and_cache_writable_checks` | Both checks registered | Unit | ✅ Automated |
| `test_doctor_gpu_visibility_reported_when_torch_installed` | CUDA check conditional on torch | Unit | ⚠️ Deferred |
| `test_doctor_backend_and_llm_and_voices_rows_present` | Each backend, LLM provider, voices checked | Unit | ⚠️ Deferred |
| `test_config_precedence_flags_over_env_over_file_over_defaults` | Full precedence chain | Unit | ✅ Automated |
| `test_config_audio_smith_toml_discovered_upward_from_cwd` | Upward discovery | Unit | ✅ Automated |
| `test_config_unknown_key_warns_not_crashes` | Unknown keys warn | Unit | ✅ Automated |
| `test_config_env_prefix_audio_smith` | `AUDIO_SMITH_` prefix | Unit | ✅ Automated |
| `smoke_run_mock_outputs_exist` | End to end with mocks | Smoke | ✅ Automated |
| `smoke_doctor_exit_0_on_clean_machine` | `doctor` exits 0 first | Smoke | ⚠️ Deferred |
| `smoke_run_mock_manifest_validates` | Manifest passes the schema in the smoke run | Smoke | ⚠️ Deferred |
| `smoke_version_prints_semver` | `--version` smoke | Smoke | ✅ Automated |

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
| `test_player_attributes_parse_tracks_json` | `tracks` JSON parsed; invalid JSON handled | Unit | ✅ Automated |
| `test_player_captions_cue_active_class_follows_time` | Active cue tracking (vitest) | Unit | ✅ Automated |
| `test_player_no_external_network_requests` | Player makes no third-party requests | Unit | ✅ Automated |
| `e2e_US006_player_browser_matrix_chrome_firefox_safari` | Playback in Chromium, Firefox, WebKit | E2E | ❌ Skipped: WebKit and real Safari audio behavior needs a human. Manual step: open the example page in current Safari (macOS and iOS), Firefox, and Chrome; verify play, seek, captions, and language toggle |
| `e2e_US006_player_screen_reader_announcements` | Screen reader labels and live-region announcements | E2E | ❌ Skipped: human required. Manual step: with VoiceOver (macOS) and NVDA (Windows), tab to the player and confirm labels, state changes, and caption toggle are announced |

### 5.19 Embed and inject (FR-017, FR-018)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_embed_snippet_wraps_audio_fallback_inside_component` | Plain `<audio>` inside `<audio-smith-player>` | Unit | ✅ Automated |
| `test_embed_snippet_includes_captions_track` | `<track kind="captions">` present | Unit | ✅ Automated |
| `test_embed_snippet_language_toggle_only_when_multiple_languages` | Toggle conditional | Unit | ✅ Automated |
| `test_embed_snippet_valid_html` | Parses cleanly | Unit | ✅ Automated |
| `test_embed_script_ref_self_hosted_default_path` | `/media/audio/audio-smith-player.js` and file copied | Unit | ✅ Automated |
| `test_embed_script_ref_jsdelivr_pinned_exact_version` | jsDelivr URL pins the exact version | Unit | ✅ Automated |
| `test_inject_idempotent_second_run_no_diff` | Inject idempotence | Unit | ✅ Automated |
| `test_inject_outside_markers_untouched` | Inject safety (byte-identical outside markers) | Unit | ✅ Automated |
| `test_inject_creates_markers_after_selector_when_absent` | Default selector `h1` | Unit | ✅ Automated |
| `test_inject_custom_selector_flag` | `--selector` honored | Unit | ✅ Automated |
| `test_inject_dry_run_prints_unified_diff_writes_nothing` | Dry run | Unit | ✅ Automated |
| `test_inject_replaces_existing_marker_content` | Stale snippet replaced | Unit | ✅ Automated |
| `test_inject_preserves_original_formatting_no_dom_reserialize` | Splice on offsets | Unit | ✅ Automated |
| `test_inject_reference_letter_fixture_idempotent` | Sprint 4 gate on `letter-calm.html` | Unit | ✅ Automated |

### 5.20 Site batch mode (FR-019)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_site_same_origin_links_only` | Cross-origin links dropped | Unit | ✅ Automated |
| `test_site_match_glob_filters_links` | `--match` applied | Unit | ✅ Automated |
| `test_site_max_pages_limit_respected` | Stops at the limit | Unit | ✅ Automated |
| `test_site_unchanged_page_skipped_by_hash` | Skips on identical hash | Unit | ✅ Automated |
| `test_site_fixture_index_second_run_renders_zero` | 3-page fixture, second run renders 0 | Unit | ✅ Automated |
| `test_site_summary_table_columns_page_status_duration` | Table shape and statuses (cached, rendered, failed) | Unit | ✅ Automated |
| `test_site_one_page_failure_does_not_abort_batch` | Failure recorded, run continues | Unit | ✅ Automated |
| `test_site_inject_root_maps_urls_to_local_files` | `--inject-root` mapping | Unit | ✅ Automated |
| `test_examples_letters_to_a_child_runs_with_mock` | Example project runs end to end with mocks in CI | Smoke | ✅ Automated |

### 5.21 GitHub Action (FR-025)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_action_yml_inputs_and_composite_steps_valid` | `action/action.yml` schema valid (actionlint) | Unit | ✅ Automated |
| `test_action_only_files_matching_glob_processed` | Glob filter on changed files | Unit | ✅ Automated |
| `test_action_noop_when_hashes_unchanged` | No commit when nothing changed | Unit | ⚠️ Deferred |
| `test_action_commit_message_format_skip_ci` | `chore(audio): narrate {n} pages [skip ci]` | Unit | ✅ Automated |
| `test_action_remote_server_url_mode_uses_jobs_api` | `server-url` and `server-token` path | Unit | ✅ Automated |
| `test_action_no_voice_clips_in_site_repo` | Clips never committed | Unit | ✅ Automated |
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
| `test_studio_binds_127_0_0_1_by_default` | Loopback default | Unit | ✅ Automated |
| `test_studio_routes_require_session_token` | Missing or wrong token gets 401/403 | Unit | ✅ Automated |
| `test_studio_save_script_runs_validation` | Invalid script rejected with chunk numbers | Unit | ✅ Automated |
| `test_studio_render_chunk_returns_take_id` | Take id returned | Unit | ✅ Automated |
| `test_studio_list_takes_includes_similarity_scores` | Scores in listing | Unit | ✅ Automated |
| `test_studio_select_take_and_remaster` | Selection triggers re-master | Unit | ✅ Automated |

### 5.23 HTTP server (FR-023)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_server_post_job_returns_job_id_async` | Job accepted asynchronously | Unit | ✅ Automated |
| `test_server_job_status_endpoint_states` | queued, running, done, failed | Unit | ✅ Automated |
| `test_server_artifacts_downloadable_after_done` | MP3, VTT, manifest download | Unit | ✅ Automated |
| `test_server_bearer_token_required_when_configured` | 401 without token | Unit | ✅ Automated |
| `test_server_no_auth_when_token_unset_binds_loopback` | Safe default bind | Unit | ✅ Automated |
| `test_server_clone_request_unregistered_voice_403` | Consent enforced over HTTP | Unit | ✅ Automated |
| `test_server_ssrf_guard_applies_to_submitted_urls` | Private URLs refused | Unit | ✅ Automated |
| `it_server_job_roundtrip_with_mock_backend` | Submit, poll, download with real uvicorn | Integration | ⚠️ Deferred |

### 5.24 MCP server (FR-024)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_mcp_tools_listed_match_appendix_e` | All Appendix E tools present | Unit | ✅ Automated |
| `test_mcp_tool_input_schemas_valid_json_schema` | Schemas are valid | Unit | ✅ Automated |
| `test_mcp_tool_call_narrate_returns_manifest_summary` | Tool executes with mocks | Unit | ✅ Automated |
| `test_mcp_clone_tool_enforces_consent` | Same registry guard | Unit | ✅ Automated |
| `it_mcp_stdio_transport_list_tools` | Real stdio session lists tools | Integration | ✅ Automated |
| `it_mcp_streamable_http_transport_list_tools` | Real streamable HTTP session lists tools | Integration | ⚠️ Deferred |

### 5.25 Agent harness (Appendix K, S0-T08)

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_harness_claude_md_first_line_imports_agents_md` | First line is `@import AGENTS.md` | Unit | ⚠️ Deferred |
| `test_harness_soul_md_has_6_constraints_no_commands_or_paths` | SOUL.md rules | Unit | ⚠️ Deferred |
| `test_harness_required_skills_run_and_exit_0` | `run-tests` and `check-types` skills exit 0 | Unit | ⚠️ Deferred |
| `test_harness_no_em_dash_in_repo_text_files` | Em dash check over md, py, ts, yaml | Unit | ✅ Automated |
| `test_harness_em_dash_hook_fails_on_u2014` | Pre-commit hook rejects the character | Unit | ✅ Automated |
| `smoke_harness_narrate_fixture_skill_exits_0` | `narrate-fixture` skill runs with mocks | Smoke | ⚠️ Deferred |
| `it_harness_pi_extension_loads_and_lists_commands` | `integrations/pi` extension loads (vitest) | Integration | ✅ Automated |

### 5.26 Packaging, release, and versions

| ID | Scenario | Type | Status |
|---|---|---|---|
| `test_versions_check_exits_1_naming_mismatched_file` | `check-versions.sh` failure message | Unit | ✅ Automated |
| `test_versions_extract_changelog_prints_only_section` | `extract-changelog.sh 0.1.0` | Unit | ✅ Automated |
| `test_packaging_uv_sync_all_extras_succeeds` | `uv sync --all-extras --dev` on macOS arm64 and Linux x86_64 | Integration | ⚠️ Deferred |
| `test_packaging_wheel_contains_studio_static_and_schemas` | Built wheel includes `audio_smith/studio/static/` and schemas | Integration | ⚠️ Deferred |
| `test_packaging_third_party_licenses_covers_all_deps` | CI fails when a dependency has no entry | Unit | ⚠️ Deferred |
| `test_packaging_uv_tool_install_runs_version_and_doctor` | Clean `uv tool install .` works | Integration | ✅ Automated |
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

### 5.28 Additional automated scenarios

| ID | Scenario | Type | Status |
|---|---|---|---|
| `smoke_doctor_json_parses` | doctor json parses | Smoke | ✅ Automated |
| `test_cli_doctor_table_output_ok` | cli doctor table output ok | Unit | ✅ Automated |
| `test_cli_main_keyboard_interrupt_exits_130` | cli main keyboard interrupt exits 130 | Unit | ✅ Automated |
| `test_cli_main_maps_audio_smith_error_to_exit_code` | cli main maps audio smith error to exit code | Unit | ✅ Automated |
| `test_cli_main_unknown_command_is_usage_exit_2` | cli main unknown command is usage exit 2 | Unit | ✅ Automated |
| `test_config_cli_none_override_ignored` | config cli none override ignored | Unit | ✅ Automated |
| `test_config_cli_overrides_env` | config cli overrides env | Unit | ✅ Automated |
| `test_config_defaults_when_nothing_set` | config defaults when nothing set | Unit | ✅ Automated |
| `test_config_env_overrides_file` | config env overrides file | Unit | ✅ Automated |
| `test_config_explicit_config_path` | config explicit config path | Unit | ✅ Automated |
| `test_config_file_overrides_defaults` | config file overrides defaults | Unit | ✅ Automated |
| `test_config_invalid_toml_raises_usage_error` | config invalid toml raises usage error | Unit | ✅ Automated |
| `test_config_ollama_host_standard_env_honored` | config ollama host standard env honored | Unit | ✅ Automated |
| `test_config_redacted_dump_hides_secrets` | config redacted dump hides secrets | Unit | ✅ Automated |
| `test_config_secret_keys_in_file_ignored_with_warning` | config secret keys in file ignored with warning | Unit | ✅ Automated |
| `test_config_settings_is_pydantic_model` | config settings is pydantic model | Unit | ✅ Automated |
| `test_doctor_cache_dir_writable` | doctor cache dir writable | Unit | ✅ Automated |
| `test_doctor_check_exception_becomes_failure` | doctor check exception becomes failure | Unit | ✅ Automated |
| `test_doctor_disk_space_low_fails` | doctor disk space low fails | Unit | ✅ Automated |
| `test_doctor_ffmpeg_missing_has_hint` | doctor ffmpeg missing has hint | Unit | ✅ Automated |
| `test_doctor_ffmpeg_parse_version` | doctor ffmpeg parse version | Unit | ✅ Automated |
| `test_doctor_python_version_check_ok` | doctor python version check ok | Unit | ✅ Automated |
| `test_doctor_run_all_fails_when_required_fails` | doctor run all fails when required fails | Unit | ✅ Automated |
| `test_errors_exit_code_mapping_matches_spec` | errors exit code mapping matches spec | Unit | ✅ Automated |
| `test_errors_fetch_error_is_extract_error` | errors fetch error is extract error | Unit | ✅ Automated |
| `test_errors_problem_json_has_rfc9457_fields` | errors problem json has rfc9457 fields | Unit | ✅ Automated |
| `test_init_version_matches_package_metadata` | init version matches package metadata | Unit | ✅ Automated |
| `test_proc_run_nonzero_raises` | proc run nonzero raises | Unit | ✅ Automated |
| `test_proc_run_rejects_shell_string` | proc run rejects shell string | Unit | ✅ Automated |
| `test_proc_run_returns_stdout` | proc run returns stdout | Unit | ✅ Automated |
| `test_scripts_check_coverage_directory_prefix_aggregates` | scripts check coverage directory prefix aggregates | Unit | ✅ Automated |
| `test_scripts_check_coverage_module_under_target_fails` | scripts check coverage module under target fails | Unit | ✅ Automated |
| `test_scripts_check_coverage_overall_under_target_fails` | scripts check coverage overall under target fails | Unit | ✅ Automated |
| `test_scripts_check_versions_consistent_passes` | scripts check versions consistent passes | Unit | ✅ Automated |
| `test_scripts_em_dash_clean_file_passes` | scripts em dash clean file passes | Unit | ✅ Automated |
| `it_ollama_chat_tiny_model_returns_text` | ollama chat tiny model returns text | Integration | ✅ Automated |
| `test_api_markdown_source_extracts_blocks` | api markdown source extracts blocks | Unit | ✅ Automated |
| `test_api_markdown_to_html_closes_trailing_list` | api markdown to html closes trailing list | Unit | ✅ Automated |
| `test_api_resolve_profile_uses_settings_default` | api resolve profile uses settings default | Unit | ✅ Automated |
| `test_api_write_script_writes_blocks_and_scripts` | api write script writes blocks and scripts | Unit | ✅ Automated |
| `test_blocks_normalize_strips_emoji_and_space_before_punct` | blocks normalize strips emoji and space before punct | Unit | ✅ Automated |
| `test_blocks_to_json_uses_schema_alias` | blocks to json uses schema alias | Unit | ✅ Automated |
| `test_cache_keys_change_with_every_input` | cache keys change with every input | Unit | ✅ Automated |
| `test_cache_parse_age_forms` | cache parse age forms | Unit | ✅ Automated |
| `test_cache_rejects_traversal_addresses` | cache rejects traversal addresses | Unit | ✅ Automated |
| `test_cli_cache_info_and_prune` | cli cache info and prune | Unit | ✅ Automated |
| `test_cli_script_command_with_local_fixture` | cli script command with local fixture | Unit | ✅ Automated |
| `test_default_resolver_localhost_and_failure` | default resolver localhost and failure | Unit | ✅ Automated |
| `test_extract_blocks_verbatim_attribute_marks_block` | extract blocks verbatim attribute marks block | Unit | ✅ Automated |
| `test_extract_empty_article_raises_extract_error` | extract empty article raises extract error | Unit | ✅ Automated |
| `test_extract_list_item_skip_and_parent_attributes` | extract list item skip and parent attributes | Unit | ✅ Automated |
| `test_extract_list_item_without_paragraph_strips_number` | extract list item without paragraph strips number | Unit | ✅ Automated |
| `test_extract_metadata_title_lang_author_date` | extract metadata title lang author date | Unit | ✅ Automated |
| `test_extract_no_content_raises_extract_error` | extract no content raises extract error | Unit | ✅ Automated |
| `test_extract_parent_headings_routes_heading_tag_sections` | extract parent headings routes heading tag sections | Unit | ✅ Automated |
| `test_fetch_content_length_over_limit_rejected_early` | fetch content length over limit rejected early | Unit | ✅ Automated |
| `test_fetch_creates_and_closes_own_client` | fetch creates and closes own client | Unit | ✅ Automated |
| `test_fetch_empty_resolution_rejected` | fetch empty resolution rejected | Unit | ✅ Automated |
| `test_fetch_five_redirects_then_success` | fetch five redirects then success | Unit | ✅ Automated |
| `test_fetch_http_error_names_status` | fetch http error names status | Unit | ✅ Automated |
| `test_fetch_local_bad_extension_missing_and_oversize` | fetch local bad extension missing and oversize | Unit | ✅ Automated |
| `test_fetch_metadata_hostname_blocked` | fetch metadata hostname blocked | Unit | ✅ Automated |
| `test_fetch_network_error_raises_fetch_error` | fetch network error raises fetch error | Unit | ✅ Automated |
| `test_fetch_non_text_content_type_rejected` | fetch non text content type rejected | Unit | ✅ Automated |
| `test_fetch_pinned_request_keeps_port_and_ipv6_host_header` | fetch pinned request keeps port and ipv6 host header | Unit | ✅ Automated |
| `test_fetch_private_ip_literal_and_any_answer_blocked` | fetch private ip literal and any answer blocked | Unit | ✅ Automated |
| `test_fetch_redirect_to_non_http_scheme_blocked` | fetch redirect to non http scheme blocked | Unit | ✅ Automated |
| `test_fetch_redirect_without_location_is_not_followed` | fetch redirect without location is not followed | Unit | ✅ Automated |
| `test_fetch_timeout_raises_fetch_error` | fetch timeout raises fetch error | Unit | ✅ Automated |
| `test_fetch_total_time_budget_enforced` | fetch total time budget enforced | Unit | ✅ Automated |
| `test_fetch_unknown_or_missing_charset_falls_back_to_utf8` | fetch unknown or missing charset falls back to utf8 | Unit | ✅ Automated |
| `test_lexicon_apply_phrase_before_word` | lexicon apply phrase before word | Unit | ✅ Automated |
| `test_lexicon_invalid_file_raises` | lexicon invalid file raises | Unit | ✅ Automated |
| `test_llm_anthropic_missing_sdk_and_failure` | llm anthropic missing sdk and failure | Unit | ✅ Automated |
| `test_llm_anthropic_preflight_states` | llm anthropic preflight states | Unit | ✅ Automated |
| `test_llm_bad_replies_raise` | llm bad replies raise | Unit | ✅ Automated |
| `test_llm_check_states` | llm check states | Unit | ✅ Automated |
| `test_llm_fake_provider_queue_mode` | llm fake provider queue mode | Unit | ✅ Automated |
| `test_llm_get_provider_factory` | llm get provider factory | Unit | ✅ Automated |
| `test_llm_ollama_preflight_ok_and_model_missing` | llm ollama preflight ok and model missing | Unit | ✅ Automated |
| `test_llm_ollama_retries_5xx_then_succeeds` | llm ollama retries 5xx then succeeds | Unit | ✅ Automated |
| `test_llm_ollama_tags_malformed_means_model_missing` | llm ollama tags malformed means model missing | Unit | ✅ Automated |
| `test_llm_openai_compat_no_key_no_header_and_bad_reply` | llm openai compat no key no header and bad reply | Unit | ✅ Automated |
| `test_llm_openai_compat_preflight_cloud_and_unreachable` | llm openai compat preflight cloud and unreachable | Unit | ✅ Automated |
| `test_llm_parse_provider_rejects_invalid` | llm parse provider rejects invalid | Unit | ✅ Automated |
| `test_llm_provider_label_drops_base_url` | llm provider label drops base url | Unit | ✅ Automated |
| `test_llm_retries_exhausted_raises` | llm retries exhausted raises | Unit | ✅ Automated |
| `test_llm_strip_think_and_locality` | llm strip think and locality | Unit | ✅ Automated |
| `test_llm_unknown_provider_lists_known_kinds` | llm unknown provider lists known kinds | Unit | ✅ Automated |
| `test_paths_atomic_write_replaces_and_sets_mode` | paths atomic write replaces and sets mode | Unit | ✅ Automated |
| `test_paths_ensure_inside_blocks_traversal` | paths ensure inside blocks traversal | Unit | ✅ Automated |
| `test_paths_safe_slug_sanitizes` | paths safe slug sanitizes | Unit | ✅ Automated |
| `test_profiles_get_profile_version_pin_and_unknown` | profiles get profile version pin and unknown | Unit | ✅ Automated |
| `test_profiles_invalid_yaml_and_non_mapping_rejected` | profiles invalid yaml and non mapping rejected | Unit | ✅ Automated |
| `test_profiles_language_code_validated` | profiles language code validated | Unit | ✅ Automated |
| `test_profiles_track_reference_must_exist` | profiles track reference must exist | Unit | ✅ Automated |
| `test_script_parse_structural_errors_raise` | script parse structural errors raise | Unit | ✅ Automated |
| `test_script_plain_text_and_word_count` | script plain text and word count | Unit | ✅ Automated |
| `test_script_validate_numbering_and_no_chunks` | script validate numbering and no chunks | Unit | ✅ Automated |
| `test_script_validate_sentence_count_warning` | script validate sentence count warning | Unit | ✅ Automated |
| `test_script_validate_verbatim_ignores_terminal_punct_and_quotes` | script validate verbatim ignores terminal punct and quotes | Unit | ✅ Automated |
| `test_script_writer_prompt_carries_profile_rules` | script writer prompt carries profile rules | Unit | ✅ Automated |
| `test_script_writer_strips_think_blocks_and_fences` | script writer strips think blocks and fences | Unit | ✅ Automated |
| `test_script_writer_too_short_retries_then_warns` | script writer too short retries then warns | Unit | ✅ Automated |
| `test_script_writer_user_prompt_wraps_untrusted_content_and_track` | script writer user prompt wraps untrusted content and track | Unit | ✅ Automated |
| `test_script_verbatim_empty_signature_chunk_replaced_with_exact_text` | script verbatim empty signature chunk replaced with exact text | Unit | ✅ Automated |
| `test_script_verbatim_missing_sources_appended_signature_last` | script verbatim missing sources appended signature last | Unit | ✅ Automated |
| `test_script_verbatim_no_sources_is_identity` | script verbatim no sources is identity | Unit | ✅ Automated |
| `test_script_verbatim_paraphrased_signature_restored_in_place` | script verbatim paraphrased signature restored in place | Unit | ✅ Automated |
| `test_script_verbatim_signature_moved_to_end` | script verbatim signature moved to end | Unit | ✅ Automated |
| `test_api_render_applies_lexicon_at_synthesis_only` | api render applies lexicon at synthesis only | Unit | ✅ Automated |
| `test_api_render_default_voice_is_backend_builtin` | api render default voice is backend builtin | Unit | ✅ Automated |
| `test_api_render_noncommercial_backend_requires_flag` | api render noncommercial backend requires flag | Unit | ✅ Automated |
| `test_api_render_registered_voice_with_consent_renders` | api render registered voice with consent renders | Unit | ✅ Automated |
| `test_api_render_subset_chunks` | api render subset chunks | Unit | ✅ Automated |
| `test_apply_rate_identity_and_failure` | apply rate identity and failure | Unit | ✅ Automated |
| `test_backend_checks_failure_and_import_error` | backend checks failure and import error | Unit | ✅ Automated |
| `test_backend_checks_one_row_per_backend_default_required` | backend checks one row per backend default required | Unit | ✅ Automated |
| `test_chatterbox_builtin_voice_no_consent` | chatterbox builtin voice no consent | Unit | ✅ Automated |
| `test_chatterbox_clone_requires_consent` | chatterbox clone requires consent | Unit | ✅ Automated |
| `test_chatterbox_clone_without_reference_raises` | chatterbox clone without reference raises | Unit | ✅ Automated |
| `test_chatterbox_device_selection` | chatterbox device selection | Unit | ✅ Automated |
| `test_chatterbox_missing_package` | chatterbox missing package | Unit | ✅ Automated |
| `test_chatterbox_preflight_ok` | chatterbox preflight ok | Unit | ✅ Automated |
| `test_cli_render_mock_produces_wav_chunks` | cli render mock produces wav chunks | Unit | ✅ Automated |
| `test_cli_voice_add_errors` | cli voice add errors | Unit | ✅ Automated |
| `test_cli_voice_add_explicit_statement_and_unreadable_clip_check` | cli voice add explicit statement and unreadable clip check | Unit | ✅ Automated |
| `test_cli_voice_check_clip_problems_exit_3` | cli voice check clip problems exit 3 | Unit | ✅ Automated |
| `test_clipcheck_edge_cases` | clipcheck edge cases | Unit | ✅ Automated |
| `test_consent_enforced_from_cli_unregistered_voice_exit_8` | consent enforced from cli unregistered voice exit 8 | Unit | ✅ Automated |
| `test_consent_enforced_from_python_api_unregistered_voice` | consent enforced from python api unregistered voice | Unit | ✅ Automated |
| `test_consent_hash_mismatch_after_tamper_raises` | consent hash mismatch after tamper raises | Unit | ✅ Automated |
| `test_consent_record_edge_cases` | consent record edge cases | Unit | ✅ Automated |
| `test_doctor_default_checks_include_tts` | doctor default checks include tts | Unit | ✅ Automated |
| `test_doctor_voices_check` | doctor voices check | Unit | ✅ Automated |
| `test_get_backend_kokoro_and_chatterbox_lazy` | get backend kokoro and chatterbox lazy | Unit | ✅ Automated |
| `test_get_backend_mock_and_unknown` | get backend mock and unknown | Unit | ✅ Automated |
| `test_gpu_check` | gpu check | Unit | ✅ Automated |
| `test_is_local_host` | is local host | Unit | ✅ Automated |
| `test_kokoro_empty_audio_raises` | kokoro empty audio raises | Unit | ✅ Automated |
| `test_kokoro_lang_code_from_voice` | kokoro lang code from voice | Unit | ✅ Automated |
| `test_kokoro_preflight_clean` | kokoro preflight clean | Unit | ✅ Automated |
| `test_kokoro_preflight_espeak_missing_warning` | kokoro preflight espeak missing warning | Unit | ✅ Automated |
| `test_kokoro_preflight_missing_package` | kokoro preflight missing package | Unit | ✅ Automated |
| `test_kokoro_preflight_reports_weights_mismatch` | kokoro preflight reports weights mismatch | Unit | ✅ Automated |
| `test_kokoro_rate_passthrough` | kokoro rate passthrough | Unit | ✅ Automated |
| `test_kokoro_rejects_non_builtin_voice` | kokoro rejects non builtin voice | Unit | ✅ Automated |
| `test_kokoro_synth_concatenates_chunks` | kokoro synth concatenates chunks | Unit | ✅ Automated |
| `test_kokoro_synth_without_package_raises` | kokoro synth without package raises | Unit | ✅ Automated |
| `test_kokoro_weights_checksum` | kokoro weights checksum | Unit | ✅ Automated |
| `test_maya2_hash_derived_when_missing` | maya2 hash derived when missing | Unit | ✅ Automated |
| `test_maya2_inproc_with_fake_module` | maya2 inproc with fake module | Unit | ✅ Automated |
| `test_maya2_preflight_ok_loading_unreachable` | maya2 preflight ok loading unreachable | Unit | ✅ Automated |
| `test_maya2_registration_conflict_and_exists_are_success` | maya2 registration conflict and exists are success | Unit | ✅ Automated |
| `test_maya2_registration_failures` | maya2 registration failures | Unit | ✅ Automated |
| `test_maya2_unsupported_language_names_supported` | maya2 unsupported language names supported | Unit | ✅ Automated |
| `test_normalize_resamples_and_peaks_at_minus_1_dbfs` | normalize resamples and peaks at minus 1 dbfs | Unit | ✅ Automated |
| `test_openai_compat_invalid_wav_raises` | openai compat invalid wav raises | Unit | ✅ Automated |
| `test_openai_compat_preflight_local_and_unreachable` | openai compat preflight local and unreachable | Unit | ✅ Automated |
| `test_openai_preflight_cloud_warning_and_key` | openai preflight cloud warning and key | Unit | ✅ Automated |
| `test_pcm_duration_zero_rate` | pcm duration zero rate | Unit | ✅ Automated |
| `test_registry_maya2_and_openai_factories_delegate` | registry maya2 and openai factories delegate | Unit | ✅ Automated |
| `test_resolve_builtin_vs_cloned` | resolve builtin vs cloned | Unit | ✅ Automated |
| `test_scan_voices_reports_invalid` | scan voices reports invalid | Unit | ✅ Automated |
| `test_to_float32_int16_and_stereo` | to float32 int16 and stereo | Unit | ✅ Automated |
| `test_tts_chatterbox_rate_applied_post_synthesis` | tts chatterbox rate applied post synthesis | Unit | ✅ Automated |
| `test_tts_registry_lists_all_backends` | tts registry lists all backends | Unit | ✅ Automated |
| `test_voices_add_rejects_bad_input` | voices add rejects bad input | Unit | ✅ Automated |
| `test_voices_check_clip_problem_when_clip_degrades` | voices check clip problem when clip degrades | Unit | ✅ Automated |
| `test_voices_check_reports_clip_and_consent_problems` | voices check reports clip and consent problems | Unit | ✅ Automated |
| `test_voices_check_warns_and_fixes_broad_permissions` | voices check warns and fixes broad permissions | Unit | ✅ Automated |
| `test_voices_cli_add_list_check_remove` | voices cli add list check remove | Unit | ✅ Automated |
| `test_voices_permissions_0700_dir_0600_files` | voices permissions 0700 dir 0600 files | Unit | ✅ Automated |
| `test_cli_main_prints_code_and_violations` | cli main prints code and violations | Unit | ✅ Automated |
| `smoke_manifest_validates_schema` | manifest validates schema | Smoke | ✅ Automated |
| `smoke_unchanged_rerun_is_cached` | unchanged rerun is cached | Smoke | ✅ Automated |
| `test_api_render_mock_full_script_masters_track` | api render mock full script masters track | Unit | ✅ Automated |
| `test_api_render_settings_default_backend_mock` | api render settings default backend mock | Unit | ✅ Automated |
| `test_assemble_empty_and_short_units` | assemble empty and short units | Unit | ✅ Automated |
| `test_assemble_no_clicks_around_silence` | assemble no clicks around silence | Unit | ✅ Automated |
| `test_cache_unchanged_rerun_under_2s` | cache unchanged rerun under 2s | Unit | ✅ Automated |
| `test_cli_main_prints_code_and_violations` | cli main prints code and violations | Unit | ✅ Automated |
| `test_cli_run_mock_end_to_end` | cli run mock end to end | Unit | ✅ Automated |
| `test_errors_synthesis_error_retryable_flag` | errors synthesis error retryable flag | Unit | ✅ Automated |
| `test_has_deesser_detection_and_failure` | has deesser detection and failure | Unit | ✅ Automated |
| `test_http_get_bytes_pins_ip_follows_redirect_and_blocks_private` | http get bytes pins ip follows redirect and blocks private | Unit | ✅ Automated |
| `test_http_get_bytes_redirect_loop_and_network_error` | http get bytes redirect loop and network error | Unit | ✅ Automated |
| `test_manifest_has_no_secrets_clips_or_consent` | manifest has no secrets clips or consent | Unit | ✅ Automated |
| `test_manifest_rejects_bad_input` | manifest rejects bad input | Unit | ✅ Automated |
| `test_manifest_round_trip_and_fields` | manifest round trip and fields | Unit | ✅ Automated |
| `test_manifest_schemas_published_are_current` | manifest schemas published are current | Unit | ✅ Automated |
| `test_master_failure_has_stderr_tail_and_hint` | master failure has stderr tail and hint | Unit | ✅ Automated |
| `test_master_graph_variants_and_fallback_deesser` | master graph variants and fallback deesser | Unit | ✅ Automated |
| `test_master_timeout_and_parse_errors` | master timeout and parse errors | Unit | ✅ Automated |
| `test_measure_rms_dbfs` | measure rms dbfs | Unit | ✅ Automated |
| `test_narrate_approve_invalid_edit_rejected` | narrate approve invalid edit rejected | Unit | ✅ Automated |
| `test_narrate_approve_uses_edited_script` | narrate approve uses edited script | Unit | ✅ Automated |
| `test_narrate_dry_run_plans_without_audio` | narrate dry run plans without audio | Unit | ✅ Automated |
| `test_parent_track_rendered_separately_never_in_child_track` | parent track rendered separately never in child track | Unit | ✅ Automated |
| `test_peaks_edge_cases_and_attr` | peaks edge cases and attr | Unit | ✅ Automated |
| `test_peaks_normalized_28_bars` | peaks normalized 28 bars | Unit | ✅ Automated |
| `test_planner_oversized_sentence_split_at_comma_with_warning` | planner oversized sentence split at comma with warning | Unit | ✅ Automated |
| `test_planner_oversized_word_without_break_still_bounded` | planner oversized word without break still bounded | Unit | ✅ Automated |
| `test_planner_pause_only_chunk_extends_previous_unit` | planner pause only chunk extends previous unit | Unit | ✅ Automated |
| `test_proc_run_capture_returns_both_streams` | proc run capture returns both streams | Unit | ✅ Automated |
| `test_python_api_package_level_narrate_exposed` | python api package level narrate exposed | Unit | ✅ Automated |
| `test_qa_cached_unit_without_score_is_rescored` | qa cached unit without score is rescored | Unit | ✅ Automated |
| `test_qa_cosine` | qa cosine | Unit | ✅ Automated |
| `test_qa_from_reference_clip_embeds_once` | qa from reference clip embeds once | Unit | ✅ Automated |
| `test_qa_good_first_take_not_rerendered` | qa good first take not rerendered | Unit | ✅ Automated |
| `test_qa_resemblyzer_embedder_uses_encoder` | qa resemblyzer embedder uses encoder | Unit | ✅ Automated |
| `test_qa_takes_cached_separately_and_scores_not_recomputed` | qa takes cached separately and scores not recomputed | Unit | ✅ Automated |
| `test_resolve_sting_builtin_relative_and_guards` | resolve sting builtin relative and guards | Unit | ✅ Automated |
| `test_rich_progress_callback_runs_to_completion` | rich progress callback runs to completion | Unit | ✅ Automated |
| `test_runner_consent_error_not_retried` | runner consent error not retried | Unit | ✅ Automated |
| `test_runner_corrupt_cache_entry_is_resynthesized` | runner corrupt cache entry is resynthesized | Unit | ✅ Automated |
| `test_runner_failure_keeps_completed_units_cached` | runner failure keeps completed units cached | Unit | ✅ Automated |
| `test_runner_non_retryable_synthesis_error_fails_fast` | runner non retryable synthesis error fails fast | Unit | ✅ Automated |
| `test_runner_progress_events_reported` | runner progress events reported | Unit | ✅ Automated |
| `test_script_verbatim_empty_signature_chunk_replaced_with_exact_text` | script verbatim empty signature chunk replaced with exact text | Unit | ✅ Automated |
| `test_script_verbatim_missing_sources_appended_signature_last` | script verbatim missing sources appended signature last | Unit | ✅ Automated |
| `test_script_verbatim_no_sources_is_identity` | script verbatim no sources is identity | Unit | ✅ Automated |
| `test_script_verbatim_paraphrased_signature_restored_in_place` | script verbatim paraphrased signature restored in place | Unit | ✅ Automated |
| `test_script_verbatim_signature_moved_to_end` | script verbatim signature moved to end | Unit | ✅ Automated |
| `test_smoke_run_mock_outputs_exist_and_manifest_validates` | smoke run mock outputs exist and manifest validates | Unit | ✅ Automated |
| `test_stings_generate_script_is_deterministic` | stings generate script is deterministic | Unit | ✅ Automated |
| `test_tags_cover_fetch_errors_are_swallowed` | tags cover fetch errors are swallowed | Unit | ✅ Automated |
| `test_vtt_abbreviations_stay_intact` | vtt abbreviations stay intact | Unit | ✅ Automated |
| `test_vtt_cues_monotonic_and_non_overlapping` | vtt cues monotonic and non overlapping | Unit | ✅ Automated |
| `test_vtt_empty_text_yields_no_cues_and_write` | vtt empty text yields no cues and write | Unit | ✅ Automated |
| `test_vtt_escapes_markup` | vtt escapes markup | Unit | ✅ Automated |
| `test_vtt_long_sentence_split_at_comma` | vtt long sentence split at comma | Unit | ✅ Automated |
| `test_action_changed_files_mapped_to_urls` | action changed files mapped to urls | Unit | ✅ Automated |
| `test_action_command_construction_run_then_inject` | action command construction run then inject | Unit | ✅ Automated |
| `test_action_failed_page_does_not_stop_the_rest` | action failed page does not stop the rest | Unit | ✅ Automated |
| `test_action_falls_back_to_all_files` | action falls back to all files | Unit | ✅ Automated |
| `test_action_noop_when_nothing_changed` | action noop when nothing changed | Unit | ✅ Automated |
| `test_action_slug_matches_package_slug` | action slug matches package slug | Unit | ✅ Automated |
| `test_embed_copy_player_script_none_when_not_built` | embed copy player script none when not built | Unit | ✅ Automated |
| `test_embed_escapes_hostile_label` | embed escapes hostile label | Unit | ✅ Automated |
| `test_embed_excludes_parent_track` | embed excludes parent track | Unit | ✅ Automated |
| `test_embed_find_player_returns_path_or_none` | embed find player returns path or none | Unit | ✅ Automated |
| `test_embed_media_base_prefix_and_write` | embed media base prefix and write | Unit | ✅ Automated |
| `test_embed_no_captions_omits_track_and_attr` | embed no captions omits track and attr | Unit | ✅ Automated |
| `test_embed_no_main_track_raises` | embed no main track raises | Unit | ✅ Automated |
| `test_embed_works_without_js` | embed works without js | Unit | ✅ Automated |
| `test_examples_letters_to_a_child_profile_override_loads` | examples letters to a child profile override loads | Unit | ✅ Automated |
| `test_inject_bad_markers_raise` | inject bad markers raise | Unit | ✅ Automated |
| `test_inject_cli_rejects_bad_size` | inject cli rejects bad size | Unit | ✅ Automated |
| `test_inject_cli_writes_then_reports_unchanged` | inject cli writes then reports unchanged | Unit | ✅ Automated |
| `test_inject_file_crlf_bytes_preserved` | inject file crlf bytes preserved | Unit | ✅ Automated |
| `test_inject_preserves_crlf` | inject preserves crlf | Unit | ✅ Automated |
| `test_inject_selector_not_found_or_bad` | inject selector not found or bad | Unit | ✅ Automated |
| `test_inject_self_closing_and_unclosed_target` | inject self closing and unclosed target | Unit | ✅ Automated |
| `test_site_cli_exit_code_6_when_any_page_failed` | site cli exit code 6 when any page failed | Unit | ✅ Automated |
| `test_site_inject_root_rejects_path_traversal` | site inject root rejects path traversal | Unit | ✅ Automated |
| `test_site_missing_local_file_is_a_failed_row` | site missing local file is a failed row | Unit | ✅ Automated |
| `test_site_shares_one_backend_instance_across_pages` | site shares one backend instance across pages | Unit | ✅ Automated |
| `test_translate_alignment_detects_heading_changes` | translate alignment detects heading changes | Unit | ✅ Automated |
| `test_translate_retry_fixes_dropped_pause` | translate retry fixes dropped pause | Unit | ✅ Automated |
| `test_unified_diff_labels_path` | unified diff labels path | Unit | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `test_narrate_embed_options_from_settings` | narrate embed options from settings | Unit | ✅ Automated |
| `test_narrate_inject_writes_markers_once` | narrate inject writes markers once | Unit | ✅ Automated |
| `test_player_adopts_slotted_audio_and_hides_native_controls` | player adopts slotted audio and hides native controls | Unit | ✅ Automated |
| `test_player_attributes_invalid_tracks_json_falls_back` | player attributes invalid tracks json falls back | Unit | ✅ Automated |
| `test_player_captions_failure_hides_toggle_without_blocking_audio` | player captions failure hides toggle without blocking audio | Unit | ✅ Automated |
| `test_player_captions_fetch_parses_body` | player captions fetch parses body | Unit | ✅ Automated |
| `test_player_captions_fetch_rejects_on_http_error` | player captions fetch rejects on http error | Unit | ✅ Automated |
| `test_player_captions_ignore_malformed_blocks` | player captions ignore malformed blocks | Unit | ✅ Automated |
| `test_player_captions_labels_overridable` | player captions labels overridable | Unit | ✅ Automated |
| `test_player_captions_parse_webvtt_cues` | player captions parse webvtt cues | Unit | ✅ Automated |
| `test_player_captions_toggle_shows_cue_and_persists` | player captions toggle shows cue and persists | Unit | ✅ Automated |
| `test_player_creates_audio_when_none_slotted` | player creates audio when none slotted | Unit | ✅ Automated |
| `test_player_debug_attribute_logs_state_transitions` | player debug attribute logs state transitions | Unit | ✅ Automated |
| `test_player_disconnect_saves_position_and_cleans_up` | player disconnect saves position and cleans up | Unit | ✅ Automated |
| `test_player_download_is_opt_in` | player download is opt in | Unit | ✅ Automated |
| `test_player_error_state_has_retry_and_custom_copy` | player error state has retry and custom copy | Unit | ✅ Automated |
| `test_player_error_while_going_offline_switches_to_offline` | player error while going offline switches to offline | Unit | ✅ Automated |
| `test_player_keyboard_arrows_seek_5s_and_clamp` | player keyboard arrows seek 5s and clamp | Unit | ✅ Automated |
| `test_player_keyboard_c_and_l_ignored_without_captions_or_tracks` | player keyboard c and l ignored without captions or tracks | Unit | ✅ Automated |
| `test_player_keyboard_ignores_modifiers_and_unknown_keys` | player keyboard ignores modifiers and unknown keys | Unit | ✅ Automated |
| `test_player_keyboard_k_and_space_toggle` | player keyboard k and space toggle | Unit | ✅ Automated |
| `test_player_keyboard_space_on_button_left_to_native_click` | player keyboard space on button left to native click | Unit | ✅ Automated |
| `test_player_label_default_and_override` | player label default and override | Unit | ✅ Automated |
| `test_player_language_switch_keeps_relative_position_and_playing` | player language switch keeps relative position and playing | Unit | ✅ Automated |
| `test_player_language_switch_restarts_when_durations_differ` | player language switch restarts when durations differ | Unit | ✅ Automated |
| `test_player_language_toggle_only_when_multiple_tracks` | player language toggle only when multiple tracks | Unit | ✅ Automated |
| `test_player_loading_text_only_after_300ms` | player loading text only after 300ms | Unit | ✅ Automated |
| `test_player_localstorage_blocked_still_works` | player localstorage blocked still works | Unit | ✅ Automated |
| `test_player_media_session_metadata_set` | player media session metadata set | Unit | ✅ Automated |
| `test_player_no_autoplay_on_connect` | player no autoplay on connect | Unit | ✅ Automated |
| `test_player_no_captions_attribute_hides_toggle` | player no captions attribute hides toggle | Unit | ✅ Automated |
| `test_player_offline_state_disables_retry_until_online` | player offline state disables retry until online | Unit | ✅ Automated |
| `test_player_play_rejection_not_allowed_returns_to_idle` | player play rejection not allowed returns to idle | Unit | ✅ Automated |
| `test_player_remembers_position_per_src` | player remembers position per src | Unit | ✅ Automated |
| `test_player_replay_after_end_restarts_at_zero` | player replay after end restarts at zero | Unit | ✅ Automated |
| `test_player_size_kid_sets_variant` | player size kid sets variant | Unit | ✅ Automated |
| `test_player_state_idle_to_playing_to_paused_to_ended` | player state idle to playing to paused to ended | Unit | ✅ Automated |
| `test_player_theme_attribute_reaches_stylesheet` | player theme attribute reaches stylesheet | Unit | ✅ Automated |
| `test_player_time_format` | player time format | Unit | ✅ Automated |
| `test_player_waveform_bar_height_range` | player waveform bar height range | Unit | ✅ Automated |
| `test_player_waveform_bars_left_of_playhead_filled` | player waveform bars left of playhead filled | Unit | ✅ Automated |
| `test_player_waveform_click_seeks` | player waveform click seeks | Unit | ✅ Automated |
| `test_player_waveform_ended_fills_all_no_head` | player waveform ended fills all no head | Unit | ✅ Automated |
| `test_player_waveform_flat_fallback_without_peaks` | player waveform flat fallback without peaks | Unit | ✅ Automated |
| `test_player_waveform_parse_peaks_malformed_returns_null` | player waveform parse peaks malformed returns null | Unit | ✅ Automated |
| `test_player_waveform_parse_peaks_valid` | player waveform parse peaks valid | Unit | ✅ Automated |
| `test_player_waveform_slider_semantics` | player waveform slider semantics | Unit | ✅ Automated |
| `test_studio_api_media_fetched_with_token_and_cached` | studio api media fetched with token and cached | Unit | ✅ Automated |
| `test_studio_api_non_json_error_and_network_failure` | studio api non json error and network failure | Unit | ✅ Automated |
| `test_studio_api_problem_json_error` | studio api problem json error | Unit | ✅ Automated |
| `test_studio_api_request_shapes` | studio api request shapes | Unit | ✅ Automated |
| `test_studio_api_sends_token_header_on_every_request` | studio api sends token header on every request | Unit | ✅ Automated |
| `test_studio_approve_persists_in_manifest` | studio approve persists in manifest | Unit | ✅ Automated |
| `test_studio_approve_without_manifest_is_400` | studio approve without manifest is 400 | Unit | ✅ Automated |
| `test_studio_cli_explains_missing_server_extra` | studio cli explains missing server extra | Unit | ✅ Automated |
| `test_studio_cli_opens_browser_unless_no_open` | studio cli opens browser unless no open | Unit | ✅ Automated |
| `test_studio_failed_render_marks_chunk_failed` | studio failed render marks chunk failed | Unit | ✅ Automated |
| `test_studio_inject_diff_preview_before_write` | studio inject diff preview before write | Unit | ✅ Automated |
| `test_studio_inject_rejects_paths_outside_project_root` | studio inject rejects paths outside project root | Unit | ✅ Automated |
| `test_studio_insert_emphasis_wraps_selection` | studio insert emphasis wraps selection | Unit | ✅ Automated |
| `test_studio_insert_marker_at_caret` | studio insert marker at caret | Unit | ✅ Automated |
| `test_studio_lists_and_loads_projects` | studio lists and loads projects | Unit | ✅ Automated |
| `test_studio_media_rejects_traversal_and_unknown_types` | studio media rejects traversal and unknown types | Unit | ✅ Automated |
| `test_studio_player_bundle_route` | studio player bundle route | Unit | ✅ Automated |
| `test_studio_queue_fail_and_clear` | studio queue fail and clear | Unit | ✅ Automated |
| `test_studio_queue_is_sequential_and_dedupes` | studio queue is sequential and dedupes | Unit | ✅ Automated |
| `test_studio_reducer_edit_marks_draft_and_reverts` | studio reducer edit marks draft and reverts | Unit | ✅ Automated |
| `test_studio_reducer_filter_and_counts` | studio reducer filter and counts | Unit | ✅ Automated |
| `test_studio_reducer_loaded_selects_first` | studio reducer loaded selects first | Unit | ✅ Automated |
| `test_studio_reducer_select_and_move` | studio reducer select and move | Unit | ✅ Automated |
| `test_studio_reducer_take_added_and_kept` | studio reducer take added and kept | Unit | ✅ Automated |
| `test_studio_reducer_track_and_approved` | studio reducer track and approved | Unit | ✅ Automated |
| `test_studio_remaster_falls_back_to_fresh_render_for_stale_selection` | studio remaster falls back to fresh render for stale selection | Unit | ✅ Automated |
| `test_studio_render_unknown_chunk_404` | studio render unknown chunk 404 | Unit | ✅ Automated |
| `test_studio_render_unregistered_cloned_voice_is_403_consent` | studio render unregistered cloned voice is 403 consent | Unit | ✅ Automated |
| `test_studio_save_valid_edit_marks_chunk_stale` | studio save valid edit marks chunk stale | Unit | ✅ Automated |
| `test_studio_security_headers_and_placeholder_index` | studio security headers and placeholder index | Unit | ✅ Automated |
| `test_studio_serves_built_static_files` | studio serves built static files | Unit | ✅ Automated |
| `test_studio_toasts_add_dismiss` | studio toasts add dismiss | Unit | ✅ Automated |
| `test_studio_token_stripped_from_url` | studio token stripped from url | Unit | ✅ Automated |
| `test_studio_unknown_project_is_404_problem` | studio unknown project is 404 problem | Unit | ✅ Automated |
| `test_studio_validate_accepts_allowed_markers` | studio validate accepts allowed markers | Unit | ✅ Automated |
| `test_studio_validate_empty_and_stray` | studio validate empty and stray | Unit | ✅ Automated |
| `test_studio_validate_max_chunk_chars` | studio validate max chunk chars | Unit | ✅ Automated |
| `test_studio_validate_pause_range` | studio validate pause range | Unit | ✅ Automated |
| `test_studio_validate_rejects_unknown_marker` | studio validate rejects unknown marker | Unit | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `regression_logs_redact_secret_named_keys_in_json_output` | logs redact secret named keys in json output | Regression | ✅ Automated |
| `test_docs_cli_reference_is_current` | docs cli reference is current | Unit | ✅ Automated |
| `test_docs_every_cli_flag_documented` | docs every cli flag documented | Unit | ✅ Automated |
| `test_docs_every_command_documented` | docs every command documented | Unit | ✅ Automated |
| `test_extract_fuzz_generated_html_trees_never_crash` | extract fuzz generated html trees never crash | Unit | ✅ Automated |
| `test_fetch_mixed_public_and_private_answers_rejected_whole` | fetch mixed public and private answers rejected whole | Unit | ✅ Automated |
| `test_fetch_rebinding_second_resolution_never_reaches_private_ip` | fetch rebinding second resolution never reaches private ip | Unit | ✅ Automated |
| `test_licenses_allowlisted_package_passes_denylist` | licenses allowlisted package passes denylist | Unit | ✅ Automated |
| `test_licenses_committed_file_has_required_sections` | licenses committed file has required sections | Unit | ✅ Automated |
| `test_licenses_denylist_blocks_agpl_and_gpl3_but_not_lgpl_or_gpl2` | licenses denylist blocks agpl and gpl3 but not lgpl or gpl2 | Unit | ✅ Automated |
| `test_licenses_new_dependency_without_entry_fails` | licenses new dependency without entry fails | Unit | ✅ Automated |
| `test_licenses_normalize_license_cases` | licenses normalize license cases | Unit | ✅ Automated |
| `test_licenses_npm_ls_fallback_reads_manifest` | licenses npm ls fallback reads manifest | Unit | ✅ Automated |
| `test_licenses_override_applies_only_to_unknown_metadata` | licenses override applies only to unknown metadata | Unit | ✅ Automated |
| `test_licenses_parse_license_checker_drops_own_packages` | licenses parse license checker drops own packages | Unit | ✅ Automated |
| `test_licenses_parse_pip_filters_to_runtime_and_normalizes` | licenses parse pip filters to runtime and normalizes | Unit | ✅ Automated |
| `test_licenses_replace_section_preserves_hand_written_sections` | licenses replace section preserves hand written sections | Unit | ✅ Automated |
| `test_licenses_unknown_license_fails_even_with_entry` | licenses unknown license fails even with entry | Unit | ✅ Automated |
| `test_logging_deeply_nested_input_is_bounded` | logging deeply nested input is bounded | Unit | ✅ Automated |
| `test_logging_exception_text_does_not_leak_through_redacted_keys` | logging exception text does not leak through redacted keys | Unit | ✅ Automated |
| `test_logging_json_format_goes_to_stderr_and_redacts` | logging json format goes to stderr and redacts | Unit | ✅ Automated |
| `test_logging_leaves_innocent_values_alone` | logging leaves innocent values alone | Unit | ✅ Automated |
| `test_logging_pretty_format_redacts_and_respects_level` | logging pretty format redacts and respects level | Unit | ✅ Automated |
| `test_logging_redaction_runs_before_renderer` | logging redaction runs before renderer | Unit | ✅ Automated |
| `test_logging_redacts_nested_and_listed_values_and_secretstr` | logging redacts nested and listed values and secretstr | Unit | ✅ Automated |
| `test_logging_redacts_secret_named_keys` | logging redacts secret named keys | Unit | ✅ Automated |
| `test_tags_write_failure_raises_mastering_error` | tags write failure raises mastering error | Unit | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `it_mcp_stdio_narrate_with_mocks` | mcp stdio narrate with mocks | Integration | ✅ Automated |
| `test_cli_run_server_flag` | cli run server flag | Unit | ✅ Automated |
| `test_mcp_bearer_auth_rejects_and_accepts` | mcp bearer auth rejects and accepts | Unit | ✅ Automated |
| `test_mcp_catalog_tools` | mcp catalog tools | Unit | ✅ Automated |
| `test_mcp_cli_rejects_unknown_transport` | mcp cli rejects unknown transport | Unit | ✅ Automated |
| `test_mcp_http_non_loopback_requires_token` | mcp http non loopback requires token | Unit | ✅ Automated |
| `test_mcp_inject_path_outside_working_directory_refused` | mcp inject path outside working directory refused | Unit | ✅ Automated |
| `test_mcp_invalid_input_becomes_usage_tool_error` | mcp invalid input becomes usage tool error | Unit | ✅ Automated |
| `test_mcp_monotonic_progress_skips_repeats_and_missing_context` | mcp monotonic progress skips repeats and missing context | Unit | ✅ Automated |
| `test_mcp_narrate_progress_is_monotonic` | mcp narrate progress is monotonic | Unit | ✅ Automated |
| `test_mcp_recommend_backend_fallback_to_mock` | mcp recommend backend fallback to mock | Unit | ✅ Automated |
| `test_mcp_recommend_requires_input` | mcp recommend requires input | Unit | ✅ Automated |
| `test_mcp_recommend_rules` | mcp recommend rules | Unit | ✅ Automated |
| `test_mcp_render_script_outside_allowed_dirs_refused` | mcp render script outside allowed dirs refused | Unit | ✅ Automated |
| `test_mcp_runtime_defaults_to_empty_env` | mcp runtime defaults to empty env | Unit | ✅ Automated |
| `test_mcp_script_then_render_chunks_and_full` | mcp script then render chunks and full | Unit | ✅ Automated |
| `test_remote_local_file_source_rejected` | remote local file source rejected | Unit | ✅ Automated |
| `test_remote_run_downloads_artifacts_from_local_server` | remote run downloads artifacts from local server | Unit | ✅ Automated |
| `test_remote_run_inject_locally` | remote run inject locally | Unit | ✅ Automated |
| `test_remote_wrong_token_is_usage_error` | remote wrong token is usage error | Unit | ✅ Automated |
| `test_server_catalog_endpoints` | server catalog endpoints | Unit | ✅ Automated |
| `test_server_concurrent_jobs_run_in_submission_order` | server concurrent jobs run in submission order | Unit | ✅ Automated |
| `test_server_cors_disabled_by_default_and_allowlist` | server cors disabled by default and allowlist | Unit | ✅ Automated |
| `test_server_fetch_error_becomes_failed_job` | server fetch error becomes failed job | Unit | ✅ Automated |
| `test_server_file_path_traversal_rejected` | server file path traversal rejected | Unit | ✅ Automated |
| `test_server_job_survives_restart` | server job survives restart | Unit | ✅ Automated |
| `test_server_missing_bearer_returns_401_problem_json` | server missing bearer returns 401 problem json | Unit | ✅ Automated |
| `test_server_non_localhost_bind_requires_token` | server non localhost bind requires token | Unit | ✅ Automated |
| `test_server_problem_json_shapes` | server problem json shapes | Unit | ✅ Automated |
| `test_server_progress_reported_per_stage` | server progress reported per stage | Unit | ✅ Automated |
| `test_server_rate_limit_returns_429` | server rate limit returns 429 | Unit | ✅ Automated |
| `test_server_rate_limit_window_slides` | server rate limit window slides | Unit | ✅ Automated |
| `test_server_readyz_flips_when_backend_down` | server readyz flips when backend down | Unit | ✅ Automated |
| `test_server_readyz_reports_missing_ffmpeg` | server readyz reports missing ffmpeg | Unit | ✅ Automated |
| `test_server_requeued_jobs_run_after_restart` | server requeued jobs run after restart | Unit | ✅ Automated |
| `test_server_scripts_and_render_roundtrip` | server scripts and render roundtrip | Unit | ✅ Automated |
| `test_server_serve_command_needs_server_extra_hint` | server serve command needs server extra hint | Unit | ✅ Automated |
| `test_server_serve_command_starts_uvicorn` | server serve command starts uvicorn | Unit | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `it_harness_claude_code_mcp_add_command_lists_tools` | harness claude code mcp add command lists tools | Integration | ✅ Automated |
| `it_harness_goose_toolkit_lists_tools` | harness goose toolkit lists tools | Integration | ✅ Automated |
| `it_harness_opencode_config_lists_tools` | harness opencode config lists tools | Integration | ✅ Automated |
| `test_app_dockerfiles_are_non_root_with_serve_entrypoint` | app dockerfiles are non root with serve entrypoint | Unit | ✅ Automated |
| `test_chart_app_version_equals_pyproject_and_chart_version_is_plain_semver` | chart app version equals pyproject and chart version is plain semver | Unit | ✅ Automated |
| `test_compose_local_cpu_profile_has_no_gpu_or_maya` | compose local cpu profile has no gpu or maya | Unit | ✅ Automated |
| `test_compose_local_requires_token_and_localhost_only` | compose local requires token and localhost only | Unit | ✅ Automated |
| `test_compose_maya2_uses_port_8080` | compose maya2 uses port 8080 | Unit | ✅ Automated |
| `test_helm_openstoke_values_use_cdi_without_gpu_requests` | helm openstoke values use cdi without gpu requests | Unit | ✅ Automated |
| `test_versions_check_ignores_chart_version_but_checks_app_version` | versions check ignores chart version but checks app version | Unit | ✅ Automated |
| `test_compose_prod_images_pinned_by_digest` | compose prod images pinned by digest | Unit | ✅ Automated |
| `test_compose_prod_internal_network_and_read_only` | compose prod internal network and read only | Unit | ✅ Automated |
| `test_compose_prod_no_published_ports_for_internal_services` | compose prod no published ports for internal services | Unit | ✅ Automated |
| `test_compose_prod_requires_token` | compose prod requires token | Unit | ✅ Automated |
| `test_harness_agent_skills_have_frontmatter_and_runner` | harness agent skills have frontmatter and runner | Unit | ✅ Automated |
| `test_harness_claude_code_skill_frontmatter_valid` | harness claude code skill frontmatter valid | Unit | ✅ Automated |
| `test_harness_pyproject_mcp_extra_present` | harness pyproject mcp extra present | Unit | ✅ Automated |
| `test_helm_ci_values_use_mock_backend_without_gpu_services` | helm ci values use mock backend without gpu services | Unit | ✅ Automated |
| `test_helm_k3s_values_use_nvidia_runtime` | helm k3s values use nvidia runtime | Unit | ✅ Automated |
| `test_helm_maya2_template_uses_port_8080_and_gpu` | helm maya2 template uses port 8080 and gpu | Unit | ✅ Automated |
| `test_helm_values_safe_defaults` | helm values safe defaults | Unit | ✅ Automated |
| `test_maya2_dockerfile_pinned_and_loopback_by_default` | maya2 dockerfile pinned and loopback by default | Unit | ✅ Automated |
| `test_pi_client_unreachable_and_unauthorized` | pi client unreachable and unauthorized | Unit | ✅ Automated |
| `test_pi_config_from_env_and_overrides` | pi config from env and overrides | Unit | ✅ Automated |
| `test_pi_context_hook_fails_soft_when_server_down` | pi context hook fails soft when server down | Unit | ✅ Automated |
| `test_pi_context_hook_lists_voices_and_profiles` | pi context hook lists voices and profiles | Unit | ✅ Automated |
| `test_pi_list_and_status_tools` | pi list and status tools | Unit | ✅ Automated |
| `test_pi_narrate_command_reports_failure` | pi narrate command reports failure | Unit | ✅ Automated |
| `test_pi_narrate_command_streams_progress` | pi narrate command streams progress | Unit | ✅ Automated |
| `test_pi_narrate_tool_streams_on_update` | pi narrate tool streams on update | Unit | ✅ Automated |
| `test_pi_problem_json_maps_to_readable_error` | pi problem json maps to readable error | Unit | ✅ Automated |
| `test_pi_schemas_match_mcp_tools` | pi schemas match mcp tools | Unit | ✅ Automated |
| `test_pi_voices_and_status_commands` | pi voices and status commands | Unit | ✅ Automated |
| `test_pi_wait_for_job_aborts_with_signal` | pi wait for job aborts with signal | Unit | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `regression_cli_never_imports_click_directly` | cli never imports click directly | Regression | ✅ Automated |
| `e2e_US006_player_axe_core_dark_error_state_zero_violations` | US006 player axe core dark error state zero violations | E2E | ✅ Automated |
| `e2e_US006_player_axe_core_zero_violations` | US006 player axe core zero violations | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_arrows_seek_5s` | US006 player keyboard arrows seek 5s | E2E | ✅ Automated |
| `e2e_US006_player_keyboard_play_pause` | US006 player keyboard play pause | E2E | ✅ Automated |
| `e2e_US006_player_kid_size_variant_renders` | US006 player kid size variant renders | E2E | ✅ Automated |
| `e2e_US006_player_language_toggle_switches_track` | US006 player language toggle switches track | E2E | ✅ Automated |
| `e2e_US006_player_media_session_metadata_set` | US006 player media session metadata set | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_native_audio_plays` | US006 player no js fallback native audio plays | E2E | ✅ Automated |
| `e2e_US006_player_no_js_fallback_plays` | US006 player no js fallback plays | E2E | ✅ Automated |
| `e2e_US006_player_reduced_motion_disables_breathing` | US006 player reduced motion disables breathing | E2E | ✅ Automated |
| `e2e_US006_player_remembers_position_per_src` | US006 player remembers position per src | E2E | ✅ Automated |
| `e2e_US006_player_storage_blocked_still_plays` | US006 player storage blocked still plays | E2E | ✅ Automated |
| `e2e_US006_player_theme_auto_light_dark` | US006 player theme auto light dark | E2E | ✅ Automated |
| `e2e_US012_player_captions_toggle` | US012 player captions toggle | E2E | ✅ Automated |
| `e2e_US017_studio_approve_persists_in_manifest` | US017 studio approve persists in manifest | E2E | ✅ Automated |
| `e2e_US017_studio_compare_takes_keep_best` | US017 studio compare takes keep best | E2E | ✅ Automated |
| `e2e_US017_studio_edit_validate_save_chunk` | US017 studio edit validate save chunk | E2E | ✅ Automated |
| `e2e_US017_studio_inject_diff_preview_before_write` | US017 studio inject diff preview before write | E2E | ✅ Automated |
| `e2e_US017_studio_marker_autocomplete_pause` | US017 studio marker autocomplete pause | E2E | ✅ Automated |
| `e2e_US017_studio_zero_external_requests` | US017 studio zero external requests | E2E | ✅ Automated |
| `regression_player_resume_when_metadata_loaded_before_upgrade` | player resume when metadata loaded before upgrade | Regression | ✅ Automated |

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
