"""Shared tool-call helpers (ask_qwen) for hybrid pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Sequence

from worker_job.qwen_client import QwenClient, QwenClientError
from worker_job.field_processors.base import (
    FIELD_STATUS_ERROR,
    FIELD_STATUS_NO_DATA,
    FIELD_STATUS_OK,
    FieldResult,
)


@dataclass
class ToolCallResult:
    status: str
    value: Optional[str]
    reasoning: Sequence[str]
    page_num: Optional[int] = None


def _normalize_digits(raw: str, expected_lengths: Optional[Iterable[int]] = None) -> Optional[str]:
    if raw is None:
        return None
    cleaned = (
        str(raw)
        .replace(" ", "")
        .replace("\xa0", "")
        .replace("-", "")
        .replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace("S", "5")
        .replace("B", "8")
    )
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if expected_lengths:
        if len(digits) not in expected_lengths:
            return None
    return digits or None


def ask_qwen(
    *,
    field_id: str,
    field_name: str,
    page_num: Optional[int],
    question_text: str,
    page_image: Optional[bytes],
    qwen_client: Optional[QwenClient] = None,
    run_logger: Optional[Callable[[str], None]] = None,
    log_dir: Optional[Path] = None,
) -> ToolCallResult:
    """
    Tool-call wrapper: one call = one page = one question. Returns normalized digits only.
    """
    if run_logger:
        run_logger(f"ask_qwen start field={field_id} page={page_num} question='{question_text}'")

    if page_image is None:
        reasoning = ["page_not_available"]
        if run_logger:
            run_logger(f"ask_qwen result field={field_id} status=no_data reason=page_not_available")
        return ToolCallResult(status=FIELD_STATUS_NO_DATA, value=None, reasoning=reasoning, page_num=page_num)
    
    # Сохранение изображения для отладки (уникальное имя для каждого вызова)
    if log_dir and page_image:
        try:
            qwen_images_dir = log_dir / "qwen_images"
            qwen_images_dir.mkdir(exist_ok=True)
            # Уникальное имя: field + page + timestamp
            timestamp = str(int(time.time() * 1000))  # milliseconds
            img_filename = f"{field_id}_page{page_num}_{timestamp}.jpg"
            img_path = qwen_images_dir / img_filename
            img_path.write_bytes(page_image)
            if run_logger:
                run_logger(f"qwen_image_saved path={img_path} size={len(page_image)}b")
        except Exception as e:  # noqa: BLE001
            if run_logger:
                run_logger(f"qwen_image_save_failed err={e}")

    client = qwen_client or QwenClient()
    try:
        response = client.ask_number(page_image, page_num or 0, question_text)
        status = response.get("status") or FIELD_STATUS_OK
        value_raw = response.get("value") or ""
        qwen_context = response.get("context") or ""
        qwen_explanation = response.get("explanation") or ""

        # Проверка согласованности: value_raw должен присутствовать в context
        if value_raw and qwen_context:
            normalized_value = _normalize_digits(value_raw, expected_lengths=None)
            context_digits = _normalize_digits(qwen_context, expected_lengths=None)

            if normalized_value and normalized_value not in context_digits:
                # Противоречие: raw не найден в context
                reasoning = [
                    f"ask_qwen via qwen; page={page_num}",
                    f"raw={value_raw}",
                    f"context={qwen_context}",
                    f"explanation={qwen_explanation}",
                    "inconsistency: value not in context"
                ]
                if run_logger:
                    run_logger(f"ask_qwen inconsistency field={field_id} page={page_num} value={value_raw} not in context")
                return ToolCallResult(
                    status=FIELD_STATUS_ERROR,
                    value=None,
                    reasoning=reasoning,
                    page_num=page_num
                )
    except QwenClientError as e:
        if run_logger:
            run_logger(f"ask_qwen error field={field_id} page={page_num} err={e}")
        return ToolCallResult(
            status=FIELD_STATUS_ERROR,
            value=None,
            reasoning=[f"qwen_call_failed: {e}"],
            page_num=page_num,
        )
    except Exception as e:  # noqa: BLE001
        if run_logger:
            run_logger(f"ask_qwen error field={field_id} page={page_num} err={e}")
        return ToolCallResult(
            status=FIELD_STATUS_ERROR,
            value=None,
            reasoning=[f"qwen_call_failed: {e}"],
            page_num=page_num,
        )

    # Expected lengths for numeric fields: ОГРН (13), ОРНЗ (11), аттестат (variable)
    expected_lengths_map: Dict[str, Iterable[int]] = {
        "field_07": (13,),  # ОГРН аудируемого лица
        "field_14": (13,),  # ОГРН аудиторской организации
        "field_15": (11,),  # ОРНЗ аудиторской организации
        "field_18": (11,),  # ОРНЗ руководителя аудита
        "field_21": (11,),  # ОРНЗ второго лица
        # field_19, field_22 (аттестаты) - без проверки длины, формат переменный
    }
    normalized = _normalize_digits(value_raw, expected_lengths_map.get(field_id))
    if not normalized:
        status = FIELD_STATUS_NO_DATA if status == FIELD_STATUS_OK else status
    
    # Формирование расширенного reasoning
    reasoning = [f"ask_qwen via qwen; page={page_num}"]
    if value_raw:
        reasoning.append(f"raw={value_raw}")
    if qwen_context:
        reasoning.append(f"context={qwen_context}")
    if qwen_explanation:
        reasoning.append(f"explanation={qwen_explanation}")

    if run_logger:
        # Логируем результат с context и explanation для диагностики
        log_parts = [f"ask_qwen result field={field_id} status={status} value={normalized or ''}"]
        if qwen_context:
            log_parts.append(f"context='{qwen_context}'")
        if qwen_explanation:
            log_parts.append(f"explanation='{qwen_explanation}'")
        run_logger(" ".join(log_parts))
    return ToolCallResult(status=status, value=normalized, reasoning=reasoning, page_num=page_num)


def tool_result_to_field_result(field_id: str, name: str, tool_res: ToolCallResult) -> FieldResult:
    """Convert ToolCallResult to FieldResult."""
    return FieldResult(
        field_id=field_id,
        name=name,
        status=tool_res.status,
        value=tool_res.value,
        reasoning=list(tool_res.reasoning),
        notes=[],
        meta={"page": tool_res.page_num} if tool_res.page_num is not None else None,
    )

