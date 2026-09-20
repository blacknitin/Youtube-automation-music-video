"""Feedback → AI interpretation → minimal targeted revision.

The interpreter returns ops; applying ops touches ONLY the affected scenes
(plus optional style-bible patch), then regenerates just those images.
"""
import json

from ..models import (FeedbackItem, Lyrics, Scene, Status, Storyboard, PJ)
from ..providers.registry import get_llm


def interpret(db, project, feedback: FeedbackItem, scenes) -> dict:
    llm = get_llm()
    style_bible = {}
    sb = db.query(Storyboard).filter(Storyboard.project_id == project.id,
                                     Storyboard.status != "archived")\
        .order_by(Storyboard.id.desc()).first()
    if sb:
        style_bible = PJ(sb.style_json) or {}
    context = {
        "idea": project.idea, "visual_style": project.visual_style,
        "characters": style_bible.get("characters", []),
        "scenes": [{"id": s.id, "idx": s.idx, "description": s.description, "prompt": s.prompt} for s in scenes],
    }
    try:
        plan = llm.interpret_feedback(feedback.text, context)
    except Exception as e:
        from ..providers.llm_mock import MockLLMProvider
        plan = MockLLMProvider().interpret_feedback(feedback.text, context)
        plan["summary"] = f"(offline interpretation — {type(e).__name__}) " + plan["summary"]
    # sanity: keep only valid scene ids
    valid = {s.id for s in scenes}
    ops = []
    for op in plan.get("ops", []):
        if op.get("op") == "scene_image":
            if op.get("scene_id") in valid:
                ops.append(op)
        else:
            ops.append(op)
    plan["ops"] = ops
    feedback.plan_json = json.dumps(plan, ensure_ascii=False)
    feedback.status = "interpreted"
    db.add(feedback)
    return plan


def apply_plan(db, project, feedback: FeedbackItem, regenerate: bool = True) -> dict:
    """Apply ops. Returns {scene_ids: [...], style_patched: bool}."""
    plan = PJ(feedback.plan_json) or {}
    ops = plan.get("ops", [])
    affected, style_patched = [], False

    sb = db.query(Storyboard).filter(Storyboard.project_id == project.id,
                                     Storyboard.status != "archived")\
        .order_by(Storyboard.id.desc()).first()
    style_bible = PJ(sb.style_json) if sb else {}

    for op in ops:
        kind = op.get("op")
        if kind == "scene_image":
            sc = db.query(Scene).get(int(op["scene_id"]))
            if not sc or sc.project_id != project.id:
                continue
            adj = (op.get("prompt_adjust") or "").strip()
            if adj:
                base = sc.prompt or sc.description
                sc.prompt = f"{base}, {adj}"[:2000]
            sc.seed = (sc.seed * 1103515245 + 12345) % (2**31 - 1)
            sc.image_status = "pending"
            affected.append(sc.id)
            db.add(sc)
        elif kind == "style_bible":
            patch = op.get("patch") or {}
            for key in ("visual_style",):
                if patch.get(key):
                    style_bible[key] = patch[key]
            for ch_patch in patch.get("characters", []) or []:
                for ch in style_bible.get("characters", []):
                    if ch.get("name", "").lower() == str(ch_patch.get("name", "")).lower():
                        if ch_patch.get("prompt_token"):
                            ch["prompt_token"] = ch_patch["prompt_token"]
            if sb:
                sb.style_json = json.dumps(style_bible, ensure_ascii=False)
                db.add(sb)
            style_patched = True

    # a style patch can affect scenes: regenerate scenes whose prompt mentions changed tokens
    if style_patched:
        tokens = [c.get("prompt_token", "") for c in style_bible.get("characters", [])]
        for sc in db.query(Scene).filter(Scene.project_id == project.id).all():
            text = f"{sc.description} {sc.prompt}".lower()
            if any(t and t.split(",")[0].lower() in text for t in tokens if t) and sc.id not in affected:
                sc.image_status = "pending"
                affected.append(sc.id)
                db.add(sc)

    feedback.status = "applied"
    db.add(feedback)
    db.flush()
    return {"scene_ids": sorted(set(affected)), "style_patched": style_patched}
