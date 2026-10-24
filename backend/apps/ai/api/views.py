from uuid import uuid4
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema
from apps.documents.exceptions import DocumentError
from ..services import answer_chat
from ..models import ChatResponseRecord
from .serializers import ChatRequest, ChatResponse, ChatErrorResponse, ChatFeedbackRequest


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
        description='Trả lời từ học liệu được phép và dẫn nguồn theo trang. Không hỗ trợ AI khi học viên đang làm bài kiểm tra. Gợi ý chỉ dành cho bài ôn tập.',
        request=ChatRequest,responses={200:ChatResponse,**{code:ChatErrorResponse for code in (400,401,403,404,409,429,503)}})
    def post(self,request):
        serializer=ChatRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        result=answer_chat(user=request.user,data=serializer.validated_data,request_id=self.request_id)
        ChatResponseRecord.objects.create(id=self.request_id, user=request.user)
        result['request_id'] = self.request_id
        return Response(result)


class ChatFeedbackView(ChatView):
    http_method_names = ['patch', 'options']

    @extend_schema(tags=['AI'], request=ChatFeedbackRequest, responses={200: ChatFeedbackRequest})
    def patch(self, request, answer_id):
        serializer = ChatFeedbackRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = ChatResponseRecord.objects.filter(pk=answer_id, user=request.user).first()
        if record is None:
            raise DocumentError('NOT_FOUND', 'Câu trả lời không khả dụng.', 404)
        record.rating = serializer.validated_data['rating']
        record.save(update_fields=['rating', 'updated_at'])
        return Response({'rating': record.rating})
