"""Dispersion model layer (Phase BA.6).

Predicts the per-receptor concentration share contributed by a unit
emission at a source zone, given current wind regime + stability.
The intervention-impact pipeline multiplies the model's output by
each source zone's AP-42 emission rate to recover absolute
concentration delta at the receptor.

`model_kind = "dispersion"` is the registry discriminator.
`current` is decided by `app.domain.dispersion_promotion.maybe_promote_cfd_lookup`
at lifespan time, mirroring the AP-42 / cycle-time promotion path.

Two implementations:

* `distance_decay_baseline` — heuristic. Always available; falls
  back when no calibrated CFD matrix exists.
* `cfd_lookup_v0_1_0` — Phase BA campaign output. Snap-to-grid
  lookup against a persisted `DispersionMatrix` with Pasquill-
  Gifford analytic rescaling for stability classes off the trained
  grid.
"""

DISPERSION_MODEL_KIND = "dispersion"
