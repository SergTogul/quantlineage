"""Backend-owned data-source identity labels for UI badges."""

from app.market.history.data_mode import data_source_label


def test_synthetic_replay_label_uses_dataset_identity() -> None:
    assert (
        data_source_label("demo-multi-factor-history", "v1")
        == "Synthetic replay · demo-multi-factor-history/v1"
    )


def test_public_eod_label_uses_real_public_prefix() -> None:
    assert data_source_label("real:public:wave-a", "deadbeef") == (
        "Public EOD · real:public:wave-a/deadbeef"
    )


def test_missing_dataset_id_returns_none() -> None:
    assert data_source_label(None, "v1") is None
    assert data_source_label("", "v1") is None
