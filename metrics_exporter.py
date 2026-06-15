"""
metrics_exporter.py - Eksport wlasnych metryk kontrolera dla Prometheus/Grafana.

Uruchamia serwer HTTP (domyslnie port 9105), z ktorego Prometheus moze
scrapowac metryki kontrolera: liczbe sesji, aktualny tier oraz licznik
operacji skalowania. Pozwala to zwizualizowac prace kontrolera w Grafanie.
"""

from prometheus_client import start_http_server, Gauge, Counter

SESSIONS = Gauge("upf_scaler_sessions", "Liczba aktywnych sesji UE odczytana przez kontroler")
TIER_GAUGE = Gauge("upf_scaler_current_tier", "Aktualny tier zasobowy (numer)")
SCALE_OPS = Counter("upf_scaler_operations_total", "Liczba operacji skalowania", ["direction"])


def start_exporter(port: int = 9105):
    start_http_server(port)
    print(f"[exporter] Serwer metryk kontrolera nasluchuje na :{port}/metrics")


def _tier_to_number(tier_name: str) -> int:
    try:
        return int(tier_name.lstrip("T"))
    except ValueError:
        return 0


def update(sessions: float, tier_name: str):
    SESSIONS.set(sessions)
    TIER_GAUGE.set(_tier_to_number(tier_name))


def record_scale(direction: str):
    """direction: 'up' lub 'down'."""
    SCALE_OPS.labels(direction=direction).inc()
