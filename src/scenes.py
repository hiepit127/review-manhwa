"""Gom panel liên tiếp thành từng cảnh review."""

from __future__ import annotations


def group_panels(panels: list[dict], scene_count: int) -> list[dict]:
    count = len(panels)
    if count == 0:
        return []
    scenes_n = max(1, min(int(scene_count or count), count))
    sizes = [count // scenes_n] * scenes_n
    for index in range(count % scenes_n):
        sizes[index] += 1

    scenes = []
    cursor = 0
    for scene_id, size in enumerate(sizes, start=1):
        chunk = panels[cursor : cursor + size]
        cursor += size
        ocr = "\n".join(panel["ocr"].strip() for panel in chunk if (panel.get("ocr") or "").strip())
        scenes.append(
            {
                "id": scene_id,
                "panel_indexes": [panel["index"] for panel in chunk],
                "images": [panel["image"] for panel in chunk],
                "ocr": ocr,
                "narration": "",
            }
        )
    return scenes
