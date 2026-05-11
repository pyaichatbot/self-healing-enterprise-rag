from __future__ import annotations

from dataclasses import dataclass

from shrag.settings import Settings

@dataclass(slots=True)
class RegressionGate:
    min_quality: float = 0.55
    max_error_rate: float = 0.2

    @classmethod
    def from_env(cls) -> RegressionGate:
        runtime_settings = Settings()
        return cls(
            min_quality=float(runtime_settings.eval_regression_min_quality),
            max_error_rate=float(runtime_settings.eval_regression_max_error_rate),
        )

    def check(self, quality: float, error_rate_value: float) -> tuple[bool, str]:
        if quality < self.min_quality:
            return False, "quality_below_threshold"
        if error_rate_value > self.max_error_rate:
            return False, "error_rate_above_threshold"
        return True, "pass"
