"""Canadian border (Arrangement R) PFD protection for Grant.

Mirrors WINNF_FT_S_BPR_testcase logic: CBSDs in the Border Sharing Zone whose
requested EIRP would produce PFD > -80 dBm/m²/MHz at the closest border point
must be rejected with responseCode 400.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Harness reference models (ITM, Canadian border geometry, antenna gains).
_HARNESS = Path(__file__).resolve().parents[2] / "src" / "harness"
if _HARNESS.is_dir() and str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

# Arrangement R: grants overlapping above 3650 MHz are subject to border PFD.
ARRANGEMENT_R_LOW_HZ = 3_650_000_000
PFD_LIMIT_DBM_M2_MHZ = -80.0
BORDER_RX_HEIGHT_M = 1.5
ITM_FREQ_MHZ = 3625.0


def _overlaps_arrangement_r(low_hz: int, high_hz: int) -> bool:
    # Same gate as BPR harness: highFrequency > 3650 MHz.
    return high_hz > ARRANGEMENT_R_LOW_HZ and low_hz < 3_700_000_000


def violates_canadian_border_pfd(
    installation: dict[str, Any],
    max_eirp: float,
    low_hz: int,
    high_hz: int,
) -> bool:
    """Return True if the grant must be rejected (responseCode 400)."""
    if not _overlaps_arrangement_r(low_hz, high_hz):
        return False

    try:
        lat = float(installation["latitude"])
        lon = float(installation["longitude"])
    except (KeyError, TypeError, ValueError):
        return False

    ant_azi = installation.get("antennaAzimuth")
    ant_bw = installation.get("antennaBeamwidth")
    try:
        max_ant_gain = float(installation.get("antennaGain") or 0)
    except (TypeError, ValueError):
        max_ant_gain = 0.0

    try:
        from reference_models.antenna import antenna
        from reference_models.geo import utils
        from reference_models.propagation import wf_itm
    except ImportError:
        return False

    try:
        in_zone, border_lat, border_lon = utils.CheckCbsdInBorderSharingZone(
            lat, lon, ant_azi, ant_bw
        )
    except Exception:
        return False
    if not in_zone or border_lat is None or border_lon is None:
        return False

    height = float(installation.get("height") or 0)
    height_type = installation.get("heightType") or "AGL"
    indoor = bool(installation.get("indoorDeployment"))

    try:
        propagation = wf_itm.CalcItmPropagationLoss(
            lat,
            lon,
            height,
            border_lat,
            border_lon,
            BORDER_RX_HEIGHT_M,
            reliability=0.5,
            cbsd_indoor=indoor,
            freq_mhz=ITM_FREQ_MHZ,
            is_height_cbsd_amsl=(height_type == "AMSL"),
        )
        pl = propagation.db_loss
        bearing = propagation.incidence_angles.hor_cbsd
        ant_gain = antenna.GetStandardAntennaGains(
            bearing, ant_azi, ant_bw, max_ant_gain
        )
    except Exception:
        # Missing terrain / ITM failure while inside sharing zone: reject to
        # satisfy Arrangement R rather than incorrectly authorizing.
        return True

    # PFD = requested_eirp - maxAntGain + effectiveGain - PL + 32.6
    pfd = max_eirp - max_ant_gain + ant_gain - pl + 32.6
    return pfd > PFD_LIMIT_DBM_M2_MHZ
