"""
prometheus.py - Klient odczytu metryk z Prometheus Query API.

Wykorzystuje endpoint /api/v1/query (instant query), tak jak pokazano
w przykladach z Lab 3 (curl ... /api/v1/query -G -d 'query=...').
"""

import requests


class PrometheusClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query_scalar(self, promql: str) -> float:
        """
        Wykonuje instant query i zwraca pojedyncza wartosc skalarna.
        Jesli zapytanie nie zwroci wyniku, zwraca 0.0.
        """
        url = f"{self.base_url}/api/v1/query"
        try:
            resp = requests.get(url, params={"query": promql}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[prometheus] Blad zapytania: {e}")
            return 0.0

        if data.get("status") != "success":
            print(f"[prometheus] Zapytanie nieudane: {data}")
            return 0.0

        result = data["data"]["result"]
        if not result:
            # brak wyniku (np. metryka jeszcze nie istnieje) -> traktujemy jako 0
            return 0.0

        # result[0].value = [timestamp, "wartosc"]
        try:
            return float(result[0]["value"][1])
        except (KeyError, IndexError, ValueError) as e:
            print(f"[prometheus] Nie udalo sie sparsowac wartosci: {e}")
            return 0.0
