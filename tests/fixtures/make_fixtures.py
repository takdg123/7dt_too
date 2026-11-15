"""Regenerate the derived fixtures in this directory.

The EP, IceCube initial and SVOM files are verbatim examples from the GCN schema repository and the
gcn.nasa.gov SVOM page. This script derives the rest from them, plus a synthetic GW alert whose
skymap is a Gaussian (sigma 2.5 deg, so the 90% area is 2*pi*sigma^2*ln(10) = 90.4 deg2) at 100 Mpc.

    /home/7dt/too-trigger-venv/bin/python tests/fixtures/make_fixtures.py
"""

import base64
import io
import json
from pathlib import Path

import healpy as hp
import numpy as np
from astropy.io import fits

HERE = Path(__file__).parent
GW_CENTER = (150.0, -30.0)
GW_SIGMA_DEG = 2.5


def _centre_distance_deg(order: int, ipix: int) -> float:
    ra, dec = hp.pix2ang(2 ** order, ipix, nest=True, lonlat=True)
    return float(np.degrees(hp.rotator.angdist([ra, dec], list(GW_CENTER), lonlat=True))[0])


def synthetic_multiorder_fits() -> bytes:
    """A valid multi-order tree: order 5 out to 12 deg, refined to 6 inside 6 deg and to 7 inside 3 deg."""
    refine_within_deg = {5: 6.0, 6: 3.0}
    vec = hp.ang2vec(*GW_CENTER, lonlat=True)
    stack = [(5, int(p)) for p in hp.query_disc(2 ** 5, vec, np.radians(12.0), nest=True)]
    leaves = []
    while stack:
        order, p = stack.pop()
        if order in refine_within_deg and _centre_distance_deg(order, p) < refine_within_deg[order]:
            stack.extend((order + 1, 4 * p + k) for k in range(4))
        else:
            leaves.append((order, p))
    order = np.array([o for o, _ in leaves])
    ipix = np.array([p for _, p in leaves])
    sep = np.array([_centre_distance_deg(o, p) for o, p in leaves])
    area_sr = 4 * np.pi / (12 * 4.0 ** order)
    weight = np.exp(-0.5 * (sep / GW_SIGMA_DEG) ** 2)
    density = weight / np.sum(weight * area_sr)
    n = len(order)
    hdu = fits.BinTableHDU.from_columns([
        fits.Column("UNIQ", "K", array=4 * 4 ** order + ipix),
        fits.Column("PROBDENSITY", "D", array=density),
        fits.Column("DISTMU", "D", array=np.full(n, 100.0)),
        fits.Column("DISTSIGMA", "D", array=np.full(n, 25.0)),
        fits.Column("DISTNORM", "D", array=np.full(n, 1e-4)),
    ])
    hdu.header["DISTMEAN"] = 100.0
    hdu.header["DISTSTD"] = 25.0
    buf = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(), hdu]).writeto(buf)
    return buf.getvalue()


def gw_initial() -> dict:
    return {
        "superevent_id": "S260115a",
        "time_created": "2026-01-15T03:05:00Z",
        "alert_type": "INITIAL",
        "event": {
            "time": "2026-01-15T03:00:00.000Z",
            "far": 1e-9,
            "significant": True,
            "instruments": ["H1", "L1", "V1"],
            "group": "CBC",
            "pipeline": "gstlal",
            "search": "AllSky",
            "classification": {"BNS": 0.85, "NSBH": 0.1, "BBH": 0.0, "Terrestrial": 0.05},
            "properties": {"HasNS": 0.99, "HasRemnant": 0.9, "HasMassGap": 0.0},
            "skymap": base64.b64encode(synthetic_multiorder_fits()).decode(),
        },
        "external_coinc": None,
    }


def main():
    (HERE / "gw_initial.json").write_text(json.dumps(gw_initial()))

    initial = json.loads((HERE / "icecube_bronze_initial.json").read_text())
    update = dict(initial, alert_type="update", record_number=2, systematic_included=True, ra_dec_error=0.6)
    (HERE / "icecube_bronze_update.json").write_text(json.dumps(update, indent=2))

    mxt = (HERE / "svom_mxt_initial.xml").read_text()
    (HERE / "svom_mxt_update.xml").write_text(mxt.replace("_mxt-initial_qf1", "_mxt-update_qf1"))


if __name__ == "__main__":
    main()
