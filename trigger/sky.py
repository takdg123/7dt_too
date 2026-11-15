"""Sky geometry for the trigger: GW skymap summaries and visibility from El Sauce."""

import io
import math
from datetime import datetime
from typing import NamedTuple, Optional

import astropy.units as u
import healpy as hp
import numpy as np
from astropy.coordinates import TETE, AltAz, EarthLocation, SkyCoord, get_body
from astropy.io import fits
from astropy.time import Time

from .model import Visibility

# Matches supy's MainObserver defaults (supy/observer/mainobserver.py).
EL_SAUCE = EarthLocation.from_geodetic(lat=-30.4704 * u.deg, lon=-70.7804 * u.deg, height=1580 * u.m)
SUN_MAX_ALT_DEG = -18.0
TARGET_MIN_ALT_DEG = 30.0
STEP_MIN = 10
HORIZON_H = 24
VISIBILITY_MAX_ORDER = 6
SR_TO_DEG2 = (180.0 / math.pi) ** 2


class ProbTable(NamedTuple):
    """Pixels of the 90% credible region, merged to at most VISIBILITY_MAX_ORDER."""

    ra_deg: np.ndarray
    dec_deg: np.ndarray
    prob: np.ndarray


def skymap_summary(fits_bytes: bytes) -> tuple[float, Optional[float], ProbTable]:
    with fits.open(io.BytesIO(fits_bytes)) as hdul:
        hdu = hdul[1]
        uniq = np.asarray(hdu.data["UNIQ"], dtype=np.int64)
        density = np.asarray(hdu.data["PROBDENSITY"], dtype=float)
        distmean = hdu.header.get("DISTMEAN")

    order = (np.log2(uniq // 4) // 2).astype(np.int64)
    ipix = uniq - 4 * 4 ** order
    pix_area_sr = 4 * np.pi / (12 * 4.0 ** order)
    prob = density * pix_area_sr

    by_density = np.argsort(density)[::-1]
    cumulative = np.cumsum(prob[by_density])
    n_in = min(int(np.searchsorted(cumulative, 0.9)) + 1, len(by_density))
    region = by_density[:n_in]
    area90 = float(pix_area_sr[region].sum() * SR_TO_DEG2)

    coarse_order = np.minimum(order[region], VISIBILITY_MAX_ORDER)
    coarse_ipix = ipix[region] >> (2 * (order[region] - coarse_order))
    coarse_uniq = 4 * 4 ** coarse_order + coarse_ipix
    merged, inverse = np.unique(coarse_uniq, return_inverse=True)
    merged_prob = np.bincount(inverse, weights=prob[region])
    m_order = (np.log2(merged // 4) // 2).astype(np.int64)
    m_ipix = merged - 4 * 4 ** m_order
    ra = np.empty(len(merged))
    dec = np.empty(len(merged))
    for o in np.unique(m_order):
        sel = m_order == o
        ra[sel], dec[sel] = hp.pix2ang(2 ** int(o), m_ipix[sel], nest=True, lonlat=True)

    distance = float(distmean) if distmean is not None and np.isfinite(distmean) else None
    return area90, distance, ProbTable(ra, dec, merged_prob)


def _observable_grid(ra_deg: np.ndarray, dec_deg: np.ndarray, now: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Boolean (n_targets, n_times) grid of observable samples and the sample offsets in hours."""
    hours = np.arange(0, HORIZON_H * 60 + STEP_MIN, STEP_MIN) / 60.0
    times = Time(now) + hours * u.hour
    sun_alt = get_body("sun", times, EL_SAUCE).transform_to(AltAz(obstime=times, location=EL_SAUCE)).alt.deg
    dark = sun_alt < SUN_MAX_ALT_DEG
    if not dark.any():
        return np.zeros((len(ra_deg), len(hours)), dtype=bool), hours

    # Apparent place at the mid-horizon epoch plus local apparent sidereal time gives altitudes to
    # well under 0.1 deg for 24 h, at the cost of one coordinate transform instead of n_targets x n_times.
    apparent = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg).transform_to(
        TETE(obstime=Time(now) + HORIZON_H / 2 * u.hour, location=EL_SAUCE))
    last = times[dark].sidereal_time("apparent", longitude=EL_SAUCE.lon).rad
    lat = EL_SAUCE.lat.rad
    dec = apparent.dec.rad[:, None]
    ha = last[None, :] - apparent.ra.rad[:, None]
    sin_alt = np.sin(dec) * np.sin(lat) + np.cos(dec) * np.cos(lat) * np.cos(ha)
    grid = np.zeros((len(ra_deg), len(hours)), dtype=bool)
    grid[:, dark] = sin_alt > math.sin(math.radians(TARGET_MIN_ALT_DEG))
    return grid, hours


def _first_hour(observable_at: np.ndarray, hours: np.ndarray) -> Optional[float]:
    if not observable_at.any():
        return None
    return float(hours[np.argmax(observable_at)])


def visibility_point(ra: float, dec: float, now: datetime) -> Visibility:
    grid, hours = _observable_grid(np.array([ra]), np.array([dec]), now)
    first = _first_hour(grid[0], hours)
    return Visibility(first, 0.0 if first is None else 1.0)


def visibility_map(prob_table: ProbTable, now: datetime) -> Visibility:
    """observable_fraction is the share of the 90% region's probability observable at some sample."""
    grid, hours = _observable_grid(prob_table.ra_deg, prob_table.dec_deg, now)
    fraction = float(prob_table.prob[grid.any(axis=1)].sum() / prob_table.prob.sum())
    return Visibility(_first_hour(grid.any(axis=0), hours), fraction)
