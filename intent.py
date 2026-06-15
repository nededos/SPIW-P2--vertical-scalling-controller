"""
intent.py - Model deklaratywnego intentu skalowania.

Wczytuje polityke z pliku YAML (scaling_policy.yaml), waliduje i udostepnia
jako obiekt Pythona. Obsluguje hot-reload: kontroler wykrywa zmiane pliku
(po czasie modyfikacji) i przeladowuje polityke bez restartu.

Decyzja opiera sie wylacznie na liczbie sesji UE - tiery definiuja progi
w liczbie sesji (session_threshold).
"""

from dataclasses import dataclass, field
from typing import List
import os
import yaml


@dataclass
class Tier:
    """Pojedynczy tier zasobowy. Prog wyrazony w liczbie sesji UE."""
    name: str
    session_threshold: int   # minimalna liczba sesji aby wejsc w ten tier
    cpu: str                 # np. "500m"
    memory: str              # np. "512Mi"


@dataclass
class ScalingPolicy:
    """Kompletna polityka skalowania (sparsowany intent)."""
    # target
    target_namespace: str
    pod_prefix: str
    container_name: str
    # control
    interval_seconds: int
    cooldown_seconds: int
    scale_down_stabilization: int
    # metryka
    prometheus_url: str
    sessions_query: str
    # tiery (posortowane rosnaco wg session_threshold)
    tiers: List[Tier] = field(default_factory=list)

    def tier_index_for_sessions(self, sessions: float) -> int:
        """Zwraca indeks najwyzszego tieru, ktorego prog sesji zostal osiagniety."""
        idx = 0
        for i, tier in enumerate(self.tiers):
            if sessions >= tier.session_threshold:
                idx = i
            else:
                break
        return idx


def load_policy(path: str) -> ScalingPolicy:
    """Wczytuje i waliduje polityke z pliku YAML."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if raw.get("kind") != "UpfScalingPolicy":
        raise ValueError(f"Nieprawidlowy kind: {raw.get('kind')}")

    spec = raw["spec"]
    target = spec["target"]
    control = spec["control"]
    metrics = spec["metrics"]

    tiers = [
        Tier(
            name=t["name"],
            session_threshold=int(t["sessionThreshold"]),
            cpu=t["cpu"],
            memory=t["memory"],
        )
        for t in spec["tiers"]
    ]
    tiers.sort(key=lambda t: t.session_threshold)

    if not tiers:
        raise ValueError("Polityka musi definiowac co najmniej jeden tier")

    return ScalingPolicy(
        target_namespace=target["namespace"],
        pod_prefix=target["podPrefix"],
        container_name=target["containerName"],
        interval_seconds=int(control["intervalSeconds"]),
        cooldown_seconds=int(control["cooldownSeconds"]),
        scale_down_stabilization=int(control["scaleDownStabilization"]),
        prometheus_url=metrics["prometheusUrl"],
        sessions_query=metrics["sessionsQuery"],
        tiers=tiers,
    )


class PolicyWatcher:
    """Sledzi plik intentu i przeladowuje polityke przy zmianie (hot-reload)."""

    def __init__(self, path: str):
        self.path = path
        self._mtime = 0.0
        self.policy = self._load()

    def _load(self) -> ScalingPolicy:
        self._mtime = os.path.getmtime(self.path)
        return load_policy(self.path)

    def maybe_reload(self) -> bool:
        """Zwraca True jesli plik sie zmienil i polityka zostala przeladowana."""
        try:
            current = os.path.getmtime(self.path)
        except OSError:
            return False
        if current != self._mtime:
            try:
                self.policy = self._load()
                return True
            except Exception as e:
                print(f"[intent] Blad przeladowania, uzywam poprzedniej polityki: {e}")
                self._mtime = current
        return False
