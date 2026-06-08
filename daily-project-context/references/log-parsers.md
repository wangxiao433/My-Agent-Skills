# Engineering Log Parsers

The collector has a generic keyword parser plus tool-specific profiles. Tool
detection is conservative: a profile is applied when the file path or early log
content contains profile indicators, or when the user forces a parser with
`--log-tool`.

## Ansys

Detected by path/content indicators such as `ansys`, `fluent`, `cfx`,
`mechanical`, `apdl`, `mapdl`, `workbench`, `solver.out`, and structural solver
phrases.

High-value categories:

- `fatal_error`: fatal solver failures.
- `license`: checkout, license server, or denied license events.
- `memory`: allocation failures and out-of-memory events.
- `numerics`: floating-point exceptions and divide-by-zero.
- `convergence`: divergence, unconverged solutions, residual warnings, and
  iteration limits.
- `mesh`: negative volume, reversed elements, poor element quality, mesh failure.
- `solver_stability`: pivots, singular systems, rigid-body motion, contact jumps.

## Zemax / OpticStudio

Detected by path/content indicators such as `zemax`, `opticstudio`, `zpl`, `ray
trace`, `non-sequential`, `sequential`, `merit function`, and `glass catalog`.

High-value categories:

- `ray_trace`: ray trace errors, inability to trace, total internal reflection.
- `geometry`: no intersection, missed surfaces, missed objects.
- `aperture`: vignetting, aperture stop, surface aperture issues.
- `optimization`: invalid operands, merit function failures, optimization
  failures.
- `tolerance`: tolerance failures.
- `catalog`: missing glass or catalog files.
- `model`: negative thickness, invalid surfaces, chief-ray or pupil issues.

## MuJoCo

Detected by path/content indicators such as `mujoco`, `mjmodel`, `mjdata`,
`mjwarn`, `qpos`, `qvel`, `qacc`, `mjcf`, and `constraint solver`.

High-value categories:

- `numerics`: NaN, infinity, and non-finite values.
- `state`: qpos/qvel/qacc/control anomalies.
- `stability`: divergence and instability.
- `constraint`: constraint and contact solver issues.
- `integration`: timestep and integration instability.
- `model_compile`: XML, MJCF, schema, and compiler errors.
- `model`: inertia, mass, joint, actuator, and keyframe issues.

## Output Fields

Each local log record can include:

- `detected_tools`
- `highest_severity`
- `severity_counts`
- `matches[].severity`
- `matches[].parser_hits`

Severity values are `info`, `low`, `medium`, `high`, and `critical`.
