from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class VisionFrame:
    """Screenshot prepared for a multimodal LLM, with click coordinate mapping."""

    path: str
    screen_w: int
    screen_h: int
    vision_w: int
    vision_h: int
    mime: str
    b64: str
    scale_x: float  # screen_x = vision_x * scale_x
    scale_y: float

    def map_click(self, x: int, y: int) -> tuple[int, int]:
        sx = int(round(x * self.scale_x))
        sy = int(round(y * self.scale_y))
        sx = max(0, min(self.screen_w - 1, sx))
        sy = max(0, min(self.screen_h - 1, sy))
        return sx, sy

    def instruction_text(self) -> str:
        return (
            f"Desktop screenshot attached. Image size: {self.vision_w}x{self.vision_h} pixels "
            f"(0,0 is top-left). Full screen is {self.screen_w}x{self.screen_h}. "
            f"When calling computer_click, use x,y in THIS IMAGE's pixel coordinates "
            f"(0–{self.vision_w - 1}, 0–{self.vision_h - 1}). "
            "Look carefully, then click or type only if needed. Prefer allowlisted open_app first."
        )


def prepare_screenshot_for_llm(
    path: str | Path,
    *,
    max_side: int = 1280,
    jpeg_quality: int = 75,
) -> VisionFrame:
    """Downscale + JPEG-encode a screenshot for vision models."""
    src = Path(path)
    with Image.open(src) as im:
        image = im.convert("RGB")
        screen_w, screen_h = image.size
        max_side = max(256, int(max_side))
        longest = max(screen_w, screen_h)
        if longest > max_side:
            ratio = max_side / float(longest)
            vision_w = max(1, int(screen_w * ratio))
            vision_h = max(1, int(screen_h * ratio))
            image = image.resize((vision_w, vision_h), Image.Resampling.LANCZOS)
        else:
            vision_w, vision_h = screen_w, screen_h

        buf = io.BytesIO()
        quality = max(40, min(95, int(jpeg_quality)))
        image.save(buf, format="JPEG", quality=quality, optimize=True)
        raw = buf.getvalue()

    scale_x = screen_w / float(vision_w)
    scale_y = screen_h / float(vision_h)
    return VisionFrame(
        path=str(src),
        screen_w=screen_w,
        screen_h=screen_h,
        vision_w=vision_w,
        vision_h=vision_h,
        mime="image/jpeg",
        b64=base64.b64encode(raw).decode("ascii"),
        scale_x=scale_x,
        scale_y=scale_y,
    )


def openai_image_message(frame: VisionFrame, *, text: str | None = None) -> dict:
    """OpenAI / OpenRouter multimodal user message."""
    body = text or frame.instruction_text()
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": body},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{frame.mime};base64,{frame.b64}"},
            },
        ],
    }


def ollama_image_message(frame: VisionFrame, *, text: str | None = None) -> dict:
    """Ollama chat message with images list."""
    return {
        "role": "user",
        "content": text or frame.instruction_text(),
        "images": [frame.b64],
    }
