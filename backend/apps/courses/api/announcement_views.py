import io
import uuid
import warnings
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.http import FileResponse
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from apps.courses.models import ClassroomAnnouncement
from apps.courses.enrollment_services import locked_course
from .serializers import StrictRequestSerializer
from .session_views import ClassroomSessionsView


class AnnouncementInput(StrictRequestSerializer):
    content = serializers.CharField(max_length=5000)
    link = serializers.URLField(max_length=2000, required=False, allow_blank=True, default='')
    image = serializers.FileField(required=False, write_only=True)

    def validate_link(self, value):
        if value and not value.lower().startswith(('https://', 'http://')):
            raise serializers.ValidationError('Link phải bắt đầu bằng https:// hoặc http://.')
        return value

    def validate_image(self, upload):
        if upload.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Ảnh phải nhỏ hơn hoặc bằng 5 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(upload) as source:
                    if source.format not in ('JPEG', 'PNG', 'WEBP'):
                        raise ValueError('Unsupported image format')
                    if source.width * source.height > 20000000:
                        raise ValueError('Image dimensions too large')
                    source.load()
                    image = ImageOps.exif_transpose(source).convert('RGBA' if 'A' in source.getbands() else 'RGB')
                    output = io.BytesIO()
                    image.save(output, format='PNG')
            if output.tell() > 5 * 1024 * 1024:
                raise ValueError('Image output too large')
            return ContentFile(output.getvalue(), name=f'{uuid.uuid4().hex}.png')
        except Exception as exc:
            raise serializers.ValidationError('Chọn ảnh JPG, PNG hoặc WebP hợp lệ, tối đa 5 MB và 20 triệu pixel.') from exc


class AnnouncementSerializer(serializers.ModelSerializer):
    has_image = serializers.SerializerMethodField()

    def get_has_image(self, obj) -> bool:
        return bool(obj.image)

    author_name = serializers.CharField(source='author.full_name', read_only=True)

    class Meta:
        model = ClassroomAnnouncement
        fields = ['id', 'classroom_id', 'author_name', 'content', 'link', 'has_image', 'created_at']
        read_only_fields = fields


class ClassroomAnnouncementsView(ClassroomSessionsView):
    serializer_class = AnnouncementSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(tags=['Classrooms'], operation_id='classroom_announcements_list', summary='Xem bảng tin của lớp', description='Giáo viên sở hữu khóa học và học viên ghi danh còn hiệu lực trong đúng lớp được đọc thông báo. Các thông báo được hiển thị mới nhất trước và không chia sẻ sang lớp khác.', responses=AnnouncementSerializer(many=True))
    def get(self, request, course_id, classroom_id):
        room = self.room(request, course_id, classroom_id)
        page = self.paginate_queryset(room.announcements.select_related('author'))
        return self.get_paginated_response(AnnouncementSerializer(page, many=True).data)

    @extend_schema(tags=['Classrooms'], operation_id='classroom_announcements_create', summary='Đăng thông báo của lớp', description='Chỉ giáo viên sở hữu khóa học được đăng thông báo trong lớp. Nội dung phải có ít nhất một ký tự khác khoảng trắng, tối đa 5000 ký tự và được lưu cùng người đăng, thời điểm đăng.', request=AnnouncementInput, responses={201: AnnouncementSerializer})
    def post(self, request, course_id, classroom_id):
        room = self.room(request, course_id, classroom_id, manage=True)
        serializer = AnnouncementInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        image = values.pop('image', None)
        announcement = ClassroomAnnouncement(classroom=room, author=request.user, **values)
        try:
            with transaction.atomic():
                locked_course(request.user, room.course)
                if image:
                    announcement.image.save(image.name, image, save=False)
                    announcement.image_content_type = 'image/png'
                announcement.save()
        except Exception:
            if image and announcement.image:
                announcement.image.delete(save=False)
            raise
        return Response(AnnouncementSerializer(announcement).data, status=201)


class ClassroomAnnouncementImageView(ClassroomSessionsView):
    http_method_names = ['get', 'head', 'options']
    @extend_schema(tags=['Classrooms'], operation_id='classroom_announcement_image', summary='Xem ảnh thông báo', description='Ảnh thông báo được lưu riêng tư và chỉ trả về khi người xem có quyền đọc đúng lớp. Mỗi lần xem đều yêu cầu xác thực JWT; không cung cấp đường dẫn media công khai.', responses={(200, 'image/png'): bytes})
    def get(self, request, course_id, classroom_id, announcement_id):
        room = self.room(request, course_id, classroom_id)
        item = room.announcements.filter(pk=announcement_id).first()
        if not item or not item.image:
            raise NotFound('Image unavailable.')
        try:
            stream = item.image.open('rb')
        except FileNotFoundError:
            raise NotFound('Image unavailable.')
        response = FileResponse(stream, content_type='image/png')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
