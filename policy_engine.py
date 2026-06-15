"""
policy_engine.py - Logika decyzyjna kontrolera.

Decyzja opiera sie wylacznie na liczbie aktywnych sesji UE:
  1. Wybor tieru wg progow sessionThreshold (T1/T2/T3).
  2. Skalowanie asymetryczne:
     - scale-up: natychmiastowy, skokowy (np. T1 -> T3),
     - scale-down: stopniowy, jeden tier na raz (T3 -> T2 -> T1).
  3. Ochrony: cooldown (odstep miedzy operacjami) oraz stabilizacja
     scale-down (ochrona przed oscylacjami).
"""

import time
from dataclasses import dataclass
from intent import ScalingPolicy, Tier


@dataclass
class Decision:
    """Wynik pojedynczej iteracji petli decyzyjnej."""
    sessions: float
    target_tier: Tier
    current_tier_name: str
    should_scale: bool
    reason: str


class PolicyEngine:
    def __init__(self, policy: ScalingPolicy):
        self.policy = policy
        self._last_scale_ts = 0.0
        self._current_idx = None     # indeks aktualnego tieru
        self._lower_streak = 0       # licznik interwalow nizszej liczby sesji

    def update_policy(self, policy: ScalingPolicy):
        """Podmienia polityke (po hot-reloadzie intentu)."""
        self.policy = policy

    def evaluate(self, sessions: float) -> Decision:
        """Podejmuje decyzje na podstawie liczby sesji UE."""
        p = self.policy
        target_idx = p.tier_index_for_sessions(sessions)
        target_tier = p.tiers[target_idx]
        now = time.time()

        # pierwsza iteracja - inicjalizacja biezacego tieru bez skalowania
        if self._current_idx is None:
            self._current_idx = target_idx
            return Decision(sessions, target_tier, target_tier.name,
                            False, "inicjalizacja - przyjeto biezacy tier")

        # ten sam tier - brak akcji
        if target_idx == self._current_idx:
            self._lower_streak = 0
            return Decision(sessions, target_tier, p.tiers[self._current_idx].name,
                            False, "tier bez zmian")

        # cooldown - za wczesnie na kolejna operacje
        if (now - self._last_scale_ts) < p.cooldown_seconds:
            remaining = int(p.cooldown_seconds - (now - self._last_scale_ts))
            return Decision(sessions, target_tier, p.tiers[self._current_idx].name,
                            False, f"cooldown ({remaining}s pozostalo)")

        current_tier = p.tiers[self._current_idx]

        if target_idx > self._current_idx:
            # SCALE-UP natychmiastowy, skokowy (np. T1 -> T3)
            self._current_idx = target_idx
            self._last_scale_ts = now
            self._lower_streak = 0
            return Decision(sessions, target_tier, target_tier.name, True,
                            f"scale-up {current_tier.name} -> {target_tier.name}")
        else:
            # SCALE-DOWN stopniowy: schodzimy o jeden tier na raz
            self._lower_streak += 1
            if self._lower_streak >= p.scale_down_stabilization:
                next_idx = self._current_idx - 1
                next_tier = p.tiers[next_idx]
                self._current_idx = next_idx
                self._last_scale_ts = now
                self._lower_streak = 0
                return Decision(sessions, next_tier, next_tier.name, True,
                                f"scale-down (stopniowy) {current_tier.name} -> "
                                f"{next_tier.name} (cel: {target_tier.name})")
            else:
                return Decision(sessions, target_tier, current_tier.name, False,
                                f"stabilizacja scale-down "
                                f"({self._lower_streak}/{p.scale_down_stabilization})")
