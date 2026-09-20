"""Storyboard creation: lyrics + analysis -> style bible + scene rows with timings."""
import json
import random

from ..models import Scene, Storyboard, PJ
from ..providers.base import AnalysisSummary
from ..providers.registry import get_llm
from .arrange import align_lines, assign_scene_times


def _analysis_summary(analysis) -> AnalysisSummary:
    return AnalysisSummary(
        duration=analysis.duration if analysis else 0.0,
        bpm=analysis.bpm if analysis else 0.0,
        sections=PJ(analysis.sections_json) if analysis else [])


def create_storyboard(db, project, analysis, lyrics: dict, progress=None) -> Storyboard:
    llm = get_llm()
    if progress:
        progress(10, "Designing storyboard with AI…")
    data = llm.generate_storyboard(lyrics, _analysis_summary(analysis), project.visual_style, project.idea)

    # deactivate old storyboard
    db.query(Storyboard).filter(Storyboard.project_id == project.id).update({"status": "archived"})
    sb = Storyboard(project_id=project.id, version=1, style_json=json.dumps(
        data.get("style_bible", {}), ensure_ascii=False), status="draft")
    count = db.query(Storyboard).filter(Storyboard.project_id == project.id).count()
    sb.version = count + 1
    db.add(sb)
    db.commit()  # commit (not flush): progress() writes from its own connection

    if progress:
        progress(55, "Creating scene rows…")
    old = db.query(Scene).filter(Scene.project_id == project.id).all()
    for o in old:
        db.delete(o)
    db.commit()

    for i, sc in enumerate(data.get("scenes", [])):
        scene = Scene(
            project_id=project.id, storyboard_id=sb.id, idx=i,
            section=str(sc.get("section", ""))[:100],
            lyrics_text=str(sc.get("lyrics_text", ""))[:500],
            description=str(sc.get("description", ""))[:1000],
            prompt=str(sc.get("prompt", sc.get("description", "")))[:2000],
            negative=str(sc.get("negative", ""))[:500],
            shot=str(sc.get("shot", "wide"))[:40],
            motion=str(sc.get("motion", "slow_zoom_in"))[:40],
            seed=random.randint(1, 2**31 - 1))
        db.add(scene)
    db.commit()

    # AI prompt pass — the ACTIVE LLM writes every scene prompt (no hardcoded
    # templates). Falls back to the local rule engine only if the provider
    # cannot write prompts.
    try:
        scenes = db.query(Scene).filter(Scene.storyboard_id == sb.id).order_by(Scene.idx).all()
        scene_dicts = [{"index": i, "section": s.section, "lyrics_text": s.lyrics_text,
                        "description": s.description, "shot": s.shot, "motion": s.motion}
                       for i, s in enumerate(scenes)]
        written = None
        try:
            written = llm.generate_scene_prompts(scene_dicts, data.get("style_bible", {}),
                                                 project.idea, project.genre)
        except NotImplementedError:
            written = None
        if written:
            for sc, lp in zip(scenes, written):
                if isinstance(lp, dict):
                    if lp.get("prompt"):
                        sc.prompt = str(lp["prompt"])[:2000]
                    if lp.get("negative"):
                        sc.negative = str(lp["negative"])[:500]
                    if lp.get("motion"):
                        sc.motion = str(lp["motion"])[:40]
        else:
            from .prompt import enhance_storyboard_prompts
            enhance_storyboard_prompts(scenes, data.get("style_bible", {}))
        db.commit()
    except Exception:
        db.rollback()  # prompts stay as the LLM wrote them — never fail here

    if progress:
        progress(75, "Aligning lyrics to music and timing the scenes…")
    align_lines(db, project, analysis, lyrics)
    scenes = db.query(Scene).filter(Scene.storyboard_id == sb.id).order_by(Scene.idx).all()
    assign_scene_times(db, project, sb, scenes, analysis, lyrics)
    db.commit()
    if progress:
        progress(95, f"Storyboard ready: {len(scenes)} scenes")
    return sb


def build_image_prompt(style_bible: dict, scene: Scene) -> tuple:
    """Compose final image prompt + negative, injecting character tokens for consistency."""
    style = style_bible.get("visual_style", "cinematic")
    base = scene.prompt or scene.description
    prompt = f"{base}, {style}" if style and style.lower() not in base.lower() else base
    low = f"{scene.description} {scene.prompt}".lower()
    for ch in style_bible.get("characters", []):
        name = (ch.get("name") or "").lower()
        token = ch.get("prompt_token") or ""
        if name and name in low and token and token.lower() not in low:
            prompt += f", {token}"
    palette = style_bible.get("color_palette") or []
    if palette:
        prompt += ", color palette " + " ".join(palette[:4])
    neg = ", ".join(x for x in [style_bible.get("global_negative", ""), scene.negative] if x)
    return prompt[:1800], neg[:500]
