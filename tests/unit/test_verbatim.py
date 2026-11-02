from audio_smith.script.markdown import Chunk
from audio_smith.script.verbatim import enforce_verbatim

SIG = "Your calm spot in every storm, Dad"


def _c(*texts: str, verbatim: tuple[int, ...] = ()) -> list[Chunk]:
    return [Chunk(number=i, text=t, verbatim=i in verbatim) for i, t in enumerate(texts, 1)]


def test_script_verbatim_empty_signature_chunk_replaced_with_exact_text() -> None:
    out = enforce_verbatim(_c("Hello there. Bye.", "", verbatim=(2,)), [SIG], SIG)
    assert [(c.number, c.text, c.verbatim) for c in out] == [(1, "Hello there. Bye.", False), (2, SIG, True)]


def test_script_verbatim_paraphrased_signature_restored_in_place() -> None:
    out = enforce_verbatim(_c("Hi. Ok.", "Your calm spot in every single storm, love Dad"), [SIG], SIG)
    assert out[-1].text == SIG and out[-1].verbatim and len(out) == 2


def test_script_verbatim_missing_sources_appended_signature_last() -> None:
    quote = "Chaos is where new things are made."
    out = enforce_verbatim(_c("Completely different words here. Yes."), [quote, SIG], SIG)
    assert [c.text for c in out[-2:]] == [quote, SIG]
    assert all(c.verbatim for c in out[-2:])


def test_script_verbatim_signature_moved_to_end() -> None:
    out = enforce_verbatim(_c(SIG, "After the sign-off. More words.", verbatim=(1,)), [SIG], SIG)
    assert out[-1].text == SIG and [c.number for c in out] == [1, 2]


def test_script_verbatim_no_sources_is_identity() -> None:
    chunks = _c("A. B.", "C. D.")
    assert enforce_verbatim(chunks, [], None) == chunks
