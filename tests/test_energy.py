import pytest

from wohnung.energy import sniff_energy


@pytest.mark.parametrize("text,cls,hwb", [
    ("Energieklasse A, HWB 25 kWh/m²a", "A", 25.0),
    ("HWB-Klasse: B", "B", None),
    ("Heizwärmebedarf 45,5 kWh/m²a (Klasse C)", "C", 45.5),
    ("HWB 120.3 kWh", "", 120.3),
    ("Energieausweis liegt vor", "", None),
    ("", "", None),
    ('finalEnergyDemandClass":"D"', "D", None),
])
def test_sniff_energy(text, cls, hwb):
    assert sniff_energy(text) == (cls, hwb)
