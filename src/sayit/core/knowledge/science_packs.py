"""Scientific / engineering domain packs (domain-coverage expansion).

Built to cover the DOMAINS revealed by the TIE held-out failures (aerospace,
control systems, chemistry/biochemistry, electronics, mathematics) using
ESTABLISHED, INDEPENDENT terminology — NOT by copying the held-out TIE target
terms. Provenance is recorded per term.

Sources (established, redistributable terminology — names/acronyms only, no
copyrighted prose is bundled):
- NASA / aerospace standard terminology (US Government works, public domain):
  https://www.nasa.gov  (aerodynamics / propulsion / structures vocabulary)
- Standard control-theory terminology (textbook/IEEE-standard acronyms):
  established usage (PID, LQR, LQG, MPC, SISO/MIMO, Bode/Nyquist).
- IUPAC + standard laboratory method acronyms (universal scientific usage):
  HPLC, ELISA, PCR, NMR, GC-MS, SDS-PAGE, etc.
- Standard electronics terminology (IEEE): MOSFET, PCB, ADC/DAC, FPGA, PWM.
- Standard mathematics / scientific-computing terminology: ODE/PDE, FFT, SVD.

LEAKAGE DISCIPLINE: terms here are chosen because they are *canonical, widely
attested* in the domain, independent of the TIE test transcripts. Any coincidental
overlap with a held-out TIE target (e.g. a universal acronym) is reported and
justified in artifacts/domain_coverage/leakage_report.md, never added "to score".

AMBIGUITY DISCIPLINE: single ordinary words that collide with technical meanings
(control, model, plant, state, gain, phase) are deliberately EXCLUDED or flagged
AMB_ORDINARY so a domain being active never turns ordinary speech technical.
"""

from __future__ import annotations

from typing import Dict, List

from .domain_packs import (
    AMB_NONE, AMB_ORDINARY, AMB_PROPER, CONF_CURATED, CONF_OFFICIAL,
    CONF_STRUCTURED, DomainTerm,
)
from .models import Domain


def _s(spoken, canonical, category, aliases=(), amb=AMB_NONE, domain=Domain.GENERAL,
       source="curated", sconf=CONF_CURATED, cconf=CONF_OFFICIAL,
       provenance="") -> DomainTerm:
    dt = DomainTerm(spoken_form=spoken, canonical_form=canonical, aliases=aliases,
                    domain=domain, category=category, source=source,
                    source_confidence=sconf, canonical_confidence=cconf,
                    ambiguity_class=amb)
    # record per-term provenance in metadata via to_knowledge_term path later;
    # DomainTerm has no provenance field, so stash it on the object for the
    # inventory tool (inert).
    dt.provenance = provenance  # type: ignore[attr-defined]
    return dt


# ---------------------------------------------------------------------------
# AEROSPACE / ENGINEERING. Multi-word entities + established acronyms. No bare
# ordinary words. Canonicals are standard forms.
# ---------------------------------------------------------------------------
_AEROSPACE = [
    _s("angle of attack", "angle of attack", "aerodynamics", ("a o a",),
       provenance="NASA aerodynamics terminology"),
    _s("lift coefficient", "lift coefficient", "aerodynamics", ("c l",),
       provenance="NASA aerodynamics terminology"),
    _s("drag coefficient", "drag coefficient", "aerodynamics", ("c d",),
       provenance="NASA aerodynamics terminology"),
    _s("reynolds number", "Reynolds number", "fluid_dynamics", ("reynold number",),
       provenance="standard fluid dynamics"),
    _s("mach number", "Mach number", "aerodynamics", (),
       provenance="standard aerodynamics"),
    _s("boundary layer", "boundary layer", "aerodynamics", (),
       provenance="NASA aerodynamics terminology"),
    _s("computational fluid dynamics", "CFD", "method", ("c f d",),
       provenance="standard engineering acronym"),
    _s("finite element method", "FEM", "method", ("f e m", "finite element"),
       provenance="standard engineering acronym"),
    _s("finite element analysis", "FEA", "method", ("f e a",),
       provenance="standard engineering acronym"),
    _s("thrust to weight ratio", "thrust-to-weight ratio", "propulsion", (),
       provenance="standard propulsion terminology"),
    _s("specific impulse", "specific impulse", "propulsion", ("i s p", "isp"),
       provenance="NASA propulsion terminology"),
    _s("turbofan", "turbofan", "propulsion", (),
       provenance="standard propulsion terminology"),
    _s("aeroelastic", "aeroelastic", "structures", ("aero elastic",),
       provenance="standard structures terminology"),
    _s("fuselage", "fuselage", "structures", (),
       provenance="standard aircraft structures"),
    _s("empennage", "empennage", "structures", (),
       provenance="standard aircraft structures"),
]

