"""
k8s_actuator.py - Aktuacja na Kubernetes: in-place pod vertical scaling.

Uzywa oficjalnej biblioteki kubernetes-client (>=31). Skalowanie odbywa sie
przez dedykowana metode patch_namespaced_pod_resize, ktora wola subresource
'resize' obiektu Pod (feature InPlacePodVerticalScaling). Odpowiada to komendzie
z Lab 3:

    kubectl patch -n default pod <upf-pod> --subresource resize \
      --patch '{"spec":{"containers":[{"name":"open5gs-upf",
                "resources":{"limits":{"cpu":"150m"}}}]}}'
"""

from kubernetes import client, config
from kubernetes.client.rest import ApiException


class K8sActuator:
    def __init__(self, namespace: str, pod_prefix: str, container_name: str):
        self.namespace = namespace
        self.pod_prefix = pod_prefix
        self.container_name = container_name

        # in-cluster (gdy kontroler dziala jako pod) lub lokalny kubeconfig (na kpi051)
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.api = client.CoreV1Api()

    def find_upf_pod(self) -> str:
        """Znajduje nazwe biezacego, dzialajacego poda UPF (po prefiksie)."""
        pods = self.api.list_namespaced_pod(self.namespace)
        for pod in pods.items:
            if pod.metadata.name.startswith(self.pod_prefix) and pod.status.phase == "Running":
                return pod.metadata.name
        return None

    def get_current_resources(self, pod_name: str) -> dict:
        """Zwraca aktualne limits/requests kontenera UPF (ze statusu poda)."""
        pod = self.api.read_namespaced_pod(pod_name, self.namespace)
        for cs in (pod.status.container_statuses or []):
            if cs.name == self.container_name and cs.resources:
                return {
                    "limits": dict(cs.resources.limits or {}),
                    "requests": dict(cs.resources.requests or {}),
                }
        return {"limits": {}, "requests": {}}

    def resize(self, pod_name: str, cpu: str, memory: str) -> bool:
        """
        In-place resize poda UPF: ustawia requests i limits CPU+RAM.
        Zwraca True przy powodzeniu.
        """
        patch = {
            "spec": {
                "containers": [
                    {
                        "name": self.container_name,
                        "resources": {
                            "requests": {"cpu": cpu, "memory": memory},
                            "limits": {"cpu": cpu, "memory": memory},
                        },
                    }
                ]
            }
        }
        try:
            self.api.patch_namespaced_pod_resize(
                name=pod_name,
                namespace=self.namespace,
                body=patch,
                field_manager="upf-scaler",
            )
            return True
        except ApiException as e:
            print(f"[k8s] Blad resize: {e.status} {e.reason}")
            return False
