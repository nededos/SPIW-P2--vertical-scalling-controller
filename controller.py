#!/usr/bin/env python3
"""
controller.py - Glowny kontroler skalowania UPF.

Petla sterowania (control loop):
  1. (opcjonalnie) przeladuj intent jesli plik sie zmienil (hot-reload),
  2. pobierz liczbe sesji UE z Prometheusa,
  3. wybierz tier i podejmij decyzje (z cooldown i stabilizacja),
  4. jesli trzeba - wykonaj in-place resize poda UPF (CPU + RAM),
  5. wyeksportuj wlasne metryki dla Grafany,
  6. odczekaj interval i powtorz.

Uruchomienie:
    python3 controller.py [sciezka_do_intentu]
domyslnie: ./scaling_policy.yaml
"""

import sys
import time
import signal

from intent import PolicyWatcher
from prometheus import PrometheusClient
from k8s_actuator import K8sActuator
from policy_engine import PolicyEngine
import metrics_exporter


_running = True


def _handle_stop(signum, frame):
    global _running
    print("\n[controller] Otrzymano sygnal zatrzymania, koncze petle...")
    _running = False


def main():
    policy_path = sys.argv[1] if len(sys.argv) > 1 else "scaling_policy.yaml"

    print(f"[controller] Start. Intent: {policy_path}")
    watcher = PolicyWatcher(policy_path)
    policy = watcher.policy

    prom = PrometheusClient(policy.prometheus_url)
    actuator = K8sActuator(
        namespace=policy.target_namespace,
        pod_prefix=policy.pod_prefix,
        container_name=policy.container_name,
    )
    engine = PolicyEngine(policy)

    metrics_exporter.start_exporter(port=9105)

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    print("[controller] Tiery: " +
          ", ".join(f"{t.name}(sesje>={t.session_threshold}, cpu={t.cpu}, mem={t.memory})"
                    for t in policy.tiers))

    while _running:
        loop_start = time.time()

        # 1. hot-reload intentu
        if watcher.maybe_reload():
            policy = watcher.policy
            engine.update_policy(policy)
            prom = PrometheusClient(policy.prometheus_url)
            print("[controller] Intent przeladowany.")

        # 2. odczyt metryki
        sessions = prom.query_scalar(policy.sessions_query)

        # 3. decyzja
        decision = engine.evaluate(sessions)

        # 4. aktuacja
        if decision.should_scale:
            pod = actuator.find_upf_pod()
            if pod is None:
                print("[controller] UWAGA: nie znaleziono dzialajacego poda UPF")
            else:
                tier = decision.target_tier
                ok = actuator.resize(pod, tier.cpu, tier.memory)
                if ok:
                    direction = "up" if "scale-up" in decision.reason else "down"
                    metrics_exporter.record_scale(direction)
                    print(f"[controller] SKALOWANIE: pod={pod} -> tier={tier.name} "
                          f"(cpu={tier.cpu}, mem={tier.memory}) | {decision.reason}")
                else:
                    print(f"[controller] Skalowanie nieudane dla pod={pod}")

        # 5. eksport metryk
        metrics_exporter.update(sessions=sessions, tier_name=decision.current_tier_name)

        # log statusu
        print(f"[loop] sesje={sessions:.0f} tier={decision.current_tier_name} "
              f"| {decision.reason}")

        # 6. sleep do nastepnego interwalu
        elapsed = time.time() - loop_start
        time.sleep(max(0.0, policy.interval_seconds - elapsed))

    print("[controller] Zatrzymano.")


if __name__ == "__main__":
    main()