# ---------------------------------------------------------------------------
# CONTROL SYSTEMS. Established acronyms + multi-word methods. Single ordinary
# words (control/model/plant/state/gain/phase) are EXCLUDED by design.
# ---------------------------------------------------------------------------
_CONTROL = [
    _s("p i d controller", "PID controller", "method", ("pid", "p i d"),
       provenance="standard control-theory acronym"),
    _s("model predictive control", "MPC", "method", ("m p c",),
       provenance="standard control-theory acronym"),
    _s("linear quadratic regulator", "LQR", "method", ("l q r",),
       provenance="standard control-theory acronym (independent of TIE)"),
    _s("linear quadratic gaussian", "LQG", "method", ("l q g",),
       provenance="standard control-theory acronym (independent of TIE)"),
    _s("state space", "state-space", "method", ("state space model",),
       provenance="standard control terminology"),
    _s("transfer function", "transfer function", "method", (),
       provenance="standard control terminology"),
    _s("bode plot", "Bode plot", "method", ("bodie plot",),
       provenance="standard control terminology (H. Bode)"),
    _s("nyquist plot", "Nyquist plot", "method", (),
       provenance="standard control terminology (H. Nyquist)"),
    _s("root locus", "root locus", "method", (),
       provenance="standard control terminology"),
    _s("single input single output", "SISO", "term", ("s i s o",),
       provenance="standard control acronym"),
    _s("multiple input multiple output", "MIMO", "term", ("m i m o",),
       provenance="standard control acronym"),
    _s("system identification", "system identification", "method", ("sys id",),
       provenance="standard control terminology"),
    _s("kalman filter", "Kalman filter", "method", ("kalman",),
       provenance="standard estimation terminology (R. Kalman)"),
    _s("proportional integral derivative", "proportional-integral-derivative",
       "method", (), provenance="standard control terminology"),
]

# ---------------------------------------------------------------------------
# CHEMISTRY / BIOCHEMISTRY. Established lab-method acronyms + IUPAC-style forms.
# ---------------------------------------------------------------------------
_CHEMISTRY = [
    _s("high performance liquid chromatography", "HPLC", "method",
       ("h p l c",), provenance="standard analytical-chemistry acronym (IUPAC/independent of TIE)"),
    _s("gas chromatography mass spectrometry", "GC-MS", "method", ("g c m s",),
       provenance="standard analytical-chemistry acronym"),
    _s("nuclear magnetic resonance", "NMR", "method", ("n m r",),
       provenance="standard analytical-chemistry acronym"),
    _s("enzyme linked immunosorbent assay", "ELISA", "method", ("elisa",),
       provenance="standard biochemistry acronym (independent of TIE)"),
    _s("polymerase chain reaction", "PCR", "method", ("p c r",),
       provenance="standard molecular-biology acronym"),
    _s("mass spectrometry", "mass spectrometry", "method", ("mass spec",),
       provenance="standard analytical chemistry"),
    _s("sodium dodecyl sulfate", "SDS", "compound", ("s d s",),
       provenance="standard biochemistry (IUPAC)"),
    _s("deoxyribonucleic acid", "DNA", "compound", ("d n a",),
       provenance="standard biochemistry (IUPAC)"),
    _s("ribonucleic acid", "RNA", "compound", ("r n a",),
       provenance="standard biochemistry (IUPAC)"),
    _s("adenosine triphosphate", "ATP", "compound", ("a t p",),
       provenance="standard biochemistry (IUPAC)"),
    _s("protein protein interaction", "protein-protein interaction", "term",
       ("protein protein",), provenance="standard biochemistry terminology"),
    _s("chromatography", "chromatography", "method", (),
       provenance="standard analytical chemistry"),
    _s("titration", "titration", "method", (),
       provenance="standard analytical chemistry"),
]

