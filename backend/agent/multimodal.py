"""多模态支持 — 视觉理解、截图分析、图片输入。

支持的视觉模型:
- Claude 3.5/4 Sonnet (Anthropic)
- GPT-4o / GPT-4V (OpenAI)
- DeepSeek-VL 系列 (OpenAI-compat)
- 本地模型 (通过 OpenAI-compat 接口)

五层架构: 交互层 → 引擎层 → 工具层 → 记忆层 → 安全层
          └── 多模态能力横跨全部五层
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)


class ImageSource(str, Enum):
    FILE = "file"           # 本地图片文件
    SCREENSHOT = "screenshot"  # 桌面截图
    CLIPBOARD = "clipboard"    # 剪贴板
    URL = "url"              # 远程图片 URL


@dataclass
class ImageContent:
    """视觉内容单元。"""
    source: ImageSource
    base64_data: str = ""        # base64 编码的图片数据
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    description: str = ""        # 用户对图片的描述/问题
    file_path: str = ""          # 原始文件路径

    @classmethod
    def from_file(cls, path: str | Path, description: str = "") -> "ImageContent":
        """从本地文件加载图片。"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()

        ext = path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                    ".webp": "image/webp", ".bmp": "image/bmp"}

        img = Image.open(path)
        return cls(
            source=ImageSource.FILE,
            base64_data=data,
            mime_type=mime_map.get(ext, "image/png"),
            width=img.width,
            height=img.height,
            description=description,
            file_path=str(path),
        )

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str = "image/png",
                   description: str = "") -> "ImageContent":
        """从字节数据加载图片。"""
        b64 = base64.b64encode(data).decode()
        img = Image.open(io.BytesIO(data))
        return cls(
            source=ImageSource.SCREENSHOT,
            base64_data=b64,
            mime_type=mime_type,
            width=img.width,
            height=img.height,
            description=description,
        )

    @classmethod
    def from_screenshot(cls, pil_image: Image.Image,
                        description: str = "") -> "ImageContent":
        """从 PIL Image（截图）创建。"""
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return cls.from_bytes(buf.getvalue(), "image/png", description)


# ---- 多模态消息构建 ----
def build_multimodal_message(
    role: str,
    text: str,
    images: list[ImageContent] | None = None,
) -> dict[str, Any]:
    """构建多模态消息（支持文本+图片）。

    Anthropic 格式: {"role": "user", "content": [{"type": "text", ...}, {"type": "image", ...}]}
    OpenAI 格式: {"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}
    """
    if not images:
        return {"role": role, "content": text}

    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})

    for img in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.mime_type,
                "data": img.base64_data,
            },
        })

    return {"role": role, "content": content}


def build_openai_multimodal_message(
    role: str,
    text: str,
    images: list[ImageContent] | None = None,
) -> dict[str, Any]:
    """构建 OpenAI 兼容格式的多模态消息。"""
    if not images:
        return {"role": role, "content": text}

    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})

    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img.mime_type};base64,{img.base64_data}",
                "detail": "auto",
            },
        })

    return {"role": role, "content": content}


# ---- 视觉分析工具 ----
class VisionAnalyzer:
    """视觉分析器 — 调用多模态模型分析图片内容。

    支持:
    - 截图理解: "这段代码有什么问题？"
    - UI 审查: "这个界面布局怎么样？"
    - 图表分析: "这个架构图的要点是什么？"
    - 错误诊断: "这个报错截图是什么原因？"
    """

    # 支持视觉的模型列表
    VISION_MODELS = {
        "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229", "claude-3-haiku-20240307",
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview",
        "deepseek-chat", "deepseek-vl2",
        "gpt-4.1", "gpt-4.1-mini",
    }

    @classmethod
    def supports_vision(cls, model: str) -> bool:
        return model.lower() in {m.lower() for m in cls.VISION_MODELS}

    @classmethod
    def analyze_screenshot(
        cls,
        image: ImageContent,
        question: str = "描述这张截图中显示的内容",
        model: str = "gpt-4o",
    ) -> str:
        """分析截图内容（同步版本，用于工具调用）。

        工具调用格式:
          tool: analyze_screenshot
          args: {image_path: "screenshot.png", question: "这个报错是什么意思？"}
        """
        if not image.base64_data:
            return "[Error] No image data"

        return (
            f"[Vision Analysis: {model}]\n"
            f"Image: {image.width}x{image.height}, {len(image.base64_data)//1024}KB\n"
            f"Question: {question}\n"
            f"(Actual vision model call happens in streaming loop)"
        )


# ---- 图片预处理 ----
def preprocess_image(
    image: Image.Image,
    max_size: int = 1568,
    quality: int = 85,
) -> Image.Image:
    """预处理图片：缩放 + 压缩，控制 token 消耗。

    大图按比例缩放到 max_size 以内，减少视觉 token 占用。
    """
    w, h = image.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        image = image.resize((new_w, new_h), Image.LANCZOS)

    # 转 RGB（处理 RGBA/灰度）
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    return image


def encode_image_for_vision(image: Image.Image, max_size: int = 1568) -> ImageContent:
    """将 PIL Image 编码为视觉模型可用的格式。"""
    processed = preprocess_image(image, max_size)
    buf = io.BytesIO()
    processed.save(buf, format="JPEG", quality=85)
    return ImageContent.from_bytes(
        buf.getvalue(),
        mime_type="image/jpeg",
        description="Screenshot",
    )
