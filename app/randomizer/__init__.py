"""LIBRA: constrained (pseudo)randomization of crossover and parallel designs via ILP."""
from .spec import DesignSpec, validate
from .solver import DesignError, Result, solve

__all__ = ["DesignSpec", "validate", "solve", "Result", "DesignError"]
__version__ = "1.0.0"

APP_NAME = "LIBRA"
APP_TITLE = "LIBRA – Crossover Randomizer"
APP_EXPANSION = "Linear Integer Programming for Balanced Randomization"

# How to cite LIBRA (used by the methods paragraph, the About dialog and CITATION.cff).
# Fill in the authors and the journal details once the article is published.
CITE_AUTHORS = "Brejtr, V., Šíchová, K., Páleníček, T., & Lhotská, L."
CITE_YEAR = "2026"
CITE_SHORT = f"Brejtr et al., {CITE_YEAR}"
CITATION = (f"{CITE_AUTHORS} ({CITE_YEAR}). LIBRA: Linear Integer Programming for Balanced Randomization. "
            "Behavior Research Methods (submitted). "
            f"Software: LIBRA – Crossover Randomizer, version {__version__}.")
