from dataclasses import replace

from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import active_snapshot, plan_incremental, restore_previous, store
from test_starter_dummy import FakeClient


def chunk(source, text, index=0, superseded=False):
    return Chunk(
        id=f"{source.removesuffix('.md')}:{index:05d}", text=text, source=source,
        section="Section", page=1, doc_version="2026", superseded=superseded,
        chunk_index=index, tokens=4,
    )


def test_unchanged_documents_reuse_vectors_and_deleted_sources_are_removed():
    client = FakeClient()
    settings = replace(get_settings(), embed_model="test-model")
    initial = [chunk("rules.md", "Original rules"), chunk("calendar.md", "Calendar"),
               chunk("obsolete.md", "Obsolete document")]
    initial_digests = {"rules.md": "digest-1", "calendar.md": "digest-2",
                       "obsolete.md": "digest-4"}
    store(initial, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], settings, client=client,
          source_digests=initial_digests)

    snapshot = active_snapshot(settings, client)
    changed = [chunk("rules.md", "Revised rules"), chunk("calendar.md", "Calendar")]
    current_digests = {"rules.md": "digest-3", "calendar.md": "digest-2"}
    reusable, summary = plan_incremental(changed, current_digests, settings, snapshot)

    assert set(reusable) == {changed[1].id}
    assert summary["embedded_chunks"] == 1
    assert summary["reused_chunks"] == 1
    assert summary["changed"] == ["rules.md"]
    assert summary["deleted"] == ["obsolete.md"]

    vectors = [reusable.get(item.id, [0.5, 0.5]) for item in changed]
    store(changed, vectors, settings, client=client, source_digests=current_digests,
          incremental=summary)
    after = active_snapshot(settings, client)
    assert set(after["chunk_counts"]) == {"rules.md", "calendar.md"}
    assert after["chunk_counts"] == {"rules.md": 1, "calendar.md": 1}
    assert after["metadata"]["incremental_summary"]


def test_superseded_metadata_is_updated_and_previous_index_can_be_restored():
    client = FakeClient()
    settings = replace(get_settings(), embed_model="test-model")
    active_chunks = [chunk("rules-2023.md", "Prior rules")]
    store(active_chunks, [[1.0, 0.0]], settings, client=client,
          source_digests={"rules-2023.md": "old"})
    first_active = client.collections["rahbar-active"].metadata["active"]

    current = [chunk("rules-2023.md", "Prior rules", superseded=True),
               chunk("rules-2026.md", "Current rules")]
    snapshot = active_snapshot(settings, client)
    reusable, _summary = plan_incremental(
        current, {"rules-2023.md": "old", "rules-2026.md": "new"}, settings, snapshot)
    vectors = [reusable[current[0].id], [0.0, 1.0]]
    store(current, vectors, settings, client=client,
          source_digests={"rules-2023.md": "old", "rules-2026.md": "new"})
    pointer = client.collections["rahbar-active"]
    now_active = client.collections[pointer.metadata["active"]]
    archived = next(meta for _text, _vector, meta in now_active.rows.values()
                    if meta["source"] == "rules-2023.md")
    assert archived["superseded"] is True
    assert pointer.metadata["previous"] == first_active
    restored = restore_previous(settings, client)
    assert restored == first_active
    assert pointer.metadata["active"] == first_active
