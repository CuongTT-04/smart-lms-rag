from uuid import uuid4
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema, PolymorphicProxySerializer, OpenApiExample
from apps.documents.exceptions import DocumentError
from ..services import answer_chat
from ..models import ChatResponseRecord
from .serializers import ChatRequest, ChatResponse, ChatErrorResponse, ChatFeedbackRequest, ConversationSelector
from .serializers import (ConversationMetadata, ConversationDetail, ConversationPage, ConversationPendingResponse)
from .serializers import SummaryTaskResponse
from ..conversations import (send_conversation, owned_conversation, list_conversations,
                             create_conversation, conversation_detail, metadata)


AI_ERRORS = {code: ChatErrorResponse for code in (400, 401, 403, 404, 409, 429, 503)}


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class ChatView(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes=[IsAuthenticated]
    http_method_names=['post','options']

    def initial(self, request, *args, **kwargs):
        self.request_id=str(uuid4())
        super().initial(request,*args,**kwargs)

    def handle_exception(self, exc):
        request_id=getattr(self,'request_id',str(uuid4()))
        if isinstance(exc,DocumentError):
            code=exc.code
            if exc.status==404: message='Tài nguyên không khả dụng hoặc bạn không có quyền truy cập.'
            elif exc.status==409: message='Học liệu hoặc quyền truy cập đã thay đổi. Vui lòng tải lại.'
            elif exc.status==400: message='Yêu cầu không hợp lệ. Vui lòng kiểm tra dữ liệu.'
            else: message=exc.message
            return Response({'request_id':request_id,'code':code,'message':message},status=exc.status)
        response=super().handle_exception(exc)
        code='UNAUTHENTICATED' if response.status_code==401 else 'THROTTLED' if response.status_code==429 else 'INVALID_REQUEST'
        message='Vui lòng đăng nhập lại.' if response.status_code==401 else 'Yêu cầu không hợp lệ. Vui lòng thử lại.'
        response.data={'request_id':request_id,'code':code,'message':message}
        return response

    @extend_schema(tags=['AI'],operation_id='ai_chat',summary='Hỏi đáp học liệu và gợi ý ôn tập',
        description='QA trả 200 hoặc 202 khi lượt hội thoại đang xử lý. Hint chỉ nhận bài PRACTICE và đề công khai. Summary tạo công việc 202, một tài liệu/tối đa 20 trang; dùng URL summaries để tiếp tục. TEST đang làm chặn AI. Lỗi index/Kaggle không phải thiếu căn cứ học liệu.',
        examples=[OpenApiExample('Gợi ý câu ôn tập', request_only=True, value={
            'mode':'hint', 'question':'Gợi ý cách đọc đề, không giải bài.',
            'course_id':'11111111-1111-4111-8111-111111111111',
            'assessment_id':'22222222-2222-4222-8222-222222222222',
            'question_id':'33333333-3333-4333-8333-333333333333'}),
            OpenApiExample('Tóm tắt một học liệu', request_only=True, value={
                'mode':'summary', 'question':'Tóm tắt nội dung học liệu.',
                'course_id':'11111111-1111-4111-8111-111111111111',
                'document_ids':['44444444-4444-4444-8444-444444444444'], 'page_start':1,
                'summary_request_id':'55555555-5555-4555-8555-555555555555'})],
        request=ChatRequest,responses={200:ChatResponse,202:PolymorphicProxySerializer(component_name='ChatPending', serializers=[ConversationPendingResponse, SummaryTaskResponse], resource_type_field_name=None),**AI_ERRORS})
    def post(self,request):
        serializer=ChatRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('conversation_id'):
            result, status = send_conversation(user=request.user, data=serializer.validated_data)
            return Response(result, status=status)
        result=answer_chat(user=request.user,data=serializer.validated_data,request_id=self.request_id)
        if serializer.validated_data['mode'] == 'summary':
            return Response(result, status=202)
        ChatResponseRecord.objects.create(id=self.request_id, user=request.user)
        result['request_id'] = self.request_id
        return Response(result)


class SummaryTaskView(ChatView):
    http_method_names = ['get', 'post', 'options']

    @extend_schema(tags=['AI'], operation_id='ai_summary_status', summary='Đọc tiến độ tóm tắt học liệu',
        description='Chỉ chủ công việc được đọc; kiểm lại quyền, TEST và phiên bản nguồn. PENDING/PROCESSING chưa có result. COMPLETED có kết quả; FAILED có error. Đọc trạng thái không gọi model.',
        responses={200:SummaryTaskResponse, **AI_ERRORS})
    def get(self, request, summary_id):
        from ..summary import descriptor, owned_task
        return Response(descriptor(owned_task(request.user, summary_id)))

    @extend_schema(tags=['AI'], operation_id='ai_summary_advance', request=None, summary='Tiếp tục một bước tóm tắt học liệu',
        description='Không nhận body. Một bước có lease 120 giây, timeout gọi gateway tối đa 100 giây. Trả 202 nếu còn việc, 200 khi COMPLETED/FAILED; HTTP 200 không đồng nghĩa thành công. Mất kết nối: GET cùng ID trước khi tiếp tục POST, không tạo công việc mới.',
        responses={200:SummaryTaskResponse, 202:SummaryTaskResponse, **AI_ERRORS})
    def post(self, request, summary_id):
        if request.data:
            raise DocumentError('INVALID_REQUEST', 'Bước tóm tắt không nhận nội dung từ client.', 400)
        from ..summary import advance_summary
        result = advance_summary(request.user, summary_id)
        return Response(result, status=200 if result['status'] in ('COMPLETED', 'FAILED') else 202)


class ChatFeedbackView(ChatView):
    http_method_names = ['patch', 'options']

    @extend_schema(tags=['AI'], summary='Đánh giá câu trả lời của trợ lý',
        description='Lưu hoặc bỏ đánh giá LIKE/DISLIKE cho câu trả lời của chính người dùng; kiểm lại quyền nếu thuộc hội thoại tài liệu.',
        request=ChatFeedbackRequest, responses={200: ChatFeedbackRequest, **AI_ERRORS})
    def patch(self, request, answer_id):
        serializer = ChatFeedbackRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = ChatResponseRecord.objects.filter(pk=answer_id, user=request.user).first()
        if record is None:
            raise DocumentError('NOT_FOUND', 'Câu trả lời không khả dụng.', 404)
        if record.turn_id:
            owned_conversation(request.user, record.turn.conversation_id)
        record.rating = serializer.validated_data['rating']
        record.save(update_fields=['rating', 'updated_at'])
        return Response({'rating': record.rating})


class ConversationListView(ChatView):
    http_method_names = ['get', 'post', 'options']

    @extend_schema(tags=['AI'], operation_id='ai_conversations_list', parameters=[ConversationSelector], responses={200: ConversationPage, **AI_ERRORS}, summary='Các phiên chat của tài liệu',
        description='Liệt kê hội thoại của chính người dùng trong tài liệu được phép; kiểm lại quyền và TEST. Phân trang bằng cursor; không trả lịch sử của tài khoản khác.')
    def get(self, request):
        raw = request.query_params.dict()
        cursor = raw.pop('cursor', None)
        if cursor and len(cursor) > 2000:
            raise DocumentError('INVALID_REQUEST', 'Trang lịch sử không hợp lệ.', 400)
        selector = ConversationSelector(data=raw)
        selector.is_valid(raise_exception=True)
        return Response(list_conversations(request.user, selector.validated_data, cursor))

    @extend_schema(tags=['AI'], request=ConversationSelector, responses={201: ConversationMetadata, **AI_ERRORS}, summary='Tạo phiên chat theo tài liệu',
        description='Tạo hội thoại gắn một tài liệu và bản công bố hiện hành. Backend tự kiểm quyền và TEST; không nhận lịch sử, phiên bản hoặc quyền do client khai báo.')
    def post(self, request):
        selector = ConversationSelector(data=request.data)
        selector.is_valid(raise_exception=True)
        conversation = create_conversation(request.user, selector.validated_data)
        return Response(metadata(conversation), status=201)


class ConversationDetailView(ChatView):
    http_method_names = ['get', 'options']

    @extend_schema(tags=['AI'], operation_id='ai_conversation_detail', responses={200: ConversationDetail, **AI_ERRORS}, summary='Lịch sử các lượt hỏi trong phiên chat',
        description='Đọc hội thoại của chính người dùng sau khi kiểm lại quyền, TEST và phiên bản tài liệu. Dùng before để đọc lượt cũ; không sinh lại kết quả đã lưu.')
    def get(self, request, conversation_id):
        raw = request.query_params
        try:
            if set(raw)-{'before'}:
                raise ValueError('fields')
            before = int(raw['before']) if 'before' in raw else None
            if before is not None and before < 1:
                raise ValueError('before')
        except (ValueError, TypeError) as exc:
            raise DocumentError('INVALID_REQUEST', 'Trang hội thoại không hợp lệ.', 400) from exc
        return Response(conversation_detail(request.user, conversation_id, before))
