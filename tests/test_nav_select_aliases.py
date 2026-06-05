import pytest

from cgn_model.vessel_model.config import VesselSectionsCfg


@pytest.mark.parametrize(
    ("alias", "selection_field", "selection_value", "expected"),
    [
        ("croisiere", "cruise_name", "Lavaux - Haut-Lac", "cruise"),
        ("croisière", "cruise_name", "Lavaux - Haut-Lac", "cruise"),
        ("course", "course_no", 101, "course"),
        ("etape", "leg", {"from_port": "A", "to_port": "B"}, "leg"),
        ("étape", "leg", {"from_port": "A", "to_port": "B"}, "leg"),
    ],
)
def test_nav_select_by_aliases_are_normalised(
    alias: str,
    selection_field: str,
    selection_value: object,
    expected: str,
) -> None:
    cfg = VesselSectionsCfg.model_validate(
        {
            "profiles": [
                {
                    "id": "speed",
                    "kind": "nav_speed",
                    "unit": "m/s",
                    "source": "cgn_croisieres/all",
                    "select": {
                        "by": alias,
                        selection_field: selection_value,
                    },
                }
            ]
        }
    )

    assert cfg.profiles[0].select.by == expected