# ---------------------------------------------------------------------------
# ELECTRONICS (audited in; small, high-value acronyms).
# ---------------------------------------------------------------------------
_ELECTRONICS = [
    _s("printed circuit board", "PCB", "component", ("p c b",),
       provenance="standard electronics acronym"),
    _s("field effect transistor", "MOSFET", "component", ("mosfet", "mos fet"),
       provenance="standard electronics acronym"),
    _s("analog to digital converter", "ADC", "component", ("a d c",),
       provenance="standard electronics acronym"),
    _s("digital to analog converter", "DAC", "component", ("d a c",),
       provenance="standard electronics acronym"),
    _s("field programmable gate array", "FPGA", "component", ("f p g a",),
       provenance="standard electronics acronym"),
    _s("pulse width modulation", "PWM", "method", ("p w m",),
       provenance="standard electronics acronym"),
    _s("operational amplifier", "op-amp", "component", ("op amp", "opamp"),
       provenance="standard electronics terminology"),
]

# ---------------------------------------------------------------------------
# MATHEMATICS / SCIENTIFIC COMPUTING (audited in; established acronyms).
# ---------------------------------------------------------------------------
_MATH = [
    _s("ordinary differential equation", "ODE", "term", ("o d e",),
       provenance="standard mathematics acronym"),
    _s("partial differential equation", "PDE", "term", ("p d e",),
       provenance="standard mathematics acronym"),
    _s("fast fourier transform", "FFT", "method", ("f f t",),
       provenance="standard numerical-methods acronym"),
    _s("singular value decomposition", "SVD", "method", ("s v d",),
       provenance="standard linear-algebra acronym"),
    _s("partial differential equations", "PDEs", "term", (),
       provenance="standard mathematics"),
    _s("eigenvalue", "eigenvalue", "term", ("eigen value",),
       provenance="standard linear algebra"),
    _s("eigenvector", "eigenvector", "term", ("eigen vector",),
       provenance="standard linear algebra"),
]

SCIENCE_PACKS: Dict[str, List[DomainTerm]] = {
    "aerospace_engineering": _AEROSPACE,
    "control_systems": _CONTROL,
    "chemistry_biochem": _CHEMISTRY,
    "electronics": _ELECTRONICS,
    "mathematics": _MATH,
}

# Assign the correct low-level Domain to each pack's terms (single source of truth).
_PACK_DOMAIN = {
    "aerospace_engineering": Domain.AEROSPACE,
    "control_systems": Domain.CONTROL,
    "chemistry_biochem": Domain.CHEMISTRY,
    "electronics": Domain.ELECTRONICS,
    "mathematics": Domain.MATHEMATICS,
}
for _name, _terms in SCIENCE_PACKS.items():
    for _dt in _terms:
        _dt.domain = _PACK_DOMAIN[_name]


def science_pack_terms(domains: List[str] | None = None):
    names = domains if domains is not None else list(SCIENCE_PACKS)
    out = []
    for name in names:
        for dt in SCIENCE_PACKS.get(name, []):
            if dt.enabled:
                kt = dt.to_knowledge_term()
                kt.metadata["provenance"] = getattr(dt, "provenance", "")
                out.append(kt)
    return out


def science_pack_stats() -> Dict[str, dict]:
    stats = {}
    for name, terms in SCIENCE_PACKS.items():
        multiword = sum(1 for t in terms if len(t.canonical_form.split()) >= 2)
        stats[name] = {
            "terms": len(terms),
            "ambiguous": sum(1 for t in terms if t.ambiguity_class != AMB_NONE),
            "multiword": multiword,
            "acronyms": sum(1 for t in terms if t.canonical_form.isupper() and len(t.canonical_form) <= 6),
        }
    return stats


def all_science_terms_lower() -> set:
    """Every spoken/canonical/alias form (lowercased) across science packs —
    used by the leakage checker."""
    out = set()
    for terms in SCIENCE_PACKS.values():
        for t in terms:
            out.add(t.spoken_form.lower())
            out.add(t.canonical_form.lower())
            for a in t.aliases:
                out.add(a.lower())
    return out
