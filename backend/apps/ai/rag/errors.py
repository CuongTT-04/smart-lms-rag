"""Public validation failures. Never expose generated text or provider exceptions."""

_MISSING = ('GENERATION_MISSING_CITATION', 'AI đã tạo câu trả lời nhưng thiếu dẫn nguồn từ học liệu nên chưa được hiển thị. Hãy gửi lại hoặc hỏi cụ thể hơn.')
_SOURCE = ('GENERATION_INVALID_CITATION', 'AI dẫn nguồn không có trong học liệu được cung cấp cho lượt hỏi này. Câu trả lời chưa được hiển thị để tránh dẫn nguồn sai. Hãy gửi lại câu hỏi.')
_FORMAT = ('GENERATION_INVALID_FORMAT', 'AI trả lời sai định dạng hoặc trộn câu trả lời với thông báo thiếu căn cứ. Câu trả lời chưa được hiển thị. Hãy gửi lại hoặc chia nhỏ câu hỏi.')
_CHOICE = ('GENERATION_CHOICE_MISMATCH', 'Lựa chọn AI đưa ra không khớp với các phương án trong câu hỏi. Câu trả lời chưa được hiển thị. Hãy gửi lại câu hỏi kèm đầy đủ phương án.')

VALIDATION_ERRORS = {
    'EMPTY_OUTPUT': ('GENERATION_EMPTY_RESPONSE', 'AI kết thúc xử lý nhưng không tạo được nội dung trả lời. Hãy gửi lại câu hỏi.'),
    'MISSING_CITATION': _MISSING,
    'UNKNOWN_CITATION': _SOURCE,
    'MIXED_OUTPUT_FORMAT': _FORMAT,
    'UNEXPECTED_CJK': ('GENERATION_WRONG_LANGUAGE', 'AI trả lời lẫn ngôn ngữ ngoài yêu cầu nên câu trả lời chưa được hiển thị. Hãy yêu cầu trả lời bằng tiếng Việt và thử lại.'),
    'CHOICE_FORMAT': _CHOICE,
    'CHOICE_LABEL_TEXT_MISMATCH': _CHOICE,
    'CHOICE_TEXT_NOT_VERBATIM': _CHOICE,
}
VALIDATION_ERROR_CODES = frozenset(code for code, _ in VALIDATION_ERRORS.values())


def public_validation_error(reason=None):
    code, message = VALIDATION_ERRORS.get(reason, (None, None)) if isinstance(reason, str) else (None, None)
    if code is None:
        code = 'INVALID_GENERATION'
        message = ('Câu trả lời đã bị chặn ở bước kiểm tra phản hồi; dịch vụ AI chưa cung cấp nguyên nhân chi tiết. '
                   'Hãy gửi lại hoặc chia nhỏ câu hỏi.')
    return code, message, 503
