import pytest


torch = pytest.importorskip("torch")

from models import create_model, list_models


@pytest.mark.parametrize(
    ("model_name", "in_channels"),
    [
        ("unet3d", 1),
        ("sdf_refine_unet", 9),
    ],
)
def test_model_factory_cpu_forward(model_name, in_channels):
    torch.set_num_threads(1)
    model = create_model(model_name, base_filters=2)
    model.eval()

    x = torch.randn(1, in_channels, 9, 11, 13)
    with torch.inference_mode():
        output = model(x)

    assert output.shape == (1, 1, 9, 11, 13)
    assert torch.isfinite(output).all()


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown model_name"):
        create_model("unknown")


def test_advertised_models_are_available():
    assert set(list_models()) == {
        "unet3d",
        "sdf_refine_unet",
        "sam_med3d",
    }
