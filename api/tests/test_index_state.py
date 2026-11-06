from app.config import Settings
from app.services.index_state import IndexState


class Collection:
    def __init__(self, metadata, count=1):
        self.metadata = metadata
        self._count = count

    def count(self):
        return self._count


class Client:
    def __init__(self):
        self.collections = {
            "rahbar-active": Collection({"active": "rahbar-v1", "previous": ""}),
            "rahbar-v1": Collection({"status": "complete", "embed_model": "dummy-768", "dimension": 768}),
        }

    def heartbeat(self):
        return 1

    def get_collection(self, name, embedding_function=None):
        if name not in self.collections:
            raise ValueError(f"missing collection: {name}")
        return self.collections[name]


def test_index_state_resolves_pointer_and_complete_collection():
    status = IndexState(Settings(embed_model="dummy-768"), Client()).refresh()
    assert status.active == "rahbar-v1"
    assert status.ready is True
    assert status.failed is None
    assert status.checks == {"chroma": "ok", "index_pointer": "ok", "collection": "ok"}
    assert status.metadata["dimension"] == 768


def test_index_state_reports_missing_pointer():
    client = Client()
    del client.collections["rahbar-active"]
    status = IndexState(Settings(), client).refresh()
    assert status.failed == "index_pointer"
    assert status.checks["collection"] == "skipped"
    assert status.ready is False


def test_index_state_reports_empty_or_building_collection():
    client = Client()
    client.collections["rahbar-v1"] = Collection({"status": "building"}, count=0)
    status = IndexState(Settings(), client).refresh()
    assert status.failed == "collection"
    assert status.checks["collection"] == "empty"
